"""Independent audit of metrics, retained witnesses, experiment clocks and archived comparisons."""
from collections import Counter, defaultdict
import csv
import gzip
import json
import math
import statistics as st
import sys
import time
from pathlib import Path

from large75 import (HERE, PARETO, JMS, SOURCE, METHODS, SEEDS, BUDGET, BOUNDS, REF, TOL,
                     Config, digest, metrics, read, save, signature, validate)
from campaign75 import OUT, contract
from complete_front import front

REPORT = HERE / "review"
SMALL = PARETO / "runs/formal02"
S1 = PARETO / "runs/s1_refine01"
NAMES = dict(domain="领域搜索", nsga2="NSGA-II",moead="MOEA/D",fixed="固定结构 ε 扫描")


def rows(file):
    with file.open(encoding="utf-8-sig",newline="") as f:
        return list(csv.DictReader(f))


def write_table(file, records):
    with file.open("w",encoding="utf-8-sig",newline="") as f:
        w = csv.DictWriter(f,fieldnames=list(records[0]))
        w.writeheader()
        w.writerows(records)


def hypervolume(points,bounds):
    # Integrate vertical strips by x, independently of the original y-sweep.
    normalized = [tuple((t-lo)/(hi-lo) for t,(lo,hi) in zip(p,bounds)) for p in points]
    xs = sorted({x for x,y in normalized if x<REF[0] and y<REF[1]} | {REF[0]})
    return sum((v-u)*max(0, REF[1]-min(y for x,y in normalized if x<=u))
               for u,v in zip(xs,xs[1:]))


def loaded(path):
    with gzip.open(path,"rt",encoding="utf-8") as f:
        return json.load(f)


def checked_numeric_adapter():
    from contextlib import ExitStack
    from types import SimpleNamespace
    from unittest.mock import patch
    from large75 import PATTERNS, GridTiming
    from common import config
    from decoder import Decoder, Retiming
    from native import Native
    from witness import sparse_witness
    sys.path.append(str(PATTERNS/"audit"))
    import check_model as ck
    cfg=config("S1")
    decoder=Decoder(cfg)
    genes=(0,0,3,1,0)*decoder.n
    batch=decoder.build(genes,decoder.pairing(genes))
    batch.__class__=GridTiming
    sample=Retiming(batch,25).solve("A",None,15)
    # A common dyadic shift retains all physical resource differences and
    # supplies a genuinely non-integer complete-model test witness.
    shifts=[]
    for pattern,base in batch.blocks:
        # The constructive shifts already satisfy the selected action orders.
        shifts.extend(t+.5 for t in batch.initial[base:base+len(pattern.actions)])
    sample=batch.schedule(shifts)
    assert any(e["start"]%1 for e in sample["events"])
    cfg=Config(**sample["config"])
    native=Native(cfg,1,25)
    raw=sparse_witness(cfg,sample)
    def streamed(values):
        rows=ck.RowCheck(values)
        api=SimpleNamespace(Model=lambda name:rows, quicksum=sum)
        inst=ck.model.Integrated.__new__(ck.model.Integrated)
        with ExitStack() as stack:
            for module in (ck.model,ck.joint_pairing_model,ck.joint_chamber_cycle_model):
                stack.enter_context(patch.object(module,"scip",api))
            try:
                inst.__init__(cfg)
            except ck.RowsComplete:
                return rows.rows,sum(rows.types.values()),float(inst.secondary_objective)
        raise ValueError("Incomplete stream")
    try:
        stream=streamed(raw)
        assert native.warm(sample) and stream[:2]==(native.x.original_dimensions["constraints"],native.x.original_dimensions["variables"])
        assert stream[2]==metrics(sample,25)["secondary"]
        broken={**sample,"cmax":0}
        assert not native.warm(broken)
        try:
            streamed({**raw,"Cmax":0})
        except ValueError as e:
            assert "Row " in str(e)
        else:
            raise ValueError("Invalid Cmax accepted")
    finally:
        native.close()
    return dict(rows=stream[0],variables=stream[1],B=stream[2],passed_fractional=True,both_rejected_zero_cmax=True)


def small():
    from native import Native
    from common import ROOT, config
    REPORT.mkdir(exist_ok=True)
    protocol = read(SMALL/"protocol.json")
    assert all(digest(ROOT/path)==h for path,h in protocol["code"].items())
    policy=protocol["policy"]
    assert digest(policy["checkpoint"])==policy["sha256"] and digest(policy["config"])==policy["config_sha256"]
    warm = read(SMALL/"shared_initials/manifest.json")
    assert all(digest(SMALL/"shared_initials"/v["file"])==v["sha256"] for v in warm.values())
    table = rows(SMALL/"evaluation/runs.csv")
    registered = {v["id"]:v for v in table}
    raw = rows(SMALL/"evaluation/points.csv")
    bycase=defaultdict(list)
    for r in raw:
        bycase[r["case"]].append(r)
    per_run=defaultdict(list)
    begin=time.monotonic()
    count=unique=0
    for case, batch in bycase.items():
        cache=set()
        native=Native(config(case),1,25)
        try:
            for r in batch:
                path=SMALL/r["schedule"]
                assert digest(path)==r["sha256"]
                d=loaded(path)
                s=registered[r["id"]]
                m=metrics(d,float(r["weight"]))
                ab=m["cmax"],m["secondary"]
                assert all(abs(x-float(r[y]))<TOL for x,y in zip(ab,("A","B")))
                assert all(abs(m[x]-float(r[y]))<TOL for x,y in
                           (("wait_sum","L_sum"),("wait_max","L_max"),("rhythm","R")))
                assert float(r["admitted_s"])<=float(s["budget_s"]) and r["original_check"]=="True"
                key=signature(d)
                if key not in cache:
                    assert validate(d)["valid"] and native.warm(d)
                    cache.add(key)
                count+=1
                per_run[r["id"]].append(ab)
        finally:
            native.close()
        unique+=len(cache)
        elapsed=time.monotonic()-begin
        print(f"Small review: {count}/{len(raw)} schedules | failed 0 | elapsed {elapsed:.0f}s | ETA {elapsed*(len(raw)-count)/count:.0f}s",flush=True)
    for r in table:
        bounds=[(float(r[f"scale_{k}_min"]),float(r[f"scale_{k}_max"])) for k in ("A","B")]
        assert len(per_run[r["id"]])==int(r["front_count"])
        assert abs(hypervolume(per_run[r["id"]],bounds)-float(r["HV"]))<TOL
    main = {c:{m:st.median(float(r["HV"]) for r in table if
                            (r["case"],r["method"],r["suite"])==(c,m,"main"))
               for m in ("domain","rl_domain","epsilon","nsga2","moead","legacy")}
            for c in ("S1","M4","H4","H8","H16")}
    exact=rows(S1/"front_checked.csv")
    native=Native(config("S1"),1,25)
    try:
        for r in exact:
            path=S1/r["archived_file"]
            assert digest(path)==r["sha256"]
            d=loaded(path)
            m=metrics(d,25)
            assert native.warm(d) and validate(d)["valid"]
            assert abs(m["cmax"]-float(r["certified_A"]))<TOL and abs(m["secondary"]-float(r["certified_B"]))<TOL
    finally:
        native.close()
    assert len(table)==164 and count==699 and len(exact)==7 and sum(r["unsupported"]=="True" for r in exact)==3
    save(REPORT/"small.json",dict(runs=len(table),artifacts=count,distinct_checks_by_case=unique,initials=len(warm),
        source_files=len(protocol["code"]),checkpoint=policy["sha256"],main_HV=main,S1=read(S1/"independent_score.json"),
        checked_original_again=True,elapsed_s=time.monotonic()-begin))


def final_review():
    assert (REPORT/"small.json").exists() and (OUT/"pooled/front.json").exists()
    assert json.loads(json.dumps(contract()))==read(OUT/"protocol.json")
    cert=read(SOURCE/"original_row_audit/certificate.json")
    assert cert["original_rows"]==24271470
    reference=metrics(read(SOURCE/"result.json"),25)
    assert (round(reference["cmax"],6),round(reference["secondary"],6))==(8630,3932)
    table=[]
    pooled=[]
    submissions=0
    all_internal=[]
    reviewed=set()
    def check(path,sig,a,b):
        if sig not in reviewed:
            d=loaded(path)
            assert signature(d)==sig and validate(d)["valid"]
            replay=metrics(d,25)
            audit=read(OUT/"row_audit"/(sig+".json"))
            assert audit["physical_valid"] and audit["rows"]==24271470 and sum(audit["types"].values())==6764011
            assert audit["products"]==75 and audit["secondary_original"]==b and audit["metrics"]==replay
            assert replay["cmax"]==a and replay["secondary"]==b
            reviewed.add(sig)
    for m in METHODS:
        for seed in SEEDS:
            folder=OUT/f"{m}_{seed}"
            r=read(folder/"run.json")
            full=r["internal_nondominated"]
            selected=r["archive"]
            all_internal.extend(full)
            assert r["budget"]==BUDGET and len(selected)==min(7,len(full))
            assert sorted(map(tuple,full))==front(full)
            scan=[(a,b) for t,a,b in r["trace"] if 0<=t<=BUDGET]
            assert sorted(map(tuple,full))==front(scan)
            a_b=[(x["a"],x["b"]) for x in selected]
            assert list(a_b)==front(a_b) and tuple(full[0]) in a_b and tuple(full[-1]) in a_b
            for x in selected:
                assert x["found_s"]<=BUDGET
                check(folder/x["file"],x["schedule_sha256"],x["a"],x["b"])
            submissions+=len(selected)
            table.append(dict(method=m,seed=seed,budget=BUDGET,wall=r["elapsed"],last_accepted=max(x["found_s"] for x in selected),
                returned=len(selected),internal=len(full),HV=hypervolume(a_b,BOUNDS),
                min_A=min(p[0] for p in a_b),min_B=min(p[1] for p in a_b),
                A_B3750=min((a for a,b in a_b if b<=3750),default=None),
                A_B2949=min((a for a,b in a_b if b<=2949),default=None),
                lp_calls=r["stats"]["lp_attempts"],bound_skips=r["stats"].get("bound_screened",0),
                physical_admissions=r["stats"]["physically_validated"]))
    frontier=read(OUT/"pooled/front.json")
    assert [(r["a"],r["b"]) for r in frontier]==front(all_internal)
    for r in frontier:
        path=OUT/r["file"]
        a,b=r["a"],r["b"]
        check(path,r["schedule_sha256"],a,b)
        assert all(x["admitted_s"]<=BUDGET for x in r["observed_in"])
        d=loaded(path)
        m=metrics(d,25)
        pooled.append(dict(A=a,B=b,L_sum=m["wait_sum"],L_max=m["wait_max"],R=m["rhythm"],
                           rhythm_centers=m["rhythm_centers"],cycles=len(d["cycles"]),
                           method=r["method"],seed=r["seed"],file=r["file"],schedule_sha256=r["schedule_sha256"]))
    summary=[]
    for m in METHODS:
        group=[r for r in table if r["method"]==m]
        spread=[r["HV"] for r in group]
        summary.append(dict(method=m,HV_median=st.median(spread),HV_min=min(spread),HV_max=max(spread),
            A_median=st.median(r["min_A"] for r in group),B_median=st.median(r["min_B"] for r in group),
            B2949_hits=sum(r["A_B2949"] is not None for r in group),LP_median=st.median(r["lp_calls"] for r in group)))
    for name,items in (("runs75",table),("methods75",summary),("front75",pooled)):
        write_table(REPORT/(name+".csv"),items)
    parity=checked_numeric_adapter()
    save(REPORT/"verified.json",dict(small=read(REPORT/"small.json"),numeric_adapter=parity,large_runs=len(table),returned=submissions,
         distinct_original_checks=len(reviewed),full_observed=len(pooled),original_rows=24271470,variables=6764011,
         medians=summary,first=pooled[0],last=pooled[-1],warm=[8630,3932],sources_match=True,
         pooled_equals_all_internal=True,global_75_certified=False))
    print("Reviewed",len(table),"runs,",len(reviewed),"distinct original assignments,",len(pooled),"pooled front coordinates.",flush=True)


if __name__=="__main__":
    if len(sys.argv)==2 and sys.argv[1]=="small":
        small()
    else:
        final_review()

"""Validate endpoint bindings and aggregate completed seed groups."""
import csv
import os
from functools import lru_cache
from statistics import mean
from jobs import CELLS, EPS, HERE, JMS, METHODS, OUT, SEEDS, folder, publish_file, read, sha, write
from score import metrics


def export_csv(path,fields,rows):
    tmp=path.with_suffix(f".{os.getpid()}.tmp")
    with tmp.open("w",encoding="utf-8-sig",newline="") as f:
        writer=csv.DictWriter(f,fieldnames=fields,extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    publish_file(tmp,path)


def secondary(directory):
    doc=read(directory/"result.json")
    assert doc["eligible"] and doc["replay"]["valid"]
    assert doc["original_rows"]>0 and doc["replayed_rows"]>0
    assert all(sha(directory/name)==digest for name,digest in doc["files"].items())
    m=metrics(read(directory/"schedule.json"))
    assert all(abs(m[k]-v)<EPS for k,v in doc["measured"].items())
    assert doc["record"]["upper"] >= doc["record"]["lower"]-EPS
    assert doc["record"]["gap"]<=doc["target_gap"]+1e-8
    for parent in doc["parents"]:
        from pathlib import Path
        assert sha(Path(parent["schedule"]))==parent["schedule_sha256"]
        assert sha(Path(parent["assignment"]))==parent["assignment_sha256"]
    return doc


@lru_cache(None)
def check(key,complete_digest):
    d=folder(key)
    file=d/"complete.json"
    assert sha(file)==complete_digest
    doc=read(file)
    r=doc["report"]
    assert doc["key"]==key
    if key.startswith("t4_") or key.startswith("ref5_"):
        b=secondary(d/"B")
        if key.startswith("t4_"):
            assert sha(d/"B/result.json")==r["result_sha256"]
            assert r["measured"]==b["measured"] and r["record"]==b["record"]
        else:
            assert sha(d/"B/result.json")==r["new_B_sha256"] and r==read(d/"timing.json")
    elif key.startswith("primary_"):
        assert sha(d/"schedule.json")==r["schedule_sha256"] and sha(d/"assignment.json.gz")==r["assignment_sha256"]
        pr=read(d/"primary.json")
        assert pr["replay"]["valid"] and pr["rows"]>0
        assert abs(r["record"]["upper"]-metrics(read(d/"schedule.json"))["cmax"])<EPS
        assert r["record"]["upper"]<=1.01*r["record"]["lower"]+EPS
    else:
        schedule=d/"endpoint/schedule.json"
        assert sha(schedule)==r["schedule_sha256"] and sha(d/"endpoint/assignment.json.gz")==r["assignment_sha256"]
        assert read(d/"endpoint/primary.json")["replay"]["valid"]
        m=metrics(read(schedule))
        assert abs(m["secondary"]-r["f_B"])<EPS and abs(m["cmax"]-r["f_A"])<EPS
        ref=folder("ref5_"+str(r["seed"]))/"timing.json"
        assert r["key"]["reference"]==sha(ref)
        reference=read(ref)
        assert r["key"]["arm"]==r["arm"] and r["key"]["seed"]==r["seed"]
        assert r["calls"]>=0 and r["calls"]==int(r["calls"])
        assert abs(r["reference_s"]-reference["total_s"])<1e-5
        assert abs(r["reference_f_A"]-reference["f_A"])<EPS and abs(r["reference_f_B"]-reference["f_B"])<EPS
        assert r["witness_s"]<=r["observed_s"]+1e-5<=r["reference_s"]+2e-5
        reached=r["f_A"]<=reference["f_A"]+EPS and r["f_B"]<=reference["f_B"]+EPS
        assert (r["reason"]=="target")==reached
        assert r["reason"] in ("target","time_budget")
        expected=r["witness_s"] if reached else r["reference_s"]
        assert abs(r["observed_s"]-expected)<1e-5
    return r


def report():
    rows4=[]
    rows5=[]
    provenance5=[]
    for f in sorted((OUT/"runs").glob("*/complete.json")):
        key=f.parent.name
        r=check(key,sha(f))
        if key.startswith("t4_"):
            n,h,s,level=r["n"],r["H"],r["seed"],r["gap_percent"]
            if r["arm"]=="fixed":
                rows4.append(dict(level=level,n=n,H=h,seed=s,arm="A",**r["initial"],source=r["source"]))
            rows4.append(dict(level=level,n=n,H=h,seed=s,arm="AB" if r["arm"]=="fixed" else "B",
                              **r["measured"],lower=r["record"]["lower"],upper=r["record"]["upper"],
                              gap=r["record"]["gap"],source=str(f.relative_to(JMS))))
        if key.startswith("ref5_") or key.startswith("t5_"):
            if key.startswith("ref5_"):
                r=dict(r,observed_s=r["total_s"],used_s=r["total_s"],reason="reference")
            rows5.append(dict(r,source=str(f.relative_to(JMS))))
            provenance=dict(seed=r["seed"],arm=r["arm"],stage_A="new primary search",stage_B="not entered",
                            source=str(f.relative_to(JMS)),cut_calls=r["calls"])
            if key.startswith("ref5_"):
                provenance.update(stage_A="original certified full-method primary",stage_B="new fixed-structure solve",
                                  reused_primary_s=r["prep_seconds"]+r["A_seconds"],new_secondary_s=r["B_wall_seconds"])
                if HERE.name=="huber_residence_20261125":
                    provenance.update(stage_B="verified identical objective on every allowed retiming",
                                      new_secondary_s="",reused_secondary_s=r["B_wall_seconds"])
            else:
                hand=f.parent/"A_reuse.json"
                b=f.parent/"B_reuse.json"
                if hand.is_file():
                    h=read(hand)
                    provenance.update(stage_A="audited native primary prefix",primary_proof=str(hand.relative_to(JMS)),
                         primary_proof_sha256=sha(hand),reused_primary_s=h.get("restored_s",h.get("restored_seconds")))
                if r["stage"]=="B":
                    provenance["stage_B"]="new fixed-structure solve"
                    if HERE.name=="huber_residence_20261125" and hand.is_file():
                        provenance["stage_B"]="reused fixed solve with identically zero within-recipe spread"
                if b.is_file():
                    provenance.update(stage_B="constant objective shift on every allowed fixed retiming",
                                 secondary_proof=str(b.relative_to(JMS)),secondary_proof_sha256=sha(b))
            provenance5.append(provenance)
    metric_cols=["cmax","secondary","mean_residence","residence_range","clean_deficit"]
    if HERE.name=="huber_residence_20261125":
        metric_cols.append("huber_penalty")
    if HERE.name=="quota_objective_20261125":
        metric_cols+=["production_count","clean_count","quota_unused"]
    cols=["level","n","H","arm","seed",*metric_cols,"lower","upper","gap","source"]
    export_csv(OUT/"table4_seeds.csv",cols,rows4)
    means=[]
    for level in (1,10):
        for n,h in CELLS:
            if n==2 and level==10:
                continue
            for arm in ("A","B","AB"):
                same=[row for row in rows4 if (row["level"],row["n"],row["H"],row["arm"])==(level,n,h,arm)]
                complete={row["seed"] for row in same}==set(SEEDS)
                means.append(dict(level=level,n=n,H=h,arm=arm,completed=len(same),**(
                    {k:mean(row[k] for row in same) for k in metric_cols} if complete else {})))
    export_csv(OUT/"table4_means.csv",[*cols[:4],"completed",*metric_cols],means)
    fields=["seed","arm","f_A","f_B_handoff","f_B","observed_s","used_s","calls","reason","witness_s","source"]
    export_csv(OUT/"table5_seeds.csv",fields,rows5)
    export_csv(OUT/"table5_provenance.csv",["seed","arm","stage_A","stage_B","reused_primary_s","new_secondary_s",
               "reused_secondary_s","cut_calls","primary_proof","primary_proof_sha256","secondary_proof","secondary_proof_sha256","source"],provenance5)
    means5=[]
    for arm in ("full",*METHODS):
        same=[r for r in rows5 if r["arm"]==arm]
        complete={r["seed"] for r in same}==set(SEEDS)
        agg={}
        if complete:
            for k in ("f_A","f_B_handoff","f_B","observed_s","used_s","calls"):
                vals=[r[k] for r in same if r.get(k) is not None]
                agg[k]=mean(vals) if vals else None
            agg["handoffs"]=sum(r.get("f_B_handoff") is not None for r in same)
            agg["target_hits"]=sum(r["reason"]=="target" for r in same) if arm!="full" else None
        means5.append(dict(arm=arm,completed=len(same),**agg))
    export_csv(OUT/"table5_means.csv",["arm","completed","handoffs","target_hits",*fields[2:8]],means5)


if __name__=="__main__":
    report()

"""Revalidate saved event records, align seeds and compute manuscript quantities."""
import argparse
import csv
from pathlib import Path
from statistics import mean
import sys

from controls import JMS,OUT,ROOT,cell,matched,product,read,save,sha
from objective16 import register

EPS=2e-4
NAMES=("cmax","secondary","wait_sum","wait_max","rhythm","rhythm_centers")
LEVELS={"10pct":.1,"1pct":.01,"0p01pct":.0001}
OLD=JMS/"results/product_wait_20261122"

def mean_metrics(rows):
    return {k:mean(e[k] for e in rows) for k in NAMES}

def csv_write(name,rows):
    with (OUT/name).open("w",encoding="utf-8-sig",newline="") as f:
        keys=list(dict.fromkeys(k for row in rows for k in row))
        writer=csv.DictWriter(f,fieldnames=keys)
        writer.writeheader();writer.writerows(rows)

def verified(path):
    e=read(path)
    s=path.with_name("schedule.json")
    if not s.exists():s=ROOT/e["job"]["schedule"]
    for filename,h in e["files"].items():assert sha(path.with_name(filename))==h
    assert sha(ROOT/e["job"]["assignment"])==e["job"]["assignment_sha256"]
    assert sha(ROOT/e["job"]["schedule"])==e["job"]["schedule_sha256"]
    m=product.product_metrics(read(s))
    assert e["replay"]["valid"] and all(abs(m[k]-e["measured"][k])<EPS for k in NAMES)
    return e

def source_row(p,metrics,**extra):
    return dict(record=p.relative_to(ROOT).as_posix(),**extra,**{k:metrics[k] for k in NAMES})

def grid():
    rows=[]; normalized={}
    for size,section in ((2,"grid2"),(4,"grid4"),(None,"grid_2x2")):
        for path in (OUT/section).glob("*/result.json"):
            d=read(path);a=d["a"];r=d["primary"]
            assert r["gap"]<=LEVELS[a]+1e-9
            for b,entry in d["results"].items():
                e=verified(path.parent/b/"runs/endpoint/result.json")
                assert e["eligible"] and e["record"]["gap"]<=LEVELS[b]+1e-9
                assert r["lower"]-EPS <= e["measured"]["cmax"] <= r["upper"]+EPS
                rows.append(source_row(path,e["measured"],size=size or d["size"],case=d["case"],gA=a,gB=b,
                                       handoff_A=r["upper"],lower_A=r["lower"],actual_gap_A=r["gap"],
                                       actual_gap_B=e["record"]["gap"]))
    cases={r["case"] for r in rows}
    assert len(cases)==6 and len(rows)==54
    assert {(r["case"],r["gA"],r["gB"]) for r in rows} == {
        (c,a,b) for c in cases for a in LEVELS for b in LEVELS}
    for a in LEVELS:
        for b in LEVELS:
            scores=[]
            for c in cases:
                group=[r for r in rows if r["case"]==c]
                row=next(r for r in group if r["gA"]==a and r["gB"]==b)
                scores.append([row[k]/max(1,min(x[k] for x in group)) for k in ("cmax","secondary")])
            normalized[a,b]=tuple(round(mean(x[i] for x in scores),6) for i in (0,1))
    chosen=min(normalized,key=lambda t:(*normalized[t],-LEVELS[t[0]],-LEVELS[t[1]]))
    csv_write("thresholds.csv",rows)
    return list(chosen)

def attempts(suite):
    paths=sorted((OUT/suite).glob("*/result.json"))
    paths+=sorted((OUT/"retries"/suite).glob("*/*/result.json"))
    return paths

def objectives(strict):
    register()
    data={}
    rows=[]
    with (OLD/"corrected_results.csv").open(encoding="utf-8-sig",newline="") as f:
        for row in csv.DictReader(f):
            k=row["job"].split("__")
            if len(k)!=4 or k[0]!="matched" or k[1] not in matched.SMALL or row["eligible"]!="True":continue
            _,case,seed,arm=k;path=ROOT/row["source"];e=verified(path)
            old=read(matched.OUT/"__".join(k[1:])/"result.json")
            start=old["input_sha256"]
            assert start==matched.CASES[case]["assignment_sha256"]
            rows.append(source_row(path,e["measured"],case=case,seed=int(seed[1:]),arm=arm,eligible=True,start=start))
    for p in attempts("objectives")+attempts("objectives16"):
        d=read(p);case,arm=d["case"],d["arm"]
        if arm!="A":
            e=verified(p.parent/"secondary/runs/endpoint/result.json")
            if arm in ("B","J"):assert e["job"]["assignment_sha256"]==d["start"]
            else:assert e["job"]["assignment_sha256"]==sha(p.parent/"primary/assignment.json.gz")
            m=e["measured"]
        else:
            stage=read(p.parent/"primary/primary.json")
            assert stage["replay"]["valid"] and stage["schedule_sha256"]==sha(p.parent/"primary/schedule.json")
            m=product.product_metrics(read(p.parent/"primary/schedule.json"))
        assert all(abs(d["metrics"][k]-m[k])<EPS for k in NAMES)
        assert d["start"]==matched.CASES[case]["assignment_sha256"]
        rows.append(source_row(p,m,case=case,seed=d["seed"],arm=arm,eligible=d["eligible"],start=d["start"]))
    for r in rows:
        if r["eligible"]:data.setdefault((r["case"],r["seed"],r["arm"]),r)
    csv_write("objective_runs.csv",rows)
    summary={}
    for case in sorted({r["case"] for r in rows}):
        seeds=[s for s in (1,2,3) if all((case,s,a) in data for a in ("A","B","J","AB"))]
        if strict:assert seeds==[1,2,3],(case,seeds)
        if seeds:summary[case]=dict(seeds=seeds,arms={a:mean_metrics([data[case,s,a] for s in seeds]) for a in ("A","B","J","AB")})
    if strict:assert len(summary)==5
    return summary

def ablations(strict):
    rows=[];by_key={}
    suites=("ablations_verified",) if strict else ("ablations_verified","mixed16","raw_policies")
    for suite in suites:
        for p in attempts(suite):
            d=read(p);s=d["seed"]
            arm=d["arm"]
            if suite=="ablations_verified":
                assert d["feasibility_tolerance"]==1e-8 and (ROOT/d["primary_source"]/"primary.json").exists()
            prep="raw" if arm.startswith("plain_") else "prepared"
            assert d["initial"]==sha(OUT/"mixed16"/f"s{s}/raw/assignment.json.gz")
            assert d["start"]==sha(OUT/"mixed16"/f"s{s}"/prep/"assignment.json.gz")
            e=verified(p.parent/"B/runs/endpoint/result.json")
            assert d["physical_replay"]["valid"]
            assert all(abs(d["metrics"][k]-e["measured"][k])<EPS for k in NAMES)
            stages=[r for r,_ in d["stages"]]
            row=source_row(p,e["measured"],arm=arm,seed=s,eligible=d["eligible"],
                           callback_calls=sum(r["policy_calls"] or 0 for r in stages),
                           start=d["start"],first_cmax=stages[-1]["upper"],first_lower=stages[-1]["lower"])
            rows.append(row)
            if d["eligible"]:by_key.setdefault((arm,s),row)
    csv_write("ablation_runs.csv",rows)
    arms=sorted({r["arm"] for r in rows})
    summary={}
    for arm in arms:
        seeds=[s for s in (1,2,3) if (arm,s) in by_key]
        if strict:assert seeds==[1,2,3],(arm,seeds)
        if seeds:
            rs=[by_key[arm,s] for s in seeds]
            summary[arm]=dict(seeds=seeds,**mean_metrics(rs),calls=[r["callback_calls"] for r in rs],
                              first_cmax=mean(r["first_cmax"] for r in rs),first_lower=mean(r["first_lower"] for r in rs))
    if strict:assert len(arms)==14
    return summary

def rhythm():
    rows=[]
    for p in sorted((OUT/"mixed_rhythm").glob("*/result.json")):
        d=read(p)
        for w,entry in d["weights"].items():
            e=verified(p.parent/f"w{w}/runs/endpoint/result.json")
            assert e["eligible"] and e["job"]["assignment_sha256"]==d["assignment_sha256"]
            rows.append(source_row(p,e["measured"],seed=d["seed"],weight=w))
    assert len(rows)==12
    csv_write("rhythm_runs.csv",rows)
    return {w:mean_metrics([r for r in rows if r["weight"]==w]) for w in ("0","5","25","100")}

if __name__=="__main__":
    strict="--partial" not in sys.argv
    result=dict(grid_choice=grid(),rhythm=rhythm(),objectives=objectives(strict),ablations=ablations(strict))
    save(OUT/("summary.json" if strict else "progress_summary.json"),result)
    print(result["grid_choice"],list(result["objectives"]),len(result["ablations"]))

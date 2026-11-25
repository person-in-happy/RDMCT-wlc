"""Foreground queues. Relaunch with table4 or table5 to adopt active jobs and resume missing cells."""
import csv
from datetime import datetime
import json
import msvcrt
import os
from pathlib import Path
import subprocess
import sys
import time
from statistics import mean

import psutil

HERE=Path(__file__).resolve().parent
JMS=HERE.parents[1]
ROOT=JMS.parent
RUNROOT=JMS/"results"
LEGACY=RUNROOT/"table4_residence100_20261123"
TABLE4_CASES=((4,3),(4,10),(8,3),(8,10))
TABLE4_SEEDS=(1,2,3)
TABLE4_ARMS=("A","B","AB")
TABLE4_TOTAL=len(TABLE4_CASES)*len(TABLE4_SEEDS)*len(TABLE4_ARMS)
METHODS=("full","hem","scip_default","no_rerank","no_spbs")
A3C="G:/conda/envs/a3cenv/python.exe"
CP="G:/conda/python.exe"

def read(p):
    return json.loads(p.read_text(encoding="utf-8-sig"))

def write(p,doc):
    tmp=p.with_suffix(".tmp")
    tmp.write_text(json.dumps(doc,ensure_ascii=False,indent=2),encoding="utf8")
    tmp.replace(p)

def csv_file(path,fields,rows):
    tmp=path.with_suffix(".tmp")
    with tmp.open("w",encoding="utf-8-sig",newline="") as f:
        writer=csv.DictWriter(f,fieldnames=fields,extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    tmp.replace(path)

def endpoint(out,n,h,s,arm):
    rel=Path("runs")/f"D_n{n}_H{h}_mixed_dual__s{s}"/arm/"endpoint.json"
    return LEGACY/rel if (LEGACY/rel).is_file() else out/rel

def report(out,group):
    values=[]
    means=[]
    if group=="table5":
        fields=["arm","f_A","f_B_handoff","f_B","total_s","calls"]
        for arm in METHODS:
            rows=[read(p) for p in sorted(out.glob(f"runs/s*_{arm}/1pct/timing.json"))]
            values.extend(rows)
            means.append(dict(arm=arm,completed=len(rows),**({k:mean(r[k] for r in rows) for k in fields[1:]} if {r["seed"] for r in rows}=={1,2,3} else {})))
        csv_file(out/"table5.csv",["arm","completed",*fields[1:]],means)
    else:
        fields=["n","H","arm","f_A","f_B"]
        for n,h in TABLE4_CASES:
            for arm in TABLE4_ARMS:
                rows=[]
                for s in TABLE4_SEEDS:
                    p=endpoint(out,n,h,s,arm)
                    if p.exists():
                        r=read(p)
                        assert r["target"]==.10 and r["actual_gap"]<=.10+1e-9
                        rows.append(dict(n=n,H=h,seed=s,arm=arm,f_A=r["metrics"]["cmax"],f_B=r["metrics"]["secondary"],source=str(p.relative_to(JMS))))
                values.extend(rows)
                means.append(dict(n=n,H=h,arm=arm,completed=len(rows),**({k:mean(r[k] for r in rows) for k in ("f_A","f_B")} if len(rows)==3 else {})))
        csv_file(out/"table4.csv",[*fields[:3],"completed",*fields[3:]],means)
    if values:
        csv_file(out/"verified_runs.csv",list(values[0]),values)
    return len(values)

def main(group):
    is5=group=="table5"
    out=RUNROOT/("table5_one_percent_20261124" if is5 else "table4_three_arms_20261124")
    out.mkdir(parents=True,exist_ok=True)
    logs=out/"logs"
    logs.mkdir(exist_ok=True)
    lock=(out/"controller.lock").open("a+b")
    lock.seek(0)
    msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
    script=(HERE.parent/"four_gap_ablation_20261123/one_percent.py") if is5 else HERE/"three_arms.py"
    jobs=[(str(seed),method) for seed in (1,2,3) for method in METHODS] if is5 else [
            (str(n),str(h),str(s),a) for s in TABLE4_SEEDS for n,h in TABLE4_CASES for a in ("A","B")]
    def done(j):
        if is5: return (out/f"runs/s{j[0]}_{j[1]}/1pct/timing.json").is_file()
        n,h,s=map(int,j[:3])
        return all(endpoint(out,n,h,s,a).is_file() for a in (("A","AB") if j[3]=="A" else ("B",)))
    active={}
    failed={}
    for p in psutil.process_iter(["name","cmdline"]):
        args=p.info["cmdline"] or []
        if p.info["name"] and p.info["name"].lower()=="python.exe" and str(script) in args:
            j=tuple(args[args.index(str(script))+1:])
            if j in jobs: active[j]=p
    maximum=15 if is5 else TABLE4_TOTAL
    while True:
        for j,p in list(active.items()):
            if not p.is_running():
                del active[j]
                if not done(j): failed[j]="see latest worker log"
        for j in jobs:
            if done(j) or j in active or j in failed: continue
            if len(active)>=(4 if is5 else 3): break
            if psutil.virtual_memory().available/1024**3 < 3.8: continue
            args=[A3C if is5 else CP,"-B","-u","-X","utf8",str(script),*j]
            with (logs/("-".join(j)+f"-{time.time_ns()}.log")).open("w") as log:
                active[j]=psutil.Popen(args,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
        count=report(out,group)
        at=datetime.now().astimezone().isoformat(timespec="seconds")
        state=dict(at=at,pid=os.getpid(),verified=count,expected=maximum,
                   active={" ".join(j):p.pid for j,p in active.items()},failures={" ".join(j):v for j,v in failed.items()})
        write(out/"progress.json",state)
        print(at,group,f"{count}/{maximum} verified | {len(active)} active | {len(failed)} failed | ETA pending gap convergence",flush=True)
        if count==maximum or (not active and all(done(j) or j in failed for j in jobs)): break
        time.sleep(8)

if __name__=="__main__":
    if sys.argv[1] not in ("table4","table5"): raise ValueError("Choose table4 or table5")
    main(sys.argv[1])

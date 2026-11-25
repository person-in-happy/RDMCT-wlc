"""Visible first-threshold campaign with separate capacity for projected and native searches."""
import csv
from datetime import datetime
import msvcrt
import os
from pathlib import Path
from statistics import mean
import subprocess
import sys
import time

import psutil
from inputs import CASES, CP, HERE, OLD, OUT, ROOT, SCIP, TAU, case_id, product, read, save, sha, validate


def refresh(cases=CASES):
    selected_cases={case_id(n,h) for n,h in cases}
    rows=[]
    for p in (OUT/"runs").glob("*/*/endpoint.json"):
        d=read(p)
        if d["case"] not in selected_cases:
            continue
        folder=OUT/d["path"]
        spec=read(OUT/"inputs"/d["case"]/"input.json")
        assert d["start"]==spec["assignment_sha256"]
        assert sha(folder/"schedule.json")==d["schedule_sha256"] and sha(folder/"assignment.json.gz")==d["assignment_sha256"]
        s=read(folder/"schedule.json")
        assert s["config"]==spec["config"] and validate(s)["valid"]
        metrics=product.product_metrics(s)
        assert all(abs(metrics[k]-v)<2e-4 for k,v in d["metrics"].items()) and d["actual_gap"]<=TAU+1e-9
        if d["arm"]=="AB":
            assert d["parent"]==sha(p.parent.parent/"A/endpoint.json")
        rows.append(dict(case=d["case"],seed=d["seed"],arm=d["arm"],f_A=metrics["cmax"],f_B=metrics["secondary"],
                         upper=d["record"]["upper"],lower=d["record"]["lower"],gap=d["actual_gap"],schedule_sha256=d["schedule_sha256"]))
    groups=[]
    for n,h in cases:
        group={"case":case_id(n,h)}
        for arm in ("A","B","J","AB"):
            selected=[v for v in rows if v["case"]==group["case"] and v["arm"]==arm]
            if {v["seed"] for v in selected}=={1,2,3}:
                for metric in ("f_A","f_B"):
                    group[f"{arm}_{metric}"]=mean(v[metric] for v in selected)
        groups.append(group)
    for name,data,fields in (("endpoints",rows, list(rows[0]) if rows else []),
                             ("table4_10pct",groups,["case"]+[f"{a}_{k}" for a in ("A","B","J","AB") for k in ("f_A","f_B")])):
        if not fields:
            continue
        tmp=OUT/(name+".tmp")
        with tmp.open("w",encoding="utf-8-sig",newline="") as f:
            w=csv.DictWriter(f,fieldnames=fields)
            w.writeheader()
            w.writerows(data)
        tmp.replace(OUT/(name+".csv"))
    return len(rows)


def main():
    lock=(OUT/"controller.lock").open("a+b")
    lock.seek(0)
    msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
    jobs=[(n,h,seed,arm) for seed in (1,2,3) for n,h in CASES for arm in ("A","J","B")]
    # Fast analytic checks for all three four-wafer seeds can finish before larger projections.
    jobs.sort(key=lambda j:(j[3]=="A" and j[0]!=4,j[3]=="A" and j[0]==16))
    protocol=dict(cases=[read(OUT/"inputs"/case_id(*key)/"input.json") for key in CASES],seeds=[1,2,3],
                  relative_gap=TAU,active_level="10pct",deferred_levels=[.01,.0001],seconds=None,
                  original_scope=sha(OLD/"ten_percent/switch_from_previous.json"),
                  arms=["A","B","J","AB"],threads=1,max_active=5,expected=60,
                  source_sha256={p.name:sha(p) for p in HERE.glob("*.py")})
    path=OUT/"protocol.json"
    if path.exists() and read(path)!=protocol:
        raise ValueError("A different protocol is already registered")
    save(path,protocol)
    def done(j):
        n,h,s,a=j
        base=OUT/"runs"/f"{case_id(n,h)}__s{s}"
        return (base/a/"endpoint.json").is_file() and (a!="A" or (base/"AB/endpoint.json").is_file())
    pending=[j for j in jobs if not done(j)]
    active={}
    failed={}
    start=time.monotonic()
    count=-1
    while pending or active:
        for j,(proc,stream,_) in list(active.items()):
            if proc.poll() is not None:
                stream.close()
                del active[j]
                if proc.returncode or not done(j):
                    failed[str(j)]=dict(code=proc.returncode,log=stream.name)
        for j in pending[:]:
            n,h,s,a=j
            if len(active)>=5:
                break
            cp=a=="A"
            if sum((k[3]=="A")==cp for k in active)>=(2 if cp else 3):
                continue
            reserve=6.8 if n==16 else (4.2 if n==8 else 2.8)
            free=psutil.virtual_memory().available/1024**3
            for proc,_,mb in active.values():
                try:
                    free-=max(0,mb-psutil.Process(proc.pid).memory_info().rss/1024**3)
                except psutil.NoSuchProcess:
                    continue
            if free<reserve+2.0:
                continue
            logs=OUT/"logs"
            logs.mkdir(exist_ok=True)
            stream=(logs/f"{case_id(n,h)}__s{s}__{a}-{time.time_ns()}.log").open("w",encoding="utf8")
            cmd=[CP if cp else SCIP,"-B","-u","-X","utf8",str(HERE/"worker.py"),*map(str,j)]
            proc=subprocess.Popen(cmd,cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT)
            active[j]=(proc,stream,reserve)
            pending.remove(j)
        observed=sum(1 for _ in (OUT/"runs").glob("*/*/endpoint.json"))
        if observed!=count:
            count=refresh()
        eta=(time.monotonic()-start)*(60-count)/count if count else None
        state=dict(at=datetime.now().astimezone().isoformat(timespec="seconds"),pid=os.getpid(),verified=count,expected=60,
                   active={str(j):p.pid for j,(p,_,_) in active.items()},queued=len(pending),failures=failed,
                   eta_seconds_from_average=eta,state="running" if pending or active else ("incomplete" if failed else "completed"))
        save(OUT/"progress.json",state)
        print(state["at"], f"{count}/60 verified, {len(active)} active, {len(failed)} failed,",
              f"rough ETA {eta/3600:.2f} h" if eta is not None else "ETA pending",flush=True)
        if pending or active:
            time.sleep(10)
    assert count==60 and not failed


if __name__=="__main__":
    main()

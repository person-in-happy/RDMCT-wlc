"""Foreground, resumable 1% Table 4 campaign. Run with G:/conda/python.exe."""
from datetime import datetime
from functools import lru_cache
import msvcrt
import os
from pathlib import Path
from statistics import mean, median
import subprocess
import sys
import time

import ortools
import psutil
from bench import ARMS, CASES, GAP, HERE, OUT, SEEDS, cell, group, old, preparation, product, read, save, sha, validate
from queue_runs import csv_file

JOBS=[(n,h,s,a) for a in ("B","A") for n,h in CASES for s in SEEDS]
TOTAL=len(CASES)*len(SEEDS)*len(ARMS)
FIELDS=["n","H","seed","arm","f_A","f_B","lower","upper","actual_gap","source"]


def path(n,h,s,a):
    return OUT/"runs"/f"{group(n,h)}__s{s}"/a/"endpoint.json"


def done(n,h,s,a):
    return path(n,h,s,a).is_file() and (a!="A" or path(n,h,s,"AB").is_file())


@lru_cache(None)
def verified(n,h,s,a,endpoint_hash):
    f=path(n,h,s,a)
    r=read(f)
    inp=read(OUT/"inputs"/group(n,h)/"input.json")
    assert sha(f)==endpoint_hash and (r["case"],r["seed"],r["arm"])==(group(n,h),s,a)
    assert r["start"]==inp["assignment_sha256"] and r["target"]==GAP
    loc=OUT/r["path"]
    assert sha(loc/"schedule.json")==r["schedule_sha256"] and sha(loc/"assignment.json.gz")==r["assignment_sha256"]
    d=read(loc/"schedule.json")
    assert d["config"]==inp["config"] and validate(d)["valid"]
    scores=product.product_metrics(d)
    bound=r["record"]
    actual=old.worker.gap(bound["upper"],bound["lower"])
    assert abs(actual-r["actual_gap"])<1e-10 and actual<=GAP+1e-9 and scores==r["metrics"]
    assert abs(scores["cmax" if a=="A" else "secondary"]-bound["upper"])<cell.EPS
    if a=="AB":
        af=path(n,h,s,"A")
        parent=read(af)
        sub=read(loc/"result.json")
        assert r["parent"]==sha(af) and sub["job"]["assignment_sha256"]==parent["assignment_sha256"]
        assert sub["eligible"] and sub["replay"]["valid"] and scores["cmax"]<=parent["metrics"]["cmax"]+cell.EPS
    return dict(n=n,H=h,seed=s,arm=a,f_A=scores["cmax"],f_B=scores["secondary"],
                lower=bound["lower"],upper=bound["upper"],actual_gap=actual,source=str(f.relative_to(OUT)))


def report():
    rows=[]
    lines=["# 表4　1%间隙下的目标对照","",
           "各单元依次列出同一排程的工期和工艺目标（秒）。按已核验种子取均值，括号后的数字为已完成种子数。","",
           "| 产品片数 | 清洁阈值 $H$ | 仅优化 $f_A$ | 仅优化 $f_B$ | 两阶段 |",
           "|---:|---:|---:|---:|---:|"]
    for n,h in CASES:
        cells=[]
        for a in ARMS:
            sample=[verified(n,h,s,a,sha(path(n,h,s,a))) for s in SEEDS if path(n,h,s,a).exists()]
            rows.extend(sample)
            cells.append(f"({mean(r['f_A'] for r in sample):.2f}, {mean(r['f_B'] for r in sample):.2f})　{len(sample)}/3" if sample else "—")
        lines.append("| "+" | ".join([str(n),str(h),*cells])+" |")
    csv_file(OUT/"verified_runs.csv",FIELDS,rows)
    lines+=["",f"已核验 {len(rows)}/{TOTAL} 项。"]
    report_file=OUT/"TABLE4_CN.md"
    temp=report_file.with_suffix(".tmp")
    temp.write_text("\n".join(lines)+"\n",encoding="utf-8")
    temp.replace(report_file)
    return len(rows)


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    lock=(OUT/"controller.lock").open("a+b")
    lock.seek(0)
    msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
    for n,h in CASES:preparation(n,h)
    manifest=dict(cases=[list(c) for c in CASES],seeds=list(SEEDS),arms=list(ARMS),A_gap=GAP,B_gap=GAP,
                  inputs={group(n,h):sha(OUT/"inputs"/group(n,h)/"input.json") for n,h in CASES},
                  sources={p.name:sha(p) for p in (HERE/"bench.py",HERE/"primary.py",Path(old.__file__),Path(old.worker.__file__))},
                  common_pool="Identical feasible archive pool for all arms per case. A prioritizes f_A. Free B may select its zero-cost witness. AB uses the exact same-seed A endpoint.",
                  proof="Fresh projected bounds on each case configuration; physical upper bounds checked against unrestricted native model.",
                  residence="100 s nonprocessing",objectives="product return; product wait sum + 10 max product wait + 25 pitch",
                  ortools=ortools.__version__,threads=1,concurrency=4,wafer2="LP1: one 4x1; LP2: one 2x2; D=8, H=3")
    manifestfile=OUT/"protocol.json"
    if manifestfile.exists() and read(manifestfile)!=manifest:raise ValueError("Campaign protocol changed")
    save(manifestfile,manifest)
    logs=OUT/"logs"
    logs.mkdir(exist_ok=True)
    batch=HERE/"bench.py"
    active={}
    failed={}
    for p in psutil.process_iter(["name","cmdline"]):
        args=p.info["cmdline"] or []
        if str(batch) not in args:continue
        tail=args[args.index(str(batch))+1:]
        if len(tail)==5 and tail[0]=="run":
            j=(*map(int,tail[1:4]),tail[4])
            if j in JOBS:active[j]=p
    attempts={}
    while True:
        for j,p in list(active.items()):
            if p.is_running():continue
            del active[j]
            if not done(*j):
                if attempts.get(j,0)>=2:failed[j]="check latest log"
        for j in JOBS:
            if len(active)>=4:break
            if done(*j) or j in active or j in failed:continue
            if psutil.virtual_memory().available<4*1024**3:break
            attempts[j]=attempts.get(j,0)+1
            with (logs/("_".join(map(str,j))+f"_{time.time_ns()}.log")).open("w") as log:
                active[j]=psutil.Popen([sys.executable,"-u","-B","-X","utf8",str(batch),"run",*map(str,j)],
                                       cwd=HERE.parents[2],stdout=log,stderr=subprocess.STDOUT)
        count=report()
        now=datetime.now().astimezone().isoformat(timespec="seconds")
        live={}
        for j,p in active.items():
            f=path(*j).with_name("search.json")
            state=read(f) if f.exists() else {}
            live[" ".join(map(str,j))]=dict(pid=p.pid,wall_s=round(time.time()-p.create_time(),1),
                                            lower=state.get("lower"),upper=state.get("upper"))
        errors={" ".join(map(str,j)):v for j,v in failed.items()}
        # Gap certification has a long tail. Estimate using completed A jobs at
        # the same scale, not the near-instant zero-cost reuse jobs.
        a_remaining=[j for j in JOBS if j[-1]=="A" and not done(*j)]
        per_scale={}
        for n,h,s,a in JOBS:
            if a=="A" and done(n,h,s,a):
                per_scale.setdefault(n,[]).append(read(path(n,h,s,a))["record"]["seconds"])
        eta=(sum(median(per_scale[j[0]]) for j in a_remaining)/4 if all(j[0] in per_scale for j in a_remaining) else None)
        save(OUT/"progress.json",dict(at=now,pid=os.getpid(),verified=count,expected=TOTAL,active=live,failures=errors,eta_s=eta))
        estimate="pending same-size completions" if eta is None else f"~{eta/60:.1f} min"
        print(now,f"{count}/{TOTAL} verified | {len(active)} active | {len(failed)} failed | ETA {estimate}",live,flush=True)
        if count==TOTAL or (not active and all(done(*j) or j in failed for j in JOBS)):break
        time.sleep(5)


if __name__=="__main__":
    main()

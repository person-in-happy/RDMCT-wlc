"""Visible, resumable controller for the paired Table 5 benchmark."""
from datetime import datetime
from functools import lru_cache
import msvcrt
import os
from pathlib import Path
from statistics import mean
import subprocess
import time

import psutil

from matched_ablation import OUT, TOL, load_reference, old, reference, solve
from queue_runs import A3C, HERE, ROOT, csv_file

ARMS=("no_rerank","no_spbs","hem","scip_default")
NAMES=dict(full="完整方法",no_rerank="去掉重排序",no_spbs="去掉初始解策略",hem="HEM",scip_default="SCIP 默认策略")
JOBS=[(3,"full")]+[(s,a) for s in (1,2,3) for a in ARMS]
FIELDS="seed arm reference_f_A reference_f_B reference_s f_A f_B_handoff f_B observed_s used_s calls reason witness_s exhausted".split()

def location(seed,arm):
    return reference(seed)/"timing.json" if arm=="full" else OUT/f"runs/s{seed}_{arm}/result.json"

def arguments(seed,arm):
    if arm=="full":return [str(HERE/"matched_reference.py"),str(seed)]
    return [str(HERE/"matched_ablation.py"),str(seed),arm]

@lru_cache(None)
def verified(seed,arm):
    ref=load_reference(reference(seed))
    if seed in (1,2):
        prior=solve.read(OUT/"prior_snapshot/archive.json")
        rel=str(location(seed,"full").relative_to(old.OUT))
        assert solve.sha(location(seed,"full"))==prior["files"][rel]
    if arm=="full":
        return dict(ref,reason="reference",reference_f_A=ref["f_A"],reference_f_B=ref["f_B"],
                    reference_s=ref["total_s"],observed_s=ref["total_s"],used_s=ref["total_s"])
    path=location(seed,arm)
    r=solve.read(path)
    ep=path.parent/"endpoint"
    assert r["seed"]==seed and r["arm"]==arm and r["key"]["reference"]==solve.sha(location(seed,"full"))
    schedule=solve.read(ep/"schedule.json")
    assert solve.validate(schedule)["valid"] and solve.read(ep/"primary.json")["replay"]["valid"]
    for f in ("schedule","assignment"):
        assert r[f+"_sha256"]==solve.sha(ep/(f+(".json" if f=="schedule" else ".json.gz")))
    f=solve.product.product_metrics(schedule)
    assert abs(r["f_A"]-f["cmax"])<=TOL and abs(r["f_B"]-f["secondary"])<=TOL
    assert r["reference_f_A"]==ref["f_A"] and r["reference_f_B"]==ref["f_B"] and r["reference_s"]==ref["total_s"]
    hit=r["f_A"]<=ref["f_A"]+TOL and r["f_B"]<=ref["f_B"]+TOL
    assert hit==(r["reason"]=="target") and 0<=r["witness_s"]<=r["observed_s"]<=ref["total_s"]
    assert hit or r["observed_s"]==ref["total_s"]
    return r

def protocol():
    source=old.OUT/"protocol.json"
    frozen=solve.read(source)
    spec=dict(case=frozen["case"],seeds=frozen["seeds"],methods=frozen["methods"],inputs=frozen["inputs"],
              parent_sha256=solve.sha(source),checkpoints=frozen["checkpoints"],threads=1,max_concurrent=4,
              driver=solve.sha(HERE/"matched_ablation.py"),reference_driver=solve.sha(HERE/"matched_reference.py"),
              original_solver=solve.sha(Path(old.__file__)),tolerance_s=TOL,gap_A=.01,gap_B=.01,
              target="Per seed, one feasible schedule at least as good on BOTH physical objectives. Earliest observed accepted solver solution.",
              budget="Paired full-method total: measured preparation, A search wall time, post-handoff solve. Product wafers only for wait.",
              cutoff="At cap retain smallest physical f_A then smallest f_B among observed ties. Never admit a later solution.",
              continuation="If the native 1% B gap fires before both paired conditions, continue the same fixed-structure solve with the residual budget. If optimal first, release SCIP, preserve actual used_s, and publish the last solution when the budget really elapses.",
              resume="Restore elapsed within heartbeat resolution (3s), best feasible solution, A bound, handoff and counts; rebuild the SCIP tree.",
              calls="Actual calls to cut selection in stage A, across all selectors; includes SCIP default.",
              frozen_full={str(s):solve.sha(location(s,"full")) for s in (1,2)})
    dest=OUT/"protocol.json"
    if dest.exists():
        if solve.read(dest)!=spec:raise ValueError("Paired protocol changed on resume")
    else:solve.save(dest,spec)

def render(rows):
    csv_file(OUT/"paired_runs.csv",FIELDS,rows)
    lines=["# 表5　4片混合算例的消融与基准对照","",
           "| 方法 | 已验证种子 | 同时达标数 | $f_A$ | 切换时 $f_B$ | $f_B$ | 对照时刻（s） | 选割次数 |",
           "|---|---|---:|---:|---:|---:|---:|---:|"]
    for arm,title in NAMES.items():
        subset=[r for r in rows if r["arm"]==arm]
        if not subset:continue
        def avg(key):
            nums=[r[key] for r in subset if r.get(key) is not None]
            return f"{mean(nums):.2f}" if nums else "—"
        seeds="、".join(str(r["seed"]) for r in subset)
        hits="参照" if arm=="full" else str(sum(r["reason"]=="target" for r in subset))
        lines.append("| "+" | ".join([title,seeds,hits,*[avg(k) for k in ("f_A","f_B_handoff","f_B","observed_s","calls")]])+" |")
    lines+=["","对照时刻取首次同时达到参照目标的时刻，或该种子完整方法的用时。切换时的指标取已进入第二阶段的运行。","",
            "| 种子 | 方法 | 参照 $f_A$ / $f_B$ | 参照用时（s） | 实测 $f_A$ / $f_B$ | 对照时刻（s） | 实际用时（s） | 结果 |",
            "|---:|---|---:|---:|---:|---:|---:|---|"]
    for r in rows:
        why={"target":"同时达标","time_budget":"预算到时","reference":"完整方法参照"}[r["reason"]]
        if r.get("exhausted") and r["reason"]=="time_budget":why+="（求解提前结束）"
        lines.append(f"| {r['seed']} | {NAMES[r['arm']]} | {r['reference_f_A']:.2f} / {r['reference_f_B']:.2f} | {r['reference_s']:.2f} | {r['f_A']:.2f} / {r['f_B']:.2f} | {r['observed_s']:.2f} | {r['used_s']:.2f} | {why} |")
    target=OUT/"TABLE5_CN.md"
    tmp=target.with_suffix(".tmp")
    tmp.write_text("\n".join(lines)+"\n",encoding="utf-8")
    tmp.replace(target)

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    lock=(OUT/"controller.lock").open("a+b")
    lock.seek(0)
    msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
    protocol()
    logs=OUT/"logs"
    logs.mkdir(exist_ok=True)
    active={}
    failures={}
    for p in psutil.process_iter(["name","cmdline"]):
        args=p.info["cmdline"] or []
        if (p.info["name"] or "").lower()!="python.exe":continue
        for j in JOBS:
            tail=arguments(*j)
            if args[-len(tail):]==tail:active[j]=p
    while True:
        for j,p in list(active.items()):
            if not p.is_running():
                del active[j]
                if not location(*j).is_file():failures[j]="See latest worker log"
        for j in JOBS:
            s,arm=j
            if j in active or j in failures or location(*j).exists():continue
            if arm!="full" and not location(s,"full").exists():continue
            if len(active)>=4 or psutil.virtual_memory().available<3.8*1024**3:break
            with (logs/f"{s}_{arm}_{time.time_ns()}.log").open("w",encoding="utf8") as log:
                active[j]=psutil.Popen([A3C,"-B","-u","-X","utf8",*arguments(*j)],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
        rows=[verified(s,a) for s in (1,2,3) for a in NAMES if location(s,a).exists()]
        details={}
        for (s,a),p in active.items():
            info=dict(pid=p.pid)
            if a=="full":
                path=reference(s)/"resume.json"
                if path.exists():
                    r=solve.read(path)
                    info.update(stage="A" if not (path.parent/"handoff.json").exists() else "B",upper=r["ub"],lower=r["lb"],charged_s=r["seconds"])
            else:
                path=location(s,a).parent/"progress.json"
                if path.exists():
                    r=solve.read(path)
                    used=r["charged_s"]
                    pulse=path.parent/"clock.json"
                    if pulse.exists():
                        clock=solve.read(pulse)
                        if clock["attempt"]==r["attempt"]:used=max(used,clock["charged_s"])
                    ref=verified(s,"full")
                    info.update(stage=r["stage"],f_A=r["best"]["a"],f_B=r["best"]["b"],charged_s=used,
                                remaining_s=max(0.,ref["total_s"]-used))
            details[f"{s} {a}"]=info
        now=datetime.now().astimezone().isoformat(timespec="seconds")
        errors={" ".join(map(str,j)):msg for j,msg in failures.items()}
        state=dict(at=now,pid=os.getpid(),verified=len(rows),expected=15,active=details,failures=errors)
        solve.save(OUT/"progress.json",state)
        render(rows)
        eta=", ".join(f"{k} {v['remaining_s']/60:.1f} min" for k,v in details.items() if "remaining_s" in v)
        print(f"{now}  {len(rows)}/15 verified, {len(active)} active, {len(failures)} failed | remaining per active comparator: {eta}",flush=True)
        all_resolved=all(location(*j).exists() or j in failures for j in JOBS)
        if len(rows)==15 or (not active and (all_resolved or (3,"full") in failures)):break
        time.sleep(8)

if __name__=="__main__":main()

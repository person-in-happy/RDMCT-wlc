"""Read both live campaigns. Use --resume to adopt or restart their controllers."""
import argparse
import csv
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from functools import lru_cache
import heapq
import json
import msvcrt
import os
from pathlib import Path
from statistics import median
import subprocess
import time

import psutil

HERE = Path(__file__).resolve().parent
JMS = HERE.parents[1]
RESULTS = JMS/"results"
FOUR = RESULTS/"table4_one_percent_20261124"
FIVE = RESULTS/"table5_matched_target_20261124"
REPORT = RESULTS/"table4_table5_live_status"
CONTROLLERS = {
    "table4": ("G:/conda/python.exe", HERE.parent/"table4_one_percent_20261124/campaign.py", []),
    "table5": ("G:/conda/envs/a3cenv/python.exe", HERE/"matched_queue.py", ["run"])
}


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def alive(table, pid=None):
    _, script, args = CONTROLLERS[table]
    tail = [str(script), *args]
    for p in psutil.process_iter(["name","cmdline"]):
        if pid is not None and p.pid != pid:
            continue
        if (p.info["name"] or "").lower()=="python.exe" and (p.info["cmdline"] or [])[-len(tail):]==tail:
            return True
    return False


def resume():
    for key,root in (("table4",FOUR),("table5",FIVE)):
        state = read(root/"progress.json")
        if state["verified"]==state["expected"] or alive(key):
            continue
        exe,script,args = CONTROLLERS[key]
        subprocess.Popen([exe,"-B","-u","-X","utf8",str(script),*args],
                         cwd=JMS.parent,creationflags=subprocess.CREATE_NEW_CONSOLE)


def schedule(active, queued, slots):
    """Project the completion of the last chain, with active chains pinned in place."""
    if any(v is None for v in [*active,*queued]):
        return None
    lanes = list(active)+[0.] * max(0,slots-len(active))
    heapq.heapify(lanes)
    for duration in queued:
        heapq.heapreplace(lanes,lanes[0]+duration)
    return max(lanes, default=0.)


@lru_cache(maxsize=1)
def historical():
    samples = defaultdict(dict)
    old = RESULTS/"table4_three_arms_20261124/verified_runs.csv"
    with old.open(encoding="utf-8-sig",newline="") as f:
        for row in csv.DictReader(f):
            if row["arm"] in ("A","AB"):
                key=(int(row["n"]),int(row["H"]),int(row["seed"]))
                samples[key][row["arm"]]=read(JMS/row["source"])["record"]["seconds"]
    return samples


def sample_range(samples, spent):
    # A job still running after t belongs to the tail of the reference sample.
    tail=[v-spent for v in samples if v>spent or (v==0 and spent==0)]
    return (min(tail),median(tail),max(tail)) if tail else (None,None,None)


def four_eta(state):
    protocol=read(FOUR/"protocol.json")
    hist=historical()
    completed=defaultdict(dict)
    directory={}
    pending=[]
    for n,h in protocol["cases"]:
        for s in protocol["seeds"]:
            key=(n,h,s)
            work=FOUR/"runs"/f"D_n{n}_H{h}_mixed_dual__s{s}"
            directory[key]=work
            if not (work/"B/endpoint.json").exists():
                return None,None,None,"等待仅优化 f_B 的用时样本"
            af,ab=work/"A/endpoint.json", work/"AB/endpoint.json"
            if ab.exists():
                completed[key]={"A":read(af)["record"]["seconds"],
                                "AB":max(0.,ab.stat().st_mtime-af.stat().st_mtime)}
            else:
                pending.append(key)
    active, queued = [], []
    bases=set()
    for key in pending:
        n,h,s=key
        work=directory[key]
        info=state["active"].get(f"{n} {h} {s} A")
        post=(work/"A/endpoint.json").exists()
        refs=[v for k,v in completed.items() if k[:2]==key[:2]]
        if refs:
            bases.add("本批同算例1%实测")
        else:
            refs=[v for k,v in hist.items() if k[:2]==key[:2] and "AB" in v]
            bases.add("历史同算例10%实测，当前为1%，粗估")
        samples=[v["AB"] if post else sum(v.values()) for v in refs]
        spent=0.
        sf=work/"A/search.json"
        if not post and sf.exists():
            spent=read(sf)["seconds"]
        if info:
            if post:
                spent=max(0.,min(info["wall_s"],time.time()-(work/"A/endpoint.json").stat().st_mtime))
            else:
                if sf.exists():
                    # Keep time from previous attempts; cap downtime at this worker's age.
                    spent+=min(info["wall_s"],max(0.,time.time()-sf.stat().st_mtime))
                spent=max(spent,info["wall_s"])
        (active if info else queued).append(sample_range(samples,spent))
    estimates=[schedule([r[i] for r in active],[r[i] for r in queued],protocol["concurrency"]) for i in range(3)]
    if any(s is None for s in estimates):
        bases.add("持续时间超出可比样本或尚无样本，待新的同组终点")
    return *estimates,"；".join(sorted(bases))


def five_eta(state):
    config=read(FIVE/"protocol.json")
    active, queued=[],[]
    for seed in config["seeds"]:
        root=(RESULTS/"table5_one_percent_20261124" if seed in (1,2) else FIVE/"references")
        ref=root/f"runs/s{seed}_full/1pct/timing.json"
        if not ref.exists():
            return None,None,None,"等待完整方法建立该种子的计时预算"
        for arm in config["methods"]:
            if arm=="full" or (FIVE/f"runs/s{seed}_{arm}/result.json").exists():
                continue
            info=state["active"].get(f"{seed} {arm}")
            budget=read(ref)["total_s"]
            if info is not None:
                active.append(info.get("remaining_s",budget))
            else:
                saved=FIVE/f"runs/s{seed}_{arm}/progress.json"
                charged=read(saved)["charged_s"] if saved.exists() else 0.
                queued.append(max(0.,budget-charged))
    bound=schedule(active,queued,config["max_concurrent"])
    return None,bound,None,"各任务剩余计时预算按并发排程；提前达标可缩短，另计建模及核验"


def snapshot(key, root, estimate):
    state=read(root/"progress.json")
    now=datetime.now().astimezone()
    done=state["verified"]==state["expected"]
    running=not done and alive(key,state["pid"])
    mark=datetime.fromisoformat(state["at"])
    start=(root/"protocol.json").stat().st_mtime
    preparation=root/("inputs" if key=="table4" else "references")
    if preparation.exists():
        start=min(start,preparation.stat().st_ctime)
    for log in (root/"logs").glob("*.log"):
        stamp=log.stem.replace("-","_").split("_")[-1]
        if stamp.isdigit() and len(stamp)==19:
            start=min(start,int(stamp)/1e9)
    elapsed=max(0.,(now if running else mark).timestamp()-start)
    if done:lo,eta,hi,basis=0.,0.,0.,"已完成"
    elif running:lo,eta,hi,basis=estimate(state)
    else:lo,eta,hi,basis=None,None,None,"队列已离线，恢复后重估"
    phases=Counter()
    if running:
        for job, info in state["active"].items():
            if key=="table4":
                n,h,seed,phase=job.split()
                primary=root/f"runs/D_n{n}_H{h}_mixed_dual__s{seed}/A/endpoint.json"
                if phase=="A" and primary.exists():
                    phase="AB"
            else:
                phase=info.get("stage") or "准备"
            phases[phase]+=1
    return dict(status="complete" if done else "running" if running else "offline",
                verified=state["verified"],expected=state["expected"],failures=len(state["failures"]),
                active=state["active"],phases=phases,source_updated_at=state["at"],elapsed_wall_s=round(elapsed),
                remaining_s=eta,reference_range_s=[lo,hi] if lo is not None else None,
                estimated_total_wall_s=elapsed+eta if eta is not None else None,
                estimated_finish=(now+timedelta(seconds=eta)).isoformat(timespec="minutes") if running and eta is not None else None,
                basis=basis)


def minutes(s):
    return f"{s/60:.0f} min" if s is not None else "待重估"


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--resume",action="store_true")
    ap.add_argument("--watch",action="store_true")
    args=ap.parse_args()
    if args.resume:resume()
    watch=args.watch or args.resume
    REPORT.mkdir(parents=True,exist_ok=True)
    if watch:
        lock=(REPORT/"monitor.lock").open("a+b")
        lock.seek(0)
        try:msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
        except OSError:
            print("实时进度窗口已在运行。")
            return
    while True:
        now=datetime.now().astimezone().isoformat(timespec="seconds")
        try:
            status={"at":now,"table4":snapshot("table4",FOUR,four_eta),"table5":snapshot("table5",FIVE,five_eta)}
        except (FileNotFoundError,PermissionError,json.JSONDecodeError) as exc:
            if not watch:
                raise
            print(f"暂时无法读取进度，10 秒后重试。{exc}",flush=True)
            time.sleep(10)
            continue
        for name in ("table4","table5"):
            s=status[name]
            interval=s["reference_range_s"]
            limits=f"，参考范围 {minutes(interval[0])} – {minutes(interval[1])}" if interval and s["status"]=="running" else ""
            phases="、".join(f"{stage}×{count}" for stage,count in s["phases"].items())
            print(f"{now} {name} {s['verified']}/{s['expected']}，失败 {s['failures']}，活动 {len(s['active'])}，"
                  f"{'阶段 '+phases+'，' if phases else ''}"
                  f"已用 {minutes(s['elapsed_wall_s'])}，预计剩余 {minutes(s['remaining_s'])}{limits}，"
                  f"预计总耗时 {minutes(s['estimated_total_wall_s'])}。{s['basis']}",flush=True)
        tmp=REPORT/f"progress.{os.getpid()}.tmp"
        tmp.write_text(json.dumps(status,ensure_ascii=False,indent=2),encoding="utf-8")
        tmp.replace(REPORT/"progress.json")
        if not watch or all(status[k]["status"]=="complete" for k in ("table4","table5")):return
        time.sleep(10)


if __name__=="__main__":
    main()

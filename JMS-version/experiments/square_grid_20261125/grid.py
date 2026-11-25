"""Verify and resume the three stopping levels on each archived first-stage handoff."""
import csv
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
import json
import msvcrt
import os
from pathlib import Path
import subprocess
import sys
import time

HERE=Path(__file__).resolve().parent
JMS=HERE.parents[1]
R=JMS/"results"
OUT=R/HERE.name
MOD=HERE.parent/"square_residence_20261125"
sys.path.insert(0,str(MOD))
from score import metrics,OBJECTIVE

def read(p):return json.loads(Path(p).read_bytes())
def digest(p):return sha256(Path(p).read_bytes()).hexdigest()
def atom(p,d):
    tmp=p.with_suffix(f".{os.getpid()}.tmp")
    tmp.write_text(json.dumps(d,ensure_ascii=False,indent=2),encoding="utf8")
    tmp.replace(p)
def rows(p):
    with p.open(encoding="utf-8-sig",newline="") as f:return list(csv.DictReader(f))
def rel(p):return Path(p).relative_to(JMS).as_posix()
def csv_write(p,items):
    tmp=p.with_suffix(".tmp")
    with tmp.open("w",encoding="utf-8-sig",newline="") as f:
        w=csv.DictWriter(f,fieldnames=items[0]);w.writeheader();w.writerows(items)
    tmp.replace(p)


def settings(old,seed,tau,budget):
    source=read(old/"result.json")
    par=source["parents"][0]
    a=Path(par["schedule"])
    v=Path(par["assignment"])
    assert a.is_file() and v.is_file() and digest(a)==par["schedule_sha256"] and digest(v)==par["assignment_sha256"]
    assert source["replay"]["valid"] and source["original_rows"]==source["replayed_rows"]>0
    assert all(digest(old/k)==h for k,h in source["files"].items())
    return dict(A=rel(a),values=rel(v),A_sha256=digest(a),assignment_sha256=digest(v),
                seed=seed,tau=tau,budget=budget,backend=source["backend"],n=len([j for j in read(a)["jobs"] if j["product"]]),
                objective=OBJECTIVE)


def jobs():
    hub=R/"huber_residence_20261125"
    work={};grid=[];struct=[]
    def add(folder,seed,tau,budget):
        conf=settings(folder,seed,tau,budget)
        key=sha256(json.dumps({k:v for k,v in conf.items() if k not in ("A","values")},sort_keys=True).encode()).hexdigest()[:18]
        trial=work.setdefault(key,dict(config=conf,previous=[]))
        if rel(folder) not in trial["previous"]:trial["previous"].append(rel(folder))
        return key
    for row in rows(R/"table3_grid16_20261125/threshold_cells.csv"):
        tau=dict(zip(("10pct","1pct","0p01pct"),(.10,.01,.0001)))[row["gB"]]
        key=add((JMS/row["schedule_path"]).parent,1,tau,None)
        grid.append((row,key))
    for row in rows(hub/"supplement/structure_cells.csv"):
        key=add(hub/"supplement"/row["source"],int(row["seed"]),0.,30)
        struct.append((row,key))
    return work,grid,struct


def verify(folder,trial):
    finish=folder/"square.json"
    if not finish.exists():return False
    r=read(finish)
    assert r["config"]==trial["config"] and r["solver"]==digest(MOD/"solver.py") and r["score"]==digest(MOD/"score.py")
    assert digest(JMS/r["schedule"])==r["schedule_sha256"] and digest(JMS/r["proof"])==r["certificate_sha256"]
    return True


def process(key,trial):
    folder=OUT/"cells"/key;folder.mkdir(parents=True,exist_ok=True)
    c=trial["config"]
    if verify(folder,trial):return
    a=JMS/c["A"];v=JMS/c["values"]
    meta=dict(config=c,solver=digest(MOD/"solver.py"),score=digest(MOD/"score.py"))
    got=None
    for source in trial["previous"]:
        f=JMS/source
        old=read(f/"result.json");sc=metrics(read(f/"schedule.json"))
        assert old["record"]["lower"]<=sc["secondary"]+2e-5
        lb=min(old["record"]["lower"],sc["secondary"])
        gap=max(0.,(sc["secondary"]-lb)/max(abs(lb),1e-10))
        if gap<=c["tau"]+1.e-8:
            got=(f,sc,lb,gap,old["replayed_rows"],"Huber lower bound; original schedule meets quadratic-objective gap")
            break
    if got is None:
        dest=folder/"native";dest.mkdir(exist_ok=True)
        if (dest/"result.json").exists() and read(dest/"result.json")["record"]["status"]=="memlimit":
            dest=folder/"native_11500mb";dest.mkdir(exist_ok=True)
        if not (dest/"result.json").exists():
            cmd=[sys.executable,"-B","-u","-X","utf8",str(HERE/"memory_retry.py" if dest.name=="native_11500mb" else MOD/"solver.py"),"--mode","fixed",
                 "--source",str(a.parent),"--schedule",a.name,"--assignment",str(v),
                 "--output",str(dest),"--seed",str(c["seed"]),"--backend",c["backend"],"--gap",str(c["tau"])]
            if c["budget"]:cmd+=["--seconds",str(c["budget"])]
            with (folder/"solver.log").open("a",encoding="utf8") as log:
                subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT,check=True)
        new=read(dest/"result.json")
        assert new["replay"]["valid"] and new["original_rows"]==new["replayed_rows"]>0
        assert new["parents"][0]["schedule_sha256"]==c["A_sha256"] and new["parents"][0]["assignment_sha256"]==c["assignment_sha256"]
        assert all(digest(dest/k)==h for k,h in new["files"].items())
        assert new["eligible"] or (c["budget"] and new["record"]["status"]=="timelimit")
        got=(dest,metrics(read(dest/"schedule.json")),new["record"]["lower"],new["record"]["gap"],
             new["replayed_rows"],"native quadratic solve")
    dest,sc,lb,gap,nrows,method=got
    assert abs(sc["cmax"]-metrics(read(a))["cmax"])<2e-4
    p=dest/"schedule.json";cert=dest/"result.json"
    atom(folder/"square.json",dict(**meta,metrics=sc,B_lower=lb,B_gap=gap,method=method,original_rows=nrows,
         schedule=rel(p),schedule_sha256=digest(p),proof=rel(cert),certificate_sha256=digest(cert)))
    assert verify(folder,trial)


def publish(grid,struct):
    output=[]
    for row,key in grid:
        f=OUT/"cells"/key/"square.json"
        if not f.exists():continue
        z=read(f);m=z["metrics"]
        output.append(dict(case=row["case"],gA=row["gA"],gB=row["gB"],seed=1,
          f_A=m["cmax"],f_B=m["secondary"],mean=m["mean_residence"],spread=m["residence_range"],
          clean_deficit=m["clean_deficit"],square=m["square_penalty"],A_lower=row["A_lower"],A_upper=row["A_upper"],
          A_gap=row["A_gap"],B_lower=z["B_lower"],B_upper=m["secondary"],B_gap=z["B_gap"],
          primary_schedule_sha256=z["config"]["A_sha256"],schedule_path=z["schedule"],schedule_sha256=z["schedule_sha256"],
          method=z["method"],cell=rel(f)))
    if output:csv_write(OUT/"threshold_cells.csv",output)
    out2=[]
    for row,key in struct:
        f=OUT/"cells"/key/"square.json"
        if not f.exists():continue
        z=read(f);m=z["metrics"];initial=metrics(read(JMS/z["config"]["A"]))
        out2.append(dict(name=row["name"],seed=row["seed"],f_A=m["cmax"],f_B=m["secondary"],initial_f_B=initial["secondary"],
            mean=m["mean_residence"],spread=m["residence_range"],square=m["square_penalty"],B_lower=z["B_lower"],B_gap=z["B_gap"],
            cell=rel(f),schedule=z["schedule"],schedule_sha256=z["schedule_sha256"]))
    if out2:csv_write(OUT/"structure_cells.csv",out2)
    return len(output),len(out2)


def run(workers,stop_after,mem_retry=False):
    OUT.mkdir(parents=True,exist_ok=True)
    with (OUT/("mem_retry.lock" if mem_retry else "campaign.lock")).open("a+b") as lock:
        try:msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
        except OSError:
            print("Active controller already owns this experiment.");return
        work,grid,struct=jobs();(OUT/"cells").mkdir(exist_ok=True)
        pending=[k for k,t in work.items() if not verify(OUT/"cells"/k,t)]
        if mem_retry:
            pending=[k for k in pending if (p:=OUT/"cells"/k/"native/result.json").exists()
                     and read(p)["record"]["status"]=="memlimit"]
        # Prepare small, fast runs before the 16-wafer native formulations.
        pending.sort(key=lambda k:work[k]["config"]["n"])
        if stop_after:pending=pending[:stop_after]
        measured={};failed={};begin=time.monotonic()
        with ThreadPoolExecutor(max_workers=workers) as pool:
            active={}
            while True:
                for f,(k,s) in list(active.items()):
                    if not f.done():continue
                    err=f.exception()
                    if err:failed[k]=str(err)
                    else:measured.setdefault(work[k]["config"]["n"],[]).append(time.monotonic()-s)
                    del active[f]
                while len(active)<workers and pending:
                    k=pending.pop(0);active[pool.submit(process,k,work[k])]=(k,time.monotonic())
                if mem_retry:
                    count=sum((OUT/"cells"/k/"square.json").exists() for _,k in grid)
                    h6=sum((OUT/"cells"/k/"square.json").exists() for _,k in struct)
                else:count,h6=publish(grid,struct)
                history={2:1,4:3,8:7,16:24}
                def estimate(k):
                    n=work[k]["config"]["n"]
                    obs=measured.get(n,[])
                    return max(1,sum(obs)/len(obs)) if len(obs)>=2 else history[n]
                rem=(sum(estimate(k) for k in pending)+sum(max(1,estimate(k)-(time.monotonic()-s)) for k,s in active.values()))/workers
                seconds=time.monotonic()-begin
                atom(OUT/("memory_progress.json" if mem_retry else "progress.json"),dict(complete_grid=count,complete_structure=h6,expected_grid=108,expected_structure=9,
                     active=[k for k,s in active.values()],failed=failed,elapsed_s=seconds,seconds_remaining=rem,
                     estimated_total_s=seconds+rem,concurrency=workers,seconds_by_finished_case_size=measured,
                     basis="observed cell wall times by size; before two observations use archived full-model timings"))
                print(f"Table 3 {count}/108; structures {h6}/9; failures {len(failed)}; elapsed {seconds:.0f}s, "
                      f"total ~{seconds+rem:.0f}s, remaining ~{rem:.0f}s",flush=True)
                if not active:break
                time.sleep(2)
        if failed:raise RuntimeError(failed)


if __name__=="__main__":
    import argparse
    ap=argparse.ArgumentParser();ap.add_argument("--workers",type=int,default=3);ap.add_argument("--stop-after",type=int)
    ap.add_argument("--mem-retry",action="store_true")
    args=ap.parse_args();run(args.workers,args.stop_after,args.mem_retry)

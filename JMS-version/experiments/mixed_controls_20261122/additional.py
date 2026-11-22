"""Matched uninitialized policies and a 16-wafer mixed uninterrupted-chain control."""
from dataclasses import replace
from pathlib import Path
import sys
import time

import psutil
from scale import Config,LARGE,OUT,SCIP,ROOT,HERE,cell,execute,first,product,product_solve,read,save,sha,sparse_witness,store_primary,validate

RAW=OUT/"raw_policies"
PITCH=OUT/"mixed_rhythm"

def raw(seed,method,folder):
    src=LARGE/f"s{seed}"/"raw"
    stage=folder/"A"
    r=first(src,stage,16,seed,method,"scip",270)
    e=product_solve(folder/"B",stage/"schedule.json",stage/"assignment.json.gz","D",16,seed,"fixed",30)
    original=read(ROOT/read(LARGE/f"s{seed}/source.json")["archive"])["constructive"]["config"]
    schedule=read(folder/"B/runs/endpoint/schedule.json");schedule["config"]=original
    valid=validate(schedule)
    assert valid["valid"]
    save(folder/"result.json",dict(seed=seed,arm="plain_"+method,initial=sha(src/"assignment.json.gz"),
         start=sha(src/"assignment.json.gz"),stages=[(r,270)],secondary=e["record"],metrics=e["measured"],
         physical_replay=valid,eligible=e["eligible"] and r["seconds"]<=271 and r["status"] not in ("memlimit","unknown","userinterrupt")))

def pitch(seed,folder):
    base=HERE.parent/"pareto_rl_dmct_20261119/runs/formal02/cells"/f"main_H16_rl_domain_s{seed}/attempt_01"
    for source in sorted(base.glob("point_*.json.gz")):
        data=read(source)
        if not validate(data)["valid"] or not product.product_metrics(data)["rhythm_centers"]:continue
        cfg=replace(Config(**data["config"]),max_pairs=1+max(p["id"] for p in data["pairs"]),
                    max_cycles=1+max(c["index"] for c in data["cycles"]))
        vals=sparse_witness(cfg,data)
        checked=cell.lift(cfg,vals,None,rebuild=True)
        if checked:break
    else:raise ValueError("No physically and natively checked active chain")
    src=folder/"input"
    store_primary(src,checked,dict(archive=str(source.relative_to(ROOT)),sha256=sha(source)))
    rows={}
    for weight in (0,5,25,100):
        target=folder/f"w{weight}";product.OUT=target
        s,v=src/"schedule.json",src/"assignment.json.gz"
        task=dict(case="H16",seed=seed,kind="fixed",seconds=60,gap=None,rho=None,weight=weight,
                  schedule=s.relative_to(ROOT).as_posix(),assignment=v.relative_to(ROOT).as_posix(),
                  schedule_sha256=sha(s),assignment_sha256=sha(v),parent_eligible=True,backend="D",n=16)
        save(target/"protocol.json",dict(jobs={"endpoint":task}))
        product.worker("endpoint")
        e=read(target/"runs/endpoint/result.json")
        rows[str(weight)]=dict(metrics=e["measured"],record=e["record"],eligible=e["eligible"])
    save(folder/"result.json",dict(seed=seed,case="H16",source=str(source.relative_to(ROOT)),
         first_eligible_by_filename=True,assignment_sha256=sha(v),weights=rows))

if __name__=="__main__":
    mode=sys.argv[1]
    if mode in ("raw-cell","pitch-cell"):
        while psutil.virtual_memory().available<9*1024**3:time.sleep(4)
        if mode=="raw-cell":raw(int(sys.argv[2]),sys.argv[3],Path(sys.argv[4]))
        else:pitch(int(sys.argv[2]),Path(sys.argv[3]))
    elif mode=="raw":
        jobs=[]
        for seed in (1,2,3):
            for method in ("default","hem_spbs","feature_only","no_rerank","greedy"):
                path=str(RAW/f"s{seed}__{method}")
                jobs.append((SCIP,__file__,["raw-cell",str(seed),method,path],path))
        sys.exit(execute(jobs,2,RAW))
    elif mode=="pitch":
        jobs=[]
        for seed in (1,2,3):
            path=str(PITCH/f"s{seed}")
            jobs.append((SCIP,__file__,["pitch-cell",str(seed),path],path))
        sys.exit(execute(jobs,1,PITCH))

"""Global relaxation using ordered upper-lock arrivals, chamber batches and two return slots."""
import json
import os
import time
from hashlib import sha256
from pathlib import Path

HERE = Path(__file__).resolve().parent
JMS = HERE.parents[1]
OUT = JMS / "results/table3_grid16_20261125"
SOURCE = JMS / "results/table3_pure8_20261125/4x1/prepared/schedule.json"


def evaluate(n_full, n_double, cfg):
    n = n_full+n_double
    assert cfg["chambers"] == [2,3]
    keys = ("atr_handling","handling","atr_travel","vtr_travel","pump","vent",
            "upper_reset","lower_reset","alignment","full_time","mix_time","rotation")
    assert tuple(cfg[k] for k in keys) == (4,1,3,2,30,25,30,25,20,180,90,2)
    # Ordered earliest chamber load END (all products require the one aligner and two upper slots).
    ready = []
    for k in range(1,n+1):
        t = 48+28*k
        ready.append(max(t,ready[-2]+65) if k>2 else t)
    # At or after the ith earliest release, each pair of additional products needs a lower-slot reuse.
    def return_bound(times):
        return max(t+55*((n-1-i)//2) for i,t in enumerate(sorted(times)))
    best = 10**9
    best_path = None
    visited = 0
    def visit(f,d,chambers,clock,tails,path):
        nonlocal visited,best,best_path
        visited+=1
        if not f+d:
            bound = return_bound(tails)
            if bound < best:
                best,best_path=bound,path
            return
        # Every remaining wafer must enter a production batch at or after clock.
        # Assign the shorter time-to-release to all remaining wafers for this pruning bound.
        used=n-f-d
        relaxed=tails+[max(clock,ready[k])+220 for k in range(used,n)]
        if return_bound(relaxed)>=best:
            return
        for recipe,left,capacity,tail in (("4x1",f,4,220),("2x2",d,2,226)):
            for count in range(min(left,capacity),0,-1):
                for c,(last_mode,last_start) in enumerate(chambers):
                    if c and chambers[0]==chambers[1]:
                        continue
                    separation=0
                    if last_mode=="4x1":
                        separation=188
                    elif last_mode=="2x2":
                        separation=94 if recipe=="2x2" else 192
                    start=max(clock, ready[used+count-1], last_start+separation)
                    if start+tail >= best:
                        continue
                    updated=chambers.copy()
                    updated[c]=(recipe,start)
                    visit(f-count if recipe=="4x1" else f, d-count if recipe=="2x2" else d,
                          updated,start,tails+[start+tail]*count,path+[(recipe,c,count,start)])
    visit(n_full,n_double,[(None,0),(None,0)],0,[],[])
    return dict(lower=best, visited_nodes=visited, minimizing_relaxed_batches=best_path, ready=ready)


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    cfg=json.loads(SOURCE.read_bytes())["config"]
    sig=dict(code=sha256(Path(__file__).read_bytes()).hexdigest(), physical_parameters=sha256(SOURCE.read_bytes()).hexdigest())
    start=time.monotonic()
    for i,(name,nf,nd) in enumerate((("pure_4x1",16,0),("pure_2x2",0,16),("mixed",8,8))):
        target=OUT/f"batch_bound_{name}.json"
        if target.exists() and json.loads(target.read_bytes())["signature"]==sig:
            continue
        print(f"Computing {name}. Completed {i}/3. Elapsed {time.monotonic()-start:.1f}s. Initial estimate under one minute per case (bounded enumeration).",flush=True)
        data=evaluate(nf,nd,cfg)
        tmp=target.with_suffix(".tmp")
        tmp.write_text(json.dumps(dict(signature=sig,elapsed_s=time.monotonic()-start,**data),indent=2),encoding="utf8")
        os.replace(tmp,target)
        print(f"{name}: lower {data['lower']} s, {data['visited_nodes']} nodes. Completed {i+1}/3.",flush=True)
    print("Completed 3/3. Remaining 0 s.",flush=True)


if __name__=="__main__":
    main()

"""Constrain pair-release orders in two balanced chamber allocations to search the middle time window."""
import time
from pathlib import Path
import bridge
from support import OUT,write,read,digest


def pin_route(model,variables,pattern,cap,store):
    baseline(model,variables,pattern,cap,store)
    pos={1:0,2:0}
    for i,(_,kind) in enumerate(pattern):
        model.add(variables[f"port_{i}"]==pos[kind]//2)
        pos[kind]+=1
    # Keep the order between consecutive indicated load-port wafer pairs, allowing
    # the two recipes to interleave freely at the aligner and load locks.
    for k in (1,2):
        ids=[i for i,(_,mode) in enumerate(pattern) if mode==k]
        for j,i in enumerate(ids):
            if j:
                model.add(variables[f"al_{i}"]>=variables[f"al_{ids[j-1]}"]+28)
                if j%2==0:
                    model.add(variables[f"up_{i}"]>=variables[f"up_{ids[j-1]}"]+4)
    for i in range(1,len(pattern)):
        if pattern[i]==pattern[i-1]:
            model.add(variables[f"al_{i}"]==variables[f"al_{i-1}"]+28)


baseline=bridge.rank.rank_propagation
if __name__=="__main__":
    bridge.rank.rank_propagation=pin_route
    jobs=[("balanced_guided",922,8),("mirrored_guided",942,6),("balanced_guided",974,2),("dual_first_guided",1020,1)]
    for n in ("balanced","mirrored","dual_first"):bridge.TEMPLATES[n+"_guided"]=bridge.TEMPLATES[n]
    dest=OUT/"guided_identity.json";sig={n:digest(Path(__file__).with_name(n)) for n in ("guided.py","bridge.py","search.py","support.py")}
    if dest.exists():assert read(dest)==sig
    else:write(dest,sig)
    start=time.monotonic()
    for i,task in enumerate(jobs):
        elapsed=time.monotonic()-start;eta=(len(jobs)-i)*(elapsed/i if i else 19)
        q=dict(completed=i,total=len(jobs),failed=0,elapsed=elapsed,eta_remaining=eta,eta_total=elapsed+eta,
               case=task,basis="one CPU worker, 19 s per cell initially, then measured throughput")
        write(OUT/"guided_progress.json",q);print(q,flush=True);bridge.work(task,19)
    q.update(completed=len(jobs),elapsed=time.monotonic()-start,eta_remaining=0);q["eta_total"]=q["elapsed"]
    write(OUT/"guided_progress.json",q)

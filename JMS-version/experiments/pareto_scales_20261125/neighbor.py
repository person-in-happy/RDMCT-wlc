"""Apply the same linear lower support to all remaining batches at the next integer cap."""
import argparse
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
import time
from cap810 import HERE,OUT,R,atomic,read,sha,rank,cp_model


def enumerate_cap(cap):
    base=R/"table3_grid16_20261125"
    excluded={}
    for folder in (base/"partitions/mixed_810",base/"tool_capacity/mixed_812"):
        bound_cap=int(folder.name.split("_")[1])
        if bound_cap<cap:continue
        for f in folder.glob("p*/result.json"):
            rec=read(f)
            if rec["status"]=="INFEASIBLE" or rec["lower"]>cap:
                excluded[tuple(tuple(item) for item in rec["batch_pattern"])]=(str(f.relative_to(R.parent)),sha(f))
    table=rank.tool.prepare("mixed",cap)
    ids=[i for i,(pat,_) in enumerate(table) if pat not in excluded]
    return table,ids,{i:excluded[pat] for i,(pat,_) in enumerate(table) if i not in ids}


def solve(job):
    cap,i,budget,(pattern,cycles)=job
    root=OUT/f"cap{cap}";pt=f"p{i:04}";result=root/f"{pt}.json"
    sig=sha(Path(__file__))
    if result.exists():
        old=read(result);assert old["implementation"]==sig
        if old["status"] in ("OPTIMAL","INFEASIBLE") or old["used"]>=budget-.1:return i,old["status"]
    else:old={"used":0}
    rank.tool.order.patterns=lambda n,d,lim,ready:{pattern:cycles}
    m,c=rank.tool.add_ports("mixed",cap)
    v={s.name:m.get_int_var_from_proto_index(j) for j,s in enumerate(m.proto.variables) if s.name}
    rank.rank_propagation(m,v,pattern,cap,True)
    v={s.name:m.get_int_var_from_proto_index(j) for j,s in enumerate(m.proto.variables) if s.name}
    candidates=sorted(((-count,g) for (g,k),count in Counter(pattern).items() if k==1 and count>=3))
    g=candidates[0][1] if candidates else None
    d=(v[f"bu_{g}"]-v[f"bl_{g}"]-v[f"fu_{g}"]+v[f"fl_{g}"]) if g is not None else 0
    support=sum(v[f"ul_{j}"]-v[f"ld_{j}"]-181 for j in range(16))+16*d-8
    if "lower16" in old:m.add(support>=round(old["lower16"]))
    m.minimize(support)
    hint=root/f"{pt}_hint.json"
    prior=R/f"table3_grid16_20261125/tool_capacity/mixed_812/{pt}/projection.json"
    h=read(hint) if hint.exists() else read(prior) if prior.exists() else {}
    for k,val in h.items():
        if k in v:m.add_hint(v[k],val)
    solver=cp_model.CpSolver();solver.parameters.num_workers=2;solver.parameters.random_seed=1
    solver.parameters.max_time_in_seconds=budget-old["used"]
    solver.parameters.log_search_progress=True;solver.parameters.log_to_stdout=False
    class Recorder(cp_model.CpSolverSolutionCallback):
        def on_solution_callback(self):atomic(hint,{k:self.value(z) for k,z in v.items()})
    with (root/f"{pt}.log").open("a",encoding="utf8") as f:
        solver.log_callback=lambda ln:f.write(ln.rstrip()+"\n")
        stat=solver.solve(m,Recorder())
    record=dict(status=solver.status_name(stat),lower16=solver.best_objective_bound,used=old["used"]+solver.wall_time,
                cap=cap,full_group=g,pattern=pattern,implementation=sig,support_parent=sha(HERE/"cap810.py"))
    if stat in (cp_model.OPTIMAL,cp_model.FEASIBLE):record["primal16"]=solver.objective_value
    atomic(result,record)
    return i,record["status"]


def run(cap,budget):
    table,ids,excluded=enumerate_cap(cap)
    root=OUT/f"cap{cap}";root.mkdir(exist_ok=True,parents=True)
    atomic(root/"catalogue.json",dict(total=len(table),remaining=ids,excluded=excluded))
    count=len(ids);start=time.monotonic();workers=3
    def progress(done):
        used=time.monotonic()-start
        eta=(count-done)*(budget+3)/workers if not done else (count-done)*used/done
        state=dict(completed=done,total=count,failed=0,elapsed=used,eta_remaining=eta,eta_total=eta+used,
                   basis="three concurrent patterns, then mean completed throughput; two CP workers per pattern")
        atomic(root/"progress.json",state);print(cap,state,flush=True)
    progress(0)
    with ProcessPoolExecutor(max_workers=workers) as ex:
        handles=[ex.submit(solve,(cap,i,budget,table[i])) for i in ids]
        for done,f in enumerate(as_completed(handles),1):
            print(f.result(),flush=True);progress(done)


if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("cap",type=int);p.add_argument("--budget",type=int,default=30)
    args=p.parse_args();run(args.cap,args.budget)

"""Search new resource orders at make-before-release and low-spread tradeoffs with a single CP worker."""
import argparse
from collections import Counter
import msvcrt
import os
import sys
from pathlib import Path
import time
from support import HERE,JMS,OUT,OLD,read,write,digest,rank,cp_model

TEMPLATES={
    "two_each": [(0,1,2),(10,2,2),(11,2,2),(1,1,2),(12,2,2),(13,2,2),(2,1,2),(3,1,2)],
    "dual_first": [(0,2,2),(10,1,2),(1,2,2),(2,2,2),(11,1,2),(3,2,2),(12,1,2),(13,1,2)],
    "single_terminal": [(0,1,2),(10,2,2),(11,2,2),(1,1,2),(12,2,2),(13,2,1),(2,1,2),(14,2,1),(3,1,2)],
}

JOBS=[("p26",814),("p26",822),("p26",842),("two_each",960),("dual_first",992),
      ("single_terminal",1050),("two_each",1015),("p26",876)]


def get_pattern(tag):
    if tag=="p26":return rank.tool.prepare("mixed",812)[26]
    layout=TEMPLATES[tag]
    pattern=tuple((g,k) for g,k,n in layout for _ in range(n))
    cycles=tuple(tuple(k for g,k,n in layout if g//10==ch) for ch in (0,1))
    return pattern,cycles


def run(tag,cap,budget):
    dest=OUT/"search"/f"{tag}_{cap}";dest.mkdir(exist_ok=True,parents=True)
    result=dest/"result.json"
    signature={str(p.relative_to(JMS)):digest(p) for p in (Path(__file__),HERE/"support.py",*(HERE.parent/"table3_grid16_20261125"/n for n in
               ("rank_partition.py","tool_partition.py","partition.py","port_projection.py","ordered_projection.py","batch_lower.py")))}
    prev=read(result) if result.exists() else {}
    if prev:
        assert prev["signature"]==signature
        if prev["status"] in ("OPTIMAL","INFEASIBLE") or prev["used"]>=budget-.1:return
    pattern,cyc=get_pattern(tag)
    original=rank.tool.order.patterns
    try:
        rank.tool.order.patterns=lambda nf,nd,limit,ready:{pattern:cyc}
        m,c=rank.tool.add_ports("mixed",cap)
    finally:rank.tool.order.patterns=original
    v={z.name:m.get_int_var_from_proto_index(j) for j,z in enumerate(m.proto.variables) if z.name}
    rank.rank_propagation(m,v,pattern,cap,True)
    v={z.name:m.get_int_var_from_proto_index(j) for j,z in enumerate(m.proto.variables) if z.name}
    if tag!="p26":
        # Candidate routing: single-exposure products use the front pair together.
        for i,(g,k) in enumerate(pattern):
            if k==1:m.add(v[f"front_{i}"]==1)
        dg=[g for g,k,n in TEMPLATES[tag] if k==2]
        for g in dg[:-1]:m.add(v[f"next_chain_{g}"]==1)
    r=[]
    for j in range(16):
        val=m.new_int_var(0,100,f"res_{j}")
        m.add(val==v[f"ul_{j}"]-v[f"ld_{j}"]-181);r.append(val)
    D=m.new_int_var(0,100,"range")
    for k in (1,2):
        sub=[r[j] for j,(_,kind) in enumerate(pattern) if kind==k]
        lo=m.new_int_var(0,100,"");hi=m.new_int_var(0,100,"")
        m.add_min_equality(lo,sub);m.add_max_equality(hi,sub);m.add(D>=hi-lo)
    q=m.new_int_var(0,10000,"square");m.add_multiplication_equality(q,D,D)
    m.minimize((sum(r)+8*q)*(cap+1)+c)
    nearby=[p for p in (OUT/"search").glob(tag+"_*/best.json") if p.parent!=dest]
    if tag=="p26":nearby.append(OLD/"cap812/p0026_hint.json")
    checkpoint=dest/"best.json"
    source=checkpoint if checkpoint.exists() else min(nearby,key=lambda p:abs((read(p).get("true_C",cap))-cap)) if nearby else None
    if source:
        for k,val in read(source).items():
            if k in v:m.add_hint(v[k],val)
    solver=cp_model.CpSolver();solver.parameters.num_workers=1;solver.parameters.max_time_in_seconds=max(.1,budget-prev.get("used",0))
    solver.parameters.random_seed=1;solver.parameters.log_search_progress=True;solver.parameters.log_to_stdout=False
    start=time.monotonic();old=prev.get("used",0)
    record=dict(signature=signature,used=old,status="RUNNING",pattern=pattern,cap=cap,source_hint=str(source),solutions=prev.get("solutions",[]))
    def store():
        record["used"]=old+time.monotonic()-start;write(result,record)
    class Capture(cp_model.CpSolverSolutionCallback):
        def on_solution_callback(self):
            point=[self.value(c),self.value(sum(r)),self.value(D)]
            f=dest/("p_"+"_".join(map(str,point))+".json")
            data={k:self.value(z) for k,z in v.items()}
            write(f,data);write(checkpoint,data)
            if point not in record["solutions"]:record["solutions"].append(point)
            store()
    if prev.get("solutions"):
        m.add((sum(r)+8*q)*(cap+1)+c<=min((s+8*d*d)*(cap+1)+a for a,s,d in prev["solutions"]))
    with (dest/"solver.log").open("a",encoding="utf8") as f:
        solver.log_callback=lambda ln:f.write(ln.rstrip()+"\n")
        state=solver.solve(m,Capture())
    record.update(status=solver.status_name(state),lower=solver.best_objective_bound)
    store()


def main(budget):
    OUT.mkdir(exist_ok=True,parents=True)
    with (OUT/"search.lock").open("a+b") as lock:
        try:msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
        except OSError:print("Existing search already running.",flush=True);return
        start=time.monotonic()
        for i,(tag,cap) in enumerate(JOBS):
            elapsed=time.monotonic()-start
            eta=(len(JOBS)-i)*(elapsed/i if i else budget)
            state=dict(completed=i,total=len(JOBS),failed=0,elapsed=elapsed,eta_remaining=eta,eta_total=elapsed+eta,
                       case=[tag,cap],workers=1,basis="serial budget, updated with completed elapsed per cell")
            write(OUT/"search_progress.json",state);print(state,flush=True);run(tag,cap,budget)
        state.update(completed=len(JOBS),eta_remaining=0,elapsed=time.monotonic()-start);state["eta_total"]=state["elapsed"]
        write(OUT/"search_progress.json",state);print(state,flush=True)


if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--budget",type=int,default=36);args=p.parse_args();main(args.budget)

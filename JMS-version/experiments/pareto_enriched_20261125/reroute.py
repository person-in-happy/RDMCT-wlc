"""Move late single-exposure batches to a second eligible chamber and reroute the two robots."""
import msvcrt
import sys
import time
from pathlib import Path
from native_caps import HERE,JMS,OUT,SQ
from support import cp_model,rank,read,write,digest

SRC=SQ/"search/bridge_dual_first_992_3/p_981_88_0.json"
GROUPS=[(0,2),(10,1),(1,2),(2,2),(11,1),(3,2),(12,1),(13,1)]
JOBS=[("last",970,12),("last",930,12),("last",895,12),("split",945,10),
      ("last",860,8),("early",915,6),("split",890,6),("last",875,6),("early",955,8)]


def run(tag,cap,prefix,budget):
    dest=OUT/"search"/f"{tag}_{cap}_{prefix}";dest.mkdir(parents=True,exist_ok=True)
    target=dest/"result.json"
    sig={str(p.relative_to(JMS)):digest(p) for p in (Path(__file__),SRC,*[HERE.parent/"table3_grid16_20261125"/f for f in
         ("batch_lower.py","ordered_projection.py","port_projection.py","partition.py","tool_partition.py","rank_partition.py")])}
    prev=read(target) if target.exists() else {"used":0,"solutions":[]}
    if "signature" in prev:
        assert prev["signature"]==sig
        if prev["status"] in ("OPTIMAL","INFEASIBLE") or prev["used"]>=budget-.05:return
    gr=GROUPS.copy()
    if tag=="last":gr[7]=(4,1)
    elif tag=="split":gr[6:]=[(4,1),(12,1)]
    elif tag=="early":gr[4:]=[(3,1),(11,2),(12,1),(4,1)]
    pat=tuple(g for g in gr for _ in range(2))
    cyc=tuple(tuple(k for g,k in gr if g//10==ch) for ch in (0,1))
    orig=rank.tool.order.patterns
    try:
        rank.tool.order.patterns=lambda *a:{pat:cyc}
        model,unused=rank.tool.add_ports("mixed",cap)
    finally:rank.tool.order.patterns=orig
    v={a.name:model.get_int_var_from_proto_index(i) for i,a in enumerate(model.proto.variables) if a.name}
    rank.tool.exact_sides(model,v,pat,cap,True)
    v={a.name:model.get_int_var_from_proto_index(i) for i,a in enumerate(model.proto.variables) if a.name}
    original=read(SRC);hint=read(dest/"best.json") if (dest/"best.json").exists() else original
    for k,z in v.items():
        if k in hint and not k.startswith(("batch_","pair_","kind_")):model.add_hint(z,hint[k])
        if k.startswith("next_chain_"):model.add(z==1)
    phases=("origin_pick","al","ap","up","sp","ld","ul","dp","lp","origin_put")
    for i in range(16):
        model.add(v[f"front_{i}"]==1);model.add(v[f"port_{i}"]==original[f"port_{i}"])
        for j,stage in enumerate(phases):
            key=f"{stage}_{i}"
            if i<prefix and (j<5 or i<prefix-2):
                model.add(v[key]==original[key])
    rs=[v[f"ul_{i}"]-v[f"ld_{i}"]-181 for i in range(16)]
    D=model.new_int_var(0,18,"D")
    for recipe in (1,2):
        group=[rs[i] for i,(_,k) in enumerate(pat) if k==recipe]
        for a in group:
            for b in group:model.add(a-b<=D)
    sq=model.new_int_var(0,324,"sq");model.add_multiplication_equality(sq,D,D)
    c=v["true_C"];model.minimize((sum(rs)+8*sq)*(cap+1)+c)
    solver=cp_model.CpSolver();solver.parameters.num_workers=1;solver.parameters.random_seed=3
    solver.parameters.max_time_in_seconds=max(.1,budget-prev["used"]);solver.parameters.log_search_progress=True
    solver.parameters.log_to_stdout=False
    started=time.monotonic();old=prev["used"]
    rec=dict(signature=sig,pattern=pat,cap=cap,prefix=prefix,used=old,status="RUNNING",solutions=prev["solutions"])
    def checkpoint():
        rec["used"]=old+time.monotonic()-started;write(target,rec)
    class Capture(cp_model.CpSolverSolutionCallback):
        def on_solution_callback(self):
            spreads=[max(self.value(rs[i]) for i,(_,k) in enumerate(pat) if k==s)
                     -min(self.value(rs[i]) for i,(_,k) in enumerate(pat) if k==s) for s in (1,2)]
            p=[self.value(c),self.value(sum(rs)),max(spreads)]
            d={k:self.value(z) for k,z in v.items()}
            write(dest/("p_"+"_".join(map(str,p))+".json"),d);write(dest/"best.json",d)
            if p not in rec["solutions"]:rec["solutions"].append(p)
            checkpoint()
    if rec["solutions"]:model.add((sum(rs)+8*sq)*(cap+1)+c<=min((s+8*d*d)*(cap+1)+a for a,s,d in rec["solutions"]))
    checkpoint()
    with (dest/"solver.log").open("a",encoding="utf8") as log:
        solver.log_callback=lambda l:log.write(l.rstrip()+"\n")
        state=solver.solve(model,Capture())
    rec["status"]=solver.status_name(state);rec["lower"]=solver.best_objective_bound;checkpoint()


if __name__=="__main__":
    OUT.mkdir(exist_ok=True,parents=True)
    lock=(OUT/"reroute.lock").open("a+b")
    try:msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
    except OSError:sys.exit("Existing worker is active")
    start=time.monotonic();budget=12
    for i,job in enumerate(JOBS):
        elapsed=time.monotonic()-start;eta=(len(JOBS)-i)*(elapsed/i if i else budget+1)
        p=dict(current=job,completed=i,total=len(JOBS),failed=0,elapsed=elapsed,eta_remaining=eta,eta_total=elapsed+eta,
               estimate="one CP worker, then measured throughput")
        print(p,flush=True);write(OUT/"reroute_progress.json",p);run(*job,budget)
    p.update(completed=len(JOBS),elapsed=time.monotonic()-start,eta_remaining=0);p["eta_total"]=p["elapsed"]
    write(OUT/"reroute_progress.json",p)

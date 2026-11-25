"""Explore unequal product counts per full cycle and alternative mixed exposure chains near 830 s."""
import msvcrt
import time
from pathlib import Path
from native_caps import HERE,OUT,SQ
from support import cp_model,rank,read,write,digest

P=SQ/"search/p26_842/p_823_86_12.json"
LAYOUTS={
 "late3":[(0,2,2),(10,1,2),(1,2,2),(11,1,3),(2,2,2),(3,2,2),(12,1,3)],
 "early3":[(0,2,2),(10,1,3),(1,2,2),(2,2,2),(11,1,2),(3,2,2),(12,1,3)],
 "fourlast":[(0,2,2),(10,1,2),(1,2,2),(2,2,2),(11,1,2),(3,2,2),(12,1,4)],
 "mid4":[(0,2,1),(10,1,2),(1,2,2),(2,2,1),(11,1,4),(3,2,2),(4,2,2),(12,1,2)],
 "splitfront":[(0,2,1),(10,1,2),(1,2,2),(2,2,1),(11,1,2),(3,2,2),(4,2,2),(12,1,2),(5,1,2)],
}
BASE=read(SQ/"search/p26_842/result.json")["pattern"]


def run(tag,cap):
    dest=OUT/"search"/f"pack_{tag}_{cap}";dest.mkdir(exist_ok=True,parents=True)
    path=dest/"result.json";budget=8
    signature={p.name:digest(p) for p in (Path(__file__),P,Path(rank.tool.__file__),Path(rank.tool.order.__file__))}
    prior=read(path) if path.exists() else {"used":0,"solutions":[]}
    if path.exists():
        assert signature==prior["signature"]
        if prior["status"] in ("OPTIMAL","INFEASIBLE") or prior["used"]>=budget-.05:return
    data=LAYOUTS[tag];pat=tuple((g,k) for g,k,n in data for _ in range(n))
    modes=tuple(tuple(k for g,k,n in data if g//10==ch) for ch in (0,1))
    old=rank.tool.order.patterns
    try:
        rank.tool.order.patterns=lambda *a:{pat:modes};m,c=rank.tool.add_ports("mixed",cap)
    finally:rank.tool.order.patterns=old
    v={x.name:m.get_int_var_from_proto_index(i) for i,x in enumerate(m.proto.variables) if x.name}
    rank.tool.exact_sides(m,v,pat,cap,True)
    v={x.name:m.get_int_var_from_proto_index(i) for i,x in enumerate(m.proto.variables) if x.name}
    hint=read(P);newhint=read(dest/"best.json") if (dest/"best.json").exists() else {}
    order={k:iter(i for i,(_,typ) in enumerate(BASE) if typ==k) for k in (1,2)}
    for i,(g,k) in enumerate(pat):
        src=next(order[k])
        for stage in ("origin_pick","al","ap","up","sp","ld","ul","dp","lp","origin_put"):
            name=f"{stage}_{i}"
            m.add_hint(v[name],newhint.get(name,hint[f"{stage}_{src}"]))
        m.add(v[f"port_{i}"]==hint[f"port_{src}"])
        members=[j for j,z in enumerate(pat) if z[0]==g]
        if k==1 and len(members)<=2:m.add(v[f"front_{i}"]==1)
        if k==1 and len(members)>2:
            m.add(v[f"front_{i}"]==int(i>=members[-2]))
    for k,z in v.items():
        if k.startswith("next_chain_"):m.add(z==1)
    res=[v[f"ul_{i}"]-v[f"ld_{i}"]-181 for i in range(16)]
    spread=m.new_int_var(0,14,"range")
    for k in (1,2):
        rr=[res[i] for i,(_,typ) in enumerate(pat) if typ==k]
        for r in rr:
            for s in rr:m.add(r-s<=spread)
    sq=m.new_int_var(0,196,"sq");m.add_multiplication_equality(sq,spread,spread)
    criterion=(sum(res)+8*sq)*(cap+1)+v["true_C"]
    m.minimize(criterion)
    if prior["solutions"]:m.add(criterion<=min((n+8*d*d)*(cap+1)+a for a,n,d in prior["solutions"]))
    solver=cp_model.CpSolver();solver.parameters.num_workers=1;solver.parameters.random_seed=3
    solver.parameters.max_time_in_seconds=max(.05,budget-prior["used"])
    tic=time.monotonic();record=dict(signature=signature,used=prior["used"],solutions=prior["solutions"],status="RUNNING",pattern=pat,cap=cap)
    def checkpoint():record["used"]=prior["used"]+time.monotonic()-tic;write(path,record)
    class Capture(cp_model.CpSolverSolutionCallback):
        def on_solution_callback(self):
            d=max(max(self.value(res[i]) for i,(_,a) in enumerate(pat) if a==typ)-
                  min(self.value(res[i]) for i,(_,a) in enumerate(pat) if a==typ) for typ in (1,2))
            point=[self.value(v["true_C"]),self.value(sum(res)),d];state={s:self.value(z) for s,z in v.items()}
            write(dest/("p_"+"_".join(map(str,point))+".json"),state);write(dest/"best.json",state)
            if point not in record["solutions"]:record["solutions"].append(point)
            checkpoint()
    checkpoint();st=solver.solve(m,Capture());record["status"]=solver.status_name(st)
    record["lower"]=solver.best_objective_bound;checkpoint()


if __name__=="__main__":
    lock=(OUT/"mixpacking.lock").open("a+b")
    try:msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
    except OSError:raise SystemExit("Matching worker active")
    jobs=[(tag,c) for c in (838,850,865) for tag in LAYOUTS]
    start=time.monotonic()
    for i,job in enumerate(jobs):
        e=time.monotonic()-start;eta=(len(jobs)-i)*(e/i if i else 8.5)
        p=dict(current=job,completed=i,total=len(jobs),failed=0,elapsed=e,eta_remaining=eta,eta_total=e+eta,basis="one CP worker, then measured throughput")
        print(p,flush=True);write(OUT/"packing_progress.json",p);run(*job)
    p.update(completed=len(jobs),elapsed=time.monotonic()-start,eta_remaining=0);p["eta_total"]=p["elapsed"]
    write(OUT/"packing_progress.json",p)

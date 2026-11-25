"""Target unfilled production-versus-stability gaps by bounding spread and minimizing return time."""
import msvcrt
import time
from pathlib import Path
from support import HERE,OUT,read,write,digest,rank,cp_model
from search import TEMPLATES
BALANCED=[
    (0,1,2),(10,2,2),(11,2,2),(1,1,2),(12,1,2),(2,2,2),(3,2,2),(13,1,2),
]
MIXED=[
    (0,2,2),(10,1,2),(1,2,2),(11,1,2),(2,1,2),(12,2,2),(13,2,2),(3,1,2),
]
TEMPLATES=dict(TEMPLATES,balanced=BALANCED,mirrored=MIXED)
JOBS=[("dual_first",992,3),("dual_first",1015,1),("balanced",932,5),("mirrored",936,4),
      ("dual_first",1030,0),("single_terminal",1080,1),("balanced",1000,1)]


def work(task,allowance):
    tag,cap,maxd=task;dest=OUT/"search"/f"bridge_{tag}_{cap}_{maxd}";dest.mkdir(exist_ok=True,parents=True)
    result=dest/"result.json";sig=digest(Path(__file__))
    previous=read(result) if result.exists() else {}
    if previous:
        assert previous["code"]==sig
        if previous["status"] in ("OPTIMAL","INFEASIBLE") or previous["used"]>=allowance-.1:return
    layout=TEMPLATES[tag]
    pat=tuple((g,k) for g,k,n in layout for _ in range(n))
    modes=tuple(tuple(k for g,k,n in layout if g//10==ch) for ch in (0,1))
    orig=rank.tool.order.patterns
    try:
        rank.tool.order.patterns=lambda *args:{pat:modes};m,c=rank.tool.add_ports("mixed",cap)
    finally:rank.tool.order.patterns=orig
    v={z.name:m.get_int_var_from_proto_index(i) for i,z in enumerate(m.proto.variables) if z.name}
    rank.rank_propagation(m,v,pat,cap,True)
    v={z.name:m.get_int_var_from_proto_index(i) for i,z in enumerate(m.proto.variables) if z.name}
    for i,(g,k) in enumerate(pat):
        if k==1:m.add(v[f"front_{i}"]==1)
    for key,var in v.items():
        if key.startswith("next_chain_"):m.add(var==1)
    resid=[v[f"ul_{i}"]-v[f"ld_{i}"]-181 for i in range(16)]
    D=m.new_int_var(0,maxd,"spread")
    for k in (1,2):
        idx=[i for i,(_,mode) in enumerate(pat) if mode==k]
        for i in idx:
            for j in idx:
                if i!=j:m.add(resid[i]-resid[j]<=D)
    # A different primary scalarization from the cap sweep: C is minimized at the specified D;
    # score breaks C ties. This avoids a late schedule whenever earlier equal-quality retimings exist.
    q=m.new_int_var(0,maxd*maxd,"square");m.add_multiplication_equality(q,D,D)
    med=sum(resid)+8*q
    scale=1601+8*maxd*maxd
    m.minimize(scale*c+med)
    src=dest/"best.json"
    if not src.exists():
        files=[]
        for folder in sorted((OUT/"search").iterdir()):
            if folder==dest or tag not in folder.name:continue
            files.extend(folder.glob("p_*.json"))
        if files:
            def rank_hint(f):
                a,s,d=(int(i) for i in f.stem.split("_")[1:])
                return int(a>cap or d>maxd),max(d-maxd,0),a,s
            src=min(files,key=rank_hint)
    if src.exists():
        for k,num in read(src).items():
            if k in v:m.add_hint(v[k],num)
    solver=cp_model.CpSolver();solver.parameters.num_workers=1;solver.parameters.random_seed=2
    solver.parameters.max_time_in_seconds=allowance-previous.get("used",0)
    solver.parameters.log_search_progress=True;solver.parameters.log_to_stdout=False
    rec=dict(code=sig,status="RUNNING",cap=cap,spread_limit=maxd,provenance="C-minimization under spread limit",used=previous.get("used",0),
             solutions=previous.get("solutions",[]),pattern=pat,source=str(src))
    old=rec["used"];tic=time.monotonic()
    def save():rec["used"]=old+time.monotonic()-tic;write(result,rec)
    class Capture(cp_model.CpSolverSolutionCallback):
        def on_solution_callback(self):
            fA=self.value(c);mean=self.value(sum(resid));spread=max(max(self.value(resid[i]) for i,x in enumerate(pat) if x[1]==k)
                -min(self.value(resid[i]) for i,x in enumerate(pat) if x[1]==k) for k in (1,2))
            point=[fA,mean,spread];values={k:self.value(z) for k,z in v.items()}
            write(dest/("p_"+"_".join(map(str,point))+".json"),values);write(dest/"best.json",values)
            if point not in rec["solutions"]:rec["solutions"].append(point)
            save()
    if rec["solutions"]:m.add(scale*c+med<=min(scale*a+y+8*d*d for a,y,d in rec["solutions"]))
    with (dest/"solver.log").open("a",encoding="utf8") as log:
        solver.log_callback=lambda ln:log.write(ln.rstrip()+"\n")
        status=solver.solve(m,Capture())
    rec["status"]=solver.status_name(status);rec["lower"]=solver.best_objective_bound;save()


def main(budget=27):
    with (OUT/"bridge.lock").open("a+b") as lock:
        try:msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
        except OSError:return
        start=time.monotonic()
        for i,task in enumerate(JOBS):
            elapsed=time.monotonic()-start;eta=(len(JOBS)-i)*(elapsed/i if i else budget)
            q=dict(completed=i,total=len(JOBS),failed=0,elapsed=elapsed,eta_remaining=eta,eta_total=elapsed+eta,
                   workers=1,case=task,basis="one serial worker, measured throughput after first cell")
            write(OUT/"bridge_progress.json",q);print(q,flush=True);work(task,budget)
        q.update(completed=len(JOBS),eta_remaining=0,elapsed=time.monotonic()-start);q["eta_total"]=q["elapsed"]
        write(OUT/"bridge_progress.json",q);print(q,flush=True)


if __name__=="__main__":main()

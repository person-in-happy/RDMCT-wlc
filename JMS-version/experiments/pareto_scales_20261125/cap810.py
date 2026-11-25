"""Bound continuous Huber scores at the global 16-wafer makespan by integer linear support."""
import argparse
import time
import sys
from collections import Counter
from pathlib import Path
from sweep import HERE,OUT,R,atomic,read,sha
sys.path.insert(0,str(HERE.parent/"table3_grid16_20261125"))
import rank_partition as rank
from ortools.sat.python import cp_model


def catalogue():
    base=R/"table3_grid16_20261125"
    tables=[]
    for source in ("partitions/mixed_810","tool_capacity/mixed_812"):
        d={}
        for f in (base/source).glob("p*/result.json"):
            r=read(f);ptn=tuple(tuple(x) for x in r["batch_pattern"])
            if r["status"]=="INFEASIBLE" or r["lower"]>810:
                d[ptn]=str(f.relative_to(R.parent)),sha(f)
        tables.append(d)
    pts=rank.tool.prepare("mixed",810)
    remaining={};excluded={}
    for i,(ptn,modes) in enumerate(pts):
        proof=next((d[ptn] for d in tables if ptn in d),None)
        if proof:excluded[i]=proof
        else:remaining[i]=(ptn,modes)
    return remaining,excluded


def run(i,budget):
    directory=OUT/"cap810";directory.mkdir(exist_ok=True,parents=True)
    rem,excluded=catalogue()
    atomic(directory/"catalogue.json",dict(total=len(rem)+len(excluded),remaining=list(rem),excluded=excluded))
    pattern,cycles=rem[i]
    tag=f"p{i:04}";path=directory/f"{tag}.json"
    signature={s.name:sha(s) for s in (Path(__file__),*(HERE.parent/"table3_grid16_20261125"/p for p in
        ("rank_partition.py","tool_partition.py","partition.py","port_projection.py","ordered_projection.py","batch_lower.py")))}
    historic=read(path) if path.exists() else {}
    if historic:
        assert historic["code"]==signature
        if historic["status"] in ("OPTIMAL","INFEASIBLE") or historic["used"]>=budget:return
    rank.tool.order.patterns=lambda nf,nd,cap,ready:{pattern:cycles}
    m,c=rank.tool.add_ports("mixed",810)
    v={s.name:m.get_int_var_from_proto_index(j) for j,s in enumerate(m.proto.variables) if s.name}
    rank.rank_propagation(m,v,pattern,810,True)
    v={s.name:m.get_int_var_from_proto_index(j) for j,s in enumerate(m.proto.variables) if s.name}
    full=[g for (g,k),count in Counter(pattern).items() if k==1 and count==4]
    assert len(full)==1
    g=full[0]
    back_minus_front=v[f"bu_{g}"]-v[f"bl_{g}"]-v[f"fu_{g}"]+v[f"fl_{g}"]
    total=sum(v[f"ul_{j}"]-v[f"ld_{j}"]-181 for j in range(16))
    support=total+16*back_minus_front-8
    # A common uniform floor phase preserves any fixed resource order, all integer differences,
    # capacities and the integer makespan cap. Its expected value preserves this linear support.
    if historic:m.add(support>=int(round(historic["lower16"])))
    m.minimize(support)
    hint=directory/f"{tag}_hint.json"
    if not hint.exists():
        p=R/f"table3_grid16_20261125/tool_capacity/mixed_812/{tag}/projection.json"
        hint0=read(p) if p.exists() else {}
    else:hint0=read(hint)
    for k,val in hint0.items():
        if k in v:m.add_hint(v[k],val)
    solver=cp_model.CpSolver();solver.parameters.num_workers=2;solver.parameters.random_seed=1
    old=float(historic.get("used",0));solver.parameters.max_time_in_seconds=budget-old
    solver.parameters.log_search_progress=True;solver.parameters.log_to_stdout=False
    t=time.monotonic()
    rec=dict(code=signature,pattern=pattern,full_group=g,used=old,status="RUNNING",lower16=historic.get("lower16",-10**6))
    def progress():
        rec["used"]=old+time.monotonic()-t
        rec["eta_remaining"]=max(0,budget-rec["used"]);rec["eta_total"]=budget
        atomic(path,rec)
    def lower(b):
        rec["lower16"]=b;progress()
    class Recorder(cp_model.CpSolverSolutionCallback):
        def on_solution_callback(self):
            vals={k:self.value(z) for k,z in v.items()};atomic(hint,vals)
            rec["primal16"]=self.objective_value;progress()
    solver.best_bound_callback=lower
    progress();print(tag,"cap 810; budget",budget,"s",flush=True)
    with (directory/f"{tag}.log").open("a",encoding="utf8") as f:
        solver.log_callback=lambda ln:f.write(ln.rstrip()+"\n")
        stat=solver.solve(m,Recorder())
    rec.update(status=solver.status_name(stat),lower16=solver.best_objective_bound,wall_s=solver.wall_time)
    progress();print(tag,rec["status"],"continuous B lower",rec["lower16"]/16,flush=True)


if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("index",type=int);p.add_argument("--budget",type=int,default=75)
    a=p.parse_args();run(a.index,a.budget)

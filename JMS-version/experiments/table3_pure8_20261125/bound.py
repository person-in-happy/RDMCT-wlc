"""Independent pure eight-wafer relaxed bound and export of promising physical skeletons."""
import sys
import time
from itertools import product
from projection import tightened,cp_model
from run import OUT,atomic,load,sha
from pathlib import Path

mode=sys.argv[1]
cap=int(sys.argv[2])
source=OUT/mode/"raw/schedule.json"
dest=OUT/"projection"/mode/str(cap)
dest.mkdir(parents=True,exist_ok=True)
doc=load(source)
fp=dict(assignment=sha(source),base=sha(Path(__file__).with_name("projection.py")),spec=sha(Path(__file__)),mode=mode,cap=cap)
if (dest/"proof.json").is_file() and load(dest/"proof.json")["fp"]==fp:sys.exit(0)
m=tightened(doc,cap)
v={z.name:m.get_int_var_from_proto_index(i) for i,z in enumerate(m.proto.variables)}
m.add(v["ch0"]==0)
for c,q in product(range(2),range(4)):
    used=v[f"use{c,q}"];full=v[f"full{c,q}"]
    m.add(full == (used if mode=="4x1" else 0))
    products=[]
    for i in range(8):
        for side in range(2):
            var=v.get(f"w{i}_{c}_{q}_{side}")
            if var is not None:products.append(var)
        if mode=="2x2" and q>0:products.append(v[f"w{i}_{c}_{q-1}_1"])
    m.add(used<=sum(products))

engine=cp_model.CpSolver()
engine.parameters.num_workers=1
engine.parameters.random_seed=1
engine.parameters.log_search_progress=True
engine.parameters.log_to_stdout=False
engine.parameters.max_time_in_seconds=120
state={"lower":0}
if (dest/"progress.json").exists():
    old=load(dest/"progress.json")
    assert old["fp"]==fp
    state["lower"]=old["lower"]
    m.add(v["makespan"]>=int(old["lower"]))
def event(lb):
    if lb<state["lower"]:return
    state["lower"]=lb
    atomic(dest/"progress.json", dict(fp=fp,lower=lb,elapsed_s=time.monotonic()-begin,
        remaining_s=max(0,120-(time.monotonic()-begin)),phase="running"))
    print(f"8 {mode} at C<={cap}: LB {lb} UB {state.get('upper')}; elapsed {time.monotonic()-begin:.1f}s",flush=True)
class Incumbents(cp_model.CpSolverSolutionCallback):
    def on_solution_callback(self):
        state["upper"]=self.objective_value
        coords={k:self.value(x) for k,x in v.items() if self.value(x)!=0}
        atomic(dest/f"projected_{int(self.objective_value)}.json",coords)
        event(self.best_objective_bound)
begin=time.monotonic()
with (dest/"solver.log").open("w",encoding="utf8",buffering=1) as f:
    engine.log_callback=lambda line:f.write(line.rstrip()+"\n")
    engine.best_bound_callback=event
    status=engine.solve(m,Incumbents())
info=dict(fp=fp,status=engine.status_name(status),lower=cap+1 if status==cp_model.INFEASIBLE else engine.best_objective_bound,
          objective=engine.objective_value if status in (cp_model.FEASIBLE,cp_model.OPTIMAL) else None,
          seconds=engine.wall_time,rows=len(m.proto.constraints),branches=engine.num_branches)
atomic(dest/"proof.json" if status in (cp_model.OPTIMAL,cp_model.INFEASIBLE) else dest/"attempt.json",info)
print(info,flush=True)

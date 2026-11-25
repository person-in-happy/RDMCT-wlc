"""Earliest possible upper-lock loading of a subset, under a shared two-hand ATR and one aligner."""
from itertools import combinations
from pathlib import Path
import sys,time
from ortools.sat.python import cp_model
from common16 import OUT,save,sha

def main(count,cap):
    d=OUT/"4x1/inlet"/f"n{count}_t{cap}";d.mkdir(parents=True,exist_ok=True)
    m=cp_model.CpModel();t=lambda n:m.new_int_var(0,cap,n)
    rows=[];hands=[];locks=[];events=[]
    for i in range(count):
        op,al,ap,up=(t(f"{k}_{i}") for k in ["op","al","ap","up"])
        if i:m.add(al>=rows[-1][2]+4)
        m.add(al>=op+7);m.add(ap>=al+24);m.add(up>=ap+7)
        for start,end in ((op,al+4),(ap,up+4)):
            length=m.new_int_var(0,cap,"")
            hands.append(m.new_interval_var(start,length,end,""))
        locks.append(m.new_fixed_size_interval_var(up,65,""))
        rows.append((op,al,ap,up))
        events.extend([(op,"op",i),(al,"al",i),(ap,"ap",i),(up,"up",i)])
    m.add_cumulative(hands,[1]*len(hands),2);m.add_cumulative(locks,[1]*len(locks),2)
    for (a,k,i),(b,j,h) in combinations(events,2):
        if i==h:continue
        if k==j and k in ("up","op"):
            permitted=m.new_bool_var("")
            m.add(a==b).only_enforce_if(permitted)
            flags=[~permitted]
        else:flags=[]
        z=m.new_bool_var("")
        loc=lambda name:"AL" if name in ("al","ap") else name
        fwd=4 if loc(k)==loc(j) else 10 if k=="up" and j=="op" else 7
        rev=4 if loc(k)==loc(j) else 10 if j=="up" and k=="op" else 7
        m.add(b>=a+fwd).only_enforce_if([*flags,z]);m.add(a>=b+rev).only_enforce_if([*flags,~z])
    c=t("C");m.add_max_equality(c,[r[-1] for r in rows]);m.minimize(c)
    solver=cp_model.CpSolver();solver.parameters.num_workers=1;solver.parameters.random_seed=1;solver.parameters.max_time_in_seconds=100
    solver.parameters.log_search_progress=True;solver.parameters.log_to_stdout=False
    start=time.monotonic()
    with (d/"solver.log").open("w",encoding="utf8",buffering=1) as s:
        solver.log_callback=lambda line:s.write(line.rstrip()+"\n")
        res=solver.solve(m)
    rec=dict(status=solver.status_name(res),lower=cap+1 if res==cp_model.INFEASIBLE else solver.best_objective_bound,elapsed=solver.wall_time,code=sha(Path(__file__)))
    if res in (cp_model.OPTIMAL,cp_model.FEASIBLE):rec.update(upper=solver.objective_value,moves=[[solver.value(x) for x in r] for r in rows])
    save(d/"result.json",rec);print(rec,flush=True)

if __name__=="__main__":main(int(sys.argv[1]),int(sys.argv[2]))

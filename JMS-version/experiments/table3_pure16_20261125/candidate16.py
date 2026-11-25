"""Find physically executable integer-time witnesses for the supplied pair and chamber plan."""
import sys
import time
from collections import defaultdict
from dataclasses import replace
from pathlib import Path
from threading import Event,Thread
from common16 import HERE,OUT,JMS,save,sha,load,setup,config
cell=setup()
from seed import normalize_schedule
from model import Integrated
from validate import validate
recipe=sys.argv[1]
projected=Path(sys.argv[2])
cap=int(sys.argv[3])
budget=int(sys.argv[4])
stem=sys.argv[5]
out=OUT/recipe/"search"/stem
out.mkdir(parents=True,exist_ok=True)
if (out/"result.json").exists():sys.exit(0)
cfg=config(recipe)
values=load(projected)
qmax=max(q for c in range(2) for q in range(16) if values.get(f"use{c,q}"))+1
labels=sorted([w for w in load(OUT/recipe/"raw/schedule.json")["jobs"] if w["product"]],key=lambda w:w["pjob_index"])
members=defaultdict(list)
for i,w in enumerate(labels):
    pos=[(c,q,s) for c in range(2) for q in range(qmax) for s in range(2) if values.get(f"w{i}_{c}_{q}_{s}",0)]
    assert len(pos)==1
    members[pos[0]].append(w["identity"])
template={};chamber_for={};cycles={2:[],3:[]};pair_id={}
dummy_cursor=0
for i,key in enumerate(sorted(members,key=lambda key:min(w["pjob_index"] for w in labels if w["identity"] in members[key]))):
    group=members[key][:]
    if len(group)==1:
        dummy_cursor+=1; group +=[f"D{dummy_cursor}"]
    template[i]=group
    pair_id[key]=i
    chamber_for[i]=2+key[0]
used_dummy=dummy_cursor
support_id=16
for c in range(2):
    for q in range(qmax):
        if not values.get(f"use{c,q}"):continue
        pair=[]
        for side in (0,1):
            k=(c,q,side) if recipe=="4x1" or side else (c,q-1,1)
            if k in pair_id:p_id=pair_id[k]
            else:
                p_id=support_id;support_id+=1
                if used_dummy+2>cfg.dummy_count:used_dummy=dummy_cursor
                assert used_dummy+2<=cfg.dummy_count
                template[p_id]=[f"D{used_dummy+1}",f"D{used_dummy+2}"];used_dummy+=2
                chamber_for[p_id]=c+2
            pair.append(p_id)
        cycles[c+2].append((*pair,values[f"start{c,q}"]))
small=replace(cfg,max_pairs=support_id,max_cycles=max(map(len,cycles.values())),horizon=1400)
x=Integrated(small);m=x.model
cell.scip_settings(m,dict(n=x.N,seed=1,seconds=50,gap=0),out)
m.setRealParam("numerics/feastol",1e-8)
def pin(z,val):
    if isinstance(z,(float,int)):assert z==val
    elif hasattr(z,"getLbOriginal"):
        m.chgVarLb(z,val);m.chgVarUb(z,val)
    else:m.addCons(z==val)

for p in range(x.P):
    members=template.get(p,[])
    pin(x.pair.active[p],int(bool(members)))
    for r in range(2):
        label=members[r] if members else ""
        if p<x.N:
            for g in x.groups:pin(x.pair.member[g.identifier,p,r],int(label in g.labels))
        for i in range(1,cfg.dummy_count+1):pin(x.pair.dummy_identity[f"D{i}",p,r],int(label==f"D{i}"))
    chamber=chamber_for.get(p,2)
    mode=recipe
    for c in cfg.chambers:pin(x.pair.chamber[p,c],int(bool(members) and chamber==c))
    for k in ("4x1","2x2","clean"):pin(x.pair.mode[p,k],int(bool(members) and mode==k))
for c in cfg.chambers:
    for q in range(x.Q):
        step=cycles[c][q] if q<len(cycles[c]) else None
        mode=recipe
        pin(x.cy.used[c,q],int(bool(step)))
        # All operating times and VTR hand identities remain free.
        for p in range(x.P):
            pin(x.cy.occupancy[p,c,q],int(bool(step) and p in step[:2]))
            pin(x.front[p,c,q],int(bool(step) and p==step[1]))
        for k in ("4x1","2x2","clean"):pin(x.cy.kind[c,q,k],int(bool(step) and k==mode))


m.addCons(x.cmax<=cap)
from ortools.sat.python import cp_model
from math import ceil,floor
cp=cp_model.CpModel()
allvars={};fixed_values={};scales={}
for v in m.getVars(transformed=False):
    scale=1
    lo=max(-10000000,ceil(scale*v.getLbGlobal()-1e-8));hi=min(10000000,floor(scale*v.getUbGlobal()+1e-8))
    if lo==hi:fixed_values[v.name]=lo
    else:allvars[v.name]=cp.new_int_var(lo,hi,v.name)
    scales[v.name]=scale
for row in m.getConss():
    assert row.isLinear()
    terms=[];constant=0
    for name,a in m.getValsLinear(row).items():
        w=round(a);assert abs(w-a)<1.e-8
        if name in fixed_values:constant+=w*fixed_values[name]
        else:terms.append(w*allvars[name])
    lo,hi=m.getLhs(row),m.getRhs(row)
    if lo>-1.e15:cp.add(sum(terms)>=ceil(lo-constant-1e-7))
    if hi<1.e15:cp.add(sum(terms)<=floor(hi-constant+1e-7))
cp.minimize(allvars[x.cmax.name])
engine=cp_model.CpSolver()
engine.parameters.num_workers=1
engine.parameters.random_seed=1
engine.parameters.max_time_in_seconds=90
engine.parameters.log_search_progress=True
engine.parameters.log_to_stdout=False

cp.clear_hints()
statefile=out/"progress.json"
ident=dict(case=recipe,seed=1,cap=cap,seconds=budget,input_sha256=sha(projected),worker_sha256=sha(Path(__file__)))
state=load(statefile) if statefile.exists() else dict(identity=ident,used=0,upper=None)
assert state["identity"]==ident
if state["upper"] is not None:
    prior_hint=load(out/'hint.json')
    for k,v in allvars.items():cp.add_hint(v,prior_hint.get(k,0))
    cp.add(allvars[x.cmax.name]<=int(state["upper"]))
used=state["used"]
engine.parameters.max_time_in_seconds=max(0,budget-used)
engine.parameters.random_seed=1
engine.parameters.num_workers=1
stamp=time.monotonic()
stop=Event()
import threading
locked=threading.Lock()
def progress():
    state["used"]=min(budget,used+time.monotonic()-stamp+1)
    save(statefile,state)
def pulse():
    while not stop.wait(1):
        with locked:progress()
class Capture(cp_model.CpSolverSolutionCallback):
    def on_solution_callback(self):
        vs={k:n for k,n in fixed_values.items()}
        vs.update({k:self.value(v) for k,v in allvars.items()})
        sol=cell.attach(x,vs)
        native=x.result(solution=sol)
        x.model.freeSol(sol)
        out_schedule=normalize_schedule(cfg,native)
        assert validate(out_schedule)["valid"]
        score=max(w["loan_end"] for w in out_schedule["jobs"] if w["product"])
        with locked:
            if state["upper"] is not None and score>=state["upper"]:return
            save(out/f"schedule_{int(score)}.json",out_schedule)
            save(out/f"event_{int(score)}.json",dict(timestamp=time.time(),cmax=score,source_sha256=sha(projected),
                schedule_sha256=sha(out/f"schedule_{int(score)}.json"),source=str(projected.relative_to(JMS))))
            save(out/"hint.json",{k:v for k,v in vs.items() if v and k in allvars})
            state["upper"]=score
            progress()
with (out/"solver.log").open("a",encoding="utf8",buffering=1) as log:
    engine.log_callback=lambda line:log.write(line.rstrip()+"\n")
    progress()
    th=Thread(target=pulse,daemon=True);th.start()
    status=engine.solve(cp,Capture())
    stop.set();th.join()
state.update(status=engine.status_name(status),used=used+engine.wall_time,lower_fixed_skeleton=engine.best_objective_bound)
save(out/"result.json",state)

"""Lift the recipe, pair membership, chamber assignments and cycles of a relaxed solution."""
from dataclasses import replace
from pathlib import Path
import sys
from run import JMS,OUT,load,atomic
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/"huber_residence_20261125"))
from solver import cell,read,save,sha
from score import metrics
sys.path.insert(0,str(cell.BACKENDS["D"]))
sys.path.insert(0,str(HERE.parent/"pareto_rl_dmct_20261119"))
from model import Config,Integrated
from witness import sparse_witness
from seed import normalize_schedule

recipe=sys.argv[1];projected=Path(sys.argv[2]);cap=int(sys.argv[3]); lower=int(sys.argv[4])
out=OUT/"native"/recipe/f"{projected.stem}_cap{cap}"
out.mkdir(parents=True,exist_ok=True)
if (out/"primary.json").is_file():
    r=load(out/"primary.json")
    assert sha(out/"schedule.json")==r["schedule_sha256"] and sha(out/"assignment.json.gz")==r["assignment_sha256"]
    sys.exit(0)
doc=load(OUT/recipe/"prepared/schedule.json")
cfg=Config(**doc["config"])
values=load(projected)
labels=sorted([w for w in doc["jobs"] if w["product"]],key=lambda w:(w["pjob"],w["pjob_index"]))
from collections import defaultdict
members=defaultdict(list)
for i,w in enumerate(labels):
    pos=[(c,q,s) for c in range(2) for q in range(4) for s in range(2) if values.get(f"w{i}_{c}_{q}_{s}",0)]
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
support_id=8
for c in range(2):
    for q in range(4):
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
small=replace(cfg,max_pairs=support_id,max_cycles=max(map(len,cycles.values())),horizon=1500)
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
m.addCons(x.cmax>=lower)
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
engine=cp_model.CpSolver();engine.parameters.num_workers=1;engine.parameters.max_time_in_seconds=120
engine.parameters.log_search_progress=True;engine.parameters.log_to_stdout=False
with (out/"grid.log").open("w",encoding="utf8",buffering=1) as log:
    engine.log_callback=lambda line:log.write(line.rstrip()+"\n");status=engine.solve(cp)
print("grid",engine.status_name(status),flush=True)
if status in (cp_model.FEASIBLE,cp_model.OPTIMAL):
    raw={k:n/scales[k] for k,n in fixed_values.items()}
    raw.update({k:engine.value(v)/scales[k] for k,v in allvars.items()})
    sol=cell.attach(x,raw)
    proposal=normalize_schedule(cfg,x.result(solution=sol))
    checked=cell.lift(cfg,sparse_witness(cfg,proposal),None,rebuild=True)
    if not checked:raise ValueError("Native lift")
    sched,ass,_,replay,rows=checked
    f=metrics(sched); assert f["cmax"] <= cap and f["cmax"]>=lower and replay["valid"]
    save(out/"schedule.json",sched);save(out/"assignment.json.gz",ass)
    save(out/"primary.json",dict(metrics=f,checked_C_lower=lower,rows=rows,replay=replay,schedule_sha256=sha(out/"schedule.json"),
          assignment_sha256=sha(out/"assignment.json.gz"),code_sha256=sha(Path(__file__)),seconds=engine.wall_time))
    print(f,flush=True)
else:print("No verified witness",flush=True)

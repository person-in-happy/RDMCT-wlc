"""Seek a physical four-cycle mixed chain for the unrestricted H=10 low-spread-weight endpoints."""
import sys
from dataclasses import replace
from pathlib import Path
here=Path(__file__).resolve().parent

from solver import cell,HERE,read,save,sha
from score import metrics
sys.path.insert(0,str(cell.BACKENDS["D"]))
sys.path.insert(0,str(HERE.parent/"pareto_rl_dmct_20261119"))
from model import Config,Integrated
from witness import sparse_witness
from seed import normalize_schedule
from validate import validate

root=HERE.parents[1]/"results/huber_residence_20261125"
out=root/"witnesses_grid/D_n8_H10_mixed_dual"
out.mkdir(exist_ok=True,parents=True)
cfg=Config(**read(root.parent/"table4_one_percent_20261124/inputs/D_n8_H10_mixed_dual/input.json")["config"])
small=replace(cfg,max_pairs=12,max_cycles=4,horizon=2400)
template={0:["LP1_W1","LP2_W1"],1:["LP3_W1","LP4_W1"],2:["LP1_W2","LP2_W2"],
          3:["LP3_W2","D1"],4:["LP4_W2","D2"],8:["D3","D4"],9:["D3","D4"],10:["D5","D6"],11:["D5","D6"]}
cycles={3:[(8,0,149),(9,1,418)],2:[(10,2,234),(2,3,328),(3,4,422.625),(4,11,516.625)]}
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
    chamber=3 if p in (0,1,8,9) else 2
    mode="4x1" if chamber==3 else "2x2"
    for c in cfg.chambers:pin(x.pair.chamber[p,c],int(bool(members) and chamber==c))
    for k in ("4x1","2x2","clean"):pin(x.pair.mode[p,k],int(bool(members) and mode==k))
for c in cfg.chambers:
    for q in range(x.Q):
        step=cycles[c][q] if q<len(cycles[c]) else None
        mode="4x1" if c==3 else "2x2"
        pin(x.cy.used[c,q],int(bool(step)))
        if step and c==2:pin(x.cy.start[c,q],step[2])
        if step and c==3:
            m.addCons(x.cy.start[c,q]>=95+235*q);m.addCons(x.cy.start[c,q]<=215+285*q)
        for p in range(x.P):
            pin(x.cy.occupancy[p,c,q],int(bool(step) and p in step[:2]))
            pin(x.front[p,c,q],int(bool(step) and p==step[1]))
        for k in ("4x1","2x2","clean"):pin(x.cy.kind[c,q,k],int(bool(step) and k==mode))
for p,rt in [(0,0),(1,0),(2,6.625),(3,6.625),(4,7)]:
    m.addCons(x.unload[p]["s"]-x.load[p]["e"]==180+rt)
m.addCons(x.cmax<=700)
# Search a restricted 1/8-second lattice (only witnesses use this restriction).
# Re-evaluate the result on the non-discretized original model before saving.
from ortools.sat.python import cp_model
from math import ceil,floor
cp=cp_model.CpModel()
allvars={};fixed_values={};scales={}
for v in m.getVars(transformed=False):
    scale=8 if v.vtype()=="CONTINUOUS" else 1
    lo=max(-10000000,ceil(scale*v.getLbGlobal()-1e-8));hi=min(10000000,floor(scale*v.getUbGlobal()+1e-8))
    if lo==hi:fixed_values[v.name]=lo
    else:allvars[v.name]=cp.new_int_var(lo,hi,v.name)
    scales[v.name]=scale
for row in m.getConss():
    assert row.isLinear()
    terms=[];constant=0
    for name,a in m.getValsLinear(row).items():
        w=round(8*a/scales[name]);assert abs(w-8*a/scales[name])<1.e-8
        if name in fixed_values:constant+=w*fixed_values[name]
        else:terms.append(w*allvars[name])
    lo,hi=m.getLhs(row),m.getRhs(row)
    if lo>-1.e15:cp.add(sum(terms)>=ceil(8*lo-constant-1e-7))
    if hi<1.e15:cp.add(sum(terms)<=floor(8*hi-constant+1e-7))
cp.minimize(allvars[x.cmax.name])
engine=cp_model.CpSolver();engine.parameters.num_workers=1;engine.parameters.max_time_in_seconds=55
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
    f=metrics(sched); assert abs(f["secondary"]-3.4296875)<1e-6 and f["clean_deficit"]==0
    save(out/"schedule.json",sched);save(out/"assignment.json.gz",ass)
    save(out/"primary.json",dict(metrics=f,lower=3.4296875,rows=rows,replay=replay,schedule_sha256=sha(out/"schedule.json"),
          assignment_sha256=sha(out/"assignment.json.gz"),code_sha256=sha(Path(__file__)),seconds=engine.wall_time))
    print(f,flush=True)
else:print("No verified witness",flush=True)

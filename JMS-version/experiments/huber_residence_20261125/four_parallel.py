"""Construct four-product Huber-optimal witnesses using two singleton 2x2 product pairs."""
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

h=int(sys.argv[1])
variant=sys.argv[2]
assert variant in ("concurrent","tight")
root=HERE.parents[1]/"results"
case=f"D_n4_H{h}_mixed_dual"
out=root/"huber_residence_20261125"/f"witnesses_{variant}"/case
out.mkdir(exist_ok=True,parents=True)
config=root/"table4_one_percent_20261124/inputs"/case/"input.json"
cfg=Config(**read(config)["config"])
small=replace(cfg,max_pairs=9,max_cycles=4,horizon=2400)
template={0:["LP1_W1","LP2_W1"],1:["LP3_W1","D1"],2:["LP4_W1","D2"],
          4:["D3","D4"],5:["D5","D6"],6:["D5","D6"]}
first,other=(170,216) if variant=="concurrent" else (135,190)
cycles={3:[(4,0,other)],2:[(5,1,first),(1,2,first+94.75),(2,6,first+188.75)]}
if h==3:
    template.update({7:["D1","D2"],8:["D3","D4"]})
    cycles[2].append((7,8,first+400))
x=Integrated(small);m=x.model
cell.scip_settings(m,dict(n=x.N,seed=1,seconds=30,gap=0),out)
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
    chamber=3 if p in (0,4) else 2
    mode="4x1" if chamber==3 else "clean" if p in (7,8) else "2x2"
    for c in cfg.chambers:pin(x.pair.chamber[p,c],int(bool(members) and chamber==c))
    for k in ("4x1","2x2","clean"):pin(x.pair.mode[p,k],int(bool(members) and mode==k))
for c in cfg.chambers:
    for q in range(x.Q):
        step=cycles[c][q] if q<len(cycles[c]) else None
        mode="4x1" if c==3 else "clean" if q==3 else "2x2"
        pin(x.cy.used[c,q],int(bool(step)))
        if step:pin(x.cy.start[c,q],step[2])
        for p in range(x.P):
            pin(x.cy.occupancy[p,c,q],int(bool(step) and p in step[:2]))
            pin(x.front[p,c,q],int(bool(step) and p==step[1]))
        for k in ("4x1","2x2","clean"):pin(x.cy.kind[c,q,k],int(bool(step) and k==mode))
for p,rt in [(0,0),(1,6.75),(2,7)]:
    m.addCons(x.unload[p]["s"]-x.load[p]["e"]==180+rt)
m.setObjective(x.cmax,"minimize");m.optimize()
status=str(m.getStatus());print("Compact",status,flush=True)
if m.getNSols():
    proposal=normalize_schedule(cfg,x.result(solution=m.getBestSol()))
    checked=cell.lift(cfg,sparse_witness(cfg,proposal),None,rebuild=True)
    if not checked:raise ValueError("Native lift")
    sched,ass,_,replay,rows=checked
    f=metrics(sched); assert abs(f["mean_residence"]-3.4375)<1e-6 and abs(f["residence_range"]-.25)<1e-6 and f["clean_deficit"]==0
    save(out/"schedule.json",sched);save(out/"assignment.json.gz",ass)
    save(out/"primary.json",dict(metrics=f,lower=3.46875,config_sha256=sha(config),rows=rows,replay=replay,schedule_sha256=sha(out/"schedule.json"),
          assignment_sha256=sha(out/"assignment.json.gz"),code_sha256=sha(Path(__file__)),seconds=m.getSolvingTime()))
    print(f,flush=True)
else:print("No verified witness",flush=True)

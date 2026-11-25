"""Shorten one already feasible H=10 low-beta witness with the entire integer structure fixed."""
from pathlib import Path
import sys
here=Path(__file__).resolve().parent
sys.path.insert(0,str(here.parent))
from solver import cell,HERE,read,save,sha
from score import metrics
sys.path.insert(0,str(cell.BACKENDS["D"]))
from model import Config,Integrated
from validate import validate

root=HERE.parents[1]/"results/residence_objective_20261125/preference_review"
src=root/"n8_H10_low_beta";out=root/"n8_H10_low_beta_retimed"
out.mkdir(exist_ok=True,parents=True)
cfg=Config(**read(src/"schedule.json")["config"]);x=Integrated(cfg);m=x.model
original_rows=m.getNConss()
old=cell.values(src/"assignment.json.gz")
cell.scip_settings(m,dict(n=x.N,seed=1,seconds=20,gap=0),out)
m.setRealParam("numerics/feastol",1.e-8)
for v in m.getVars(transformed=False):
    if v.vtype()!="CONTINUOUS":
        z=round(old.get(v.name,0));m.chgVarLb(v,z);m.chgVarUb(v,z)
for p,rt in [(0,0),(1,0),(2,6),(3,6),(4,7)]:
    m.addCons(x.unload[p]["s"]-x.load[p]["e"]==180+rt)
m.setObjective(x.cmax,"minimize")
assert m.addSol(cell.attach(x,old))
m.optimize()
s=m.getBestSol()
if s is not None:
    result=x.result(solution=s)
    values={v.name:m.getSolVal(s,v) for v in m.getVars(transformed=False)}
    r=validate(result);f=metrics(result);assert r["valid"] and abs(f["mean_residence"]-3.125)<1.e-8 and abs(f["residence_range"]-1)<1.e-8 and f["clean_deficit"]==0
    save(out/"schedule.json",result);save(out/"assignment.json.gz",cell.sparse(values))
    save(out/"primary.json",dict(scope="fixed all integer and synchronization choices",status=str(m.getStatus()),rows=original_rows,replay=r,metrics=f,source_sha256=sha(src/"assignment.json.gz"),assignment_sha256=sha(out/"assignment.json.gz"),schedule_sha256=sha(out/"schedule.json"),code_sha256=sha(Path(__file__))))
    print(f,flush=True)

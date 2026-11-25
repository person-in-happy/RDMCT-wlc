"""Realize the all-domain lower bound for the quadratic penalty on a fixed, validated H=10 structure."""
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
src=root/"n8_H10_low_beta";out=root/"n8_H10_quadratic"
out.mkdir(exist_ok=True,parents=True)
cfg=Config(**read(src/"schedule.json")["config"]);x=Integrated(cfg);m=x.model
original_rows=m.getNConss()
old=cell.values(src/"assignment.json.gz")
cell.scip_settings(m,dict(n=x.N,seed=1,seconds=20,gap=0),out)
m.setRealParam("numerics/feastol",1.e-8)
for v in m.getVars(transformed=False):
    if v.vtype()!="CONTINUOUS":
        z=round(old.get(v.name,0));m.chgVarLb(v,z);m.chgVarUb(v,z)
for p,rt in [(0,0),(1,0),(2,109/16),(3,109/16),(4,7)]:
    m.addCons(x.unload[p]["s"]-x.load[p]["e"]==180+rt)
m.setObjective(x.cmax,"minimize")

m.optimize()
s=m.getBestSol()
if s is not None:
    result=x.result(solution=s)
    values={v.name:m.getSolVal(s,v) for v in m.getVars(transformed=False)}
    r=validate(result);f=metrics(result);assert r["valid"] and abs(f["mean_residence"]-439/128)<1.e-8 and abs(f["residence_range"]-3/16)<1.e-8 and f["clean_deficit"]==0
    save(out/"schedule.json",result);save(out/"assignment.json.gz",cell.sparse(values))
    save(out/"primary.json",dict(scope="all-structure quadratic objective bound attained; makespan minimized only within fixed structure",quadratic_score=f["mean_residence"]+f["residence_range"]**2,quadratic_lower=3.5-(3/16)**2,status=str(m.getStatus()),rows=original_rows,replay=r,metrics=f,source_sha256=sha(src/"assignment.json.gz"),assignment_sha256=sha(out/"assignment.json.gz"),schedule_sha256=sha(out/"schedule.json"),code_sha256=sha(Path(__file__))))
    print(f,flush=True)

else: print("No witness",m.getStatus(),flush=True)

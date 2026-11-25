"""Check the dyadic H=10 quadratic endpoint in every native model row using integer arithmetic."""
from fractions import Fraction as F
from pathlib import Path
import sys
here=Path(__file__).resolve().parent
sys.path.insert(0,str(here.parent))
from solver import HERE,cell,read,save,sha
from score import metrics
sys.path.insert(0,str(cell.BACKENDS["D"]))
from model import Config,Integrated
from validate import validate

root=HERE.parents[1]/"results/residence_objective_20261125"
out=root/"preference_review"
src=out/"n8_H10_quadratic";basis=out/"audit.json"
case=read(src/"schedule.json")
p=read(src/"primary.json")
assert sha(src/"schedule.json")==p["schedule_sha256"] and sha(src/"assignment.json.gz")==p["assignment_sha256"]
x=Integrated(Config(**case["config"]));m=x.model;raw=cell.values(src/"assignment.json.gz")
scaled={k:round(16*v) for k,v in raw.items()}
max_delta=max(abs(raw[k]-n/16) for k,n in scaled.items());assert max_delta<1e-8
for var in m.getVars(transformed=False):
    n=scaled.get(var.name,0)
    assert 16*var.getLbGlobal()<=n<=16*var.getUbGlobal()
    if var.vtype()!="CONTINUOUS":assert n%16==0

def number(n):return int(n) if n==int(n) else F.from_float(n)
for row in m.getConss():
    assert row.isLinear()
    act=sum(number(coef)*scaled.get(k,0) for k,coef in m.getValsLinear(row).items())
    assert 16*number(m.getLhs(row))<=act<=16*number(m.getRhs(row)),row.name
rows=m.getNConss()
s=cell.attach(x,{k:n/16 for k,n in scaled.items()});d=x.result(solution=s);replay=validate(d);assert replay["valid"]
r=metrics(d)
assert r["cmax"]==1100.8125 and F(r["mean_residence"])==F(439,128) and F(r["residence_range"])==F(3,16) and r["clean_deficit"]==0
exact=F(r["mean_residence"])+F(r["residence_range"])**2
assert exact==F(887,256)==F(7,2)-F(3,16)**2
assert F(223,64)==F(7,2)-F(1,8)**2
save(out/"quadratic_certificate.json",dict(tau_seconds=1,short_arc=dict(t=[0,.875],C="553+t",minimum="4.25-1.75*t+t*t",terminal_C=553.875,terminal_Rq=float(F(223,64))),
    unrestricted_H3_minimum=float(F(223,64)),unrestricted_H10_minimum=float(exact),H10_witness_C=r["cmax"],
    H10_witness_metrics=r,exact_native_rows=rows,grid_denominator=16,rounding_delta=max_delta,replay=replay,
    source_sha256={k:sha(v) for k,v in {"preference_audit":basis,"H10_endpoint":src/"primary.json","script":Path(__file__)}.items()}))
print(rows,exact,flush=True)

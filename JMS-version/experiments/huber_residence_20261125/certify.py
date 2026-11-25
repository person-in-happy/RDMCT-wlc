"""Exact native feasibility audit for Huber attainers and analytical supporting-line certificate."""
from fractions import Fraction as F
from pathlib import Path
import sys
from solver import cell,HERE,read,save,sha
from score import metrics,physical_lower,final_wafers
sys.path.insert(0,str(cell.BACKENDS["D"]))
from model import Config,Integrated
from validate import validate

root=HERE.parents[1]/"results"
out=root/"huber_residence_20261125"
prior=root/"residence_objective_20261125"
def number(v):return int(v) if v==int(v) else F.from_float(v)
def audit(path):
    primary=read(path/"primary.json")
    for f,k in (("schedule.json","schedule_sha256"),("assignment.json.gz","assignment_sha256")):
        assert sha(path/f)==primary[k]
    data=read(path/"schedule.json");cfg=Config(**data["config"]);x=Integrated(cfg);m=x.model
    raw=cell.values(path/"assignment.json.gz");scaled={k:round(8*v) for k,v in raw.items()}
    diff=max(abs(v-scaled[k]/8) for k,v in raw.items());assert diff<1.e-8
    for v in m.getVars(transformed=False):
        n=scaled.get(v.name,0);assert 8*v.getLbGlobal()<=n<=8*v.getUbGlobal()
        assert v.vtype()=="CONTINUOUS" or n%8==0
    for row in m.getConss():
        assert row.isLinear();activity=sum(number(c)*scaled.get(k,0) for k,c in m.getValsLinear(row).items())
        assert 8*number(m.getLhs(row))<=activity<=8*number(m.getRhs(row)),row.name
    sol=cell.attach(x,{k:v/8 for k,v in scaled.items()});d=x.result(solution=sol)
    f=metrics(d);r=validate(d);assert r["valid"] and f["secondary"]==physical_lower(cfg)
    n=sum(sum(x.values()) for x in cfg.load_ports.values());mix=sum(x.get("2x2",0) for x in cfg.load_ports.values())
    result=dict(metrics=f,lower=physical_lower(cfg),product_count=n,mixed=mix,terminal_wafer_bound=final_wafers(mix,cfg.cleaning_interval),
                exact_native_rows=m.getNConss(),grid_denominator=8,largest_snap=diff,checks=r["checks"],witness_sha256=sha(path/"primary.json"))
    m.freeSol(sol);m.freeProb()
    return result
a=read(prior/"preference_review/audit.json")
assert a["old_continuous_certificate_sha256"]==sha(prior/"best_reuse/continuous_frontier/certificate.json")
assert a["beta2_grid_certificate_sha256"]==sha(prior/"preference_review/beta2_scale_1000/result.json")
cert={}
for sub in sorted((out/"witnesses").iterdir()):
    cert[sub.name]=audit(sub)
improved=audit(out/"witnesses_grid_middle/D_n8_H10_mixed_dual")
latest_bound=out/"frontier/H10_attainment_hardware_610/result.json";bound=read(latest_bound)
assert bound["lower_C"]==576.625 and improved["metrics"]["cmax"]==576.625
proof=dict(H10_attainment=dict(lower=bound["lower_C"],upper=improved["metrics"]["cmax"],witness=improved,lower_source_sha256=sha(latest_bound)),tau_seconds=1,gamma_seconds_per_unused_cycle=1,early_clean_deficit_only=True,
           interpolation_parameter=[0,.75],curve="C=553+t; fB=3.75-0.75*t+0.5*t^2",
           short_end=[553.75,3.46875],H3_complete_frontier=True,H10_post_554_frontier="not identified",
           H10_global_secondary=3.4296875,H10_minimum_required_makespan="exactly 576.625",
           global_table4=cert,code={k:sha(HERE/k) for k in ("score.py","solver.py","certify.py","four_witness.py","other_witnesses.py")},
           anchors={str(k.relative_to(root)):sha(k) for k in (prior/"preference_review/audit.json",prior/"best_reuse/continuous_frontier/certificate.json")})
save(out/"frontier/certificate.json",proof)
print([(k,v["lower"]) for k,v in cert.items()],flush=True)

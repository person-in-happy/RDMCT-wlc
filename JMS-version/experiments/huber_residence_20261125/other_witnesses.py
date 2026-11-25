"""Reuse, interpolate, or retime native assignments that attain the Huber range lower bound."""
from pathlib import Path
import sys
from solver import HERE,cell,read,save,sha
from score import metrics,physical_lower
sys.path.insert(0,str(cell.BACKENDS["D"]))
from model import Config,Integrated
from validate import validate

root=HERE.parents[1]/"results"
old=root/"residence_objective_20261125"
def generate(n,h):
    case=f"D_n{n}_H{h}_mixed_dual"
    dest=root/"huber_residence_20261125/witnesses"/case
    dest.mkdir(parents=True,exist_ok=True)
    config=root/"table4_one_percent_20261124/inputs"/case/"input.json"
    cfg=Config(**read(config)["config"])
    source=old/("reuse/transfers/"+case) if n==2 else old/f"best_reuse/n8_H{h}/retained_product_times"
    if (n,h)==(8,10):source=old/"preference_review/n8_H10_low_beta"
    refs=[config,source/"assignment.json.gz",source/"schedule.json"]
    raw=cell.values(source/"assignment.json.gz")
    if (n,h)==(8,3):
        second=old/f"best_reuse/n8_H{h}/ideal_fixed/assignment.json.gz";refs.append(second)
        right=cell.values(second)
        raw={k:(round(raw.get(k,0))+3*round(right.get(k,0)))/4 for k in raw.keys()|right.keys()}
    elif (n,h)==(8,10):
        x=Integrated(cfg);m=x.model
        cell.scip_settings(m,dict(n=n,seed=1,seconds=30,gap=0),dest)
        m.setRealParam("numerics/feastol",1e-8)
        for v in m.getVars(transformed=False):
            if v.vtype()!="CONTINUOUS":
                value=round(raw.get(v.name,0));m.chgVarLb(v,value);m.chgVarUb(v,value)
        for p,r in [(0,0),(1,0),(2,6.625),(3,6.625),(4,7)]:
            m.addCons(x.unload[p]["s"]-x.load[p]["e"]==180+r)
        m.setObjective(x.cmax,"minimize");m.optimize()
        s=m.getBestSol()
        if s is None:raise ValueError(m.getStatus())
        raw={v.name:m.getSolVal(s,v) for v in m.getVars(transformed=False)};m.freeProb()
    checked=cell.lift(cfg,raw,None,rebuild=True)
    if not checked:raise ValueError("Original physical model rejected witness")
    data,values,_,replay,rows=checked
    f=metrics(data);lb=physical_lower(cfg)
    assert replay["valid"] and abs(f["secondary"]-lb)<1e-7
    save(dest/"schedule.json",data);save(dest/"assignment.json.gz",values)
    save(dest/"primary.json",dict(rows=rows,metrics=f,lower=lb,replay=replay,
         origins={str(p.relative_to(root)):sha(p) for p in refs},code_sha256=sha(Path(__file__)),
         schedule_sha256=sha(dest/"schedule.json"),assignment_sha256=sha(dest/"assignment.json.gz")))
    print(n,h,f,flush=True)
for n,h in [(2,3),(8,3),(8,10)]:generate(n,h)

"""Minimize product-return time on each verified quota-optimal witness's fixed resource order."""
from pathlib import Path
import statistics
import sys
import time

from solver import cell, metrics, objective_terms, read, save, sha

BASE = Path(__file__).resolve().parents[2] / "results/quota_objective_20261125"
sys.path.insert(0,str(cell.BACKENDS["D"]))
from model import Config, Integrated


def shorten(src, out):
    record = read(src / "primary.json")
    schedule = read(src / "schedule.json")
    target = metrics(schedule)["secondary"]
    if abs(target-record["lower"])>1e-6 or sha(src/"assignment.json.gz")!=record["assignment_sha256"]:
        raise ValueError("The original optimality record is inconsistent")
    if (out/"primary.json").exists():
        result = read(out/"primary.json")
        if (result["source_assignment"]==record["assignment_sha256"] and result["replay"]["valid"]
            and all(sha(out/key)==val for key,val in result["files"].items())):
            return result
    out.mkdir(parents=True,exist_ok=True)
    start=time.monotonic()
    cfg=Config(**schedule["config"])
    x=Integrated(cfg)
    m=x.model
    cell.scip_settings(m,dict(n=x.N,seed=1,seconds=None,gap=0),out)
    m.setRealParam("numerics/feastol",1e-8)
    native=list(m.getVars(transformed=False))
    source_values=cell.values(src/"assignment.json.gz")
    original=cell.attach(x,source_values)
    m.freeSol(original)
    for var in native:
        if var.vtype()!="CONTINUOUS":
            value=round(source_values.get(var.name,0.))
            m.chgVarLb(var,value)
            m.chgVarUb(var,value)
    obj,_=objective_terms(x,source_values,True,0.,1.)
    m.addCons(obj<=target)
    m.setObjective(x.cmax,"minimize")
    m.addSol(cell.attach(x,source_values))
    m.optimize()
    if str(m.getStatus())!="optimal":
        raise ValueError(m.getStatus())
    incumbent=m.getBestSol()
    values={v.name:m.getSolVal(incumbent,v) for v in native}
    lower=m.getDualbound()
    m.freeProb()
    sched, assignment, _, replay, rows = cell.lift(cfg,values,None,rebuild=True)
    measured=metrics(sched)
    if not replay["valid"] or abs(measured["secondary"]-target)>1e-5 or abs(measured["cmax"]-lower)>1e-5:
        raise ValueError((measured,lower,replay))
    save(out/"schedule.json",sched)
    save(out/"assignment.json.gz",assignment)
    result=dict(metrics=measured,replay=replay,original_rows=rows,source_assignment=record["assignment_sha256"],
                lower_B=target,conditional_lower_C=lower,scope="Only the archived resource order, pairing, chamber assignment, production and cleaning decisions, and sync flags are fixed.",wall_s=time.monotonic()-start,
                files={k:sha(out/k) for k in ("schedule.json","assignment.json.gz")})
    save(out/"primary.json",result)
    return result


if __name__=="__main__":
    cases=sorted((BASE/"witnesses").glob("D_*"))
    if len(cases)!=5:
        raise ValueError("Expected five quota-optimal witnesses")
    elapsed=[]
    for i,source in enumerate(cases):
        left=len(cases)-i
        median=statistics.median(elapsed) if elapsed else 6
        print(f"Validated {i}/{len(cases)}, failed 0. Elapsed {sum(elapsed):.1f}s. Estimated total {sum(elapsed)+left*median:.1f}s, remaining {left*median:.1f}s (per-witness median, initially 6s).",flush=True)
        started=time.monotonic()
        result=shorten(source,BASE/"shortest_fixed_order"/source.name)
        elapsed.append(time.monotonic()-started)
        print(source.name,result["metrics"],flush=True)
        save(BASE/"shortest_fixed_order/progress.json",dict(validated=i+1,total=len(cases),failed=0,wall_s=sum(elapsed),
            estimated_remaining_s=(left-1)*statistics.median(elapsed),estimated_total_s=sum(elapsed)+(left-1)*statistics.median(elapsed),
            basis="median completed witness elapsed time, single worker; independent hash-verified endpoint; interrupted LP restarts from its verified feasible source"))

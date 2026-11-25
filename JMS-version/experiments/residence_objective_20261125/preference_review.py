"""Independent epsilon-constraint LPs on the common native discrete structure of the 8-wafer endpoints."""
import argparse
from fractions import Fraction
from pathlib import Path
import statistics
import sys
import time

from solver import cell, metrics, objective_terms, read, save, sha

ROOT=Path(__file__).resolve().parents[2]/"results/residence_objective_20261125"
OUT=ROOT/"preference_review/epsilon_native"
sys.path.insert(0,str(cell.BACKENDS["D"]))
from model import Config, Integrated


def solve(h, tenth, out, product=False):
    src=ROOT/f"best_reuse/n8_H{h}/retained_product_times"
    cap=Fraction(553)+Fraction(tenth,10)
    identity=dict(cap=str(cap),gamma=1,beta=1,seed=1,H=h,schedule=sha(src/"schedule.json"),
                  assignment=sha(src/"assignment.json.gz"),solver=sha(Path(__file__).with_name("solver.py")))
    if product:
        identity.update(objective="mean*(1+within_recipe_range/3.5s)+actual_clean_deficit",tolerance=1e-7)
    file=out/"result.json"
    if file.exists():
        archived=read(file)
        if (archived["identity"]==identity and archived["replay"]["valid"]
                and all(sha(out/k)==v for k,v in archived["files"].items())):
            return archived
    out.mkdir(parents=True,exist_ok=True)
    cfg=Config(**read(src/"schedule.json")["config"])
    warm=cell.values(src/"assignment.json.gz")
    x=Integrated(cfg)
    m=x.model
    native=list(m.getVars(transformed=False))
    rows=m.getNConss()
    cell.scip_settings(m,dict(n=x.N,seed=1,seconds=None,gap=0),out)
    m.setRealParam("numerics/feastol",1e-8)
    for var in native:
        if var.vtype()!="CONTINUOUS":
            value=round(warm.get(var.name,0))
            m.chgVarLb(var,value)
            m.chgVarUb(var,value)
    m.addCons(x.cmax<=float(cap))
    objective,extra=objective_terms(x,warm,True)
    if product:
        start_metrics=metrics(read(src/"schedule.json"))
        deficit=start_metrics["clean_deficit"]
        spread=next(v for v in m.getVars() if v.name=="residence_spread")
        average=m.addVar(name="mean_for_product",lb=0,ub=cfg.module_residency)
        score=m.addVar(name="multiplicative_score",lb=0)
        m.addCons(average==objective-spread-deficit)
        m.addCons(score>=average*(1+spread/3.5)+deficit)
        m.setRealParam("limits/gap",1e-7)
        extra[average.name]=start_metrics["mean_residence"]
        extra[score.name]=start_metrics["mean_residence"]*(1+start_metrics["residence_range"]/3.5)+deficit
        objective=score
    m.setObjective(objective,"minimize")
    assert m.addSol(cell.attach(x,warm|extra))
    m.optimize()
    status=str(m.getStatus())
    assert status=="optimal" or (product and status=="gaplimit")
    best=m.getBestSol()
    values={v.name:m.getSolVal(best,v) for v in native}
    lower,upper=m.getDualbound(),m.getPrimalbound()
    m.freeProb()
    sched,assignment,_,replay,nrows=cell.lift(cfg,values,None,rebuild=True)
    measure=metrics(sched)
    if product:
        measure["linear_secondary"]=measure["secondary"]
        measure["secondary"]=measure["mean_residence"]*(1+measure["residence_range"]/3.5)+measure["clean_deficit"]
    assert replay["valid"] and nrows==rows
    assert abs(lower-upper)<1e-5 and abs(measure["secondary"]-upper)<1e-6
    assert measure["cmax"]<=float(cap)+1e-6
    # The supporting line here is checked only after the solve, never used as an LP constraint.
    t=cap-553
    theory=(13+t)*(9-2*t)/28 if product else Fraction(17,4)-Fraction(3,4)*t
    assert abs(measure["secondary"]-float(theory))<1e-6
    save(out/"schedule.json",sched)
    save(out/"assignment.json.gz",assignment)
    result=dict(identity=identity,status=status,rows=rows,replay=replay,measured=measure,
                conditional_lower=lower,conditional_upper=upper,independent_global_value=str(theory),
                files={k:sha(out/k) for k in ("schedule.json","assignment.json.gz")},
                scope="All native times optimized, endpoint discrete structure fixed; 553s feasible point as sole start. The separate global supporting-line proof was not imposed on this LP.")
    save(file,result)
    return result


def run(product):
    import msvcrt
    out=ROOT/"preference_review/multiplicative_residence_epsilon" if product else OUT
    out.mkdir(parents=True,exist_ok=True)
    with (out/"controller.lock").open("a+b") as lock:
        lock.seek(0)
        try:
            msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
        except OSError:
            print("Another epsilon-constraint controller is active.",flush=True)
            return
        completed=[]
        durations=[]
        now=time.monotonic()
        for h in (3,10):
            for tenth in (2,4,6,8):
                eta=(8-len(completed))*(statistics.median(durations) if durations else 5)
                elapsed=time.monotonic()-now
                state=dict(completed=completed,expected=8,failed=0,elapsed_wall_s=elapsed,
                           remaining_s=eta,estimated_total_s=elapsed+eta,threads=1,
                           basis="median completed native LP, historical 5s/LP before first finish; reuse hash-verified endpoints, restart interrupted small LP from its independent 553s feasible start")
                save(out/"progress.json",state)
                print(f"{len(completed)}/8 verified, failed 0; H={h}, cap=553.{tenth}. Wall {elapsed:.1f}s, total {elapsed+eta:.1f}s, ETA {eta:.1f}s",flush=True)
                start=time.monotonic()
                key=f"H{h}_cap553p{tenth}"
                solve(h,tenth,out/key,product)
                completed.append(key)
                durations.append(time.monotonic()-start)
        elapsed=time.monotonic()-now
        save(out/"progress.json",dict(state,completed=completed,elapsed_wall_s=elapsed,remaining_s=0,estimated_total_s=elapsed))
        print("8/8 verified, failed 0, ETA 0s.",flush=True)


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--product",action="store_true",help="Direct constrained bilinear sensitivity solve")
    run(parser.parse_args().product)

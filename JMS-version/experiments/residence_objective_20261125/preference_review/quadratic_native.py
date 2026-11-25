"""Native convex quadratic epsilon-constraint solves on a common eight-wafer structure."""
from fractions import Fraction
import os
from pathlib import Path
import statistics
import sys
import time

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent))
from solver import cell, metrics, objective_terms, read, save, sha
sys.path.insert(0,str(cell.BACKENDS["D"]))
from model import Config,Integrated
from validate import validate

BASE=HERE.parents[2]/"results/residence_objective_20261125"
OUT=BASE/"preference_review/quadratic_native"
CAPS=(Fraction(0),Fraction(1,4),Fraction(1,2),Fraction(3,4),Fraction(7,8),Fraction(1))
TOL=1e-9

def solve(h,extension,directory):
    cap=553+extension
    source=BASE/f"best_reuse/n8_H{h}/retained_product_times"
    start=read(source/"schedule.json")
    settings=dict(H=h,cap=str(cap),tau=1,gamma=1,seed=1,threads=1,original_model="D",
        code_sha256=sha(Path(__file__)),native_solver_helpers=sha(HERE.parent/"solver.py"),
        source_schedule=sha(source/"schedule.json"),source_assignment=sha(source/"assignment.json.gz"))
    output=directory/"result.json"
    if output.exists():
        old=read(output)
        if old["settings"]==settings and old["physical_replay"]["valid"] and all(sha(directory/n)==s for n,s in old["files"].items()):
            return old
        raise ValueError("A frozen quadratic endpoint differs from the requested model")
    directory.mkdir(parents=True,exist_ok=True)
    cfg=Config(**start["config"]);x=Integrated(cfg);m=x.model
    native=m.getVars(transformed=False);native_rows=m.getNConss()
    cell.scip_settings(m,dict(n=x.N,seed=1,seconds=None,gap=0),directory)
    m.setRealParam("numerics/feastol",TOL)
    m.setRealParam("limits/absgap",1.e-9)
    warm=cell.values(source/"assignment.json.gz")
    ints=0
    for v in native:
        if v.vtype()!="CONTINUOUS":
            z=round(warm.get(v.name,0.))
            m.chgVarLb(v,z);m.chgVarUb(v,z);ints+=1
    m.addCons(x.cmax<=float(cap))
    base,extra=objective_terms(x,warm,True,range_weight=0,clean_weight=1)
    spread=next(v for v in m.getVars(transformed=False) if v.name=="residence_spread")
    epi=m.addVar(name="squared_residence_spread",lb=0,ub=cfg.module_residency**2)
    curvature=m.addCons(spread*spread<=epi,name="range_square_epigraph")
    m.setObjective(base+epi,"minimize")
    assert m.addSol(cell.attach(x,warm|extra|{epi.name:extra[spread.name]**2}))
    m.optimize()
    first=m.getBestSol()
    if first is None:raise ValueError("No native QCP incumbent")
    solvalues={v.name:m.getSolVal(first,v) for v in native}
    raw=m.getPrimalbound();lower=m.getDualbound();qstatus=str(m.getStatus());sec=m.getSolvingTime()
    quick=metrics(x.result(solution=first))
    base_cap=quick["mean_residence"]+quick["clean_deficit"]
    attained_spread=quick["residence_range"]
    # After solving the requested convex objective, take the earliest actual product
    # return retaining both of its measured components (including their tolerances).
    m.freeTransform()
    m.delCons(curvature)
    m.addCons(base<=base_cap+TOL)
    m.addCons(spread<=attained_spread+TOL)
    m.setObjective(x.cmax,"minimize")
    m.optimize()
    best=m.getBestSol()
    tie_status=str(m.getStatus())
    if best is not None:
        solvalues={v.name:m.getSolVal(best,v) for v in native}
    m.freeProb()
    final=cell.lift(cfg,solvalues,None,rebuild=True)
    if not final:raise ValueError("Full original row replay rejected quadratic witness")
    schedule,assignment,_,physical,nrows=final
    f=metrics(schedule);assert nrows==native_rows and physical["valid"] and validate(schedule)["valid"]
    square=f["mean_residence"]+f["residence_range"]**2+f["clean_deficit"]
    assert f["cmax"]<=float(cap)+2e-5 and abs(square-raw)<2e-5 and lower<=square+2e-5
    save(directory/"schedule.json",schedule);save(directory/"assignment.json.gz",assignment)
    rec=dict(settings=settings,native_status=qstatus,native_primal=raw,native_dual=lower,native_absolute_gap=abs(raw-lower),
        physical_objective=square,physical_minus_native_upper=square-raw,numerical_feasibility_tolerance=TOL,
        tie_break_status=tie_status,first_solution_C=quick["cmax"],first_solution_mean=quick["mean_residence"],
        first_solution_D=attained_spread,scope="Convex QCP on every continuous native time; fixed discrete structure only. No analytical tangent or interpolated schedule imposed. Earliest measured return then selected at the attained mean-plus-E and spread.",
        native_rows=nrows,integer_variables_fixed=ints,native_QCP_solve_s=sec,metrics=f,physical_replay=physical,
        files={name:sha(directory/name) for name in ("schedule.json","assignment.json.gz")})
    save(output,rec)
    return rec

def main():
    import msvcrt,psutil
    process=psutil.Process();process.cpu_affinity([process.cpu_affinity()[-1]])
    OUT.mkdir(parents=True,exist_ok=True)
    with (OUT/"controller.lock").open("a+b") as lock:
        lock.seek(0)
        try:msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
        except OSError:return
        completed={};durs=[];clock=time.monotonic();failures={}
        for h in (3,10):
            for t in CAPS:
                tag=f"H{h}_cap{str(float(553+t)).replace('.','p')}"
                expected=12
                eta=(expected-len(completed)-len(failures))*(statistics.median(durs) if durs else 6.)
                state=dict(completed=completed,failures=failures,total=expected,worker_threads=1,
                    elapsed_s=time.monotonic()-clock,remaining_estimate_s=eta,estimated_total_s=time.monotonic()-clock+eta,
                    basis="median completed convex QCP+LP and native replay; 6 seconds per case initially; serial",
                    recovery="completed endpoints checked by hashes; interrupted small unconstrained-budget cell restarts from its checked 553s input")
                save(OUT/"progress.json",state)
                print(f"{len(completed)}/{expected} verified, failed {len(failures)}, elapsed {state['elapsed_s']:.1f}s, total {state['estimated_total_s']:.1f}s, ETA {eta:.1f}s; {tag}",flush=True)
                started=time.monotonic()
                try:
                    r=solve(h,t,OUT/tag)
                    completed[tag]={"C":r["metrics"]["cmax"],"D":r["metrics"]["residence_range"],"mean":r["metrics"]["mean_residence"],
                        "f":r["physical_objective"],"native_dual":r["native_dual"],"native_upper":r["native_primal"],"result_sha256":sha(OUT/tag/"result.json")}
                except Exception as err:
                    import traceback
                    traceback.print_exc()
                    failures[tag]=repr(err)
                durs.append(time.monotonic()-started)
        save(OUT/"progress.json",state|dict(completed=completed,failures=failures,elapsed_s=time.monotonic()-clock,
                                         remaining_estimate_s=0,estimated_total_s=time.monotonic()-clock))
        print(f"{len(completed)}/12 complete; {len(failures)} failed",flush=True)

if __name__=="__main__":main()

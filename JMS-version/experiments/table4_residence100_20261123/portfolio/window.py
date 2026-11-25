"""Use a smaller verified makespan window for difficult A searches."""
from dataclasses import replace
from pathlib import Path
import gc
import math
import sys
import time
from ortools.sat.python import cp_model
from primal import OUT, Config, TAU, case_id, cell, endpoint, product, read, sha, store_primary, validate
from inputs import Integrated, certified_capacity, save
from project import export
from worker import secondary


def run(n,h,seed):
    key=case_id(n,h)
    group=f"{key}__s{seed}"
    src=OUT/"inputs"/key
    spec=read(src/"input.json")
    cfg=Config(**spec["config"])
    initial=read(src/"schedule.json")
    vals=cell.values(src/"assignment.json.gz")
    assert sha(src/"assignment.json.gz")==spec["assignment_sha256"] and validate(initial)["valid"]
    area=OUT/"portfolio/windows"/group
    area.mkdir(parents=True,exist_ok=True)
    lower=cell.lock_bound(cfg)["lower"]
    common=cell.certify_start(cfg,initial,vals)
    upper=common[2]["cmax"]
    chosen=common
    trace=[]
    began=time.monotonic()
    while upper>(1+TAU)*lower+1e-8:
        # If the sublevel is empty, its outward integer cap is a global lower bound.
        cap=math.floor(lower*(1+TAU))
        folder=area/f"cap_{cap}"
        folder.mkdir(exist_ok=True)
        plan=certified_capacity(cfg,cap)
        # The two chambers and their eligibility are identical here. Choose a canonical
        # orientation only when the count relaxation proves one recipe per chamber.
        x=Integrated(replace(cfg,max_pairs=plan["pairs"],max_cycles=plan["cycles"]))
        if plan["separated"] and all(set(g.chambers)==set(cfg.chambers) for g in x.groups):
            for q in range(x.Q):
                x.model.addCons(x.cy.kind[cfg.chambers[0],q,"2x2"]==0)
                x.model.addCons(x.cy.kind[cfg.chambers[1],q,"4x1"]==0)
        cell.strengthen(x,dict(plan,separated=False),initial,cap)
        cp,vm,audit=export(x,vals)
        x.model.freeProb()
        del x
        gc.collect()
        cp.clear_objective()
        solver=cp_model.CpSolver()
        solver.parameters.num_search_workers=1
        solver.parameters.random_seed=seed
        solver.parameters.log_search_progress=True
        solver.parameters.log_to_stdout=False
        save(folder/"query.json",dict(cap=cap,prior_lower=lower,prior_upper=upper,plan=plan,rows=audit))
        with (folder/"solve.log").open("w",encoding="utf8",buffering=1) as stream:
            solver.log_callback=lambda t:stream.write(t.rstrip()+"\n")
            status=solver.solve(cp)
        if status==cp_model.INFEASIBLE:
            lower=cap
        elif status in (cp_model.OPTIMAL,cp_model.FEASIBLE):
            raw={name:solver.value(v) for name,v in vm.items() if solver.value(v)}
            candidate=cell.lift(cfg,raw,plan["cycles"],rebuild=True)
            if not candidate or candidate[2]["cmax"]>cap+cell.EPS:
                save(folder/"rejected.json",dict(status=solver.status_name(status),native=False))
                return False
            chosen=candidate
            upper=candidate[2]["cmax"]
        else:
            raise ValueError(solver.status_name(status))
        trace.append(dict(cap=cap,status=solver.status_name(status),lower=lower,upper=upper,seconds=solver.wall_time))
        save(area/"bounds.json",trace)
        del cp,vm,solver
        gc.collect()
    # Stage B uses exactly this run's replayed A assignment.
    r=dict(status="verified_gap",engine="makespan sublevel projection",upper=upper,lower=lower,
           seconds=time.monotonic()-began,trace=trace)
    store_primary(area/"A",chosen,r)
    endpoint(area/"A",area/"A","A",spec,seed,r)
    secondary(area/"AB",area/"A",spec,seed)
    return True


if __name__=="__main__":
    run(*map(int,sys.argv[1:]))

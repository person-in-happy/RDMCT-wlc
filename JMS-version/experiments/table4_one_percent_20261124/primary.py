"""Minimize the product-return time, accepting only native feasible incumbents."""
from dataclasses import replace
import gc
import math
import time

from ortools.sat.python import cp_model
from bench import GAP, cell, old, read, reload, save, sha, store


def search(cfg,base,folder,seed,spec):
    src=base/"A"
    path=folder/"search.json"
    signature=dict(seed=seed,model=spec["model_sha256"],input=spec["assignment_sha256"],gap=GAP,
                   config=sha(base/"input.json"))
    state=(read(path) if path.exists() else
           dict(key=signature,lower=cell.lock_bound(cfg)["lower"],upper=spec["metrics"]["cmax"],
                witness=None,seconds=0.,attempt=0))
    if state["key"]!=signature:raise ValueError("Input differs from saved search")
    if state["witness"]:src=folder/state["witness"]
    best=reload(src,cfg)
    assert abs(best[2]["cmax"]-state["upper"])<=cell.EPS
    start=time.monotonic()
    previous=state["seconds"]
    state["attempt"]+=1
    dest=folder/f"attempt_{state['attempt']:03d}"
    dest.mkdir(exist_ok=True)

    def persist():
        state["seconds"]=previous+time.monotonic()-start
        save(path,state)

    def reached():
        return state["upper"]<=(1+GAP)*state["lower"]+1e-8

    def improve(checked):
        nonlocal best
        if checked and checked[3]["valid"] and checked[2]["cmax"]<state["upper"]-cell.EPS:
            w=folder/f"witness_{time.time_ns()}"
            store(w,checked,dict(seed=seed,attempt=state["attempt"]))
            best=checked
            state.update(upper=checked[2]["cmax"],witness=w.name)
            persist()

    persist()
    if not reached():
        upper=math.ceil(state["upper"])
        plan=old.certified_capacity(cfg,upper)
        x=old.Integrated(replace(cfg,max_pairs=plan["pairs"],max_cycles=plan["cycles"]))
        cell.strengthen(x,plan,best[0],upper)
        x.model.addCons(x.cmax>=state["lower"]-1e-8)
        cp,vs,audit=old.export(x,best[1]["nonzero"])
        # Physical time rows round outwards. Only the projection's dual bound is
        # globally transferable. Every new upper bound must pass native replay.
        x.model.freeProb()
        del x
        gc.collect()
        solver=cp_model.CpSolver()
        solver.parameters.num_search_workers=1
        solver.parameters.random_seed=seed
        solver.parameters.log_search_progress=True
        solver.parameters.log_to_stdout=False
        errors=[]
        def bound(b):
            if b>state["upper"]+cell.EPS:
                errors.append(ValueError(f"Projected lower bound {b} exceeds verified incumbent"))
                solver.stop_search()
                return
            if b>state["lower"]:
                state["lower"]=min(float(b),state["upper"])
                persist()
            if reached():solver.stop_search()
        solver.best_bound_callback=bound
        class Solutions(cp_model.CpSolverSolutionCallback):
            def on_solution_callback(self):
                try:
                    if self.objective_value<state["upper"]-cell.EPS:
                        raw={k:self.value(v) for k,v in vs.items() if self.value(v)}
                        chk=cell.lift(cfg,dict(raw),plan["cycles"],rebuild=True)
                        if not chk:
                            # Only continuous retiming is permitted for this proposed structure.
                            chk=old.repair(cfg,raw,state["upper"])
                        improve(chk)
                    bound(self.best_objective_bound)
                    if reached():self.stop_search()
                except Exception as exc:
                    errors.append(exc)
                    self.stop_search()
        save(dest/"model.json",dict(cap=upper,capacity=plan,export=audit,seed=seed))
        with (dest/"solver.log").open("w",encoding="utf8",buffering=1) as log:
            solver.log_callback=lambda line:log.write(line.rstrip()+"\n")
            status=solver.solve(cp,Solutions())
        if errors:raise errors[0]
        if status in (cp_model.MODEL_INVALID,cp_model.INFEASIBLE):
            raise RuntimeError(f"Projection rejected a native feasible cap: {solver.status_name(status)}")
        bound(solver.best_objective_bound)
        save(dest/"projection.json",dict(status=solver.status_name(status),lower=solver.best_objective_bound,
                                         branches=solver.num_branches,seconds=solver.wall_time))
        del vs,cp,solver
        gc.collect()
    if not reached():
        # A relaxed optimum can have no feasible lift. Continue on the unrestricted
        # original model with its verified upper bound and the valid projection lower bound.
        x=old.Integrated(cfg)
        m=x.model
        native=dest/"native"
        native.mkdir(exist_ok=True)
        cell.scip_settings(m,dict(n=spec["n"],seed=seed,seconds=None,gap=GAP),native)
        m.addCons(x.cmax>=state["lower"]-1e-8)
        m.addCons(x.cmax<=state["upper"]+1e-7)
        m.setObjective(x.cmax,"minimize")
        m.addSol(cell.attach(x,best[1]["nonzero"]))
        m.optimize()
        if str(m.getStatus()) not in ("optimal","gaplimit"):raise RuntimeError(str(m.getStatus()))
        sol=m.getBestSol()
        checked=cell.lift(cfg,{v.name:m.getSolVal(sol,v) for v in m.getVars(transformed=False)},None,rebuild=True)
        improve(checked)
        b=m.getDualbound()
        assert b<=state["upper"]+cell.EPS
        state["lower"]=max(state["lower"],min(b,state["upper"]))
        m.freeProb()
    if not reached():raise RuntimeError(f"Missing validated 1% gap: {state}")
    persist()
    return best,dict(status="verified_gap",scope="global_product_Cmax",upper=state["upper"],lower=state["lower"],
                     seconds=state["seconds"],search_sha256=sha(path))

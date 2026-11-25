"""Ten-percent table 4. Only A, B and the A-to-B handoff are eligible."""
from dataclasses import replace
import gc
import math
from pathlib import Path
import sys
import time

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/"table4_residence100_20261123/portfolio"))
import window
import worker
import primal
from inputs import OUT as LEGACY, case_id, read, save, sha, Config, Integrated, certified_capacity, cell, store_primary, product
from ortools.sat.python import cp_model
from project import export

OUT=LEGACY.parent/"table4_three_arms_20261124"
worker.OUT=OUT


def repair(cfg,raw,cap):
    """Fix the projected binary structure and recover continuous times on the original model."""
    x=Integrated(cfg)
    m=x.model
    for var in m.getVars(transformed=False):
        if var.vtype()!="CONTINUOUS" and not var.name.startswith("sync_"):
            value=round(raw.get(var.name,0))
            m.chgVarLb(var,value)
            m.chgVarUb(var,value)
    m.setObjective(x.cmax,"minimize")
    m.addCons(x.cmax<=cap+1e-6)
    m.setIntParam("lp/threads",1)
    m.hideOutput()
    m.optimize()
    best=m.getBestSol()
    checked=None
    if best:
        vals={v.name:m.getSolVal(best,v) for v in m.getVars(transformed=False)}
        m.freeProb()
        checked=cell.lift(cfg,vals,None,rebuild=True)
    else:
        m.freeProb()
    return checked


def makespan(folder,src,spec,seed):
    cfg=Config(**spec["config"])
    data=read(src/"schedule.json")
    vals=cell.values(src/"assignment.json.gz")
    assert sha(src/"assignment.json.gz")==spec["assignment_sha256"]
    baseline=cell.certify_start(cfg,data,vals)
    statepath=folder/"search.json"
    state=read(statepath) if statepath.exists() else dict(input=spec["assignment_sha256"],
                lower=cell.lock_bound(cfg)["lower"],upper=baseline[2]["cmax"],attempt=0)
    assert state["input"]==spec["assignment_sha256"]
    state["attempt"]+=1
    save(statepath,state)
    began=time.monotonic()
    while state["upper"]>1.10*state["lower"]+1e-8:
        cap=math.floor(1.10*state["lower"])
        plan=certified_capacity(cfg,cap)
        x=Integrated(replace(cfg,max_pairs=plan["pairs"],max_cycles=plan["cycles"]))
        if plan["separated"] and all(set(g.chambers)==set(cfg.chambers) for g in x.groups):
            for q in range(x.Q):
                x.model.addCons(x.cy.kind[cfg.chambers[0],q,"2x2"]==0)
                x.model.addCons(x.cy.kind[cfg.chambers[1],q,"4x1"]==0)
        cell.strengthen(x,dict(plan,separated=False),data,cap)
        cp,vs,audit=export(x,vals)
        # The projected empty-boundary sentinel of the original, unreduced domain must
        # also mark the end of a used compact prefix when lifting a grid candidate.
        x.model.freeProb()
        del x
        gc.collect()
        cp.clear_objective()
        solver=cp_model.CpSolver()
        solver.parameters.random_seed=seed
        solver.parameters.num_search_workers=1
        solver.parameters.max_memory_in_mb=5600 if spec["n"]==16 else 2200
        solver.parameters.log_search_progress=True
        solver.parameters.log_to_stdout=False
        path=folder/f"cap_{cap}_attempt{state['attempt']}"
        path.mkdir(parents=True,exist_ok=True)
        save(path/"model.json",dict(cap=cap,plan=plan,export=audit))
        with (path/"solver.log").open("a",encoding="utf-8") as log:
            solver.log_callback=lambda line: (log.write(line+"\n"),log.flush())
            status=solver.solve(cp)
        if status==cp_model.INFEASIBLE:
            state["lower"]=cap
        elif status in (cp_model.OPTIMAL,cp_model.FEASIBLE):
            raw={k:solver.value(v) for k,v in vs.items() if solver.value(v)}
            save(path/"proposal.json.gz",cell.sparse(raw))
            candidate=cell.lift(cfg,dict(raw),plan["cycles"],rebuild=True)
            if candidate is None or candidate[2]["cmax"]>cap+cell.EPS:
                candidate=repair(cfg,raw,cap)
            if candidate is None:
                # The outer projection can return an infeasible discrete structure.
                # Fall back to the full makespan optimization and its independently verified bound.
                worker.primary(folder,src,spec,seed)
                return
            assert candidate[2]["cmax"]<=cap+cell.EPS
            state["upper"]=candidate[2]["cmax"]
            store_primary(folder/"incumbent",candidate,dict(cap=cap))
        else:
            raise RuntimeError(f"No CP conclusion, status {solver.status_name(status)}")
        save(statepath,state)
        del cp,solver,vs
        gc.collect()
    if (folder/"incumbent/primary.json").exists():
        stored=folder/"incumbent"
        baseline=cell.certify_start(cfg,read(stored/"schedule.json"),cell.values(stored/"assignment.json.gz"))
    r=dict(upper=baseline[2]["cmax"],lower=state["lower"],seconds=time.monotonic()-began,
           engine="outward makespan sublevel and continuous original-model replay",status="verified_gap")
    store_primary(folder,baseline,r)
    worker.endpoint(folder,folder,"A",spec,seed,r)


def process_control(folder,src,spec,seed):
    # A constructive zero-cost proposal proves global optimality if it fits the original limits.
    cfg=Config(**spec["config"])
    decoder=primal.Decoder(cfg)
    n=spec["n"]
    for shift in (0,1):
        for stride in (2,1,3,4):
            genes=tuple(v for i in range(n) for v in (1,(i//stride+shift)%2,1,0,0))
            batch=decoder.build(genes,decoder.pairing(genes))
            data=primal.product_lp(batch).solve("B",None,15)
            if not data: continue
            data=primal.snap(data)
            if (cfg.max_cycles and max(c["index"] for c in data["cycles"])>=cfg.max_cycles or
                cfg.max_pairs and max(p["id"] for p in data["pairs"])>=cfg.max_pairs): continue
            if not primal.validate(data)["valid"]: continue
            sol=cell.lift(cfg,primal.sparse_witness(cfg,data),None,rebuild=True)
            if sol and product.product_metrics(sol[0])["secondary"]==0:
                r=dict(upper=0.,lower=0.,status="optimal",engine="physical zero-cost schedule and nonnegativity")
                store_primary(folder,sol,r)
                worker.endpoint(folder,folder,"B",spec,seed,r)
                return
    worker.free_objective(folder,src,spec,seed,"B")


def run(n,h,s,arm):
    from queue_runs import TABLE4_CASES
    if (n,h) not in TABLE4_CASES:
        raise ValueError(f"Instance {(n,h)} is outside the Table 4 comparison")
    assert arm in ("A","B")
    key=case_id(n,h)
    group=OUT/"runs"/f"{key}__s{s}"
    folder=group/arm
    src=LEGACY/"inputs"/key
    spec=read(src/"input.json")
    assert (spec["n"],spec["H"])==(n,h)
    assert sha(src/"schedule.json")==spec["schedule_sha256"] and sha(src/"assignment.json.gz")==spec["assignment_sha256"]
    cfg=spec["config"]
    assert cfg["chamber_residency_basis"]=="nonprocessing" and cfg["module_residency"]==cfg["robot_residency"]==100
    folder.mkdir(parents=True,exist_ok=True)
    if not (folder/"endpoint.json").is_file():
        (makespan if arm=="A" else process_control)(folder,src,spec,s)
    if arm=="A" and not (group/"AB/endpoint.json").is_file():
        worker.secondary(group/"AB",folder,spec,s)


if __name__=="__main__":
    run(*map(int,sys.argv[1:4]),sys.argv[4])

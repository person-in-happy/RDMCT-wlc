"""One-percent paired cut-selection experiment. Resume from native witnesses and global bounds."""
from dataclasses import replace
import math
from pathlib import Path
import sys
import time

import solve
from table5_baselines import METHODS
from pyscipopt import Eventhdlr, SCIP_EVENTTYPE, SCIP_RESULT
from pyscipopt.scip import Cutsel

OUT=solve.JMS/"results/table5_one_percent_20261124"
GAP=.01
PROOF=solve.directory(1,"projection","0p01pct")


def directory(seed,arm,level="1pct"):
    return OUT/"runs"/f"s{seed}_{arm}"/level


def common_bound(cfg):
    src,rec,data=solve.source(1,"full")
    proof=solve.read(PROOF/"handoff.json")
    log=PROOF/"projection/solver.log"
    assert solve.Config(**data["config"])==cfg
    assert proof["start_sha256"]==rec["assignment_sha256"]
    assert proof["record"]["status"]=="OPTIMAL" and proof["record"]["lower"]==397
    assert "best_bound: 397\n" in log.read_text() and "status: OPTIMAL" in log.read_text()
    return 397.


def first(seed,arm,dest):
    src,rec,data=solve.source(seed,arm)
    cfg=solve.Config(**data["config"])
    policy=METHODS[arm]
    key=dict(input=rec["assignment_sha256"],method=policy,seed=seed,gap=GAP,
             proof=solve.sha(PROOF/"handoff.json"),proof_log=solve.sha(PROOF/"projection/solver.log"))
    state_path=dest/"resume.json"
    state=solve.read(state_path) if state_path.exists() else dict(key=key,lb=common_bound(cfg),
            ub=rec["metrics"]["cmax"],seconds=0.,calls=0,witness=None,attempt=0)
    if state["key"]!=key:
        raise ValueError("Checkpoint input or policy differs")
    # Preserve earlier logs and checkpoint witnesses. The selector and current tree restart.
    state["attempt"]+=1
    attempt=dest/f"attempt_{state['attempt']:04d}"
    attempt.mkdir(parents=True,exist_ok=True)
    solve.save(state_path,state)
    upper=math.ceil(rec["metrics"]["cmax"])
    plan=solve.cell.capacity(cfg,upper)
    x=solve.Integrated(replace(cfg,max_pairs=plan["pairs"],max_cycles=plan["cycles"]))
    m=x.model
    solve.cell.strengthen(x,plan,data,upper)
    m.addCons(x.cmax>=state["lb"]-1e-7)
    solve.cell.scip_settings(m,dict(n=4,seed=seed,seconds=None,gap=GAP),attempt)
    if policy!="default":
        sys.path.insert(0,str(solve.HERE.parent/"component_gap_restore_20261119"))
        from component import POLICIES,policy_on_cpu
        spec=POLICIES[policy]
        agent,weights=policy_on_cpu(m,spec[0],spec,seed,1)
        solve.save(attempt/"policy.json",weights)
    class Count(Cutsel):
        count=0
        def cutselselect(self,cuts,forcedcuts,root,maxnselectedcuts):
            self.count+=1
            return dict(result=SCIP_RESULT.DIDNOTFIND)
    count=Count()
    m.includeCutsel(count,"count_rounds","Count selection rounds then defer to the configured selector",2000000)
    native=m.getVars(transformed=False)
    m.setObjective(x.cmax,"minimize")
    previous=src/"assignment.json.gz"
    if state["witness"]:
        previous=dest/state["witness"]
        assert solve.sha(previous)==state["witness_sha256"]
    m.addSol(solve.cell.attach(x,solve.cell.values(previous)))
    base_calls,base_seconds=state["calls"],state["seconds"]
    began=time.perf_counter()
    last=began
    def snapshot(force=False):
        nonlocal last
        now=time.perf_counter()
        best=m.getBestSol()
        price=m.getSolObjVal(best) if best is not None else math.inf
        improved=price<state["ub"]-1e-7
        if not force and not improved and now-last<4:
            return
        if improved:
            name=f"incumbent_{time.time_ns()}.json.gz"
            solve.save(dest/name,solve.cell.sparse({v.name:m.getSolVal(best,v) for v in native}))
            state.update(ub=price,witness=name,witness_sha256=solve.sha(dest/name))
        lower=m.getDualbound()
        if state["lb"]<lower<=state["ub"]+1e-8:
            state["lb"]=min(lower,state["ub"])
        state.update(seconds=base_seconds+now-began,calls=base_calls+count.count)
        solve.save(state_path,state)
        last=now
    class Monitor(Eventhdlr):
        flags=SCIP_EVENTTYPE.BESTSOLFOUND|SCIP_EVENTTYPE.DUALBOUNDIMPROVED|SCIP_EVENTTYPE.NODESOLVED|SCIP_EVENTTYPE.LPSOLVED
        def eventinit(self): self.model.catchEvent(self.flags,self)
        def eventexit(self): self.model.dropEvent(self.flags,self)
        def eventexec(self,event): snapshot()
    m.includeEventhdlr(Monitor(),"save_progress","Preserve improving incumbents, bounds and counters")
    if state["ub"]>(1+GAP)*state["lb"]+1e-8:
        m.optimize()
        snapshot(True)
    if state["ub"]>(1+GAP)*state["lb"]+1e-8:
        raise ValueError(f"SCIP stopped at {m.getStatus()} before the requested gap")
    m.freeProb()
    candidate=solve.cell.values(dest/state["witness"]) if state["witness"] else solve.cell.values(src/"assignment.json.gz")
    checked=solve.cell.lift(cfg,candidate,x.Q,rebuild=True)
    assert checked and checked[3]["valid"] and abs(checked[2]["cmax"]-state["ub"])<solve.cell.EPS
    record=dict(upper=checked[2]["cmax"],lower=state["lb"],seconds=state["seconds"],
                calls=state["calls"],status="verified_gap",method=policy)
    solve.open_gate(seed,arm,"1pct",src,record,checked[1]["nonzero"],None)


def run(seed,arm):
    solve.directory=directory
    solve.LEVELS={"1pct":GAP}
    solve.B_GAP=GAP
    dest=directory(seed,arm)
    dest.mkdir(parents=True,exist_ok=True)
    if not (dest/"handoff.json").exists():
        first(seed,arm,dest)
    if not (dest/"timing.json").exists():
        started=time.perf_counter()
        solve.finish(seed,arm,"1pct")
        elapsed=time.perf_counter()-started
        r=solve.read(dest/"result.json")
        assert r["verified"] and r["secondary"]["gap"]<=GAP+1e-9
        assert solve.relative(r["gate"]["upper"],r["gate"]["lower"])<=GAP+1e-9
        solve.save(dest/"timing.json",dict(arm=arm,seed=seed,f_A=r["after"]["cmax"],
                   f_B_handoff=r["before"]["secondary"],f_B=r["after"]["secondary"],
                   total_s=r["prep_seconds"]+r["gate"]["seconds"]+elapsed,calls=r["gate"]["calls"],
                   result_sha256=solve.sha(dest/"result.json")))

if __name__=="__main__":
    run(int(sys.argv[1]),sys.argv[2])

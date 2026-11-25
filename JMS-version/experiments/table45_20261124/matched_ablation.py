"""Stop a comparator at its paired physical target or its paired full-method wall budget."""
from dataclasses import replace
import math
from pathlib import Path
import sys
import threading
import time

from matched_reference import one_percent as old
from pyscipopt import Eventhdlr, SCIP_EVENTTYPE, SCIP_RESULT
from pyscipopt.scip import Cutsel

solve=old.solve
OUT=solve.JMS/"results/table5_matched_target_20261124"
TOL=solve.cell.EPS


def reference(seed):
    base=old.OUT if seed in (1,2) else OUT/"references"
    return base/f"runs/s{seed}_full/1pct"


def load_reference(folder):
    timing=solve.read(folder/"timing.json")
    record=solve.read(folder/"result.json")
    assert timing["result_sha256"]==solve.sha(folder/"result.json") and record["verified"]
    final=folder/"B/runs/endpoint"
    b=solve.read(final/"result.json")
    assert b["job"]["gap"]==.01 and b["job"]["assignment_sha256"]==solve.sha(folder/"A/assignment.json.gz")
    assert b["eligible"] and b["replay"]["valid"] and b["record"]["gap"]<=.01+1e-9
    assert all(solve.sha(final/k)==v for k,v in b["files"].items())
    scores=solve.product.product_metrics(solve.read(final/"schedule.json"))
    assert abs(timing["f_A"]-scores["cmax"])<TOL and abs(timing["f_B"]-scores["secondary"])<TOL
    return timing


class Trial:
    def __init__(self,seed,arm,dest,refdir):
        self.seed,self.arm,self.dest=seed,arm,dest
        dest.mkdir(parents=True,exist_ok=True)
        self.ref=load_reference(refdir)
        assert self.ref["seed"]==seed and self.ref["arm"]=="full"
        self.limit=self.ref["total_s"]
        self.src,self.initial,self.data=solve.source(seed,arm)
        self.cfg=solve.Config(**self.data["config"])
        frozen=solve.read(old.OUT/"protocol.json")
        start_arm="no_spbs" if arm=="no_spbs" else "full"
        assert self.initial["assignment_sha256"]==frozen["inputs"][f"{seed}/{start_arm}"]
        assert self.cfg.module_residency==self.cfg.robot_residency==100
        assert self.cfg.chamber_residency_basis=="nonprocessing" and self.cfg.cleaning_interval==10
        self.checkpoints=frozen["checkpoints"]
        self.base=old.common_bound(self.cfg)
        self.clock=None
        self.offset=self.initial["record"]["seconds"]
        self.key=dict(seed=seed,arm=arm,reference=solve.sha(refdir/"timing.json"),
                      start=self.initial["assignment_sha256"],tolerance=TOL)
        file=dest/"progress.json"
        if file.exists():
            self.s=solve.read(file)
            if self.s["key"]!=self.key: raise ValueError("Mismatched checkpoint")
            self.offset=self.s["charged_s"]
            heartbeat=dest/"clock.json"
            if heartbeat.exists():
                pulse=solve.read(heartbeat)
                if pulse["attempt"]==self.s["attempt"]:
                    self.offset=max(self.offset,pulse["charged_s"])
        else:
            score=solve.product.product_metrics(self.data)
            self.s=dict(key=self.key,stage="A",calls=0,lower=self.base,attempt=0,
                        charged_s=self.offset,handoff=None,hit=False,
                        best=dict(a=score["cmax"],b=score["secondary"],at=self.offset,
                                  path=str((self.src/"assignment.json.gz").resolve()),cycles=None,
                                  digest=self.initial["assignment_sha256"]))
        self.s["attempt"]+=1
        self.last=0.
        self.persist()

    def elapsed(self):
        return self.offset+(time.perf_counter()-self.clock if self.clock is not None else 0.)

    def start(self):
        self.clock=time.perf_counter()

    def freeze(self):
        self.offset=min(self.limit,self.elapsed())
        self.clock=None
        self.persist()

    def persist(self):
        self.s["charged_s"]=min(self.elapsed(),self.limit)
        solve.save(self.dest/"progress.json",self.s)
        self.last=time.perf_counter()

    def meets(self,a,b):
        return a<=self.ref["f_A"]+TOL and b<=self.ref["f_B"]+TOL

    def witness(self,x,sol,at,scores):
        vals={v.name:x.model.getSolVal(sol,v) for v in x.model.getVars(transformed=False)}
        file=self.dest/f"witness_{time.time_ns()}.json.gz"
        solve.save(file,solve.cell.sparse(vals))
        return dict(a=scores["cmax"],b=scores["secondary"],at=at,path=str(file),
                    cycles=x.Q,digest=solve.sha(file),from_stage=self.s["stage"])

    def replay(self,w):
        p=Path(w["path"])
        assert solve.sha(p)==w["digest"]
        chk=solve.cell.lift(self.cfg,solve.cell.values(p),w["cycles"],rebuild=True)
        if not chk or not chk[3]["valid"]: raise ValueError("Candidate failed original-row validation")
        f=solve.product.product_metrics(chk[0])
        assert abs(f["cmax"]-w["a"])<=TOL and abs(f["secondary"]-w["b"])<=TOL
        return chk

    def observe(self,x,sol,at):
        if at>self.limit or self.s["hit"]: return
        f=solve.product.product_metrics(x.result(solution=sol))
        a,b=f["cmax"],f["secondary"]
        best=self.s["best"]
        hit=self.meets(a,b)
        better=(a<best["a"]-TOL or (abs(a-best["a"])<=TOL and b<best["b"]-TOL))
        if hit or better:
            self.s["best"]=self.witness(x,sol,at,f)
            self.s["hit"]=hit
            self.persist()

    def optimize(self,x,stage):
        m=x.model
        trial=self
        errors=[]
        class Monitor(Eventhdlr):
            seen=-1
            flags=(SCIP_EVENTTYPE.SOLFOUND|SCIP_EVENTTYPE.NODESOLVED|
                   SCIP_EVENTTYPE.LPSOLVED|SCIP_EVENTTYPE.DUALBOUNDIMPROVED)
            def eventinit(self): self.model.catchEvent(self.flags,self)
            def eventexit(self): self.model.dropEvent(self.flags,self)
            def eventexec(self,event):
                try:
                    self.inspect(event)
                except Exception as exc:
                    errors.append(exc)
                    self.model.interruptSolve()
            def inspect(self,event):
                at=trial.elapsed()
                if at>trial.limit or trial.s["hit"]:
                    self.model.interruptSolve()
                    return
                number=self.model.getNSolsFound()
                if number!=self.seen or event.getType() & SCIP_EVENTTYPE.SOLFOUND:
                    self.seen=number
                    # Check actual feasible pairs, including tied primary objectives.
                    for sol in self.model.getSols():
                        trial.observe(x,sol,at)
                        if trial.s["hit"]:
                            self.model.interruptSolve()
                            return
                if stage=="A":
                    lb=m.getDualbound()
                    if trial.s["lower"]<lb<=trial.s["best"]["a"]+TOL:
                        trial.s["lower"]=min(lb,trial.s["best"]["a"])
                if time.perf_counter()-trial.last>3: trial.persist()
        m.includeEventhdlr(Monitor(),"paired_monitor","paired physical objectives and deadline",)
        remaining=self.limit-self.elapsed()
        if remaining<=0:return
        done=threading.Event()
        def watch():
            while not done.wait(max(0.,min(3.,self.limit-self.elapsed()))):
                elapsed=self.elapsed()
                solve.save(self.dest/"clock.json",dict(attempt=self.s["attempt"],charged_s=min(elapsed,self.limit)))
                if elapsed>=self.limit:
                    m.interruptSolve()
                    return
        timer=threading.Thread(target=watch,daemon=True)
        m.setRealParam("limits/time",max(.001,remaining+1.))
        timer.start()
        try:
            m.optimizeNogil()
            # The native gap is still the phase-B benchmark. If it fires before
            # the paired target, allow the same tree to keep improving the schedule.
            if stage=="B" and not errors and not self.s["hit"] and self.elapsed()<self.limit and str(m.getStatus())=="gaplimit":
                m.setRealParam("limits/gap",0.)
                m.optimizeNogil()
        finally:
            done.set()
            timer.join()
        if errors:raise errors[0]
        at=self.elapsed()
        if at<=self.limit and not self.s["hit"]:
            for sol in m.getSols():
                self.observe(x,sol,at)
                if self.s["hit"]:break

    def phase_a(self):
        plan=solve.cell.capacity(self.cfg,math.ceil(self.initial["metrics"]["cmax"]))
        x=solve.Integrated(replace(self.cfg,max_pairs=plan["pairs"],max_cycles=plan["cycles"]))
        m=x.model
        solve.cell.strengthen(x,plan,self.data,math.ceil(self.initial["metrics"]["cmax"]))
        m.addCons(x.cmax>=self.s["lower"]-1e-7)
        logs=self.dest/f"A_attempt{self.s['attempt']}"
        logs.mkdir(exist_ok=True)
        solve.cell.scip_settings(m,dict(n=4,seed=self.seed,seconds=None,gap=.01),logs)
        policy=old.METHODS[self.arm]
        if policy!="default":
            sys.path.insert(0,str(solve.HERE.parent/"component_gap_restore_20261119"))
            from component import POLICIES,policy_on_cpu
            spec=POLICIES[policy]
            _,weights=policy_on_cpu(m,spec[0],spec,self.seed,1)
            assert weights["sha256"]==self.checkpoints["hem" if self.arm=="hem" else "full"]
            solve.save(logs/"policy.json",weights)
        trial=self
        class Count(Cutsel):
            def cutselselect(self,cuts,forcedcuts,root,maxnselectedcuts):
                if trial.elapsed()<=trial.limit and not trial.s["hit"]:trial.s["calls"]+=1
                return dict(result=SCIP_RESULT.DIDNOTFIND)
        m.includeCutsel(Count(),"count_rounds","count selection then defer",2000000)
        m.setObjective(x.cmax,"minimize")
        m.addSol(solve.cell.attach(x,solve.cell.values(Path(self.s["best"]["path"]))))
        self.start()
        self.optimize(x,"A")
        at=self.elapsed()
        status=str(m.getStatus())
        # Physical recovery of the stage-A endpoint is outside the original A search clock.
        self.freeze()
        if not self.s["hit"] and at<self.limit and status in ("optimal","gaplimit"):
            sol=m.getBestSol()
            f=solve.product.product_metrics(x.result(solution=sol))
            self.s["handoff"]=self.witness(x,sol,at,f)
            self.s["stage"]="B"
        elif not self.s["hit"] and status not in ("timelimit","userinterrupt","optimal","gaplimit"):
            raise RuntimeError(f"First stage ended unexpectedly: {status}")
        m.freeProb()
        self.persist()

    def phase_b(self):
        self.start()
        chk=self.replay(self.s["handoff"])
        vals=chk[1]["nonzero"]
        f=solve.product.product_metrics(chk[0])
        x=solve.Integrated(self.cfg)
        m=x.model
        logs=self.dest/f"B_attempt{self.s['attempt']}"
        logs.mkdir(exist_ok=True)
        solve.cell.scip_settings(m,dict(n=4,seed=self.seed,seconds=None,gap=.01),logs)
        m.setRealParam("numerics/feastol",1e-8)
        for v in m.getVars(transformed=False):
            if v.vtype()!="CONTINUOUS" and not v.name.startswith("sync_"):
                bit=round(vals.get(v.name,0.));m.chgVarLb(v,bit);m.chgVarUb(v,bit)
        m.addCons(x.cmax<=f["cmax"]+1e-6)
        objective,maximum,extra=solve.product.objective_terms(x,vals,True,25)
        m.setObjective(objective,"minimize")
        m.addSol(solve.cell.attach(x,vals|extra|{maximum.name:f["wait_max"]}))
        best=self.s["best"]
        if best.get("from_stage")=="B":
            resumed=self.replay(best)
            bvals=resumed[1]["nonzero"]
            bmetrics=solve.product.product_metrics(resumed[0])
            m.addSol(solve.cell.attach(x,bvals|{maximum.name:bmetrics["wait_max"]}))
        self.optimize(x,"B")
        status=str(m.getStatus())
        self.freeze()
        m.freeProb()
        if not self.s["hit"] and status not in ("optimal","timelimit","userinterrupt","unknown"):
            raise RuntimeError(f"Second stage ended unexpectedly: {status}")
        self.s["exhausted"]=status=="optimal" and not self.s["hit"]
        if self.s["exhausted"]:self.s["search_end_s"]=self.s["charged_s"]
        self.persist()

    def wait_for_observation(self):
        # A proven optimum on a fixed schedule structure cannot change after
        # the solver returns. Release the solver and publish at the actual cap.
        self.start()
        while self.elapsed()<self.limit:
            time.sleep(min(3.,max(0.,self.limit-self.elapsed())))
            self.persist()
        self.freeze()

    def run(self):
        if self.meets(self.s["best"]["a"],self.s["best"]["b"]):self.s["hit"]=True
        if not self.s["hit"] and self.s["stage"]=="A" and self.elapsed()<self.limit:self.phase_a()
        if not self.s["hit"] and self.s["stage"]=="B" and self.elapsed()<self.limit and not self.s.get("exhausted"):self.phase_b()
        if not self.s["hit"] and self.elapsed()<self.limit:
            if not self.s.get("exhausted"):raise RuntimeError("Paired run returned before either stopping condition")
            self.wait_for_observation()
        w=self.s["best"]
        checked=self.replay(w)
        f=solve.product.product_metrics(checked[0])
        assert w["at"]<=self.limit and self.meets(f["cmax"],f["secondary"])==self.s["hit"]
        elapsed=w["at"] if self.s["hit"] else self.limit
        reason="target" if self.s["hit"] else "time_budget"
        solve.store_primary(self.dest/"endpoint",checked,dict(reason=reason))
        result=dict(seed=self.seed,arm=self.arm,f_A=f["cmax"],f_B=f["secondary"],
                    f_B_handoff=self.s["handoff"]["b"] if self.s["handoff"] else None,
                    stage=self.s["stage"],calls=self.s["calls"],reason=reason,observed_s=elapsed,
                    used_s=self.s.get("search_end_s",self.s["charged_s"]),witness_s=w["at"],reference_s=self.limit,
                    reference_f_A=self.ref["f_A"],reference_f_B=self.ref["f_B"],
                    exhausted=self.s.get("exhausted",False),key=self.key,
                    schedule_sha256=solve.sha(self.dest/"endpoint/schedule.json"),
                    assignment_sha256=solve.sha(self.dest/"endpoint/assignment.json.gz"))
        solve.save(self.dest/"result.json",result)


if __name__=="__main__":
    seed=int(sys.argv[1]);arm=sys.argv[2]
    if arm=="full" or arm not in old.METHODS: raise ValueError(arm)
    trial=Trial(seed,arm,OUT/"runs"/f"s{seed}_{arm}",reference(seed))
    if not (trial.dest/"result.json").exists():trial.run()

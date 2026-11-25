"""Recover a fixed-structure SCIP trial at its incumbent and remaining solver budget."""
import json
import math
import os
from pathlib import Path
import shutil
import sys
import threading
import time

from supplement import HERE, ROOT, checked, digest, load, save

PULSE = .25


class Checkpoint:
    def __init__(self, dest, job):
        self.dest = dest
        self.job = job
        self.settings = job["settings"]
        self.file = dest / "checkpoint.json"
        self.key = dict(settings=self.settings, solver=digest(HERE / "solver.py"),
                        objective=digest(HERE / "score.py"))
        self.state = load(self.file) if self.file.exists() else dict(
            key=self.key, attempt=0, charged_s=0., wall_s=0., incumbent=None, lower=None)
        if self.state["key"] != self.key:
            raise ValueError("Saved solver state belongs to another model or experiment")
        self.base = self.state["charged_s"]
        self.prior_wall = self.state["wall_s"]
        self.clock = time.monotonic()
        self.solve_clock = None
        self.limit = self.settings["seconds"]
        self.remaining = None if self.limit is None else max(0., self.limit - self.base)
        self.mutex = threading.RLock()
        self.stop = threading.Event()
        self.state.update(attempt=self.state["attempt"]+1, pid=os.getpid(), phase="preparation",
                          attempt_budget_s=self.remaining,attempt_prior_charged_s=self.base,
                          resumed_incumbent_checked=False,resumed_incumbent_submitted=False)
        self.pulse()

    def pulse(self):
        with self.mutex:
            now = time.monotonic()
            if self.solve_clock is not None:
                # Pre-charge the upcoming heartbeat to avoid re-spending a killed slice.
                accrued = self.base + max(0., now-self.solve_clock) + PULSE
                self.state["charged_s"] = min(self.limit,accrued) if self.limit is not None else accrued
            self.state["wall_s"] = self.prior_wall + now - self.clock
            save(self.file,self.state)

    def watch(self):
        while not self.stop.wait(PULSE):
            self.pulse()

    def begin(self, native_seconds):
        with self.mutex:
            self.state["phase"] = "solving"
            self.solve_clock = time.monotonic()-native_seconds
            self.pulse()

    def end(self, native_seconds):
        with self.mutex:
            if self.solve_clock is None:
                return
            self.solve_clock = None
            total=self.base+native_seconds
            self.state.update(phase="verification",charged_s=min(self.limit,total) if self.limit is not None else total)
            self.pulse()

    def finish(self, native_seconds):
        with self.mutex:
            self.solve_clock=None
            total=self.base+native_seconds
            self.state.update(phase="verification",charged_s=min(self.limit,total) if self.limit is not None else total)
            self.pulse()

    def capture(self, model):
        sol = model.getBestSol()
        if sol is None:
            return
        cost = model.getSolObjVal(sol)
        old = self.state["incumbent"]
        if old and cost >= old["objective"]-1e-8:
            return
        values = {v.name:model.getSolVal(sol,v) for v in model.getVars(transformed=False)}
        import solver
        source = self.dest / ("incumbent_%d_%d.json.gz" % (self.state["attempt"], time.time_ns()))
        solver.save(source,solver.cell.sparse(values))
        with self.mutex:
            self.state["incumbent"] = dict(file=source.name,sha256=digest(source),objective=cost)
            self.pulse()

    def native_state(self):
        entry = self.state["incumbent"]
        if entry:
            path = self.dest / entry["file"]
            if digest(path) != entry["sha256"]:
                raise ValueError("The saved incumbent changed")
            import solver
            return solver.cell.values(path)
        return None


def install(checkpoint):
    import solver
    from model import scip
    events = scip.SCIP_EVENTTYPE.BESTSOLFOUND | scip.SCIP_EVENTTYPE.DUALBOUNDIMPROVED

    class Catch(scip.Eventhdlr):
        def eventinit(self):
            self.model.catchEvent(events,self)
            checkpoint.begin(self.model.getSolvingTime())

        def eventexec(self,event):
            if event.getType() == scip.SCIP_EVENTTYPE.BESTSOLFOUND:
                checkpoint.capture(self.model)
            else:
                bound=self.model.getDualbound()
                if math.isfinite(bound) and abs(bound)<1e15:
                    with checkpoint.mutex:
                        previous=checkpoint.state.get("lower")
                        checkpoint.state["lower"] = max(previous,bound) if previous is not None else bound

        def eventexit(self):
            self.model.dropEvent(events,self)
            checkpoint.end(self.model.getSolvingTime())

    settings, attach = solver.cell.scip_settings, solver.cell.attach
    previous = checkpoint.native_state()
    def configure(model,task,folder):
        settings(model,task,folder)
        model.includeEventhdlr(Catch(),"residence_supplement_resume","durable SCIP incumbent and solver clock")
    def with_resume(x,values):
        original=attach(x,values)
        if previous is not None and "residence_spread" in values:
            warm = attach(x,previous)
            checkpoint.state["resumed_incumbent_checked"]=True
            if x.model.getSolObjVal(warm)<x.model.getSolObjVal(original)-1.e-8:
                checkpoint.state["resumed_incumbent_submitted"]=x.model.addSol(warm)
            else:
                x.model.freeSol(warm)
            checkpoint.pulse()
        return original
    solver.cell.scip_settings = configure
    solver.cell.attach = with_resume


def exhausted(cp):
    """Publish the best checked feasible incumbent when a killed search spent its limit."""
    import solver
    from score import metrics,physical_lower
    j,a = cp.job,cp.settings
    sys.path.insert(0,str(solver.cell.BACKENDS[a["backend"]]))
    from model import Config
    source=ROOT/j["source"]
    original=solver.read(source/j["schedule"])
    val=solver.cell.values(source/j["assignment"])
    cfg=Config(**original["config"])
    candidates=[val]
    prev=cp.native_state()
    if prev: candidates.append(prev)
    checked_values=[]
    for candidate in candidates:
        verified=solver.cell.lift(cfg,candidate,None,rebuild=True)
        if not verified or not verified[3]["valid"]:continue
        s=metrics(verified[0],a["range_weight"],a["clean_weight"])
        if s["cmax"]<=metrics(original)["cmax"]+solver.cell.EPS:
            checked_values.append((s,verified))
    s,v=min(checked_values,key=lambda row:row[0]["secondary"])
    bound=physical_lower(cfg,a["range_weight"])
    if cp.state["lower"] is not None:bound=max(bound,cp.state["lower"])
    if bound>s["secondary"]+solver.cell.EPS:raise ValueError("Invalid checkpoint lower bound")
    gap=solver._ratio(s["secondary"],min(s["secondary"],bound))
    p=cp.dest/f"attempt_{cp.state['attempt']:03d}"
    solver.save(p/"schedule.json",v[0])
    solver.save(p/"assignment.json.gz",v[1])
    solver.save(p/"result.json",dict(mode="fixed",backend=a["backend"],scope="primary structure with makespan cap",
        initial=metrics(original,a["range_weight"],a["clean_weight"]),measured=s,seed=a["seed"],target_gap=a["gap"],
        eligible=gap is not None and gap<=a["gap"]+1e-8,weights=dict(range=a["range_weight"],clean=a["clean_weight"]),
        parents=[dict(schedule_sha256=a["schedule"],assignment_sha256=a["assignment"])],replay=v[3],
        original_rows=v[4],replayed_rows=v[4],record=dict(status="cumulative_budget",upper=s["secondary"],lower=bound,
        gap=gap,seconds=0.,wall_seconds=0.,nodes=None),files={
            name:digest(p/name) for name in ("schedule.json","assignment.json.gz")}))


def publish(dest, attempt, job, state):
    import solver
    if not checked(attempt,job):
        raise ValueError("Incomplete attempt cannot be published")
    result=load(attempt/"result.json")
    rec=result["record"]
    limit=job["settings"]["seconds"]
    total=state["attempt_prior_charged_s"]+rec["seconds"]
    rec.update(cumulative_solver_s=min(total,limit) if limit is not None else total,
               cumulative_wall_s=state["wall_s"],attempt=state["attempt"],
               granted_solver_s=state["attempt_budget_s"])
    lower=state.get("lower")
    if lower is not None and lower>rec["lower"]:
        if lower>rec["upper"]+solver.cell.EPS:raise ValueError("Recovered bound exceeds incumbent")
        rec["lower"]=min(lower,rec["upper"])
        rec["gap"]=solver._ratio(rec["upper"],rec["lower"])
        result["eligible"]=rec["gap"] is not None and rec["gap"]<=job["settings"]["gap"]+1e-8
    for name in result["files"]:
        temp=dest/(name+".publishing")
        shutil.copyfile(attempt/name,temp)
        os.replace(temp,dest/name)
    save(dest/"result.json",result)


def worker(out,key):
    import msvcrt
    manifest=load(out/"manifest.json")
    job=next(j for j in manifest.values() if j["key"]==key)
    dest=out/key
    with (dest/"worker.lock").open("a+b") as lock:
        lock.seek(0)
        try:msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
        except OSError:return
        if checked(dest,job):return
        if (dest/"checkpoint.json").exists():
            old=load(dest/"checkpoint.json")
            previous=dest/f"attempt_{old['attempt']:03d}"
            if checked(previous,job):
                publish(dest,previous,job,old)
                old.update(phase="complete")
                save(dest/"checkpoint.json",old)
                return
        cp=Checkpoint(dest,job)
        attempt=dest/f"attempt_{cp.state['attempt']:03d}"
        attempt.mkdir(exist_ok=True)
        listener=threading.Thread(target=cp.watch,daemon=True)
        listener.start()
        try:
            import solver
            a=job["settings"]
            if cp.remaining is not None and cp.remaining<=1e-8:
                exhausted(cp)
            else:
                sys.path.insert(0,str(solver.cell.BACKENDS[a["backend"]]))
                install(cp)
                result=solver.run("fixed",ROOT/job["source"],attempt,seed=a["seed"],seconds=cp.remaining,gap=a["gap"],
                    backend=a["backend"],schedule=job["schedule"],assignment=job["assignment"],
                    range_weight=a["range_weight"],clean_weight=a["clean_weight"])
                cp.finish(result["record"]["seconds"])
            publish(dest,attempt,job,cp.state)
            assert checked(dest,job)
            cp.state["phase"]="complete"
        finally:
            cp.stop.set()
            listener.join()
            cp.pulse()

if __name__=="__main__":
    worker(Path(sys.argv[1]).resolve(),sys.argv[2])

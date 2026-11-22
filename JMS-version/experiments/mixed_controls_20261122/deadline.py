"""Recover time overruns on the same model with an enforced external deadline."""
from pathlib import Path
import subprocess
import sys
import time

from controls import HERE,OUT,ROOT,SCIP,cell,execute,matched,product,product_solve,read,save,sha,store_primary

def child(case,seed,arm,folder):
    spec=matched.CASES[case]
    sys.path.insert(0,str(cell.BACKENDS[spec["backend"]]))
    import model
    from scip_imports import scip
    src,assignment=ROOT/spec["source"],ROOT/spec["assignment"]
    start=product.product_metrics(read(src))
    seconds=270 if arm=="AB" else 300
    best=[start["cmax"] if arm in ("A","AB") else (start["secondary"] if arm=="B" else 1.1)]
    class Capture(scip.Eventhdlr):
        def eventinit(self):self.model.catchEvent(scip.SCIP_EVENTTYPE.BESTSOLFOUND,self)
        def eventexit(self):self.model.dropEvent(scip.SCIP_EVENTTYPE.BESTSOLFOUND,self)
        def eventexec(self,event):
            t=time.monotonic()-self.clock
            if t>seconds:return
            sol=self.model.getBestSol()
            if sol is None:return
            score=self.model.getSolObjVal(sol)
            if score>=best[0]-1e-8:return
            vals={v.name:x for v in self.model.getVars(transformed=False) if (x:=self.model.getSolVal(sol,v))}
            save(folder/"improved.json.gz",dict(seconds=t,score=score,values=vals))
            best[0]=score
    class ObservedModel(scip.Model):
        def optimize(self,*args,**kw):
            cap=Capture()
            self.includeEventhdlr(cap,"deadline_capture","Archive strict incumbent improvements before cutoff")
            cap.clock=time.monotonic()
            save(folder/"start.json",dict(clock=cap.clock,budget=seconds))
            return super().optimize(*args,**kw)
    scip.Model=ObservedModel
    if arm in ("A","AB"):
        cfg=model.Config(**spec["config"]);data=read(src);vals=cell.values(assignment)
        checked=cell.certify_start(cfg,data,vals)
        result,rec=matched.objective_stage(cfg,checked[2],vals,"AB",seconds,dict(n=spec["n"],seed=seed),folder)
        store_primary(folder/"completed",result,rec)
    else:
        product_solve(folder/"ordinary",src,assignment,spec["backend"],spec["n"],seed,"joint" if arm=="J" else "B",seconds)

def retry(case,seed,arm,folder):
    spec=matched.CASES[case];src=ROOT/spec["source"];v=ROOT/spec["assignment"]
    assert (sha(src),sha(v))==(spec["source_sha256"],spec["assignment_sha256"])
    budget=270 if arm=="AB" else 300
    monitor=folder/"clock";monitor.mkdir(parents=True,exist_ok=True)
    if (monitor/"start.json").exists():raise ValueError("A new deadline attempt requires a fresh directory")
    with (monitor/"worker.log").open("w",encoding="utf8") as stream:
        proc=subprocess.Popen([SCIP,"-B","-X","utf8",__file__,"child",case,str(seed),arm,str(monitor)],stdout=stream,stderr=subprocess.STDOUT)
        while proc.poll() is None and not (monitor/"start.json").exists():time.sleep(.03)
        if not (monitor/"start.json").exists():raise RuntimeError("Search did not start")
        tick=read(monitor/"start.json")["clock"]
        stopped_at_deadline=False
        try:proc.wait(timeout=max(0,tick+budget-time.monotonic()))
        except subprocess.TimeoutExpired:
            stopped_at_deadline=True
            proc.terminate();proc.wait()
        elapsed=time.monotonic()-tick
    log=monitor/"improved.json.gz"
    sys.path.insert(0,str(cell.BACKENDS[spec["backend"]]))
    import model
    cfg=model.Config(**spec["config"]);warm=product.product_metrics(read(src))
    initial_score=warm["cmax"] if arm in ("A","AB") else (warm["secondary"] if arm=="B" else 1.1)
    accepted=read(log) if log.exists() else dict(values=cell.values(v),score=initial_score,seconds=0)
    assert accepted["seconds"]<=budget
    checked=cell.lift(cfg,accepted["values"],None,rebuild=True)
    assert checked and checked[3]["valid"]
    metrics=product.product_metrics(checked[0])
    val=(metrics["cmax"] if arm in ("A","AB") else metrics["secondary"] if arm=="B" else
         metrics["cmax"]/warm["cmax"]+.1*metrics["secondary"]/warm["secondary"])
    assert abs(val-accepted["score"])<=cell.EPS
    if not stopped_at_deadline:
        if proc.returncode!=0:raise RuntimeError(f"Unexpected worker exit {proc.returncode}")
        native=(monitor/"completed/primary.json" if arm in ("A","AB") else monitor/"ordinary/runs/endpoint/result.json")
        terminal=read(native)["record"]
        assert terminal["status"] in ("optimal","gaplimit","timelimit")
        assert abs(terminal["upper"]-val)<cell.EPS
    rec=dict(status="deadline",seconds=min(elapsed,budget),upper=val,lower=None,nodes=None,
             observed_elapsed=elapsed,incumbent_seconds=accepted["seconds"],stopped_at_deadline=stopped_at_deadline)
    stages=[(rec,budget)]
    if arm in ("A","AB"):
        primary=folder/"primary";store_primary(primary,checked,rec)
        if arm=="AB":
            e=product_solve(folder/"secondary",primary/"schedule.json",primary/"assignment.json.gz",
                            spec["backend"],spec["n"],seed,"fixed",30)
            assert e["eligible"];metrics=e["measured"];stages.append((e["record"],30))
    else:
        end=folder/"secondary/runs/endpoint";s=end/"schedule.json";vs=end/"assignment.json.gz"
        save(s,checked[0]);save(vs,checked[1])
        save(end/"result.json",dict(job=dict(kind="joint" if arm=="J" else "B",schedule=spec["source"],
            assignment=spec["assignment"],schedule_sha256=sha(src),assignment_sha256=sha(v),seed=seed,rho=.1 if arm=="J" else None),
            files={s.name:sha(s),vs.name:sha(vs)},replay=checked[3],record=rec,initial=warm,measured=metrics,eligible=True))
    save(folder/"result.json",dict(case=case,seed=seed,arm=arm,start=sha(v),stages=stages,metrics=metrics,eligible=True))

if __name__=="__main__":
    if len(sys.argv)>1:
        mode,case,seed,arm,path=sys.argv[1:]
        (child if mode=="child" else retry)(case,int(seed),arm,Path(path))
    else:
        base=OUT/"objectives"
        while not (base/"progress.json").exists() or read(base/"progress.json")["remaining"]:time.sleep(6)
        jobs=[]
        for f in sorted(base.glob("*/result.json")):
            d=read(f)
            if d["eligible"]:continue
            if any(r["status"] in ("memlimit","unknown","userinterrupt") for r,b in d["stages"]):continue
            path=str(OUT/"retries/objectives/01"/f.parent.name)
            jobs.append((SCIP,__file__,["retry",d["case"],str(d["seed"]),d["arm"],path],path))
        sys.exit(execute(jobs,3,OUT/"deadline_controls"))

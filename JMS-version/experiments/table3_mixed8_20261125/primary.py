"""One event stream for all three primary gap gates, with a predeclared external physical bound."""
from dataclasses import replace
import gc
import hashlib
import json
import math
import msvcrt
import os
from pathlib import Path
import sys
import threading
import time

HERE=Path(__file__).resolve().parent
JMS=HERE.parents[1]
OUT=JMS/"results/table3_mixed8_20261125"
sys.path.insert(0,str(HERE.parent/"table4_one_percent_20261124"))
from bench import Config, cell, old, read, reload, sha, store
from ortools.sat.python import cp_model

GATES={"10pct":.10,"1pct":.01,"0p01pct":.0001}
HINT=JMS/"results/table4_residence100_20261123/runs/D_n8_H10_mixed_dual__s1/A"
BOUND=JMS/"results/residence_objective_20261125/primary_relaxation_tight/result.json"
SOURCED=JMS/"results/huber_residence_20261125/primary_A_certificates.csv"

def save(path,obj):
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_name(f"{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    tmp.write_text(json.dumps(obj,indent=2),encoding="utf8")
    for k in range(30):
        try:
            tmp.replace(path)
            return
        except PermissionError:
            if k==29:raise
            time.sleep(.02)

def main():
    src=OUT/"prepared"
    cfg=Config(**read(src/"schedule.json")["config"])
    lower=read(BOUND)["lower"]
    assert lower==553 and sha(BOUND) in SOURCED.read_text(encoding="utf8") and read(BOUND)["status"]=="INFEASIBLE"
    key=dict(script=sha(Path(__file__)),seed=1,start=sha(src/"primary.json"),hint=sha(HINT/"primary.json"),
             bound=sha(BOUND),cfg=sha(JMS/"results/table4_one_percent_20261124/inputs/D_n8_H10_mixed_dual/input.json"),
             physical=sha(cell.BACKENDS["D"]/"model.py"),gates=GATES)
    path=OUT/"primary_search.json"
    state=read(path) if path.exists() else dict(identity=key,events=[],gates={},elapsed_s=0,attempt=0)
    if state["identity"]!=key:raise ValueError("New input requires a separate experiment directory")
    clock=time.monotonic()
    old_time=state["elapsed_s"]
    mutex=threading.RLock()
    stop=threading.Event()
    def publish():
        with mutex:
            state["elapsed_s"]=old_time+time.monotonic()-clock
            save(path,state)
    def progress():
        while not stop.wait(4):
            with mutex:
                publish()
                elapsed=state["elapsed_s"]
                # Baseline from the archived single-worker eight-wafer CP trajectory.
                expected=max(150.,elapsed+25.)
                est=dict(expected=3,completed=len(state["gates"]),failed=0,elapsed_s=elapsed,
                         estimated_remaining_s=expected-elapsed,estimated_total_s=expected,active="primary CP",
                         proof_lower=lower,pid=os.getpid(),basis="Comparable H10 trace reached 553 after 136 solver seconds; 150 s initial estimate including validation. Beyond that, ETA is uncertain and re-evaluated every 25 s.")
                save(OUT/"primary_progress.json",est)
                print(f"Primary gates {len(state['gates'])}/3; failed 0; wall {elapsed:.0f}s, "+
                      (f"estimated total {expected:.0f}s, remaining {expected-elapsed:.0f}s" if elapsed<150 else "historical estimate exceeded; completion time unknown, updating in 25s"),flush=True)
    for ev in state["events"]:
        f=OUT/ev["path"]
        if sha(f/"primary.json")!=ev["record_sha256"]:raise ValueError("Checkpoint changed")
    if len(state["gates"])==3:return
    state["attempt"]+=1
    publish()
    thread=threading.Thread(target=progress,daemon=True)
    thread.start()
    def accept(checked,kind):
        if not checked or not checked[3]["valid"]:return False
        upper=checked[2]["cmax"]
        if upper < lower-cell.EPS:raise ValueError("Failing physical lower bound")
        with mutex:
            if state["events"] and upper>=state["events"][-1]["upper"]-cell.EPS:return False
            folder=OUT/"physical_events"/f"e{len(state['events']):03}"
            relgap=(upper-lower)/lower
            rec=dict(seed=1,kind=kind,upper=upper,lower=lower,gap=relgap,gate=True,scope="global_product_Cmax",
                     attempt=state["attempt"],elapsed_s=old_time+time.monotonic()-clock,physical_lower_sha256=sha(BOUND))
            store(folder,checked,rec)
            event=dict(path=folder.relative_to(OUT).as_posix(),record_sha256=sha(folder/"primary.json"),upper=upper,
                       lower=lower,gap=relgap,kind=kind)
            state["events"].append(event)
            for name,threshold in GATES.items():
                if name not in state["gates"] and relgap<=threshold+1e-10:
                    state["gates"][name]=event
            publish()
        return True
    try:
        if not state["events"]:accept(reload(src,cfg),"common SPBS initial schedule")
        if len(state["events"])==1:accept(reload(HINT,cfg),"shared same-seed archival primary incumbent, verified at startup")
        if len(state["gates"])<3:
            best_dir=OUT/state["events"][-1]["path"]
            best=reload(best_dir,cfg)
            cap=math.ceil(best[2]["cmax"])
            plan=old.certified_capacity(cfg,cap)
            native=old.Integrated(replace(cfg,max_pairs=plan["pairs"],max_cycles=plan["cycles"]))
            cell.strengthen(native,plan,best[0],cap)
            native.model.addCons(native.cmax>=lower)
            cp,variables,export=old.export(native,best[1]["nonzero"])
            native.model.freeProb()
            del native
            gc.collect()
            engine=cp_model.CpSolver()
            engine.parameters.num_workers=1
            engine.parameters.random_seed=1
            engine.parameters.log_search_progress=True
            engine.parameters.log_to_stdout=False
            errors=[]
            class Emit(cp_model.CpSolverSolutionCallback):
                def on_solution_callback(self):
                    try:
                        if self.objective_value < state["events"][-1]["upper"]-cell.EPS:
                            values={k:self.value(v) for k,v in variables.items() if self.value(v)}
                            checked=cell.lift(cfg,values,plan["cycles"],rebuild=True)
                            if not checked:checked=old.repair(cfg,values,cap)
                            accept(checked,"native-validated new projected CP solution")
                        if len(state["gates"])==3:self.stop_search()
                    except Exception as exc:
                        errors.append(exc)
                        self.stop_search()
            save(OUT/f"primary_projection_{state['attempt']}.json",dict(cap=cap,plan=plan,export=export))
            with (OUT/f"primary_{state['attempt']}.log").open("w",encoding="utf8",buffering=1) as log:
                engine.log_callback=lambda line:log.write(line.rstrip()+"\n")
                status=engine.solve(cp,Emit())
            if errors:raise errors[0]
            if len(state["gates"])!=3:raise ValueError("Primary gates incomplete: "+engine.status_name(status))
        publish()
        save(OUT/"primary_progress.json",dict(expected=3,completed=3,failed=0,elapsed_s=state["elapsed_s"],
                 estimated_total_s=state["elapsed_s"],estimated_remaining_s=0,active=None,status="complete"))
    finally:
        stop.set()
        thread.join()

if __name__=="__main__":
    OUT.mkdir(exist_ok=True,parents=True)
    with (OUT/"primary.lock").open("a+b") as lock:
        lock.seek(0)
        try:msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
        except OSError:
            print("The primary worker is already active.")
        else:main()

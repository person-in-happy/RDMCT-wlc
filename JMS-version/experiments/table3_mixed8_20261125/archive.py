"""Apply all A gates to the same complete archived CP improvement sequence and run fixed B."""
import csv
import importlib.util
import json
import msvcrt
import os
from pathlib import Path
import re
import subprocess
import sys
import time

HERE=Path(__file__).resolve().parent
JMS=HERE.parents[1]
MAIN=JMS/"results/table3_mixed8_20261125"
OUT=MAIN/"archived_stream"
spec=importlib.util.spec_from_file_location("mixed_grid_support",HERE/"run.py")
grid=importlib.util.module_from_spec(spec)
spec.loader.exec_module(grid)
grid.OUT=OUT

def prepare():
    from primary import Config, reload, store, sha, read, save, GATES, BOUND, HINT
    src=JMS/"results/table4_one_percent_20261124"
    trace=src/"runs/D_n8_H10_mixed_dual__s1/A"
    log=trace/"attempt_001/solver.log"
    regress=re.findall(r"^#\d+\s+([\d.]+)s best:([\d.]+)\s+next:",log.read_text(encoding="utf8",errors="replace"),re.M)
    paths=[src/"inputs/D_n8_H10_mixed_dual/A"]+sorted(trace.glob("witness_*/"))
    assert len(regress)==len(paths)==7
    all_candidates=[MAIN/"prepared",HINT]+paths
    # Every archived solution of the trace is accounted for, in actual solver order.
    assert all(float(pair[1])==read(p/"primary.json")["metrics"]["cmax"] for pair,p in zip(regress,paths))
    cfg=Config(**read(all_candidates[0]/"schedule.json")["config"])
    assert sha(BOUND) in (JMS/"results/huber_residence_20261125/primary_A_certificates.csv").read_text()
    lower=read(BOUND)["lower"]
    identity=dict(seed=1,cap_certificate=sha(BOUND),script=sha(Path(__file__)),log_sha256=sha(log),
                  policy="One identical predeclared bound; common SPBS, common prior seed-1 A incumbent, then every physical candidate of the archived single-worker seed-1 projection in original order.",
                  input_model=[sha(p/"primary.json") for p in all_candidates])
    f=OUT/"primary_search.json"
    state=read(f) if f.exists() else dict(identity=identity,gates={},events=[])
    if state["identity"]!=identity:raise ValueError("Frozen candidate list has changed")
    start=time.monotonic()
    for i,p in enumerate(all_candidates):
        if i<len(state["events"]):
            old=state["events"][i]
            assert old["record_sha256"]==sha(OUT/old["path"]/"primary.json")
            continue
        native=reload(p,cfg)
        ub=native[2]["cmax"]
        gap=(ub-lower)/lower
        target=OUT/"physical_events"/f"e{i:03}"
        rec=dict(seed=1,source=str(p.relative_to(JMS)),source_sha256=sha(p/"primary.json"),
                 source_assignment=sha(p/"assignment.json.gz"),source_schedule=sha(p/"schedule.json"),
                 upper=ub,lower=lower,gap=gap,replay_order=i,scope="global_product_Cmax",
                 solver_event_s=None if i<2 else float(regress[i-2][0]))
        store(target,native,rec)
        row=dict(path=target.relative_to(OUT).as_posix(),record_sha256=sha(target/"primary.json"),upper=ub,lower=lower,gap=gap)
        state["events"].append(row)
        for g,tau in GATES.items():
            if g not in state["gates"] and gap<=tau+1e-10:state["gates"][g]=row
        save(f,state)
        print(f"Replayed {i+1}/{len(all_candidates)} physical candidates, elapsed {time.monotonic()-start:.0f}s",flush=True)
    assert len(state["gates"])==3

def main():
    import psutil
    OUT.mkdir(parents=True,exist_ok=True)
    with (OUT/"controller.lock").open("a+b") as lock:
        lock.seek(0)
        try:msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
        except OSError:return
        start=time.monotonic()
        prior=grid.read(OUT/"progress.json").get("elapsed_s",0) if (OUT/"progress.json").exists() else 0
        print("Native A validation and nine B cells; historical 2-worker estimate 90–150 s.",flush=True)
        prepare()
        active={}
        for p in psutil.process_iter(["cmdline"]):
            cmd=p.info.get("cmdline") or []
            if len(cmd)>=3 and os.path.normcase(cmd[-3])==os.path.normcase(str(Path(__file__).resolve())):
                if cmd[-2] in grid.LEVELS and cmd[-1] in grid.LEVELS:active[(cmd[-2],cmd[-1])]=p
        tasks=[(a,b) for a in grid.LEVELS for b in grid.LEVELS]
        while True:
            done={k for k in tasks if grid.checked(*k)}
            for k,p in list(active.items()):
                if not p.is_running():
                    if k not in done:raise RuntimeError(k)
                    del active[k]
            for a,b in tasks:
                if len(active)>=2:break
                if (a,b) in done or (a,b) in active:continue
                loc=OUT/a/b
                loc.mkdir(exist_ok=True,parents=True)
                with (loc/"worker.log").open("a",encoding="utf8") as log:
                    p=subprocess.Popen([sys.executable,"-B","-u",str(Path(__file__).resolve()),a,b],stdout=log,stderr=subprocess.STDOUT)
                active[a,b]=psutil.Process(p.pid)
            elapsed=prior+time.monotonic()-start
            eta=(len(tasks)-len(done))*10/2
            grid.save(OUT/"progress.json",dict(expected=9,completed=len(done),failed=0,elapsed_s=elapsed,
                estimated_remaining_s=eta,estimated_total_s=elapsed+eta,active={a+"/"+b:p.pid for (a,b),p in active.items()},
                basis="Historical fixed eight-wafer B 7–10 solver seconds, two single-worker jobs in parallel",
                recovery="Resume hashed A witnesses and B endpoint cells. Adopt surviving B workers; restart the native tree for interrupted unbounded B cells."))
            print(f"Passed {len(done)}/9, failed 0, wall {elapsed:.0f}s, estimated total {elapsed+eta:.0f}s, ETA {eta:.0f}s",flush=True)
            if len(done)==len(tasks):break
            time.sleep(3)
        grid.export()

if __name__=="__main__":
    if len(sys.argv)==3:grid.worker(*sys.argv[1:])
    else:main()

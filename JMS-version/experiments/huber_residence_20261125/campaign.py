import msvcrt
import os
from datetime import datetime
import sys
import subprocess
import time

import psutil
from jobs import HERE,OUT,folder,read,ready,sha,tasks,write
from report import check,report


def run():
    OUT.mkdir(parents=True,exist_ok=True)
    handle=(OUT/"campaign.lock").open("a+b")
    handle.seek(0)
    try:
        msvcrt.locking(handle.fileno(),msvcrt.LK_NBLCK,1)
    except OSError:
        return
    logs=OUT/"logs"
    logs.mkdir(exist_ok=True)
    shared=HERE.parent/"residence_objective_20261125"
    previous_protocol=OUT.parent/"residence_objective_20261125/protocol.json"
    protocol=dict(objective="mean nonprocessing product residence + 1-second Huber penalty of maximum within-recipe residence range + one second per unused pre-clean quota unit",
        delta_s=1.,early_clean_weight_s=1.,seed_values=[1,2,3],table4_gap_levels=[.1,.01],native_solver_threads=1,
        paired_device="cpu",paired_reference="All three archived A and fixed B stages checked; D is structurally zero for every allowed reference retiming. Measured times and simultaneous targets are unchanged.",
        fixed_reuse="D is identically zero or old lower bound minus 0.5 together with replayed Huber score certifies the requested new gap.",
        paired_reuse="An earlier matched A incumbent above the paired primary target excludes earlier simultaneous hits. A complete native pool, unique minimum-makespan solution, or a winning score reduction of the maximal 0.5 supports the ranking at cutoff. Every reused B is constant-D=0 on its exact structure.",
        recovery="Adopt active workers. Revalidate completed endpoints. Interrupted paired searches restart the native tree using the recorded feasible point, lower bound, cut count and three-second cumulative budget heartbeat. Short fixed/free verification restarts at its own job.",
        previous_protocol_sha256=sha(previous_protocol),
        code={p.name:sha(p) for p in HERE.glob("*.py")},
        shared_code={n:sha(shared/n) for n in ("jobs.py","report.py","paired.py","certificates.py")})
    if (OUT/"protocol.json").exists() and read(OUT/"protocol.json")!=protocol:
        write(OUT/"protocol_history"/(sha(OUT/"protocol.json")+".json"),read(OUT/"protocol.json"))
    write(OUT/"protocol.json",protocol)
    registry=tasks()
    registry.remove("t5_1_no_spbs")
    registry.insert(3,"t5_1_no_spbs")
    workers={}
    entry=str(HERE/"jobs.py")
    for p in psutil.process_iter(["name","cmdline"]):
        a=p.info["cmdline"] or []
        if entry in a and a[-1] in registry:
            workers[a[-1]]=p
    last=set()
    attempts={}
    began=time.time()
    old=OUT/"progress.json"
    previous=read(old).get("elapsed_wall_s",0.) if old.exists() else 0.
    printed=0.
    while True:
        workers={k:p for k,p in workers.items() if p.is_running()}
        done={k for k in registry if (folder(k)/"complete.json").exists()}
        if done!=last:
            for k in done:
                check(k,sha(folder(k)/"complete.json"))
            report()
            last=done
        failed={k for k,c in attempts.items() if c>=2 and k not in workers and k not in done}
        for k in registry:
            if k in done or k in workers or k in failed or not ready(k):
                continue
            if len(workers)>=5 or psutil.virtual_memory().available<4*1024**3:
                break
            if k=="t5_2_scip_default" and not (OUT.parent/"residence_objective_20261125/runs"/k/"complete.json").exists():
                continue
            if k.endswith("_free") and not (OUT/"free_ready.json").exists():
                continue
            exe="G:/conda/envs/a3cenv/python.exe" if k.startswith("t5_") else "G:/conda/python.exe"
            env=dict(os.environ,OMP_NUM_THREADS="1",MKL_NUM_THREADS="1",OPENBLAS_NUM_THREADS="1")
            with (logs/f"{k}-{time.time_ns()}.log").open("w",encoding="utf8") as f:
                workers[k]=psutil.Popen([exe,"-u","-B","-X","utf8",entry,k],cwd=HERE.parents[2],
                       stdout=f,stderr=subprocess.STDOUT,env=env)
            attempts[k]=attempts.get(k,0)+1
        left=[k for k in registry if k not in done]
        def remaining(k):
            if k=="t5_2_scip_default":
                peer=OUT.parent/"residence_objective_20261125/progress.json"
                return max(2.,read(peer)["remaining_s"]) if peer.exists() else 2100.
            if k=="t5_1_no_spbs":
                reference=folder("ref5_1")/"timing.json"
                limit=read(reference)["total_s"] if reference.exists() else 1343.435
                pulse=folder(k)/"clock.json"
                return max(2.,limit-read(pulse)["charged_s"]) if pulse.exists() else limit
            return 10. if k.endswith("_fixed") else 4.
        costs=[remaining(k) for k in left]
        eta=max(max(costs+[0.]),sum(costs)/5)
        elapsed=previous+time.time()-began
        status=dict(at=datetime.now().astimezone().isoformat(timespec="seconds"),pid=os.getpid(),
              expected=len(registry),completed=len(done),failed=len(failed),failures=sorted(failed),
              active={k:{"pid":p.pid} for k,p in workers.items()},elapsed_wall_s=elapsed,
              estimated_total_wall_s=elapsed+eta,remaining_s=eta,free_B_witnesses_available=(OUT/"free_ready.json").exists(),
              eta_basis="Actual shared seed-2 SCIP A countdown; seed-1 no-SPBS uses its matched 1343.435s budget less verified cumulative heartbeat. Short seed jobs run up to five in parallel. Free witness construction is external.")
        write(OUT/"progress.json",status)
        if time.time()-printed>10:
            print(f"{status['at']} verified {len(done)}/{len(registry)} failed {len(failed)} elapsed {elapsed/60:.1f} min estimated total {(elapsed+eta)/60:.1f} min remaining {eta/60:.1f} min; {list(workers)}",flush=True)
            printed=time.time()
        if len(done)==len(registry):
            from final_audit import run as audit
            audit()
            break
        time.sleep(2)


if __name__=="__main__":
    run()

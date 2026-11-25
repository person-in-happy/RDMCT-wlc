"""Run or reattach to the residence-objective campaigns in a foreground console."""
import argparse
import csv
from datetime import datetime
import msvcrt
import os
from pathlib import Path
import re
from statistics import median
import subprocess
import sys
import time

import psutil
from jobs import HERE, OUT, MATCHED, ONE, TEN, folder, passive_reuse, read, ready, sha, tasks, write
from report import check, report

WORKER = HERE/"jobs.py"
CPU = "G:/conda/python.exe"
LEARNING = "G:/conda/envs/a3cenv/python.exe"


def historical(key):
    fields=key.split("_")
    if fields[0]=="primary":
        return 19598.5
    if fields[0]=="t5":
        peer="residence_objective_20261125" if HERE.name=="quota_objective_20261125" else "quota_objective_20261125"
        src=OUT.parent/peer/"runs"/key
        reference=folder("ref5_"+fields[1])/"timing.json"
        if (src/"result.json").exists() and reference.exists():
            other=read(src/"result.json")
            budget=read(reference)
            audited_trace=(src/"A_objectives.jsonl").exists() and (src/"A_cut_times.jsonl").exists()
            full_log=src/"A_attempt1/solver.log"
            if (not (src/"A_reuse.json").exists() and other["stage"]=="A" and other["reason"]=="time_budget"
                    and other["f_A"]>budget["f_A"]+2.e-4 and full_log.exists()):
                accepted=re.findall(r"Primal Bound\s*:[^\n]*\((\d+) solutions?\)",full_log.read_text(encoding="utf8",errors="replace"))
                accounted=accepted and int(accepted[-1])==1+sum(1 for _ in src.glob("witness*.json.gz"))
                if audited_trace or accounted and budget["total_s"]>=other["reference_s"]:
                    return max(3.,budget["total_s"]-other["reference_s"]+3.)
        if fields[1]=="3" and "_".join(fields[2:]) in ("no_rerank","no_spbs","hem"):
            method="_".join(fields[2:])
            hand=read(MATCHED/f"runs/s3_{method}/progress.json")["handoff"]
            reference=folder("ref5_3")/"timing.json"
            if reference.exists():
                return max(1.,read(reference)["total_s"]-hand["at"])
        with (MATCHED/"paired_runs.csv").open(encoding="utf-8-sig") as f:
            return next(float(x["reference_s"]) for x in csv.DictReader(f) if x["seed"]==fields[1])
    if fields[0]=="ref5":
        return 5.
    return 12. if fields[-1]=="fixed" else 90.


def running(jobs):
    workers={}
    for process in psutil.process_iter(["name","cmdline"]):
        args=process.info["cmdline"] or []
        if str(WORKER) in args and args[-1] in jobs and process.info["name"].lower()=="python.exe":
            workers[args[-1]]=process
    return workers


def searching(key):
    if not key.startswith("t5_") or passive_reuse(key):
        return False
    state=folder(key)/"progress.json"
    return not (state.is_file() and read(state).get("exhausted",False))


def other_workers():
    other="residence_objective_20261125" if HERE.name=="quota_objective_20261125" else "quota_objective_20261125"
    another=HERE.parent/other/"jobs.py"
    runs=OUT.parent/other/"runs"
    active={}
    for process in psutil.process_iter(["name","cmdline"]):
        args=process.info["cmdline"] or []
        if not args or str(another) not in args or not args[-1].startswith("t5_"):
            continue
        state=runs/args[-1]/"progress.json"
        if not state.is_file() or not read(state).get("exhausted",False):
            active[args[-1]]=process
    return active


def paired_forecast(registry,done,active,remote,other):
    """Schedule actual running prefixes and residual comparisons on four shared CPU slots."""
    def reference(root,j):
        src=root/"runs"/("ref5_"+j.split("_")[1])/"timing.json"
        return read(src)["total_s"] if src.exists() else historical(j)

    def charged(root,j):
        src=root/"runs"/j
        state=read(src/"progress.json") if (src/"progress.json").exists() else {}
        clock=read(src/"clock.json") if (src/"clock.json").exists() else {}
        pulse=clock.get("charged_s",0.) if clock.get("attempt")==state.get("attempt") else 0.
        return max(state.get("charged_s",0.),pulse)

    left=[j for j in registry if j.startswith("t5_") and j not in done]
    active_times={j:max(0.,reference(OUT,j)-charged(OUT,j)) for j in active if j in left}
    remote_times={j:max(0.,reference(other,j)-charged(other,j)) for j in remote}
    items={j:dict(expected_finish_s=t,source="running local measured budget or observation") for j,t in active_times.items()}

    def estimate(conservative):
        endpoints=list(active_times.values())
        owned=[t for j,t in active_times.items() if searching(j)]
        lanes=sorted(owned+list(remote_times.values()))
        lanes.extend([0.]*max(0,4-len(lanes)))
        queue=[]
        for j in left:
            if j in active_times:
                continue
            if passive_reuse(j):
                t=max(0.,reference(OUT,j)-charged(OUT,j))
                endpoints.append(t)
                if not conservative:
                    items[j]=dict(expected_finish_s=t,source="resumed passive observation")
                continue
            availability=remote_times.get(j,0.)
            if j in remote:
                # Respect the end of the *same* active method/seed. The new
                # comparison shares this primary trajectory if its evidence
                # accounts for the feasible solutions and the cut count.
                seconds=max(3.,reference(OUT,j)-reference(other,j)+3.)
                reason="running peer primary prefix plus residual, provided final trajectory audit passes"
                if conservative:
                    seconds=reference(OUT,j)
            else:
                seconds=historical(j)
                reason="verified peer prefix plus measured residual" if seconds<10 else "seed-specific paired budget"
            queue.append((availability,j,seconds,reason))
        # Tasks only become eligible after a real peer prefix finishes. Pending
        # local work is started first when it can use a released solver slot.
        for availability,j,seconds,reason in sorted(queue,key=lambda row:row[0]):
            i=lanes.index(min(lanes))
            t=max(lanes[i],availability)+seconds
            lanes[i]=t
            endpoints.append(t)
            if not conservative:
                items[j]=dict(expected_finish_s=t,peer_remaining_s=availability,local_work_s=seconds,source=reason)
        return max(endpoints+[0.])
    expected=estimate(False)
    contingency=estimate(True)
    return expected,contingency,items


def main(only):
    OUT.mkdir(parents=True,exist_ok=True)
    logs=OUT/"logs"
    logs.mkdir(exist_ok=True)
    lock=(OUT/"campaign.lock").open("a+b")
    lock.seek(0)
    try:
        msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
    except OSError:
        print("Existing residence-objective controller owns the campaign.",flush=True)
        return
    registry=[j for j in tasks() if not only or j in only]
    quota=HERE.name=="quota_objective_20261125"
    description=("mean product chamber nonprocessing residence + sum over all physical chambers of H*(cleanings+1) minus production cycles"
                 if quota else "mean product chamber nonprocessing residence + maximum within-recipe residence range + actual pre-clean unused production-cycle quota")
    protocol=dict(objectives=["last product return",description],
                  weights=dict(range=0 if quota else 1,clean_seconds_per_cycle=1),seeds=[1,2,3],table4_gap_levels=[.1,.01],
                  table5=dict(gap_A=.01,gap_B=.01,matched="first simultaneous seed-specific target or the complete reference duration",
                              reference="measured preparation + previously verified same-policy A + remeasured residence B including replay",
                              comparator="actual CPU A search or complete validated A trace; original A cut rounds; new B at the exact recorded handoff",
                              active_comparison_limit=4),
                  previous={p.parent.name:sha(p) for p in [ONE/"protocol.json",TEN/"protocol.json",MATCHED/"protocol.json"]},
                  threads_per_worker=1,learning_device="cpu",parent_assignment="recorded and revalidated against full physical model and product events",
                  recovery="controller adopts existing workers. Verified endpoints are skipped. A restores native witnesses and rigorous lower bounds. Paired runs restore incumbent, upper/lower bounds, cutoff rounds and elapsed budget to a three second heartbeat; SCIP/CP search trees restart. Short fixed B solves restart only their own stage.",
                  code={name:sha(HERE/name) for name in ("campaign.py","jobs.py","paired.py","solver.py","score.py","report.py")})
    if quota:
        shared_sources=HERE.parent/"residence_objective_20261125"
        protocol["shared_runner_source"]={name:sha(shared_sources/name) for name in ("campaign.py","jobs.py","paired.py","report.py")}
    p=OUT/"protocol.json"
    if p.exists() and read(p)!=protocol:
        write(OUT/"protocol_history"/(sha(p)+".json"),read(p))
    write(p,protocol)
    active=running(registry)
    statusfile=OUT/"progress.json"
    past=read(statusfile).get("elapsed_wall_s",0.) if statusfile.exists() else 0.
    start=time.time()
    attempts={}
    peak=8
    last_print=0.
    last_verified_count=-1
    shared=(OUT.parent/"residence_objective_20261125/paired_allocation.lock").open("a+b")
    while True:
        ended=[j for j,p in active.items() if not p.is_running()]
        for j in ended:
            del active[j]
        done={j for j in registry if (folder(j)/"complete.json").is_file()}
        scope_file=OUT/"run_scope.json"
        scope=read(scope_file) if scope_file.exists() else {}
        deferred={j for j in registry if j not in done and "allow" in scope and j not in scope["allow"]}
        if len(done)!=last_verified_count:
            for key in done:
                check(key,sha(folder(key)/"complete.json"))
            report()
            last_verified_count=len(done)
        failed={j for j,n in attempts.items() if n>=2 and j not in active and j not in done}
        if failed:
            fresh=OUT/"retry.json"
            if fresh.exists():
                old=read(fresh)
                for j in failed & set(old):
                    if old[j]>attempts.get("retry:"+j,0):
                        attempts["retry:"+j]=old[j]
                        attempts[j]=0
                failed={j for j in failed if attempts[j]>=2}
        shared.seek(0)
        msvcrt.locking(shared.fileno(),msvcrt.LK_LOCK,1)
        remote=other_workers()
        other=OUT.parent/("residence_objective_20261125" if quota else "quota_objective_20261125")
        remote_controller=other/"progress.json"
        has_peer=remote_controller.exists() and psutil.pid_exists(read(remote_controller)["pid"])
        for j in registry:
            if j in done or j in deferred or j in active or j in failed or not ready(j):
                continue
            if len(active)>=peak or psutil.virtual_memory().available<4.0*1024**3:
                break
            if j.startswith("t5_") and not passive_reuse(j) and has_peer:
                if j in remote:
                    continue
                if not quota and not (other/"runs"/j/"complete.json").exists():
                    continue
            # Keep slots for the parallel, relatively short Table 4 handoffs.
            if j.startswith("t5_") and not passive_reuse(j) and sum(searching(k) for k in active)>=2 and any(
                    k.startswith("t4_") and k.endswith("_fixed") and k not in done and ready(k) for k in registry):
                continue
            if j.startswith("t5_") and not passive_reuse(j) and len(remote)+sum(searching(k) for k in active)>=4:
                continue
            if j.startswith("primary_") and sum(k.startswith("primary_") for k in active)>=2:
                continue
            if j.startswith("t4_") and j.endswith("_free") and not (OUT/"free_ready.json").exists():
                continue
            log=logs/f"{j}-{time.time_ns()}.log"
            exe=LEARNING if j.startswith("t5_") else CPU
            env=dict(os.environ,OMP_NUM_THREADS="1",MKL_NUM_THREADS="1",OPENBLAS_NUM_THREADS="1")
            with log.open("w",encoding="utf8") as fh:
                active[j]=psutil.Popen([exe,"-B","-u","-X","utf8",str(WORKER),j],
                    cwd=HERE.parents[2],stdout=fh,stderr=subprocess.STDOUT,env=env)
            attempts[j]=attempts.get(j,0)+1
        shared.seek(0)
        msvcrt.locking(shared.fileno(),msvcrt.LK_UNLCK,1)
        now=time.time()
        # Age of the most recent completed attempt forms the sample for its own size/stage.
        samples={}
        for j in done:
            parts=j.split("_")
            group=tuple(parts[i] for i in (0,2,5)) if j.startswith("t4_") else parts[0]
            samples.setdefault(group,[]).append(read(folder(j)/"complete.json")["wall_seconds"])
        def remaining(j):
            parts=j.split("_")
            group=tuple(parts[i] for i in (0,2,5)) if j.startswith("t4_") else parts[0]
            seconds=historical(j) if j.startswith("t5_") or group not in samples else median(samples[group])
            if j in active:
                seconds=max(seconds*.1,seconds-(now-active[j].create_time()))
            return seconds
        left=[j for j in registry if j not in done and j not in failed and j not in deferred]
        independent=[remaining(j) for j in left if not j.startswith("t5_")]
        paired_s,contingency_s,work_items=paired_forecast(registry,done|deferred,active,remote,other)
        eta=max(sum(independent)/peak,max(independent+[0.]),
                sum(remaining(j) for j in left if j.startswith("primary_"))/2,
                paired_s)
        elapsed=past+now-start
        state=dict(at=datetime.now().astimezone().isoformat(timespec="seconds"),pid=os.getpid(),
                   expected=len(registry),completed=len(done),failed=len(failed),failures=sorted(failed),
                   deferred_by_scope=sorted(deferred),scope_reason=scope.get("reason"),
                   active={k:dict(pid=p.pid,wall_s=round(now-p.create_time(),1),
                        waiting_for_observation=k.startswith("t5_") and not searching(k)) for k,p in active.items()},
                   elapsed_wall_s=elapsed,estimated_total_wall_s=elapsed+eta,remaining_s=eta,concurrency=peak,
                   other_live_comparison_workers=list(remote),
                   paired_forecast=work_items,remaining_s_if_pending_peer_prefixes_fail=max(eta,contingency_s),
                   eta_basis="Four solver slots are shared. T5 deducts actual source and local cumulative time, models absent tasks on open slots and reuses each active peer prefix once if verified. A second estimate assumes all pending peer prefix audits require a new solve.")
        write(statusfile,state)
        if now-last_print>=10 or ended:
            print(f"{state['at']} verified {len(done)}/{len(registry)}; failed {len(failed)}; "
                  f"elapsed {elapsed/60:.1f} min; estimated total {(elapsed+eta)/60:.1f} min; "
                  f"remaining {eta/60:.1f} min; active {', '.join(active)}",flush=True)
            last_print=now
        if (not active and not left) or (not active and failed and not any(ready(j) for j in left)):
            if not quota and not only and len(done)==len(tasks()):
                from final_audit import run as verify_all
                verify_all()
            break
        time.sleep(3)


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--only",nargs="*")
    main(parser.parse_args().only)

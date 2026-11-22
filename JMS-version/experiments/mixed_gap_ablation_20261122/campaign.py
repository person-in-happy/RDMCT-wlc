"""Visible foreground controller for two-gap experiments and paired result review."""
import csv
from datetime import datetime
import msvcrt
import os
from pathlib import Path
import subprocess
import sys
import time

import psutil
from inputs import BASE, HERE, ROOT, SCENARIOS, TAU, read, save, sha
from controls import SCIP
from joint_algorithms import policy_record

METHODS = dict(full="proposed", no_rerank="proposed_no_structure", greedy="proposed_greedy",
               feature_only="feature_only", hem_spbs="hem", default="scip")
GIB = 1024**3


def protocol():
    jobs = {}
    weights = {}
    for train in (1, 2, 3):
        for seed in (1, 2, 3):
            for case in SCENARIOS:
                for start in ("prepared", "raw"):
                    for method, family in METHODS.items():
                        if case == "H6" and train != 1:
                            continue
                        if method == "default" and train != 1:
                            continue
                        if case != "H6" and start == "raw" and method not in ("default", "full", "hem_spbs"):
                            continue
                        key = f"{case}__s{seed}__t{train}__{start}__{method}"
                        if (family, train) not in weights:
                            weights[family, train] = policy_record(family, train)
                        weight = weights[family, train]
                        jobs[key] = dict(case=case, seed=seed, training_seed=train, initialization=start,
                             method=method, checkpoint_sha256=weight["sha256"] if weight else None)
    assert len(jobs) == 36+3*69
    return dict(gap_A=TAU, gap_B=TAU, seconds_A=None, seconds_B=None, jobs=jobs,
        instance_parameters=SCENARIOS, workers=2, solver_threads=1, inference="CPU",
        primary_domain="All schedules at or below the constructive upper bound, safe count capacities.",
        secondary_domain="First-stage makespan cap and discrete structure except sync decisions; product waiting only.",
        weights=[rec for rec in weights.values() if rec])


def write_review(jobs, completed):
    rows = []
    for key in completed:
        result = read(BASE/"runs"/key/"result.json")
        assert result["verified"] and result["physical_replay"]
        a, b = result["A"], result["B"]
        assert a["gate"] and a["gap"] <= TAU+1e-9 and b["gap"] <= TAU+1e-9
        rows.append(dict(**jobs[key], f_A=result["metrics"]["cmax"], f_B=result["metrics"]["secondary"],
             seconds_A=a["seconds"], seconds_B=b["seconds"], calls=a["policy_calls"],
             gap_A=a["gap"], gap_B=b["gap"], lower_A=a["lower"], lower_B=b["lower"], source=key))
    if rows:
        path=BASE/"verified_runs.csv"
        tmp=path.with_suffix(".tmp")
        with tmp.open("w",newline="",encoding="utf-8-sig") as stream:
            w=csv.DictWriter(stream,fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)
        os.replace(tmp,path)


def controller():
    BASE.mkdir(parents=True, exist_ok=True)
    with (BASE/"controller.lock").open("a+b") as lock:
        lock.seek(0)
        msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        config = protocol()
        file = BASE/"protocol.json"
        if file.exists():
            # JSON lists replace tuples in saved parameters; compare the experimental design.
            previous = read(file)
            assert previous["jobs"] == config["jobs"] and previous["weights"] == config["weights"]
            assert previous["gap_A"] == TAU and previous["gap_B"] == TAU
        else:
            save(file,config)
        jobs = config["jobs"]
        done = {k for k in jobs if (BASE/"runs"/k/"result.json").is_file()}
        failed = {}
        pending = [k for k in jobs if k not in done]
        active = {}
        start = time.monotonic()
        initial = len(done)
        writes = -1
        while pending or active:
            for key,(proc,started) in list(active.items()):
                code=proc.poll()
                if code is None:
                    continue
                del active[key]
                if code==0 and (BASE/"runs"/key/"result.json").exists():
                    done.add(key)
                else:
                    failed[key]=dict(code=code, ended=datetime.now().isoformat(timespec="seconds"))
            while len(active)<2:
                if psutil.virtual_memory().available < (9 if active else 7)*GIB:
                    break
                key=next((k for k in pending if (BASE/"inputs"/jobs[k]["case"]/f"s{jobs[k]['seed']}"/"input.json").exists()),None)
                if not key:
                    break
                pending.remove(key)
                folder=BASE/"runs"/key
                folder.mkdir(parents=True,exist_ok=True)
                log=folder/f"console-{time.time_ns()}.log"
                with log.open("w",encoding="utf8") as output:
                    proc=subprocess.Popen([SCIP,"-B","-X","utf8","-u",str(HERE/"worker.py"),key,"6500"],
                                          cwd=ROOT,stdout=output,stderr=subprocess.STDOUT)
                active[key]=(proc,time.time())
            snapshot={}
            for key,(proc,started) in active.items():
                statefile=BASE/"runs"/key/"live.json"
                info=read(statefile) if statefile.exists() else dict(stage="A",activity="loading")
                snapshot[key]=dict(pid=proc.pid,launched=started,**info)
            new=len(done)-initial
            eta=(time.monotonic()-start)*(len(pending)+len(active))/new if new else None
            progress=dict(total=len(jobs),completed=len(done),failed=failed,queued=len(pending),active=snapshot,
                          eta_seconds=eta,updated=datetime.now().isoformat(timespec="seconds"))
            save(BASE/"progress.json",progress)
            print(f"{progress['updated']}  complete {len(done)}/{len(jobs)} | failed {len(failed)} | "
                  f"queued {len(pending)} | ETA "+(f"{eta/3600:.1f} h" if eta else "awaiting completed pairs"),flush=True)
            for k,v in snapshot.items():
                print(f"  {k} stage {v['stage']} | {v['activity']} | L={v.get('lower')} U={v.get('upper')}",flush=True)
            if writes!=len(done):
                write_review(jobs,sorted(done))
                writes=len(done)
            if pending or active:
                time.sleep(12)
        write_review(jobs,sorted(done))
        return int(bool(failed))


if __name__=="__main__":
    sys.exit(controller())

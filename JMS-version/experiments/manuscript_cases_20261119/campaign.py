"""Run the measured manuscript configurations in an isolated, resumable foreground queue."""
import argparse
from collections import deque
from contextlib import contextmanager
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path
import os
import subprocess
import sys
import time

import psutil

from cases import BACKENDS, HERE, JMS, RESULTS, ROOT, catalog, dump, read, sha

OUT = RESULTS / "manuscript_cases_A0p001pct_B0p001pct_20261119"
SWEEPS = [[560,100,2.5,False],[760,140,4.,True],[660,130,3.,False],[940,160,5.,True]]


def protocol(out):
    cases, screened = catalog()
    code = [HERE / f for f in ("cases.py","archived.py","grouping.py","certificate.py","worker.py")]
    for family in BACKENDS.values():
        code.extend(family.glob("*.py"))
    for name,files in (
        ("scale75_repack_20261118",("improve.py","neighborhood.py","search.py")),
        ("scale75_20261118",("run.py","resources.py","patterns.py","packing.py","timing.py")),
        ("finite_budget_20261116",("finite_budget.py",)),
    ):
        code.extend(HERE.parent / name / f for f in files)
    code.extend((ROOT/"scip_imports.py",JMS/"JMS_Review_CN.tex",JMS/"tools/incumbent_sublevel.py",
                 JMS/"tools/render_journal_schedule_examples.py", JMS/"tools/current_defaults_swimlane.py"))
    spec = dict(cases=cases, historical_qualification=screened, seed=1, beam_width=14, sweeps=SWEEPS,
                A_relative_gap=1e-5, B_relative_gap=1e-5, workers_per_solve=1,
                solver_memory_mib=256, process_commit_limit_mib=1024, reserve_system_mib=2048,
                B_time_limit_s=60, B_objective=dict(wait_sum=1,wait_max=10,rhythm=25),
                packages={n:version(n) for n in ("ortools","pyscipopt")},
                sources={p.relative_to(ROOT).as_posix():sha(p) for p in sorted(set(code))})
    path=out/"campaign.json"
    if path.exists():
        saved=read(path)
        # A reviewed manuscript may move to the dated archive after the run.
        paper="JMS-version/JMS_Review_CN.tex"
        original=saved["sources"].get(paper)
        if original and spec["sources"][paper]!=original:
            snapshots=(JMS/"review").glob("*/JMS_Review_CN.before.tex")
            if any(sha(p)==original for p in snapshots):
                spec["sources"][paper]=original
        if saved!=spec:
            raise ValueError("Saved search protocol or frozen input differs from the current sources")
    else:
        dump(path,spec)
    return spec


def complete(out, case, token):
    folder=out/"cases"/case["id"]
    if not (folder/"evidence.json").exists():
        return False
    record=read(folder/"evidence.json")
    if record["protocol"]!=token or record["case"]!=case["id"]:
        raise ValueError(f"Incompatible result for {case['id']}")
    for name,expected in record["files"].items():
        if sha(folder/name)!=expected:
            raise ValueError(f"Saved file changed: {case['id']}/{name}")
    return True


@contextmanager
def queue_lock(out):
    import msvcrt
    out.mkdir(parents=True,exist_ok=True)
    with (out/"queue.lock").open("a+b") as f:
        if not f.tell():
            f.write(b"0")
            f.flush()
        f.seek(0)
        try:
            msvcrt.locking(f.fileno(),msvcrt.LK_NBLCK,1)
        except OSError as error:
            raise RuntimeError("This experiment already has a foreground controller") from error
        try:
            yield
        finally:
            f.seek(0)
            msvcrt.locking(f.fileno(),msvcrt.LK_UNLCK,1)


def run(out,jobs):
    with queue_lock(out):
        spec=protocol(out)
        token=sha(out/"campaign.json")
        cases=spec["cases"]
        done=[c["id"] for c in cases if complete(out,c,token)]
        waiting=deque(c for c in cases if c["id"] not in done)
        active,failed,durations={},{},[]
        last=0.
        def status(state):
            stages={}
            for key,(p,log,t,_) in active.items():
                path=out/"cases"/key/"progress.json"
                stages[key]=dict(pid=p.pid, **(read(path) if path.exists() else {"phase":"starting"}))
            eta=(round(sum(durations)/len(durations)*(len(waiting)+len(active))/jobs) if durations else None)
            if not waiting and not active: eta=0
            info=dict(state=state,completed=done,active=stages,failed=failed,pending=[c["id"] for c in waiting],
                      eta_s=eta,concurrency=jobs,total=len(cases),protocol=token,
                      updated=datetime.now(timezone.utc).isoformat())
            dump(out/"status.json",info)
            labels=" ".join(f"{k}={r['phase']}" for k,r in stages.items())
            print(f"{state} | completed {len(done)}/{len(cases)} | failed {len(failed)} | "
                  f"ETA {str(eta)+' s' if eta is not None else 'estimating'} | {labels}",flush=True)
        try:
            while waiting or active:
                for key,(p,log,t,case) in list(active.items()):
                    if p.poll() is None: continue
                    log.close()
                    del active[key]
                    durations.append(time.monotonic()-t)
                    if p.returncode==0 and complete(out,case,token):
                        done.append(key)
                    else:
                        failed[key]=dict(exit_code=p.returncode,log=f"cases/{key}/worker.log")
                    last=0
                while waiting and len(active)<jobs and psutil.virtual_memory().available>=(jobs+2)*1024**3:
                    case=waiting.popleft()
                    key=case["id"]
                    folder=out/"cases"/key
                    folder.mkdir(parents=True,exist_ok=True)
                    log=(folder/"worker.log").open("ab",buffering=0)
                    log.write(f"\n{datetime.now(timezone.utc).isoformat()} | starting {key}\n".encode())
                    child=subprocess.Popen([sys.executable,"-B","-X","utf8","-u",str(HERE/"worker.py"),str(out),key],
                                           cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
                    active[key]=child,log,time.monotonic(),case
                    last=0
                if time.monotonic()-last>=4:
                    status("running")
                    last=time.monotonic()
                if waiting or active: time.sleep(.6)
        except (KeyboardInterrupt,SystemExit):
            status("interrupted")
            raise
        finally:
            for p,log,_,_ in active.values():
                if p.poll() is None: p.terminate()
                p.wait()
                log.close()
        status("completed" if not failed else "incomplete")
        if failed: raise RuntimeError("Inspect the failed case logs and use Resume to retry")


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action",choices=("prepare","run","resume","status","report","figures","verify"))
    parser.add_argument("--output",type=Path,default=OUT)
    parser.add_argument("--jobs",type=int,choices=(1,2,3),default=2)
    args=parser.parse_args()
    out=args.output.resolve()
    if args.action=="prepare":
        print(f"{len(protocol(out)['cases'])} cases prepared at {out}")
    elif args.action in ("run","resume"):
        run(out,args.jobs)
        from report import summarize
        summarize(out)
    elif args.action=="status":
        import json
        print(json.dumps(read(out/"status.json"),indent=2,ensure_ascii=False))
    elif args.action=="figures":
        from report import figures
        figures(out)
    else:
        from report import summarize,verify_figures
        summarize(out)
        if args.action=="verify": verify_figures(out)

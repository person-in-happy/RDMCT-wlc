"""Product-only four-arm comparisons. Each process owns its backend and output."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import importlib.util
from pathlib import Path
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "product_wait_20261122"))
import run as product
from run import JMS, ROOT, cell, read, save, sha

def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    obj = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(obj)
    return obj

matched = module("matched_legacy", HERE.parent / "matched_controls_20261122/run.py")
OUT = JMS / "results/mixed_controls_20261122"
SCIP = "G:/conda/envs/a3cenv/python.exe"
CP = "G:/conda/python.exe"

def product_solve(folder, source, assignment, backend, n, seed, kind, seconds=None, gap=None):
    key = "endpoint"
    task = dict(case=folder.name, seed=seed, kind=kind, seconds=seconds, gap=gap,
                rho=0.1 if kind=="joint" else None, weight=25, backend=backend, n=n,
                schedule=source.relative_to(ROOT).as_posix(), assignment=assignment.relative_to(ROOT).as_posix(),
                schedule_sha256=sha(source), assignment_sha256=sha(assignment), parent_eligible=True)
    folder.mkdir(parents=True, exist_ok=True)
    save(folder/"protocol.json", dict(jobs={key:task}))
    product.OUT = folder
    product.worker(key)
    return read(folder/"runs"/key/"result.json")

def store_primary(folder, checked, record):
    save(folder/"schedule.json",checked[0])
    save(folder/"assignment.json.gz",checked[1])
    save(folder/"primary.json",dict(record=record,replay=checked[3],rows=checked[4],
        metrics=product.product_metrics(checked[0]), schedule_sha256=sha(folder/"schedule.json"),
        assignment_sha256=sha(folder/"assignment.json.gz")))

def compare(key, seed, arm, folder):
    case = matched.CASES[key]
    sys.path.insert(0,str(cell.BACKENDS[case["backend"]]))
    import model
    source, assignment = ROOT/case["source"],ROOT/case["assignment"]
    assert (sha(source),sha(assignment))==(case["source_sha256"],case["assignment_sha256"])
    stages = []
    if arm in ("A","AB"):
        seconds = 300 if arm=="A" else 270
        cfg = model.Config(**case["config"])
        data,vals = read(source),cell.values(assignment)
        checked = cell.certify_start(cfg,data,vals)
        result,record = matched.objective_stage(cfg,checked[2],vals,"AB",seconds,dict(n=case["n"],seed=seed),folder)
        store_primary(folder/"primary",result,record)
        source,assignment=folder/"primary/schedule.json",folder/"primary/assignment.json.gz"
        stages.append((record,seconds))
        metrics=product.product_metrics(result[0])
    if arm!="A":
        seconds=30 if arm=="AB" else 300
        e=product_solve(folder/"secondary",source,assignment,case["backend"],case["n"],seed,
                        {"AB":"fixed","B":"B","J":"joint"}[arm],seconds)
        stages.append((e["record"],seconds))
        metrics=e["measured"]
    valid=all(r["seconds"]<=budget+1 and r["status"] not in ("memlimit","unknown","userinterrupt") for r,budget in stages)
    save(folder/"result.json",dict(case=key,seed=seed,arm=arm,start=case["assignment_sha256"],
                                  stages=stages,eligible=valid,metrics=metrics))

def execute(jobs,workers,output):
    output.mkdir(parents=True,exist_ok=True)
    save(output/"plan.json",dict(tasks=jobs,workers=workers,threads_per_solver=1))
    def launch(j):
        exe, script, args, directory = j
        folder=Path(directory)
        folder.mkdir(parents=True,exist_ok=True)
        if (folder/"result.json").exists():return True
        with (folder/"console.log").open("w",encoding="utf8") as stream:
            return subprocess.run([exe,"-B","-X","utf8",script,*args],cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT).returncode==0
    start=time.monotonic(); failed=[]
    with ThreadPoolExecutor(workers) as pool:
        futures={pool.submit(launch,j):j for j in jobs}
        pending=set(futures)
        import concurrent.futures
        while pending:
            done,pending=concurrent.futures.wait(pending,timeout=8,return_when=concurrent.futures.FIRST_COMPLETED)
            failed.extend(futures[f][-1] for f in done if not f.result())
            count=len(jobs)-len(pending);left=len(pending)
            eta=(time.monotonic()-start)*left/count if count else 300*left/workers
            print(f"{count}/{len(jobs)} finished | {len(failed)} failed | ETA {eta/60:.1f} min",flush=True)
            save(output/"progress.json",dict(finished=count,total=len(jobs),failed=failed,remaining=left))
    return int(bool(failed))

if __name__=="__main__":
    if len(sys.argv)>1:
        case,seed,arm,path = sys.argv[1:]
        compare(case,int(seed),arm,Path(path))
    else:
        jobs=[]
        for seed in (1,2,3):
            for n in (4,8):
                for h in (10,3):
                    case=f"E_n{n}_H{h}_mixed_dual"
                    for arm in (("J",) if h==10 else ("J","A","B","AB")):
                        folder=str(OUT/"objectives"/f"{case}__s{seed}__{arm}")
                        jobs.append((SCIP,__file__,[case,str(seed),arm,folder],folder))
        sys.exit(execute(jobs,4,OUT/"objectives"))

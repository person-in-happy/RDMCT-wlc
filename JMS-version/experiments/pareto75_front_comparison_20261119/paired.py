"""Frozen paired experiment protocol and visible CPU supervisor with atomic result checkpoints."""
from concurrent.futures import ProcessPoolExecutor, wait, FIRST_COMPLETED
import json
import random
import time
import traceback
from case_setup import HERE, OUT, OLD, ROOT, CASES, METHODS, SEEDS, WORKERS, NFE, digest, read, save
from campaign75 import contract as previous_contract
from trial import run_cell


def spec():
    inputs={str((HERE/p).relative_to(ROOT)):digest(HERE/p) for p in ("trial.py","case_setup.py","paired.py")}
    inputs.update({str(p.relative_to(ROOT)):digest(p) for p in sorted((OUT/"shared").glob("*"))})
    return dict(cases=CASES,methods=METHODS,seeds=SEEDS,budget_evaluations=NFE,workers=WORKERS,threads=1,
        primary="Per-run HV of at most 7 exported schedules, shared case-specific scales from the warm timetable and reference (1.1,1.1).",
        secondary="Untruncated HV, run endpoints, 50% empirical attainment curves, paired wins/ties/losses, total wall time and actual LP calls. No global Pareto certificate at N=75.",
        controls="Same frozen schedule and same 12 charged endpoint evaluations of six structures for all four arms; evolutionary methods use those genotypes to form the starting population; uniform differs from domain solely by long-visit sampling. One fixed-route deterministic run per workload is descriptive.",
        tests="Within each case, domain minus NSGA-II, MOEA/D, uniform. Six exact two-sided binomial sign tests, ties omitted with zero tolerance 1e-10. Holm FWER .05 over all six, one predetermined family. Median paired HV difference and exact distribution-free median interval; 12 independent paired seeds per case, not 12 different workloads. Fixed sample; no optional stopping.",
        verification="Every final internal and submitted point checked against the full original model. Common founders, archive construction, time/evaluation cutoff and post-hoc score recomputed. Full and seven-point HV as separate endpoints.",
        order="Balanced random method order within case and seed, shuffle paired blocks with seed 20261119; fixed-route references run once per case.",
        previous_frozen=previous_contract(),sha256=inputs)


def log(s):
    print(s,flush=True)
    with (OUT/"progress.log").open("a",encoding="utf-8") as f:
        f.write(time.strftime("%H:%M:%S ")+s+"\n")


def execute(label,items,fn,on_done,workers,estimate):
    if not items:
        return
    start=time.monotonic()
    n=len(items)
    complete=failed=0
    with ProcessPoolExecutor(max_workers=workers) as pool:
        pending={pool.submit(fn,job):job for job in items}
        while pending:
            finished,_=wait(pending,timeout=10,return_when=FIRST_COMPLETED)
            for future in finished:
                job=pending.pop(future)
                try:
                    result=future.result()
                    on_done(job,result)
                    complete+=1
                except Exception:
                    failed+=1
                    log(f"FAILED {job}: "+traceback.format_exc())
            elapsed=time.monotonic()-start
            eta=elapsed*len(pending)/(complete+failed) if complete+failed>=workers else max(0,(n+workers-1)//workers*estimate-elapsed)
            log(f"{label}: complete {complete}/{n}, failed {failed}, elapsed {elapsed:.0f}s, ETA {eta:.0f}s")
    if failed:
        raise RuntimeError(f"{label}: {failed} failed cells")


def jobs():
    rng=random.Random(20261119)
    blocks=[(c,s) for c in CASES for s in SEEDS]
    rng.shuffle(blocks)
    all_jobs=[]
    for c,s in blocks:
        methods=list(METHODS)
        rng.shuffle(methods)
        all_jobs.extend((c,m,s) for m in methods)
    return [(c,"fixed",0) for c in CASES]+all_jobs


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    frozen=json.loads(json.dumps(spec()))
    path=OUT/"protocol.json"
    if path.exists():
        if read(path)!=frozen:
            raise RuntimeError("Frozen protocol or inputs changed")
    else:
        save(path,frozen)
    cells=jobs()
    pending=[j for j in cells if not (OUT/j[0]/f"{j[1]}_{j[2]}"/"run.json").exists()]
    log(f"Two 75-wafer workloads | {len(pending)}/{len(cells)} cells | 6 one-thread CPU workers | 160 evaluations including common founders")
    execute("search",pending,run_cell,lambda j,r:None,WORKERS,65)
    assert all((OUT/c/f"{m}_{s}"/"run.json").is_file() for c,m,s in cells)
    save(OUT/"finished.json",dict(cells=len(cells),source_match=read(path)==json.loads(json.dumps(spec()))))
    log(f"SEARCH COMPLETE {len(cells)}/{len(cells)}")


if __name__=="__main__":
    main()

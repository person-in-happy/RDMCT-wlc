"""Visible foreground supervisor. Freeze comparisons first, then audit every returned timetable."""
import argparse
from concurrent.futures import ProcessPoolExecutor, wait, FIRST_COMPLETED
import gzip
import json
import os
from pathlib import Path
import platform
import sys
import time
import traceback
from collections import Counter
from contextlib import ExitStack
from types import SimpleNamespace
from unittest.mock import patch

from large75 import (HERE, JMS, PARETO, PATTERNS, SOURCE, GRID, BUDGET, WORKERS, METHODS, SEEDS,
                     BOUNDS, REF, Config, Search, digest, metrics, read, save, signature, validate, write_run)

OUT = HERE / "results" / "formal02"


def contract():
    from common import ROOT, BACKEND
    import numpy, scipy, pyscipopt
    files = set(HERE / n for n in ("large75.py", "campaign75.py"))
    files.update(PARETO / n for n in ("common.py","decoder.py","evolution.py","witness.py"))
    files.update(SOURCE / n for n in ("result.json","search.json","timing_B.json","campaign.json","original_row_audit/certificate.json"))
    for directory in (BACKEND,PATTERNS,PATTERNS/"audit"):
        files.update(directory.glob("*.py"))
    files.update(ROOT / n for n in ("joint_pairing_model.py","joint_chamber_cycle_model.py"))
    files.add(JMS/"experiments/finite_budget_20261116/finite_budget.py")
    return dict(methods=list(METHODS), seeds=list(SEEDS), budget_s=BUDGET, workers=WORKERS, threads=1,
                python=sys.version, platform=platform.platform(), scipy=scipy.__version__, numpy=numpy.__version__,
                pyscipopt=pyscipopt.__version__, time_grid=1/GRID, rhythm_weight=25, bounds=BOUNDS, ref=REF,
                selection="At most 7 returned per run: both extrema, then maximum normalized minimum Euclidean distance. Ties use increasing A.",
                timing="Same precomputed starting plan and base decoder initialized before clock; search, LP and physical validation charged. Full row audit separately timed.",
                thresholds=[3750,2949], sha256={str(p.relative_to(ROOT)):digest(p) for p in sorted(files)})


def audit_schedule(path):
    from witness import sparse_witness
    sys.path.append(str(PATTERNS / "audit"))
    import check_model as ck
    begin = time.monotonic()
    with gzip.open(path,"rt",encoding="utf-8") as f:
        data = json.load(f)
    assert signature(data) == path.name.split(".")[0]
    cfg = Config(**data["config"])
    replay = validate(data)
    assert replay["valid"] and not cfg.max_pairs and not cfg.max_cycles
    actual = metrics(data,25)
    assert actual["cmax"] == max(j["loan_end"] for j in data["jobs"] if j["product"])
    covered = [j["identity"] for j in data["jobs"] if j["product"]]
    assert len(covered) == 75 and sorted(covered) == sorted(w for job in cfg.pjobs for w in job["wafers"])
    values = sparse_witness(cfg,data)
    assert all(v*GRID == round(v*GRID) for v in values.values())
    rows = ck.RowCheck(values)
    api = SimpleNamespace(Model=lambda name:rows, quicksum=sum)
    instance = ck.model.Integrated.__new__(ck.model.Integrated)
    with ExitStack() as stack:
        for module in (ck.model, ck.joint_pairing_model, ck.joint_chamber_cycle_model):
            stack.enter_context(patch.object(module,"scip",api))
        try:
            instance.__init__(cfg)
        except ck.RowsComplete:
            pass
        else:
            raise RuntimeError("The original model generator did not finish all rows")
    assert rows.rows == 24271470 and sum(rows.types.values()) == 6764011
    assert float(instance.secondary_objective) == actual["secondary"]
    assert rows.nonzero["Cmax"] == actual["cmax"]
    return dict(schedule=signature(data), metrics=actual, rows=rows.rows, types=rows.types,
                products=len(covered), cycles=len(data["cycles"]), physical_valid=True,
                secondary_original=float(instance.secondary_objective), elapsed=time.monotonic()-begin)


def run_one(item):
    method, seed = item
    folder = OUT / f"{method}_{seed}"
    folder.mkdir(exist_ok=True)
    return write_run(folder,method,seed)


def status(message):
    print(message,flush=True)
    with (OUT / "progress.log").open("a",encoding="utf-8") as f:
        f.write(time.strftime("%H:%M:%S ")+message+"\n")


def pool(label, items, function, done, estimate):
    start = time.monotonic()
    n = len(items)
    complete, errors = 0, []
    with ProcessPoolExecutor(max_workers=WORKERS) as executor:
        active = {executor.submit(function, item):item for item in items}
        while active:
            finished,_ = wait(active,timeout=10,return_when=FIRST_COMPLETED)
            for future in finished:
                item = active.pop(future)
                try:
                    value = future.result()
                    done(item,value)
                    complete += 1
                except Exception:
                    errors.append((str(item),traceback.format_exc()))
                    status(f"FAILED {item}: {errors[-1][1]}")
            elapsed = time.monotonic()-start
            eta = ((elapsed/(complete+len(errors))*(len(active))) if complete+len(errors) >= WORKERS
                   else max(0, (n+WORKERS-1)//WORKERS*estimate-elapsed))
            status(f"{label}: complete {complete}/{n} | failed {len(errors)} | elapsed {elapsed:.0f}s | ETA {eta:.0f}s")
    if errors:
        raise RuntimeError(f"{label}: {len(errors)} failure(s)")


def run():
    OUT.mkdir(parents=True, exist_ok=True)
    spec = json.loads(json.dumps(contract()))
    if (OUT/"protocol.json").exists():
        if read(OUT/"protocol.json") != spec:
            raise RuntimeError("Protocol changed; use a new output directory")
    else:
        save(OUT/"protocol.json",spec)
    jobs = [(m,s) for s in SEEDS for m in METHODS if not (OUT/f"{m}_{s}"/"run.json").exists()]
    status(f"75 product wafers | {len(jobs)} searches pending | 3 CPU workers, one thread each | {BUDGET} s cap")
    pool("search",jobs,run_one,lambda item,value:status(f"{item}: {value} returned points"),BUDGET)
    paths = {}
    for m in METHODS:
        for s in SEEDS:
            folder = OUT / f"{m}_{s}"
            for row in read(folder/"run.json")["archive"]:
                paths.setdefault(row["schedule_sha256"], folder/row["file"])
    audit_dir = OUT / "row_audit"
    audit_dir.mkdir(exist_ok=True)
    todo = [p for sig,p in paths.items() if not (audit_dir/(sig+".json")).exists()]
    pool("original 24,271,470 rows",todo, audit_schedule,
         lambda item,value:save(audit_dir/(value["schedule"]+".json"),value),25)
    status(f"COMPLETE: 12 searches and {len(paths)} distinct original-row certificates")
    save(OUT/"complete.json",dict(runs=12, verified_schedules=len(paths)))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--probe",action="store_true")
    args = parser.parse_args()
    if args.probe:
        search = Search(1)
        search.admit(search.routes.warm, search.initial, time.monotonic()+60)
        for fam in range(6):
            for goal in ("A","B"):
                st = time.monotonic()
                ab = search.evaluate((fam,0,0,0),goal,None,False,st+8)
                print(fam,goal,ab,round(time.monotonic()-st,2),flush=True)
        print(search.stats,flush=True)
    else:
        run()

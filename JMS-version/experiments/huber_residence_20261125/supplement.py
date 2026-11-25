"""Verify transported bounds or solve the 54 threshold and nine structure cells."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
from score import metrics

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
PREVIOUS = HERE.parent / "residence_objective_20261125"
OLD = ROOT / "JMS-version/results/residence_objective_20261125/supplement"
OUT = OLD.parents[1] / "huber_residence_20261125/supplement"
spec = importlib.util.spec_from_file_location("threshold_archive", PREVIOUS / "supplement.py")
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)
load, save, digest, prior_checked = base.load, base.save, base.digest, base.checked


def checked(path, job):
    if not prior_checked(path, job):
        return False
    result = load(path / "result.json")
    values = metrics(load(path / "schedule.json"))
    return ("huber_penalty" in result["measured"] and
            abs(result["measured"]["secondary"] - values["secondary"]) < 2e-4)


def manifest():
    jobs = {}
    for name, row in base.cases().items():
        if name.startswith("range_"):
            continue
        _, job = base.target(name, row)
        job["settings"].update(objective="mean_plus_huber_spread_plus_actual_clean_loss", delta=1)
        job["key"] = hashlib.sha256(json.dumps(job["settings"], sort_keys=True).encode()).hexdigest()[:24]
        jobs[name] = job
    return jobs


def adopt(jobs):
    from collections import defaultdict
    old_manifest = load(OLD / "manifest.json")
    for name, job in jobs.items():
        dest = OUT / job["key"]
        if checked(dest, job):
            continue
        previous = old_manifest[name]
        for k in ("seed", "schedule", "assignment", "gap", "seconds", "range_weight", "clean_weight", "backend"):
            assert job["settings"][k] == previous["settings"][k]
        src = OLD / previous["key"]
        assert prior_checked(src, previous)
        row = load(src / "result.json")
        initial = load(ROOT / job["source"] / job["schedule"])
        recipe = {g["id"]:g["mode"] for g in initial["config"]["pjobs"]}
        pairs = defaultdict(set)
        for wafer in initial["jobs"]:
            if wafer["product"]:
                pairs[recipe[wafer["pjob"]]].add(wafer["pair"])
        correction = 0 if all(len(group)==1 for group in pairs.values()) else .5
        value = metrics(load(src / "schedule.json"))
        upper = value["secondary"]
        lower = max(0, row["record"]["lower"] - correction)
        assert lower <= upper + 2e-5
        lower = min(upper, lower)
        gap = (upper-lower)/max(1e-10, lower)
        if gap > job["settings"]["gap"] + 1e-8:
            continue
        row.update(initial=metrics(initial), measured=value, eligible=True,
                   reuse=dict(source=str(src.relative_to(ROOT)), result_sha256=digest(src/"result.json"),
                              maximum_reduction=correction, original_lower=row["record"]["lower"],
                              historical_solver_seconds=row["record"]["seconds"]))
        row["record"].update(status="verified_transferred_bound", lower=lower, upper=upper, gap=gap,
                             seconds=0, wall_seconds=0, cumulative_wall_s=0, cumulative_solver_s=0)
        dest.mkdir(exist_ok=True)
        for file in row["files"]:
            shutil.copyfile(src/file, dest/file)
        save(dest/"result.json", row)
        assert checked(dest, job)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jobs", type=int, default=2)
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    jobs = manifest()
    adopt(jobs)
    base.checked = checked
    base.controller(OUT, jobs, args.jobs, HERE/"supplement_worker.py")

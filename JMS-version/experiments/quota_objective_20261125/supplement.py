"""Threshold grid and fixed-structure results for the mean-plus-quota objective."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
PREVIOUS = HERE.parent / "residence_objective_20261125"
OLD = ROOT / "JMS-version/results/residence_objective_20261125/supplement"
OUT = ROOT / "JMS-version/results/quota_objective_20261125/supplement"
spec = importlib.util.spec_from_file_location("archived_threshold_runner", PREVIOUS / "supplement.py")
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)
load, save, digest = base.load, base.save, base.digest


def checked(path, job):
    if not base.checked(path, job):
        return False
    result = load(path / "result.json")
    return result.get("objective_definition", "all_chambers_terminal_quota") == "all_chambers_terminal_quota"


def manifest():
    jobs = {}
    for name, row in base.cases().items():
        if name.startswith("range_"):
            continue
        _, data = base.target(name, row)
        data["settings"].update(range_weight=0, clean_weight=1, objective="mean_plus_all_chambers_terminal_quota")
        data["key"] = hashlib.sha256(json.dumps(data["settings"], sort_keys=True).encode()).hexdigest()[:24]
        jobs[name] = data
    return jobs


def adopt_mean_optima(out, jobs):
    from score import metrics
    archived = load(OLD / "manifest.json")
    for name, job in jobs.items():
        if not name.startswith("structure_") or checked(out / job["key"], job):
            continue
        raw = archived[f"range_0__s{job['settings']['seed']}"]
        if any(raw["settings"][k] != job["settings"][k] for k in ("schedule", "assignment", "seed", "seconds", "backend")):
            continue
        src = OLD / raw["key"]
        if not base.checked(src, raw):
            continue
        r = load(src / "result.json")
        if r["record"]["status"] != "optimal" or abs(r["record"]["upper"]-r["record"]["lower"]) > 1e-6:
            continue
        obj = metrics(load(src / "schedule.json"), 0, 1)
        original = metrics(load(ROOT / job["source"] / job["schedule"]), 0, 1)
        delta = obj["secondary"] - r["measured"]["secondary"]
        if abs(original["secondary"] - r["initial"]["secondary"] - delta) > 1e-6:
            raise ValueError("Quota is not fixed throughout this handoff")
        r["initial"], r["measured"] = original, obj
        r["record"].update(lower=r["record"]["lower"] + delta, upper=r["record"]["upper"] + delta,
                           gap=0, status="certified_fixed_offset_reuse")
        r["objective_definition"] = "all_chambers_terminal_quota"
        r["reuse"] = {"source":str(src.relative_to(ROOT)), "source_sha256":digest(src / "result.json"),
                      "offset":delta, "reason":"Same handoff hashes and fixed production and cleaning cycles. The archived zero-range-weight objective differs by a known constant."}
        target = out / job["key"]
        target.mkdir(parents=True, exist_ok=True)
        for filename in r["files"]:
            shutil.copyfile(src / filename, target / filename)
        save(target / "result.json", r)
        if not checked(target, job):
            raise ValueError(name)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jobs", type=int, default=2)
    args = parser.parse_args()
    rows = manifest()
    OUT.mkdir(parents=True, exist_ok=True)
    adopt_mean_optima(OUT, rows)
    base.controller(OUT, rows, args.jobs, HERE / "supplement_worker.py")

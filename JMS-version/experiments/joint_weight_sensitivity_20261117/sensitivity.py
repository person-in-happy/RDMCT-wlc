"""Read-only planning and isolated weight extensions of the frozen table-4 experiment."""
from __future__ import annotations

import argparse
import importlib.util
import json
import math
import os
from pathlib import Path
import statistics

HERE = Path(__file__).resolve().parent
BASE_ENTRY = HERE.parent / "finite_budget_20261116/finite_budget.py"
RESUME_ENTRY = HERE.parent / "formal_ablation_resume_20261117/resume.py"


def module(name, path):
    loader = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(loader)
    loader.loader.exec_module(result)
    return result


f = module("weight_base", BASE_ENTRY)
r = module("weight_resume", RESUME_ENTRY)
r.f = f
ROOT, JMS = f.ROOT, f.JMS
BASE = JMS / "results/finite_budget_20261116_r1"
DEFAULT = JMS / "results/joint_weight_sensitivity_20261117_r1"
CASES = ("D_n4_mixed", "D_n16_4x1", "E_n16_2x2")
WEIGHTS = (0.0001, 0.0005, 0.001, 10.0, 100.0)
OLD_REPORT = f.report
OLD_INVENTORY = f.inventory
OLD_FOREIGN = f.foreign_research_workers


def checked_weights(values):
    weights = tuple(float(v) for v in values)
    if not weights or any(not math.isfinite(v) or v <= 0 for v in weights):
        raise ValueError("Weights must be finite and positive")
    names = [format(v, ".12g") for v in weights]
    if len(set(names)) != len(names):
        raise ValueError("Duplicate weights")
    if any(v in (0.01, 0.1, 1.0) for v in weights):
        raise ValueError("Reuse the existing 0.01/0.1/1 results; do not repeat them in this extension")
    return weights


def make_cells(cases, weights):
    cells = []
    for case in cases:
        for seed in (1, 2, 3):
            for weight in checked_weights(weights):
                arm = "joint_" + format(weight, ".12g")
                cells.append(dict(case=case["case"], backend=case["backend"], suite="objectives",
                                  seed=seed, training_seed=1, method="scip", arm=arm, budget=300.0,
                                  id=f'{case["case"]}__objectives__s{seed}__{arm}'))
    return cells


def make_plan(weights):
    """Read hashes/configuration only: no model construction, optimizer, or output directory."""
    weights = checked_weights(weights)
    source = f.checked(BASE)
    cases = [c for c in source["cases"] if c["case"] in CASES]
    if {c["case"] for c in cases} != set(CASES):
        raise ValueError("Missing table-4 source case")
    cells = make_cells(cases, weights)
    return dict(action="plan_only", solver_started=False, source_campaign=str(BASE),
                source_campaign_sha256=f.sha(BASE / "campaign.json"), weights=list(weights),
                cases=[dict(case=c["case"], backend=c["backend"], scales=c["scales"],
                            source_assignment_sha256=f.sha(c["values"])) for c in cases],
                seeds=[1, 2, 3], total_budget_seconds=300, cells=len(cells),
                nominal_solver_hours=sum(c["budget"] for c in cells) / 3600,
                reference="Reuse original same-seed two-stage results, same normalization and original input; no N=2 case",
                waiting="Run waits for existing experiment controllers and workers; Plan/Prepare do not start solvers")


def inventory():
    paths = [Path(__file__), HERE / "control.ps1", HERE / "README_CN.txt", HERE / "test_sensitivity.py", RESUME_ENTRY]
    return OLD_INVENTORY() | {str(p.relative_to(ROOT)): f.sha(p) for p in paths}


def prepare(out, weights):
    plan = make_plan(weights)
    old = f.checked(BASE)
    selected = [c for c in old["cases"] if c["case"] in CASES]
    f.source_records = lambda: [{k: c[k] for k in ("case", "backend", "source", "values")} for c in selected]
    f.make_cells = lambda cases: make_cells(cases, weights)
    f.inventory = inventory
    f.prepare(out)
    spec = f.read(out / "campaign.json")
    for case in spec["cases"]:
        original = next(c for c in selected if c["case"] == case["case"])
        if any(case[k] != original[k] for k in ("config", "scales", "input_metrics", "values", "source")):
            raise ValueError("Input/normalization drift relative to table 4")
    references = []
    for case in selected:
        for seed in (1, 2, 3):
            directory = BASE / "runs" / f'{case["case"]}__objectives__s{seed}__two_stage'
            evidence = f.read(directory / "evidence.json")
            if not evidence["valid"] or not evidence["budget_eligible"]:
                raise ValueError("Existing two-stage reference is ineligible")
            if f.sha(directory / "result.json") != evidence["result_sha256"] or f.sha(directory / "variables.json") != evidence["assignment_sha256"]:
                raise ValueError("Existing reference hash mismatch")
            for leaf in ("evidence.json", "result.json", "variables.json"):
                spec["sources"][str(directory / leaf)] = f.sha(directory / leaf)
            references.append(dict(case=case["case"], seed=seed, evidence=str(directory / "evidence.json")))
    spec["sources"][str(BASE / "campaign.json")] = f.sha(BASE / "campaign.json")
    spec.update(weights=list(weights), supplement="table_4_weight_sensitivity", source_campaign=str(BASE),
                reference_two_stage=references,
                selection="All three current table-4 cases, seeds 1/2/3, every declared new weight; no selection by result and no N=2 instance",
                inference="Same original inputs, backends, solver settings, fixed normalization and 300-second nominal budget as table 4. Reuse existing paired two-stage references. Preserve every win/tie/loss, failure and budget exclusion. A weighted-objective dual bound is not an A bound.",
                sensitivity_rationale="Existing valid N=4 candidates (541,1694) and (542,499) exchange scalar ordering near rho=0.00077043; this is a known-candidate preference crossing, not a guarantee of solver discovery. For both N=16 cases the available two-stage candidate dominates the unchanged joint input for every positive rho.")
    # This is still preparation: finalize the isolated manifest before any worker exists.
    f.dump(out / "campaign.json", spec)
    f.dump(out / "contract.json", dict(campaign_sha256=f.sha(out / "campaign.json")))
    f.dump(out / "prepared_plan.json", plan)
    report(out)
    print(f'FROZEN {len(spec["cells"])} new-weight runs; no solver started', flush=True)


def report(out):
    coverage = OLD_REPORT(out)
    spec = f.checked(out, full=False)
    if "reference_two_stage" not in spec:
        return coverage
    rows = {row["id"]: row for row in f.read(out / "summary/rows.json")}
    refs = {(ref["case"], ref["seed"]): f.read(ref["evidence"]) for ref in spec["reference_two_stage"]}
    groups = {}
    for cell in spec["cells"]:
        group = groups.setdefault((cell["case"], cell["arm"]), [])
        row = rows.get(cell["id"])
        ref = refs[cell["case"], cell["seed"]]
        if row and row["valid"] and row["budget_eligible"] and ref["valid"] and ref["budget_eligible"]:
            group.append(dict(seed=cell["seed"], joint=row["metrics"], two_stage=ref["metrics"]))
    result = []
    for (case, arm), pairs in sorted(groups.items()):
        record = dict(case=case, weight=float(arm.split("_", 1)[1]), expected=3,
                      paired=len(pairs), complete=len(pairs) == 3, pairs=pairs)
        if pairs:
            for method in ("joint", "two_stage"):
                record[method + "_mean"] = {key: statistics.mean(p[method][key] for p in pairs)
                                            for key in ("cmax", "secondary", "wait_sum", "wait_max", "rhythm", "rhythm_centers")}
        result.append(record)
    f.dump(out / "summary/paired_with_existing_two_stage.json", result)
    return coverage


def process_role(args, out):
    try:
        i = args.index("--campaign")
        if Path(args[i + 1]).resolve() != out.resolve():
            return None
    except (ValueError, IndexError, OSError):
        return None
    for i, arg in enumerate(args[:-1]):
        try:
            path = Path(arg).resolve()
        except (ValueError, OSError):
            continue
        if path == BASE_ENTRY.resolve() and args[i + 1] == "worker":
            return "worker"
        if path == Path(__file__).resolve() and args[i + 1] in ("run", "resume"):
            return "resume"
    return None


def active_processes(out):
    import psutil
    found = []
    for p in psutil.process_iter(["pid", "name", "cmdline", "create_time"]):
        if p.pid == os.getpid() or "python" not in (p.info["name"] or "").lower():
            continue
        role = process_role(p.info["cmdline"] or [], out)
        if role:
            found.append(dict(pid=p.pid, role=role, create_time=p.info["create_time"]))
    return found


def foreign_workers(own):
    import psutil
    found = set(OLD_FOREIGN(own))
    for p in psutil.process_iter(["pid", "name", "cmdline"]):
        if p.pid in own or "python" not in (p.info["name"] or "").lower():
            continue
        command = " ".join(p.info["cmdline"] or []).lower()
        if any(token in command for token in ("formal_ablation", "finite_budget.py", "readiness.py", "sensitivity.py")):
            found.add(p.pid)
    return sorted(found)


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("action", choices=("plan", "prepare", "run", "resume", "stop", "status", "report"))
    parser.add_argument("--campaign", default=str(DEFAULT))
    parser.add_argument("--weights", nargs="+", type=float)
    args = parser.parse_args()
    out = Path(args.campaign).resolve()
    root = (JMS / "results").resolve()
    if not out.is_relative_to(root) or out == root:
        parser.error("Use an isolated results directory")
    if args.weights is not None and args.action not in ("plan", "prepare"):
        parser.error("Weights are frozen during Prepare; Run/Resume cannot change them")
    weights = checked_weights(WEIGHTS if args.weights is None else args.weights)
    f.report = report
    f.foreign_research_workers = foreign_workers
    r.active_processes = active_processes
    r.INTERRUPTIONS = r.INTERRUPTIONS | {"new_worker_RAM_guard"}
    if args.action == "plan":
        print(json.dumps(make_plan(weights), ensure_ascii=False, indent=2))
    elif args.action == "prepare":
        prepare(out, weights)
    elif args.action in ("run", "resume"):
        r.resume(out)
    elif args.action == "stop":
        r.stop(out)
    elif args.action == "report":
        f.checked(out)
        print(json.dumps(report(out), ensure_ascii=False))
    else:
        f.checked(out, full=False)
        live = out / "live_status.json"
        print(json.dumps(dict(processes=active_processes(out), progress=f.read(live) if live.exists() else None), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

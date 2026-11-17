"""Isolated, non-learning search-readiness pilot; never select by policy wins."""
from pathlib import Path
import argparse
import copy
import importlib.util
import json
import re
import shutil

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
OLD = ROOT / "JMS-version/results/finite_budget_20261116_r1"
ENTRY = ROOT / "JMS-version/experiments/finite_budget_20261116/finite_budget.py"
imp = importlib.util.spec_from_file_location("existing_finite_budget", ENTRY)
base = importlib.util.module_from_spec(imp)
imp.loader.exec_module(base)
# The unchanged supervisor launches this wrapper for workers. Frozen old code stays intact.
base.__file__ = str(Path(__file__).resolve())


def classify(valid, budget_eligible, status, rounds, improvement):
    if not valid or not budget_eligible:
        return "invalid_or_overbudget"
    if status == "optimal":
        return "optimal_control_only"
    if rounds <= 0:
        return "no_cut_selection_opportunity"
    return "active_search_with_improvement" if improvement > 2e-4 else "cuts_active_incumbent_stagnant"


def prepare(out):
    if out.exists():
        raise FileExistsError("A fresh pilot directory is required")
    spec = copy.deepcopy(base.read(OLD / "campaign.json"))
    spec["cases"] = [c for c in spec["cases"] if c["case"] in ("D_n4_mixed", "D_n16_4x1")]
    spec["cells"] = [dict(case=c["case"], backend="D", suite="readiness", seed=17,
                          training_seed=1, method="scip", arm="primary", budget=900.,
                          id=c["case"] + "__readiness__s17__T900") for c in spec["cases"]]
    spec["created_utc"] = base.stamp()
    spec["parent"] = str(OLD)
    spec["settings"].update(max_workers=2, gpu_slots=0, threads=1)
    spec["selection"] = "Both previously stagnant N=4 and N=16 instances; seed 17; SCIP only; 900 s fixed in advance. No learned-policy performance is observed or used to qualify instances."
    spec["timing"] = "Pilot only: 900 s nominal solver budget per instance, no SPBS or stage 2; builds/load/validation separate. This does not supply a 300 s algorithm comparison."
    spec["inference"] = "Cut-separation activity establishes opportunity to test a selector, not a learned-method advantage. Stagnation and failures remain in the pilot report."
    spec["readiness_categories"] = ["invalid_or_overbudget", "optimal_control_only", "no_cut_selection_opportunity", "active_search_with_improvement", "cuts_active_incumbent_stagnant"]
    spec["sources"] = {c[key]: base.sha(c[key]) for c in spec["cases"] for key in ("source", "values")}
    for p in (Path(__file__).resolve(), HERE / "launch.ps1", HERE / "PROTOCOL_CN.md"):
        spec["assets"][str(p.relative_to(ROOT))] = base.sha(p)
    out.mkdir(parents=True)
    base.dump(out / "campaign.json", spec)
    base.dump(out / "contract.json", dict(campaign_sha256=base.sha(out / "campaign.json")))
    for path in spec["assets"]:
        target = out / "frozen_code" / path
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / path, target)
    base.report(out)
    print("PREPARED 2 baseline readiness probes; no policy comparison", flush=True)


def worker(out, cid):
    base.worker(out, cid)
    dest = out / "runs" / cid
    evidence = base.read(dest / "evidence.json")
    # The reused worker's legacy bookkeeping constant is irrelevant to this pilot.
    # Replace it with the actual predeclared stage allocation before final reporting.
    evidence["nominal_total"] = sum(s["limit"] for s in evidence["stages"])
    evidence["experiment_scope"] = "search_readiness_pilot_only"
    log = (dest / "solver.log").read_text(encoding="utf-8", errors="replace")
    rounds, cuts = [], []
    for line in log.splitlines():
        columns = line.split("|")
        if len(columns) >= 16:
            try:
                cuts.append(int(columns[10].strip()))
                rounds.append(int(columns[11].strip()))
            except ValueError:
                pass
    presolve = re.search(r"Presolving Time:\s*([\d.]+)", log)
    improvement = evidence["input_metrics"]["cmax"] - evidence["metrics"]["cmax"]
    status = evidence["stages"][0]["status"]
    opportunities = max(rounds, default=0) if max(cuts, default=0) > 0 else 0
    diagnostic = dict(case=cid.split("__")[0], seed=17, budget=900,
                      valid=evidence["valid"], budget_eligible=evidence["budget_eligible"],
                      status=status, initial_A=evidence["input_metrics"]["cmax"],
                      final_A=evidence["metrics"]["cmax"], A_improvement=improvement,
                      max_logged_separation_rounds=max(rounds, default=0),
                      max_logged_applied_cuts=max(cuts, default=0),
                      presolving_seconds=float(presolve.group(1)) if presolve else None,
                      category=classify(evidence["valid"], evidence["budget_eligible"], status,
                                        opportunities, improvement),
                      inference="SCIP-only pilot; no evidence of learned-policy advantage.")
    base.dump(dest / "evidence.json", evidence)
    base.dump(dest / "readiness.json", diagnostic)
    print("READINESS " + json.dumps(diagnostic), flush=True)


def report(out):
    coverage = base.report(out)
    rows = [base.read(p) for p in sorted((out / "runs").glob("*/readiness.json"))]
    base.dump(out / "summary/readiness.json", dict(coverage=coverage, rows=rows,
              formal_ablation_started=False, all_pilot_outcomes_retained=True))
    return coverage


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("action", choices=("prepare", "check", "run", "worker", "report"))
    p.add_argument("--campaign", type=Path, required=True)
    p.add_argument("--cell")
    a = p.parse_args()
    out = a.campaign.resolve()
    out.relative_to(ROOT / "JMS-version/results")
    if a.action == "prepare":
        prepare(out)
    elif a.action == "check":
        spec = base.checked(out)
        print(json.dumps(dict(cells=len(spec["cells"]), settings=spec["settings"], timing=spec["timing"])))
    elif a.action == "worker":
        worker(out, a.cell)
    elif a.action == "run":
        base.run(out)
        report(out)
    else:
        print(json.dumps(report(out)))

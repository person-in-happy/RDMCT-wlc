"""Plan/report one-factor gap and budget perturbations without editing the active 5% campaign.

The PowerShell controller invokes each frozen nine-cell campaign in the foreground.
This module never runs an optimizer and never writes into the reference campaign.
"""
from __future__ import annotations

import argparse
import copy
import csv
import importlib.util
import json
import math
from pathlib import Path
import shutil
import statistics
import sys

HERE = Path(__file__).resolve().parent
ENTRY = HERE.parent / "gap_two_stage_20261117/gap_two_stage.py"
loader = importlib.util.spec_from_file_location("frozen_gap_engine", ENTRY)
g = importlib.util.module_from_spec(loader)
loader.loader.exec_module(g)
f, ROOT, JMS = g.f, g.ROOT, g.JMS
DEFAULT = JMS / "results/gap_sensitivity_20261118_r2"
BASE_GAP, BASE_BUDGET = .05, 300.
METRICS = ("cmax", "secondary", "wait_sum", "wait_max", "rhythm", "rhythm_centers")


def tag(gap, budget):
    return "g" + format(100 * gap, ".10g").replace(".", "p") + "_b" + format(budget, ".10g").replace(".", "p")


def matrix(gaps, budgets):
    gaps, budgets = sorted(set([BASE_GAP, *gaps])), sorted(set([BASE_BUDGET, *budgets]))
    if any(not math.isfinite(v) or not 0 <= v < 1 for v in gaps):
        raise ValueError("Gaps are fractions in [0,1), e.g. 0.01, 0.05, 0.10")
    if any(not math.isfinite(v) or not 0 < v <= 1800 for v in budgets):
        raise ValueError("Budgets must be in (0,1800] seconds")
    points = [(v, BASE_BUDGET, "reference" if v == BASE_GAP else "gap") for v in gaps]
    points += [(BASE_GAP, v, "budget") for v in budgets if v != BASE_BUDGET]
    rows = [dict(id=tag(gap, budget), gap=gap, budget=budget, factor=factor,
                 reuse=factor == "reference", flows=9) for gap, budget, factor in points]
    if len({r["id"] for r in rows}) != len(rows):
        raise ValueError("Parameter names collide at the recorded precision")
    return rows


def reference(path):
    spec = g.checked(path)
    if spec["relative_gap"] != BASE_GAP or len(spec["cells"]) != 9 or any(c["budget"] != BASE_BUDGET for c in spec["cells"]):
        raise ValueError("Reference must be the frozen 5%, 300s nine-flow protocol")
    if {c["case"] for c in spec["cases"]} != set(g.CASES):
        raise ValueError("Reference cases changed")
    return spec


def plan(gaps, budgets, ref):
    reference(ref)
    rows = matrix(gaps, budgets)
    return dict(reference=str(ref), reference_campaign_sha256=f.sha(ref / "campaign.json"),
                members=rows, new_flows=sum(r["flows"] for r in rows if not r["reuse"]),
                reused_flows=9, expected_flows=9 * len(rows),
                new_nominal_solver_minutes=sum(r["flows"] * r["budget"] / 60 for r in rows if not r["reuse"]),
                design="One factor at a time: gap changes at 300s; budget changes at 5%. No implicit Cartesian product.",
                solver_started=False)


def prepare(out, gaps, budgets, ref):
    if out.exists():
        raise FileExistsError("Suite already exists; use Run/Resume, or a fresh Suite for different parameters")
    p = plan(gaps, budgets, ref)
    template = reference(ref)
    extra = {str(path.relative_to(ROOT)): f.sha(path) for path in
             (Path(__file__), HERE / "control.ps1", HERE / "README_CN.txt", HERE / "test_sensitivity.py")}
    assets = template["assets"] | extra
    out.mkdir(parents=True)
    for member in p["members"]:
        if member["reuse"]:
            member["campaign"] = str(ref)
        else:
            dest = out / "campaigns" / member["id"]
            member["campaign"] = str(dest)
            spec = copy.deepcopy(template)
            spec.update(created_utc=f.stamp(), relative_gap=member["gap"], assets=assets,
                        sensitivity_factor=member["factor"], source_reference=str(ref),
                        inference="All three cases and seeds 1/2/3 retained. Compare matched seeds to the 5%,300s reference. Budget perturbation is a separate computational-budget experiment, not an equal-budget algorithm win.",
                        timing=f'Total SCIP solve budget {member["budget"]:g}s; phase 2 gets max(0,total-actual primary time), with the same 1s eligibility tolerance. Build/validation excluded from solve budget but recorded in wall time.')
            for cell in spec["cells"]:
                cell["budget"] = member["budget"]
            # Never present a 600/1200s run as an equal-budget comparison with
            # the old 300s weighted-objective baselines.
            if member["budget"] != BASE_BUDGET:
                spec["references"] = []
            spec["weighted_comparison_enabled"] = member["budget"] == BASE_BUDGET
            spec["sources"][str(ref / "campaign.json")] = f.sha(ref / "campaign.json")
            f.dump(dest / "campaign.json", spec)
            f.dump(dest / "contract.json", dict(campaign_sha256=f.sha(dest / "campaign.json")))
            for rel in assets:
                target = dest / "frozen_code" / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(ROOT / rel, target)
        member["campaign_sha256"] = f.sha(Path(member["campaign"]) / "campaign.json")
    p.update(created_utc=f.stamp(), assets=assets,
             reporting="Always report completed/eligible counts, gate hits, switches, bounds/gaps, phase times, A and B, matched differences and exclusions. Unswitched valid rows remain in all-run means. First-stage-only trace diagnostics are not rerun outcomes.")
    f.dump(out / "suite.json", p)
    f.dump(out / "contract.json", dict(suite_sha256=f.sha(out / "suite.json")))
    report(out)
    print(json.dumps(dict(prepared=True, new_flows=p["new_flows"], reused_flows=9,
                         new_nominal_solver_minutes=p["new_nominal_solver_minutes"], solver_started=False), ensure_ascii=False))


def checked(out, full=True):
    spec = f.read(out / "suite.json")
    if f.sha(out / "suite.json") != f.read(out / "contract.json")["suite_sha256"]:
        raise RuntimeError("Frozen suite changed")
    if full:
        for rel, expected in spec["assets"].items():
            if f.sha(ROOT / rel) != expected:
                raise RuntimeError("Frozen source changed: " + rel)
    for member in spec["members"]:
        path = Path(member["campaign"])
        if f.sha(path / "campaign.json") != member["campaign_sha256"]:
            raise RuntimeError("Member protocol changed: " + str(path))
        g.checked(path, full=full)
    return spec


def csv_dump(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    keys = list(dict.fromkeys(k for row in rows for k in row))
    temp = path.with_suffix(".tmp")
    with temp.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=keys)
        writer.writeheader()
        writer.writerows(rows)
    temp.replace(path)


def collect(spec):
    rows = []
    for member in spec["members"]:
        path = Path(member["campaign"])
        campaign = g.checked(path, full=False)
        for cell in campaign["cells"]:
            info = g.inspect_cell(path, cell["id"])
            row = dict(variant=member["id"], factor=member["factor"], gap_target=member["gap"],
                       budget=member["budget"], case=cell["case"], seed=cell["seed"], state=info["state"],
                       eligible=False, attempt=info.get("attempt"), source_campaign=str(path))
            if info["state"] == "failed":
                row["failure_reason"] = info["failure"].get("reason")
            if info["state"] == "completed":
                e = info["evidence"]
                primary = e["stages"][0]
                row.update(eligible=bool(e["valid"] and e["budget_eligible"]),
                           quality_met=e["gate"]["quality_met"], switched=e["gate"]["switch"],
                           primary_status=primary["status"], primary_ub=primary["primal_bound"],
                           primary_lb=primary["dual_bound"], actual_primary_gap=primary["relative_gap"],
                           primary_seconds=primary["seconds"], secondary_seconds=sum(s["seconds"] for s in e["stages"][1:]),
                           switch_seconds=primary["seconds"] if e["gate"]["switch"] else None,
                           secondary_allocated_seconds=e["gate"]["remaining_seconds"] if e["gate"]["switch"] else 0.,
                           wall_seconds=e["wall_seconds"], primary_cmax=e["primary_metrics"]["cmax"],
                           primary_secondary=e["primary_metrics"]["secondary"],
                           refinement_B_gain=e["primary_metrics"]["secondary"] - e["metrics"]["secondary"],
                           **{k: e["metrics"][k] for k in METRICS})
                dest = path / "runs" / cell["id"] / "attempts" / info["attempt"]
                row["evidence_sha256"] = f.sha(dest / "evidence.json")
                resource = dest / "resources.json"
                row["peak_rss_gib"] = f.read(resource)["peak_rss_gib_sampled"] if resource.exists() else None
            rows.append(row)
    return rows


def summarize(rows):
    groups, pairs = [], []
    for variant, case in sorted({(r["variant"], r["case"]) for r in rows}):
        selected = [r for r in rows if r["variant"] == variant and r["case"] == case]
        eligible = [r for r in selected if r["eligible"]]
        row = dict(variant=variant, case=case, expected=3,
                   completed=sum(r["state"] == "completed" for r in selected), eligible=len(eligible),
                   failures=sum(r["state"] == "failed" for r in selected),
                   complete=len(eligible) == 3, gap_target=selected[0]["gap_target"], budget=selected[0]["budget"])
        row.update(gate_hits=sum(r["quality_met"] for r in eligible), switches=sum(r["switched"] for r in eligible),
                   finite_gap_count=sum(r["actual_primary_gap"] is not None for r in eligible))
        row["switch_rate_of_eligible"] = row["switches"] / len(eligible) if eligible else None
        for key in (*METRICS, "primary_seconds", "secondary_seconds", "refinement_B_gain", "wall_seconds"):
            row["mean_" + key] = statistics.mean(r[key] for r in eligible) if eligible else None
        # Conditional first-hit times must not turn non-switches into zeros.
        switched = [r for r in eligible if r["switched"]]
        row["conditional_mean_switch_seconds"] = statistics.mean(r["switch_seconds"] for r in switched) if switched else None
        groups.append(row)
    baselines = {(r["case"], r["seed"]): r for r in rows if r["factor"] == "reference"}
    for r in rows:
        if r["factor"] == "reference":
            continue
        b = baselines[r["case"], r["seed"]]
        paired = r["eligible"] and b["eligible"]
        record = dict(variant=r["variant"], factor=r["factor"], case=r["case"], seed=r["seed"],
                      paired=paired, variant_eligible=r["eligible"], reference_eligible=b["eligible"],
                      equal_budget=r["budget"] == b["budget"],
                      interpretation="Gap perturbation at equal budget" if r["factor"] == "gap" else "Extra/less computational budget; not an equal-budget algorithm win")
        if paired:
            for key in (*METRICS, "primary_seconds", "secondary_seconds"):
                record["delta_" + key] = r[key] - b[key]
            record.update(reference_switched=b["switched"], variant_switched=r["switched"],
                          delta_B_percent=100 * (r["secondary"] - b["secondary"]) / abs(b["secondary"]) if b["secondary"] != 0 else None)
        pairs.append(record)
    return groups, pairs


def diagnose(ref, gaps):
    campaign = reference(ref)
    rows = []
    for cell in campaign["cells"]:
        info = g.inspect_cell(ref, cell["id"])
        for threshold in sorted(set(gaps)):
            row = dict(case=cell["case"], seed=cell["seed"], gap_target=threshold,
                       reference_state=info["state"], diagnosis="pending_reference")
            if info["state"] == "completed":
                e = info["evidence"]
                primary = e["stages"][0]
                observed = primary["relative_gap"]
                row.update(reference_primary_gap=observed, primary_ub=primary["primal_bound"],
                           primary_lb=primary["dual_bound"], reference_primary_seconds=primary["seconds"])
                if not e["valid"] or not e["budget_eligible"]:
                    row["diagnosis"] = "reference_ineligible"
                elif primary["status"] == "optimal" or (threshold > 0 and observed is not None and observed <= threshold):
                    row["diagnosis"] = "observed_endpoint_meets_target_not_a_rerun"
                elif e["gate"]["switch"]:
                    row["diagnosis"] = "unknown_after_reference_early_switch"
                elif primary["status"] == "timelimit":
                    row["diagnosis"] = "target_not_met_on_reference_trajectory"
                else:
                    row["diagnosis"] = "uncertified_reference_stop"
            rows.append(row)
    return dict(note="Read-only reachability diagnosis of the observed 5% trajectories. It is neither a new experiment nor proof that changing a parameter must reproduce the same trajectory. No claim of different outcomes is guaranteed.", rows=rows)


def report(out, write=True):
    spec = checked(out, full=False)
    rows = collect(spec)
    summary, pairs = summarize(rows)
    coverage = dict(expected=spec["expected_flows"], new_expected=spec["new_flows"], reused_expected=9,
                    completed=sum(r["state"] == "completed" for r in rows), eligible=sum(r["eligible"] for r in rows),
                    failed=sum(r["state"] == "failed" for r in rows),
                    pending_or_running=sum(r["state"] in ("pending", "incomplete") for r in rows))
    if write:
        with g.controller_lock(out):
            f.dump(out / "summary/coverage.json", coverage)
            f.dump(out / "summary/rows.json", rows)
            f.dump(out / "summary/group_summary.json", summary)
            f.dump(out / "summary/paired_differences.json", pairs)
            f.dump(out / "summary/reference_reachability.json", diagnose(Path(spec["reference"]), [r["gap"] for r in spec["members"]]))
            for name, values in (("rows", rows), ("group_summary", summary), ("paired_differences", pairs)):
                csv_dump(out / "summary" / (name + ".csv"), values)
    return coverage


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("action", choices=("plan", "prepare", "diagnose", "members", "status", "report"))
    parser.add_argument("--suite", default=str(DEFAULT))
    parser.add_argument("--reference", default=str(g.DEFAULT))
    parser.add_argument("--gaps", type=float, nargs="+")
    parser.add_argument("--budgets", type=float, nargs="+")
    parser.add_argument("--family", choices=("all", "gap", "budget"), default="all")
    args = parser.parse_args()
    out, ref = Path(args.suite).resolve(), Path(args.reference).resolve()
    root = (JMS / "results").resolve()
    if not out.is_relative_to(root) or out == root or out == ref or out.is_relative_to(ref):
        parser.error("Use a separate results suite; never write into the reference campaign")
    if (args.gaps is not None or args.budgets is not None) and args.action not in ("plan", "prepare", "diagnose"):
        parser.error("Parameters are frozen at Prepare")
    gaps = [.01, .05, .1] if args.gaps is None else args.gaps
    budgets = [300.] if args.budgets is None else args.budgets
    if args.action == "plan":
        result = plan(gaps, budgets, ref)
    elif args.action == "prepare":
        prepare(out, gaps, budgets, ref)
        return
    elif args.action == "diagnose":
        matrix(gaps, budgets)
        result = diagnose(ref, gaps)
    elif args.action == "members":
        spec = checked(out)
        # The active/completed reference is always read-only; never launch it.
        result = [dict(**m, engine=str(ENTRY)) for m in spec["members"] if not m["reuse"]
                  and (args.family == "all" or m["factor"] == args.family)]
    elif args.action == "status":
        spec = checked(out, full=False)
        result = dict(coverage=report(out, write=False), members=[dict(id=m["id"], campaign=m["campaign"],
                      coverage=g.report(Path(m["campaign"]), write=False),
                      processes=g.processes(Path(m["campaign"]))[0]) for m in spec["members"]])
    else:
        checked(out)
        result = report(out)
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()

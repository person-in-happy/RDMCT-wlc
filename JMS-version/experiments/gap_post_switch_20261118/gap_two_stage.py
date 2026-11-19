"""Solve to a primary gap certificate, then give refinement its own 300-second limit."""
from __future__ import annotations

import argparse
import csv
from contextlib import contextmanager
from datetime import datetime, timezone
import importlib
import importlib.util
from importlib.metadata import version
import json
import math
import os
from pathlib import Path
import shutil
import statistics
import subprocess
import sys
import time
import traceback

HERE = Path(__file__).resolve().parent
BASE_ENTRY = HERE.parent / "finite_budget_20261116/finite_budget.py"
loader = importlib.util.spec_from_file_location("gap_frozen_helpers", BASE_ENTRY)
f = importlib.util.module_from_spec(loader)
loader.loader.exec_module(f)
ROOT, JMS = f.ROOT, f.JMS
BASE = JMS / "results/finite_budget_20261116_r1"
DEFAULT = JMS / "results/gap_post_switch_20261118_r1"
CASES = ("D_n4_mixed", "D_n16_4x1", "E_n16_2x2")
DEFAULT_GAPS = (.05, .01, .10)
PROTOCOL = "gap_certificate_then_independent_refinement_v1"
RECOVERABLE = {"foreground_interrupted", "orphaned_attempt", "RAM_guard", "RSS_guard", "wall_guard", "solver_resource_limit"}
GIB = 1024 ** 3


def finite(value, infinity=1e20):
    """SCIP +/-infinity sentinels must not become numerical certificates."""
    return float(value) if value is not None and math.isfinite(value) and abs(value) < infinity else None


def gate(primary, threshold, secondary_seconds):
    """The primary duration never consumes the independent refinement budget."""
    ub, lb = primary["primal_bound"], primary["dual_bound"]
    gap = primary["relative_gap"]
    bounds_ok = (ub is not None and lb is not None and lb <= ub + 1e-6)
    # These experiments minimize a positive makespan. A zero/negative lower
    # bound gives no finite relative certificate for a positive incumbent.
    computed = max(0., ub - lb) / min(abs(ub), abs(lb)) if bounds_ok and ub * lb > 0 else None
    quality = bool(bounds_ok and (primary["status"] == "optimal" or
                   (threshold > 0 and gap is not None and computed is not None and
                    gap <= threshold + 1e-10 and computed <= threshold + 1e-10)))
    resource_stop = primary["status"] not in ("optimal", "gaplimit", "timelimit")
    switched = quality and secondary_seconds > 1e-3 and not resource_stop
    reason = ("resource_or_unexpected_stop" if resource_stop else
              "target_not_met" if not quality else
              "no_refinement_budget" if not switched else "quality_certified")
    return dict(threshold=threshold, quality_met=quality, switch=switched,
                secondary_seconds=secondary_seconds, reason=reason, recomputed_gap=computed,
                definition="abs(UB-LB)/min(abs(UB),abs(LB)); global Cmax bounds")


def make_cells(cases, gaps=DEFAULT_GAPS, secondary_seconds=300., primary_seconds=0.):
    cells = [dict(id=f'{c["case"]}__s{s}__g{g * 100:.12g}__post{secondary_seconds:g}',
                  case=c["case"], backend=c["backend"], seed=s, method="scip",
                  relative_gap=g, primary_time_limit=primary_seconds or None,
                  secondary_time_limit=secondary_seconds)
             for g in gaps for c in cases for s in (1, 2, 3)]
    if len({c["id"] for c in cells}) != len(cells):
        raise ValueError("Gap settings must have distinct experiment identifiers")
    return cells


def plan(gaps=DEFAULT_GAPS, secondary_seconds=300., primary_seconds=0.):
    if not gaps or any(not math.isfinite(g) or not 0 <= g < 1 for g in gaps):
        raise ValueError("Relative gaps must be fractions in [0,1)")
    if not math.isfinite(secondary_seconds) or not 0 < secondary_seconds < 1e20:
        raise ValueError("Secondary time limit must be positive and finite")
    if not math.isfinite(primary_seconds) or not 0 <= primary_seconds < 1e20:
        raise ValueError("Primary safety limit must be nonnegative; zero means no time limit")
    original = f.checked(BASE)
    cases = [next(c for c in original["cases"] if c["case"] == name) for name in CASES]
    sources = {str(BASE / "campaign.json"): f.sha(BASE / "campaign.json")}
    for c in cases:
        for key in ("source", "values"):
            sources[c[key]] = f.sha(c[key])
    return dict(protocol=PROTOCOL, relative_gaps=list(gaps), cases=cases,
                cells=make_cells(cases, gaps, secondary_seconds, primary_seconds),
                primary_time_limit=primary_seconds or None, secondary_time_limit=secondary_seconds,
                sources=sources, original_environment=original["environment"],
                equal_budget_comparison_to_old_300s=False)


def prepare(out, gaps=DEFAULT_GAPS, secondary_seconds=300., primary_seconds=0.):
    if out.exists():
        raise FileExistsError("Use Run/Resume for this campaign, or a fresh directory for a new protocol")
    spec = plan(gaps, secondary_seconds, primary_seconds)
    packages = {name: version(name) for name in ("pyscipopt", "numpy", "psutil")}
    if any(packages[k] != spec["original_environment"]["packages"][k] for k in packages):
        raise RuntimeError("Python packages differ from the frozen comparison environment")
    paths = [BASE_ENTRY, *HERE.glob("*.py"), HERE / "control.ps1", HERE / "README_CN.txt",
             ROOT / "scip_imports.py", ROOT / "runtime_compat.py"]
    for backend in f.BACKENDS.values():
        paths.extend(backend / name for name in ("model.py", "validate.py", "physical_validate.py", "pjobs.py", "pjob_order.py", "grippers.py",
                                                "joint_pairing_model.py", "joint_chamber_cycle_model.py"))
    import psutil
    spec.update(schema=2, created_utc=f.stamp(), assets={str(p.relative_to(ROOT)): f.sha(p) for p in sorted(set(paths))},
                environment=dict(python=sys.executable, python_version=sys.version, packages=packages,
                                 ram_gib=psutil.virtual_memory().total / GIB, cpu_logical=psutil.cpu_count()),
                settings=dict(threads=1, default_workers=2, max_large_workers=1, min_available_gib=8.,
                              small_reservation_gib=4., large_reservation_gib=12., max_worker_rss_gib=16.,
                              wall_guard_seconds=None, refresh_seconds=10., solver_budget_tolerance=1.),
                timing="Primary phase runs to its gap certificate or optimality, with no default time limit or wall guard. Optional primary_time_limit is only a safety cap, never permission to switch. Secondary phase has its own secondary_time_limit (default 300s), not the remainder of a total budget; optimality may end it early. Record both phases, their sum, worker process wall time, and cumulative supervisor wall time including resource waiting. Each configured finite solver limit allows 1s soft-limit qualification tolerance.",
                objectives="Phase 1: unrestricted product-return Cmax. Phase 2 only after gap certificate: fix noncontinuous variables except sync_; cap Cmax at phase-1 value+1e-6; minimize wait_sum+10*wait_max+25*rhythm. This is conditional fixed-structure refinement, not a global lexicographic optimum.",
                reuse="Reuse only original frozen inputs and model definitions. All selected gaps, including 5%, are new runs; old total-300s outcomes are not observations of this protocol. Old weighted 300s results are not equal-budget baselines. Gap comparisons report solution quality and actual runtime together.",
                retries="Append new attempt directories only for interruption/execution failure. Keep completed timeouts, target-not-met and completed budget exclusions; never rerun them to select a better outcome. Retries start from the original frozen warm start, not a saved SCIP search tree.")
    out.mkdir(parents=True)
    f.dump(out / "campaign.json", spec)
    f.dump(out / "contract.json", dict(campaign_sha256=f.sha(out / "campaign.json")))
    for rel in spec["assets"]:
        target = out / "frozen_code" / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / rel, target)
    print(json.dumps(report(out), ensure_ascii=False))
    print(f'PREPARED {len(spec["cells"])} flows; no model built, no solver started', flush=True)


def checked(out, full=True):
    spec = f.checked(out, full=full)
    if spec.get("protocol") != PROTOCOL:
        raise ValueError("This runner accepts only the independent-refinement protocol; use a new campaign")
    if full:
        if sys.version != spec["environment"]["python_version"]:
            raise RuntimeError("Frozen Python version changed")
        for name, expected in spec["environment"]["packages"].items():
            if version(name) != expected:
                raise RuntimeError("Frozen package changed: " + name)
    return spec


def attempts(out, cid):
    return sorted((out / "runs" / cid / "attempts").glob("[0-9][0-9][0-9][0-9]"))


def inspect_cell(out, cid):
    dirs = attempts(out, cid)
    if not dirs:
        return dict(state="pending")
    last = dirs[-1]
    failure = f.read(last / "failure.json") if (last / "failure.json").exists() else None
    if failure and (not (last / "evidence.json").exists() or
                    failure.get("reason") in {"RAM_guard", "RSS_guard", "wall_guard", "solver_resource_limit"}):
        return dict(state="failed", attempt=last.name, failure=failure)
    if not (last / "evidence.json").exists():
        return dict(state="incomplete", attempt=last.name)
    ev = f.read(last / "evidence.json")
    for leaf, key in (("result.json", "result_sha256"), ("variables.json", "assignment_sha256")):
        if f.sha(last / leaf) != ev[key]:
            raise RuntimeError("Completed result changed: " + str(last / leaf))
    # A cleanup/exit exception after a complete certificate must not create a
    # second scientific observation. Retain even a completed budget exclusion.
    return dict(state="completed", attempt=last.name, evidence=ev, post_result_failure=failure)


def write_csv(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = list(dict.fromkeys(key for row in rows for key in row))
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    tmp.replace(path)


def timing_summary(out, rows):
    sessions = [f.read(p) for p in sorted((out / "sessions").glob("*.json"))]
    resources = [f.read(p) for p in (out / "runs").glob("*/attempts/*/resources.json")]
    completed = [r["evidence"] for r in rows if r["state"] == "completed"]
    recorded = sum("elapsed_wall_seconds" in s for s in sessions)
    return dict(completed_solver_seconds_sum=sum(e["solver_seconds"] for e in completed),
                completed_worker_wall_seconds_sum=sum(e["wall_seconds"] for e in completed),
                all_attempt_process_wall_seconds_sum=sum(r["wall_seconds"] for r in resources),
                timed_attempts=len(resources),
                attempts=sum(len(attempts(out, r["id"])) for r in rows),
                controller_wall_seconds=sum(s.get("elapsed_wall_seconds", 0.) for s in sessions),
                sessions=len(sessions), timed_sessions=recorded,
                scope="Controller wall time sums active Run/Resume sessions including resource waits and retries, excluding downtime between sessions. Process/solver sums add overlapping parallel jobs and are not campaign elapsed time. Running/aborted attempts lacking final records remain incomplete, never zero-duration completed runs.")


def report(out, write=True):
    spec = checked(out, full=False)
    rows = [c | inspect_cell(out, c["id"]) for c in spec["cells"]]
    done = [r for r in rows if r["state"] == "completed"]
    eligible = [r for r in done if r["evidence"]["valid"] and r["evidence"]["budget_eligible"]]
    coverage = dict(expected=len(rows), completed=len(done), failed=sum(r["state"] == "failed" for r in rows),
                    incomplete=sum(r["state"] == "incomplete" for r in rows),
                    pending=sum(r["state"] == "pending" for r in rows), budget_eligible=len(eligible),
                    quality_met=sum(r["evidence"]["gate"]["quality_met"] for r in eligible),
                    refined=sum(r["evidence"]["gate"]["switch"] for r in eligible))
    if not write:
        return coverage
    flat = []
    for row in rows:
        item = {k: row.get(k) for k in ("id", "case", "seed", "relative_gap", "primary_time_limit", "secondary_time_limit", "state", "attempt")}
        ev = row.get("evidence")
        if ev:
            first = ev["stages"][0]
            item.update(valid=ev["valid"], budget_eligible=ev["budget_eligible"],
                        quality_met=ev["gate"]["quality_met"], switched=ev["gate"]["switch"],
                        primary_status=first["status"], primary_ub=first["primal_bound"],
                        primary_lb=first["dual_bound"], primary_gap=first["relative_gap"],
                        primary_solver_seconds=first["seconds"],
                        secondary_solver_seconds=ev["stages"][1]["seconds"] if len(ev["stages"]) > 1 else None,
                        total_solver_seconds=ev["solver_seconds"], worker_wall_seconds=ev["wall_seconds"],
                        switch_wall_seconds=ev["switch_wall_seconds"], **ev["metrics"])
            resource_path = out / "runs" / row["id"] / "attempts" / row["attempt"] / "resources.json"
            item["process_wall_seconds"] = f.read(resource_path)["wall_seconds"] if resource_path.exists() else None
        flat.append(item)
    groups, pairs = [], []
    for case in CASES:
        for gap in spec["relative_gaps"]:
            group = [r for r in flat if r["case"] == case and r["relative_gap"] == gap]
            valid = [r for r in group if r.get("budget_eligible")]
            agg = dict(case=case, relative_gap=gap, expected=len(group),
                       completed=sum(r["state"] == "completed" for r in group), eligible=len(valid),
                       refined=sum(bool(r["switched"]) for r in valid))
            for name in ("cmax", "secondary", "primary_solver_seconds", "secondary_solver_seconds", "total_solver_seconds", "worker_wall_seconds"):
                values = [r[name] for r in valid if r.get(name) is not None]
                agg[name + "_mean"] = statistics.mean(values) if values else None
                agg[name + "_n"] = len(values)
            groups.append(agg)
            if gap == .05 or .05 not in spec["relative_gaps"]:
                continue
            for row in group:
                baseline = next(r for r in flat if r["case"] == case and r["seed"] == row["seed"] and r["relative_gap"] == .05)
                ok = bool(row.get("budget_eligible") and baseline.get("budget_eligible"))
                pair = dict(case=case, seed=row["seed"], relative_gap=gap, reference_gap=.05, paired=ok,
                            comparison_scope="same inputs; different gap stopping times, not equal total time")
                for name in ("cmax", "secondary", "total_solver_seconds", "worker_wall_seconds"):
                    pair["delta_" + name] = row[name] - baseline[name] if ok else None
                pairs.append(pair)
    f.dump(out / "summary/coverage.json", coverage)
    f.dump(out / "summary/rows.json", rows)
    f.dump(out / "summary/timing.json", timing_summary(out, rows))
    f.dump(out / "summary/group_summary.json", groups)
    f.dump(out / "summary/paired_gaps.json", pairs)
    write_csv(out / "summary/rows.csv", flat)
    write_csv(out / "summary/group_summary.csv", groups)
    write_csv(out / "summary/paired_gaps.csv", pairs)
    return coverage


def stage_record(m, phase, limit):
    inf = m.infinity()
    return dict(phase=phase, limit=limit, seconds=m.getSolvingTime(), status=str(m.getStatus()),
                primal_bound=finite(m.getPrimalbound(), inf), dual_bound=finite(m.getDualbound(), inf),
                relative_gap=finite(m.getGap(), inf), nodes=m.getNNodes(), solutions=m.getNSols(),
                bound_scope="global_product_Cmax" if phase == "primary" else "fixed_structure_secondary")


def start_refinement(x, values, primary_cmax, secondary_seconds):
    """Keep the old refinement feasible region; reset the primary gap limit."""
    m = x.model
    m.freeTransform()
    for v in m.getVars(transformed=False):
        if v.vtype() != "CONTINUOUS" and not v.name.startswith("sync_"):
            m.chgVarLb(v, round(values[v.name]))
            m.chgVarUb(v, round(values[v.name]))
    cap = m.addCons(x.cmax <= primary_cmax + 1e-6, name="gap_primary_cap")
    m.setObjective(x.secondary_objective, "minimize")
    m.setRealParam("limits/gap", 0.)
    m.setRealParam("limits/absgap", 0.)
    m.setRealParam("limits/time", secondary_seconds)
    return cap


def stage_overrun(stages, tolerance):
    return any(s["limit"] is not None and s["seconds"] > s["limit"] + tolerance for s in stages)


def worker(out, cid, attempt):
    started = time.monotonic()
    spec = checked(out)
    cell = next(c for c in spec["cells"] if c["id"] == cid)
    case = next(c for c in spec["cases"] if c["case"] == cell["case"])
    dest = out / "runs" / cid / "attempts" / attempt
    if not (dest / "launch.json").exists() or (dest / "evidence.json").exists():
        raise RuntimeError("Worker requires a fresh supervisor-created attempt")
    sys.path.insert(0, str(f.BACKENDS[cell["backend"]]))
    sys.path.insert(1, str(ROOT))
    backend = importlib.import_module("model")
    validate = importlib.import_module("validate").validate
    from scip_imports import scip
    f.dump(dest / "progress.json", dict(phase="building", updated_utc=f.stamp()))
    build_start = time.monotonic()
    x = backend.Integrated(backend.Config(**case["config"]))
    m = x.model
    build_seconds = time.monotonic() - build_start
    m.setIntParam("parallel/maxnthreads", 1)
    m.setIntParam("randomization/randomseedshift", cell["seed"])
    m.setLogfile(str(dest / "solver.log"))
    original = m.getVars(transformed=False)
    bounds = {v.name: (v.getLbOriginal(), v.getUbOriginal()) for v in original}

    def assignment(values):
        sol = m.createSol()
        for v in original:
            m.setSolVal(sol, v, values[v.name])
        return sol

    def physical(sol):
        data = x.result(solution=sol)
        data["validation"] = validate(data)
        if not data["validation"]["valid"]:
            raise ValueError("Independent schedule validation failed")
        return data, f.physical_metrics(data)

    def tighten_epigraphs(sol, measured):
        m.setSolVal(sol, x.cmax, measured["cmax"])
        m.setSolVal(sol, x.max_wait, measured["wait_max"])
        by_name = {v.name: v for v in original}
        for c in x.cfg.chambers:
            for q in range(2, x.Q):
                active = m.getSolVal(sol, x.keep[c, q]) > .5 and m.getSolVal(sol, x.keep[c, q - 1]) > .5
                delta = abs(m.getSolVal(sol, x.cy.start[c, q] - 2 * x.cy.start[c, q - 1] + x.cy.start[c, q - 2])) if active else 0.
                m.setSolVal(sol, by_name[f"rhythm_{c}_{q}"], delta)

    warm = assignment(f.read(case["values"])["values"])
    if not m.checkSol(warm, printreason=True, completely=True, original=True):
        raise ValueError("Frozen original assignment rejected")
    _, initial = physical(warm)
    tighten_epigraphs(warm, initial)
    if not m.checkSol(warm, printreason=True, completely=True, original=True):
        raise ValueError("Objective epigraph tightening invalidated input")
    m.addSol(warm)
    m.setObjective(x.primary_objective, "minimize")
    m.setRealParam("limits/gap", cell["relative_gap"])
    m.setRealParam("limits/absgap", 0.)
    m.setRealParam("limits/time", cell["primary_time_limit"] or 1e20)
    f.dump(dest / "input.json", dict(path=case["values"], sha256=f.sha(case["values"]), metrics=initial,
                                    normalization=case["scales"], build_seconds=build_seconds,
                                    variables=m.getNVars(), constraints=m.getNConss(),
                                    primary_time_limit=cell["primary_time_limit"], secondary_time_limit=cell["secondary_time_limit"],
                                    clock_type=m.getParam("timing/clocktype"), native_memory_limit_mb=m.getParam("limits/memory")))
    phase, trace = "primary", []
    class Progress(scip.Eventhdlr):
        last = -100.
        mask = scip.SCIP_EVENTTYPE.BESTSOLFOUND | scip.SCIP_EVENTTYPE.DUALBOUNDIMPROVED | scip.SCIP_EVENTTYPE.NODESOLVED
        def eventinit(self):
            self.model.catchEvent(self.mask, self)
        def eventexit(self):
            self.model.dropEvent(self.mask, self)
        def eventexec(self, event):
            now = time.monotonic()
            if now - self.last >= 2:
                row = dict(phase=phase, solver_seconds=m.getSolvingTime(), worker_wall_seconds=time.monotonic() - started,
                           primal_bound=finite(m.getPrimalbound()), dual_bound=finite(m.getDualbound()),
                           relative_gap=finite(m.getGap()), updated_utc=f.stamp())
                trace.append(row)
                f.dump(dest / "progress.json", row)
                self.last = now
    m.includeEventhdlr(Progress(), "gap_progress", "bounded progress sampling")
    f.dump(dest / "progress.json", dict(phase=phase, updated_utc=f.stamp()))
    m.optimize()
    stages = [stage_record(m, phase, cell["primary_time_limit"])]
    primary_finished_wall_seconds = time.monotonic() - started
    if not m.getNSols():
        raise ValueError("SCIP lost the validated warm start")
    best = m.getBestSol()
    first_data, first_metrics = physical(best)
    values = {v.name: m.getSolVal(best, v) for v in original}
    first_data["solver_record"] = stages[0]
    f.dump(dest / "phase1.json", first_data)
    f.dump(dest / "variables_phase1.json", dict(values=values))
    decision = gate(stages[0], cell["relative_gap"], cell["secondary_time_limit"])
    f.dump(dest / "gate.json", decision)
    cap, switch_wall_seconds = None, None
    if decision["switch"]:
        switch_wall_seconds = time.monotonic() - started
        phase = "secondary"
        cap = start_refinement(x, values, first_metrics["cmax"], decision["secondary_seconds"])
        warm = assignment(values)
        # Phase 1 did not minimize these epigraphs. Tighten them to the actual
        # unchanged schedule so a secondary timeout cannot accept a worse B.
        tighten_epigraphs(warm, first_metrics)
        if not m.checkSol(warm, printreason=True, completely=True, original=True):
            raise ValueError("First-stage assignment rejected by restricted refinement")
        m.addSol(warm)
        f.dump(dest / "progress.json", dict(phase=phase, updated_utc=f.stamp()))
        m.optimize()
        stages.append(stage_record(m, phase, decision["secondary_seconds"]))
        if not m.getNSols():
            raise ValueError("Refinement lost the validated primary assignment")
        values = {v.name: m.getSolVal(m.getBestSol(), v) for v in original}
    # Validate again against the original unrestricted model, not only the
    # reduced stage-2 model. Preserve the first-stage certificate separately.
    m.freeTransform()
    if cap is not None:
        m.delCons(cap)
    for v in original:
        lb, ub = bounds[v.name]
        m.chgVarLb(v, lb)
        m.chgVarUb(v, ub)
    m.setObjective(x.primary_objective, "minimize")
    final = assignment(values)
    valid = bool(m.checkSol(final, printreason=True, completely=True, original=True))
    data, metrics = physical(final)
    if not valid:
        raise ValueError("Final original-model feasibility check failed")
    if metrics["cmax"] > first_metrics["cmax"] + 2e-4:
        raise ValueError("Final schedule worsened the primary objective")
    if decision["switch"] and metrics["secondary"] > first_metrics["secondary"] + 2e-3:
        raise ValueError("Refinement worsened the actual secondary metric")
    total = sum(s["seconds"] for s in stages)
    overrun = stage_overrun(stages, spec["settings"]["solver_budget_tolerance"])
    resource = any(s["status"] not in ("optimal", "gaplimit", "timelimit") for s in stages)
    data.update(original_model_check=valid, experiment_scope="gap_gated_fixed_structure_refinement",
                global_lexicographic_optimality_claim=False, primary_certificate=stages[0], gate=decision)
    f.dump(dest / "result.json", data)
    f.dump(dest / "variables.json", dict(values=values))
    f.dump(dest / "trace.json", trace)
    f.dump(dest / "evidence.json", dict(valid=valid, budget_eligible=valid and not overrun and not resource,
           metrics=metrics, primary_metrics=first_metrics, input_metrics=initial, stages=stages, gate=decision,
           solver_seconds=total, nominal_total=None, primary_time_limit=cell["primary_time_limit"],
           secondary_time_limit=cell["secondary_time_limit"], primary_solver_seconds=stages[0]["seconds"],
           secondary_solver_seconds=stages[1]["seconds"] if len(stages) > 1 else None,
           switch_wall_seconds=switch_wall_seconds, primary_finished_wall_seconds=primary_finished_wall_seconds,
           stage_overrun=overrun, resource_interruption=resource, equal_budget_comparison_to_old_300s=False,
           completed_utc=f.stamp(), wall_seconds=time.monotonic() - started, build_seconds=build_seconds,
           result_sha256=f.sha(dest / "result.json"), assignment_sha256=f.sha(dest / "variables.json"),
           source_assignment_sha256=f.sha(case["values"]), campaign_sha256=f.sha(out / "campaign.json")))
    m.freeSol(final)
    m.setLogfile(None)
    m.freeProb()
    if resource:
        f.dump(dest / "failure.json", dict(reason="solver_resource_limit", completed_utc=f.stamp()))
    print("COMPLETE " + cid + " " + json.dumps(dict(metrics=metrics, gate=decision)), flush=True)


def process_role(args, out):
    try:
        if Path(args[args.index("--campaign") + 1]).resolve() != out.resolve():
            return None
        for i, arg in enumerate(args[:-1]):
            if Path(arg).resolve() == Path(__file__).resolve() and args[i + 1] in ("run", "resume", "worker"):
                return args[i + 1]
    except (ValueError, IndexError, OSError):
        pass
    return None


def processes(out, own=()):
    import psutil
    same, foreign = [], []
    tokens = ("finite_budget", "formal_ablation", "s1_ablation", "sensitivity.py", "gap_two_stage.py",
              "readiness.py", "thesis_parallel", "large_schedule_experiments", "journal_support_experiments",
              "journal_gap_experiments", "paper_defaults.py", "run_cie_benchmarks.py", "run_experiments.py", "revalidate.py")
    for p in psutil.process_iter(["pid", "name", "cmdline", "create_time"]):
        if p.pid == os.getpid() or p.pid in own or "python" not in (p.info["name"] or "").lower():
            continue
        args = p.info["cmdline"] or []
        role = process_role(args, out)
        if role:
            same.append(dict(pid=p.pid, role=role, create_time=p.info["create_time"]))
        elif any(token in " ".join(args).lower() for token in tokens):
            foreign.append(p.pid)
    return same, foreign


@contextmanager
def controller_lock(out):
    """OS-held byte lock: released on crash; no stale-PID deletion race."""
    lock = (out / "controller.lock").open("a+b")
    if lock.tell() == 0:
        lock.write(b"0")
        lock.flush()
    lock.seek(0)
    try:
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        lock.close()
        raise RuntimeError("Another controller owns this campaign")
    try:
        yield
    finally:
        lock.seek(0)
        if os.name == "nt":
            msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            fcntl.flock(lock, fcntl.LOCK_UN)
        lock.close()


def retryable(info, explicit=False):
    if info["state"] in ("pending", "incomplete"):
        return True
    return info["state"] == "failed" and (explicit or info["failure"].get("reason") in RECOVERABLE)


def reservation(cell, settings):
    return settings["large_reservation_gib" if "n16" in cell["case"] else "small_reservation_gib"]


def can_launch(cell, active, available_gib, settings, max_workers):
    if len(active) >= max_workers:
        return False
    if "n16" in cell["case"] and any("n16" in a["cell"]["case"] for a in active):
        return False
    growth = sum(max(0., reservation(a["cell"], settings) - a["rss_gib"]) for a in active)
    return available_gib >= settings["min_available_gib"] + reservation(cell, settings) + growth


def stop_own(task):
    p = task["process"]
    if p.poll() is None:
        p.terminate()
        try:
            p.wait(timeout=10)
        except subprocess.TimeoutExpired:
            p.kill()
            p.wait(timeout=10)


def supervise(out, spec, max_workers, retry_failed, selected):
    import psutil
    same, _ = processes(out)
    if same:
        raise RuntimeError("Campaign processes already active; no duplicate launch: " + json.dumps(same))
    settings = spec["settings"]
    selected = set(selected or [c["id"] for c in spec["cells"]])
    unknown = selected - {c["id"] for c in spec["cells"]}
    if unknown:
        raise ValueError("Unknown cells: " + str(sorted(unknown)))
    pending = []
    for cell in spec["cells"]:
        info = inspect_cell(out, cell["id"])
        if cell["id"] in selected and retryable(info, retry_failed):
            if info["state"] == "incomplete":
                f.dump(out / "runs" / cell["id"] / "attempts" / info["attempt"] / "failure.json",
                       dict(reason="orphaned_attempt", detected_utc=f.stamp()))
            pending.append(cell)
    active, completed_durations, last = {}, [], -100.
    session = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S_%fZ")
    session_start = time.monotonic()
    session_path = out / "sessions" / (session + ".json")
    session_data = dict(created_utc=f.stamp(), pid=os.getpid(), elapsed_wall_seconds=0.,
                        max_workers=max_workers, retry_failed=retry_failed,
                        selected=sorted(selected), pending=[c["id"] for c in pending])
    f.dump(session_path, session_data)
    try:
        while pending or active:
            for cid, task in list(active.items()):
                elapsed = time.monotonic() - task["started"]
                if task["process"].poll() is None:
                    try:
                        rss = psutil.Process(task["process"].pid).memory_info().rss / GIB
                    except psutil.NoSuchProcess:
                        rss = 0.
                    task["rss_gib"] = rss
                    task["peak_rss_gib"] = max(task["peak_rss_gib"], rss)
                    reason = ("RAM_guard" if psutil.virtual_memory().available / GIB < settings["min_available_gib"] else
                              "RSS_guard" if rss > settings["max_worker_rss_gib"] else
                              "wall_guard" if settings["wall_guard_seconds"] is not None and elapsed > settings["wall_guard_seconds"] else None)
                    if reason:
                        task["reason"] = reason
                        stop_own(task)
                if task["process"].poll() is not None:
                    task["log"].close()
                    dest = task["dest"]
                    if task.get("reason") or task["process"].returncode != 0 or not (dest / "evidence.json").exists():
                        if not (dest / "failure.json").exists():
                            f.dump(dest / "failure.json", dict(reason=task.get("reason", "worker_exit"),
                                   exit_code=task["process"].returncode, ended_utc=f.stamp()))
                    f.dump(dest / "resources.json", dict(peak_rss_gib_sampled=task["peak_rss_gib"],
                           wall_seconds=elapsed, max_workers=max_workers, exit_code=task["process"].returncode))
                    state = inspect_cell(out, cid)
                    if state["state"] == "completed":
                        completed_durations.append(elapsed)
                    print(f'END {cid} state={state["state"]}', flush=True)
                    del active[cid]
                    report(out)
            _, foreign = processes(out, [a["process"].pid for a in active.values()])
            reason = "external_experiment_wait" if foreign else "RAM_or_large_slot_wait"
            for cell in list(pending):
                if foreign:
                    break
                if not can_launch(cell, list(active.values()), psutil.virtual_memory().available / GIB, settings, max_workers):
                    continue
                cid = cell["id"]
                old = attempts(out, cid)
                number = f'{(int(old[-1].name) + 1) if old else 1:04d}'
                dest = out / "runs" / cid / "attempts" / number
                dest.mkdir(parents=True, exist_ok=False)
                env = os.environ.copy()
                env.update(OMP_NUM_THREADS="1", MKL_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1", PYTHONUNBUFFERED="1")
                command = [sys.executable, "-X", "utf8", "-u", str(Path(__file__).resolve()), "worker",
                           "--campaign", str(out), "--cell", cid, "--attempt", number]
                log = (dest / "console.log").open("w", encoding="utf-8")
                f.dump(dest / "launch.json", dict(command=command, created_utc=f.stamp(), max_workers=max_workers,
                       active_before=list(active), available_gib=psutil.virtual_memory().available / GIB,
                       thread_environment={k: env[k] for k in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS")}))
                try:
                    process = subprocess.Popen(command, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
                except BaseException:
                    log.close()
                    raise
                active[cid] = dict(process=process, cell=cell, dest=dest, log=log, started=time.monotonic(),
                                   rss_gib=0., peak_rss_gib=0.)
                pending.remove(cell)
                print(f'START {cid} attempt={number}', flush=True)
                reason = "running"
            if time.monotonic() - last >= settings["refresh_seconds"]:
                session_data.update(elapsed_wall_seconds=time.monotonic() - session_start, updated_utc=f.stamp())
                f.dump(session_path, session_data)
                coverage = report(out)
                typical = statistics.mean(completed_durations) if completed_durations else None
                count = len(pending) + len(active)
                large = sum("n16" in c["case"] for c in pending) + sum("n16" in a["cell"]["case"] for a in active.values())
                eta = max(count / max_workers, large) * typical if typical is not None else None
                progress = {}
                for cid, a in active.items():
                    path = a["dest"] / "progress.json"
                    progress[cid] = (f.read(path) if path.exists() else dict(phase="loading")) | dict(rss_gib=a["rss_gib"], process_wall_seconds=time.monotonic() - a["started"])
                state = coverage | dict(updated_utc=f.stamp(), supervisor_pid=os.getpid(), active=progress,
                    available_gib=psutil.virtual_memory().available / GIB, state=reason, foreign_pids=foreign,
                    session_wall_seconds=session_data["elapsed_wall_seconds"],
                    estimated_remaining_minutes=eta / 60. if eta is not None else None,
                    eta_note="No finite initial ETA: primary phase has no time cap. Later estimate uses observed completed runs, with different case/gap difficulty; convergence and external/resource waiting times are unknown. Large jobs serialized.")
                f.dump(out / "live_status.json", state)
                eta_text = f'{eta/60:.1f}min (observed estimate)' if eta is not None else 'unknown (primary gap not reached)'
                print(f'complete={coverage["completed"]}/{coverage["expected"]} failed={coverage["failed"]} running={len(active)} '
                      f'left={len(pending)} RAM={state["available_gib"]:.1f}GiB elapsed={state["session_wall_seconds"]/60:.1f}min ETA={eta_text} {reason}', flush=True)
                for cid, info in progress.items():
                    print("  " + cid + " " + json.dumps(info), flush=True)
                last = time.monotonic()
            if pending or active:
                time.sleep(1)
    finally:
        for task in active.values():
            stop_own(task)
            task["log"].close()
            f.dump(task["dest"] / "resources.json", dict(peak_rss_gib_sampled=task["peak_rss_gib"],
                   wall_seconds=time.monotonic() - task["started"], max_workers=max_workers,
                   exit_code=task["process"].returncode, interrupted=True))
            if not (task["dest"] / "evidence.json").exists():
                f.dump(task["dest"] / "failure.json", dict(reason="foreground_interrupted", ended_utc=f.stamp()))
        session_data.update(elapsed_wall_seconds=time.monotonic() - session_start, ended_utc=f.stamp())
        f.dump(session_path, session_data)
        coverage = report(out)
        f.dump(out / "last_session.json", coverage | dict(ended_utc=f.stamp(), session=session))
    print("FINISHED " + json.dumps(coverage), flush=True)
    return 1 if coverage["failed"] or coverage["incomplete"] else 0


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("action", choices=("plan", "prepare", "run", "resume", "status", "report", "worker"))
    parser.add_argument("--campaign", default=str(DEFAULT))
    parser.add_argument("--gaps", type=float, nargs="+")
    parser.add_argument("--secondary-seconds", type=float)
    parser.add_argument("--primary-seconds", type=float, help="Optional safety limit; default 0 means no primary time limit")
    parser.add_argument("--max-workers", type=int, choices=(1, 2), default=2)
    parser.add_argument("--retry-failed", action="store_true")
    parser.add_argument("--cells", nargs="+")
    parser.add_argument("--cell")
    parser.add_argument("--attempt")
    args = parser.parse_args()
    out = Path(args.campaign).resolve()
    root = (JMS / "results").resolve()
    if not out.is_relative_to(root) or out == root or out == BASE:
        parser.error("Use a separate subdirectory of JMS-version/results")
    if any(v is not None for v in (args.gaps, args.secondary_seconds, args.primary_seconds)) and args.action not in ("plan", "prepare"):
        parser.error("Gaps and stage limits are frozen at Prepare; use a fresh campaign to change them")
    settings = (DEFAULT_GAPS if args.gaps is None else args.gaps,
                300. if args.secondary_seconds is None else args.secondary_seconds,
                0. if args.primary_seconds is None else args.primary_seconds)
    if args.action == "plan":
        spec = plan(*settings)
        print(json.dumps(dict(protocol=spec["protocol"], gaps=spec["relative_gaps"],
              cells=len(spec["cells"]), cases=CASES, seeds=[1, 2, 3],
              primary_time_limit=spec["primary_time_limit"], secondary_time_limit=spec["secondary_time_limit"],
              total_solver_time_limit=None, old_total300_results_reused=False,
              equal_budget_comparison_to_old_300s=False, solver_started=False), ensure_ascii=False, indent=2))
    elif args.action == "prepare":
        prepare(out, *settings)
    elif args.action in ("run", "resume"):
        spec = checked(out)
        with controller_lock(out):
            return supervise(out, spec, args.max_workers, args.retry_failed, args.cells)
    elif args.action == "worker":
        spec = checked(out, full=False)
        if args.cell not in {c["id"] for c in spec["cells"]} or not args.attempt or not (len(args.attempt) == 4 and args.attempt.isdigit()):
            parser.error("Invalid worker cell/attempt")
        try:
            worker(out, args.cell, args.attempt)
        except BaseException as exc:
            f.dump(out / "runs" / args.cell / "attempts" / args.attempt / "failure.json",
                   dict(reason="worker_exception", message=str(exc), traceback=traceback.format_exc(), ended_utc=f.stamp()))
            raise
    elif args.action == "status":
        same, foreign = processes(out)
        print(json.dumps(dict(coverage=report(out, write=False), processes=same, external_experiment_pids=foreign,
                         latest_progress=f.read(out / "live_status.json") if (out / "live_status.json").exists() else None),
                         ensure_ascii=False, indent=2))
    else:
        checked(out)
        with controller_lock(out):
            print(json.dumps(report(out), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

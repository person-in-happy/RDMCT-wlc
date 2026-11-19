"""Nine gap-gated SCIP flows; frozen inputs, foreground supervision, append-only retries."""
from __future__ import annotations

import argparse
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
DEFAULT = JMS / "results/gap_two_stage_20261117_g05_r1"
CASES = ("D_n4_mixed", "D_n16_4x1", "E_n16_2x2")
WEIGHTS = (0.01, 0.1, 1.0)
RECOVERABLE = {"foreground_interrupted", "orphaned_attempt", "RAM_guard", "RSS_guard", "wall_guard", "solver_resource_limit"}
GIB = 1024 ** 3


def finite(value, infinity=1e20):
    """SCIP +/-infinity sentinels must not become numerical certificates."""
    return float(value) if value is not None and math.isfinite(value) and abs(value) < infinity else None


def gate(primary, threshold, total):
    """Time is only a safety budget, never an alternative to the quality gate."""
    ub, lb = primary["primal_bound"], primary["dual_bound"]
    gap = primary["relative_gap"]
    bounds_ok = (ub is not None and lb is not None and lb <= ub + 1e-6)
    # These experiments minimize a positive makespan. A zero/negative lower
    # bound gives no finite relative certificate for a positive incumbent.
    computed = max(0., ub - lb) / min(abs(ub), abs(lb)) if bounds_ok and ub * lb > 0 else None
    quality = bool(bounds_ok and (primary["status"] == "optimal" or
                   (threshold > 0 and gap is not None and computed is not None and
                    gap <= threshold + 1e-10 and computed <= threshold + 1e-10)))
    remaining = max(0., total - primary["seconds"])
    resource_stop = primary["status"] not in ("optimal", "gaplimit", "timelimit")
    switched = quality and remaining > 1e-3 and not resource_stop
    reason = ("resource_or_unexpected_stop" if resource_stop else
              "target_not_met" if not quality else
              "no_budget_remaining" if not switched else "quality_certified")
    return dict(threshold=threshold, quality_met=quality, switch=switched,
                remaining_seconds=remaining, reason=reason, recomputed_gap=computed,
                definition="abs(UB-LB)/min(abs(UB),abs(LB)); global Cmax bounds")


def make_cells(cases):
    return [dict(id=f'{c["case"]}__s{s}__gap_two_stage', case=c["case"],
                 backend=c["backend"], seed=s, method="scip", budget=300.)
            for c in cases for s in (1, 2, 3)]


def baseline_references(cases):
    refs, hashes = [], {str(BASE / "campaign.json"): f.sha(BASE / "campaign.json")}
    for c in cases:
        for seed in (1, 2, 3):
            for weight in WEIGHTS:
                directory = BASE / "runs" / f'{c["case"]}__objectives__s{seed}__joint_{weight:g}'
                ev = f.read(directory / "evidence.json")
                if f.sha(directory / "result.json") != ev["result_sha256"] or f.sha(directory / "variables.json") != ev["assignment_sha256"]:
                    raise ValueError("Frozen baseline certificate hash mismatch: " + str(directory))
                for leaf in ("evidence.json", "result.json", "variables.json", "input.json"):
                    hashes[str(directory / leaf)] = f.sha(directory / leaf)
                inp = f.read(directory / "input.json")
                if inp["sha256"] != f.sha(c["values"]) or inp["normalization"] != c["scales"]:
                    raise ValueError("Baseline input/normalization mismatch")
                refs.append(dict(case=c["case"], seed=seed, weight=weight,
                                 evidence=str(directory / "evidence.json"),
                                 eligible=bool(ev["valid"] and ev["budget_eligible"])))
    return refs, hashes


def plan(threshold=.05):
    if not math.isfinite(threshold) or not 0 <= threshold < 1:
        raise ValueError("Relative gap must be a fraction in [0,1)")
    original = f.checked(BASE)
    cases = [next(c for c in original["cases"] if c["case"] == name) for name in CASES]
    refs, sources = baseline_references(cases)
    for c in cases:
        for key in ("source", "values"):
            sources[c[key]] = f.sha(c[key])
    return dict(relative_gap=threshold, cases=cases, cells=make_cells(cases),
                references=refs, sources=sources, original_environment=original["environment"])


def prepare(out, threshold):
    if out.exists():
        raise FileExistsError("Use Run/Resume for this campaign, or a fresh directory for a new protocol")
    spec = plan(threshold)
    packages = {name: version(name) for name in ("pyscipopt", "numpy", "psutil")}
    if any(packages[k] != spec["original_environment"]["packages"][k] for k in packages):
        raise RuntimeError("Python packages differ from the frozen comparison environment")
    paths = [BASE_ENTRY, *HERE.glob("*.py"), HERE / "control.ps1", HERE / "README_CN.txt",
             ROOT / "scip_imports.py", ROOT / "runtime_compat.py"]
    for backend in f.BACKENDS.values():
        paths.extend(backend / name for name in ("model.py", "validate.py", "physical_validate.py", "pjobs.py", "pjob_order.py", "grippers.py",
                                                "joint_pairing_model.py", "joint_chamber_cycle_model.py"))
    import psutil
    spec.update(schema=1, created_utc=f.stamp(), assets={str(p.relative_to(ROOT)): f.sha(p) for p in sorted(set(paths))},
                environment=dict(python=sys.executable, python_version=sys.version, packages=packages,
                                 ram_gib=psutil.virtual_memory().total / GIB, cpu_logical=psutil.cpu_count()),
                settings=dict(threads=1, default_workers=2, max_large_workers=1, min_available_gib=8.,
                              small_reservation_gib=4., large_reservation_gib=12., max_worker_rss_gib=16.,
                              wall_guard_seconds=3600., refresh_seconds=10., solver_budget_tolerance=1.),
                timing="Total SCIP solve time <=300s (+same 1s soft-limit qualification tolerance as the old campaign). Build, validation and switching overhead separately included in wall time. Phase 2 receives max(0,300-actual_phase1_solver_time).",
                objectives="Phase 1: unrestricted product-return Cmax. Phase 2 only after gap certificate: fix noncontinuous variables except sync_; cap Cmax at phase-1 value+1e-6; minimize wait_sum+10*wait_max+25*rhythm. This is conditional fixed-structure refinement, not a global lexicographic optimum.",
                reuse="Reuse qualified same-case/same-seed old weighted SCIP results. Existing 30 refinement pairs and rhythm weights remain conditional module evidence from their ORIGINAL inputs, not observations from the new stopping rule. Other experiments keep their original scopes.",
                retries="Append new attempt directories only for interruption/execution failure. Keep completed timeouts, target-not-met and completed budget exclusions; never rerun them to select a better outcome. Retries start from the original frozen warm start, not a saved SCIP search tree.")
    out.mkdir(parents=True)
    f.dump(out / "campaign.json", spec)
    f.dump(out / "contract.json", dict(campaign_sha256=f.sha(out / "campaign.json")))
    for rel in spec["assets"]:
        target = out / "frozen_code" / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / rel, target)
    print(json.dumps(report(out), ensure_ascii=False))
    print("PREPARED 9 flows; no model built, no solver started", flush=True)


def checked(out, full=True):
    spec = f.checked(out, full=full)
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


def report(out, write=True):
    spec = checked(out, full=False)
    rows = [c | inspect_cell(out, c["id"]) for c in spec["cells"]]
    done = [r for r in rows if r["state"] == "completed"]
    eligible = [r for r in done if r["evidence"]["valid"] and r["evidence"]["budget_eligible"]]
    coverage = dict(expected=9, completed=len(done), failed=sum(r["state"] == "failed" for r in rows),
                    incomplete=sum(r["state"] == "incomplete" for r in rows),
                    pending=sum(r["state"] == "pending" for r in rows), budget_eligible=len(eligible),
                    quality_met=sum(r["evidence"]["gate"]["quality_met"] for r in eligible),
                    refined=sum(r["evidence"]["gate"]["switch"] for r in eligible))
    if not write:
        return coverage
    paired = []
    for case in CASES:
        for weight in WEIGHTS:
            pairs, exclusions = [], []
            for ref in spec["references"]:
                if ref["case"] != case or ref["weight"] != weight:
                    continue
                current = next((r for r in eligible if r["case"] == case and r["seed"] == ref["seed"]), None)
                if current is None or not ref["eligible"]:
                    exclusions.append(dict(seed=ref["seed"], new_eligible=current is not None, old_eligible=ref["eligible"]))
                    continue
                old = f.read(ref["evidence"])
                pairs.append(dict(seed=ref["seed"], gap_two_stage=current["evidence"]["metrics"],
                                  joint=old["metrics"], switched=current["evidence"]["gate"]["switch"]))
            row = dict(case=case, weight=weight, expected=3, paired=len(pairs), complete=len(pairs) == 3,
                       pairs=pairs, exclusions=exclusions)
            for arm in ("gap_two_stage", "joint"):
                if pairs:
                    row[arm + "_mean"] = {k: statistics.mean(p[arm][k] for p in pairs)
                                           for k in ("cmax", "secondary", "wait_sum", "wait_max", "rhythm", "rhythm_centers")}
            paired.append(row)
    f.dump(out / "summary/coverage.json", coverage)
    f.dump(out / "summary/rows.json", rows)
    f.dump(out / "summary/paired_weighted.json", paired)
    return coverage


def stage_record(m, phase, limit):
    inf = m.infinity()
    return dict(phase=phase, limit=limit, seconds=m.getSolvingTime(), status=str(m.getStatus()),
                primal_bound=finite(m.getPrimalbound(), inf), dual_bound=finite(m.getDualbound(), inf),
                relative_gap=finite(m.getGap(), inf), nodes=m.getNNodes(), solutions=m.getNSols(),
                bound_scope="global_product_Cmax" if phase == "primary" else "fixed_structure_secondary")


def start_refinement(x, values, primary_cmax, remaining):
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
    m.setRealParam("limits/time", remaining)
    return cap


def worker(out, cid, attempt):
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
    started = time.monotonic()
    f.dump(dest / "progress.json", dict(phase="building", updated_utc=f.stamp()))
    x = backend.Integrated(backend.Config(**case["config"]))
    m = x.model
    build_seconds = time.monotonic() - started
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
    m.setRealParam("limits/gap", spec["relative_gap"])
    m.setRealParam("limits/absgap", 0.)
    m.setRealParam("limits/time", cell["budget"])
    f.dump(dest / "input.json", dict(path=case["values"], sha256=f.sha(case["values"]), metrics=initial,
                                    normalization=case["scales"], build_seconds=build_seconds,
                                    variables=m.getNVars(), constraints=m.getNConss(),
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
                row = dict(phase=phase, solver_seconds=m.getSolvingTime(),
                           primal_bound=finite(m.getPrimalbound()), dual_bound=finite(m.getDualbound()),
                           relative_gap=finite(m.getGap()), updated_utc=f.stamp())
                trace.append(row)
                f.dump(dest / "progress.json", row)
                self.last = now
    m.includeEventhdlr(Progress(), "gap_progress", "bounded progress sampling")
    f.dump(dest / "progress.json", dict(phase=phase, updated_utc=f.stamp()))
    m.optimize()
    stages = [stage_record(m, phase, cell["budget"])]
    if not m.getNSols():
        raise ValueError("SCIP lost the validated warm start")
    best = m.getBestSol()
    first_data, first_metrics = physical(best)
    values = {v.name: m.getSolVal(best, v) for v in original}
    first_data["solver_record"] = stages[0]
    f.dump(dest / "phase1.json", first_data)
    f.dump(dest / "variables_phase1.json", dict(values=values))
    decision = gate(stages[0], spec["relative_gap"], cell["budget"])
    f.dump(dest / "gate.json", decision)
    cap = None
    if decision["switch"]:
        phase = "secondary"
        cap = start_refinement(x, values, first_metrics["cmax"], decision["remaining_seconds"])
        warm = assignment(values)
        # Phase 1 did not minimize these epigraphs. Tighten them to the actual
        # unchanged schedule so a secondary timeout cannot accept a worse B.
        tighten_epigraphs(warm, first_metrics)
        if not m.checkSol(warm, printreason=True, completely=True, original=True):
            raise ValueError("First-stage assignment rejected by restricted refinement")
        m.addSol(warm)
        f.dump(dest / "progress.json", dict(phase=phase, updated_utc=f.stamp()))
        m.optimize()
        stages.append(stage_record(m, phase, decision["remaining_seconds"]))
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
    overrun = total > cell["budget"] + spec["settings"]["solver_budget_tolerance"]
    resource = any(s["status"] not in ("optimal", "gaplimit", "timelimit") for s in stages)
    data.update(original_model_check=valid, experiment_scope="gap_gated_fixed_structure_refinement",
                global_lexicographic_optimality_claim=False, primary_certificate=stages[0], gate=decision)
    f.dump(dest / "result.json", data)
    f.dump(dest / "variables.json", dict(values=values))
    f.dump(dest / "trace.json", trace)
    f.dump(dest / "evidence.json", dict(valid=valid, budget_eligible=valid and not overrun and not resource,
           metrics=metrics, primary_metrics=first_metrics, input_metrics=initial, stages=stages, gate=decision,
           solver_seconds=total, nominal_total=cell["budget"], stage_overrun=overrun, resource_interruption=resource,
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
    f.dump(out / "sessions" / (session + ".json"), dict(created_utc=f.stamp(), pid=os.getpid(),
           max_workers=max_workers, retry_failed=retry_failed, selected=sorted(selected), pending=[c["id"] for c in pending]))
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
                              "wall_guard" if elapsed > settings["wall_guard_seconds"] else None)
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
                coverage = report(out)
                typical = statistics.mean(completed_durations) if completed_durations else 300.
                count = len(pending) + len(active)
                large = sum("n16" in c["case"] for c in pending) + sum("n16" in a["cell"]["case"] for a in active.values())
                eta = max(count / max_workers, large) * typical
                progress = {}
                for cid, a in active.items():
                    path = a["dest"] / "progress.json"
                    progress[cid] = (f.read(path) if path.exists() else dict(phase="loading")) | dict(rss_gib=a["rss_gib"])
                state = coverage | dict(updated_utc=f.stamp(), supervisor_pid=os.getpid(), active=progress,
                    available_gib=psutil.virtual_memory().available / GIB, state=reason, foreign_pids=foreign,
                    estimated_remaining_minutes=eta / 60.,
                    eta_note="Initial estimate uses nominal solver time; later uses observed full wall time. External/resource waiting time unknown; large jobs serialized.")
                f.dump(out / "live_status.json", state)
                print(f'complete={coverage["completed"]}/9 failed={coverage["failed"]} running={len(active)} '
                      f'left={len(pending)} RAM={state["available_gib"]:.1f}GiB ETA~{eta/60:.1f}min {reason}', flush=True)
                for cid, info in progress.items():
                    print("  " + cid + " " + json.dumps(info), flush=True)
                last = time.monotonic()
            if pending or active:
                time.sleep(1)
    finally:
        for task in active.values():
            stop_own(task)
            task["log"].close()
            if not (task["dest"] / "evidence.json").exists():
                f.dump(task["dest"] / "failure.json", dict(reason="foreground_interrupted", ended_utc=f.stamp()))
        coverage = report(out)
        f.dump(out / "last_session.json", coverage | dict(ended_utc=f.stamp(), session=session))
    print("FINISHED " + json.dumps(coverage), flush=True)
    return 1 if coverage["failed"] or coverage["incomplete"] else 0


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("action", choices=("plan", "prepare", "run", "resume", "status", "report", "worker"))
    parser.add_argument("--campaign", default=str(DEFAULT))
    parser.add_argument("--relative-gap", type=float)
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
    if args.relative_gap is not None and args.action not in ("plan", "prepare"):
        parser.error("The gap is frozen at Prepare; Run/Resume cannot change it")
    if args.action == "plan":
        spec = plan(.05 if args.relative_gap is None else args.relative_gap)
        print(json.dumps(dict(gap=spec["relative_gap"], cells=spec["cells"],
              existing_weighted_references=len(spec["references"]),
              eligible_existing_references=sum(r["eligible"] for r in spec["references"]),
              nominal_solver_minutes=45., solver_started=False), ensure_ascii=False, indent=2))
    elif args.action == "prepare":
        prepare(out, .05 if args.relative_gap is None else args.relative_gap)
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

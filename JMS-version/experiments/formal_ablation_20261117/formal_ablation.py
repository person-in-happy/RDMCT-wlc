"""Prospectively frozen, finite-budget ablation; independent of old campaigns."""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import gc
import hashlib
import importlib
import importlib.util
from importlib.metadata import version
import json
import math
import os
from pathlib import Path
import random
import shutil
import statistics
import subprocess
import sys
import time
import traceback

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
JMS = ROOT / "JMS-version"
BASE_PATH = HERE.parent / "finite_budget_20261116/finite_budget.py"
loader = importlib.util.spec_from_file_location("finite_budget_helpers", BASE_PATH)
base = importlib.util.module_from_spec(loader)
loader.loader.exec_module(base)
read, dump, sha, stamp, physical_metrics = base.read, base.dump, base.sha, base.stamp, base.physical_metrics
BACKEND = JMS / "model4_pjob_nonprocessing_20261103"
METHODS = base.METHODS
SEEDS = (11, 12, 13)
EPS = 2e-4
TIME_EPS = 1e-3


def source_records():
    qualification = JMS / "results/journal_d_qualification_20261109_r1/runs"
    records = []
    for name in ("n2_4x1_scenario1", "n2_2x2_scenario2", "n2_mixed_scenario2", "n2_mixed_scenario3"):
        directory = qualification / (name + "__s17__t1__qualification")
        records.append(dict(case=name, backend="D", source=str(directory / "result.json"),
                            values=str(directory / "variables.json"), budgets=[60, 120, 300],
                            group="main", optimal_control=name == "n2_4x1_scenario1"))
    for record in base.source_records()[:3]:
        large = record["case"] != "D_n2_mixed"
        records.append(record | dict(budgets=[900] if large else [60, 120, 300],
                                     group="expansion" if large else "main", optimal_control=False))
    return records


def make_cells(cases):
    cells = []
    # Finish complete budget/instance blocks in this fixed order, regardless of results.
    for group, budgets in (("main", (60, 120, 300)), ("expansion", (900,))):
        for total in budgets:
            for case in cases:
                if case["group"] != group or total not in case["budgets"]:
                    continue
                for seed in SEEDS:
                    prefix = f'{case["case"]}__b{total}__s{seed}'
                    common = dict(case=case["case"], backend="D", group=group,
                                  optimal_control=case["optimal_control"], seed=seed, total_budget=total)
                    prep_id = prefix + "__spbs"
                    cells.append(common | dict(id=prep_id, suite="preparation", method="scip", arm="spbs",
                                               training_seed=0, budget=.2 * total, init_budget=.2 * total,
                                               with_spbs=True))
                    for with_spbs, methods in ((False, ("scip", "hem", "proposed")), (True, METHODS)):
                        for method in methods:
                            for training_seed in ((0,) if method == "scip" else (1, 2, 3)):
                                arm = method + ("_spbs" if with_spbs else "_raw")
                                cell = common | dict(id=prefix + f'__t{training_seed}__{arm}',
                                      suite="ablation", method=method, arm=arm, training_seed=training_seed,
                                      budget=(.8 if with_spbs else 1.) * total,
                                      init_budget=(.2 if with_spbs else 0.) * total, with_spbs=with_spbs)
                                if with_spbs:
                                    cell["preparation"] = prep_id
                                cells.append(cell)
    return cells


def backend_modules():
    sys.path.insert(0, str(BACKEND))
    sys.path.insert(1, str(ROOT))
    return importlib.import_module("model"), importlib.import_module("validate").validate


def assignment(m, values):
    sol = m.createSol()
    variables = m.getVars(transformed=False)
    if set(values) != {v.name for v in variables}:
        raise ValueError("Complete original-variable assignment required")
    for v in variables:
        m.setSolVal(sol, v, values[v.name])
    return sol


def qualify(case):
    backend, validate = backend_modules()
    started = time.monotonic()
    data = read(case["source"])
    if not data.get("solutions") or not data.get("original_model_check") or not data.get("validation", {}).get("valid"):
        raise ValueError("Unqualified source: " + case["case"])
    x = backend.Integrated(backend.Config(**data["config"]))
    m = x.model
    values = read(case["values"])["values"]
    sol = assignment(m, values)
    accepted = bool(m.checkSol(sol, printreason=True, completely=True, original=True))
    decoded = x.result(solution=sol)
    check = validate(decoded)
    metrics = physical_metrics(decoded)
    if not accepted or not check["valid"] or abs(metrics["cmax"] - physical_metrics(data)["cmax"]) > EPS:
        raise ValueError("Source failed independent qualification: " + case["case"])
    certificate = dict(case=case["case"], valid=True, variables=m.getNVars(), constraints=m.getNConss(),
                       validation=check, metrics=metrics, wall_seconds=time.monotonic() - started,
                       source_sha256=sha(case["source"]), assignment_sha256=sha(case["values"]))
    m.freeSol(sol)
    m.freeProb()
    del x, sol, m, values
    gc.collect()
    return data["config"], metrics, certificate


def inventory():
    paths = [Path(__file__), HERE / "launch.ps1", HERE / "PROTOCOL_CN.txt", HERE / "test_formal_ablation.py", BASE_PATH]
    paths.extend(BACKEND.glob("*.py"))
    paths.extend(ROOT / n for n in ("scip_imports.py", "runtime_compat.py", "utils.py", "cutsel_agent_parallel.py",
          "environments.py", "global_const.py", "cie/code/run_cie_benchmarks.py", "pointer_net.py",
          "pointer_net_end_token.py", "beam_search.py", "logger.py", "path_utils.py", "petri_warm_start.py",
          "petri_mip_generator.py"))
    paths.extend((ROOT / "utilss").glob("*.py"))
    return {str(p.relative_to(ROOT)): sha(p) for p in sorted(set(paths))}


def prepare(out, smoke=False):
    if out.exists():
        raise FileExistsError("Use a fresh directory; no observations may be overwritten")
    cases = source_records()
    if smoke:
        cases = [c for c in cases if c["case"] == "n2_mixed_scenario2"]
        cases[0]["budgets"] = [60]
    sources, certificates = {}, []
    for case in cases:
        config, metrics, certificate = qualify(case)
        case.update(config=config, input_metrics=metrics)
        certificates.append(certificate)
        for key in ("source", "values"):
            sources[case[key]] = sha(case[key])
        print("QUALIFIED " + case["case"] + " A=" + str(metrics["cmax"]), flush=True)
    manifest = ROOT / "cie/results/repro_manifest/selected_checkpoint_manifest.csv"
    policies = [r for r in csv.DictReader(manifest.open(encoding="utf-8-sig"))
                if r["family"] in ("hem", "proposed", "feature_only") and int(r["training_seed"]) in (1, 2, 3)]
    if len(policies) != 9:
        raise ValueError("Expected exactly nine frozen checkpoints")
    sources[str(manifest)] = sha(manifest)
    for policy in policies:
        checkpoint = ROOT / policy["checkpoint"]
        if sha(checkpoint) != policy["checkpoint_sha256"]:
            raise ValueError("Frozen checkpoint hash mismatch")
        sources[str(checkpoint)] = policy["checkpoint_sha256"]
        variant = checkpoint.with_name("variant.json")
        if variant.exists():
            sources[str(variant)] = sha(variant)
    for name in ("cie/configs/cie_hem_train.json", "cie/configs/cie_proposed_inference.json"):
        sources[str(ROOT / name)] = sha(ROOT / name)
    cells = make_cells(cases)
    if smoke:
        cells = [c for c in cells if c["seed"] == 11 and
                 (c["suite"] == "preparation" or (c["method"] == "scip" and not c["with_spbs"]) or
                  (c["method"] == "proposed" and c["training_seed"] == 1 and c["with_spbs"]))]
    spec = dict(schema=2, created_utc=stamp(), formal=not smoke, cases=cases, cells=cells, sources=sources,
        assets=inventory(), policies=policies,
        environment=dict(python=sys.executable, python_version=sys.version,
                         packages={n: version(n) for n in ("pyscipopt", "numpy", "torch", "psutil")}),
        settings=dict(max_workers=2, gpu_slots=1, preparation_slots=1, threads=1,
                      min_available_gib=8., launch_reserve_gib=12., large_launch_gib=20.,
                      refresh_seconds=10., wall_guard_seconds=3600., external_experiments_must_be_idle=True),
        timing="A is the best complete incumbent captured by the allocated deadline. SPBS wall time is charged at 20% of T; main SCIP wall-clock solve budget is 80% of T (100% without SPBS). No transfer of unused allocation. Offline source construction, model build, input validation, policy loading and final certification are excluded and separately recorded. Late incumbents/bounds are never used; actual stopping overruns are reported.",
        selection="One preselected proven-optimal control; all four available nonoptimal small configurations; both cut-active large probes in a separate 900-second stratum. No outcome-dependent selection, retuning or retraining.",
        inference="Within-case paired solver/training seeds; SCIP has no training-seed replication. Average within each instance first, then equally across instances, separately by budget and main/expansion and control/noncontrol. Incomplete pairs remain pending. All wins/ties/losses retained.",
        tolerance=dict(objective=EPS, deadline_seconds=TIME_EPS), stage_two=False)
    out.mkdir(parents=True)
    dump(out / "campaign.json", spec)
    dump(out / "contract.json", dict(campaign_sha256=sha(out / "campaign.json")))
    dump(out / "source_qualification.json", certificates)
    for rel in spec["assets"]:
        target = out / "frozen_code" / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / rel, target)
    report(out)
    print(f'PREPARED formal={not smoke} cells={len(cells)} solver_hours={sum(c["budget"] for c in cells)/3600:.2f}', flush=True)


def checked(out, full=True):
    return base.checked(out, full=full)


def timely(elapsed, limit, allocated, total):
    return elapsed <= limit + TIME_EPS and allocated <= total + TIME_EPS


def spbs_fixed(name, level, vtr_names):
    if name.startswith("sync_"):
        return False
    if level >= 2 and name.startswith("order_") and any(name.startswith("order_" + e + "_") for e in vtr_names):
        return False
    if level >= 3 and name.startswith(("order_U_", "order_L_")):
        return False
    if level >= 4 and name.startswith("order_"):
        return False
    if level >= 5:
        return name.startswith(("jp_", "pj_", "jc_used_", "jc_kind_"))
    return True


def worker(out, cell_id):
    spec = checked(out)
    cell = next(c for c in spec["cells"] if c["id"] == cell_id)
    case = next(c for c in spec["cases"] if c["case"] == cell["case"])
    dest = out / "runs" / cell_id
    dest.mkdir(parents=True, exist_ok=False)
    backend, validate = backend_modules()
    algorithms = importlib.import_module("joint_algorithms")
    from scip_imports import scip
    import psutil
    started = time.monotonic()
    random.seed(cell["seed"])
    x = backend.Integrated(backend.Config(**case["config"]))
    m = x.model
    m.setIntParam("parallel/maxnthreads", 1)
    m.setIntParam("lp/threads", 1)
    m.setIntParam("timing/clocktype", 2)
    m.setIntParam("randomization/randomseedshift", cell["seed"])
    m.setLogfile(str(dest / "solver.log"))
    build_seconds = time.monotonic() - started
    original_bounds = {v.name: (v.getLbOriginal(), v.getUbOriginal()) for v in m.getVars(transformed=False)}
    source_values = case["values"]
    trace = [dict(allocated_budget_time=0., phase="original_input", cmax=case["input_metrics"]["cmax"])]
    if cell.get("preparation"):
        prep = out / "runs" / cell["preparation"]
        certificate = read(prep / "evidence.json")
        if not certificate["valid"] or not certificate["budget_eligible"]:
            raise ValueError("Shared SPBS certificate failed")
        source_values = str(prep / "variables.json")
        if sha(source_values) != certificate["assignment_sha256"]:
            raise ValueError("Shared SPBS assignment changed")
        trace = read(prep / "trace.json")
    check_started = time.monotonic()
    values = read(source_values)["values"]
    warm = assignment(m, values)
    if not m.checkSol(warm, printreason=True, completely=True, original=True):
        raise ValueError("Common full assignment rejected")
    source_data = x.result(solution=warm)
    source_validation = validate(source_data)
    if not source_validation["valid"]:
        raise ValueError("Input physical validation failed")
    input_metrics = physical_metrics(source_data)
    m.setSolVal(warm, x.cmax, input_metrics["cmax"])
    values = {v.name: m.getSolVal(warm, v) for v in m.getVars(transformed=False)}
    if not m.checkSol(warm, printreason=True, completely=True, original=True):
        raise ValueError("Tightened Cmax invalidated common input")
    m.addSol(warm)
    input_check_seconds = time.monotonic() - check_started
    dump(dest / "input.json", dict(path=source_values, sha256=sha(source_values), metrics=input_metrics,
         build_seconds=build_seconds, input_check_seconds=input_check_seconds,
         variables=m.getNVars(), constraints=m.getNConss()))
    if cell.get("preparation"):
        trace.append(dict(allocated_budget_time=cell["init_budget"], phase="shared_spbs_input", cmax=input_metrics["cmax"]))
    stages, bound_trace = [], []
    best_values, best_cmax = values.copy(), input_metrics["cmax"]
    phase, limit, offset = "primary", cell["budget"], cell["init_budget"] if cell["suite"] != "preparation" else 0.
    total = cell["total_budget"] if cell["suite"] != "preparation" else cell["budget"]
    spbs_started = None
    solve_started = None
    interrupted, late_events = False, 0
    last_progress, last_bound = -1., None
    progress_clock = -100.

    def solve_elapsed():
        return 0. if solve_started is None else time.monotonic() - solve_started

    def allocated_time():
        return time.monotonic() - spbs_started if spbs_started is not None else offset + solve_elapsed()

    def remember(sol, elapsed, allocated, allow_tie=False):
        nonlocal best_values, best_cmax
        if sol is None or not timely(elapsed, limit, allocated, total):
            return
        value = m.getSolVal(sol, x.cmax)
        if value > best_cmax + EPS or (not allow_tie and value >= best_cmax - EPS):
            return
        snapshot = {v.name: m.getSolVal(sol, v) for v in m.getVars(transformed=False)}
        # Extraction itself is inside optimize() for callbacks, hence charged.
        finished = allocated_time()
        if not timely(solve_elapsed(), limit, finished, total):
            return
        best_values, best_cmax = snapshot, value
        trace.append(dict(allocated_budget_time=allocated, captured_by=finished, phase=phase,
                          cmax=value, wall_seconds=time.monotonic() - started))

    def save_progress(force=False):
        nonlocal progress_clock
        now = time.monotonic()
        if force or now - progress_clock >= 5:
            dump(dest / "progress.json", dict(updated_utc=stamp(), phase=phase, cmax=best_cmax,
                 allocated_budget_time=allocated_time(), total_budget=total, dual_bound=last_bound))
            progress_clock = now

    class Recorder(scip.Eventhdlr):
        events = scip.SCIP_EVENTTYPE.BESTSOLFOUND | scip.SCIP_EVENTTYPE.LPSOLVED | scip.SCIP_EVENTTYPE.NODESOLVED

        def eventinit(self):
            self.model.catchEvent(self.events, self)

        def eventexit(self):
            self.model.dropEvent(self.events, self)

        def eventexec(self, event):
            nonlocal interrupted, late_events, last_progress, last_bound
            elapsed, allocated = solve_elapsed(), allocated_time()
            if not timely(elapsed, limit, allocated, total):
                late_events += 1
                m.interruptSolve()
                return
            if event.getType() & scip.SCIP_EVENTTYPE.BESTSOLFOUND:
                remember(m.getBestSol(), elapsed, allocated)
            if cell["suite"] != "preparation":
                bound = float(m.getDualbound())
                if math.isfinite(bound) and abs(bound) < 1e19:
                    last_bound = bound
                    if allocated - last_progress >= 1 or event.getType() & scip.SCIP_EVENTTYPE.BESTSOLFOUND:
                        bound_trace.append(dict(allocated_budget_time=allocated, dual_bound=bound))
                        last_progress = allocated
            save_progress()
            if psutil.virtual_memory().available < spec["settings"]["min_available_gib"] * 1024**3:
                interrupted = True
                m.interruptSolve()

    recorder = Recorder()
    m.includeEventhdlr(recorder, "deadline_recorder", "complete incumbent and bound before cutoff")
    agent, policy_load_seconds = None, 0.
    spbs_wall_seconds = None

    def solve_stage(fixed_count=0):
        nonlocal last_bound, solve_started
        m.setObjective(x.primary_objective, "minimize")
        m.setRealParam("limits/time", limit)
        solve_started = time.monotonic()
        m.optimize()
        elapsed, allocated = solve_elapsed(), allocated_time()
        status = str(m.getStatus())
        if timely(elapsed, limit, allocated, total):
            remember(m.getBestSol(), elapsed, allocated, allow_tie=True)
            if cell["suite"] != "preparation":
                bound = float(m.getDualbound())
                if math.isfinite(bound) and abs(bound) < 1e19:
                    last_bound = bound
                    bound_trace.append(dict(allocated_budget_time=allocated, dual_bound=bound))
        stages.append(dict(phase=phase, seconds=elapsed, scip_seconds=m.getSolvingTime(), limit=limit, status=status, fixed=fixed_count,
                      raw_final_cmax=float(m.getSolVal(m.getBestSol(), x.cmax)) if m.getNSols() else None,
                      raw_final_dual_bound=float(m.getDualbound()), selected_cmax=best_cmax,
                      raw_final_available_by_deadline=timely(elapsed, limit, allocated, total)))

    if cell["suite"] == "preparation":
        spbs_started = time.monotonic()
        vtr_names = {e["name"] for e in x.robots["VTR"]}
        for level in range(1, 6):
            if time.monotonic() - spbs_started >= total or interrupted:
                break
            phase = "spbs_" + str(level)
            fixed = []
            for v in m.getVars(transformed=False):
                if v.vtype() != "CONTINUOUS" and spbs_fixed(v.name, level, vtr_names):
                    fixed.append(v)
                    value = round(best_values[v.name])
                    m.chgVarLb(v, value)
                    m.chgVarUb(v, value)
            sol = assignment(m, best_values)
            if not m.checkSol(sol, printreason=True, completely=True, original=True):
                raise ValueError("SPBS incumbent violates the selected neighborhood")
            m.addSol(sol)
            limit = min(total / 5., total - (time.monotonic() - spbs_started))
            if limit > 0:
                solve_stage(len(fixed))
            m.freeTransform()
            for v in fixed:
                lb, ub = original_bounds[v.name]
                m.chgVarLb(v, lb)
                m.chgVarUb(v, ub)
        spbs_wall_seconds = time.monotonic() - spbs_started
        dump(dest / "spbs_levels.json", stages)
    else:
        load_started = time.monotonic()
        if cell["method"] != "scip":
            import numpy as np
            import torch
            np.random.seed(cell["seed"])
            torch.manual_seed(cell["seed"])
        agent, policy = algorithms.install(m, cell["method"], cell["training_seed"])
        policy_load_seconds = time.monotonic() - load_started
        dump(dest / "policy.json", dict(record=policy, load_seconds=policy_load_seconds))
        save_progress(force=True)
        solve_stage()
    if agent is not None:
        dump(dest / "cutsel_telemetry.json", agent.get_telemetry())
    # Final certification is on the original, fully unrestricted model.
    validation_started = time.monotonic()
    m.freeTransform()
    for v in m.getVars(transformed=False):
        lb, ub = original_bounds[v.name]
        m.chgVarLb(v, lb)
        m.chgVarUb(v, ub)
    m.setObjective(x.primary_objective, "minimize")
    final = assignment(m, best_values)
    valid = bool(m.checkSol(final, printreason=True, completely=True, original=True))
    data = x.result(solution=final)
    validation = validate(data)
    metrics = physical_metrics(data)
    valid = valid and validation["valid"] and abs(metrics["cmax"] - best_cmax) <= EPS
    if metrics["cmax"] > input_metrics["cmax"] + EPS:
        raise ValueError("Selected solution worsened the common incumbent")
    data.update(original_model_check=valid, validation=validation, experiment_scope="formal_ablation" if spec["formal"] else "smoke",
                global_optimality_claim=False, benchmark_objective_scope="product_return_cmax")
    dump(dest / "result.json", data)
    dump(dest / "variables.json", dict(values=best_values))
    dump(dest / "trace.json", trace)
    dump(dest / "bound_trace.json", bound_trace)
    overrun = any(s["seconds"] > s["limit"] + TIME_EPS for s in stages)
    evidence = dict(valid=bool(valid), budget_eligible=bool(valid and not interrupted), completed_utc=stamp(),
        metrics=metrics, input_metrics=input_metrics, stages=stages, nominal_total=total,
        stage_overrun=overrun, spbs_wall_seconds=spbs_wall_seconds, late_events_ignored=late_events,
        resource_interruption=interrupted, deadline_rule="Only complete incumbents captured before the allocated cutoff are accepted; a late solver stop does not extend the observation window.",
        wall_seconds=time.monotonic() - started, build_seconds=build_seconds,
        input_check_seconds=input_check_seconds, policy_load_seconds=policy_load_seconds,
        final_validation_seconds=time.monotonic() - validation_started, valid_cmax_lower_bound=last_bound,
        optimal_at_cutoff=bool(cell["suite"] != "preparation" and last_bound is not None and abs(metrics["cmax"] - last_bound) <= EPS),
        source_assignment_sha256=sha(source_values), source_construction="offline; common frozen feasible assignment",
        result_sha256=sha(dest / "result.json"), assignment_sha256=sha(dest / "variables.json"))
    dump(dest / "evidence.json", evidence)
    m.freeSol(final)
    m.freeProb()
    if not valid:
        raise ValueError("Independent final validation failed")
    print(f'COMPLETE {cell_id} A={metrics["cmax"]:.6f} valid={valid} eligible={evidence["budget_eligible"]}', flush=True)


CONTRASTS = (("spbs_scip", "scip_spbs", "scip_raw"), ("spbs_hem", "hem_spbs", "hem_raw"),
             ("spbs_proposed", "proposed_spbs", "proposed_raw"),
             ("full_vs_scip_spbs", "proposed_spbs", "scip_spbs"),
             ("full_vs_hem_spbs", "proposed_spbs", "hem_spbs"),
             ("full_vs_feature_only", "proposed_spbs", "feature_only_spbs"),
             ("full_vs_no_structure", "proposed_spbs", "proposed_no_structure_spbs"),
             ("full_vs_greedy", "proposed_spbs", "proposed_greedy_spbs"),
             ("full_vs_scip_raw", "proposed_spbs", "scip_raw"),
             ("raw_vs_scip_raw", "proposed_raw", "scip_raw"),
             ("raw_vs_hem_raw", "proposed_raw", "hem_raw"))


def paired_rows(spec, rows):
    cells = {c["id"]: c for c in spec["cells"] if c["suite"] == "ablation"}
    expected = {(c["case"], c["total_budget"], c["seed"], c["training_seed"], c["arm"]): c["id"] for c in cells.values()}
    accepted = {r["id"]: r for r in rows if r.get("valid") and r.get("budget_eligible")}
    pairs = []
    for name, arm_a, arm_b in CONTRASTS:
        for cell in cells.values():
            if cell["arm"] != arm_a:
                continue
            training_b = 0 if arm_b.startswith("scip_") else cell["training_seed"]
            partner = expected.get((cell["case"], cell["total_budget"], cell["seed"], training_b, arm_b))
            if partner is None:
                continue
            a, b = accepted.get(cell["id"]), accepted.get(partner)
            pair = dict(contrast=name, case=cell["case"], group=cell["group"],
                 optimal_control=cell["optimal_control"], total_budget=cell["total_budget"], seed=cell["seed"],
                 training_seed=cell["training_seed"], left=cell["id"], right=partner, complete=bool(a and b))
            if a and b:
                delta = a["metrics"]["cmax"] - b["metrics"]["cmax"]
                pair.update(left_cmax=a["metrics"]["cmax"], right_cmax=b["metrics"]["cmax"], delta=delta,
                            improvement_percent=100. * -delta / b["metrics"]["cmax"],
                            outcome="win" if delta < -EPS else "loss" if delta > EPS else "tie")
            pairs.append(pair)
    return pairs


def report(out):
    spec = checked(out, full=False)
    rows, failures = [], []
    for cell in spec["cells"]:
        dest = out / "runs" / cell["id"]
        if (dest / "failure.json").exists():
            failures.append(cell | read(dest / "failure.json"))
        elif (dest / "evidence.json").exists():
            rows.append(cell | read(dest / "evidence.json"))
    coverage = dict(expected=len(spec["cells"]), completed=len(rows), failed=len(failures),
        pending=len(spec["cells"]) - len(rows) - len(failures), valid=sum(bool(r["valid"]) for r in rows),
        budget_eligible=sum(bool(r["budget_eligible"]) for r in rows), formal=spec["formal"],
        expected_main=sum(c["suite"] == "ablation" for c in spec["cells"]),
        completed_main=sum(r["suite"] == "ablation" for r in rows),
        expected_preparations=sum(c["suite"] == "preparation" for c in spec["cells"]))
    pairs = paired_rows(spec, rows)
    grouped = {}
    for pair in pairs:
        grouped.setdefault((pair["case"], pair["total_budget"], pair["contrast"]), []).append(pair)
    by_case = []
    for (case, budget, contrast), group in sorted(grouped.items()):
        complete = [p for p in group if p["complete"]]
        row = dict(case=case, total_budget=budget, contrast=contrast, group=group[0]["group"],
                   optimal_control=group[0]["optimal_control"], expected=len(group), completed=len(complete),
                   win=sum(p["outcome"] == "win" for p in complete), tie=sum(p["outcome"] == "tie" for p in complete),
                   loss=sum(p["outcome"] == "loss" for p in complete))
        if complete:
            row.update(mean_delta=statistics.mean(p["delta"] for p in complete),
                       mean_improvement_percent=statistics.mean(p["improvement_percent"] for p in complete))
        by_case.append(row)
    # Aggregate only fully observed instances; keep groups/budgets/control separate.
    aggregate = {}
    for row in by_case:
        key = (row["group"], row["total_budget"], row["optimal_control"], row["contrast"])
        aggregate.setdefault(key, []).append(row)
    equal_weight = []
    for (group, budget, control, contrast), entries in sorted(aggregate.items()):
        complete = [r for r in entries if r["completed"] == r["expected"]]
        equal_weight.append(dict(group=group, total_budget=budget, optimal_control=control, contrast=contrast,
            expected_instances=len(entries), completed_instances=len(complete),
            mean_improvement_percent=statistics.mean(r["mean_improvement_percent"] for r in complete) if complete else None,
            inference_ready=len(complete) == len(entries)))
    for name, data in (("coverage", coverage), ("rows", rows), ("failures", failures),
                       ("paired_comparisons", pairs), ("paired_by_case", by_case), ("equal_instance_summary", equal_weight)):
        dump(out / "summary" / (name + ".json"), data)
    return coverage


def foreign_workers(own):
    import psutil
    found = []
    for process in psutil.process_iter(["pid", "name", "cmdline"]):
        if process.pid in own or "python" not in (process.info["name"] or "").lower():
            continue
        command = " ".join(process.info["cmdline"] or []).lower()
        if any(t in command for t in ("finite_budget", "formal_ablation", "readiness.py", "thesis_parallel",
               "large_schedule_experiments", "journal_support_experiments", "journal_gap_experiments",
               "paper_defaults.py", "run_cie_benchmarks.py", "run_experiments.py", "revalidate.py")):
            found.append(process.pid)
    return found


def run(out):
    import psutil
    spec = checked(out)
    lock = out / "supervisor.lock"
    fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    os.write(fd, str(os.getpid()).encode())
    os.close(fd)
    settings, active = spec["settings"], {}
    last_refresh, changed = -100., True
    cov = report(out)
    finished = set()
    for cell in spec["cells"]:
        dest = out / "runs" / cell["id"]
        if (dest / "evidence.json").exists() or (dest / "failure.json").exists():
            finished.add(cell["id"])
    try:
        while True:
            for cid, task in list(active.items()):
                if task["process"].poll() is None:
                    reason = ("RAM_guard" if psutil.virtual_memory().available < settings["min_available_gib"] * 1024**3 else
                              "wall_guard" if time.monotonic() - task["start"] > settings["wall_guard_seconds"] else None)
                    if reason:
                        task["process"].terminate()
                        task["process"].wait(timeout=30)
                        task["reason"] = reason
                if task["process"].poll() is not None:
                    task["log"].close()
                    evidence_path = out / "runs" / cid / "evidence.json"
                    if task["process"].returncode != 0 or not evidence_path.exists():
                        dump(out / "runs" / cid / "failure.json", dict(reason=task.get("reason", "worker_exit"),
                             exit_code=task["process"].returncode, ended_utc=stamp()))
                        print("FAILED " + cid, flush=True)
                    else:
                        evidence = read(evidence_path)
                        print(f'DONE {cid} A={evidence["metrics"]["cmax"]:.6f} eligible={evidence["budget_eligible"]}', flush=True)
                    finished.add(cid)
                    del active[cid]
                    changed = True
            if changed:
                cov = report(out)
                changed = False
            if not cov["pending"] and not active:
                dump(out / "finished.json", cov | dict(ended_utc=stamp()))
                print("FINISHED " + json.dumps(cov), flush=True)
                break
            foreign = foreign_workers({os.getpid()} | {t["process"].pid for t in active.values()})
            reason = "external_experiment_wait" if foreign else "ready"
            for cell in spec["cells"]:
                if foreign or len(active) >= settings["max_workers"]:
                    break
                cid, dest = cell["id"], out / "runs" / cell["id"]
                if cid in finished or cid in active:
                    continue
                if dest.exists():
                    raise RuntimeError("Preserved incomplete attempt requires inspection: " + str(dest))
                learned, prep = cell["method"] != "scip", cell["suite"] == "preparation"
                if learned and any(t["learned"] for t in active.values()):
                    continue
                if prep and any(t["prep"] for t in active.values()):
                    continue
                if cell.get("preparation"):
                    dependency = out / "runs" / cell["preparation"]
                    if (dependency / "failure.json").exists():
                        dump(dest / "failure.json", dict(reason="shared_preparation_failed", ended_utc=stamp()))
                        finished.add(cid)
                        changed = True
                        continue
                    if not (dependency / "evidence.json").exists():
                        continue
                    qualification = read(dependency / "evidence.json")
                    if not qualification["valid"] or not qualification["budget_eligible"]:
                        dump(dest / "failure.json", dict(reason="shared_preparation_ineligible", ended_utc=stamp()))
                        finished.add(cid)
                        changed = True
                        continue
                needed = settings["large_launch_gib"] if "n16" in cid else settings["launch_reserve_gib"]
                growth = 0.
                for task in active.values():
                    try:
                        rss = psutil.Process(task["process"].pid).memory_info().rss / 1024**3
                    except psutil.NoSuchProcess:
                        rss = 0.
                    growth += max(0., task["reservation"] - rss)
                if psutil.virtual_memory().available / 1024**3 - growth < needed:
                    reason = "waiting_for_RAM"
                    continue
                logdir = out / "logs"
                logdir.mkdir(exist_ok=True)
                logfile = (logdir / (cid + ".log")).open("wb")
                env = dict(os.environ, OMP_NUM_THREADS="1", MKL_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1")
                process = subprocess.Popen([sys.executable, "-X", "utf8", "-u", str(__file__), "worker",
                    "--campaign", str(out), "--cell", cid], cwd=ROOT, env=env, stdout=logfile, stderr=subprocess.STDOUT)
                active[cid] = dict(process=process, log=logfile, learned=learned, prep=prep,
                                   start=time.monotonic(), reservation=8. if "n16" in cid else 2.)
                dump(out / "launch_records" / (cid + ".json"), dict(started_utc=stamp(), pid=process.pid,
                     parallel_cells=list(active), available_gib=psutil.virtual_memory().available / 1024**3,
                     threads=1, gpu_device=0 if learned else None, external_experiments=[]))
                print("START " + cid, flush=True)
            if time.monotonic() - last_refresh >= settings["refresh_seconds"]:
                pending = [c for c in spec["cells"] if c["id"] not in finished]
                rows = read(out / "summary/rows.json")
                overheads = {}
                for row in rows:
                    overheads.setdefault(row["case"], []).append(max(0., row["wall_seconds"] - sum(s["seconds"] for s in row["stages"])))
                estimates = [(c, c["budget"] + statistics.median(overheads.get(c["case"], [60. if "n16" in c["case"] else 5.]))) for c in pending]
                eta = max(sum(t for _, t in estimates) / settings["max_workers"],
                          sum(t for c, t in estimates if c["method"] != "scip"),
                          sum(t for c, t in estimates if "n16" in c["case"]))
                free = psutil.virtual_memory().available / 1024**3
                progress = {}
                for cid in active:
                    path = out / "runs" / cid / "progress.json"
                    progress[cid] = read(path) if path.exists() else {"phase": "loading_or_building"}
                state = cov | dict(updated_utc=stamp(), supervisor_pid=os.getpid(), state=reason, active=list(active),
                      progress=progress, foreign_experiment_pids=foreign, available_gib=free,
                      remaining_nominal_solver_hours=sum(c["budget"] for c in pending)/3600.,
                      estimated_remaining_hours=eta/3600., eta_note="GPU jobs serialized; resource waits unknown; nominal full-budget estimate may fall when solves finish early.")
                dump(out / "live_status.json", state)
                print(f'complete={cov["completed"]}/{cov["expected"]} failed={cov["failed"]} running={len(active)} '
                      f'RAM={free:.1f} GiB ETA~{eta/3600:.2f} h | {reason}', flush=True)
                for cid, info in progress.items():
                    print("  " + cid + " " + json.dumps(info, ensure_ascii=False), flush=True)
                last_refresh = time.monotonic()
            time.sleep(1)
    finally:
        for cid, task in active.items():
            if task["process"].poll() is None:
                task["process"].terminate()
                task["process"].wait(timeout=30)
            task["log"].close()
            dump(out / "runs" / cid / "failure.json", dict(reason="foreground_supervisor_interrupted", ended_utc=stamp()))
        lock.unlink()


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("action", choices=("prepare", "prepare-smoke", "run", "worker", "report"))
    parser.add_argument("--campaign", required=True)
    parser.add_argument("--cell")
    args = parser.parse_args()
    out = Path(args.campaign).resolve()
    if not out.is_relative_to((JMS / "results").resolve()) or out == (JMS / "results").resolve():
        parser.error("Use an isolated subdirectory of JMS-version/results")
    if args.action in ("prepare", "prepare-smoke"):
        prepare(out, smoke=args.action == "prepare-smoke")
    elif args.action == "worker":
        worker(out, args.cell)
    elif args.action == "run":
        run(out)
    else:
        print(json.dumps(report(out)))


if __name__ == "__main__":
    try:
        main()
    except BaseException:
        traceback.print_exc()
        raise

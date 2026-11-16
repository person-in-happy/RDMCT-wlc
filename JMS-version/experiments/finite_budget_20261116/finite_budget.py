"""Independent, frozen finite-budget objective and cut-component comparisons.

Preparation is read-only with respect to old experiments and does not build or
solve models. The visible supervisor waits for unrelated research workers and
resource headroom. Every worker writes only its own new campaign directory.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import importlib
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
ROOT = HERE.parents[2]
JMS = ROOT / "JMS-version"
BACKENDS = {"D": JMS / "model4_pjob_nonprocessing_20261103",
            "E": JMS / "model4_pjob_nondecreasing_20261102"}
METHODS = ("scip", "hem", "feature_only", "proposed_no_structure", "proposed_greedy", "proposed")
WEIGHTS = (.01, .1, 1.)


def read(p):
    return json.loads(Path(p).read_text(encoding="utf-8-sig"))


def dump(p, data):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    tmp.replace(p)


def sha(p):
    h = hashlib.sha256()
    with Path(p).open("rb") as f:
        for block in iter(lambda: f.read(8 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def stamp():
    return datetime.now(timezone.utc).isoformat()


def physical_metrics(d):
    """Calculate actual event metrics, never unused epigraph variable values."""
    cfg = d["config"]
    events, waits, rhythms = {}, [], []
    for e in d["events"]:
        if "job" in e:
            events.setdefault(e["job"], {})[e["kind"]] = e
    for j in d["jobs"]:
        es = events[j["name"]]
        waits.extend((j["load_start"] - es["source_pick"]["end"] - cfg["vtr_travel"],
                      es["destination_put"]["start"] - j["unload_end"] - cfg["vtr_travel"]))
        if j["origin"] != "VS":
            legs = [("origin_pick", "al_put", cfg["atr_travel"]),
                    ("al_put", "al_pick", cfg["alignment"]),
                    ("al_pick", "upper_put", cfg["atr_travel"])] if "al_put" in es else [
                    ("origin_pick", "upper_put", cfg["atr_travel"])]
            legs += [("upper_put", "source_pick", cfg["pump"]),
                     ("destination_put", "lower_pick", cfg["vent"]),
                     ("lower_pick", "origin_put", cfg["atr_travel"])]
            waits.extend(es[b]["start"] - es[a]["end"] - dt for a, b, dt in legs)
    if min(waits, default=0) < -2e-4:
        raise ValueError("Negative physical waiting time")
    for c in cfg["chambers"]:
        cycles = sorted((v for v in d["cycles"] if v["chamber"] == c), key=lambda v: v["index"])
        for a, b, z in zip(cycles, cycles[1:], cycles[2:]):
            if (all(v["mode"] == "2x2" for v in (a, b, z)) and
                    set(a["pairs"]) & set(b["pairs"]) and set(b["pairs"]) & set(z["pairs"])):
                rhythms.append(abs(z["start"] - 2 * b["start"] + a["start"]))
    result = dict(cmax=max(j["loan_end"] for j in d["jobs"] if j["product"]),
                  wait_sum=sum(max(0., w) for w in waits), wait_max=max(0., *waits),
                  rhythm=sum(rhythms), rhythm_centers=len(rhythms))
    result["secondary"] = result["wait_sum"] + 10 * result["wait_max"] + 25 * result["rhythm"]
    return result


def source_records():
    small = JMS / "results/current_defaults_small_prepared_20261103/runs/n2_H3_mixed_dual__s1__scip"
    medium = JMS / "results/current_defaults_paper_20261104_075634/runs/n4_H10_mixed_dual__s1__scip"
    large = JMS / "review/gantt_current_model_20261111/n16_current_D_920"
    rhythm = JMS / "results/pjob_fifo_crossover_all_20261030_190540/runs/n16_H10_2x2_dual__s1__joint"
    return [dict(case="D_n2_mixed", backend="D", source=str(small / "phase1.json"), values=str(small / "variables_phase1.json")),
            dict(case="D_n4_mixed", backend="D", source=str(medium / "phase1.json"), values=str(medium / "variables_phase1.json")),
            dict(case="D_n16_4x1", backend="D", source=str(large / "result.json"), values=str(large / "variables.json")),
            dict(case="E_n16_2x2", backend="E", source=str(rhythm / "result.json"), values=str(rhythm / "variables_phase1.json"))]


def make_cells(cases):
    cells = []
    for c in cases:
        for seed in (1, 2, 3):
            for arm in ("primary", "two_stage", "joint_0.01", "joint_0.1", "joint_1"):
                cells.append(dict(case=c["case"], backend=c["backend"], suite="objectives", seed=seed,
                                  training_seed=1, method="scip", arm=arm, budget=300.,
                                  id=f'{c["case"]}__objectives__s{seed}__{arm}'))
    for c in cases:
        if c["case"] not in ("D_n4_mixed", "D_n16_4x1"):
            continue
        for seed in (1, 2, 3):
            prep_id = f'{c["case"]}__spbs__s{seed}'
            cells.append(dict(case=c["case"], backend="D", suite="preparation", seed=seed,
                              training_seed=1, method="scip", arm="spbs", budget=60., id=prep_id))
            for method in METHODS:
                for training_seed in ((1,) if method == "scip" else (1, 2, 3)):
                    cells.append(dict(case=c["case"], backend="D", suite="components", seed=seed,
                                      training_seed=training_seed, method=method, arm=method, budget=240.,
                                      preparation=prep_id,
                                      id=f'{c["case"]}__components__s{seed}__t{training_seed}__{method}'))
    return cells


def budgets(cell):
    if cell["arm"] == "two_stage":
        return (.9 * cell["budget"], .1 * cell["budget"])
    return (cell["budget"], 0.)


def configure_objective(x, arm, scales):
    if arm.startswith("joint_"):
        weight = float(arm.split("_", 1)[1])
        x.model.setObjective(x.cmax / scales["cmax"] + weight * x.secondary_objective / scales["secondary"], "minimize")
        return "normalized_weighted_objective"
    x.model.setObjective(x.primary_objective, "minimize")
    return "product_return_cmax"


def inventory():
    paths = [Path(__file__), HERE / "launch.ps1"]
    for backend in BACKENDS.values():
        paths.extend(backend.glob("*.py"))
    paths.extend(ROOT / n for n in ("scip_imports.py", "runtime_compat.py", "utils.py", "cutsel_agent_parallel.py", "environments.py", "global_const.py", "cie/code/run_cie_benchmarks.py"))
    return {str(p.relative_to(ROOT)): sha(p) for p in sorted(set(paths))}


def prepare(out):
    if out.exists():
        raise FileExistsError("Use a fresh campaign; existing observations are never overwritten")
    sources, cases = {}, source_records()
    for c in cases:
        d = read(c["source"])
        if not d.get("solutions") or not d.get("validation", {}).get("valid") or not d.get("original_model_check"):
            raise ValueError("Source certificate missing: " + c["source"])
        measured = physical_metrics(d)
        if c["backend"] == "E" and measured["rhythm_centers"] < 1:
            raise ValueError("Rhythm comparison requires actual nonzero-center coverage")
        c.update(config=d["config"], input_metrics=measured,
                 scales={"cmax": max(1., measured["cmax"]), "secondary": max(1., measured["secondary"])})
        for key in ("source", "values"):
            sources[c[key]] = sha(c[key])
    manifest_path = ROOT / "cie/results/repro_manifest/selected_checkpoint_manifest.csv"
    policies = [r for r in csv.DictReader(manifest_path.open(encoding="utf-8-sig"))
                if r["family"] in ("hem", "proposed", "feature_only") and int(r["training_seed"]) in (1, 2, 3)]
    sources[str(manifest_path)] = sha(manifest_path)
    for r in policies:
        p = ROOT / r["checkpoint"]
        if sha(p) != r["checkpoint_sha256"]:
            raise ValueError("Checkpoint hash mismatch")
        sources[str(p)] = r["checkpoint_sha256"]
    for n in ("cie/configs/cie_hem_train.json", "cie/configs/cie_proposed_inference.json"):
        sources[str(ROOT / n)] = sha(ROOT / n)
    spec = dict(created_utc=stamp(), cases=cases, cells=make_cells(cases), sources=sources,
                assets=inventory(), policies=policies, schema=1,
                environment=dict(python=sys.executable, python_version=sys.version,
                                 packages={name: version(name) for name in ("pyscipopt", "numpy", "torch", "psutil")}),
                settings=dict(max_workers=2, gpu_slots=1, threads=1, min_available_gib=8.,
                              launch_reserve_gib=12., wall_guard_seconds=3600., refresh_seconds=10.,
                              external_experiments_must_be_idle=True),
                timing="Nominal solver budgets, NOT end-to-end wall deadlines. Construction, model build, policy load and validation are recorded separately. SPBS 60 s is charged to EACH component arm; unused time is not transferred.",
                selection="Prospectively fixed D N=2 mixed, N=4 mixed and N=16 pure 4x1; E N=16 continuous-chain mechanism case. No selection by new algorithm advantage. D N=8 mixed has no qualified incumbent and remains excluded with that reason.",
                inference="D and E have different residency/horizon semantics and are reported separately. Joint-objective dual bounds are not Cmax lower bounds. Fewer rhythm centers or no centers do not prove better stability.")
    out.mkdir(parents=True)
    dump(out / "campaign.json", spec)
    dump(out / "contract.json", dict(campaign_sha256=sha(out / "campaign.json")))
    for rel in spec["assets"]:
        target = out / "frozen_code" / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / rel, target)
    report(out)
    print(f'PREPARED {len(spec["cells"])} cells; no solver started', flush=True)


def checked(out, full=True):
    spec = read(out / "campaign.json")
    if sha(out / "campaign.json") != read(out / "contract.json")["campaign_sha256"]:
        raise RuntimeError("Frozen protocol changed")
    if full:
        for p, expected in spec["assets"].items():
            if sha(ROOT / p) != expected:
                raise RuntimeError("Frozen code changed: " + p)
        for p, expected in spec["sources"].items():
            if sha(p) != expected:
                raise RuntimeError("Frozen input changed: " + p)
    return spec


def report(out):
    spec = checked(out, full=False)
    rows, failures = [], []
    for c in spec["cells"]:
        dest = out / "runs" / c["id"]
        if (dest / "evidence.json").exists():
            rows.append(c | read(dest / "evidence.json"))
        elif (dest / "failure.json").exists():
            failures.append(c | read(dest / "failure.json"))
    groups, eligible_groups = {}, {}
    for r in rows:
        if r.get("valid"):
            groups.setdefault((r["case"], r["suite"], r["arm"]), []).append(r)
            if r.get("budget_eligible"):
                eligible_groups.setdefault((r["case"], r["suite"], r["arm"]), []).append(r)
    table = []
    for (case, suite, arm), rs in sorted(groups.items()):
        row = dict(case=case, suite=suite, arm=arm, count=len(rs),
                   budget_eligible=sum(r["budget_eligible"] for r in rs))
        row.update({key: statistics.mean(r["metrics"][key] for r in rs)
                    for key in ("cmax", "wait_sum", "wait_max", "rhythm", "rhythm_centers", "secondary")})
        table.append(row)
    coverage = dict(expected=len(spec["cells"]), completed=len(rows), failed=len(failures),
                    pending=len(spec["cells"]) - len(rows) - len(failures),
                    valid=sum(bool(r.get("valid")) for r in rows),
                    budget_eligible=sum(bool(r.get("budget_eligible")) for r in rows))
    dump(out / "summary/coverage.json", coverage)
    dump(out / "summary/rows.json", rows)
    dump(out / "summary/failures.json", failures)
    dump(out / "summary/table.json", table)
    eligible = []
    for (case, suite, arm), rs in sorted(eligible_groups.items()):
        eligible.append(dict(case=case, suite=suite, arm=arm, count=len(rs),
             **{key: statistics.mean(r["metrics"][key] for r in rs)
                for key in ("cmax", "wait_sum", "wait_max", "rhythm", "rhythm_centers", "secondary")}))
    dump(out / "summary/budget_eligible_table.json", eligible)
    return coverage


def worker(out, cell_id):
    spec = checked(out)
    cell = next(c for c in spec["cells"] if c["id"] == cell_id)
    case = next(c for c in spec["cases"] if c["case"] == cell["case"])
    dest = out / "runs" / cell_id
    dest.mkdir(parents=True, exist_ok=False)
    sys.path.insert(0, str(BACKENDS[cell["backend"]]))
    sys.path.insert(1, str(ROOT))
    backend = importlib.import_module("model")
    validation = importlib.import_module("validate").validate
    algorithms = importlib.import_module("joint_algorithms")
    from scip_imports import scip
    import psutil
    started = time.monotonic()
    cfg = backend.Config(**case["config"])
    print("BUILD " + cell_id, flush=True)
    x = backend.Integrated(cfg)
    m = x.model
    build_seconds = time.monotonic() - started
    m.setIntParam("parallel/maxnthreads", 1)
    m.setIntParam("randomization/randomseedshift", cell["seed"])
    m.setLogfile(str(dest / "solver.log"))
    source_values = case["values"]
    if cell.get("preparation"):
        source_values = str(out / "runs" / cell["preparation"] / "variables.json")
        prep_evidence = read(out / "runs" / cell["preparation"] / "evidence.json")
        if not prep_evidence["valid"] or not prep_evidence["budget_eligible"]:
            raise ValueError("Shared preparation failed qualification")
    values = read(source_values)["values"]
    original_bounds = {v.name: (v.getLbOriginal(), v.getUbOriginal()) for v in m.getVars(transformed=False)}

    def assignment(vals):
        sol = m.createSol()
        for v in m.getVars(transformed=False):
            # No inferred/default assignment: all original variable values must exist.
            m.setSolVal(sol, v, vals[v.name])
        return sol

    def physical(sol):
        d = x.result(solution=sol)
        check = validation(d)
        if not check["valid"]:
            raise ValueError("Independent physical validation failed: " + str(check))
        d["validation"] = check
        return d, physical_metrics(d)

    warm = assignment(values)
    if not m.checkSol(warm, printreason=True, completely=True, original=True):
        raise ValueError("Common full assignment rejected by selected backend")
    source_data, input_metrics = physical(warm)
    # Tighten objective epigraphs without changing any physical event or structure.
    m.setSolVal(warm, x.cmax, input_metrics["cmax"])
    m.setSolVal(warm, x.max_wait, input_metrics["wait_max"])
    by_name = {v.name: v for v in m.getVars(transformed=False)}
    for c in cfg.chambers:
        for q in range(2, x.Q):
            v = by_name[f"rhythm_{c}_{q}"]
            active = m.getSolVal(warm, x.keep[c, q]) > .5 and m.getSolVal(warm, x.keep[c, q - 1]) > .5
            delta = abs(m.getSolVal(warm, x.cy.start[c, q] - 2 * x.cy.start[c, q - 1] + x.cy.start[c, q - 2])) if active else 0.
            m.setSolVal(warm, v, delta)
    if not m.checkSol(warm, printreason=True, completely=True, original=True):
        raise ValueError("Tightening epigraphs invalidated input")
    values = {v.name: m.getSolVal(warm, v) for v in m.getVars(transformed=False)}
    m.addSol(warm)
    dump(dest / "input.json", dict(path=source_values, sha256=sha(source_values), metrics=input_metrics,
                                   normalization=case["scales"], build_seconds=build_seconds,
                                   variables=m.getNVars(), constraints=m.getNConss()))
    stages, trace = [], [dict(allocated_budget_time=0., phase="original_input", **case["input_metrics"])]
    if cell["suite"] == "components":
        trace.append(dict(allocated_budget_time=60., phase="shared_spbs_input", **input_metrics))
    phase, offset, budget_stopped = "primary", (60. if cell["suite"] == "components" else 0.), False
    current_limit = cell["budget"]

    class Trace(scip.Eventhdlr):
        def eventinit(self):
            self.model.catchEvent(scip.SCIP_EVENTTYPE.BESTSOLFOUND, self)

        def eventexit(self):
            self.model.dropEvent(scip.SCIP_EVENTTYPE.BESTSOLFOUND, self)

        def eventexec(self, event):
            nonlocal budget_stopped
            elapsed = m.getSolvingTime()
            # Keep callback work inside the solver clock; no uncharged validation.
            sol = m.getBestSol()
            if sol is not None and elapsed <= current_limit + 1e-3:
                trace.append(dict(allocated_budget_time=offset + elapsed, phase=phase,
                                  cmax=m.getSolVal(sol, x.cmax),
                                  scalar_objective=m.getSolVal(sol, m.getObjective()),
                                  wall_seconds=time.monotonic() - started))
            if psutil.virtual_memory().available < spec.get("settings", {}).get("min_available_gib", 2.) * 1024**3:
                budget_stopped = True
                m.interruptSolve()

    recorder = Trace()
    # SPBS has five solver restarts; its own level record supplies the timeline.
    if cell["suite"] != "preparation":
        m.includeEventhdlr(recorder, "finite_budget_trace", "incumbent times")
    agent = None
    cap = None
    if cell["suite"] == "preparation":
        values, levels = algorithms.improve_skeleton(x, values, cell["budget"])
        for row in levels:
            stages.append(dict(phase="spbs_" + str(row["level"]), seconds=row["seconds"],
                               limit=cell["budget"] / 5, status=row["status"]))
        dump(dest / "spbs_levels.json", levels)
        scope = "product_return_cmax"
    else:
        load_start = time.monotonic()
        agent, policy = algorithms.install(m, cell["method"], cell["training_seed"])
        dump(dest / "policy.json", dict(record=policy, load_seconds=time.monotonic() - load_start))
        scope = configure_objective(x, cell["arm"], case["scales"])
        first, second = budgets(cell)
        current_limit = first
        m.setRealParam("limits/time", first)
        m.optimize()
        stages.append(dict(phase="primary", seconds=m.getSolvingTime(), limit=first,
                           status=str(m.getStatus()), bound_scope=scope, dual_bound=m.getDualbound()))
        if not m.getNSols():
            raise RuntimeError("Solver lost validated shared incumbent")
        best = m.getBestSol()
        primary_data, primary_metrics = physical(best)
        values = {v.name: m.getSolVal(best, v) for v in m.getVars(transformed=False)}
        dump(dest / "phase1.json", primary_data)
        if second > 0:
            m.freeTransform()
            for v in m.getVars(transformed=False):
                if v.vtype() != "CONTINUOUS" and not v.name.startswith("sync_"):
                    m.chgVarLb(v, round(values[v.name]))
                    m.chgVarUb(v, round(values[v.name]))
            cap = m.addCons(x.cmax <= primary_metrics["cmax"] + 1e-6, name="finite_budget_primary_cap")
            m.setObjective(x.secondary_objective, "minimize")
            phase, offset, current_limit = "secondary", first, second
            m.setRealParam("limits/time", second)
            sol = assignment(values)
            if not m.checkSol(sol, printreason=True, completely=True, original=True):
                raise ValueError("First-stage solution not feasible for refinement")
            m.addSol(sol)
            m.optimize()
            stages.append(dict(phase="secondary", seconds=m.getSolvingTime(), limit=second,
                               status=str(m.getStatus()), bound_scope="fixed_structure_secondary", dual_bound=m.getDualbound()))
            if m.getNSols():
                values = {v.name: m.getSolVal(m.getBestSol(), v) for v in m.getVars(transformed=False)}
    if agent is not None:
        dump(dest / "cutsel_telemetry.json", agent.get_telemetry())
    # Restore the unrestricted original feasible region before final acceptance.
    m.freeTransform()
    if cap is not None:
        m.delCons(cap)
    for v in m.getVars(transformed=False):
        lb, ub = original_bounds[v.name]
        m.chgVarLb(v, lb)
        m.chgVarUb(v, ub)
    m.setObjective(x.primary_objective, "minimize")
    final = assignment(values)
    valid = bool(m.checkSol(final, printreason=True, completely=True, original=True))
    data, measured = physical(final)
    valid &= data["validation"]["valid"]
    if cell["arm"] == "two_stage" and measured["cmax"] > primary_metrics["cmax"] + 2e-4:
        raise ValueError("Refinement worsened product completion")
    overrun = any(s["seconds"] > s["limit"] + 1. for s in stages)
    data.update(original_model_check=valid, experiment_scope=cell["suite"],
                benchmark_objective_scope=scope, global_optimality_claim=False)
    dump(dest / "result.json", data)
    dump(dest / "variables.json", dict(values=values))
    dump(dest / "trace.json", trace)
    evidence = dict(valid=valid, budget_eligible=bool(valid and not overrun and not budget_stopped),
                    completed_utc=stamp(), metrics=measured, input_metrics=input_metrics, stages=stages,
                    nominal_total=300. if cell["suite"] != "preparation" else 60.,
                    stage_overrun=overrun, resource_interruption=budget_stopped,
                    wall_seconds=time.monotonic() - started, build_seconds=build_seconds,
                    source_assignment_sha256=sha(source_values),
                    timeline_scope="Allocated solver-budget time; callback incumbents are solver reported, final assignment independently validated. Build/load/validation excluded from budget and included in wall time.",
                    native_scip_memory_limit_mb=m.getParam("limits/memory"),
                    result_sha256=sha(dest / "result.json"), assignment_sha256=sha(dest / "variables.json"))
    dump(dest / "evidence.json", evidence)
    m.freeSol(final)
    m.freeProb()
    if not valid:
        raise ValueError("Final original-model check failed")
    print("COMPLETE " + cell_id + " " + json.dumps(measured), flush=True)


def foreign_research_workers(own_pids):
    import psutil
    found = []
    for p in psutil.process_iter(["pid", "name", "cmdline"]):
        if p.pid in own_pids or "python" not in (p.info["name"] or "").lower():
            continue
        cmd = p.info["cmdline"] or []
        text = " ".join(cmd).lower()
        if ("finite_budget.py" not in text and any(t in text for t in (
                "large_schedule_experiments", "journal_support_experiments", "journal_gap_experiments",
                "paper_defaults.py", "run_cie_benchmarks.py", "run_experiments.py", "revalidate.py"))):
            found.append(p.pid)
    return found


def run(out):
    import psutil
    spec = checked(out)
    lock = out / "supervisor.lock"
    fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    os.write(fd, str(os.getpid()).encode())
    os.close(fd)
    active, started, last = {}, time.monotonic(), 0.
    settings = spec["settings"]
    try:
        while True:
            for cid, a in list(active.items()):
                if a["process"].poll() is None and psutil.virtual_memory().available < settings["min_available_gib"] * 1024**3:
                    # This guard can stop only this supervisor's NEW worker.
                    a["process"].terminate()
                    a["process"].wait(timeout=30)
                    a["reason"] = "new_worker_RAM_guard"
                if a["process"].poll() is None and time.monotonic() - a["start"] > settings["wall_guard_seconds"]:
                    a["process"].terminate()
                    a["process"].wait(timeout=30)
                    a["reason"] = "wall_guard"
                if a["process"].poll() is not None:
                    a["log"].close()
                    if a["process"].returncode != 0:
                        dump(out / "runs" / cid / "failure.json", dict(reason=a.get("reason", "worker_exit"),
                              exit_code=a["process"].returncode, ended_utc=stamp()))
                    del active[cid]
            cov = report(out)
            if not cov["pending"] and not active:
                dump(out / "finished.json", cov | dict(ended_utc=stamp()))
                print("FINISHED " + json.dumps(cov), flush=True)
                break
            foreign = foreign_research_workers({os.getpid()} | {a["process"].pid for a in active.values()})
            free = psutil.virtual_memory().available / 1024**3
            reason = ("existing_experiment_pids=" + str(foreign) if foreign else
                      "waiting_for_RAM" if free < settings["launch_reserve_gib"] else "ready")
            for cell in spec["cells"]:
                if reason != "ready" or len(active) >= settings["max_workers"]:
                    break
                cid, dest = cell["id"], out / "runs" / cell["id"]
                if cid in active or (dest / "evidence.json").exists() or (dest / "failure.json").exists():
                    continue
                if dest.exists():
                    raise RuntimeError("Unfinished attempt preserved; inspect before resuming: " + str(dest))
                if cell.get("preparation"):
                    dependency = out / "runs" / cell["preparation"]
                    if (dependency / "failure.json").exists():
                        dump(dest / "failure.json", dict(reason="shared_preparation_failed", ended_utc=stamp()))
                        continue
                    if not (dependency / "evidence.json").exists():
                        continue
                    qualification = read(dependency / "evidence.json")
                    if not qualification["valid"] or not qualification["budget_eligible"]:
                        dump(dest / "failure.json", dict(reason="shared_preparation_ineligible", ended_utc=stamp()))
                        continue
                learned = cell["method"] != "scip"
                if learned and any(a["learned"] for a in active.values()):
                    continue
                # Large models need extra free RAM; small independent CPU runs can overlap.
                needed = settings["launch_reserve_gib"] + (8. if "n16" in cid else 0.)
                growth = 0.
                for a in active.values():
                    try:
                        rss = psutil.Process(a["process"].pid).memory_info().rss / 1024**3
                    except psutil.NoSuchProcess:
                        rss = 0.
                    growth += max(0., a["reservation"] - rss)
                if psutil.virtual_memory().available / 1024**3 - growth < needed:
                    reason = "waiting_for_large_model_RAM" if "n16" in cid else "waiting_for_RAM"
                    continue
                logdir = out / "logs"
                logdir.mkdir(exist_ok=True)
                log = (logdir / (cid + ".log")).open("wb")
                env = dict(os.environ, OMP_NUM_THREADS="1", MKL_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1")
                proc = subprocess.Popen([sys.executable, "-X", "utf8", "-u", str(__file__), "worker", "--campaign", str(out), "--cell", cid],
                                        cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
                active[cid] = dict(process=proc, log=log, learned=learned, start=time.monotonic(),
                                   reservation=8. if "n16" in cid else 2.)
                dump(out / "launch_records" / (cid + ".json"), dict(started_utc=stamp(), pid=proc.pid,
                     parallel_cells=list(active), available_gib=psutil.virtual_memory().available / 1024**3,
                     threads=1, gpu_device=0 if learned else None, external_experiments=[]))
                print("START " + cid, flush=True)
            if time.monotonic() - last >= settings["refresh_seconds"]:
                pending = [c for c in spec["cells"] if not (out / "runs" / c["id"] / "evidence.json").exists()
                           and not (out / "runs" / c["id"] / "failure.json").exists()]
                remaining_seconds = sum(c["budget"] for c in pending)
                # Rough lane estimate, updated with observed build/validation costs.
                observed = read(out / "summary/rows.json")
                overheads = {}
                for r in observed:
                    overheads.setdefault(r["case"], []).append(max(0., r["wall_seconds"] - sum(s["seconds"] for s in r["stages"])))
                estimates = [(c, c["budget"] + statistics.median(overheads.get(c["case"], [60. if "n16" in c["case"] else 5.]))) for c in pending]
                eta = max(sum(t for _, t in estimates)/settings["max_workers"],
                          sum(t for c, t in estimates if c["method"] != "scip"),
                          sum(t for c, t in estimates if "n16" in c["case"]))
                state = cov | dict(updated_utc=stamp(), supervisor_pid=os.getpid(), state=reason,
                                   active=list(active), foreign_experiment_pids=foreign,
                                   available_gib=free, remaining_nominal_solver_hours=remaining_seconds / 3600,
                                   estimated_remaining_hours=eta / 3600,
                                   eta_note="Resource-wait duration unknown; solve-hour sum excludes builds and validation.")
                dump(out / "live_status.json", state)
                print(f'complete={cov["completed"]}/{cov["expected"]} failed={cov["failed"]} running={len(active)} '
                      f'RAM={free:.1f} GiB ETA~{eta/3600:.2f} h remaining_solver_budget~{remaining_seconds/3600:.2f} h | {reason}', flush=True)
                last = time.monotonic()
            time.sleep(1)
    finally:
        for cid, a in active.items():
            if a["process"].poll() is None:
                a["process"].terminate()
                a["process"].wait(timeout=30)
            a["log"].close()
            dump(out / "runs" / cid / "failure.json", dict(reason="foreground_supervisor_interrupted", ended_utc=stamp()))
        lock.unlink()


def main():
    p = argparse.ArgumentParser(__doc__)
    p.add_argument("action", choices=("prepare", "run", "report", "worker"))
    p.add_argument("--campaign", required=True)
    p.add_argument("--cell")
    a = p.parse_args()
    out = Path(a.campaign).resolve()
    if not out.is_relative_to((JMS / "results").resolve()) or out == (JMS / "results").resolve():
        p.error("Use an isolated subdirectory of JMS-version/results")
    try:
        if a.action == "prepare":
            prepare(out)
        elif a.action == "run":
            run(out)
        elif a.action == "worker":
            worker(out, a.cell)
        else:
            print(json.dumps(report(out)))
    except BaseException:
        traceback.print_exc()
        raise


if __name__ == "__main__":
    main()

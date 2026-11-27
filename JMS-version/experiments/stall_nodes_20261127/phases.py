"""The two native SCIP phases of RL-DMCT with optional incumbent stall limits."""
import math
from dataclasses import replace
from pathlib import Path
import sys
import time

JMS = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(JMS / "experiments" / name) for name in
                ("terminal_unload_20261125", "square_residence_20261125", "component_gap_restore_20261119")]
from extended_model import Config, Integrated
from score import metrics
from seed import constrain_seed, release_fixed, normalize_schedule
from validate import validate

CHECK_TOL = 2e-4  # Same tolerance as the independent event replay.
CAP_TOL = 1e-6


def relative_gap(upper, lower):
    """Return the manuscript's relative gap, using None for an infinite gap."""
    if not (math.isfinite(upper) and math.isfinite(lower)) or lower > upper:
        return None
    if upper == lower == 0:
        return 0.
    if upper * lower <= 0:
        return None
    return abs(upper - lower) / min(abs(upper), abs(lower))


def physical_bound(stage, cfg):
    n = sum(sum(port.values()) for port in cfg.load_ports.values())
    chain = sum(port.get("2x2", 0) for port in cfg.load_ports.values())
    if stage == "B":
        # The optional product-first terminal unload is legal here.
        return (2 * cfg.rotation + 2 * cfg.handling) * chain / n
    a, t = cfg.atr_handling, cfg.atr_travel
    exposure = min(duration for count, duration in ((chain, 2 * cfg.mix_time),
                   (n - chain, cfg.full_time)) if count)
    after_aligner = (2 * t + 3 * a + 4 * cfg.handling + 2 * cfg.vtr_travel
                     + cfg.pump + exposure + cfg.vent)
    return a + t + n * (2 * a + cfg.alignment) + after_aligner


def checked_assignment(x, values):
    model = x.model
    sol = model.createSol()
    for var in model.getVars(transformed=False):
        model.setSolVal(sol, var, values.get(var.name, 0.))
    if not model.checkSol(sol, original=True, completely=True, printreason=False):
        model.freeSol(sol)
        raise ValueError("Assignment violates the extended model's original constraints")
    return sol


def values_of(x, sol):
    return {v.name: x.model.getSolVal(sol, v) for v in x.model.getVars(transformed=False)}


def verify_events(schedule):
    checked = validate(schedule)
    if not checked["valid"]:
        raise ValueError(f"Physical event replay failed: {checked['errors'][:3]}")
    measured = metrics(schedule)
    if abs(checked["product_return_cmax"] - measured["cmax"]) > CHECK_TOL:
        raise ValueError("Product-return time disagrees with the event replay")
    return checked, measured


def check_start_matches(x, sol, schedule):
    decoded = x.result(solution=sol)
    _, measured = verify_events(decoded)
    expected = {e["name"]: e for e in schedule["events"]}
    actual = {e["name"]: e for e in decoded["events"]}
    if expected.keys() != actual.keys() or any(
        a["location"] != expected[name]["location"]
        or any(abs(a[t] - expected[name][t]) > CHECK_TOL for t in ("start", "end"))
        for name, a in actual.items()
    ):
        raise ValueError("Assignment and starting schedule describe different physical events")
    def pairs_by_id(data):
        return {p["id"]: (p["mode"], p["chamber"], p["members"]) for p in data["pairs"]}
    if pairs_by_id(decoded) != pairs_by_id(schedule):
        raise ValueError("Assignment and starting schedule have different wafer pairs")
    if any(abs(measured[k] - v) > CHECK_TOL for k, v in metrics(schedule).items()):
        raise ValueError("Assignment and starting schedule have different physical scores")
    return decoded, measured


def lift_schedule(x, schedule):
    # Complete hidden resource-order/slot bits with all physical event times fixed.
    # rot_priority_* events in an input schedule select the product-first unload.
    model = x.model
    reference = normalize_schedule(x.cfg, schedule)
    reference["cmax"] = metrics(reference)["cmax"]
    fixed = constrain_seed(x, reference, times=True)
    model.setIntParam("limits/solutions", 1)
    model.optimize()
    if str(model.getStatus()) == "userinterrupt":
        raise KeyboardInterrupt
    best = model.getBestSol()
    if best is None:
        raise ValueError(f"Cannot lift the starting events into the extended model ({model.getStatus()})")
    values = values_of(x, best)
    model.freeTransform()
    release_fixed(model, fixed)
    model.setIntParam("limits/solutions", -1)
    return values, reference


def process_auxiliaries(x, schedule, measured):
    """Exact epigraph/start variables for extended_model.minimize_process_score."""
    by_pair = {p["id"]: p["mode"] for p in schedule["pairs"]}
    durations = {"4x1": x.cfg.full_time, "2x2": 2 * x.cfg.mix_time}
    by_mode = {}
    for job in schedule["jobs"]:
        if job["product"]:
            mode = by_pair[job["pair"]]
            dwell = job["unload_start"] - job["load_end"] - durations[mode]
            by_mode.setdefault(mode, []).append(max(0., dwell))
    values = {"residence_spread": measured["residence_range"],
              "spread_penalty": measured["square_penalty"]}
    for mode, dwells in by_mode.items():
        values[f"res_low_{mode}"] = min(dwells)
        values[f"res_high_{mode}"] = max(dwells)
    previous = {}
    for cycle in sorted(schedule["cycles"], key=lambda c: (c["chamber"], c["index"])):
        chamber, q = cycle["chamber"], cycle["index"]
        if cycle["mode"] == "clean":
            values[f"unused_{chamber}_{q}"] = x.cfg.cleaning_interval - previous[chamber]
        previous[chamber] = cycle["counter"]
    return values


def run_phase(stage, schedule, *, assignment=None, gap, stall_nodes, seed=1, training_seed=1,
              spbs_seconds=0., seconds=None, full_domain=False, search_clock=None):
    """Return (audited stage record, decoded schedule, sparse native assignment)."""
    if stage not in ("A", "B") or (stage == "B" and assignment is None):
        raise ValueError("Stage B requires the native stage A assignment")
    if stall_nodes is not None and (type(stall_nodes) is not int
                                    or not (stall_nodes == -1 or 1 <= stall_nodes < 2**63)):
        raise ValueError("stall_nodes must be positive or disabled with -1/None")
    if not math.isfinite(gap) or gap < 0 or not math.isfinite(spbs_seconds) or spbs_seconds < 0:
        raise ValueError("Invalid gap or SPBS budget")
    if seconds is not None and (not math.isfinite(seconds) or seconds < 0):
        raise ValueError("Stage time limit must be finite and nonnegative")
    started = time.monotonic()
    verify_events(schedule)
    cfg = Config(**schedule["config"])
    if stage == "A" and full_domain:
        cfg = replace(cfg, max_pairs=0, max_cycles=0)
    x = Integrated(cfg)
    model = x.model
    model.setIntParam("parallel/maxnthreads", 1)
    model.setIntParam("lp/threads", 1)
    model.setIntParam("randomization/randomseedshift", seed)
    model.setIntParam("timing/clocktype", 2)
    model.setRealParam("numerics/feastol", 1e-8)
    try:
        return solve(x, stage, schedule, assignment, gap, stall_nodes, seed, training_seed,
                     spbs_seconds, seconds, search_clock, started)
    finally:
        model.freeProb()


def solve(x, stage, schedule, assignment, gap, stall_nodes, seed, training_seed,
          spbs_seconds, seconds, search_clock, started):
    model = x.model
    # B uses the actual native handoff, including resource-order decisions.
    if assignment is None:
        values, schedule = lift_schedule(x, schedule)
    else:
        values = dict(assignment)
    sol = checked_assignment(x, values)
    schedule, initial = check_start_matches(x, sol, schedule)
    values = values_of(x, sol)
    model.freeSol(sol)
    values[x.cmax.name] = initial["cmax"]
    trace = []
    if stage == "A" and spbs_seconds:
        from joint_algorithms import improve_skeleton
        values, trace = improve_skeleton(x, values, spbs_seconds)
        if any(row["status"] == "userinterrupt" for row in trace):
            raise KeyboardInterrupt
        sol = checked_assignment(x, values)
        schedule = x.result(solution=sol)
        _, initial = verify_events(schedule)
        model.freeSol(sol)
        values[x.cmax.name] = initial["cmax"]

    cap = None
    if stage == "B":
        cap = initial["cmax"]
        model.addCons(x.cmax <= cap + CAP_TOL)
        for v in model.getVars(transformed=False):
            if v.vtype() != "CONTINUOUS" and not v.name.startswith("sync_"):
                fixed_value = round(values[v.name])
                model.chgVarLb(v, fixed_value)
                model.chgVarUb(v, fixed_value)
        objective = x.minimize_process_score()
        values.update(process_auxiliaries(x, schedule, initial))
    else:
        objective = x.cmax
        model.setObjective(objective, "minimize")

    key = "cmax" if stage == "A" else "secondary"
    upper, lower = initial[key], physical_bound(stage, x.cfg)
    if lower > upper + CHECK_TOL:
        raise ValueError("Physical lower bound exceeds the verified start")
    model.addCons(objective >= lower)
    warm = checked_assignment(x, values)
    if abs(model.getSolObjVal(warm) - upper) > CHECK_TOL:
        raise ValueError("Native objective differs from the physical starting score")
    stored = model.addSol(warm)
    if not stored and model.getNSols() == 0:
        raise RuntimeError("SCIP did not retain the verified starting incumbent")

    gap_value = relative_gap(upper, min(upper, lower))
    native_status = None
    policy, agent = None, None
    nodes, solver_seconds = 0, 0.
    raw_dual = None
    raw_primal = None
    model.setLongintParam("limits/stallnodes", -1 if stall_nodes is None else stall_nodes)
    model.setRealParam("limits/gap", gap)
    model.setRealParam("limits/absgap", 0.)
    model.setRealParam("limits/time", model.infinity() if seconds is None else seconds)
    comparison_gap = gap * (1. + 1e-12)
    if gap_value is None or gap_value > comparison_gap:
        if seconds != 0:
            if stage == "A":
                from component import POLICIES, policy_on_cpu
                agent, policy = policy_on_cpu(model, "proposed", POLICIES["full"], seed, training_seed)
            if search_clock is not None:
                search_clock(True)
            try:
                model.optimize()
            finally:
                if search_clock is not None:
                    search_clock(False)
            native_status = str(model.getStatus())
            if native_status == "userinterrupt":
                raise KeyboardInterrupt
            nodes, solver_seconds = model.getNTotalNodes(), model.getSolvingTime()
            best = model.getBestSol()
            if best is None:
                raise RuntimeError(f"Verified incumbent lost in stage {stage}: {native_status}")
            raw_primal = model.getPrimalbound()
            dual = model.getDualbound()
            if math.isfinite(dual) and not model.isInfinity(abs(dual)):
                raw_dual = dual
                lower = max(lower, dual)
            values = values_of(x, best)
            model.freeTransform()

    # Final restartable assignment corresponds to the physical event score. If
    # the epigraph or Cmax has slack, tighten only those auxiliary variables.
    final = checked_assignment(x, values)
    schedule = x.result(solution=final)
    model.freeSol(final)
    replay, measured = verify_events(schedule)
    upper = measured[key]
    if upper > initial[key] + CHECK_TOL or (cap is not None and measured["cmax"] > cap + CAP_TOL + 1e-8):
        raise ValueError("Returned schedule violates the handoff cap or worsens its incumbent")
    if raw_primal is not None and raw_primal + CHECK_TOL < upper:
        raise ValueError("Reported primal bound is better than its physical schedule")
    values[x.cmax.name] = schedule["cmax"] = measured["cmax"]
    if stage == "B":
        values.update(process_auxiliaries(x, schedule, measured))
    final = checked_assignment(x, values)
    if abs(model.getSolObjVal(final) - upper) > CHECK_TOL:
        raise ValueError("Polished assignment and physical objective disagree")
    model.freeSol(final)
    if lower > upper + CHECK_TOL:
        raise ValueError("Stage dual bound exceeds the verified physical incumbent")
    lower = min(upper, lower)
    gap_value = relative_gap(upper, lower)
    gap_met = gap_value is not None and gap_value <= comparison_gap
    if gap_met:
        reason = "gap"
    elif native_status == "stallnodelimit":
        reason = "stagnation"
    elif native_status is None and seconds == 0:
        reason = "timelimit"
    else:
        reason = native_status
    scope = ("fixed handoff structure and product-return cap" if stage == "B" else
             "input candidate domain" if x.bounded else "full extended model")
    record = dict(stage=stage, native_status=native_status, stop_reason=reason, gap_met=gap_met,
                  upper=upper, lower=lower, gap=gap_value, target_gap=gap,
                  physical_lower=physical_bound(stage, x.cfg), native_primal=raw_primal, native_dual=raw_dual,
                  stall_nodes=stall_nodes, nodes=nodes, solver_seconds=solver_seconds,
                  wall_seconds=time.monotonic()-started, metrics=measured, initial_metrics=initial,
                  scope=scope, restricted_candidate_bounds=x.bounded, cmax_cap=cap,
                  seed=seed, policy=policy, policy_calls=agent.get_telemetry()["callback_calls"] if agent else 0,
                  spbs=trace, validation=replay, original_rows_checked=model.getNConss(transformed=False))
    return record, schedule, {name: val for name, val in values.items() if val != 0}

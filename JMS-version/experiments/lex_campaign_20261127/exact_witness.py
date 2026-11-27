"""Post-run integer-time feasibility witness for a small-case double-bound endpoint."""
import argparse
import copy
from fractions import Fraction
import gzip
import hashlib
import json
from math import floor
from pathlib import Path
import sys
import time
import uuid

from campaign_audit import CASES, PROOF_TOL, audit_endpoint, audit_schedule, read
from replay_events import raw_objectives

HERE = Path(__file__).resolve().parent
JMS = HERE.parents[1]
SMALL = {"n2_h3", "n4_h3", "n8_h3"}
JOB_TIMES = ("loan_start", "loan_end", "load_start", "load_end", "unload_start", "unload_end")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def from_current_case(folder, case, source):
    state = read(folder / "case.json")
    if state["key"] != case:
        raise ValueError("Case folder and requested instance differ")
    if source is None:
        source = state.get("final_endpoint")
        if not source:
            return None
    if isinstance(source, dict):
        data = source
    else:
        path = (folder / source).resolve()
        if path.name == "endpoint.json" and path.is_relative_to(folder / "artifacts"):
            return path
        if path.name == "schedule.json.gz" and path.is_relative_to(folder / "artifacts"):
            return path.with_name("endpoint.json")
        data = read(path)
    # A detached schedule must also match a raw artifact from this run.
    preferred = list(filter(None, [state.get("final_endpoint")] +
                     [s.get("endpoint") for s in state["stages"].values()]))
    candidates = [folder / pointer for pointer in preferred]
    candidates.extend((folder / "artifacts").glob("*/endpoint.json"))
    for candidate in dict.fromkeys(candidates):
        if read(candidate.with_name("schedule.json.gz")) == data:
            return candidate
    raise ValueError("Supplied schedule is absent from this run's raw artifacts")


def integer_schedule(raw):
    schedule = copy.deepcopy(raw)
    for row in schedule["events"] + schedule["cycles"]:
        for key in ("start", "end"):
            row[key] = floor(row[key] + 1e-5)
    for job in schedule["jobs"]:
        for key in JOB_TIMES:
            job[key] = floor(job[key] + 1e-5)
    schedule["cmax"] = max(j["loan_end"] for j in schedule["jobs"] if j["product"])
    return schedule


def exact_scores(schedule):
    data = copy.deepcopy(schedule)
    for row in data["events"] + data["cycles"]:
        for key in ("start", "end"):
            if type(row[key]) != int:
                raise ValueError("Exact event replay requires integer event and cycle times")
            row[key] = Fraction(row[key])
    measured = raw_objectives(data)
    return {key: Fraction(val) for key, val in measured.items()}


def native_completion(schedule):
    sys.path.insert(0, str(HERE.parent / "stall_nodes_20261127"))
    from phases import (Config, Integrated, checked_assignment, check_start_matches,
                        constrain_seed, normalize_schedule, process_auxiliaries, release_fixed,
                        values_of, verify_events)
    from grippers import HANDS

    cfg = Config(**schedule["config"])
    x = Integrated(cfg)
    m = x.model
    try:
        m.setIntParam("parallel/maxnthreads", 1)
        m.setIntParam("lp/threads", 1)
        m.setRealParam("numerics/feastol", 1e-9)
        canon = normalize_schedule(cfg, schedule)
        _, score = verify_events(canon)
        fixed = constrain_seed(x, canon, times=True)
        # constrain_seed fixes times and material structure. Also fix every
        # reported physical hand, so the native solution realizes those labels.
        for job in canon["jobs"]:
            for leg in ("in", "out"):
                hand = job.get("vtr_hand_" + leg)
                if hand is not None:
                    var = x.vtr_hands[job["name"] + "_" + leg, HANDS.index(hand)]
                    fixed.append((var, var.getLbOriginal(), var.getUbOriginal()))
                    m.chgVarLb(var, 1)
                    m.chgVarUb(var, 1)
        m.setIntParam("limits/solutions", 1)
        m.optimize()
        native_status = str(m.getStatus())
        solution = m.getBestSol()
        if solution is None:
            raise ValueError(f"No native solution at the fixed integer event times: {native_status}")
        values = values_of(x, solution)
        m.freeTransform()
        release_fixed(m, fixed)
        objective = x.minimize_process_score()
        values.update(process_auxiliaries(x, canon, score))
        m.addCons(x.cmax <= score["cmax"], name="audited_integer_makespan_cap")
        m.addCons(objective <= score["secondary"], name="audited_integer_secondary_cap")
        witness = checked_assignment(x, values)
        try:
            decoded, _ = check_start_matches(x, witness, canon)
            events = {e["name"]: (e["start"], e["end"]) for e in decoded["events"]}
            if any(events[e["name"]] != (e["start"], e["end"]) for e in canon["events"]):
                raise ValueError("Native assignment differs from an integer operation time")
            cycles = {(c["chamber"], c["index"]): c for c in decoded["cycles"]}
            for c in canon["cycles"]:
                actual = cycles[c["chamber"], c["index"]]
                if any(actual[k] != c[k] for k in ("start", "end", "mode", "front", "counter")):
                    raise ValueError("Native assignment differs from the fixed integer cycle")
            native_objective = m.getSolObjVal(witness)
            if abs(native_objective - score["secondary"]) > 1e-9:
                raise ValueError("Native quadratic objective disagrees with physical event score")
        finally:
            m.freeSol(witness)
        return ({k: v for k, v in values.items() if v != 0.},
                dict(feasible=True, fixed_time_status=native_status,
                     feastol=1e-9, checked_original_rows=m.getNConss(transformed=False),
                     candidate_pairs=x.P, cycles_per_chamber=x.Q, objective=native_objective,
                     inputs="normalized interchangeable pair/dummy labels; all physical times and VTR hands fixed"))
    finally:
        m.freeProb()


def save(path, data):
    raw = (json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf8")
    tmp = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    tmp.write_bytes(gzip.compress(raw, mtime=0) if path.suffix == ".gz" else raw)
    tmp.replace(path)


def build_witness(folder, case, source=None):
    """Return audit record or None when the raw objectives do not meet both bounds."""
    if case not in SMALL:
        return None
    folder = Path(folder).resolve()
    src = from_current_case(folder, case, source)
    if src is None:
        return None
    pointer = src.relative_to(folder).as_posix()
    observed = audit_endpoint(folder, pointer, case)
    spec = read(folder / "spec.json")
    target = (CASES[case][2], 3)
    if (spec["lb_A"], spec["lb_B"]) != target:
        raise ValueError("Small-case registered bounds disagree with the campaign audit")
    if any(abs(observed[k]-goal) > PROOF_TOL for k, goal in zip(("cmax", "secondary"), target)):
        return None
    for proof in spec["proof_sources"]:
        if digest(JMS / proof["path"]) != proof["sha256"]:
            raise ValueError(f"Registered bound/model source has changed: {proof['path']}")
    base = folder / "post_audit" / observed["schedule_sha256"]
    record = base / "record.json"
    program = digest(Path(__file__))
    raw = read(src.with_name("schedule.json.gz"))
    rounded = integer_schedule(raw)
    integer_audit = audit_schedule(rounded, case)
    exact = exact_scores(rounded)
    if (exact["cmax"], exact["secondary"]) != target:
        raise ValueError("Uniform integer-time flooring does not attain both exact bounds")
    if record.exists():
        existing = read(record)
        if (existing["program_sha256"] != program or existing["source"]["schedule_sha256"]
            != observed["schedule_sha256"] or read(base / "schedule.json.gz") != rounded
            or any(digest(base / name) != h for name, h in existing["hashes"].items())):
            raise ValueError("Cached exact witness does not match this source or audit program")
        return existing
    started = time.monotonic()
    assignment, native = native_completion(rounded)
    base.mkdir(parents=True, exist_ok=True)
    save(base / "schedule.json.gz", rounded)
    save(base / "assignment.json.gz", assignment)
    report = dict(case=case, path=record.relative_to(folder).as_posix(), source=observed,
                  source_endpoint_sha256=digest(src), program_sha256=program,
                  method="floor(t + 1e-5) applied uniformly to every event, cycle and job timestamp",
                  method_reference="experiments/terminal_unload_20261125/replay_events.py:eight_ideal",
                  exact_objectives={k: dict(numerator=v.numerator, denominator=v.denominator)
                                    for k, v in exact.items()},
                  metrics=integer_audit, native=native, proof_sources=spec["proof_sources"],
                  native_verification_seconds=time.monotonic()-started,
                  hashes={name: digest(base / name) for name in ("schedule.json.gz", "assignment.json.gz")})
    save(record, report)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder", type=Path)
    parser.add_argument("case", choices=sorted(SMALL))
    parser.add_argument("source", nargs="?")
    args = parser.parse_args()
    row = build_witness(args.folder, args.case, args.source)
    print(json.dumps({"witness": row["path"], "metrics": row["metrics"]} if row else {"witness": None}))

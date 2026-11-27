"""Substitute a sparse primal witness into every row emitted by the original D model.

The numeric adapter consumes rows as they are emitted. A native SCIP check on
a smaller mixed/cleaning instance checks its row/variable counts and witness.
The 75-product search and the input schedule are read-only in this process.
"""
import argparse
from collections import Counter, defaultdict
from contextlib import ExitStack
import gc
import gzip
import json
import math
from pathlib import Path
import sys
import time
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import run
import joint_chamber_cycle_model
import joint_pairing_model
import model
from grippers import HANDS
from pjobs import task_for_product
from resources import limit_process, peers, sample, wait_for_headroom


def witness(data):
    """The value for every unnamed entry is zero. Only emitted names are saved."""
    cfg = model.Config(**data["config"])
    pairs = {p["id"]: p for p in data["pairs"]}
    events = {e["name"]: e for e in data["events"]}
    jobs = data["jobs"]
    groups = task_for_product(cfg)
    v = {"Cmax": data["cmax"], "max_wait": run.physical_metrics(data)["wait_max"]}
    resources = defaultdict(list)
    for p, pair in pairs.items():
        products = [w for w in pair["members"] if w in groups]
        v[f"jp_active_{p}"] = v[f"jp_mode_{p}_{pair['mode']}"] = v[f"jp_chamber_{p}_{pair['chamber']}"] = 1
        v[f"jc_product_pair_{p}"] = bool(products)
        v[f"jc_mixed_product_{p}"] = bool(products) and pair["mode"] == "2x2"
        v[f"pj_product_{p}_1"] = len(products) == 2
        for r, w in enumerate(pair["members"]):
            if w in groups:
                v[f"pj_x_{groups[w].identifier}_{p}_{r}"] = 1
            else:
                v[f"jp_identity_{w}_{p}_{r}"] = 1
                v[f"identity_code_{p}_{r}"] = int(w[1:])
    for ch in cfg.chambers:
        cycles = sorted((c for c in data["cycles"] if c["chamber"] == ch), key=lambda c: c["index"])
        before, carry_before = set(), False
        for q, cy in enumerate(cycles):
            current = set(cy["pairs"])
            following = set(cycles[q+1]["pairs"]) if q+1 < len(cycles) else set()
            carry, tail = bool(current & before), not bool(current & following)
            v[f"jc_kind_{ch}_{q}_{cy['mode']}"] = 1
            v[f"jc_start_{ch}_{q}"], v[f"jc_count_{ch}_{q}"] = cy["start"], cy["counter"]
            v[f"carry_{ch}_{q}"], v[f"tail_{ch}_{q}"] = carry, tail
            for p in current:
                v[f"jc_occ_{p}_{ch}_{q}"] = 1
                v[f"jc_first_{p}_{ch}_{q}"] = p not in before
                v[f"jc_po_{p}_{ch}_{q}"] = any(w in groups for w in pairs[p]["members"])
                v[f"front_{p}_{ch}_{q}"] = p == cy["front"]
                v[f"bt_{p}_{ch}_{q}"] = tail and p != cy["front"]
            unloaded = current-following
            v[f"empty_boundary_{ch}_{q+1}"] = max(events[f"unload_{p}"]["end"] for p in unloaded)
            if not tail:
                v[f"exchange_boundary_{ch}_{q+1}"] = v[f"empty_boundary_{ch}_{q+1}"]
            if q >= 2 and carry and carry_before:
                v[f"rhythm_active_{ch}_{q}"] = 1
                v[f"rhythm_{ch}_{q}"] = abs(cy["start"] - 2*cycles[q-1]["start"] + cycles[q-2]["start"])
            before, carry_before = current, carry
    for e in events.values():
        v[e["name"]+"_s"] = e["start"]
    # The model may order simultaneous same-pair pickups or placements either
    # way in its capacity prefix. Both have the same signed capacity change.
    job_pair = {job["name"]: job["pair"] for job in jobs}
    for robot in ("ATR", "VTR"):
        ordered = sorted((e for e in events.values() if e["robot"] == robot), key=lambda e: e["start"])
        for i, e in enumerate(ordered):
            for later in ordered[i+1:]:
                if e["end"] > later["start"] + 1e-8:
                    pair = job_pair.get(e.get("job"))
                    compatible = (pair is not None and pair == job_pair.get(later.get("job"))
                                  and e["job"] != later["job"]
                                  and e["kind"] == later["kind"]
                                  and e["kind"] not in ("al_put", "al_pick")
                                  and e["location"] == later["location"]
                                  and (e["start"], e["end"]) == (later["start"], later["end"]))
                    if not compatible:
                        raise ValueError(f"Incompatible robot operations: {e['name']}, {later['name']}")
                    for a,b in ((e,later),(later,e)):
                        v[f"sync_{a['name']}_{b['name']}"] = 1
                v[f"order_{e['name']}_{later['name']}"] = 1
    width = cfg.horizon + max(cfg.upper_reset, cfg.lower_reset)
    for j in jobs:
        name = j["name"]
        event = lambda tag: events[f"{name}_{tag}"]
        v[name+"_ch_load_s"], v[name+"_ch_unload_s"] = j["load_start"], j["unload_start"]
        if j["product"]:
            boundary = f"pjob_release_boundary_{j['pjob']}_{j['load_port']}"
            v[boundary] = max(v.get(boundary, 0), event("origin_pick")["start"])
            resources["AL"].append((event("al_put")["start"], name))
        else:
            key = name.removeprefix("aux_")
            resources["identity"].append((j["loan_start"] + width*int(j["identity"][1:]), key))
        for leg, start in (("in", event("source_pick")["start"]), ("out", j["unload_start"])):
            code = 1 + HANDS.index(j["vtr_hand_"+leg])
            key = f"{name}_{leg}"
            v[f"slot_VTR_hand_{key}_{code-1}"] = 1
            v[f"code_VTR_hand_{key}"] = code
            resources["VTR_hand"].append((start + width*code, key))
    for resource, put, pick, reset in (("U", "upper_put", "source_pick", cfg.upper_reset),
                                        ("L", "destination_put", "lower_pick", cfg.lower_reset)):
        occupied = [-1., -1.]
        ordered = sorted((events[j["name"]+"_"+put]["start"], j["name"]) for j in jobs if j["origin"] != "VS")
        for at, name in ordered:
            slot = min(range(2), key=occupied.__getitem__)
            if occupied[slot] > at + 1e-8:
                raise ValueError("Cannot color the load lock")
            occupied[slot] = events[name+"_"+pick]["end"]+reset
            v[f"slot_{resource}_{name}_{slot}"] = 1
            v[f"code_{resource}_{name}"] = slot+1
            resources[resource].append((at + width*(slot+1), name))
    for resource, items in resources.items():
        ordered = sorted(items)
        for i, (_, earlier) in enumerate(ordered):
            for _, later in ordered[i+1:]:
                v[f"order_{resource}_{earlier}_{later}"] = 1
    error = max(abs(x-round(x)) for x in v.values())
    if error > 1e-8:
        raise ValueError("An integer-second witness is required for exact numeric row substitution")
    return {k:round(x) for k,x in v.items() if round(x)}, error


class Number(float):
    # The model distinguishes named variables by object identity and distinguishes
    # integer literals (propagated constants) from named binary variables.
    __slots__ = ()


class RowsComplete(Exception):
    pass


class RowCheck:
    def __init__(self, values, verbose=False):
        self.values, self.nonzero = values, {}
        self.types, self.rows = Counter(), 0
        self.verbose, self.begin = verbose, time.monotonic()

    def hideOutput(self):
        pass

    def addVar(self, name, vtype="C", lb=0, ub=None):
        x = self.values.get(name, 0)
        upper = 1 if vtype == "B" else ub
        if x < lb or (upper is not None and x > upper) or (vtype in ("I", "B") and x != int(x)):
            raise ValueError(f"Variable domain violated: {name}={x}")
        self.types[vtype] += 1
        if x:
            self.nonzero[name] = x
        return Number(x)

    def addCons(self, satisfied, name=None):
        self.rows += 1
        if satisfied is not True:
            frame = sys._getframe(1)
            details = {k:frame.f_locals[k] for k in ("p", "q", "c", "a", "b", "active")
                       if isinstance(frame.f_locals.get(k), (int, float, str))}
            raise ValueError(f"Row {self.rows} failed at {frame.f_code.co_filename}:{frame.f_lineno}, {name}, {details}")
        if self.verbose and self.rows % 2000000 == 0:
            print(f"Checked {self.rows:,} original rows | elapsed {time.monotonic()-self.begin:.1f}s | {sample()}", flush=True)

    def setObjective(self, objective, sense):
        if objective != self.values["Cmax"] or sense != "minimize":
            raise ValueError("Unexpected primary objective")
        # The unmodified generator has now finished emitting all constraints.
        # Its subsequent native matrix-nonzero statistics require storing a matrix.
        raise RowsComplete


def evaluate(data, verbose=False):
    values, delta = witness(data)
    cfg = model.Config(**data["config"])
    if cfg.max_pairs or cfg.max_cycles:
        raise ValueError("Complete candidate bounds required")
    rows = RowCheck(values, verbose)
    api = SimpleNamespace(Model=lambda name: rows, quicksum=sum)
    with ExitStack() as patches:
        for module in (model, joint_pairing_model, joint_chamber_cycle_model):
            patches.enter_context(patch.object(module, "scip", api))
        try:
            model.Integrated(cfg)
        except RowsComplete:
            pass
        else:
            raise ValueError("Model generation did not end at its primary objective")
    del rows.values
    gc.collect()
    return rows, delta


def native_crosscheck():
    cfg = model.Config(run.ports(5, "mixed"))
    packing = run.Packing(cfg)
    beam = [()]
    for _ in range(packing.n):
        beam = packing.advance(beam, 6)
    timing = run.BatchTiming(packing, beam[0])
    data = timing.schedule(timing.initial)
    rows, _ = evaluate(data)
    x = model.Integrated(cfg)
    m = x.model
    try:
        dims = x.original_dimensions
        if sum(rows.types.values()) != dims["variables"] or rows.rows != dims["constraints"]:
            raise ValueError(f"Native row/variable count mismatch: {dims} / {rows.rows}, {rows.types}")
        if {kind:rows.types[short] for short,kind in (("B","BINARY"),("I","INTEGER"),("C","CONTINUOUS"))} != dims["types"]:
            raise ValueError("Native variable types differ")
        sol = m.createSol()
        for v in m.getVars(transformed=False):
            m.setSolVal(sol, v, rows.nonzero.get(v.name, 0))
        accepted = bool(m.checkSol(sol, completely=True, original=True, printreason=True))
        if not accepted:
            raise ValueError("Native complete original check rejected the streamed witness")
        # A broken product makespan must also fail in both independent engines.
        m.setSolVal(sol, x.cmax, 0)
        rejected = not m.checkSol(sol, completely=True, original=True, printreason=False)
        m.freeSol(sol)
        try:
            evaluate(data | {"cmax":0})
        except ValueError:
            if not rejected:
                raise ValueError("Native negative control unexpectedly passed")
        else:
            raise ValueError("Streamed negative control unexpectedly passed")
        return dict(products=5, modes=sorted({c["mode"] for c in data["cycles"]}), dimensions=dims,
                    native_scip_original_check=True, both_rejected_zero_cmax=True)
    finally:
        m.freeProb()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--campaign", type=Path, default=run.DEFAULT)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    job_handle = limit_process()
    wait_for_headroom()
    if args.self_test:
        print(json.dumps(native_crosscheck(), indent=2))
        return
    out = args.campaign.resolve()
    dest = out/"original_row_audit"
    with run.output_lock(dest):
        begin = time.monotonic()
        inputs = {p.name:run.digest(p) for p in (Path(__file__), run.BACKEND/"model.py",
                  run.BACKEND/"joint_pairing_model.py", run.BACKEND/"joint_chamber_cycle_model.py", run.BACKEND/"pjob_order.py",
                  run.BACKEND/"pjobs.py", out/"result.json", out/"summary.json")}
        if (dest/"certificate.json").exists():
            old = run.read(dest/"certificate.json")
            if old["input_sha256"] != inputs or old["assignment_sha256"] != run.digest(dest/"assignment.json.gz"):
                raise ValueError("Changed audit source or result")
            print(f"Already verified {old['original_rows']:,} original rows", flush=True)
            return
        print("0/1 cases complete | checking original SCIP and numeric engines on five products", flush=True)
        tested = native_crosscheck()
        run.check_finished(out)
        data = run.read(out/"result.json")
        concurrent = peers()
        print("0/1 cases complete | streaming every row of the unrestricted 75-product model | ETA unknown", flush=True)
        rows, delta = evaluate(data, verbose=True)
        temp, final = dest/"assignment.json.gz.tmp", dest/"assignment.json.gz"
        with gzip.open(temp, "wt", encoding="utf-8", compresslevel=4) as f:
            json.dump(dict(default=0, nonzero_values=rows.nonzero), f, separators=(",", ":"), sort_keys=True)
        temp.replace(final)
        nf = sum(p["4x1"] for p in data["config"]["load_ports"].values())
        nm = sum(p["2x2"] for p in data["config"]["load_ports"].values())
        productive = nf+2*nm
        cert = dict(status="all_original_rows_satisfied", full_candidate_space=True, products=nf+nm,
                    candidates=dict(pairs=nf+nm+3*productive, cycles_per_chamber=2*productive),
                    cmax=data["cmax"], original_rows=rows.rows, variables=sum(rows.types.values()),
                    variable_types=dict(rows.types), nonzero_variables=len(rows.nonzero),
                    verification="Exact integer-second substitution in every original model generator row; zero-default sparse assignment",
                    max_variable_rounding_s=delta, native_scip_crosscheck=tested, native_75_scip_checkSol=False,
                    unrestricted_optimization_calls=0, global_optimality_claim=False,
                    input_sha256=inputs, assignment_sha256=run.digest(final), elapsed_s=time.monotonic()-begin,
                    resources=sample(), concurrent_processes=concurrent, completed_utc=run.stamp())
        run.dump(dest/"certificate.json", cert)
        print(f"Complete=1/1 failed=0 ETA=0 | {rows.rows:,} rows | {cert['variables']:,} variables | {cert['resources']}", flush=True)


if __name__ == "__main__":
    main()

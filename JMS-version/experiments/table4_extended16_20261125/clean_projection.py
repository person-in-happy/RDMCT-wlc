"""Lower bound for the 16-wafer H=3 case, retaining clean loads, unloads and VTR conflicts."""
import argparse
from concurrent.futures import ProcessPoolExecutor
from contextlib import contextmanager
import hashlib
from itertools import combinations
import json
import math
import msvcrt
import os
from pathlib import Path
import sys
import time

from ortools.sat.python import cp_model
from bound import enumerate_batches

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OLD = HERE.parent / "table3_grid16_20261125"
sys.path.insert(0, str(OLD))
import ordered_projection
import port_projection
import tool_partition


def store(path, data):
    temp = path.with_suffix(f".{os.getpid()}.tmp")
    temp.write_text(json.dumps(data, indent=2), encoding="utf8")
    os.replace(temp, path)


def make_projection(trace, cutoff):
    pattern, modes, positions = [], [[], []], {}
    for c, mode, qty, step, _ in trace:
        group = 10*c + len(modes[c])
        modes[c].append(mode)
        pattern.extend([(group, mode)]*qty)
        positions[group] = step
    pattern = tuple(pattern)
    ordered_projection.patterns = lambda *args: {pattern: modes}
    model, end = port_projection.add_ports("mixed", cutoff)
    def indexed():
        return {v.name: model.get_int_var_from_proto_index(i)
                for i, v in enumerate(model.proto.variables) if v.name}
    tool_partition.exact_sides(model, indexed(), pattern, cutoff, False)
    v = indexed()
    chamber_ops, cleaning_ops = [], []
    for c, chamber in enumerate(modes):
        for i, mode in enumerate(chamber):
            g = 10*c + i
            before = positions[g]
            carry_next = positions.get(g+1) == "carry"
            chain = v.get(f"next_chain_{g}")
            if chain is not None:
                model.add(chain == int(carry_next))
            if mode == 1:
                names = ["bl", "fl", "fu", "bu"]
            else:
                names = ["fl", "bu"]
                if before != "carry":
                    names.extend(["dhead_load", "dhead_unload"])
                if not carry_next:
                    names.extend(["dtail_load", "dtail_unload"])
            chamber_ops += [(v[f"{name}_{g}"], c) for name in names]
            if before != "clean":
                continue
            cl = [model.new_int_var(0, cutoff, f"clean_{g}_{name}") for name in ("bl","fl","fu","bu")]
            model.add(cl[0] >= v[f"bu_{g-1}"]+1)
            model.add(cl[1] >= cl[0]+3)
            model.add(cl[2] >= cl[1]+501)
            model.add(cl[3] >= cl[2]+3)
            first = "bl" if mode == 1 else "dhead_load"
            model.add(v[f"{first}_{g}"] >= cl[3]+1)
            cleaning_ops += [(t,c) for t in cl]
    def separate(t,u,lag):
        b = model.new_bool_var("")
        model.add(t>=u+lag).only_enforce_if(b)
        model.add(u>=t+lag).only_enforce_if(~b)
    for t,c in cleaning_ops:
        for u,d in chamber_ops:
            separate(t,u,1+2*(c!=d))
        for i in range(16):
            for name in ("sp","dp"):
                separate(t, v[f"{name}_{i}"], 3)
    for (t,c),(u,d) in combinations(cleaning_ops,2):
        separate(t,u,1+2*(c!=d))
    return model,end,indexed()


def worker(args):
    path, trace, cutoff, budget, signature, initial = args
    state = json.loads(path.read_bytes()) if path.exists() else dict(
        signature=signature, trace=trace, used=0, lower=initial, status="PENDING")
    if state["signature"] != signature or state["trace"] != trace:
        raise ValueError(f"Checkpoint configuration changed: {path}")
    if state["status"] in ("INFEASIBLE","OPTIMAL") or state["used"] >= budget:
        return
    model,end,variables = make_projection(trace,cutoff)
    model.add(end >= state["lower"])
    solver = cp_model.CpSolver()
    solver.parameters.num_workers = 1
    solver.parameters.random_seed = 1
    old = state["used"]
    solver.parameters.max_time_in_seconds = budget-old
    t0 = time.monotonic()
    def update(lb):
        if lb > state["lower"]:
            state.update(lower=math.ceil(lb-1.e-6), used=min(budget,old+time.monotonic()-t0))
            store(path,state)
    solver.best_bound_callback = update
    config = path.with_suffix(".witness.json")
    if config.exists():
        for name,value in json.loads(config.read_bytes()).items():
            model.add_hint(variables[name],value)
    class Witness(cp_model.CpSolverSolutionCallback):
        def on_solution_callback(self):
            store(config,{k:self.value(t) for k,t in variables.items()})
    status = solver.solve(model,Witness())
    lower = cutoff+1 if status == cp_model.INFEASIBLE else max(state["lower"], math.ceil(solver.best_objective_bound-1.e-6))
    state.update(status=solver.status_name(status),lower=lower,used=min(budget,old+time.monotonic()-t0))
    store(path,state)


@contextmanager
def controller_lock(path):
    with path.open("a+b") as f:
        try:
            msvcrt.locking(f.fileno(),msvcrt.LK_NBLCK,1)
        except OSError:
            print("An active foreground controller owns this cutoff.",flush=True)
            yield False
        else:
            yield True


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cap",type=int,default=1235)
    parser.add_argument("--budget",type=int,default=20)
    parser.add_argument("--workers",type=int,default=4)
    a=parser.parse_args()
    dest=ROOT/"results/table4_extended16_20261125/clean_bounds"/str(a.cap)
    dest.mkdir(exist_ok=True,parents=True)
    scripts=[Path(__file__), HERE/"bound.py",*(OLD/f"{f}.py" for f in ("batch_lower","ordered_projection","port_projection","tool_partition"))]
    signature={f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in scripts}
    with controller_lock(dest/"controller.lock") as own:
        if not own:return
        cases=enumerate_batches(a.cap,True)["patterns"]
        tasks=[(dest/f"pattern{i:03}.json",list(map(list,trace)),a.cap,a.budget,signature,lb)
               for i,(lb,trace) in enumerate(cases)]
        t0=time.monotonic()
        def report(done):
            records=[json.loads(t[0].read_bytes()) if t[0].exists() else {"lower":t[-1],"used":0} for t in tasks]
            remaining=sum(max(0,a.budget-r["used"]) for r in records if r.get("status") not in ("INFEASIBLE","OPTIMAL"))
            seconds=round(time.monotonic()-t0,1)
            res=dict(completed=done,planned=len(cases),failed=0,workers=a.workers,
                     elapsed_s=seconds,remaining_budget_estimate_s=round(remaining/a.workers,1),
                     estimated_total_s=round(seconds+remaining/a.workers,1),estimate_basis="aggregate remaining solver allocations / independent foreground workers",
                     recovery="completed pattern, last proven bound or last feasible hint; interrupted partial tree restarts",
                     lower=min([a.cap+1]+[r["lower"] for r in records]))
            store(dest/"progress.json",res)
            print(res,flush=True)
        report(0)
        with ProcessPoolExecutor(max_workers=a.workers) as pool:
            futures=[pool.submit(worker,t) for t in tasks]
            while any(not f.done() for f in futures):
                time.sleep(4)
                report(sum(f.done() for f in futures))
            for f in futures:f.result()
        report(len(tasks))


if __name__ == "__main__":
    main()

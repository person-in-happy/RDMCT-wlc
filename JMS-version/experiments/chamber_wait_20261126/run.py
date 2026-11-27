"""Retiming the two published Gantt schedules with their discrete assignments fixed."""
import concurrent.futures
import hashlib
import json
import math
import os
import sys
import time
from pathlib import Path

from ortools.sat.python import cp_model

JMS = Path(__file__).resolve().parents[2]
OUT = JMS / "results/chamber_wait_20261126"
ORIENT = "--orientation" in sys.argv
HOLD = "--holding" in sys.argv
RESOURCE = "--resources" in sys.argv or ORIENT
REORDER = "--reorder" in sys.argv or RESOURCE
if HOLD:
    OUT = OUT/"holding_tiebreak"
elif ORIENT:
    OUT = OUT/"four_front_assignment"
elif RESOURCE:
    OUT = OUT/"resource_order_search"
elif REORDER:
    OUT = OUT/"local_order_search"
CASES = {4: JMS / "results/mixed_controls_20261122/grid4/pure__1pct/A",
         16: JMS / "results/gantt_huber_comparison_20261125/n16/exact_cap"}
sys.path[:0] = [str(JMS / "experiments/manuscript_projection_20261120"),
                 str(JMS / "experiments/square_residence_20261125"), str(JMS / "tools")]
import cell
from score import metrics
from current_defaults_swimlane import build
sys.path.insert(0, str(cell.BACKENDS["D"]))
from model import Config, Integrated
from validate import validate


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, data):
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def profile(doc):
    _, bars, _, _ = build(doc)
    result = metrics(doc)
    result["vtr_held_wait"] = sum(b["end"]-b["start"] for b in bars
                                  if b["lane"]=="VTR机械手" and b["action"]=="承片等待")
    result["equipment_release"] = max(b["end"] for b in bars)
    result["chambers"] = {}
    for c in doc["config"]["chambers"]:
        blocks = sorted((b for b in bars if b["lane"] == f"旋转腔 CH{c}"), key=lambda b: b["start"])
        waits = [(b["start"], b["end"]) for b in blocks if b["action"] == "腔内等待"]
        gaps = [(p["end"], q["start"]) for p, q in zip(blocks, blocks[1:]) if q["start"] > p["end"] + 1e-5]
        result["chambers"][str(c)] = dict(occupied_wait=sum(b-a for a,b in waits), wait_intervals=waits,
            internal_empty=sum(b-a for a,b in gaps), empty_intervals=gaps, first=blocks[0]["start"], last=blocks[-1]["end"])
    result["product_residence"] = {j["identity"]:j["unload_start"] - j["load_end"] - doc["config"]["full_time"]
                                    for j in doc["jobs"] if j["product"]}
    return result


def run(n):
    dest = OUT / f"n{n}"
    dest.mkdir(parents=True, exist_ok=True)
    src = CASES[n]
    identity = {p: sha(src / p) for p in ("schedule.json", "assignment.json.gz")}
    identity["worker"] = sha(Path(__file__))
    warm = None
    if RESOURCE:
        warm_stage="resource_order_search" if ORIENT else "local_order_search"
        warm = OUT.parent/warm_stage/f"n{n}"/"assignment.json.gz"
        identity["warm_assignment"] = sha(warm)
    if HOLD:
        warm_stage="four_front_assignment" if n==4 else "local_order_search"
        warm = OUT.parent/warm_stage/f"n{n}"/"assignment.json.gz"
        identity["warm_assignment"] = sha(warm)
    endpoint = dest / "evidence.json"
    if endpoint.exists():
        old = cell.read(endpoint)
        if old["identity"] == identity and old["schedule_sha256"] == sha(dest / "schedule.json"):
            if validate(cell.read(dest / "schedule.json"))["valid"]:
                return old["after"]
    source = cell.read(src / "schedule.json")
    baseline = profile(source)
    start_values = cell.values(src / "assignment.json.gz")
    if warm is not None:
        start_values = cell.values(warm)
        if HOLD:
            source = cell.read(warm.parent/"schedule.json")
    before = profile(source)
    cfg = Config(**source["config"])
    x = Integrated(cfg)
    native = x.model
    model = cp_model.CpModel()
    native_vars = native.getVars(transformed=False)
    vm = {}
    integers = {}
    domains = {}
    movable = set()
    if REORDER:
        actions=[e for e in source["events"] if e["robot"]]
        for a in actions:
            for b in actions:
                if a["name"]==b["name"] or a["robot"]!=b["robot"] or abs(a["start"]-b["start"])>120:
                    continue
                for prefix in ("order_", "sync_"):
                    movable.add(prefix+a["name"]+"_"+b["name"])
        if RESOURCE:
            active_jobs = {j["name"] for j in source["jobs"]}
            for res, intervals in x.intervals.items():
                keys = [key for key,*_ in intervals if key in active_jobs or
                        (key.endswith(("_in","_out")) and key.rsplit("_",1)[0] in active_jobs)]
                for key in keys:
                    if n==4:
                        movable.add(f"code_{res}_{key}")
                        movable.update(f"slot_{res}_{key}_{i}" for i in range(4))
                    for other in keys:
                        if key!=other:
                            movable.add(f"order_{res}_{key}_{other}")
        if ORIENT:
            for cycle in source["cycles"]:
                for p in cycle["pairs"]:
                    movable.update(f"{k}_{p}_{cycle['chamber']}_{cycle['index']}" for k in ("front","bt"))
    for v in native_vars:
        if v.vtype() != "CONTINUOUS" and v.name not in movable:
            integers[v.name] = round(start_values.get(v.name, 0.))
            continue
        lb, ub = math.ceil(v.getLbOriginal()-1e-7), math.floor(v.getUbOriginal()+1e-7)
        vm[v.name] = model.new_int_var(lb, ub, v.name)
        domains[v.name] = (lb,ub)
        model.add_hint(vm[v.name], round(start_values.get(v.name, 0.)))
    for row in native.getConss():
        co = native.getValsLinear(row)
        constant = sum(a * integers[k] for k, a in co.items() if k in integers)
        terms = [(k, round(a)) for k,a in co.items() if k in vm]
        if any(abs(co[k]-a)>1e-8 for k,a in terms):
            raise ValueError(row.name)
        low = sum(min(a*domains[k][0], a*domains[k][1]) for k,a in terms)
        hi = sum(max(a*domains[k][0], a*domains[k][1]) for k,a in terms)
        lhs = math.ceil(native.getLhs(row)-constant-1e-6)
        rhs = math.floor(native.getRhs(row)-constant+1e-6)
        if lhs > hi or rhs < low:
            raise ValueError(f"Source integer decisions violate {row.name}")
        if lhs <= low and rhs >= hi:
            continue
        expr = sum(a*vm[k] for k,a in terms)
        model.add_linear_constraint(expr, max(lhs,low), min(rhs,hi))
    product_r = []
    for j in source["jobs"]:
        if j["product"]:
            key = j["name"]
            product_r.append(vm[key+"_ch_unload_s"]-vm[key+"_ch_load_s"]-cfg.handling-cfg.full_time)
    cap = math.ceil(max(before["product_residence"].values())*2+4)
    rmin = model.new_int_var(0,cap,"min_r")
    rmax = model.new_int_var(0,cap,"max_r")
    model.add_min_equality(rmin,product_r)
    model.add_max_equality(rmax,product_r)
    spread = model.new_int_var(0,cap,"spread")
    squared = model.new_int_var(0,cap**2,"spread_squared")
    model.add(spread==rmax-rmin)
    model.add_multiplication_equality(squared,[spread,spread])
    f_scaled = 2*sum(product_r)+n*squared
    model.add(f_scaled<=round(2*n*before["secondary"]))
    cmax = vm[x.cmax.name]
    model.add(cmax <= round(before["cmax"]))
    for j in source["jobs"]:
        name = j["name"]
        if any(e["kind"]=="lower_pick" and e.get("job")==name for e in source["events"]):
            model.add(vm[name+"_lower_pick_s"] + cfg.atr_handling + cfg.lower_reset <= round(before["equipment_release"]))
    waits, gaps = [], []
    for c in cfg.chambers:
        prev = None
        for cycle in sorted((z for z in source["cycles"] if z["chamber"]==c),key=lambda z:z["index"]):
            pairs = cycle["pairs"]
            jobs = [j for j in source["jobs"] if j["pair"] in pairs]
            first = min(jobs,key=lambda j:j["load_start"])
            last = max(jobs,key=lambda j:j["unload_end"])
            first_time = vm[first["name"]+"_ch_load_s"]
            last_time = vm[last["name"]+"_ch_unload_s"]+cfg.handling
            if ORIENT:
                first_time=model.new_int_var(0,cfg.horizon,"first_"+str(c))
                last_time=model.new_int_var(0,cfg.horizon,"last_"+str(c))
                model.add_min_equality(first_time,[vm[j["name"]+"_ch_load_s"] for j in jobs])
                model.add_max_equality(last_time,[vm[j["name"]+"_ch_unload_s"]+cfg.handling for j in jobs])
            # Two pairs are loaded and unloaded, with two half-turns in each 4x1 cycle.
            waits.append(last_time-first_time-cfg.full_time-4*cfg.handling-2*cfg.rotation)
            if prev is None:
                # Delaying a dummy's first load can remove occupied waiting.
                # Guard the first *process start* to avoid merely shifting the cycle later.
                model.add(vm[f"jc_start_{c}_{cycle['index']}"]<=round(cycle["start"]))
            else:
                gaps.append(first_time-prev)
                if HOLD:
                    model.add(first_time-prev==round(before["chambers"][str(c)]["internal_empty"]))
            prev = last_time
    # First minimize the time a wafer waits in an otherwise inactive chamber.
    # Then minimize internal empty time, batch process score and product return.
    total_gaps = sum(gaps)
    base_wait = sum(z["occupied_wait"] for z in before["chambers"].values())
    base_gap = sum(z["internal_empty"] for z in before["chambers"].values())
    model.add(sum(waits)<=round(base_wait))
    model.add(total_gaps<=round(base_gap))
    span = round(before["cmax"])+1
    score_cap = round(2*n*before["secondary"])+1
    model.minimize(((sum(waits)*(round(base_gap)+1)+total_gaps)*score_cap+f_scaled)*span+cmax)
    if HOLD:
        total_holding = sum(vm[j["name"]+"_ch_load_s"] - vm[j["name"]+"_source_pick_s"]
                            + vm[j["name"]+"_destination_put_s"] - vm[j["name"]+"_ch_unload_s"]
                            for j in source["jobs"])
        model.minimize(total_holding)
    budget = 90 if RESOURCE else 60 if REORDER else 40
    checkpoint = dest/"checkpoint.json"
    prior = cell.read(checkpoint) if checkpoint.exists() else {}
    if prior.get("identity")!=identity:
        prior = {}
    if prior.get("values"):
        model.clear_hints()
        for k,v in vm.items():
            model.add_hint(v,prior["values"].get(k,0))
    used = prior.get("used",0)
    start = time.monotonic()
    class Keep(cp_model.CpSolverSolutionCallback):
        def on_solution_callback(self):
            vals = {k:int(self.value(v)) for k,v in vm.items() if self.value(v)}
            write(checkpoint,dict(identity=identity,values=vals,used=used+time.monotonic()-start))
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds=max(.01,budget-used)
    solver.parameters.num_search_workers=2 if REORDER else 1
    solver.parameters.random_seed=1
    status=solver.solve(model,Keep())
    cpstatus=solver.status_name(status)
    if status in (cp_model.OPTIMAL,cp_model.FEASIBLE):
        vals={k:solver.value(v) for k,v in vm.items()}
    elif prior.get("values"):
        vals=prior["values"]
    else:
        raise RuntimeError(cpstatus)
    vals.update(integers)
    sol=cell.attach(x,vals)
    doc=x.result(solution=sol)
    validation=validate(doc)
    if not validation["valid"]:
        raise ValueError(validation)
    after=profile(doc)
    if any(after[k]>before[k]+2e-4 for k in ("cmax","secondary","equipment_release")):
        raise ValueError("Guarded endpoints worsened.")
    cell.save(dest/"assignment.json.gz",cell.sparse(vals))
    cell.save(dest/"schedule.json",doc)
    write(endpoint,dict(identity=identity,source=str(src.relative_to(JMS)),before=baseline,after=after,
        warm_before=before if HOLD else None,vtr_holding_tiebreak=HOLD,
        native_rows=native.getNConss(),original_rows_valid=True,physical_validation=validation,
        schedule_sha256=sha(dest/"schedule.json"),assignment_sha256=sha(dest/"assignment.json.gz"),
        source_discrete_decisions_fixed=not REORDER,resource_order_search=RESOURCE,order_window_s=120 if REORDER else 0,
        free_order_or_sync_variables=sum(k in movable for k in vm),
        integer_time_lattice_seconds=1,solver=cpstatus,
        solve_seconds=solver.wall_time,solver_budget_s=budget,cpu_workers=solver.parameters.num_search_workers))
    native.freeSol(sol)
    native.freeProb()
    return after


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    started=time.monotonic()
    failed=0
    with concurrent.futures.ProcessPoolExecutor(max_workers=2) as workers:
        futures={workers.submit(run,n):n for n in ((4,) if ORIENT else CASES)}
        done=0
        while futures:
            elapsed=time.monotonic()-started
            estimate=max(130 if RESOURCE else 100 if REORDER else 80,elapsed+10)
            state=dict(elapsed_s=round(elapsed,1),estimated_total_s=round(estimate,1),
                       estimated_remaining_s=round(estimate-elapsed,1),completed=done,failed=failed,
                       active=list(futures.values()),concurrency=2,solver_threads_per_case=2 if REORDER else 1,
                       basis="Concurrent solve limits (resource order 90s, local order 60s, fixed 40s) plus approximately 40s for model construction and validation")
            write(OUT/"status.json",state)
            print(state,flush=True)
            completed,_=concurrent.futures.wait(futures,timeout=8,return_when=concurrent.futures.FIRST_COMPLETED)
            for f in completed:
                n=futures.pop(f)
                try:
                    result=f.result()
                    print(n,result,flush=True)
                    done+=1
                except Exception as e:
                    import traceback
                    traceback.print_exception(e);failed+=1
    elapsed=time.monotonic()-started
    write(OUT/"status.json",dict(elapsed_s=elapsed,estimated_total_s=elapsed,estimated_remaining_s=0,
                                 completed=done,failed=failed,active=[]))
    return int(failed>0)


if __name__=="__main__":
    sys.exit(main())

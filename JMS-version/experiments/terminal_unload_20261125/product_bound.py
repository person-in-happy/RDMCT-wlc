"""Integer product-route outer projection for the product-first hardware.

The two unit shortenings below cover every changed terminal arc. All other
projected arcs and the continuous-time flooring argument are documented in
results/terminal_unload_20261125/product_bound/derivation.md.
"""
import hashlib
import json
import msvcrt
from pathlib import Path
import sys
import time

JMS = Path(__file__).resolve().parents[2]
SRC = JMS / "experiments/residence_objective_20261125"
OUT = JMS / "results/terminal_unload_20261125/product_bound"
sys.path.insert(0, str(SRC))
import tight_primary
from ortools.sat.python import cp_model


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def adjusted():
    paths = [SRC/"primary_relaxation.py", SRC/"tight_primary.py"]
    assert [digest(p) for p in paths] == [
        "a896d4e0068d62a3ed2e99bf04fd21b706526eaa7d1f5a59773978a5f2b00cbe",
        "7e32bf9a3a74846335278d107b89a684137814b99bd91ed06d5bb0b79df8b968"]
    # Apply explicit, counted changes to pinned source without changing the archives.
    base = paths[0].read_text(encoding="utf8")
    for old,new in (("== 4\n    m =", "<= 4\n    m ="), ("assert len(wafers)==8", "assert len(wafers) in (4,8)"),
                    ("0 if side else 3", "0 if side else 2"), ('integer("makespan",519,cap)', 'integer("makespan",0,cap)')):
        assert base.count(old) == 1
        base = base.replace(old,new)
    base_ns = {"__name__": "terminal_product_projection"}
    exec(compile(base,str(paths[0]),"exec"),base_ns)
    extra = paths[1].read_text(encoding="utf8")
    assert extra.count("finish+3") == 3
    extra = extra.replace("finish+3","finish+2").replace(
        "from primary_relaxation import DUR, STEPS, cp_model, model", "")
    more_ns = dict(base_ns)
    exec(compile(extra,str(paths[1]),"exec"),more_ns)
    return more_ns["tightened"]


def write(path, data):
    tmp=path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data,indent=2)+"\n",encoding="utf8")
    tmp.replace(path)


def main():
    build = adjusted()
    OUT.mkdir(parents=True,exist_ok=True)
    lock=(OUT/"active.lock").open("a+b")
    try:
        msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
    except OSError:
        print("An active bound test already owns this queue.",flush=True)
        return
    begin=time.time()
    cases=[(4,396, JMS/"results/terminal_unload_20261125/scope/four_order/schedule.json",20),
           (8,552, JMS/"results/terminal_unload_20261125/eight_event_replay/H3/schedule.json",100)]
    records=[]
    for n,cap,path,limit in cases:
        sig=[digest(path),digest(Path(__file__))]
        target=OUT/f"n{n}.json"
        if target.exists():
            row=json.loads(target.read_bytes())
            assert row["signature"]==sig
            records.append(row)
            continue
        mark=OUT/f"attempt{n}.json"
        charged=0
        if mark.exists():
            prev=json.loads(mark.read_bytes())
            assert prev["signature"]==sig
            charged=min(limit,prev["charged"]+max(0,time.time()-prev["start"]))
        doc=json.loads(path.read_bytes())
        # Each expanded witness must project when we pin all preserved event times.
        witness=cp_model.CpSolver()
        witness.parameters.num_workers=1
        assert witness.solve(build(doc,cap+1,True)) in (cp_model.OPTIMAL,cp_model.FEASIBLE)
        model=build(doc,cap)
        solver=cp_model.CpSolver()
        solver.parameters.num_workers=3
        solver.parameters.max_time_in_seconds=max(.01,limit-charged)
        future=sum(t for i,_,_,t in cases if i>n)
        def update(*_):
            elapsed=time.time()-begin
            remaining=max(0,limit-charged-(time.time()-attempt_start))+future
            state=dict(active=n,completed=len(records),failed=0,elapsed_s=elapsed,
                       remaining_s=remaining,estimated_total_s=elapsed+remaining,
                       basis="remaining sequential caps with three CP-SAT threads")
            write(OUT/"status.json",state)
            print(state,flush=True)
        attempt_start=time.time()
        write(mark,dict(start=attempt_start,charged=charged,signature=sig))
        update()
        solver.best_bound_callback=update
        status=solver.solve(model)
        row=dict(n=n,cap=cap,status=solver.status_name(status),solver_s=solver.wall_time,
                 signatures_pinned=True,signature=sig,pinned_expanded_witness_passed=True,
                 projection_lower=cap+1 if status==cp_model.INFEASIBLE else solver.best_objective_bound,
                 projection_upper=solver.objective_value if status in (cp_model.FEASIBLE,cp_model.OPTIMAL) else None,
                 workers=3,rows=len(model.proto.constraints),columns=len(model.proto.variables))
        write(target,row)
        records.append(row)
    write(OUT/"summary.json",records)
    elapsed=time.time()-begin
    write(OUT/"status.json",dict(completed=2,failed=0,elapsed_s=elapsed,remaining_s=0,estimated_total_s=elapsed))
    lock.close()


if __name__=="__main__":
    main()

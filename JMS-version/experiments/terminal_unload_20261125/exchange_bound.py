"""Strengthen the product-only projection with physical product exchange order."""
import itertools
import json
import msvcrt
from pathlib import Path
import time
from product_bound import JMS, OUT, adjusted, cp_model, digest, write


def build(source, cap, fixed=False):
    model=adjusted()(source,cap,fixed)
    by={v.name:model.get_int_var_from_proto_index(i) for i,v in enumerate(model.proto.variables)}
    wafers=sorted((j for j in source["jobs"] if j["product"]),key=lambda j:(j["pjob"],j["pjob_index"]))
    modes={p["id"]:p["mode"] for p in source["pairs"]}
    opts=[]
    for i,w in enumerate(wafers):
        for c,q,s in itertools.product(range(2),range(4),range(2)):
            key=f"w{i}_{c}_{q}_{s}"
            if key in by:
                opts.append((i,c,q,s,modes[w["pair"]],by[key]))
    for i,c,q,s,mode,take in opts:
        last=q+(mode=="2x2")
        for j,d,r,k,other,assigned in opts:
            if i==j or c!=d:
                continue
            if r==last+1:
                model.add(by[f"{j}_load"]>=by[f"{i}_unload"]+1).only_enforce_if([take,assigned])
            if r==q and mode==other=="4x1" and s==0 and k==1:
                # With product on both sides only front-first unloading is allowed.
                model.add(by[f"{i}_unload"]>=by[f"{j}_unload"]+3).only_enforce_if([take,assigned])
    return model


def main():
    source=JMS/"results/terminal_unload_20261125/eight_event_replay/H3/schedule.json"
    doc=json.loads(source.read_bytes())
    target=OUT/"exchange8.json"
    sig=[digest(p) for p in (source,Path(__file__),Path(__file__).with_name("product_bound.py"))]
    lock=(OUT/"exchange8.lock").open("a+b")
    try:
        msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
    except OSError:
        print("The exchange check is already running.",flush=True)
        return
    if target.exists():
        assert json.loads(target.read_bytes())["signature"]==sig
        return
    verify=cp_model.CpSolver()
    verify.parameters.num_workers=1
    assert verify.solve(build(doc,553,True)) in (cp_model.FEASIBLE,cp_model.OPTIMAL)
    m=build(doc,552)
    solver=cp_model.CpSolver()
    solver.parameters.num_workers=3
    start=time.time()
    mark=OUT/"exchange8_attempt.json"
    charged=0
    if mark.exists():
        saved=json.loads(mark.read_bytes())
        assert sig==saved["signature"]
        charged=min(60,saved["charged"]+max(0,time.time()-saved["start"]))
    write(mark,dict(start=start,charged=charged,signature=sig))
    seconds=max(.01,60-charged)
    solver.parameters.max_time_in_seconds=seconds
    def progress(*_):
        elapsed=time.time()-start
        row=dict(completed=0,failed=0,elapsed_s=elapsed,estimated_total_s=seconds,
                 remaining_s=max(0,seconds-elapsed),basis="remaining solver budget, three workers")
        write(OUT/"exchange8_status.json",row)
        print(row,flush=True)
    progress()
    solver.best_bound_callback=progress
    status=solver.solve(m)
    row=dict(cap=552,signature=sig,status=solver.status_name(status),solver_s=solver.wall_time,
             product_projection_lower=553 if status==cp_model.INFEASIBLE else solver.best_objective_bound,
             product_projection_upper=solver.objective_value if status in (cp_model.FEASIBLE,cp_model.OPTIMAL) else None,
             rows=len(m.proto.constraints), columns=len(m.proto.variables),witness_pinned=True)
    write(target,row)
    elapsed=time.time()-start
    write(OUT/"exchange8_status.json",dict(completed=1,failed=0,elapsed_s=elapsed,estimated_total_s=elapsed,remaining_s=0))
    lock.close()


if __name__=="__main__":
    main()

"""Certify affine supporting lower bounds for squared residence spread in the short-cap domain."""
import argparse
import hashlib
import json
import msvcrt
import os
from pathlib import Path
import sys
import time

HERE=Path(__file__).resolve().parent
JMS=HERE.parents[1]
R=JMS/"results"
OUT=R/HERE.name
OLD=R/"pareto_scales_20261125"
sys.path.insert(0,str(HERE.parent/"table3_grid16_20261125"))
import rank_partition as rank
from ortools.sat.python import cp_model


def read(path):
    return json.loads(path.read_bytes())


def write(path,data):
    tmp=path.with_suffix(f".{os.getpid()}.tmp")
    tmp.write_text(json.dumps(data,indent=2),encoding="utf8")
    tmp.replace(path)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


JOBS=[(810,20,30,0,0),(811,20,30,0,0),(812,20,16,0,0),(812,26,16,10,10),(812,26,16,11,11)]


def solve(job,budget):
    cap,idx,slope,back,front=job
    directory=OUT/"support"/("_".join(map(str,job)));directory.mkdir(exist_ok=True,parents=True)
    file=directory/"result.json"
    sig={p.name:digest(p) for p in (Path(__file__),*(HERE.parent/"table3_grid16_20261125"/k for k in
         ("rank_partition.py","tool_partition.py","partition.py","port_projection.py","ordered_projection.py","batch_lower.py")))}
    prev=read(file) if file.exists() else {}
    if prev:
        assert prev["signature"]==sig
        if prev["status"] in ("OPTIMAL","INFEASIBLE") or prev["used"]>=budget-.05:return
    # Rebuild the exhaustive catalogue before restricting it to this case.
    table=rank.tool.prepare("mixed",cap)
    ptn,cyc=table[idx]
    assert ptn.count((back,1))>=3 and ptn.count((front,1))>=3
    original=rank.tool.order.patterns
    try:
        rank.tool.order.patterns=lambda nf,nd,cap,ready:{ptn:cyc}
        m,_=rank.tool.add_ports("mixed",cap)
    finally:
        rank.tool.order.patterns=original
    v={z.name:m.get_int_var_from_proto_index(j) for j,z in enumerate(m.proto.variables) if z.name}
    rank.rank_propagation(m,v,ptn,cap,True)
    v={z.name:m.get_int_var_from_proto_index(j) for j,z in enumerate(m.proto.variables) if z.name}
    # Every real schedule has D >= this signed residence difference between two occupied sides.
    d=v[f"bu_{back}"]-v[f"bl_{back}"]-v[f"fu_{front}"]+v[f"fl_{front}"]
    s=sum(v[f"ul_{j}"]-v[f"ld_{j}"]-181 for j in range(16))+16*slope*d
    if "lower16" in prev:m.add(s>=round(prev["lower16"]))
    m.minimize(s)
    path=directory/"projection.json"
    hints=read(path) if path.exists() else read(OLD/f"cap{cap}/p{idx:04}_hint.json")
    for k,num in hints.items():
        if k in v:m.add_hint(v[k],num)
    solver=cp_model.CpSolver();solver.parameters.num_workers=1;solver.parameters.random_seed=1
    old=prev.get("used",0)
    solver.parameters.max_time_in_seconds=budget-old
    solver.parameters.log_to_stdout=False;solver.parameters.log_search_progress=True
    rec=dict(signature=sig,status="RUNNING",used=old,job=job)
    start=time.monotonic()
    def persist():
        rec["used"]=old+time.monotonic()-start
        write(file,rec)
    def lb(num):
        rec["lower16"]=num;persist()
    class Capture(cp_model.CpSolverSolutionCallback):
        def on_solution_callback(self):
            write(path,{k:self.value(z) for k,z in v.items()})
            rec["upper16"]=self.objective_value;persist()
    solver.best_bound_callback=lb
    with (directory/"search.log").open("a",encoding="utf8") as f:
        solver.log_callback=lambda ln:f.write(ln.rstrip()+"\n")
        stat=solver.solve(m,Capture())
    rec.update(status=solver.status_name(stat),lower16=solver.best_objective_bound,elapsed=solver.wall_time)
    persist()


def main(budget):
    OUT.mkdir(exist_ok=True,parents=True);started=time.monotonic();lock=(OUT/"support.lock").open("a+b")
    try:msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
    except OSError:print("Existing support worker active.",flush=True);return
    for n,job in enumerate(JOBS,1):
        elapsed=time.monotonic()-started
        eta=(len(JOBS)+1-n)*(budget if n==1 else elapsed/(n-1))
        state=dict(stage=job,completed=n-1,total=len(JOBS),failed=0,elapsed=elapsed,eta_remaining=eta,eta_total=elapsed+eta,
                   workers=1,basis="per-cell limit until first observed cell, then completed throughput")
        write(OUT/"support_progress.json",state);print(state,flush=True);solve(job,budget)
    state.update(completed=len(JOBS),elapsed=time.monotonic()-started,eta_remaining=0);state["eta_total"]=state["elapsed"]
    write(OUT/"support_progress.json",state);print(state,flush=True)


if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--budget",type=int,default=65);args=p.parse_args();main(args.budget)

"""Certify a cap across every admissible chronological chamber-batch pattern."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import msvcrt

import ordered_projection as ordered
import port_projection as ports
from batch_lower import OUT

HERE=Path(__file__).resolve()


def prepare(kind,cap):
    nf,nd,stem={"4x1":(16,0,"pure_4x1"),"mixed":(8,8,"mixed")}[kind]
    case=json.loads((OUT/f"batch_bound_{stem}.json").read_bytes())
    rows=ordered.patterns(nf,nd,cap,case["ready"])
    return list(rows.items())


def atom(file,data):
    tmp=file.with_suffix(f".{os.getpid()}.tmp")
    tmp.write_text(json.dumps(data,indent=2),encoding="utf8");tmp.replace(file)


def bucket(kind,cap):
    where=OUT/"partitions"/f"{kind}_{cap}"
    where.mkdir(parents=True,exist_ok=True)
    return where


def worker(kind,cap,index,budget):
    where=bucket(kind,cap)/f"p{index:04d}"
    where.mkdir(exist_ok=True)
    target=where/"result.json"
    lock=(where/"worker.lock").open("a+b")
    try:msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
    except OSError:return
    sig={s:sha256(HERE.with_name(s).read_bytes()).hexdigest() for s in
         ("partition.py","port_projection.py","ordered_projection.py","batch_lower.py")}
    ptn=prepare(kind,cap)[index]
    previous=json.loads(target.read_bytes()) if target.exists() else dict(signature=sig,used=0,lower=0,upper=None)
    assert previous["signature"]==sig
    if previous.get("status") in ("OPTIMAL","INFEASIBLE") or previous["used"]>=budget:
        return
    # This process owns exactly one exhaustive partition. All product identities within a
    # chronological batch remain interchangeable. Keep the solver for this partition isolated.
    ordered.patterns=lambda nf,nd,cap,ready:dict([ptn])
    m,c=ports.add_ports(kind,cap)
    m.add(c>=int(previous["lower"]))
    v={s.name:m.get_int_var_from_proto_index(i) for i,s in enumerate(m.proto.variables) if s.name}
    witness=where/"projection.json"
    if witness.exists():
        for k,value in json.loads(witness.read_bytes()).items():
            if k in v:m.add_hint(v[k],value)
        m.add(c<=previous["upper"])
    solver=ordered.cp_model.CpSolver();solver.parameters.num_workers=1;solver.parameters.random_seed=1
    solver.parameters.max_time_in_seconds=budget-previous["used"]
    prior=previous["used"];start=time.monotonic()
    def store():
        previous["used"]=min(budget,prior+time.monotonic()-start)
        atom(target,previous)
    def bound(lb):
        if lb>previous["lower"]:
            previous["lower"]=lb;store()
    class Recorder(ordered.cp_model.CpSolverSolutionCallback):
        def on_solution_callback(self):
            if previous["upper"] is None or self.objective_value<previous["upper"]:
                previous["upper"]=int(self.objective_value)
                doc={k:self.value(var) for k,var in v.items()}
                doc["C"]=int(self.objective_value)
                atom(witness,doc);store()
    solver.best_bound_callback=bound
    previous["batch_pattern"]=ptn[0]
    store()
    result=solver.solve(m,Recorder())
    previous["status"]=solver.status_name(result)
    previous["lower"]=cap+1 if result==ordered.cp_model.INFEASIBLE else max(previous["lower"],solver.best_objective_bound)
    store()


def controller(kind,cap,budget,workers):
    where=bucket(kind,cap)
    lock=(where/"controller.lock").open("a+b")
    try:msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
    except OSError:return
    count=len(prepare(kind,cap))
    args=[sys.executable,"-B","-X","utf8",str(HERE),kind,str(cap),"--budget",str(budget)]
    start=time.monotonic()
    def dispatch(i):
        return subprocess.run(args+["--index",str(i)],check=True).returncode
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futures=[ex.submit(dispatch,i) for i in range(count)]
        while True:
            rows=[json.loads(p.read_bytes()) for p in where.glob("p*/result.json")]
            done=sum(f.done() for f in futures)
            l=min([int(r["lower"]) for r in rows]+([0] if len(rows)<count else []))
            upper=min((r["upper"] for r in rows if r["upper"] is not None),default=None)
            eta=(count-done)*(budget+3)/workers if done==0 else (count-done)*(time.monotonic()-start)/done
            summary=dict(kind=kind,cap=cap,expected=count,completed=done,failed=sum(f.done() and f.exception() is not None for f in futures),
                         lower=l,upper=upper,elapsed_s=time.monotonic()-start,estimated_remaining_s=eta,
                         workers=workers,per_pattern_budget_s=budget,exact_infeasible=sum(r.get("status")=="INFEASIBLE" for r in rows),
                         basis="Initial bound from per-pattern allowances, updated using completed partitions per wall time.")
            atom(where/"summary.json",summary)
            print(f"{kind} ≤ {cap}: partitions {done}/{count}, failed {summary['failed']}, LB {l}, relaxed UB {upper}, elapsed {summary['elapsed_s']:.0f}s, estimated total {summary['elapsed_s']+eta:.0f}s, ETA {eta:.0f}s.",flush=True)
            if done==count:break
            time.sleep(3)
        for f in futures:f.result()


if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("kind");p.add_argument("cap",type=int)
    p.add_argument("--index",type=int);p.add_argument("--budget",type=int,default=12);p.add_argument("--workers",type=int,default=2)
    a=p.parse_args()
    if a.index is None:controller(a.kind,a.cap,a.budget,a.workers)
    else:worker(a.kind,a.cap,a.index,a.budget)

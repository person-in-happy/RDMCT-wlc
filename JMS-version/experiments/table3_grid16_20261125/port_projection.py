"""Add LP-specific ATR moves, pair synchronization and second-exposure timing to ordered batches."""
import argparse
from hashlib import sha256
from itertools import combinations,product
import json
import os
from pathlib import Path
import threading
import time
import msvcrt

from ordered_projection import build
from batch_lower import OUT
from ortools.sat.python import cp_model


def add_ports(kind,cap):
    m,relaxed,patterns=build(kind,cap)
    v={s.name:m.get_int_var_from_proto_index(i) for i,s in enumerate(m.proto.variables) if s.name}
    groups=sorted(int(k[5:]) for k in v if k.startswith("kind_"))
    horizon=cap+160
    ports=[]; flags=[]; starts=[]; ends=[]; held=[]; secondary=[]
    def sep(t,u,ab,ba,flags=()):
        order=m.new_bool_var("")
        m.add(u>=t+ab).only_enforce_if([*flags,order])
        m.add(t>=u+ba).only_enforce_if([*flags,~order])
    def flag_eq(a,b):
        f=m.new_bool_var("")
        m.add(a==b).only_enforce_if(f)
        m.add(a!=b).only_enforce_if(~f)
        return f
    def hold(t,end):
        dur=m.new_int_var(0,horizon,"")
        held.append(m.new_interval_var(t,dur,end,""))
    cuts={k:[m.new_int_var(0,cap,"") for _ in range(3)] for k in (1,2)}
    for i in range(16):
        p=m.new_int_var(0,3,f"port_{i}")
        ports.append(p)
        port=[flag_eq(p,j) for j in range(4)]
        recipe=m.new_int_var(1,2,"")
        m.add_element(v[f"batch_{i}"],[v[f"kind_{g}"] for g in groups],recipe)
        which={k:flag_eq(recipe,k) for k in (1,2)}
        start=m.new_int_var(0,cap,f"origin_pick_{i}")
        end=m.new_int_var(0,cap,f"origin_put_{i}")
        starts.append(start); ends.append(end)
        m.add(v[f"al_{i}"]>=start+7)
        m.add(end>=v[f"lp_{i}"]+7)
        hold(start,v[f"al_{i}"]+4)
        hold(v[f"ap_{i}"],v[f"up_{i}"]+4)
        hold(v[f"lp_{i}"],end+4)
        for k,j in product((1,2),range(4)):
            assignment=m.new_bool_var("")
            m.add(assignment<=port[j]);m.add(assignment<=which[k])
            m.add(assignment>=port[j]+which[k]-1)
            secondary.append((k,j,assignment))
            if j>0:
                m.add(start>=cuts[k][j-1]).only_enforce_if(assignment)
            if j<3:
                m.add(start<=cuts[k][j]).only_enforce_if(assignment)
    for k,j in product((1,2),range(4)):
        qty=2 if kind=="mixed" else 4*int((k==1)==(kind=="4x1"))
        m.add(sum(f for typ,port,f in secondary if (typ,port)==(k,j))==qty)
    m.add_cumulative(held,[1]*len(held),2)
    for i,j in combinations(range(16),2):
        paired=flag_eq(v[f"pair_{i}"],v[f"pair_{j}"])
        home=flag_eq(ports[i],ports[j])
        for k,d in (("sp",1),("dp",1),("up",4),("lp",4)):
            sync=m.new_bool_var("")
            m.add(sync<=paired)
            a,b=v[f"{k}_{i}"],v[f"{k}_{j}"]
            m.add(a==b).only_enforce_if(sync)
            sep(a,b,d,d,[~sync])
        for a,b in ((starts[i],starts[j]),(ends[i],ends[j])):
            sync=m.new_bool_var("")
            m.add(sync<=paired);m.add(sync<=home)
            m.add(a==b).only_enforce_if(sync)
            sep(a,b,7-3*home,7-3*home,[~sync])
        for a,b in ((starts[i],ends[j]),(starts[j],ends[i])):
            sep(a,b,7-3*home,7-3*home)
    for i,j in product(range(16),repeat=2):
        for dest in ("al","ap","lp","up"):
            other=v[f"{dest}_{j}"]
            if dest=="al" and i==j:
                continue
            sep(starts[i],other,7,10 if dest in ("lp","up") else 7)
            sep(ends[i],other,7,7)
    for g in groups:
        dual=flag_eq(v[f"kind_{g}"],2)
        s,u=v[f"start_{g}"],v[f"bu_{g}"]
        if g+1 not in groups or g//10!=(g+1)//10:
            m.add(u>=s+187).only_enforce_if(dual)
            continue
        next_dual=flag_eq(v[f"kind_{g+1}"],2)
        chain=m.new_bool_var("")
        m.add(chain<=dual);m.add(chain<=next_dual)
        m.add(u>=v[f"start_{g+1}"]+92).only_enforce_if(chain)
        m.add(v[f"start_{g+1}"]>=s+188).only_enforce_if([dual,next_dual,~chain])
        m.add(u>=s+187).only_enforce_if([dual,~chain])
    c=m.new_int_var(0,cap,"true_C")
    m.add(c>=relaxed)
    m.add_max_equality(c,[t+4 for t in ends])
    m.minimize(c)
    return m,c


def run(kind,cap,budget,workers):
    dest=OUT/"ports"/f"{kind}_{cap}"
    dest.mkdir(parents=True,exist_ok=True)
    lock=(dest/"active.lock").open("a+b")
    try: msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
    except OSError: return
    fname=dest/"result.json"
    signature={p:sha256(Path(__file__).with_name(p).read_bytes()).hexdigest() for p in
               ("port_projection.py","ordered_projection.py","batch_lower.py")}
    state=json.loads(fname.read_bytes()) if fname.exists() else dict(signature=signature,used=0,lower=0,upper=None)
    assert state["signature"]==signature
    if state.get("status") in ("INFEASIBLE","OPTIMAL") or state["used"]>=budget:
        return
    m,c=add_ports(kind,cap)
    m.add(c>=int(state["lower"]))
    vars_={s.name:m.get_int_var_from_proto_index(i) for i,s in enumerate(m.proto.variables) if s.name}
    witness=dest/"projection.json"
    if witness.exists():
        for k,value in json.loads(witness.read_bytes()).items():
            if k in vars_:m.add_hint(vars_[k],value)
        m.add(c<=state["upper"])
    solver=cp_model.CpSolver()
    solver.parameters.num_workers=workers
    solver.parameters.random_seed=1
    solver.parameters.log_search_progress=True;solver.parameters.log_to_stdout=False
    solver.parameters.max_time_in_seconds=budget-state["used"]
    start=time.monotonic();prior=state["used"]
    mutex=threading.Lock();end=threading.Event()
    def store(path,doc):
        tmp=path.with_suffix(".tmp")
        tmp.write_text(json.dumps(doc),encoding="utf8");os.replace(tmp,path)
    def persist():
        state["used"]=min(budget,prior+time.monotonic()-start)
        state["remaining_s"]=budget-state["used"]
        store(fname,state)
    def improve(lb):
        with mutex:
            if lb>state["lower"]:
                state["lower"]=lb;persist()
    class Recorder(cp_model.CpSolverSolutionCallback):
        def on_solution_callback(self):
            with mutex:
                if state["upper"] is None or self.objective_value<state["upper"]:
                    state["upper"]=int(self.objective_value)
                    store(witness,{k:self.value(v) for k,v in vars_.items()})
                    persist()
    def heartbeat():
        while not end.is_set():
            with mutex:
                persist()
                print(f"{kind} cap {cap} | 0/1 complete | elapsed {state['used']:.0f}s | allotted {budget}s | remaining budget {state['remaining_s']:.0f}s | LB {state['lower']}, projected UB {state['upper']}",flush=True)
            end.wait(5)
    thread=threading.Thread(target=heartbeat,daemon=True);thread.start()
    solver.best_bound_callback=improve
    try:
        with (dest/"cp.log").open("a",encoding="utf8",buffering=1) as log:
            solver.log_callback=lambda s:log.write(s.rstrip()+"\n")
            result=solver.solve(m,Recorder())
    finally:
        end.set();thread.join()
    state["status"]=solver.status_name(result)
    state["lower"]=cap+1 if result==cp_model.INFEASIBLE else max(state["lower"],solver.best_objective_bound)
    persist()
    print(f"1/1 finished. {state['status']} lower {state['lower']}.",flush=True)


if __name__=="__main__":
    a=argparse.ArgumentParser();a.add_argument("kind");a.add_argument("cap",type=int)
    a.add_argument("--budget",type=int,default=180);a.add_argument("--workers",type=int,default=2)
    options=a.parse_args();run(options.kind,options.cap,options.budget,options.workers)

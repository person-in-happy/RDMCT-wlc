"""Run the labeled mixed product relaxation, preserving cumulative budget and every improvement."""
import argparse
import itertools
import json
import math
import os
from pathlib import Path
import threading
import time
from hashlib import sha256
import msvcrt
from mixed_product import tightened, cp_model
from batch_lower import OUT,JMS

SOURCE=JMS/"results/table3_mixed16_20261125/prepared/schedule.json"
HERE=Path(__file__).resolve().parent


def read(p):
    return json.loads(p.read_bytes())


def save(p,obj):
    tmp=p.with_suffix(f".{os.getpid()}.tmp")
    tmp.write_text(json.dumps(obj),encoding="utf8")
    os.replace(tmp,p)


def strengthen(m,v,doc,cap):
    collections={}
    groups={(cy["chamber"]-2,cy["index"]) for cy in doc["cycles"]}
    chamber_cycles=1+(cap-76-40-90)//94
    products=sorted((j for j in doc["jobs"] if j["product"]),key=lambda w:(w["pjob"],w["pjob_index"]))
    modes={p["id"]:p["mode"] for p in doc["pairs"]}
    m.add(v["ch0"]==0)
    for c,q in itertools.product(range(2),range(chamber_cycles)):
        slot=c,q
        flags=[v[k] for i in range(16) for t in (0,1) if (k:=f"w{i}_{c}_{q}_{t}") in v]
        if q:
            flags+=[v[f"w{i}_{c}_{q-1}_1"] for i,w in enumerate(products) if modes[w["pair"]]=="2x2"]
        m.add(v[f"use{slot}"]<=sum(flags))
        full=v[f"full{slot}"]
        s=v[f"start{slot}"]
        bl,fl,fu,bu=[m.new_int_var(0,cap+160,f"{word}_{c}_{q}") for word in ("bl","fl","fu","bu")]
        collections[slot]=((bl,fl,fu,bu),full)
        m.add(fl+1==s).only_enforce_if(full)
        m.add(fl>=bl+3).only_enforce_if(full)
        m.add(fu>=s+180).only_enforce_if(full)
        m.add(bu>=fu+3).only_enforce_if(full)
        if q:
            a,prior=collections[c,q-1]
            m.add(bl>=a[-1]+1).only_enforce_if([prior,full])
        for i,w in enumerate(products):
            if modes[w["pair"]]!="4x1":
                continue
            for side in (0,1):
                at=v[f"w{i}_{c}_{q}_{side}"]
                m.add(v[f"{i}_load"]==(fl if side else bl)).only_enforce_if(at)
                m.add(v[f"{i}_unload"]==(fu if side else bu)).only_enforce_if(at)
    all_events=[(c,t,on) for (c,q),(times,on) in collections.items() for t in times]
    def disj(t,u,g,flags):
        ord_=m.new_bool_var("")
        m.add(t>=u+g).only_enforce_if([*flags,ord_])
        m.add(u>=t+g).only_enforce_if([*flags,~ord_])
    for (c,t,on),(d,u,un) in itertools.combinations(all_events,2):
        disj(t,u,1+2*(c!=d),[on,un])
    for _,t,on in all_events:
        for i,k in itertools.product(range(16),("source_pick","destination_put")):
            disj(t,v[f"{i}_{k}"],3,[on])


def starting_hint(model,v,doc,path):
    hint=read(path)
    native=sorted((w for w in doc["jobs"] if w["product"]),key=lambda w:(w["pjob"],w["pjob_index"]))
    names={w["identity"]:i for i,w in enumerate(native)}
    operations=hint["product_event_hints"]
    for label,row in operations.items():
        i=names[label]
        for k,t in row.items():
            model.add_hint(v[f"{i}_{k}"],t)
        model.add_hint(v[f"{i}_origin_pick"],max(0,row["al_put"]-7))
        model.add_hint(v[f"{i}_origin_put"],row["lower_pick"]+7)
    orientations=[c for c,seq in hint["cycles"].items() if any(native[0]["identity"] in gr for step in seq for gr in (step["front"],step["back"]))]
    assert len(orientations)==1
    flip=int(orientations[0])-2
    seen=set()
    for ch,cycles in hint["cycles"].items():
        c=(int(ch)-2)^flip
        for q,step in enumerate(cycles):
            model.add_hint(v[f"use{c,q}"],1)
            model.add_hint(v[f"full{c,q}"],int(step["mode"]=="4x1"))
            if step["first_start_hint"] is not None:
                model.add_hint(v[f"start{c,q}"],step["first_start_hint"])
            for side,products in enumerate((step["back"],step["front"])):
                for label in products:
                    if label in seen:
                        continue
                    seen.add(label); i=names[label]
                    model.add_hint(v[f"w{i}_{c}_{q}_{side}"],1)
                    model.add_hint(v[f"ch{i}"],c)


def run(cap,budget,workers,hardware):
    where=OUT/f"mixed_labeled_{cap}_{'sides' if hardware else 'base'}"
    where.mkdir(parents=True,exist_ok=True)
    lock=(where/"run.lock").open("a+b")
    try:
        msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
    except OSError:
        print("Existing foreground solver owns this run.",flush=True)
        return
    src=read(SOURCE)
    ref=OUT/"ordered/mixed_815/status.json"
    sha=lambda p:sha256(p.read_bytes()).hexdigest()
    inputs=dict(program=sha(Path(__file__)),model=sha(HERE/"mixed_product.py"),source=sha(SOURCE),bound_proof=sha(ref),cap=cap)
    checkpoint=where/"checkpoint.json"
    state=read(checkpoint) if checkpoint.exists() else dict(inputs=inputs,used=0,lower=read(ref)["lower"],upper=None)
    assert state["inputs"]==inputs
    if state.get("status") in ("OPTIMAL","INFEASIBLE") or budget<=state["used"]:
        print("Reused prior endpoint.",flush=True)
        return
    cp=tightened(src,cap)
    v={s.name:cp.get_int_var_from_proto_index(i) for i,s in enumerate(cp.proto.variables)}
    if hardware:
        strengthen(cp,v,src,cap)
    else:
        cp.add(v["ch0"]==0)
    cp.add(v["makespan"]>=math.ceil(state["lower"]-1e-6))
    cp.clear_hints()
    if state["upper"] is None:
        starting_hint(cp,v,src,OUT/"ordered/mixed_815/native_hint.json")
    else:
        coords=read(where/f"candidate_{int(state['upper'])}.json")
        for name,var in v.items():
            cp.add_hint(var,coords.get(name,0))
        cp.add(v["makespan"]<=state["upper"])
    solver=cp_model.CpSolver()
    solver.parameters.num_workers=workers
    solver.parameters.random_seed=1
    solver.parameters.max_time_in_seconds=budget-state["used"]
    solver.parameters.log_search_progress=True
    solver.parameters.log_to_stdout=False
    mutex=threading.Lock()
    begin=time.monotonic(); charged=state["used"]
    def update():
        state["used"]=min(budget,charged+time.monotonic()-begin)
        state["remaining_s"]=budget-state["used"]
        save(checkpoint,state)
    def bound(value):
        with mutex:
            if value>state["lower"]:
                state["lower"]=value
                update()
    class Record(cp_model.CpSolverSolutionCallback):
        def on_solution_callback(self):
            with mutex:
                val=int(self.objective_value)
                if state["upper"] is None or val<state["upper"]:
                    save(where/f"candidate_{val}.json",{k:self.value(w) for k,w in v.items() if self.value(w)})
                    state["upper"]=val
                    update()
    solver.best_bound_callback=bound
    end=threading.Event()
    def pulse():
        while not end.is_set():
            with mutex:
                update()
                print(f"Mixed ≤{cap}: 0/1 complete | elapsed {state['used']:.0f}s | total budget {budget}s | remaining {state['remaining_s']:.0f}s | LB {state['lower']} | relaxed UB {state['upper']}",flush=True)
            end.wait(5)
    thread=threading.Thread(target=pulse,daemon=True)
    thread.start()
    try:
        with (where/"cp.log").open("a",encoding="utf8",buffering=1) as log:
            solver.log_callback=lambda line:log.write(line.rstrip()+"\n")
            status=solver.solve(cp,Record())
    finally:
        end.set();thread.join()
    state["status"]=solver.status_name(status)
    state["lower"]=cap+1 if status==cp_model.INFEASIBLE else max(state["lower"],solver.best_objective_bound)
    update()
    print(f"1/1 completed. {state['status']} LB {state['lower']} relaxed UB {state['upper']}",flush=True)


if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("cap",type=int)
    p.add_argument("--budget",type=int,default=480)
    p.add_argument("--workers",type=int,default=2)
    p.add_argument("--hardware",action="store_true")
    a=p.parse_args(); run(a.cap,a.budget,a.workers,a.hardware)

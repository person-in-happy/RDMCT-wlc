"""Retain chamber occupancy and search native dummy identities, hand allocation, full-cycle sides and local timing."""
from dataclasses import replace
import math
from pathlib import Path
import sys
import threading
import time
from ortools.sat.python import cp_model
from candidate import atomic
from prepare import OUT,Integrated,configuration,cell,normalize_schedule,read,sha,sparse_witness,validate
from seed import constrain_seed


def main(input_path,tag,window):
    src=Path(input_path)
    folder=OUT/"proposals"/tag
    folder.mkdir(exist_ok=True,parents=True)
    sig=dict(source=sha(src),script=sha(Path(__file__)),window=window,seed=1)
    state=folder/"checkpoint.json"
    prev=read(state) if state.exists() else dict(identity=sig,elapsed=0)
    assert prev["identity"]==sig
    if (folder/"result.json").exists():return
    cfg=configuration()
    d=read(src)
    compact=replace(cfg,max_pairs=1+max(p["id"] for p in d["pairs"]),
                    max_cycles=1+max(c["index"] for c in d["cycles"]),horizon=2500)
    d=normalize_schedule(compact,d)
    seed=cell.lift(compact,sparse_witness(compact,d),None,rebuild=True)
    assert seed and seed[3]["valid"]
    x=Integrated(compact);m=x.model
    fixings=constrain_seed(x,d,times=False)
    sides={x.front[p,q["chamber"],q["index"]].name for q in d["cycles"] if q["mode"]=="4x1" for p in q["pairs"]}
    for var,lb,ub in fixings:
        if var is not None and (var.name.startswith("jp_identity_") or var.name in sides):
            m.chgVarLb(var,lb);m.chgVarUb(var,ub)
    values=seed[1]["nonzero"]
    events=d["events"]
    distant={"order_"+a["name"]+"_"+b["name"] for a in events for b in events
             if a["robot"]==b["robot"] and a["robot"] in ("ATR","VTR") and abs(a["start"]-b["start"])>window}
    cp=cp_model.CpModel()
    free={};fixed={}
    for v in m.getVars(transformed=False):
        n=v.name
        l,h=math.ceil(v.getLbOriginal()-1e-8),math.floor(v.getUbOriginal()+1e-8)
        if n in distant:l=h=round(values.get(n,0))
        if l==h:fixed[n]=l
        else:free[n]=cp.new_int_var(l,h,n)
    for row in m.getConss():
        const=0;terms=[]
        for n,xval in m.getValsLinear(row).items():
            coeff=round(xval);assert coeff==xval
            if n in fixed:const+=coeff*fixed[n]
            else:terms.append(coeff*free[n])
        l,h=m.getLhs(row),m.getRhs(row)
        if l>-1e15:cp.add(sum(terms)>=math.ceil(l-const-1e-7))
        if h<1e15:cp.add(sum(terms)<=math.floor(h-const+1e-7))
    upper=round(seed[2]["cmax"])
    if (folder/"best.json").exists():
        info=read(folder/"best.json");upper=min(upper,round(info["upper"]));values=read(folder/info["values"])
    cp.add(free["Cmax"]<=upper);cp.add(free["Cmax"]>=809);cp.minimize(free["Cmax"])
    for n,v in free.items():cp.add_hint(v,round(values.get(n,0)))
    e=cp_model.CpSolver();e.parameters.num_workers=1;e.parameters.random_seed=1
    seconds=200
    e.parameters.max_time_in_seconds=max(0,seconds-prev["elapsed"])
    e.parameters.log_search_progress=True;e.parameters.log_to_stdout=False
    clock=time.monotonic()
    def used():return min(seconds,prev["elapsed"]+time.monotonic()-clock)
    stop=threading.Event()
    def heartbeat():
        while not stop.wait(3):atomic(state,dict(identity=sig,elapsed=min(seconds,used()+3)))
    monitor=threading.Thread(target=heartbeat,daemon=True);monitor.start()
    class Solutions(cp_model.CpSolverSolutionCallback):
        def on_solution_callback(self):
            vals={n:v for n,v in fixed.items() if v}
            vals.update({n:self.value(v) for n,v in free.items() if self.value(v)})
            sol=cell.attach(x,vals);doc=x.result(solution=sol);m.freeSol(sol)
            check=validate(doc);assert check["valid"]
            C=check["product_return_cmax"];name=f"candidate_{C:g}"
            atomic(folder/(name+".json"),normalize_schedule(cfg,doc))
            atomic(folder/(name+"_values.json"),vals)
            atomic(folder/"best.json",dict(upper=C,values=name+"_values.json"))
            print(tag,C,flush=True)
    with (folder/"solver.log").open("a",encoding="utf8",buffering=1) as f:
        e.log_callback=lambda s:f.write(s.rstrip()+"\n")
        status=e.solve(cp,Solutions())
    stop.set();monitor.join()
    atomic(state,dict(identity=sig,elapsed=used()))
    atomic(folder/"result.json",dict(identity=sig,elapsed=used(),status=e.status_name(status),local_lower=e.best_objective_bound))
    m.freeProb()

if __name__=="__main__":main(sys.argv[1],sys.argv[2],int(sys.argv[3]))

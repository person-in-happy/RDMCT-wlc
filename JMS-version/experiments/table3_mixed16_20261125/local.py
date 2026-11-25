"""Improve a validated native witness by releasing nearby route and resource decisions jointly."""
from dataclasses import replace
import math
from pathlib import Path
import sys
import threading
import time
from prepare import OUT,configuration,cell,Integrated,normalize_schedule,sparse_witness,read,sha,validate
from candidate import atomic
from ortools.sat.python import cp_model


def main(source,name,window):
    src=Path(source).resolve()
    folder=OUT/"proposals"/name
    folder.mkdir(exist_ok=True,parents=True)
    signature=dict(seed=1,program=sha(Path(__file__)),source=sha(src),cfg=sha(OUT/"input.json"),window=window)
    checkpoint=folder/"checkpoint.json"
    old=read(checkpoint) if checkpoint.exists() else dict(identity=signature,elapsed=0)
    assert old["identity"]==signature
    if (folder/"result.json").exists():return
    base=read(src);cfg=configuration()
    compact=replace(cfg,horizon=2500,max_pairs=max(p["id"] for p in base["pairs"])+1,max_cycles=max(q["index"] for q in base["cycles"])+1)
    warm=normalize_schedule(compact,base)
    checked=cell.lift(compact,sparse_witness(compact,warm),None,rebuild=True)
    if not checked:raise ValueError("Compact physical seed invalid")
    vals=checked[1]["nonzero"]
    x=Integrated(compact);m=x.model
    # Only sequencing binaries for nearby active operations and synchronization
    # flags are released. Every released choice remains governed by native rows.
    allowed=set()
    events=warm["events"]
    for e in events:
        for f in events:
            if e["robot"]==f["robot"] and e["robot"] in ("ATR","VTR") and abs(e["start"]-f["start"])<=window:
                allowed.add("order_"+e["name"]+"_"+f["name"])
    for v in m.getVars(transformed=False):
        if v.vtype()=="CONTINUOUS" or v.name.startswith("sync_") or v.name in allowed:continue
        if v.name.startswith(("order_U_","order_L_","order_ATR_hand_","order_VTR_hand_")):continue
        value=round(vals.get(v.name,0.))
        m.chgVarLb(v,value);m.chgVarUb(v,value)
    cp=cp_model.CpModel()
    variables={};constants={}
    for var in m.getVars(transformed=False):
        lo,hi=math.ceil(var.getLbOriginal()-1e-8),math.floor(var.getUbOriginal()+1e-8)
        if lo==hi:constants[var.name]=lo
        else:variables[var.name]=cp.new_int_var(lo,hi,var.name)
    for row in m.getConss():
        bias=0;terms=[]
        for k,a in m.getValsLinear(row).items():
            n=round(a);assert n==a
            if k in constants:bias+=n*constants[k]
            else:terms.append(n*variables[k])
        l,h=m.getLhs(row),m.getRhs(row)
        if l>-1e15:cp.add(sum(terms)>=math.ceil(l-bias-1e-7))
        if h<1e15:cp.add(sum(terms)<=math.floor(h-bias+1e-7))
    cp.add(variables["Cmax"]>=794)
    upper=round(checked[2]["cmax"])
    if (folder/"best.json").exists():
        rec=read(folder/"best.json")
        upper=min(upper,round(rec["upper"]));vals=read(folder/rec["values"])
    cp.add(variables["Cmax"]<=upper)
    for n,v in variables.items():cp.add_hint(v,round(vals.get(n,0)))
    cp.minimize(variables["Cmax"])
    engine=cp_model.CpSolver()
    budget=140
    engine.parameters.num_workers=1;engine.parameters.random_seed=1
    engine.parameters.log_search_progress=True;engine.parameters.log_to_stdout=False
    engine.parameters.max_time_in_seconds=max(0,budget-old["elapsed"])
    started=time.perf_counter()
    def charged():return min(budget,old["elapsed"]+time.perf_counter()-started)
    stop=threading.Event()
    def heartbeat():
        while not stop.wait(3):atomic(checkpoint,dict(identity=signature,elapsed=min(budget,charged()+3)))
    clock=threading.Thread(target=heartbeat,daemon=True);clock.start()
    class Capture(cp_model.CpSolverSolutionCallback):
        def on_solution_callback(self):
            result={k:v for k,v in constants.items() if v}
            result.update({k:self.value(v) for k,v in variables.items() if self.value(v)})
            s=cell.attach(x,result)
            d=x.result(solution=s);m.freeSol(s)
            report=validate(d);assert report["valid"]
            C=report["product_return_cmax"]
            prefix=f"candidate_{C:g}"
            atomic(folder/(prefix+".json"),normalize_schedule(cfg,d))
            atomic(folder/(prefix+"_values.json"),result)
            atomic(folder/"best.json",dict(upper=C,values=prefix+"_values.json"))
            print(name,C,flush=True)
    with (folder/"solver.log").open("a",encoding="utf8",buffering=1) as log:
        engine.log_callback=lambda s:log.write(s.rstrip()+"\n")
        status=engine.solve(cp,Capture())
    stop.set();clock.join()
    atomic(checkpoint,dict(identity=signature,elapsed=charged()))
    atomic(folder/"result.json",dict(identity=signature,elapsed=charged(),status=engine.status_name(status),local_lower=engine.best_objective_bound))
    m.freeProb()

if __name__=="__main__":main(sys.argv[1],sys.argv[2],int(sys.argv[3]))

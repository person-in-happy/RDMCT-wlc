"""Recover original-model integer schedules for a compact two-chamber packing."""
from dataclasses import replace
import math
from pathlib import Path
import sys
import time
import threading
import os

from prepare import (HERE,JMS,OUT,Config,Integrated,Decoder,Retiming,validate,cell,read,sha,
                     save,store_primary,sparse_witness,normalize_schedule,configuration)
from seed import constrain_seed
from ortools.sat.python import cp_model


def atomic(path,data):
    import json
    tmp=path.with_name(path.name+f".{os.getpid()}.tmp")
    tmp.write_text(json.dumps(data),encoding="utf8")
    os.replace(tmp,path)


def skeleton(cfg,layout):
    dec=Decoder(cfg)
    groups=[]
    for p in cfg.pjobs:
        ids=p["wafers"]
        groups.append([tuple(ids[i:i+2]) for i in range(0,8,2)])
    f,d=groups
    if layout=="chain31":
        specs=[("4x1",2,f[:2]),("4x1",3,f[2:]),("2x2",2,d[:3]),("2x2",3,d[3:])]
    elif layout=="chain22":
        specs=[("4x1",2,f[:2]),("4x1",3,f[2:]),("2x2",2,d[:2]),("2x2",3,d[2:])]
    elif layout=="mixedlead":
        specs=[("2x2",2,d[:2]),("4x1",3,f[:2]),("4x1",2,f[2:]),("2x2",3,d[2:])]
    else:raise ValueError(layout)
    genes=tuple(v for _ in range(16) for v in (0,0,1,1,0))
    doc=Retiming(dec.build(genes,specs),25).solve("A",None,10)
    if doc is None or not validate(doc)["valid"]:
        genes=tuple(v for _ in range(16) for v in (0,0,0,0,0))
        doc=Retiming(dec.build(genes,specs),25).solve("A",None,10)
    if doc is None or not validate(doc)["valid"]:raise ValueError("Failed to generate the candidate structure")
    return doc


def main(layout):
    dest=OUT/"proposals"/layout
    dest.mkdir(exist_ok=True,parents=True)
    code=sha(Path(__file__))
    prior=read(dest/"checkpoint.json") if (dest/"checkpoint.json").exists() else dict(elapsed=0,code=code)
    assert prior["code"]==code
    if (dest/"result.json").exists():return
    cfg=configuration()
    source=skeleton(cfg,layout)
    compact=replace(cfg,max_pairs=1+max(p["id"] for p in source["pairs"]),max_cycles=1+max(q["index"] for q in source["cycles"]),horizon=2500)
    warm=normalize_schedule(compact,source)
    warmvals=sparse_witness(compact,warm)
    x=Integrated(compact)
    m=x.model
    constrain_seed(x,warm,times=False)
    # The sole purpose of this restricted model is to discover feasible witnesses.
    # Release both robot orders, lock slots, hand assignment and all operation times.
    for v in m.getVars(transformed=False):
        if v.vtype()!="CONTINUOUS" and not v.name.startswith(("order_","sync_","slot_","code_")):
            val=round(warmvals.get(v.name,0))
            m.chgVarLb(v,val)
            m.chgVarUb(v,val)
    cp=cp_model.CpModel()
    variables={}
    constants={}
    for var in m.getVars(transformed=False):
        lo,hi=math.ceil(var.getLbOriginal()-1e-7),math.floor(var.getUbOriginal()+1e-7)
        if lo==hi:constants[var.name]=lo
        else:variables[var.name]=cp.new_int_var(lo,hi,var.name)
    for row in m.getConss():
        rhs=m.getRhs(row)
        lhs=m.getLhs(row)
        baseline=0
        terms=[]
        for key,value in m.getValsLinear(row).items():
            val=round(value)
            assert abs(val-value)<1e-8
            if key in constants:baseline+=val*constants[key]
            else:terms.append(val*variables[key])
        if lhs>-1e15:cp.add(sum(terms)>=math.ceil(lhs-baseline-1e-7))
        if rhs<1e15:cp.add(sum(terms)<=math.floor(rhs-baseline+1e-7))
    # The first a-priori practical target uses the independently proven 794-s lower bound.
    assert read(JMS/"results/table3_grid16_20261125/batch_bound_mixed.json")["lower"]==794
    cp.add(variables["Cmax"]<=900)
    cp.add(variables["Cmax"]>=794)
    cp.minimize(variables["Cmax"])
    rule=cp_model.CpSolver()
    rule.parameters.num_workers=1
    rule.parameters.random_seed=1
    rule.parameters.log_search_progress=True
    rule.parameters.log_to_stdout=False
    budget=360.
    used=prior["elapsed"]
    rule.parameters.max_time_in_seconds=max(0,budget-used)
    best_slot=dest/"best.json"
    if best_slot.exists():
        p=read(best_slot)
        cp.add(variables["Cmax"]<=math.ceil(p["upper"]))
        for key,v in read(dest/p["values"]).items():
            if key in variables:cp.add_hint(variables[key],v)
    start=time.monotonic()
    stop=threading.Event()
    def publish():
        while not stop.wait(3):
            atomic(dest/"checkpoint.json",dict(code=code,elapsed=min(budget,used+time.monotonic()-start+3)))
    clock=threading.Thread(target=publish,daemon=True)
    clock.start()
    class Solutions(cp_model.CpSolverSolutionCallback):
        def on_solution_callback(self):
            vals={k:v for k,v in constants.items() if v}
            vals.update({k:self.value(v) for k,v in variables.items() if self.value(v)})
            sol=cell.attach(x,vals)
            native=x.result(solution=sol)
            m.freeSol(sol)
            report=validate(native)
            if not report["valid"]:raise ValueError(report["errors"][:2])
            upper=report["product_return_cmax"]
            dest_file=f"candidate_{upper:g}"
            atomic(dest/(dest_file+".json"),normalize_schedule(cfg,native))
            atomic(dest/(dest_file+"_values.json"),vals)
            atomic(best_slot,dict(upper=upper,values=dest_file+"_values.json"))
            print("Compact feasible",layout,upper,flush=True)
    with (dest/"solver.log").open("a",encoding="utf8",buffering=1) as log:
        rule.log_callback=lambda line:log.write(line.rstrip()+"\n")
        status=rule.solve(cp,Solutions())
    stop.set()
    clock.join()
    elapsed=min(budget,used+time.monotonic()-start)
    atomic(dest/"checkpoint.json",dict(code=code,elapsed=elapsed))
    atomic(dest/"result.json",dict(code=code,elapsed=elapsed,status=rule.status_name(status),fixed_model_bound=rule.best_objective_bound))
    m.freeProb()

if __name__=="__main__":main(sys.argv[1])

"""Find native witnesses with compact, physically assigned pairs and ordered inbound routes."""
from dataclasses import replace
from itertools import pairwise
from pathlib import Path
import math
import os
import sys
import threading
import time
from candidate import atomic
from prepare import OUT,cell,configuration,Config,Integrated,normalize_schedule,read,sha,validate
from ortools.sat.python import cp_model


def main(layout):
    dest=OUT/"proposals"/layout
    dest.mkdir(exist_ok=True,parents=True)
    checkpoint=dest/"checkpoint.json"
    ident=dict(program=sha(Path(__file__)),config=sha(OUT/"input.json"),layout=layout)
    prior=read(checkpoint) if checkpoint.exists() else dict(identity=ident,elapsed=0)
    assert prior["identity"]==ident
    if (dest/"result.json").exists():return
    # The first two full batches occupy CH2 and CH3. New dual-exposure pairs
    # enter the front side and remain on the back side at the next cycle.
    chains={"guided31":([4,5,6],[7]),"guided22":([4,5],[6,7]),"guidedinter":([4,5,7],[6])}[layout]
    seq={2:[(0,1)],3:[(2,3)]}
    full=set(range(4))
    for c,chain in zip((2,3),chains):
        base=16+2*(c-2)
        seq[c]+=[*pairwise([base,*chain,base+1])]
    cfg=configuration()
    compact=replace(cfg,max_pairs=20,max_cycles=max(map(len,seq.values())),horizon=2500)
    x=Integrated(compact)
    m=x.model
    groups={g.labels[0]:g for g in x.groups}
    def fix(v,b):
        if isinstance(v,(int,float)):assert v==b
        elif hasattr(v,"getLbOriginal"):
            m.chgVarLb(v,b);m.chgVarUb(v,b)
        else:m.addCons(v==b)
    active_ids=set(range(8))|set(range(16,20))
    these_ch={p:c for c in seq for step in seq[c] for p in step}
    def payload(p,r):
        if p in range(8):
            return cfg.pjobs[p//4]["wafers"][2*(p%4)+r]
        if p>=16:
            # A chamber's two boundary dummy pairs may re-use the same two
            # identities once the starting pair has left.
            return f"D{1+4*((p-16)//2)+2*((p-16)%2)+r}"
        return ""
    # Canonical model requires no skipped first use of dummy IDs. The two
    # boundary pairs per chamber have distinct identities D1...D8.
    for p in range(x.P):
        on=p in active_ids
        fix(x.pair.active[p],int(on))
        for r in (0,1):
            label=payload(p,r) if on else ""
            if p<16:
                for g in x.groups:fix(x.pair.member[g.identifier,p,r],int(label in g.labels))
            for d in range(1,9):fix(x.pair.dummy_identity[f"D{d}",p,r],int(label==f"D{d}"))
        for c in (2,3):fix(x.pair.chamber[p,c],int(these_ch.get(p)==c))
        for k in ("4x1","2x2","clean"):fix(x.pair.mode[p,k],int(on and k==("4x1" if p in full else "2x2")))
    for (c,q),used in x.cy.used.items():
        step=seq[c][q] if q<len(seq[c]) else None
        fix(used,int(step is not None))
        for p in range(x.P):
            fix(x.cy.occupancy[p,c,q],int(step is not None and p in step))
            fix(x.front[p,c,q],int(step is not None and p==step[1]))
        for k in ("4x1","2x2","clean"):
            fix(x.cy.kind[c,q,k],int(step is not None and k==("4x1" if q==0 else "2x2")))
    names={v.name:v for v in m.getVars(transformed=False)}
    for p in range(8):
        for r in (0,1):
            for kind,index in (("U",r),("L",r),("VTR_hand_in",r),("VTR_hand_out",r+2)):
                key=(f"slot_{kind}_prod_{p}_{r}_{index}" if kind in ("U","L") else
                     f"slot_VTR_hand_prod_{p}_{r}_{kind.split('_')[-1]}_{index}")
                fix(names[key],1)
    inbound=[(p,r) for p in range(8) for r in (0,1)]
    outbound=[(p,r) for p in (1,0,3,2,4,5,6,7) for r in (0,1)]
    for way,steps in ((inbound,("origin_pick","al_put","al_pick","upper_put","source_pick")),
                      (outbound,("destination_put","lower_pick","origin_put"))):
        for first,second in pairwise(way):
            for step in steps:
                a=names[f"prod_{first[0]}_{first[1]}_{step}_s"]
                b=names[f"prod_{second[0]}_{second[1]}_{step}_s"]
                m.addCons(b>=a)
    cp=cp_model.CpModel()
    var={}
    fixed={}
    for n,v in names.items():
        lo,hi=math.ceil(v.getLbOriginal()-1e-7),math.floor(v.getUbOriginal()+1e-7)
        if lo==hi:fixed[n]=lo
        else:var[n]=cp.new_int_var(lo,hi,n)
    for row in m.getConss():
        constant=0;terms=[]
        for n,v in m.getValsLinear(row).items():
            a=round(v);assert a==v
            if n in fixed:constant+=a*fixed[n]
            else:terms.append(a*var[n])
        lo,hi=m.getLhs(row),m.getRhs(row)
        if lo>-1e15:cp.add(sum(terms)>=math.ceil(lo-constant-1e-7))
        if hi<1e15:cp.add(sum(terms)<=math.floor(hi-constant+1e-7))
    cp.add(var["Cmax"]>=794)
    cp.add(var["Cmax"]<=990)
    cp.minimize(var["Cmax"])
    engine=cp_model.CpSolver()
    engine.parameters.num_workers=1
    engine.parameters.random_seed=1
    engine.parameters.log_search_progress=True
    engine.parameters.log_to_stdout=False
    budget=240.
    engine.parameters.max_time_in_seconds=max(0,budget-prior["elapsed"])
    warm=dest/"best.json"
    if warm.exists():
        info=read(warm)
        cp.add(var["Cmax"]<=info["upper"])
        for n,a in read(dest/info["values"]).items():
            if n in var:cp.add_hint(var[n],a)
    start=time.monotonic()
    stop=threading.Event()
    def elapsed():return min(budget,prior["elapsed"]+time.monotonic()-start)
    def monitor():
        while not stop.wait(3):atomic(checkpoint,dict(identity=ident,elapsed=min(budget,elapsed()+3)))
    timer=threading.Thread(target=monitor,daemon=True);timer.start()
    class Capture(cp_model.CpSolverSolutionCallback):
        def on_solution_callback(self):
            vals={k:v for k,v in fixed.items() if v}
            vals.update({k:self.value(v) for k,v in var.items() if self.value(v)})
            sol=cell.attach(x,vals)
            doc=x.result(solution=sol);m.freeSol(sol)
            rep=validate(doc)
            assert rep["valid"],rep["errors"][:2]
            upper=rep["product_return_cmax"]
            name=f"candidate_{upper:g}"
            atomic(dest/(name+".json"),normalize_schedule(cfg,doc))
            atomic(dest/(name+"_values.json"),vals)
            atomic(warm,dict(upper=upper,values=name+"_values.json"))
            print(layout,upper,flush=True)
    with (dest/"solver.log").open("a",encoding="utf8",buffering=1) as log:
        engine.log_callback=lambda s:log.write(s.rstrip()+"\n")
        result=engine.solve(cp,Capture())
    stop.set();timer.join()
    atomic(checkpoint,dict(identity=ident,elapsed=elapsed()))
    atomic(dest/"result.json",dict(identity=ident,elapsed=elapsed(),status=engine.status_name(result),
                                  fixed_structure_bound=engine.best_objective_bound))
    m.freeProb()

if __name__=="__main__":main(sys.argv[1])

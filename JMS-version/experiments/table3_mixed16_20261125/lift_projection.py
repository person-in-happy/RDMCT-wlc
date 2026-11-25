"""Complete a frozen product-projection chamber sequence in the full native physical model."""
from dataclasses import replace
import itertools
import math
from pathlib import Path
import sys
import threading
import time

from prepare import OUT,JMS,Integrated,cell,configuration,normalize_schedule,read,sha,validate
from candidate import atomic
from ortools.sat.python import cp_model


def structure(hint):
    cfg=configuration()
    members={}
    by_product={}
    cycle_map={}
    aux_groups=[]
    cfg_wafer=[w for job in cfg.pjobs for w in job["wafers"]]
    # Product pair and dummy IDs follow canonical first use.
    labels=set()
    for cycles in hint["cycles"].values():
        for cy in cycles:
            for side in ("back","front"):
                if cy[side]:labels.add(tuple(sorted(cy[side],key=cfg_wafer.index)))
    sorted_groups=sorted(labels,key=lambda q:tuple(cfg_wafer.index(w) for w in q))
    next_dummy=1
    for p,group in enumerate(sorted_groups):
        members[p]=list(group)
        for r,w in enumerate(group):by_product[w]=(p,r)
        if len(group)==1:
            members[p].append(f"D{next_dummy}");next_dummy+=1
    assert next_dummy<=9
    for c,rows in sorted(hint["cycles"].items()):
        seq=[]
        for t,cy in enumerate(rows):
            ids=[]
            for side in ("back","front"):
                group=tuple(sorted(cy[side],key=cfg_wafer.index))
                if group:p=sorted_groups.index(group)
                else:
                    p=16+len(aux_groups);aux_groups.append(p)
                    if next_dummy<=7:
                        members[p]=[f"D{next_dummy}",f"D{next_dummy+1}"]
                        next_dummy+=2
                    else:
                        # Late or chamber-separated boundary pairs can borrow
                        # an identity again; native loan mutual exclusion remains.
                        i=2*((len(aux_groups)-1)%4)+1
                        members[p]=[f"D{i}",f"D{i+1}"]
                ids.append(p)
            seq.append((cy["mode"],*ids))
        cycle_map[int(c)]=seq
    return members,by_product,cycle_map


def main(path,name,policy):
    reference=Path(path).resolve()
    hint=read(reference)
    folder=OUT/"proposals"/name
    folder.mkdir(exist_ok=True,parents=True)
    checkpoint=folder/"checkpoint.json"
    signature=dict(program=sha(Path(__file__)),source=sha(reference),cfg=sha(OUT/"input.json"),policy=policy)
    prior=read(checkpoint) if checkpoint.exists() else dict(identity=signature,elapsed=0)
    assert prior["identity"]==signature
    if (folder/"result.json").exists():return
    cfg=configuration()
    members,by_label,seq=structure(hint)
    small=replace(cfg,max_pairs=1+max(members),max_cycles=max(map(len,seq.values())),horizon=2400)
    x=Integrated(small)
    m=x.model
    chamber={p:c for c,rows in seq.items() for _,a,b in rows for p in (a,b)}
    mode={p:kind for rows in seq.values() for kind,a,b in rows for p in (a,b)}
    def pin(v,val):
        if isinstance(v,(int,float)):assert v==val
        elif hasattr(v,"getLbOriginal"):
            m.chgVarLb(v,val);m.chgVarUb(v,val)
        else:m.addCons(v==val)
    for p in range(x.P):
        group=members.get(p,[])
        pin(x.pair.active[p],int(bool(group)))
        for r in (0,1):
            w=group[r] if group else ""
            if p<16:
                for g in x.groups:pin(x.pair.member[g.identifier,p,r],int(w in g.labels))
            for i in range(1,9):pin(x.pair.dummy_identity[f"D{i}",p,r],int(w==f"D{i}"))
        for c in cfg.chambers:pin(x.pair.chamber[p,c],int(chamber.get(p)==c))
        for k in ("4x1","2x2","clean"):pin(x.pair.mode[p,k],int(mode.get(p)==k))
    for (c,q),used in x.cy.used.items():
        cycle=seq[c][q] if q<len(seq[c]) else None
        pin(used,int(bool(cycle)))
        for p in range(x.P):
            pin(x.cy.occupancy[p,c,q],int(bool(cycle) and p in cycle[1:]))
            pin(x.front[p,c,q],int(bool(cycle) and p==cycle[2]))
        for k in ("4x1","2x2","clean"):pin(x.cy.kind[c,q,k],int(bool(cycle) and cycle[0]==k))
    names={v.name:v for v in m.getVars(transformed=False)}
    events=hint["product_event_hints"]
    def z(w,step):
        p,r=by_label[w]
        if step in ("load","unload"):return f"prod_{p}_{r}_ch_{step}_s"
        return f"prod_{p}_{r}_{step}_s"
    # Preserve only the requested traffic order from the relaxation. Identity,
    # exposure, all physical resources, residence and dummy loans remain native.
    steps=("al_put","al_pick","upper_put","source_pick","destination_put","lower_pick") if policy=="ordered" else ("al_put","al_pick")
    for kind in steps:
        wafers=sorted(events,key=lambda w:(events[w][kind],w))
        for a,b in itertools.pairwise(wafers):
            if events[a][kind]!=events[b][kind]:
                m.addCons(names[z(a,kind)]<=names[z(b,kind)])
    for w,(p,r) in by_label.items():
        for direction,i in (("in",r),("out",r+2)):pin(names[f"slot_VTR_hand_prod_{p}_{r}_{direction}_{i}"],1)
    cp=cp_model.CpModel()
    free={};fixed={}
    for n,v in names.items():
        low,high=math.ceil(v.getLbOriginal()-1e-7),math.floor(v.getUbOriginal()+1e-7)
        if low==high:fixed[n]=low
        else:free[n]=cp.new_int_var(low,high,n)
    for row in m.getConss():
        terms=[];c0=0
        for n,a in m.getValsLinear(row).items():
            b=round(a);assert a==b
            if n in fixed:c0+=fixed[n]*b
            else:terms.append(free[n]*b)
        low,high=m.getLhs(row),m.getRhs(row)
        if low>-1e15:cp.add(sum(terms)>=math.ceil(low-c0-1e-7))
        if high<1e15:cp.add(sum(terms)<=math.floor(high-c0+1e-7))
    cp.add(free["Cmax"]>=794);cp.add(free["Cmax"]<=925)
    cp.minimize(free["Cmax"])
    best=folder/"best.json"
    if best.exists():
        b=read(best)
        cp.add(free["Cmax"]<=b["upper"])
        hints=read(folder/b["values"])
    else:
        hints={z(w,k):int(round(v)) for w,ts in events.items() for k,v in ts.items() if k in
               ("origin_pick","origin_put","al_put","al_pick","upper_put","lower_pick","load","unload","source_pick","destination_put")}
    for n,v in hints.items():
        if n in free:cp.add_hint(free[n],v)
    engine=cp_model.CpSolver()
    budget=180
    engine.parameters.num_workers=1;engine.parameters.random_seed=1
    engine.parameters.max_time_in_seconds=max(0,budget-prior["elapsed"])
    engine.parameters.log_search_progress=True;engine.parameters.log_to_stdout=False
    started=time.perf_counter()
    def used():return min(budget,prior["elapsed"]+time.perf_counter()-started)
    stop=threading.Event()
    def heartbeat():
        while not stop.wait(4):atomic(checkpoint,dict(identity=signature,elapsed=min(budget,used()+4)))
    clock=threading.Thread(target=heartbeat,daemon=True);clock.start()
    class Capture(cp_model.CpSolverSolutionCallback):
        def on_solution_callback(self):
            values={k:v for k,v in fixed.items() if v}
            values.update({k:self.value(v) for k,v in free.items() if self.value(v)})
            sol=cell.attach(x,values)
            native=x.result(solution=sol);m.freeSol(sol)
            checked=validate(native);assert checked["valid"],checked["errors"][:2]
            upper=checked["product_return_cmax"];stem=f"candidate_{upper:g}"
            atomic(folder/(stem+".json"),normalize_schedule(cfg,native))
            atomic(folder/(stem+"_values.json"),values)
            atomic(best,dict(upper=upper,values=stem+"_values.json"))
            print(name,upper,flush=True)
    with (folder/"solver.log").open("a",buffering=1,encoding="utf8") as log:
        engine.log_callback=lambda s:log.write(s.rstrip()+"\n")
        status=engine.solve(cp,Capture())
    stop.set();clock.join()
    atomic(checkpoint,dict(identity=signature,elapsed=used()))
    atomic(folder/"result.json",dict(identity=signature,status=engine.status_name(status),elapsed=used(),
                                    fixed_model_lower=engine.best_objective_bound))
    m.freeProb()

if __name__=="__main__":main(*sys.argv[1:])

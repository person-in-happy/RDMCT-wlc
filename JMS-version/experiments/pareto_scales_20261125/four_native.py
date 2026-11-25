"""Complete the two-singleton mixed chain in the native model at the projected makespan."""
import argparse
from dataclasses import replace
from pathlib import Path
import sys
import time
from sweep import cell, Config, Integrated, HERE, JMS, OUT, atomic, metrics, read, save, sha
sys.path.insert(0,str(HERE.parent/"pareto_rl_dmct_20261119"))
from witness import sparse_witness
from seed import normalize_schedule


def run(h,cap,timing):
    s=read(OUT/"four_bound/2_1.json")
    src=JMS/f"results/table4_one_percent_20261124/inputs/D_n4_H{h}_mixed_dual/input.json"
    cfg=Config(**read(src)["config"])
    dest=OUT/f"four_native_H{h}"/f"{cap}_{timing}"
    dest.mkdir(exist_ok=True,parents=True)
    signature={"implementation":sha(Path(__file__)),"input":sha(src),"projection":sha(OUT/"four_bound/2_1.json")}
    if (dest/"result.json").exists() and read(dest/"result.json")["signature"]==signature:
        return
    small=replace(cfg,max_pairs=9 if h==3 else 7,max_cycles=4 if h==3 else 3,horizon=1600)
    x=Integrated(small);m=x.model
    budget=40
    cell.scip_settings(m,dict(n=x.N,seed=1,seconds=budget,gap=0),dest)
    m.setRealParam("numerics/feastol",1e-8)
    def pin(v,val):
        if isinstance(v,(int,float)):assert v==val
        elif hasattr(v,"getLbOriginal"):
            m.chgVarLb(v,val);m.chgVarUb(v,val)
        else:m.addCons(v==val)
    template={0:["LP1_W1","LP2_W1"],1:["LP3_W1","D1"],2:["LP4_W1","D2"],
              4:["D3","D4"],5:["D5","D6"],6:["D7","D8"]}
    starts=[s["routes"][i]["load"]+1 for i in (2,3)]+[s["chamber_ops"]["('D', 'fl2')"]+1,s["routes"][0]["load"]+1]
    cycles={3:[(4,0)],2:[(5,1),(1,2),(2,6)]}
    if h==3:
        template.update({7:["D1","D2"],8:["D3","D4"]})
        cycles[2].append((7,8))
    for p in range(x.P):
        members=template.get(p,[]);pin(x.pair.active[p],int(bool(members)))
        for r in range(2):
            w=members[r] if members else ""
            if p<x.N:
                for group in x.groups:pin(x.pair.member[group.identifier,p,r],int(w in group.labels))
            for i in range(1,cfg.dummy_count+1):pin(x.pair.dummy_identity[f"D{i}",p,r],int(w==f"D{i}"))
        ch=3 if p in (0,4) else 2
        mode="4x1" if ch==3 else "clean" if p in (7,8) else "2x2"
        for c in cfg.chambers:pin(x.pair.chamber[p,c],int(bool(members) and c==ch))
        for k in ("4x1","2x2","clean"):pin(x.pair.mode[p,k],int(bool(members) and k==mode))
    for c in cfg.chambers:
        for q in range(x.Q):
            step=cycles[c][q] if q<len(cycles[c]) else None;pin(x.cy.used[c,q],int(bool(step)))
            k="4x1" if c==3 else "clean" if q==3 else "2x2"
            if step and k!="clean" and timing=="pinned":
                pin(x.cy.start[c,q],starts[-1] if c==3 else starts[q])
            for p in range(x.P):
                pin(x.cy.occupancy[p,c,q],int(bool(step) and p in step))
                pin(x.front[p,c,q],int(bool(step) and p==step[1]))
            for mode in ("4x1","2x2","clean"):pin(x.cy.kind[c,q,mode],int(bool(step) and k==mode))
    for p,r in ((0,0),(1,6.75),(2,7)):
        m.addCons(x.unload[p]["s"]-x.load[p]["e"]==180+r)
    m.addCons(x.cmax<=cap)
    m.setObjective(x.cmax,"minimize")
    t=time.monotonic()
    atomic(dest/"progress.json",dict(completed=0,failed=0,elapsed=0,eta_remaining=budget,eta_total=budget,
                                   basis="per-try SCIP time limit; stop on feasible endpoint"))
    print(f"H{h} cap={cap} {timing}, 0/1; solver budget {budget}s",flush=True)
    if cap==417:m.setIntParam("limits/solutions",1)
    m.optimize()
    status=str(m.getStatus())
    rec=dict(status=status,signature=signature,cap=cap,timing=timing,wall=time.monotonic()-t)
    if m.getNSols():
        doc=normalize_schedule(cfg,x.result(solution=m.getBestSol()))
        native=cell.lift(cfg,sparse_witness(cfg,doc),None,rebuild=True)
        assert native
        doc,a,_,replay,rows=native
        v=metrics(doc)
        assert abs(v["secondary"]-3.46875)<1e-7 and v["cmax"]<=cap+1e-7
        save(dest/"schedule.json",doc);save(dest/"assignment.json.gz",a)
        rec.update(metrics=v,replay=replay,rows=rows,files={k:sha(dest/k) for k in ("assignment.json.gz","schedule.json")})
    atomic(dest/"result.json",rec)
    atomic(dest/"progress.json",dict(completed=1,failed=0,elapsed=rec["wall"],eta_remaining=0,eta_total=rec["wall"]))
    print(rec.get("metrics",status),flush=True)


if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("h",type=int);p.add_argument("cap",type=int)
    p.add_argument("timing",choices=("pinned","free"));a=p.parse_args();run(a.h,a.cap,a.timing)

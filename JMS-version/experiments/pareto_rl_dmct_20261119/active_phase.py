"""Supplemental small-instance search with product-pair topology fixed and robot orders open."""
import argparse
from dataclasses import replace
import gzip
import json
from pathlib import Path
import sys
import time

from common import JMS, TOL, config, dominates, metrics, lower_bound, save
from decoder import Decoder, Retiming
from native import Native
from scip_imports import scip
from validate import validate

# Only the physical terminal-clean reconstruction is reused from the two-wafer model.
# No reference coordinates, caps, witnesses or prior run files enter this search.
sys.path.append(str(JMS/"experiments/pareto_front_20261118"))
from family import extend


def productive(cfg, paired, upper):
    blocks = 1 if paired else 2
    cut = replace(cfg, cleaning_interval=cfg.cleaning_interval+1, max_pairs=2+2*blocks, max_cycles=2)
    part = Native(cut,1,25)
    x,m = part.x,part.m
    small_horizon = upper+max(cfg.module_residency,cfg.robot_residency)+max(cfg.lower_reset,cfg.upper_reset)
    for v in part.variables:
        if v.vtype()=="CONTINUOUS":
            m.chgVarUb(v,min(v.getUbOriginal(),small_horizon))
    active = {0,2,3} if paired else set(range(6))
    def fix(variable, value):
        if isinstance(variable,(int,float)):
            if variable != value:
                raise ValueError("Inconsistent active pair topology")
        else:
            m.addCons(variable==int(value))
    events = {e["name"]:e for e in x.events}
    for p in range(x.P):
        fix(x.pair.active[p],p in active)
        if p<2:
            fix(x.pair.product[p,1],paired and p==0)
        elif p in active:
            for leg in ("source_pick","destination_put"):
                m.addCons(events[f"aux_{p}_0_{leg}"]["s"]==events[f"aux_{p}_1_{leg}"]["s"])
    if paired:
        for p, ids in ((2,(1,2)),(3,(3,4))):
            for slot, ident in enumerate(ids):
                fix(x.pair.dummy_identity[f"D{ident}",p,slot],1)
        m.addCons(x.jobs["prod_0_0"]["al_put"]["s"]<=x.jobs["prod_0_1"]["al_put"]["s"])
    for k,ch in enumerate(cfg.chambers):
        for q in range(2):
            cycle = ((2+2*k,k) if q==0 else (k,3+2*k)) if k<blocks else ()
            for mode in ("2x2","clean"):
                fix(x.cy.kind[ch,q,mode],bool(cycle) and mode=="2x2")
            for p in range(x.P):
                fix(x.cy.occupancy[p,ch,q],p in cycle)
                fix(x.front[p,ch,q],bool(cycle) and p==cycle[-1])
    if not paired:
        # During each exposure a PD pair and a DD support pair occupy three dummies.
        # Two such exposures overlap only when at least six dummies are available.
        left,right = cfg.chambers
        m.addCons(x.cy.start[left,0]<=x.cy.start[right,0])
        if cfg.dummy_count<6:
            for i in range(2):
                for j in range(2):
                    precedes=m.addVar(vtype="B")
                    m.addCons(x.cy.start[right,j]>=x.cy.end[left,i]-small_horizon*(1-precedes))
                    m.addCons(x.cy.start[left,i]>=x.cy.end[right,j]-small_horizon*precedes)
    m.addCons(x.cmax<=upper)
    m.addCons(part.B>=lower_bound(cfg,2,int(paired)))
    return part


def run(out, seconds):
    out.mkdir(parents=True,exist_ok=False)
    start=time.monotonic()
    cfg=config("S1")
    full=Native(cfg,1,25)
    dec=Decoder(cfg)
    records=[]
    log=[]
    def admit(data, origin):
        if not validate(data)["valid"] or not full.warm(data):
            raise ValueError("Physical extension rejected by the original model")
        mm=metrics(data,25)
        ab=mm["cmax"],mm["secondary"]
        elapsed=time.monotonic()-start
        if elapsed>seconds:
            return ab
        if any(dominates(r["ab"],ab) or max(abs(a-b) for a,b in zip(r["ab"],ab))<=TOL for r in records):
            return ab
        records[:]=[r for r in records if not dominates(ab,r["ab"])]
        path="witness_%03d.json.gz" % (len(list(out.glob("witness_*")))+1)
        with gzip.open(out/path,"wt",encoding="utf-8") as f:
            json.dump(data,f,separators=(",",":"),allow_nan=False)
        records.append(dict(ab=ab,origin=origin,seconds=elapsed,file=path))
        return ab

    try:
        # Infer the useful makespan ceiling from a same-run constructive point on the
        # analytic B floor. Any slower solution is dominated by this actual timetable.
        candidates=[]
        for g in ((0,0,2,1,0,0,0,0,0,0),(1,0,0,0,0,1,1,0,0,0),
                  (1,0,1,0,0,1,1,1,0,0),(1,0,1,1,0,1,1,1,1,0)):
            data=Retiming(dec.build(g,dec.pairing(g)),25).solve("B",None,4)
            if data is not None:
                candidates.append(admit(data,"constructive"))
        ceiling=min((a for a,b in candidates if b<=lower_bound(cfg,2,0)+TOL),default=None)
        if ceiling is None:
            ceiling=max(a for a,b in candidates)+cfg.module_residency
        for i,paired in enumerate((True,False)):
            deadline=start+seconds*(.33 if paired else 1)
            part=productive(cfg,paired,ceiling)
            phase="PP" if paired else "PD+PD"
            try:
                cap=None
                for step in range(12):
                    m,x=part.m,part.x
                    if time.monotonic()+.4>deadline:
                        break
                    if cap is not None:
                        m.addCons(part.B<=cap)
                    statuses=[]
                    candidate=None
                    first_a=None
                    # All cutoffs here derive from feasible solutions found in this run.
                    lock=None
                    for goal in ("A","B"):
                        left=deadline-time.monotonic()
                        if left<.15:
                            break
                        m.setObjective(x.cmax if goal=="A" else part.B,"minimize")
                        m.setRealParam("limits/time",max(.05,min(left-.06,12. if paired else 23.)))
                        m.optimize()
                        status=str(m.getStatus())
                        statuses.append(status)
                        sol=m.getBestSol()
                        if sol is None:
                            m.freeTransform()
                            break
                        if not m.checkSol(sol,original=True,completely=True):
                            statuses.append("candidate_rejected_original_rows")
                            m.freeTransform()
                            break
                        prod=x.result(solution=sol)
                        candidate=admit(extend(cfg,prod),phase)
                        m.freeTransform()
                        if goal=="A":
                            first_a=candidate[0]
                            lock=m.addCons(x.cmax<=first_a+1e-7)
                    if lock is not None:
                        m.delCons(lock)
                    log.append(dict(family=phase,cap=cap,observed=candidate,status=statuses,
                                    elapsed_s=time.monotonic()-start))
                    save(out/"queries.json",log)
                    if candidate is None or (cap is not None and candidate[1]>cap+TOL):
                        break
                    if candidate[1]<=lower_bound(cfg,2,int(paired))+TOL:
                        break
                    # Sampling a continuous objective at this resolution is heuristic.
                    cap=candidate[1]-.01
                    print(f"{phase} 查询 {step+1} | 物理折中 {candidate} | 已保留 {len(records)} | "
                          f"预计剩余 {max(0,start+seconds-time.monotonic()):.0f}s",flush=True)
            finally:
                part.close()
            print(f"结构完成 {i+1}/2 | 失败 0 | 当前排程 {len(records)}",flush=True)
    finally:
        full.close()
    save(out/"result.json",dict(case="S1",seconds_budget=seconds,seconds_used=time.monotonic()-start,
         initial_ceiling=ceiling,front=sorted(records,key=lambda r:r["ab"]),queries=len(log),
         full_original_accepted=True,B_resolution=.01,output_scope="active topologies, checked feasible witnesses"))
    return records


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("out",type=Path)
    parser.add_argument("--seconds",type=int,default=150)
    args=parser.parse_args()
    run(args.out.resolve(),args.seconds)

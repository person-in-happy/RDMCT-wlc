"""Compress the inter-cycle gaps of the validated 75-wafer schedule."""
from pathlib import Path
from collections import Counter,defaultdict
import time
import sys
import threading
import msvcrt

import numpy as np
from scipy.optimize import linprog
from scipy.sparse import coo_matrix
from ortools.sat.python import cp_model
from scale75 import (OUT as PRIOR, SOURCE, chamber_gaps, robot_gaps, observed, source_timing,
                     read, atom, digest, rel, pairs, numeric)

OUT=PRIOR.parent/"n75_compact"
# The largest observed gaps lie at 4392--4647 and 4098--4296 s.
WINDOWS=[(3800,4800),(4200,4880),(3850,4450),(550,880),(1850,2250),
         (5350,6050),(0,600),(3700,4700)]
SECONDS=7

def compact_key(score):
    ch=score["chambers"]
    return (sum(c["longest_empty"] for c in ch.values()),
            sum(c["internal_empty"] for c in ch.values()),
            max(c["longest_empty"] for c in ch.values()),
            sum(c["occupied_wait"] for c in ch.values()),
            score["secondary"],score["cmax"],score["vtr_held_wait"]+score["atr_held_wait"])

def refine(timing,s,records,doc,limits):
    n=len(s); dim=n+2; rows=[];cols=[];vals=[];rhs=[]
    def row(components,ub):
        for j,x in components:
            rows.append(len(rhs));cols.append(j);vals.append(x)
        rhs.append(ub)
    def coeff(parts):
        multipliers=Counter();lag=0
        for a,b,dt in parts:
            multipliers[a]-=1;multipliers[b]+=1;lag+=dt
        return multipliers,lag
    objective=np.zeros(dim)
    for a,b,dt in timing.edges:row([(a,1),(b,-1)],-dt)
    for _,_,a,b,dt in pairs(timing):
        row([(a,1),(b,-1)],s[a]-s[b]);row([(a,-1),(b,1)],s[b]-s[a])
    bounds=[(0,limits["equipment_release"]-t) for t in timing.tails]
    for i in timing.returns:bounds[i]=(0,min(bounds[i][1],limits["cmax"]-timing.actions[i].duration))
    holds,empty=chamber_gaps(timing)
    for j,ch in enumerate(sorted(holds)):
        cap=limits["chambers"][ch]
        bounds.append((0,cap["longest_empty"]));objective[n+j]=3500
        for a,b,dt in empty[ch]:
            row([(a,-1),(b,1),(n+j,-1)],dt)
        for label,spans,w in (("occupied_wait",holds[ch],1),("internal_empty",empty[ch],220)):
            c,constant=coeff(spans);row(c.items(),cap[label]+constant)
            for i,v in c.items():objective[i]+=w*v
    for robot,spans in robot_gaps(records,s,doc).items():
        c,constant=coeff(spans);row(c.items(),limits[robot.lower()+"_held_wait"]+constant)
        for i,v in c.items():objective[i]+=.008*v
    a=coo_matrix((vals,(rows,cols)),shape=(len(rhs),dim)).tocsr()
    res=linprog(objective,A_ub=a,b_ub=rhs,bounds=bounds,method="highs-ds")
    if not res.success:return None
    if np.max(abs(res.x[:n]-np.rint(res.x[:n])))>1e-6:
        res=linprog(objective,A_ub=a,b_ub=rhs,bounds=bounds,integrality=np.ones(dim),method="highs",options={"time_limit":4})
        if res.x is None or np.max(abs(res.x[:n]-np.rint(res.x[:n])))>1e-5:return None
    return np.rint(res.x[:n]).astype(int).tolist()

def adjust(timing,engine,ref,window,limits,seconds):
    m=cp_model.CpModel()
    lo,hi=window
    # A common suffix advance can transmit a gain made in a local window to the last returns.
    shift=m.new_int_var(0,65,"advance");m.add_hint(shift,0)
    times=[]
    for i,t in enumerate(ref):
        if t<lo-180:
            v=m.new_constant(t)
        elif t>hi+180:
            v=m.new_int_var(t-65,t,"");m.add(v==t-shift);m.add_hint(v,t)
        else:
            v=m.new_int_var(max(0,t-150),min(t+150,int(limits["equipment_release"]-timing.tails[i])),"");m.add_hint(v,t)
        times.append(v)
    engine.add_order(m,times,ref,(lo,hi,100))
    for i in timing.returns:m.add(times[i]+int(timing.actions[i].duration)<=round(limits["cmax"]))
    groups=defaultdict(list);total=[]
    for mode,count,a,b,dt in pairs(timing):
        v=m.new_int_var(0,100,"");m.add(v==times[b]-times[a]-dt);m.add_hint(v,ref[b]-ref[a]-dt)
        groups[mode].append(v);total.append(count*v)
    differences=[]
    for vals in groups.values():
        low=m.new_int_var(0,100,"");high=m.new_int_var(0,100,"")
        m.add_min_equality(low,vals);m.add_max_equality(high,vals);differences.append(high-low)
    spread=m.new_int_var(0,100,"");sq=m.new_int_var(0,10000,"")
    m.add_max_equality(spread,differences);m.add_multiplication_equality(sq,[spread,spread])
    m.add(2*sum(total)+75*sq<=round(limits["secondary"]*150))
    held,empty=chamber_gaps(timing)
    objective=[]
    for ch in held:
        cap=limits["chambers"][ch]
        for name,spans in [("occupied_wait",held[ch]),("internal_empty",empty[ch])]:
            gaps=[times[b]-times[a]-int(dt) for a,b,dt in spans]
            m.add(sum(gaps)<=cap[name])
            objective.append((10 if name=="internal_empty" else 1)*sum(gaps))
            if name=="internal_empty":
                maxgap=m.new_int_var(0,cap["longest_empty"],f"max{ch}")
                m.add_max_equality(maxgap,gaps)
                m.add_hint(maxgap,max(ref[b]-ref[a]-dt for a,b,dt in spans))
                objective.append(500*maxgap)
    m.minimize(sum(objective)-shift)
    solver=cp_model.CpSolver();solver.parameters.max_time_in_seconds=seconds
    solver.parameters.num_search_workers=4;solver.parameters.random_seed=19
    status=solver.solve(m)
    if status in (cp_model.INFEASIBLE,cp_model.MODEL_INVALID):raise ValueError(solver.status_name(status))
    return ([solver.value(v) for v in times] if status in (cp_model.OPTIMAL,cp_model.FEASIBLE) else ref),solver.status_name(status)

def run():
    OUT.mkdir(parents=True,exist_ok=True)
    with (OUT/"run.lock").open("a+b") as lock:
        try:msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
        except OSError:print("Compression search already active.");return
        before=read(PRIOR/"evidence.json");assert before["schedule_sha256"]==digest(PRIOR/"result.json")
        signature={"worker":digest(Path(__file__)),"parent":before["schedule_sha256"],"source":digest(SOURCE),"seed":19,"cp_workers":4,"seconds_per_window":SECONDS}
        endpoint=OUT/"evidence.json"
        if endpoint.exists():
            assert read(endpoint)["signature"]==signature and digest(OUT/"result.json")==read(endpoint)["schedule_sha256"]
            print("Validated endpoint, remaining 0 s.");return
        save=OUT/"checkpoint.json";w=read(save) if save.exists() else dict(next=0,signature=signature,history=[])
        if w["signature"]!=signature:raise ValueError("Protocol changed")
        status_path=OUT/"status.json";status=read(status_path) if status_path.exists() else {}
        carry=status.get("elapsed_s",0);start=time.monotonic();total=len(WINDOWS)+2
        status.update(stage="starting gap compression",completed=w["next"],failed=0,total=total)
        quit_signal=threading.Event()
        def report():
            elapsed=carry+time.monotonic()-start
            left=(max(0,total-1-status["completed"])*9+max(1,24-(time.monotonic()-status.get("audit_start",time.monotonic())))) if status["completed"]<total else 0
            status.update(elapsed_s=round(elapsed,2),estimated_total_s=round(elapsed+left,2),remaining_s=round(left,2),basis="7 s per local search with 4 threads plus retiming; first 75-wafer audit took about 20 s.")
            atom(status_path,dict(status));print(f'{status["completed"]}/{total} {status["stage"]}, failed={status["failed"]}, elapsed {elapsed:.1f}s, total ~{elapsed+left:.0f}s, remaining ~{left:.0f}s.',flush=True)
        def beat():
            while not quit_signal.wait(7):report()
        report();thread=threading.Thread(target=beat,daemon=True);thread.start()
        try:
            base,_,records,_,source=source_timing();from scale import first
            blocks=[b for b,_ in base.blocks];engine=first.ChamberIdle(base.cfg,blocks)
            ref=w.get("starts",read(PRIOR/"checkpoint.json")["starts"]);best=w.get("best",before["after"])
            for k in range(w["next"],total-1):
                trial=ref;stage="fixed-order minimax gaps";solverstatus="retiming"
                if k:
                    stage=f"resource order {WINDOWS[k-1]}"
                    spent=w.setdefault("spent",{}).get(str(k),0)
                    w["spent"][str(k)]=SECONDS;atom(save,w)
                    trial,solverstatus=adjust(base,engine,ref,WINDOWS[k-1],best,max(.05,SECONDS-spent))
                status["stage"]=stage
                timing=first.fixed_timing(base.cfg,blocks,trial);doc=timing.schedule(trial)
                polished=refine(timing,trial,records,doc,best)
                accepted=False
                if polished is not None:
                    new=observed(timing.schedule(polished))
                    if compact_key(new)<compact_key(best):
                        for key in ("secondary","cmax","equipment_release","vtr_held_wait","atr_held_wait"):
                            assert new[key]<=best[key]+1e-6,key
                        for ch,entry in best["chambers"].items():
                            assert all(new["chambers"][ch][key]<=entry[key] for key in ("internal_empty","occupied_wait","longest_empty"))
                        accepted=True;ref=polished;best=new
                w["history"].append(dict(stage=stage,solver=solverstatus,accepted=accepted,summary=best))
                w.update(next=k+1,starts=ref,best=best);atom(save,w);status["completed"]=k+1
                print(stage,accepted,best["chambers"],flush=True)
                if "--pause-after-first" in sys.argv and k==0:return
            if compact_key(best)>=compact_key(before["after"]):
                atom(OUT/"no_improvement.json",dict(signature=signature,history=w["history"]))
                status.update(completed=total,stage="No improvement; parent selected");return
            final=base.schedule(ref)
            assert observed(final)==best and final["config"]==source["config"] and final["pairs"]==source["pairs"]
            atom(OUT/"result.json",final)
            status.update(stage="full original-model row verification",audit_start=time.monotonic())
            cert=first.prior.audit_result(OUT,first.old.fingerprint(signature),final)
            assert cert["status"]=="all_original_rows_satisfied" and cert["result_sha256"]==digest(OUT/"result.json")
            atom(endpoint,dict(signature=signature,source=rel(SOURCE),before=before["before"],intermediate=before["after"],
                after=best,original_rows_valid=True,native_rows=cert["original_rows"],physical_validation=final["validation"],
                schedule_sha256=cert["result_sha256"],certificate_path=rel(OUT/"original_row_audit/certificate.json"),
                scope="Validated local reordering and timing of the same 39 production cycles and 13 cleanings."))
            status.update(completed=total,stage="independently verified")
        except BaseException:
            status["failed"]=1
            raise
        finally:
            quit_signal.set();thread.join();report()

if __name__=="__main__":
    run()


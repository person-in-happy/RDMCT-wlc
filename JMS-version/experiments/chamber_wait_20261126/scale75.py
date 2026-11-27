"""Improve the published 75-wafer schedule with local resource-order search and retiming."""
import argparse
from collections import Counter, defaultdict
import json
import os
from pathlib import Path
import sys
import threading
import time

import numpy as np
from ortools.sat.python import cp_model
from scipy.optimize import linprog
from scipy.sparse import coo_matrix

HERE = Path(__file__).resolve().parent
JMS = HERE.parents[1]
sys.path.insert(0, str(HERE.parent / "square_grid_20261125"))
from gap75 import source_timing, read, atom, digest, metrics, rel

OUT = JMS / "results/chamber_wait_20261126/n75"
SOURCE = JMS / "results/gantt_huber_comparison_20261125/n75/result.json"
# Windows cover the extreme within-recipe waits, supply gaps, and final cleaning.
WINDOWS = [(3800, 4630), (5400, 6100), (4500, 5350), (0, 410),
           (3100, 4000), (480, 1290), (1320, 2100), (2070, 2900)]
SECONDS = 5


def pairs(timing):
    for block, base in timing.blocks:
        for j, members in enumerate(block.members):
            count = sum(w.startswith("LP") for w in members)
            if count:
                load = base + block.handling[j, "pair_load"]
                unload = base + block.handling[j, "pair_unload"]
                work = timing.cfg.full_time if block.mode == "4x1" else 2*timing.cfg.mix_time
                yield block.mode, count, load, unload, int(timing.actions[load].duration + work)


def chamber_gaps(timing):
    previous = {}
    held, empty = defaultdict(list), defaultdict(list)
    for block, base in timing.blocks:
        ch = str(block.chamber)
        group = [base+i for i in block.chamber_ops]
        if ch in previous:
            a = previous[ch]
            empty[ch].append((a, group[0], timing.actions[a].duration))
        held[ch].extend((a, b, timing.actions[a].duration) for a,b in zip(group,group[1:]))
        previous[ch] = group[-1]
    return held, empty


def robot_gaps(records,starts,doc):
    from patterns import travel
    from model import Config
    cfg=Config(**doc["config"])
    members=defaultdict(list)
    for w in doc["jobs"]:
        members[w["pair"]].append(w["name"])
    by_robot=defaultdict(list)
    for i,row in enumerate(records):
        if row.get("robot"):
            by_robot[row["robot"]].append(i)
    parts = {}
    for robot,ids in by_robot.items():
        held=set()
        last=None
        gaps=[]
        for i in sorted(ids,key=lambda a:starts[a]):
            row=records[i]
            if held and last is not None:
                prev=records[last]
                lag=prev["end"]-prev["start"]+travel(cfg,robot,prev["location"],row["location"],row["kind"])
                gaps.append((last,i,lag))
            names=members[row["pair"]] if "pair" in row else [row["job"]]
            if row["kind"] in ("origin_pick","lower_pick","al_pick","source_pick","pair_unload"):
                held.update(names)
            else:
                held.difference_update(names)
            last=i
        assert not held
        parts[robot]=gaps
    return parts


def observed(doc):
    from current_defaults_swimlane import build
    _,bars,_,_=build(doc)
    score=metrics(doc)
    score.update(equipment_release=max(b["end"] for b in bars),chambers={})
    for ch in doc["config"]["chambers"]:
        rows=sorted((b for b in bars if b["lane"]==f"旋转腔 CH{ch}"), key=lambda v:v["start"])
        gaps=[b["start"]-a["end"] for a,b in zip(rows,rows[1:]) if b["start"]>a["end"]]
        score["chambers"][str(ch)]={"occupied_wait":sum(b["end"]-b["start"] for b in rows if b["action"]=="腔内等待"),
                                   "internal_empty":sum(gaps),"longest_empty":max(gaps,default=0),
                                   "first":rows[0]["start"],"last":rows[-1]["end"]}
    for robot in ("ATR","VTR"):
        score[robot.lower()+"_held_wait"]=sum(b["end"]-b["start"] for b in bars if b["lane"]==robot+"机械手" and b["action"]=="承片等待")
    return score


def numeric(intervals,starts):
    return sum(starts[b]-starts[a]-dt for a,b,dt in intervals)


def polish(timing, ref, records, doc, limits):
    """Optimize idle intervals without changing any product's residence or resource order."""
    n=len(ref)
    row_index=[]; column=[]; values=[]; rhs=[]
    def row(coefs,ub):
        for i,val in coefs:
            row_index.append(len(rhs));column.append(i);values.append(val)
        rhs.append(ub)
    for a,b,dt in timing.edges:row([(a,1),(b,-1)],-dt)
    for _,_,a,b,_ in pairs(timing):
        span=ref[b]-ref[a]
        row([(a,-1),(b,1)],span);row([(a,1),(b,-1)],-span)
    bounds=[(0,limits["equipment_release"]-t) for t in timing.tails]
    for a in timing.returns:bounds[a]=(0,min(bounds[a][1],doc["cmax"]-timing.actions[a].duration))
    c=np.zeros(n)
    holds,empties=chamber_gaps(timing)
    baseline=observed(doc)
    groups=[]
    for ch in holds:
        for label,parts,weight in (("occupied_wait",holds[ch],15),("internal_empty",empties[ch],12)):
            assert abs(numeric(parts,ref)-baseline["chambers"][ch][label]) < 1e-5
            groups.append((parts,limits["chambers"][ch][label],weight))
    for robot,parts in robot_gaps(records,ref,doc).items():
        key=robot.lower()+"_held_wait"
        assert abs(numeric(parts,ref)-baseline[key])<1e-5
        groups.append((parts,limits[key],1))
    for parts,upper,weight in groups:
        co=Counter();constant=0
        for a,b,dt in parts:co[b]+=1;co[a]-=1;constant+=dt
        row(co.items(),upper+constant)
        for i,v in co.items():c[i]+=weight*v
    a=coo_matrix((values,(row_index,column)),shape=(len(rhs),n)).tocsr()
    res=linprog(c,A_ub=a,b_ub=rhs,bounds=bounds,method="highs-ds")
    if not res.success:return None
    if np.max(abs(res.x-np.rint(res.x)))>1e-6:
        # LP can select a fractional vertex of an otherwise integer-feasible face.
        res=linprog(c,A_ub=a,b_ub=rhs,bounds=bounds,integrality=np.ones(n),method="highs",options={"time_limit":4})
        if res.x is None or np.max(abs(res.x-np.rint(res.x)))>1e-5:return None
    return np.rint(res.x).astype(int).tolist()


def search(timing, engine, ref, window, best, budget):
    model=cp_model.CpModel()
    times=[]
    lo,hi=window
    for i,value in enumerate(ref):
        lower=max(0,value-110)
        upper=min(int(best["equipment_release"]-timing.tails[i]),value+110)
        if value < lo-190 or value > hi+190:lower=upper=value
        v=model.new_int_var(lower,upper,f"t{i}")
        model.add_hint(v,value);times.append(v)
    engine.add_order(model,times,ref,(lo,hi,88))
    for a in timing.returns:model.add(times[a]+int(timing.actions[a].duration)<=round(best["cmax"]))
    holds,empties=chamber_gaps(timing)
    wait_expr=[]
    for ch in holds:
        for key,spans in (("occupied_wait",holds[ch]),("internal_empty",empties[ch])):
            expr=sum(times[b]-times[a]-int(dt) for a,b,dt in spans)
            model.add(expr <= round(best["chambers"][ch][key]))
            wait_expr.append(expr)
    groups=defaultdict(list);weighted=[]
    for mode,count,a,b,dt in pairs(timing):
        r=model.new_int_var(0,int(timing.cfg.module_residency),"")
        model.add(r==times[b]-times[a]-dt)
        model.add_hint(r,ref[b]-ref[a]-dt)
        groups[mode].append(r);weighted.append(count*r)
    extrema=[]
    for by_mode in groups.values():
        low=model.new_int_var(0,100,"");high=model.new_int_var(0,100,"")
        model.add_min_equality(low,by_mode);model.add_max_equality(high,by_mode)
        extrema.append(high-low)
    spread=model.new_int_var(0,100,"range")
    sq=model.new_int_var(0,10000,"range_squared")
    model.add_max_equality(spread,extrema);model.add_multiplication_equality(sq,[spread,spread])
    score=2*sum(weighted)+75*sq
    model.add(score<=round(best["secondary"]*150))
    model.minimize(16*score+sum(wait_expr))
    solver=cp_model.CpSolver()
    solver.parameters.num_search_workers=4;solver.parameters.random_seed=1
    solver.parameters.max_time_in_seconds=max(.05,budget)
    status=solver.solve(model)
    if status in (cp_model.INFEASIBLE,cp_model.MODEL_INVALID):raise ValueError(solver.status_name(status))
    if status in (cp_model.OPTIMAL,cp_model.FEASIBLE):
        return [solver.value(x) for x in times],solver.status_name(status)
    return ref.copy(),solver.status_name(status)


def rank(score):
    waits=sum(ch["occupied_wait"] for ch in score["chambers"].values())
    empty=sum(ch["internal_empty"] for ch in score["chambers"].values())
    return (score["secondary"],score["cmax"],waits+empty,waits,score["equipment_release"],score["vtr_held_wait"],score["atr_held_wait"])


def run(out,stop):
    from contextlib import ExitStack
    from threading import Event
    import msvcrt
    out.mkdir(parents=True,exist_ok=True)
    with ExitStack() as stack:
        lock=stack.enter_context((out/"run.lock").open("a+b"))
        try:msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
        except OSError:print("This case already has an active foreground worker.",flush=True);return
        if (out/"evidence.json").exists():
            e=read(out/"evidence.json");assert e["schedule_sha256"]==digest(out/"result.json") and e["signature"]["worker"]==digest(Path(__file__)) and e["signature"]["source"]==digest(SOURCE)
            print("Verified completed 75-wafer endpoint, remaining 0 s.",flush=True);return
        progress_path=out/"status.json";save=out/"checkpoint.json"
        work=read(save) if save.exists() else {"next":0,"history":[]}
        signature={"source":digest(SOURCE),"worker":digest(Path(__file__)),"per_window_seconds":SECONDS,"workers":4,"windows":WINDOWS}
        signature=json.loads(json.dumps(signature))
        if work.get("signature",signature)!=signature:raise ValueError("Saved endpoint belongs to another protocol")
        work["signature"]=signature
        old_status=read(progress_path) if progress_path.exists() else {}
        total=len(WINDOWS)+2
        start=time.monotonic();carry=old_status.get("elapsed_s",0)
        state={"stage":"restoring original schedule","failed":0,"completed":work["next"],"total":total,"estimate_basis":"One serial 5 s CP-SAT per window with 4 threads, 2 s retiming, and a historical 110 s streaming row audit."}
        closing=Event()
        def report():
            elapsed=carry+time.monotonic()-start
            left=max(0,total-1-state["completed"])*7+max(5,110-(time.monotonic()-state.get("audit_start",time.monotonic())))
            if state["completed"]==total:left=0
            state.update(elapsed_s=round(elapsed,2),remaining_s=round(left,1),estimated_total_s=round(elapsed+left,1))
            atom(progress_path,dict(state))
            print(f'{state["completed"]}/{total}, failed {state["failed"]} | {state["stage"]} | elapsed {elapsed:.1f}s, total ~{elapsed+left:.0f}s, remaining ~{left:.0f}s',flush=True)
        report()
        def heartbeat():
            while not closing.wait(8):report()
        watcher=threading.Thread(target=heartbeat,daemon=True);watcher.start()
        try:
            base,initial,records,proof,source=source_timing()
            from scale import first
            blocks=[b for b,_ in base.blocks]
            ref=work.get("starts",initial);original=observed(source)
            engine=first.ChamberIdle(base.cfg,blocks)
            best=work.get("best",original)
            for k in range(work["next"],len(WINDOWS)+1):
                state["stage"]=f'local order search {WINDOWS[k-1]}' if k else "fixed-order chamber and robot retiming"
                t0=time.monotonic();trial=ref;status="fixed timing"
                if k:
                    left=max(.05,SECONDS-work.get("spent",{}).get(str(k),0))
                    work.setdefault("spent",{})[str(k)]=SECONDS
                    atom(save,work)
                    trial,status=search(base,engine,ref,WINDOWS[k-1],best,left)
                timing=first.fixed_timing(base.cfg,blocks,trial)
                candidate=timing.schedule(trial)
                polished=polish(timing,trial,records,candidate,best)
                accepted=False
                if polished is not None:
                    candidate=timing.schedule(polished)
                    measured=observed(candidate)
                    if rank(measured)<rank(best):
                        if measured["cmax"]>best["cmax"] or measured["equipment_release"]>best["equipment_release"] or any(measured[robot+"_held_wait"]>best[robot+"_held_wait"] for robot in ("atr","vtr")):raise ValueError("A protected time increased")
                        ref,best=polished,measured;accepted=True
                work["history"].append(dict(stage=state["stage"],status=status,accepted=accepted,elapsed_s=time.monotonic()-t0,metrics=best))
                work.update(next=k+1,starts=ref,best=best)
                atom(save,work);state["completed"]=k+1
                print(f'Accepted={accepted}, score={best["secondary"]:.3f}, CH waits={best["chambers"]}',flush=True)
                if stop==k+1:print("Stopped at validated stage checkpoint.",flush=True);return
            timing=first.fixed_timing(base.cfg,blocks,ref)
            data=timing.schedule(ref);actual=observed(data)
            assert actual==best and rank(actual)<rank(original)
            for col in ("config","pairs"):
                assert data[col]==source[col],col
            atom(out/"result.json",data);state.update(stage="full original-model row audit",audit_start=time.monotonic())
            cert=first.prior.audit_result(out,first.old.fingerprint(signature),data)
            assert cert["status"]=="all_original_rows_satisfied" and cert["result_sha256"]==digest(out/"result.json")
            atom(out/"evidence.json",dict(signature=signature,source=rel(SOURCE),before=original,after=actual,
                 physical_validation=data["validation"],original_rows_valid=True,native_rows=cert["original_rows"],
                 schedule_sha256=digest(out/"result.json"),certificate_path=rel(out/"original_row_audit/certificate.json"),
                 scope="Localized robot and resource order changes; feasible schedule, no global optimality assertion.",
                 checkpoints=rel(save)))
            state.update(completed=total,stage="validated endpoint")
        except BaseException:
            state["failed"]=1
            raise
        finally:
            closing.set();watcher.join();report()


if __name__=="__main__":
    parser=argparse.ArgumentParser(__doc__)
    parser.add_argument("--out",type=Path,default=OUT)
    parser.add_argument("--stop-after",type=int)
    args=parser.parse_args()
    run(args.out,args.stop_after)


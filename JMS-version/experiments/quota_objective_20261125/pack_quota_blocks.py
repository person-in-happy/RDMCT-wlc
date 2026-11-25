"""Repack rigid chamber exposure chains using one CP-SAT worker and native MILP replay."""
from collections import defaultdict
from copy import deepcopy
from itertools import combinations
from pathlib import Path
import os
import statistics
import sys
import time

from ortools.sat.python import cp_model
from witnesses import Config, cell, metrics, normalize_schedule, read, save, sha, sparse_witness, validate
from grippers import HANDS, attach_hands

BASE=Path(__file__).resolve().parents[2]/"results/quota_objective_20261125"
OUT=BASE/"parallel_block_reuse"


def pack(source,dest,seconds,flexible=False):
    origin=read(source/"primary.json")
    for k,h in origin["files"].items():assert sha(source/k)==h
    data=read(source/"schedule.json")
    cfg=Config(**data["config"])
    target=origin["metrics"]["secondary"]
    ck=dest/"primary.json"
    if ck.exists():
        old=read(ck)
        if old["source_sha256"]==origin["files"]["schedule.json"] and all(sha(dest/k)==h for k,h in old["files"].items()):
            return old
    dest.mkdir(parents=True,exist_ok=True)
    model=cp_model.CpModel()
    clock=time.monotonic()
    by_pair={}
    by_cycle={}
    last_at={}
    n=0
    for c in sorted(data["cycles"],key=lambda c:(c["chamber"],c["index"])):
        chamber=c["chamber"]
        previous=last_at.get(chamber,set())
        shared=previous.intersection(c["pairs"])
        if shared:
            t=by_pair[next(iter(shared))]
        else:t=n;n+=1
        last_at[chamber]=set(c["pairs"])
        for p in c["pairs"]:by_pair[p]=t
        by_cycle[chamber,c["index"]]=t
    jobs={j["name"]:j for j in data["jobs"]}
    entry=dict(by_pair);exit_leg=dict(by_pair)
    if flexible:
        for p in sorted(by_pair):
            entry[p]=n;exit_leg[p]=n+1;n+=2
    inbound={"origin_pick","al_put","al_pick","upper_put","source_pick"}
    atomic={}
    if flexible=="atomic":
        n=max(by_pair.values())+1
        for e in data["events"]:
            if "job" in e:
                key=(jobs[e["job"]]["pair"],e["kind"])
                if key not in atomic:atomic[key]=n;n+=1
    def route(p,kind):return atomic.get((p,kind),(entry if kind in inbound else exit_leg)[p])
    def event_block(e):
        if "pair" in e:return by_pair[e["pair"]]
        if "job" in e:return route(jobs[e["job"]]["pair"],e["kind"])
        return by_cycle[e["chamber"],e["cycle"]]
    def N(x):
        if abs(x-round(x))>.00001:raise ValueError("Expected whole-second incumbent")
        return round(x)
    horizon=N(cfg.horizon)
    periods={i:[] for i in range(n)}
    for e in data["events"]:periods[event_block(e)].append((N(e["start"]),N(e["end"])))
    shifts=[model.new_int_var(-min(t[0] for t in periods[i]),horizon-max(t[1] for t in periods[i]),f"shift_{i}") for i in range(n)]
    for var in shifts:model.add_hint(var,0)
    # Original source witnesses carry consecutive exposures for every two-step pair.
    for ch in cfg.chambers:
        groups=[]
        for c in sorted((x for x in data["cycles"] if x["chamber"]==ch),key=lambda x:x["index"]):
            k=by_cycle[ch,c["index"]]
            if not groups or groups[-1]!=k:groups.append(k)
        operations=defaultdict(list)
        for e in data["events"]:
            if e["location"]==f"CH{ch}":operations[event_block(e)].append(e)
        for a,b in zip(groups,groups[1:]):
            model.add(shifts[b]+min(N(e["start"]) for e in operations[b])>=shifts[a]+max(N(e["end"]) for e in operations[a]))
    def travel(a,b):
        x,y=a["location"],b["location"]
        if x==y or {x,y}<={"U","L"}:return 0
        if a["robot"]=="ATR" and x in ("L","U") and (y.startswith("LP") or y=="AS") and b["kind"]=="origin_pick":
            return N(cfg.atr_empty_ll_to_lp)
        return N(cfg.atr_travel if a["robot"]=="ATR" else cfg.vtr_travel)
    forbid=defaultdict(list)
    for robot in ("ATR","VTR"):
        for a,b in combinations((e for e in data["events"] if e["robot"]==robot),2):
            i,j=event_block(a),event_block(b)
            if i==j:continue
            if i>j:i,j=j,i;a,b=b,a
            lo=N(a["start"])-N(b["end"])-travel(b,a)+1
            hi=N(a["end"])-N(b["start"])+travel(a,b)-1
            if lo<=hi:forbid[i,j].append((lo,hi))
    for (i,j),bad in forbid.items():
        domain=cp_model.Domain.from_intervals(bad).complement()
        model.add_linear_expression_in_domain(shifts[j]-shifts[i],domain)
    event={(e.get("job"),e["kind"]):e for e in data["events"] if "job" in e}
    resource=defaultdict(list)
    hands=defaultdict(list)
    for j in jobs.values():
        v=shifts[by_pair[j["pair"]]]
        def off(kind):return shifts[route(j["pair"],kind)]
        vin=off("source_pick");vout=off("destination_put")
        name=j["name"]
        def at(kind,key):return N(event[name,kind][key])
        def slot(resource_key,first,last,tail=0):
            a=at(first,"start");b=at(last,"end")+tail
            s,e=off(first),off(last)
            if s.index==e.index:
                interval=model.new_fixed_size_interval_var(s+a,b-a,"")
            else:
                size=model.new_int_var(1,N(cfg.robot_residency) if resource_key=="ATR" else horizon,"")
                model.add_hint(size,b-a)
                interval=model.new_interval_var(s+a,size,e+b,"")
            resource[resource_key].append(interval)
        if flexible:
            model.add(v+N(j["load_start"])>=vin+at("source_pick","end")+N(cfg.vtr_travel))
            model.add(vout+at("destination_put","start")>=v+N(j["unload_end"])+N(cfg.vtr_travel))
        for leg,a,b in (("in",at("source_pick","start"),N(j["load_end"])),("out",N(j["unload_start"]),at("destination_put","end"))):
            allowed=HANDS[:2] if j["product"] and leg=="in" else HANDS[2:] if j["product"] else HANDS
            a0,b0=(vin,v) if leg=="in" else (v,vout)
            duration=b-a
            if flexible:
                duration=model.new_int_var(1,N(cfg.robot_residency),"")
                model.add(duration==b0+b-(a0+a))
                model.add_hint(duration,b-a)
            take=[]
            for h in allowed:
                z=model.new_bool_var("")
                model.add_hint(z,int(j["vtr_hand_"+leg]==h))
                hands[h].append(model.new_optional_interval_var(a0+a,duration,b0+b,z,""))
                take.append(z)
            model.add_exactly_one(take)
        if not j["product"]:
            assert j["origin"]=="VS"
            a,b=N(j["loan_start"]),N(j["loan_end"])
            if flexible:
                duration=model.new_int_var(1,horizon,"")
                model.add_hint(duration,b-a)
                resource["dummy"].append(model.new_interval_var(vin+a,duration,vout+b,""))
            else:slot("dummy","source_pick","destination_put")
        else:
            slot("AL","al_put","al_pick")
            slot("U","upper_put","source_pick",N(cfg.upper_reset))
            slot("L","destination_put","lower_pick",N(cfg.lower_reset))
            slot("ATR","origin_pick","al_put")
            slot("ATR","al_pick","upper_put")
            slot("ATR","lower_pick","origin_put")
            if atomic:
                for first,last,duration,limited in (("origin_pick","al_put",cfg.atr_travel,False),
                        ("al_put","al_pick",cfg.alignment,True),("al_pick","upper_put",cfg.atr_travel,False),
                        ("upper_put","source_pick",cfg.pump,True),("destination_put","lower_pick",cfg.vent,True),
                        ("lower_pick","origin_put",cfg.atr_travel,False)):
                    slack=off(last)+at(last,"start")-off(first)-at(first,"end")
                    model.add(slack>=N(duration))
                    if limited:model.add(slack<=N(cfg.module_residency))
    for h,seq in hands.items():model.add_no_overlap(seq)
    for key,seq in resource.items():
        cap={"AL":1,"U":2,"L":2,"ATR":2,"dummy":cfg.dummy_count}[key]
        model.add_cumulative(seq,[1]*len(seq),cap)
    for group in cfg.pjobs:
        product=sorted((j for j in jobs.values() if j.get("pjob")==group["id"]),key=lambda j:j["pjob_index"])
        for a,b in zip(product,product[1:]):
            model.add(shifts[route(a["pair"],"origin_pick")]+N(a["loan_start"])<=shifts[route(b["pair"],"origin_pick")]+N(b["loan_start"]))
    makespan=model.new_int_var(0,N(data["cmax"]),"cmax")
    model.add_max_equality(makespan,[shifts[route(j["pair"],"origin_put")]+N(j["loan_end"]) for j in jobs.values() if j["product"]])
    model.add_hint(makespan,N(data["cmax"]))
    model.minimize(makespan)
    solver=cp_model.CpSolver()
    solver.parameters.num_search_workers=1
    solver.parameters.random_seed=1
    # The incumbent is a vector of original-event translations; the all-zero
    # vector is the verified source. Store each improvement independently of the
    # CP search tree and charge elapsed time if a process dies in this stage.
    checkpoint=dest/"cp_checkpoint.json"
    key=dict(source=origin["files"]["schedule.json"],flexible=flexible,solver_budget_s=seconds)
    saved=read(checkpoint) if checkpoint.exists() else dict(key=key,spent=0.,offsets=[0]*n,cmax=N(data["cmax"]))
    if saved["key"]!=key:raise ValueError("Interrupted neighborhood has different inputs")
    if "started_epoch" in saved:
        saved["spent"]=min(seconds,saved["spent"]+max(0.,time.time()-saved.pop("started_epoch")))
    remaining=max(0.,seconds-saved["spent"])
    class Candidate(cp_model.CpSolverSolutionCallback):
        def on_solution_callback(self):
            cost=self.value(makespan)
            if cost<saved["cmax"]:
                saved.update(cmax=cost,offsets=[self.value(v) for v in shifts])
                save(checkpoint,saved)
    offsets=saved["offsets"]
    status="recovered_budget"
    conditional_lower=None
    run_seconds=0.
    if remaining>.01:
        solver.parameters.max_time_in_seconds=remaining
        saved["started_epoch"]=time.time()
        save(checkpoint,saved)
        state=solver.solve(model,Candidate())
        if state in (cp_model.INFEASIBLE,cp_model.MODEL_INVALID):raise ValueError(solver.status_name(state))
        status=solver.status_name(state)
        run_seconds=solver.wall_time
        conditional_lower=solver.best_objective_bound
        saved.pop("started_epoch")
        saved["spent"]=min(seconds,saved["spent"]+run_seconds)
        offsets=saved["offsets"]
        save(checkpoint,saved)
    out=deepcopy(data)
    for e in out["events"]:
        d=offsets[event_block(e)]
        for k in ("start","end"):e[k]=N(e[k])+d
    for c in out["cycles"]:
        d=offsets[by_cycle[c["chamber"],c["index"]]]
        for k in ("start","end"):c[k]=N(c[k])+d
    for j in out["jobs"]:
        d=offsets[by_pair[j["pair"]]]
        for k in ("load_start","load_end","unload_start","unload_end"):j[k]=N(j[k])+d
        j["loan_start"]=N(j["loan_start"])+offsets[route(j["pair"],"origin_pick" if j["product"] else "source_pick")]
        j["loan_end"]=N(j["loan_end"])+offsets[route(j["pair"],"origin_put" if j["product"] else "destination_put")]
    pairs={p["id"]:p for p in out["pairs"]}
    available=[0]*cfg.dummy_count
    # Relabel fungible dummy loans in a fresh sweep; query the original member index
    # from the original pair to avoid collisions during the renaming.
    orig_pairs={p["id"]:p for p in data["pairs"]}
    for j in sorted((x for x in out["jobs"] if not x["product"]),key=lambda j:(j["loan_start"],j["name"])):
        idx=min(range(len(available)),key=available.__getitem__)
        assert available[idx]<=j["loan_start"]
        available[idx]=j["loan_end"]
        pos=orig_pairs[j["pair"]]["members"].index(j["identity"])
        pairs[j["pair"]]["members"][pos]=j["identity"]=f"D{idx+1}"
    assert attach_hands(out)
    out["cmax"]=saved["cmax"]
    out=normalize_schedule(cfg,out)
    checks=validate(out)
    if not checks["valid"]:raise ValueError(checks["errors"][:12])
    result=cell.lift(cfg,sparse_witness(cfg,out),None,rebuild=True)
    if not result:raise ValueError("Full MILP replay failed")
    sched,vals,_,checks,rows=result
    measured=metrics(sched)
    assert checks["valid"] and abs(measured["secondary"]-target)<1e-5
    save(dest/"schedule.json",sched);save(dest/"assignment.json.gz",vals)
    proof=dict(metrics=measured,lower=target,original_rows=rows,replay=checks,scope="integer translations of chamber chains with fixed chamber sequence and intra-chain timing; dummy identities and hands reallocated",independent_pair_transport=flexible,
               source_sha256=origin["files"]["schedule.json"],source_assignment_sha256=origin["files"]["assignment.json.gz"],
               solver_status=status,conditional_lower_C=conditional_lower,cumulative_solver_s=saved["spent"],
               source_C=data["cmax"],offsets=offsets,wall_s=time.monotonic()-clock,solver_s=run_seconds,
               files={k:sha(dest/k) for k in ("schedule.json","assignment.json.gz")})
    save(ck,proof)
    return proof


if __name__=="__main__":
    import msvcrt
    OUT.mkdir(parents=True,exist_ok=True)
    with (OUT/"controller.lock").open("a+b") as lock:
        lock.seek(0);msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
        names=["D_n4_H3_mixed_dual","D_n4_H10_mixed_dual","D_n8_H3_mixed_dual","D_n8_H10_mixed_dual"]
        elapsed=[];failed=[]
        for i,name in enumerate(names):
            est=statistics.median(elapsed) if elapsed else 40
            eta=(len(names)-i)*est
            print(f"Verified {i-len(failed)}/{len(names)}; failed {len(failed)}; elapsed {sum(elapsed):.1f}s; estimated total {sum(elapsed)+eta:.1f}s; remaining {eta:.1f}s; one CPU",flush=True)
            t=time.monotonic()
            try:print(name,pack(BASE/"shortest_fixed_order"/name,OUT/name,24)["metrics"],flush=True)
            except Exception as exc:
                import traceback
                traceback.print_exc()
                failed.append(name)
            elapsed.append(time.monotonic()-t)
            eta=(len(names)-i-1)*statistics.median(elapsed)
            save(OUT/"progress.json",dict(complete=i+1-len(failed),total=len(names),failed=failed,elapsed=sum(elapsed),eta_s=eta,
                 estimated_total_s=sum(elapsed)+eta,concurrency=1,basis="matched completed median, initially 40 seconds per case",
                 recovery="skip SHA-replayed endpoints; interrupted CP translation neighborhood restarts from its checked source; each completed solve is a standalone comparison of witnesses"))

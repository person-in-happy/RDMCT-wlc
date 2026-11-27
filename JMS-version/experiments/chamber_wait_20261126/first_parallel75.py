"""Target the first two parallel-recipe exposures on each chamber in the 75-wafer case."""
import argparse
from collections import defaultdict
import json
import msvcrt
from pathlib import Path
import sys
import threading
import time

from ortools.sat.python import cp_model
from scale75 import JMS, source_timing, pairs, observed, read, atom, digest, rel, chamber_gaps

PARENT = JMS / "results/chamber_wait_20261126/n75_balanced"
OUT = JMS / "results/chamber_wait_20261126/n75_first_parallel"
# lo, hi, movable order band, allowed first-cycle delay, solver seconds.
STAGES = [
    (3200, 4875, 0, 0, 3),
    (3050, 4820, 160, 0, 9),
    (3400, 4680, 300, 0, 12),
    (3100, 4850, 440, 0, 15),
    (2650, 4900, 550, 0, 18),
    (3000, 4850, 320, 45, 12),
    (2850, 4900, 420, 100, 15),
    (3050, 4900, 440, 330, 15),
    (2800, 5000, 600, 330, 18),
]


def transition_indices(timing):
    groups=defaultdict(list)
    for block, offset in timing.blocks:
        if block.mode == "4x1":
            exp, _, _ = block.cycles[0]
            groups[block.chamber].append((offset+exp, offset+block.chamber_ops[0], offset+block.chamber_ops[-1]))
    return {str(ch):(blocks[0][0],blocks[1][0],blocks[0][2],blocks[1][1]) for ch,blocks in groups.items()}


def transition_info(timing, t):
    result={}
    for ch,(a,b,off,on) in transition_indices(timing).items():
        end=t[a]+int(timing.actions[a].duration)
        out=t[off]+int(timing.actions[off].duration)
        result[ch]=dict(first_start=t[a], first_end=end, second_start=t[b], gap=t[b]-end,
                        empty_begin=out, empty_end=t[on], empty=t[on]-out)
    return result


def key(timing, starts, base):
    now=transition_info(timing,starts)
    gains=[base[ch]["gap"]-now[ch]["gap"] for ch in now]
    supply=[base[ch]["second_start"]-now[ch]["second_start"] for ch in now]
    return (min(gains),sum(gains),min(supply),sum(supply),-sum(z["empty"] for z in now.values()))


def solve(timing,engine,ref,baseline,limits,stage,budget):
    lo,hi,band,delay,_=stage
    m=cp_model.CpModel()
    t=[]
    for i,start in enumerate(ref):
        lower=0; upper=int(limits["equipment_release"]-timing.tails[i])
        if band!=0 and (start<lo-400 or start>hi+400):
            lower=upper=start
        if lower==upper:
            t.append(m.new_constant(lower))
        else:
            t.append(m.new_int_var(lower,upper,""))
            m.add_hint(t[-1],int(start))
    if band:
        engine.add_order(m,t,ref,(lo,hi,band))
    else:
        from scale import first
        fixed=first.fixed_timing(timing.cfg,[b for b,_ in timing.blocks],ref)
        for a,b,dt in fixed.edges:m.add(t[b]>=t[a]+int(dt))
    for i in timing.returns:m.add(t[i]+int(timing.actions[i].duration)<=limits["cmax"])
    grouped=defaultdict(list);total=[]
    for mode,count,a,b,dt in pairs(timing):
        x=m.new_int_var(0,100,"")
        m.add(x==t[b]-t[a]-dt);m.add_hint(x,int(ref[b]-ref[a]-dt))
        total.append(count*x);grouped[mode].append(x)
    ranges=[]
    for values in grouped.values():
        low=m.new_int_var(0,100,"");high=m.new_int_var(0,100,"")
        m.add_min_equality(low,values);m.add_max_equality(high,values);ranges.append(high-low)
    spread=m.new_int_var(0,100,"");sq=m.new_int_var(0,10000,"")
    m.add_max_equality(spread,ranges);m.add_multiplication_equality(sq,[spread,spread])
    process_score=2*sum(total)+75*sq
    m.add(process_score<=round(limits["secondary"]*150))
    gains=[];advances=[];empties=[]
    for ch,(a,b,off,on) in transition_indices(timing).items():
        original=baseline[ch];d=int(timing.actions[a].duration)
        gap=t[b]-t[a]-d;empty=t[on]-t[off]-int(timing.actions[off].duration)
        m.add(gap<=original["gap"]);m.add(empty<=original["empty"])
        m.add(t[a]<=original["first_start"]+delay);m.add(t[b]<=original["second_start"])
        g=m.new_int_var(0,original["gap"],"");m.add(g==original["gap"]-gap);gains.append(g)
        advances.append(original["second_start"]-t[b]);empties.append(empty)
    minimum=m.new_int_var(0,400,"");m.add_min_equality(minimum,gains)
    # Prefer gains visible in both intervals; also prefer earlier arrivals of the second batches.
    m.maximize(10000*minimum+160*sum(gains)+36*sum(advances)-14*sum(empties))
    solver=cp_model.CpSolver();solver.parameters.max_time_in_seconds=budget;solver.parameters.num_search_workers=6
    solver.parameters.random_seed=42
    result=solver.solve(m)
    if result not in (cp_model.FEASIBLE,cp_model.OPTIMAL):return ref,solver.status_name(result)
    return [solver.value(v) for v in t],solver.status_name(result)


def run(pause_after):
    OUT.mkdir(exist_ok=True)
    with (OUT/"run.lock").open("a+b") as lock:
        try:msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
        except OSError:print("Another foreground worker owns this case.");return
        signature=dict(worker=digest(Path(__file__)), parent=digest(PARENT/"result.json"),stages=STAGES)
        signature=json.loads(json.dumps(signature))
        if (OUT/"evidence.json").is_file():
            proof=read(OUT/"evidence.json")
            assert proof["signature"]==signature and proof["schedule_sha256"]==digest(OUT/"result.json")
            print("Validated endpoint reused; remaining 0s.");return
        base,_,records,_,original=source_timing()
        from scale import first
        blocks=[b for b,_ in base.blocks];engine=first.ChamberIdle(base.cfg,blocks)
        seed=read(PARENT/"checkpoint.json")["starts"];parent=read(PARENT/"result.json")
        limits=observed(parent);baseline=transition_info(base,seed)
        checkpoint=OUT/"checkpoint.json";statusfile=OUT/"status.json"
        s=read(checkpoint) if checkpoint.is_file() else dict(next=0,starts=seed,best_anchored=seed,history=[],signature=signature)
        assert s["signature"]==signature and base.schedule(seed)["events"]==parent["events"]
        previous=read(statusfile) if statusfile.exists() else {}; start=time.monotonic();spent0=previous.get("elapsed_s",0)
        state=dict(completed=s["next"],total=len(STAGES)+1,failed=0,stage="restore");quit=threading.Event()
        def report():
            elapsed=spent0+time.monotonic()-start;k=state["completed"]
            left=sum(x[-1]+1 for x in STAGES[k:])+max(2,24-(time.monotonic()-state.get("audit_at",time.monotonic()))) if k<state["total"] else 0
            info=dict(state,elapsed_s=round(elapsed,1),remaining_s=round(left,1),estimated_total_s=round(elapsed+left,1),basis="Serial bounded CP-SAT stages, 6 threads; prior streamed 24M-row audit about 24s.")
            atom(statusfile,info);print(f"{k}/{info['total']} {state['stage']} | failed {info['failed']} elapsed {elapsed:.1f}s remaining ~{left:.0f}s",flush=True)
        def beat():
            while not quit.wait(8):report()
        thread=threading.Thread(target=beat,daemon=True);thread.start();report()
        try:
            for index in range(s["next"],len(STAGES)):
                stage=STAGES[index];state["stage"]=str(stage);cap=stage[3]
                incumbent=s["best_anchored"] if cap==0 else s["starts"]
                spent=s.setdefault("spent",{}).get(str(index),0);s["spent"][str(index)]=stage[-1];atom(checkpoint,s)
                trial,status=solve(base,engine,incumbent,baseline,limits,stage,max(.08,stage[-1]-spent))
                score=observed(base.schedule(trial));info=transition_info(base,trial)
                assert score["secondary"]<=limits["secondary"]+1e-6
                good=key(base,trial,baseline)>key(base,incumbent,baseline)
                if good and cap==0:s["best_anchored"]=trial
                if good:s["starts"]=trial
                s["history"].append(dict(stage=stage,status=status,accepted=good,intervals=info,metrics=score))
                s["next"]=index+1;atom(checkpoint,s);state["completed"]=index+1;report();print(info,flush=True)
                if pause_after==index+1:return
            state["stage"]="full original model audit";state["audit_at"]=time.monotonic()
            candidates={"unrestricted_first":s["starts"],"first_not_delayed":s["best_anchored"]}
            for name,cand in candidates.items():
                doc=base.schedule(cand);intervals=transition_info(base,cand)
                atom(OUT/(name+".json"),dict(intervals=intervals,metrics=observed(doc)))
            # The anchored candidate is the publication default. Preserve alternatives independently.
            preferred=s["best_anchored"] if key(base,s["best_anchored"],baseline)[0]>0 else s["starts"]
            final=base.schedule(preferred);assert final["validation"]["valid"]
            atom(OUT/"result.json",final)
            cert=first.prior.audit_result(OUT,first.old.fingerprint(signature),final)
            assert cert["status"]=="all_original_rows_satisfied" and cert["result_sha256"]==digest(OUT/"result.json")
            atom(OUT/"evidence.json",dict(signature=signature,source=rel(PARENT/"result.json"),before=limits,after=observed(final),
                 intervals_before=baseline,intervals_after=transition_info(base,preferred),physical_validation=final["validation"],
                 certificate_path=rel(OUT/"original_row_audit/certificate.json"),native_rows=cert["original_rows"],
                 original_rows_valid=True,schedule_sha256=cert["result_sha256"],scope="Local robotic and resource order and timings; fixed pairing, chamber job order and source allocations."))
            state.update(completed=len(STAGES)+1,stage="all rows verified")
        except BaseException:
            state["failed"]=1;raise
        finally:
            quit.set();thread.join();report()


if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("--pause-after",type=int)
    run(parser.parse_args().pause_after)


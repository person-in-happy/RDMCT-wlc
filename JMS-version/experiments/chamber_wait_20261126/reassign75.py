"""Test exact first-to-second 4x1 gaps after reassigning the first six groups."""
from pathlib import Path
from dataclasses import replace
from copy import copy
import json
import time
import msvcrt
import threading
import sys
from contextlib import ExitStack
from ortools.sat.python import cp_model
from scale75 import JMS, source_timing, observed, read, digest, atom, rel, pairs

SOURCE = JMS / "results/chamber_wait_20261126/n75_balanced/result.json"
OUT = JMS / "results/chamber_wait_20261126/n75_firstpair_reassign"
GROUPS = (17,19,20,21,22,23)
CASES = [
    ((3,2,3,2,3,2),0,38),((3,3,2,2,3,2),0,38),
    ((3,2,2,3,3,2),0,38),((3,3,2,3,2,2),0,38),
    ((3,2,3,2,3,2),85,90),((3,3,2,2,3,2),85,90),
    ((3,2,2,3,3,2),85,90),((3,3,2,3,2,2),85,90),
]
SEC=8

def gap_data(doc):
    v=[]
    for ch in (2,3):
        a,b=[c for c in doc["cycles"] if c["chamber"]==ch and c["mode"]=="4x1"][:2]
        v.append([a["start"],a["end"],b["start"],b["start"]-a["end"]])
    return v

def try_case(base, original_times, assignment, delay, band, seconds):
    from scale import first
    from gap75 import np
    base_blocks=[b for b,_ in base.blocks]
    blocks=list(base_blocks); hint=original_times.copy()
    source_seq={ch:[i for i in GROUPS if base_blocks[i].chamber==ch] for ch in (2,3)}
    idx={2:0,3:0}
    for n,ch in zip(GROUPS,assignment):
        original=base_blocks[n]; donor=source_seq[ch][idx[ch]];idx[ch]+=1
        block=copy(original);block.chamber=ch
        block.actions=[replace(a,location=f"CH{ch}") if a.location.startswith("CH") else a for a in original.actions]
        blocks[n]=block
        offset=base.blocks[n][1];other=base.blocks[donor][1]
        # The chamber-side actions keep their previous time slot on that chamber.
        # Upstream cassette/aligner/lock actions keep the order of available supply.
        for j,a in enumerate(block.actions):
            if a.kind not in ("origin_pick","al_put","al_pick","upper_put","source_pick"):
                hint[offset+j]=original_times[other+j]
    e=first.ChamberIdle(base.cfg,blocks)
    m=cp_model.CpModel()
    times=[]
    for i,t in enumerate(hint):
        minv,maxv=(0,6533-int(e.tails[i]))
        if t < 3080 or t>5840: minv=maxv=t
        else:minv,maxv=max(minv,t-430),min(maxv,t+430)
        v=m.new_int_var(minv,maxv,f"x{i}");m.add_hint(v,t);times.append(v)
    e.add_order(m,times,hint,(3090,5780,band))
    for i in e.returns:m.add(times[i]+int(e.actions[i].duration)<=6050)
    groups={}
    for ch in (2,3):
        ids=[base.blocks[n][1]+blocks[n].cycles[0][0] for n in GROUPS if blocks[n].chamber==ch]
        groups[ch]=ids[:2]
    # Explicitly cap earliest returns and both target gaps; preserve physical endpoints.
    gaps=[]
    for ch,(oldfirst,oldsecond,gap) in zip((2,3),[(4200,4693,313),(3907,4344,257)]):
        a,b=groups[ch]
        m.add(times[a]<=oldfirst+delay);m.add(times[b]<=oldsecond-1)
        g=m.new_int_var(0,gap-1,f"gap{ch}");m.add(g==times[b]-times[a]-180);gaps.append(g)
    rgroup={}; weighted=[]
    for b,offset in zip(blocks,[o for _,o in base.blocks]):
        for j,ws in enumerate(b.members):
            count=sum(w.startswith("LP") for w in ws)
            if not count:continue
            a=offset+b.handling[j,"pair_load"];z=offset+b.handling[j,"pair_unload"]
            work=base.cfg.full_time if b.mode=="4x1" else 2*base.cfg.mix_time
            r=m.new_int_var(0,100,"");m.add(r==times[z]-times[a]-int(b.actions[b.handling[j,"pair_load"]].duration+work))
            rgroup.setdefault(b.mode,[]).append(r);weighted.append(count*r)
    ranges=[]
    for v in rgroup.values():
        l=m.new_int_var(0,100,"");h=m.new_int_var(0,100,"")
        m.add_min_equality(l,v);m.add_max_equality(h,v);ranges.append(h-l)
    width=m.new_int_var(0,53,"");m.add_max_equality(width,ranges)
    square=m.new_int_var(0,2809,"");m.add_multiplication_equality(square,[width,width])
    m.add(2*sum(weighted)+75*square<=212603)
    m.minimize(sum(gaps)*100+sum(times[groups[ch][1]] for ch in (2,3)))
    s=cp_model.CpSolver();s.parameters.num_search_workers=2;s.parameters.max_time_in_seconds=max(.02,seconds);s.parameters.random_seed=4
    st=s.solve(m);status=s.status_name(st)
    if st not in (cp_model.FEASIBLE,cp_model.OPTIMAL):return status,None
    x=[s.value(v) for v in times]
    timing=first.fixed_timing(base.cfg,blocks,x);schedule=timing.schedule(x)
    assert schedule['validation']['valid']
    return status,schedule

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    with ExitStack() as stack:
        lock=stack.enter_context((OUT/'run.lock').open('a+b'))
        try:msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
        except OSError:print('Existing worker is active.',flush=True);return
        tag=dict(source=digest(SOURCE),worker=digest(Path(__file__)),cases=json.loads(json.dumps(CASES)),case_seconds=SEC)
        cp=OUT/'checkpoint.json';state=read(cp) if cp.exists() else dict(tag=tag,done=0,spent={},results=[])
        assert state['tag']==tag
        if (OUT/'completed.json').exists():print('Completed endpoints reused.',flush=True);return
        original=read(SOURCE);base,_,records,_,_=source_timing()
        ev,cy=iter(original['events']),iter(original['cycles'])
        times=[(next(cy) if a.kind=='exposure' else next(ev))['start'] for a in base.actions]
        start=time.monotonic();prior=read(OUT/'status.json').get('elapsed_s',0) if (OUT/'status.json').exists() else 0
        active='initializing';failed=0
        def monitor():
            elapsed=prior+time.monotonic()-start; eta=max(0,(len(CASES)-state['done'])*(SEC+3)+5)
            atom(OUT/'status.json',dict(stage=active,completed=state['done'],total=len(CASES),failed=failed,elapsed_s=elapsed,estimated_total_s=elapsed+eta,remaining_s=eta,basis='serial 8 s CP budgets, two workers, plus model construction'))
            print(f"{state['done']}/{len(CASES)} {active}, failed {failed}, elapsed {elapsed:.0f}, total ~{elapsed+eta:.0f}, remaining ~{eta:.0f} s",flush=True)
        e=threading.Event()
        def heartbeat():
            while not e.wait(10):monitor()
        th=threading.Thread(target=heartbeat,daemon=True);th.start()
        try:
            for i in range(state['done'],len(CASES)):
                active=f'case {i+1}';monitor()
                # On interruption recover at case granularity and debit its reserved window.
                left=SEC-state['spent'].get(str(i),0);state['spent'][str(i)]=SEC;atom(cp,state)
                ch,delay,band=CASES[i];status,doc=try_case(base,times,ch,delay,band,left)
                row=dict(case=i,chambers=ch,first_start_delay=delay,order_band=band,status=status)
                if doc:
                    row.update(gaps=gap_data(doc),metrics=observed(doc));atom(OUT/f'case_{i}.json',doc)
                state['results'].append(row);state['done']=i+1;atom(cp,state)
                if '--pause-after-first' in sys.argv:return
            successes=[x for x in state['results'] if 'gaps' in x]
            if successes:
                from scale import first
                best=min(successes,key=lambda x:(sum(v[3] for v in x['gaps']),sum(v[2] for v in x['gaps'])))
                doc=read(OUT/f"case_{best['case']}.json");atom(OUT/'result.json',doc)
                active='full original-model verification';monitor()
                cert=first.prior.audit_result(OUT,first.old.fingerprint(tag),doc)
                assert cert['status']=='all_original_rows_satisfied'
                atom(OUT/'evidence.json',dict(before=gap_data(original),after=best,selection=tag,certificate=cert))
            active='finished';atom(OUT/'completed.json',dict(tested=len(CASES),accepted=len(successes),source=rel(SOURCE)))
        except BaseException:
            failed=1;raise
        finally:
            e.set();th.join();monitor()
if __name__=='__main__':main()

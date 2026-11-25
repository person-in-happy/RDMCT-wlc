"""Exhaust all admissible chamber-batch patterns for a cap, retaining per-pattern proof status."""
from collections import Counter
from itertools import groupby
from pathlib import Path
import sys
import time
import msvcrt
import threading
from common16 import HERE,JMS,OUT,load,save,sha
sys.path.insert(0,str(HERE.parent/"table3_grid16_20261125"))
from ordered_projection import patterns
from port_projection import add_ports,cp_model

def values_to_source(raw,groups):
    labels={}
    for port in range(4):
        indices=sorted([i for i in range(16) if raw[f"port_{i}"]==port],key=lambda i:(raw[f"origin_pick_{i}"],i))
        assert len(indices)==4
        for j,i in enumerate(indices):labels[i]=4*port+j
    out={}
    for i,n in labels.items():
        g=groups[raw[f"batch_{i}"]];c,q=divmod(g,10)
        side=raw[f"front_{i}"]
        out[f"w{n}_{c}_{q}_{side}"]=1
        out[f"use{c,q}"]=1;out[f"start{c,q}"]=raw[f"start_{g}"]
        for old,new in [("origin_pick","origin_pick"),("al","al_put"),("ap","al_pick"),("up","upper_put"),("sp","source_pick"),("ld","load"),("ul","unload"),
                ("dp","destination_put"),("lp","lower_pick"),("origin_put","origin_put")]:
            out[f"{n}_{new}"]=raw[f"{old}_{i}"]
    return out

def main(cap,allowance):
    root=OUT/"4x1";dest=root/"pattern_port"/str(cap)
    dest.mkdir(parents=True,exist_ok=True)
    lock=(dest/"controller.lock").open("a+b");lock.seek(0)
    try:msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
    except OSError:return
    params=load(JMS/"results/table3_grid16_20261125/batch_bound_pure_4x1.json")
    rows=patterns(16,0,cap,params["ready"])
    groups=sorted({g for seq in rows for g,_ in seq})
    reference,objective=add_ports("4x1",cap)
    reference.clear_objective()
    name_to_idx={k.name:i for i,k in enumerate(reference.proto.variables) if k.name}
    signature=dict(cap=cap,seed=1,worker=sha(Path(__file__)),base=sha(HERE.parent/"table3_grid16_20261125/port_projection.py"),
        ordered=sha(HERE.parent/"table3_grid16_20261125/ordered_projection.py"),recipe="4x1")
    started=time.monotonic();results=[]
    for index,(entry,modes) in enumerate(sorted(rows.items())):
        item=dest/f"pattern_{index:03d}.json"
        state=load(item) if item.exists() else dict(identity=signature,used=0,status="pending",pattern=entry)
        assert state["identity"]==signature
        if state["status"] in ("INFEASIBLE","OPTIMAL","FEASIBLE") or state["used"]>=allowance:
            results.append(state);continue
        model=reference.clone()
        v={k:model.get_int_var_from_proto_index(i) for k,i in name_to_idx.items()}
        order=[g for g,_ in groupby([g for g,k in entry])]
        qty=Counter(g for g,k in entry)
        for i,(g,k) in enumerate(entry):
            model.add(v[f"batch_{i}"]==groups.index(g))
            model.add(v[f"kind_{g}"]==1)
        used=0;lower={};back={}
        for g in order:
            n=qty[g]
            t=max(params["ready"][used+n-1],max(lower.values(),default=0),lower.get(g-1,-1000)+188)
            lower[g]=t
            model.add(v[f"start_{g}"]>=t)
            back[g]=cap-220-55*((15-used)//2)
            used+=n
        late=cap
        for g in reversed(order):
            late=min(late,back[g],back.get(g+1,2*cap)-188)
            back[g]=late
            model.add(v[f"start_{g}"]<=late)
        solver=cp_model.CpSolver();solver.parameters.num_workers=1;solver.parameters.random_seed=1
        spent=state["used"];solver.parameters.max_time_in_seconds=max(0,allowance-spent)
        since=time.monotonic();stop=threading.Event()
        def pulse():
            state["used"]=min(allowance,spent+time.monotonic()-since+1)
            save(item,state)
        def monitor():
            while not stop.wait(1):pulse()
        pulse();th=threading.Thread(target=monitor,daemon=True);th.start()
        status=solver.solve(model)
        stop.set();th.join()
        state.update(status=solver.status_name(status),used=spent+solver.wall_time)
        if status in (cp_model.OPTIMAL,cp_model.FEASIBLE):
            raw={k:solver.value(x) for k,x in v.items()}
            source=dest/f"source_{index:03d}_{raw['true_C']}.json"
            save(source,values_to_source(raw,groups))
            state.update(upper=raw["true_C"],projection=source.relative_to(JMS).as_posix(),sha256=sha(source))
        save(item,state);results.append(state)
        elapsed=time.monotonic()-started
        print(f"cap {cap} | patterns {len(results)}/{len(rows)} | {state['status']} | elapsed {elapsed:.0f}s | estimated budget ETA {(len(rows)-len(results))*allowance:.0f}s",flush=True)
        save(dest/"progress.json",dict(completed=len(results),expected=len(rows),processed_pattern=index,elapsed_s=elapsed,
            estimated_total_s=elapsed+(len(rows)-len(results))*allowance,estimated_remaining_s=(len(rows)-len(results))*allowance,failed=0))
    counts=Counter(row["status"] for row in results)
    summary=dict(identity=signature,allowance=allowance,patterns=len(rows),statuses=counts,independent_proof=counts["INFEASIBLE"]==len(rows))
    result=dest/f"summary_{allowance}.json";save(result,summary)
    if summary["independent_proof"]:
        event=root/"external_bounds"/f"pattern_{cap}.json"
        if not event.exists():save(event,dict(lower=cap+1,received=time.time(),proof=result.relative_to(JMS).as_posix(),sha256=sha(result)))

if __name__=="__main__":main(int(sys.argv[1]),int(sys.argv[2]))

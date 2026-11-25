"""Check the two first 4x1-to-4x1 gaps against the original fixed resource orders."""
from pathlib import Path
import sys
import time
from unittest.mock import patch
import msvcrt

from gantt75 import OUT, JMS, MOD, metrics, read, digest, atom, rel, np, coo_matrix, linprog


def source_timing():
    sys.path.insert(0,str(MOD.parent/"manuscript_projection_20261120"))
    from scale import OUT as original_dir, first, old, original
    source=original.RUN.parent/old.read(original.RUN/"run_manifest.json")["source_case"]
    with patch.object(first,"BASE",source): cfg,blocks,_=first.restore_seed()
    source=read(original_dir/"result.json")
    def times(schedule):
        events=iter(schedule["events"]);cycles=iter(schedule["cycles"])
        return [((next(cycles) if a.kind=="exposure" else next(events))["start"]) for b in blocks for a in b.actions]
    timing=first.fixed_timing(cfg,blocks,times(source))
    previous=read(OUT/"gantt75/square.json")
    witness=read(JMS/previous["schedule"])
    starts=times(witness)
    assert all(timing.schedule(starts)[k]==witness[k] for k in ("events","cycles","jobs","pairs","cmax"))
    records=[];events=iter(witness["events"]);cycles=iter(witness["cycles"])
    for a in timing.actions:records.append(next(cycles) if a.kind=="exposure" else next(events))
    return timing,starts,records,previous,witness


def inspect_gap(data,ch):
    cycles=[c for c in data["cycles"] if c["chamber"]==ch and c["mode"]=="4x1"][:2]
    first,second=cycles
    assert second["index"]==first["index"]+1
    a,b=first["end"],second["start"]
    chamber_events=sorted((v for v in data["events"] if v["location"]==f"CH{ch}" and a<=v["start"]<b),key=lambda v:v["start"])
    robots=[v for v in data["events"] if v["robot"]=="VTR" and a<=v["start"]<b]
    times={k:sum(v["end"]-v["start"] for v in chamber_events if v["kind"]==k) for k in ("rotate","pair_load","pair_unload")}
    load=chamber_events[-1]
    pair=next(v for v in data["pairs"] if v["id"]==load["pair"])
    last_pick=max((v for v in robots if v["kind"]=="source_pick" and any(j["pair"]==pair["id"] and j["name"]==v["job"] for j in data["jobs"])),key=lambda v:v["end"])
    upper=next(v for v in data["events"] if v["kind"]=="upper_put" and v["job"]==last_pick["job"])
    assert upper["end"]+data["config"]["pump"]<=last_pick["start"] and last_pick["end"]+data["config"]["vtr_travel"]<=load["start"] and load["end"]<=b
    return dict(first=first,second=second,gap=b-a,cycle_actions=chamber_events,local_action_time=times,
                locally_unassigned=b-a-sum(times.values()),shared_VTR_action_time=sum(v["end"]-v["start"] for v in robots),
                last_supplied_wafer=last_pick["job"],upper_load_end=upper["end"],pump_complete=upper["end"]+data["config"]["pump"],
                last_vtr_pick=[last_pick["start"],last_pick["end"]],last_vtr_load=[load["start"],load["end"]])


def program(timing,starts,records,proof,witness,kind):
    n=len(starts);c=n+4;size=c+1
    bounds=[(0,6536-tail) for tail in timing.tails]+[(0,100)]*4+[(0,6053)]
    rows=[];cols=[];coef=[];rhs=[]
    def row(terms,limit):
        for j,x in terms:rows.append(len(rhs));cols.append(j);coef.append(x)
        rhs.append(limit)
    for a,b,lag in sorted(timing.edges):row(((a,1),(b,-1)),-lag)
    for i in timing.returns:row(((i,1),(c,-1)),-timing.actions[i].duration)
    mean=np.zeros(size);constant=0
    for blk,base in timing.blocks:
        if blk.mode=="clean":continue
        lo=n+2*int(blk.mode=="2x2");hi=lo+1
        for j,members in enumerate(blk.members):
            weight=sum(p.startswith("LP") for p in members)
            if not weight:continue
            l=base+blk.handling[j,"pair_load"];u=base+blk.handling[j,"pair_unload"]
            off=timing.actions[l].duration+(timing.cfg.full_time if blk.mode=="4x1" else 2*timing.cfg.mix_time)
            row(((lo,1),(u,-1),(l,1)),-off)
            row(((hi,-1),(u,1),(l,-1)),off)
            mean[l]-=weight;mean[u]+=weight;constant-=weight*off
    # The tangent proof establishes equality: every optimum has D=64 and mean=13.
    if not kind.endswith("_physical"):
        for lo in (n,n+2):row(((lo,-1),(lo+1,1)),64.)
        row(enumerate(mean),75*13-constant)
    first={};second={};loss=np.zeros(size)
    for ch in (2,3):
        v=[i for i,a in enumerate(records) if a.get("mode")=="4x1" and a["chamber"]==ch]
        first[ch],second[ch]=v[:2]
    if kind.startswith("gap_alone"):
        ch=int(kind.split("_")[-1]);loss[first[ch]]=-1;loss[second[ch]]=1
    elif kind.startswith("next"):
        for ch in (2,3):
            i=first[ch];bounds[i]=(starts[i],starts[i])
            i=second[ch];bounds[i]=(0,starts[i])
        targets=(2,3) if "joint" in kind else (int(kind.split("_")[1]),)
        for ch in targets:loss[second[ch]]=1
    elif kind.startswith("cmax"):loss[c]=1
    else:raise ValueError(kind)
    A=coo_matrix((coef,(rows,cols)),shape=(len(rhs),size)).tocsr()
    solution=linprog(loss,A_ub=A,b_ub=rhs,bounds=bounds,method="highs-ds")
    assert solution.success,solution.message
    vector=solution.x[:n]
    result=dict(status=solution.message,objective=solution.fun,
                cycles={str(ch):[solution.x[first[ch]],solution.x[second[ch]]] for ch in (2,3)},
                cmax=max(vector[i]+timing.actions[i].duration for i in timing.returns),
                rows=len(rhs),variables=size,largest_fraction=float(np.max(np.abs(vector-np.rint(vector)))))
    if kind=="next_joint" and solution.fun<sum(starts[i] for i in second.values())-1e-5:
        # Left-justify using existing slack only where a time change is needed.
        from scipy.sparse import hstack,eye,vstack
        for i in second.values():bounds[i]=(float(solution.x[i]),)*2
        P=eye(n,size,format="csr");N=-eye(n,format="csr")
        A2=vstack((hstack((A,coo_matrix((len(rhs),n)))),hstack((P,N)),hstack((-P,N))))
        near=linprog(np.r_[np.zeros(size),np.ones(n)],A_ub=A2,b_ub=np.r_[rhs,starts,-np.asarray(starts)],
                     bounds=bounds+[(0,None)]*n,method="highs-ds")
        assert near.success
        vector=near.x[:n]
        assert np.max(np.abs(vector-np.rint(vector)))<1e-5
        candidate=timing.schedule([int(round(v)) for v in vector]);candidate["validation"]=candidate.get("validation",{})
        assert candidate["validation"]["valid"] and metrics(candidate)==metrics(witness)
        return result,candidate
    return result,None


def run(stop_after=None):
    out=OUT/"gantt75_gap";out.mkdir(exist_ok=True)
    with (out/"run.lock").open("a+b") as lock:
        try:msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
        except OSError:print("Another active process owns this experiment.",flush=True);return
        signature={rel(p):digest(p) for p in (Path(__file__),OUT/"gantt75/square.json",MOD/"score.py")}
        progress_file=out/"progress.json";begin=time.monotonic()
        time_before=read(progress_file)["elapsed_s"] if progress_file.exists() else 0
        timing,starts,records,proof,witness=source_timing()
        work=("cmax_physical","cmax_optimal","next_2_physical","next_3_physical","next_2","next_3","next_joint","gap_alone_2","gap_alone_3")
        def progress(done,message):
            elapsed=time_before+time.monotonic()-begin;remaining=(len(work)-done)*.35
            atom(progress_file,dict(completed=done,total=len(work),failed=0,current=message,remaining_s=remaining,
                                    estimated_total_s=elapsed+remaining,elapsed_s=elapsed,basis="one thread, observed fixed-time LP cost"))
            print(f"{done}/{len(work)} {message}; elapsed {elapsed:.1f}s, total ~{elapsed+remaining:.1f}s, remaining ~{remaining:.1f}s",flush=True)
        atom(out/"original_events.json",{str(ch):inspect_gap(witness,ch) for ch in (2,3)})
        for index,key in enumerate(work):
            file=out/f"{key}.json"
            progress(index,key)
            if file.exists():assert read(file)["signature"]==signature
            else:
                result,candidate=program(timing,starts,records,proof,witness,key)
                if candidate:
                    atom(out/"result.json",candidate)
                    result.update(candidate="result.json",candidate_sha256=digest(out/"result.json"))
                atom(file,dict(signature=signature,**result))
            if stop_after==index+1:break
        progress(sum((out/f"{k}.json").exists() for k in work),"checked")


if __name__=="__main__":
    import argparse
    parser=argparse.ArgumentParser()
    parser.add_argument("--stop-after",type=int)
    run(parser.parse_args().stop_after)

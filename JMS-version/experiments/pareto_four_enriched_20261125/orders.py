"""Search complete four-wafer product partitions at selected residence levels."""
from itertools import combinations
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import argparse
import math
import time
import msvcrt
from long import OUT,EX,JMS,sweep,fixed,blk,physical_lower

def designs():
    # First and second entering pairs at one chamber, with the residual product(s)
    # in a single two-exposure pair at the other chamber. Every identity is covered.
    result={}
    ids=set(range(4))
    for n1,n2 in ((1,1),(1,2),(2,1),(2,2)):
        for a in combinations(sorted(ids),n1):
            for b in combinations(sorted(ids-set(a)),n2):
                tail=tuple(sorted(ids-set(a)-set(b)))
                tag="_".join("".join(str(i+1) for i in row) for row in (a,b,tail) if row)
                result[tag]=(a,b,tail)
    return result

def trial(cfg,tag,groups,delta,budget,out):
    dest=out/f"{tag}_d{delta:g}";dest.mkdir(exist_ok=True,parents=True)
    record=dest/"result.json"
    signature={str(f.relative_to(JMS)):sweep.sha(f) for f in (Path(__file__),EX/"table4_extended16_20261125/blocks.py")}
    if record.exists():
        assert sweep.read(record)["signature"]==signature
        return
    ds=[f"D{i}" for i in range(1,9)];labels=cfg.pjobs[0]["wafers"]
    a,b,c=groups
    def pair(ids,dummy):return [labels[j] for j in ids]+([dummy] if len(ids)==1 else [])
    seq=[blk.block(cfg,"2x2",2,[ds[:2],pair(a,"D3"),pair(b,"D4"),ds[:2]])]
    if c:seq.append(blk.block(cfg,"2x2",3,[ds[4:6],pair(c,"D2" if len(b)==1 else "D4"),ds[6:8]]))
    scale=8 if delta not in (0,.25,.5,.75) else 4
    def spec(m,vs,pieces,end):
        for p,off in pieces:
            for q,row in enumerate(p.members):
                if not any(w.startswith("LP") for w in row):continue
                ld=vs[off+p.handling[q,"pair_load"]];ul=vs[off+p.handling[q,"pair_unload"]]
                r=7 if q==len(p.members)-2 else 7-delta
                m.add(ul-ld==int((181+r)*scale))
        m.add(end<=500*scale)
    source=dest/"candidate.json"
    def save(t,c):sweep.atomic(source,dict(times=t,C=c))
    begin=time.monotonic()
    try:
        if source.exists():
            v=sweep.read(source)["times"];pieces=[];i=0
            for p in seq:pieces.append((p,i));i+=len(p.actions)
        else:v,pieces=blk.time_blocks(cfg,seq,scale=scale,ideal=False,budget=budget,seed=1,workers=1,progress=save,specialize=spec)
    except RuntimeError as e:
        sweep.atomic(record,dict(signature=signature,status=str(e),seconds=time.monotonic()-begin));return
    def reassign(c,d):
        d=blk.normalize_schedule(c,d)
        assert blk.attach_hands(d)
        return d
    with patch("timing.normalize_schedule",reassign):doc=blk.BatchTiming.schedule(SimpleNamespace(cfg=cfg,blocks=pieces),v)
    native=sweep.cell.lift(cfg,blk.sparse_witness(cfg,doc),None,rebuild=True)
    assert native
    d,assignment,_,rep,n=native
    assert rep["valid"]
    sweep.save(dest/"schedule.json",d);sweep.save(dest/"assignment.json.gz",assignment)
    sweep.atomic(record,dict(signature=signature,groups=groups,delta=delta,metrics=fixed.metrics(d),scope="feasible original model",
        original_rows=n,replay=rep,files={k:sweep.sha(dest/k) for k in ("schedule.json","assignment.json.gz")},seconds=time.monotonic()-begin))

def main(part,budget):
    cfg=sweep.Config(**sweep.read(OUT/"sources/double_only/A404/schedule.json")["config"])
    out=OUT/"partitions";out.mkdir(exist_ok=True)
    with (out/f"{part}.lock").open("a+b") as lock:
        try:msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
        except OSError:return
        combos=designs()
        if part=="screen":
            todo=[(k,v,len(v[0])/4) for k,v in combos.items()]
        else:
            records=[(sweep.read(f),f.parent.name) for f in out.glob("*_d*/result.json")]
            keep={}
            for r,name in records:
                if "metrics" in r and r["delta"] in (.25,.5):
                    typ=len(r["groups"][0])
                    if typ not in keep or r["metrics"]["cmax"]<keep[typ][0]:keep[typ]=(r["metrics"]["cmax"],name.split("_d")[0])
            todo=[(k,combos[k],d) for _,k in keep.values() for d in (0,.125,.25,.375,.5)]
        begin=time.monotonic()
        for i,(k,v,d) in enumerate(todo):
            elapsed=time.monotonic()-begin; rem=(len(todo)-i)*(elapsed/i if i else budget+.3)
            info=dict(completed=i,total=len(todo),failed=0,current=k,elapsed_s=elapsed,remaining_s=rem,estimated_total_s=elapsed+rem,
                      recovery="completed original-model replays and saved feasible timestamps per layout")
            sweep.atomic(out/f"{part}.json",info);print(f"{part} {i}/{len(todo)}; elapsed {elapsed:.1f}s, remaining ~{rem:.1f}s",flush=True)
            trial(cfg,k,v,d,budget,out)
        elapsed=time.monotonic()-begin
        sweep.atomic(out/f"{part}.json",dict(completed=len(todo),total=len(todo),failed=0,elapsed_s=elapsed,remaining_s=0,estimated_total_s=elapsed))

if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("phase",choices=("screen","dense"));p.add_argument("--budget",type=float,default=1.3)
    a=p.parse_args();main(a.phase,a.budget)

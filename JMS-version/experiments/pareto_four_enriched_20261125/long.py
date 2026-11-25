"""Search short and long product pair chains and replay each surviving native 4-wafer witness."""
import argparse
from pathlib import Path
from types import SimpleNamespace
import sys
import time
from unittest.mock import patch
from probe import JMS,R,EX,OUT,sweep,fixed
sys.path.insert(0,str(EX/"table4_extended16_20261125"))
import blocks as blk
from score import physical_lower

def structures(cfg,tag):
    prod=list(cfg.pjobs[0]["wafers"]);ds=[f"D{i}" for i in range(1,9)]
    if tag=="parallel":
        return [blk.block(cfg,"2x2",2,[ds[:2],prod[:2],ds[2:4]]),
                blk.block(cfg,"2x2",3,[ds[4:6],prod[2:],ds[6:]])]
    sizes=tuple(map(int,tag));pairs=[];idx=0;dummy=2
    for s in sizes:
        grp=prod[idx:idx+s];idx+=s
        if s==1:grp=grp+[ds[dummy]];dummy+=1
        pairs.append(grp)
    return [blk.block(cfg,"2x2",2,[ds[:2],*pairs,ds[dummy:dummy+2]])]


def run(tag,cap,ideal,budget):
    source=OUT/"sources/double_only/A404/schedule.json"
    cfg=sweep.Config(**sweep.read(source)["config"])
    lower=physical_lower(cfg)
    search=structures(cfg,tag);scale=4 if ideal else 1
    dest=OUT/"long"/tag/(("floor_" if ideal else "probe_")+str(cap));dest.mkdir(exist_ok=True,parents=True)
    target=dest/"result.json"
    sig={str(p.relative_to(JMS)):sweep.sha(p) for p in (Path(__file__),source,EX/"table4_extended16_20261125/blocks.py",EX/"square_residence_20261125/score.py")}
    if target.exists():
        z=sweep.read(target);assert z["signature"]==sig
        return
    hit=dest/"candidate.json"
    def store(v,C):
        sweep.atomic(hit,dict(times=v,cmax=C))
    def spec(m,v,pieces,end):
        rr=[]
        for p,off in pieces:
            for i,pair in enumerate(p.members):
                w=sum(vv.startswith("LP") for vv in pair)
                if not w:continue
                r=m.new_int_var(6*scale,100*scale,"")
                m.add(r==v[off+p.handling[i,"pair_unload"]]-v[off+p.handling[i,"pair_load"]]-181*scale)
                if ideal:m.add(r == (7*scale if i==len(p.members)-2 else int(6.25*scale)))
                rr.extend([r]*w)
        if not ideal:
            lo=m.new_int_var(0,100,"");hi=m.new_int_var(0,100,"");D=m.new_int_var(0,100,"");sq=m.new_int_var(0,10000,"")
            m.add_min_equality(lo,rr);m.add_max_equality(hi,rr);m.add(D==hi-lo);m.add_multiplication_equality(sq,D,D)
            m.minimize((sum(rr)+2*sq)*(cap+1)+end)
    begin=time.monotonic()
    try:
        if hit.exists():
            times=sweep.read(hit)["times"];pieces=[];k=0
            for p in search:pieces.append((p,k));k+=len(p.actions)
        else:
            times,pieces=blk.time_blocks(cfg,search,scale=scale,ideal=False,seed=1,budget=budget,
                incumbent=cap,progress=store,specialize=spec,workers=1,first=False)
    except RuntimeError as e:
        sweep.atomic(target,dict(signature=sig,scope="restricted route search",message=str(e),cap=cap,elapsed=time.monotonic()-begin));return
    def reassign(c,data):
        doc=blk.normalize_schedule(c,data)
        if not blk.attach_hands(doc):raise ValueError("hand assignment")
        return doc
    with patch("timing.normalize_schedule",reassign):
        doc=blk.BatchTiming.schedule(SimpleNamespace(cfg=cfg,blocks=pieces),times)
    native=sweep.cell.lift(cfg,blk.sparse_witness(cfg,doc),None,rebuild=True)
    assert native
    doc,assign,_,replay,rows=native
    score=fixed.metrics(doc)
    assert replay["valid"] and score["cmax"]<=cap+1e-5
    if ideal and tag[-1]=="1":assert abs(score["secondary"]-lower)<1e-6
    sweep.save(dest/"schedule.json",doc);sweep.save(dest/"assignment.json.gz",assign)
    sweep.atomic(target,dict(signature=sig,cap=cap,metrics=score,global_fB_lower=lower,original_rows=rows,
        replay=replay,files={k:sweep.sha(dest/k) for k in ("schedule.json","assignment.json.gz")},elapsed=time.monotonic()-begin))


if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("batch",choices=("tail","orders"));p.add_argument("--budget",type=float,default=4)
    a=p.parse_args()
    jobs=([(k,c,True) for c in (700,550,535,525) for k in ("211","121")]+[("22",c,True) for c in (480,455)]) if a.batch=="tail" else [
        (k,c,False) for k,c in (("parallel",404),("parallel",408),("parallel",415),("parallel",440),("22",443),("22",460),("211",500),("211",530))]
    begin=time.monotonic()
    for i,(k,c,ideal) in enumerate(jobs):
        rem=(len(jobs)-i)*(a.budget+.6)
        elapsed=time.monotonic()-begin
        info=dict(completed=i,total=len(jobs),failed=0,current=[k,c],elapsed_s=elapsed,estimated_total_s=elapsed+rem,remaining_s=rem,
                  recovery="native endpoint/CP feasible checkpoint per configuration and cap; exploratory wall limit per attempt")
        sweep.atomic(OUT/(a.batch+"_progress.json"),info);print(info,flush=True)
        run(k,c,ideal,a.budget)
    elapsed=time.monotonic()-begin
    sweep.atomic(OUT/(a.batch+"_progress.json"),dict(completed=len(jobs),total=len(jobs),failed=0,elapsed_s=elapsed,remaining_s=0,estimated_total_s=elapsed))
    print(f"{len(jobs)}/{len(jobs)} complete, remaining 0s.",flush=True)

"""Certify squared-spread retiming of the 75-wafer Gantt chart at its original product-return cap."""
from collections import Counter
import os
from pathlib import Path
import sys
import time
from unittest.mock import patch

for name in ("OMP_NUM_THREADS","OPENBLAS_NUM_THREADS","MKL_NUM_THREADS"):
    os.environ[name]="1"
from grid import OUT,JMS,MOD,metrics,read,digest,atom,rel
from scipy.optimize import linprog
from scipy.sparse import coo_matrix
import numpy as np


def main():
    dest=OUT/"gantt75";dest.mkdir(parents=True,exist_ok=True)
    olddir=JMS/"results/gantt_huber_comparison_20261125/n75"
    oldcert=olddir/"original_row_audit/certificate.json"
    previous=olddir/"result.json"
    signature={rel(p):digest(p) for p in (Path(__file__),MOD/"score.py",previous,oldcert)}
    file=dest/"square.json"
    if file.exists():
        record=read(file)
        assert record["signature"]==signature and digest(JMS/record["schedule"])==record["schedule_sha256"]
        print("1/1 certified; remaining 0s.");return
    began=time.monotonic()
    print("0/1; expected 2–12s for fixed-timing supporting LP; 1 CPU.",flush=True)
    atom(dest/"progress.json",dict(completed=0,expected=1,elapsed_s=0,estimated_total_s=12,remaining_s=12,
         basis="previous 1097-event continuous retiming; native source is already certified"))
    sys.path.insert(0,str(MOD.parent/"manuscript_projection_20261120"))
    from scale import OUT as original_folder, old, first, original
    original_file=original_folder/"result.json"
    prior=original.RUN.parent/old.read(original.RUN/"run_manifest.json")["source_case"]
    with patch.object(first,"BASE",prior):
        cfg,blocks,_=first.restore_seed()
    reference=read(original_file);events=iter(reference["events"]);cycles=iter(reference["cycles"])
    initial=[(next(cycles) if a.kind=="exposure" else next(events))["start"] for b in blocks for a in b.actions]
    timing=first.fixed_timing(cfg,blocks,initial)
    assert all(timing.schedule(initial)[k]==reference[k] for k in ("config","jobs","cycles","events","pairs","cmax"))
    witness=read(previous);oldsc=metrics(witness)
    proof=read(oldcert)
    assert proof["result_sha256"]==digest(previous) and proof["status"]=="all_original_rows_satisfied"
    n=len(initial)
    extrema={"4x1":(n,n+1),"2x2":(n+2,n+3)}
    D=n+4;cost=np.zeros(n+5)
    anchor=oldsc["residence_range"];cost[D]=anchor
    constant=oldsc["clean_deficit"]-anchor**2/2
    ii=[];jj=[];aa=[];rhs=[]
    def add(values,ub):
        for col,a in values:ii.append(len(rhs));jj.append(col);aa.append(a)
        rhs.append(ub)
    for a,b,dt in timing.edges:add(((a,1),(b,-1)),-dt)
    for i in timing.returns:add(((i,1),),reference["cmax"]-timing.actions[i].duration)
    counts=Counter()
    for block,base in timing.blocks:
        for j,pair in enumerate(block.members):
            num=sum(w.startswith("LP") for w in pair)
            if not num:continue
            counts[block.mode]+=num
            lo,hi=extrema[block.mode]
            l=base+block.handling[j,"pair_load"];u=base+block.handling[j,"pair_unload"]
            spent=timing.actions[l].duration+(cfg.full_time if block.mode=="4x1" else 2*cfg.mix_time)
            cost[l]-=num/75;cost[u]+=num/75;constant-=num*spent/75
            add(((lo,1),(u,-1),(l,1)),-spent)
            add(((u,1),(l,-1),(hi,-1)),spent)
    assert counts=={"4x1":37,"2x2":38}
    for lo,hi in extrema.values():add(((hi,1),(lo,-1),(D,-1)),0)
    A=coo_matrix((aa,(ii,jj)),shape=(len(rhs),len(cost))).tocsr()
    bounds=[(0,cfg.horizon-t) for t in timing.tails]+[(0,cfg.module_residency)]*5
    o=linprog(cost,A_ub=A,b_ub=rhs,bounds=bounds,method="highs-ds")
    assert o.success
    lower=o.fun+constant
    assert abs(oldsc["secondary"]-lower)<1e-6,(oldsc,lower)
    dur=time.monotonic()-began
    atom(file,dict(signature=signature,metrics=oldsc,original_metrics=metrics(reference),lower=lower,
         scope="fixed event order and product-return cap 6053",
         proof="minimize mean + 64 D - 64^2/2 + E; the quadratic is bounded below by this tangent and the archived schedule attains it",
         tangent=anchor,events=n,rows=len(rhs),schedule=rel(previous),schedule_sha256=digest(previous),
         native_check=rel(oldcert),native_sha256=digest(oldcert),physical_checks=witness["validation"]["checks"]))
    atom(dest/"progress.json",dict(completed=1,expected=1,failed=0,elapsed_s=dur,remaining_s=0,estimated_total_s=dur))
    print(f"1/1; certified fB {oldsc['secondary']:g}, remaining 0s.",flush=True)

if __name__=="__main__":main()

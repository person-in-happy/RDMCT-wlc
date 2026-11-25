"""Lower bounds on the product makespan when the finite-batch secondary score is globally minimal."""
from functools import lru_cache
import hashlib
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
OUT=HERE.parents[1]/"results/quota_objective_20261125/conditional_553"


def enumerate_chamber(h):
    segments=[]
    for n in range(1,5):
        segments.append((n,0,1,6*max(0,n-2),180,"F"))
    for pairs in range(1,5):
        for n in range(pairs,min(4,2*pairs)+1):
            cycles=pairs+1
            if cycles<=h:
                r=6*n+(2 if n==2*pairs else 1)
                segments.append((0,n,cycles,r,cycles*90+(cycles-1)*4,"M"))
    # Record minimal span from first production start to last production end. Each
    # discontinuity of the pair chain requires front unload, rotation, back unload,
    # back load, rotation, front load; this costs at least 8 s on these inputs.
    # Account for the terminal mandated clean in the quota, but not in the product span.
    records={}
    def extend(f,m,prod,actual_cleans,current,r,span,seq):
        key=(f,m,prod,actual_cleans+int(current==h),r)
        if key not in records or span<records[key][0]:
            records[key]=(span,seq)
        for nf,nb,k,cost,dur,tag in segments:
            if f+nf>4 or m+nb>4: continue
            for reset in ((False,True) if current else (False,)):
                after=(0 if reset else current)+k
                if after>h: continue
                wait=(0 if prod==0 else 8)+(508 if reset else 0)
                extend(f+nf,m+nb,prod+k,actual_cleans+int(reset),after,r+cost,
                       span+wait+dur,seq+(("C",) if reset else ())+((tag,nf+nb,k),))
    extend(0,0,0,0,0,0,0,())
    return records


def minimize(h,optimum):
    rows=enumerate_chamber(h)
    pack=[(key,span,seq) for key,(span,seq) in rows.items()]
    best=1e6
    witnesses=[]
    for (f,m,p,k,r),span,seq in pack:
        for (of,om,op,ok,orr),other,oseq in pack:
            if f+of!=4 or m+om!=4: continue
            quota=h*(2+k+ok)-p-op
            if r+orr+8*quota>8*optimum: continue
            # Earliest productive cycle starts >=76; last productive cycle ends
            # <= Cmax-40. Both are local, valid separately for every chamber.
            lb=76+max(span,other)+40
            if lb<best:
                best=lb;witnesses=[]
            if lb==best:
                witnesses.append({"span":[span,other],"sequence":[seq,oseq],"quota":quota,"mean_lb":(r+orr)/8})
    return dict(secondary_optimum=optimum,certified_lower=best,relaxed_structures_attaining_lower=witnesses[:4])


if __name__=="__main__":
    payload={3:minimize(3,5.25),10:minimize(10,11.5)}
    payload["sha256"]=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    OUT.mkdir(parents=True,exist_ok=True)
    (OUT/"optimal_secondary_makespan_lower.json").write_text(json.dumps(payload,indent=2))
    for h in (3,10):
        print(h,payload[h],flush=True)

"""Trace the minimum event times imposed by the 75-wafer witness's resource order."""
from pathlib import Path
import time
from gap75 import OUT,JMS,read,digest,atom,rel,source_timing
from scipy.sparse import coo_matrix
from scipy.optimize import linprog
import numpy as np


def run():
    src=OUT/"gantt75/square.json";folder=OUT/"gantt75_gap";folder.mkdir(exist_ok=True)
    path=folder/"absolute_event_bounds.json"
    identity={rel(p):digest(p) for p in (Path(__file__),Path(__file__).with_name("gap75.py"),src)}
    if path.exists():
        assert read(path)["signature"]==identity
        print("1/1 verified; remaining 0s.");return
    begin=time.monotonic()
    print("0/1; current event-order lower-bound LP, estimated total ~2s and remaining ~2s.",flush=True)
    timing,starts,records,_,original=source_timing()
    # Only resource- and route-precedence inequalities are retained. Setting
    # every event to its earliest feasible time satisfies the same inequalities.
    # This LP needs neither first-cycle or endpoint anchors nor a residence target.
    edges=sorted(timing.edges);n=len(starts)
    rr=[];cc=[];vv=[];rhs=[]
    for i,(a,b,dt) in enumerate(edges):
        rr.extend((i,i));cc.extend((a,b));vv.extend((1,-1));rhs.append(-dt)
    A=coo_matrix((vv,(rr,cc)),shape=(len(rhs),n)).tocsr()
    assert np.max(A@starts-rhs)<1e-8
    assert max(x+tail for x,tail in zip(starts,timing.tails))<=6536
    s=linprog(np.ones(n),A_ub=A,b_ub=rhs,bounds=(0,None),method="highs-ds")
    assert s.success
    result={}
    derived=[]
    for ch,wafer in ((2,"LP3_W1"),(3,"LP2_W2")):
        dest=next(i for i,v in enumerate(records) if v.get("chamber")==ch and v.get("mode")=="4x1" and v["index"]=={2:21,3:17}[ch])
        objective=np.zeros(n);objective[dest]=1
        sol=linprog(objective,A_ub=A,b_ub=rhs,bounds=(0,None),method="highs-ds")
        assert sol.success and abs(sol.fun-starts[dest])<1e-7
        job=next(w for w in original["jobs"] if w["identity"]==wafer)["name"]
        route=[]
        for i,a in sorted(enumerate(records),key=lambda x:x[1]["start"]):
            if a.get("job")==job and a["start"]<starts[dest]:
                route.append(dict(kind=a["kind"],actual=[a["start"],a["end"]],earliest=s.x[i],name=a["name"]))
        dual=[(edges[i],float(v)) for i,v in enumerate(sol.ineqlin.marginals) if abs(v)>1e-8]
        def name(i):
            a=records[i];return a.get("name") or f"CH{a['chamber']}_{a['index']}_{a['mode']}"
        floor=sol.lower.marginals
        dual_value=sum(v*(-dt) for (a,b,dt),v in dual)
        assert abs(dual_value-sol.fun)<1e-7
        result[str(ch)]=dict(upper_lock_last_product=wafer,actual=starts[dest],minimum=sol.fun,last_wafer_route=route,
            dual_lower=dual_value,dual_constraints=[dict(a=name(a),b=name(b),lag=dt,multiplier=v) for (a,b,dt),v in dual])
        derived.append(s.x[dest])
    atom(path,dict(signature=identity,completed=1,failed=0,remaining_s=0,elapsed_s=time.monotonic()-begin,
                   scope="Fixed same-route and same-resource order; nonnegative starts only, no start or finish anchors, residence score or horizon caps.",
                   results=result))
    print(f"1/1; earliest CH2/CH3 = {derived}, remaining 0s.",flush=True)


if __name__=="__main__":run()

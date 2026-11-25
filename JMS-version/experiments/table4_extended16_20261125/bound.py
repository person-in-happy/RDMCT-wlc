"""Enumerate product arrivals, batch occupancy and optional H=3 cleaning on both chambers."""
from pathlib import Path
import json
import hashlib
import time

HERE=Path(__file__).resolve().parent
OUT=HERE.parents[1]/"results"/HERE.name
READY=[max(48+28*(i+1),76+65*(i//2)+(28 if i%2 else 0)) for i in range(16)]


def enumerate_batches(ceiling, collect=False):
    best=ceiling+1
    result=[]
    visited=0
    def visit(f,d,states,clock,returns,trace):
        nonlocal best,visited,result
        visited+=1
        used=16-f-d
        cut=ceiling if collect else best-1
        early=sorted(returns+[max(clock,READY[i])+220 for i in range(used,16)])
        lower=max(t+55*((15-i)//2) for i,t in enumerate(early))
        if lower>cut:return
        if not (f+d):
            if lower<best:best=lower
            if collect:result.append((lower,trace))
            else:result=[(lower,trace)]
            return
        for mode,left,capacity in ((1,f,4),(2,d,2)):
            cycles=mode
            for c,(prev,usedH,last) in enumerate(states):
                if c and states[0]==states[1]:continue
                transitions=[]
                boundary=(188 if prev==1 else 192) if prev else 0
                if prev==mode==2 and usedH<3:
                    transitions.append((94,usedH+1,'carry'))
                if usedH+cycles<=3:transitions.append((boundary,usedH+cycles,'new'))
                if prev:transitions.append((boundary+508,cycles,'clean'))
                for lag,counter,step in transitions:
                    for count in range(min(left,capacity),0,-1):
                        t=max(clock,READY[used+count-1],last+lag)
                        if t+(220 if mode==1 else 226)>cut:continue
                        new=states.copy();new[c]=(mode,counter,t)
                        visit(f-(count if mode==1 else 0),d-(count if mode==2 else 0),
                              new,t,returns+[t+(220 if mode==1 else 226)]*count,
                              trace+[(c,mode,count,step,t)])
    visit(8,8,[(0,0,0),(0,0,0)],0,[],[])
    return dict(lower=best,visited=visited,patterns=result)

if __name__=='__main__':
    import sys
    ceiling=int(sys.argv[1]) if len(sys.argv)>1 else 1400
    start=time.perf_counter();print('Both-chamber clean-aware bound: 0/1; initial estimate 5–60 s.',flush=True)
    out=enumerate_batches(ceiling)
    file=OUT/'H3_clean_bound.json'
    out.update(ceiling=ceiling,ready=READY,elapsed_s=time.perf_counter()-start,
               code_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    file.write_text(json.dumps(out,indent=2))
    print('1/1, 0 failed, remaining 0 s.',out,flush=True)

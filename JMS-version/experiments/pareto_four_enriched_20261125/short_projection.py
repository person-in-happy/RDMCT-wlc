"""Screen the missing global lower support for the short pure-double exchange."""
from itertools import combinations
from concurrent.futures import ThreadPoolExecutor,as_completed
from pathlib import Path
import time
from orders import OUT,JMS,designs,sweep
from ortools.sat.python import cp_model

def check(tag,groups):
    dest=OUT/"short_projection";dest.mkdir(exist_ok=True)
    file=dest/f"{tag}.json";identity=sweep.sha(Path(__file__))
    if file.exists():assert sweep.read(file)["signature"]==identity;return
    m=cp_model.CpModel();sc=2;top=1050
    def t(name):return m.new_int_var(0,top,name)
    def interval(s,e):return m.new_interval_var(s,t(""),e,"")
    stages=("op","al","ap","up","sp","ld","ul","dp","lp","ed")
    r=[{k:t(f"{i}_{k}") for k in stages} for i in range(4)]
    usage={k:[] for k in ("AL","U","L","ATR","vin","vout")}
    robots={"V":[],"A":[]}
    a,b,c=groups
    pairs=[a,b,c];chamber_for=[j for j,pp in enumerate(pairs) for _ in pp]
    group_for={i:j for j,pp in enumerate(pairs) for i in pp}
    for i,w in enumerate(r):
        for k,d in enumerate((7,24,7,34,3,181,3,26,7)):m.add(w[stages[k+1]]>=w[stages[k]]+sc*d)
        for z,s,e,tail in (("AL","al","ap",4),("U","up","sp",31),("L","dp","lp",29),("ATR","op","al",4),("ATR","ap","up",4),("ATR","lp","ed",4),("vin","sp","ld",1),("vout","ul","dp",1)):
            usage[z].append(interval(w[s],w[e]+tail*sc))
        for k,loc in (("op",f"P{i}"),("al","AL"),("ap","AL"),("up","LL"),("lp","LL"),("ed",f"P{i}")):
            robots["A"].append((i,k,loc,w[k],4))
        for k in ("sp","dp"):robots["V"].append((i,k,"LL",w[k],1))
        if i:m.add(r[i-1]["op"]<=w["op"])
    for z,holds in usage.items():m.add_cumulative(holds,[1]*len(holds),1 if z=="AL" else 2)
    def act(ch,label):
        s=t(f"{ch}_{label}");robots["V"].append((-1,label,ch,s,1));return s
    for ch,chain in (("primary",(a,b)),("other",(c,))):
        end=len(chain);init=act(ch,"initial");last=act(ch,"last")
        L=[act(ch,f"L{k}") for k in range(end+1)]
        U=[act(ch,f"U{k}") for k in range(end+1)]
        m.add(L[0]>=init+3*sc)
        for j in range(end):
            m.add(U[j]>=L[j]+93*sc);m.add(L[j+1]>=U[j]+sc)
        m.add(last>=L[-1]+91*sc);m.add(U[-1]>=last+3*sc)
        for j,group in enumerate(chain):
            for w in group:
                m.add(r[w]["ld"]==L[j]);m.add(r[w]["ul"]==U[j+1])
                res=r[w]["ul"]-r[w]["ld"]-181*sc
                m.add(res>=13 if j<end-1 else res>=14)
                m.add(res<=15)
    for robot,ops in robots.items():
        for (i,k,loc,S,slen),(j,l,pos,T,tlen) in combinations(ops,2):
            swap=m.new_bool_var("");conditions=[]
            if i>=0 and j>=0 and group_for[i]==group_for[j] and k==l and k in ("up","sp","dp","lp"):
                same=m.new_bool_var("");m.add(S==T).only_enforce_if(same);conditions.append(~same)
            travel=0 if loc==pos else 3 if robot=="A" else 2
            ab=6 if loc=="LL" and l=="op" else travel
            ba=6 if pos=="LL" and k=="op" else travel
            m.add(T>=S+(slen+ab)*sc).only_enforce_if([swap,*conditions])
            m.add(S>=T+(tlen+ba)*sc).only_enforce_if([~swap,*conditions])
    C=t("C");m.add_max_equality(C,[w["ed"]+4*sc for w in r]);m.add(C<=409*sc)
    i=a[0];res=r[i]["ul"]-r[i]["ld"]-181*sc
    # An upper feasibility threshold avoids seeking an optimum beyond the necessary bound.
    m.minimize(C-res)
    s=cp_model.CpSolver();s.parameters.num_workers=1;s.parameters.max_time_in_seconds=3
    st=s.solve(m)
    rec=dict(status=s.status_name(st),signature=identity,groups=groups,lower=s.best_objective_bound/sc,wall_s=s.wall_time)
    if st in (cp_model.OPTIMAL,cp_model.FEASIBLE):
        rec.update(value=s.objective_value/sc,C=s.value(C)/sc,r=s.value(res)/sc)
    sweep.atomic(file,rec)

def main():
    tasks={k:v for k,v in designs().items() if len(v[0])==1 and len(v[2])>0}
    start=time.monotonic();done=0
    with ThreadPoolExecutor(2) as p:
        fut=[p.submit(check,k,v) for k,v in tasks.items()]
        for f in as_completed(fut):
            f.result();done+=1;elapsed=time.monotonic()-start;rem=(len(tasks)-done)*elapsed/done
            print(f"{done}/{len(tasks)}; elapsed {elapsed:.1f}s, total ~{elapsed+rem:.1f}s, remaining ~{rem:.1f}s",flush=True)
            sweep.atomic(OUT/"short_projection_progress.json",dict(completed=done,total=len(tasks),failed=0,elapsed_s=elapsed,estimated_total_s=elapsed+rem,remaining_s=rem))
if __name__=="__main__":main()

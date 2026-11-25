"""Four-wafer lower bounds when beating 3.5 requires a shared chain of two singleton double pairs."""
import hashlib
import json
import time
from itertools import combinations
from pathlib import Path
from ortools.sat.python import cp_model

HERE = Path(__file__).resolve().parent
OUT = HERE.parents[1]/"results/pareto_scales_20261125/four_bound"
NAMES = ("origin_pick","al_put","al_pick","upper_put","source_pick","load","unload","destination_put","lower_pick","origin_put")
DUR = (4,4,4,4,1,1,1,1,4,4)
HORIZON=470


def projection(which,exact):
    m=cp_model.CpModel()
    sc=4 if exact else 1
    top=HORIZON*sc
    def t(name):return m.new_int_var(0,top,name)
    def sep(a,b,ab,ba,sync=False):
        order=m.new_bool_var("")
        test=[]
        if sync:
            together=m.new_bool_var("")
            m.add(a==b).only_enforce_if(together)
            test.append(~together)
        m.add(b>=a+ab*sc).only_enforce_if([order,*test])
        m.add(a>=b+ba*sc).only_enforce_if([~order,*test])
    def iv(start,end):
        return m.new_interval_var(start,m.new_int_var(0,top,""),end,"")
    routes=[{k:t(f"{i}_{k}") for k in NAMES} for i in range(4)]
    rows={tag:[] for tag in ("AL","U","L","ATR","Vin","Vout")}
    for i,r in enumerate(routes):
        for k,d in enumerate((7,24,7,34,3,181,3,26,7)):
            m.add(r[NAMES[k+1]]>=r[NAMES[k]]+d*sc)
        for name,a,b,d in (("AL",1,2,4),("U",3,4,31),("L",7,8,29),("ATR",0,1,4),("ATR",2,3,4),("ATR",8,9,4),("Vin",4,5,1),("Vout",6,7,1)):
            rows[name].append(iv(r[NAMES[a]],r[NAMES[b]]+d*sc))
    for name,intervals in rows.items():
        m.add_cumulative(intervals,[1]*len(intervals),1 if name=="AL" else 2)
    for i in (0,2):m.add(routes[i]["origin_pick"]<=routes[i+1]["origin_pick"])
    atr=[]; vtr=[]
    for i,r in enumerate(routes):
        for k,loc in ((0,f"P{i}"),(1,"AL"),(2,"AL"),(3,"LL"),(8,"LL"),(9,f"P{i}")):
            atr.append((i,k,loc,r[NAMES[k]],DUR[k]))
        for k in (4,7):vtr.append((i,k,"LL",r[NAMES[k]],1))
    ops={}
    def op(ch,k):
        s=t(f"{ch}_{k}")
        ops[ch,k]=s
        vtr.append((-1,k,ch,s,1))
        return s
    # All double products must have positive residence. Beating 3.5 then forces both
    # single-exposure products into the same front pair, at nearly zero chamber residence.
    fl=op("F","fl");bl=op("F","bl");fu=op("F","fu");bu=op("F","bu")
    m.add(fl>=bl+3*sc);m.add(fu>=fl+181*sc);m.add(bu>=fu+3*sc)
    for i in (0,1):
        m.add(routes[i]["load"]==fl);m.add(routes[i]["unload"]==fu)
        if exact:m.add(fu==fl+181*sc)
    b=op("D","initial_back");last=op("D","final_front")
    L=[op("D",f"fl{q}") for q in range(3)]
    U=[op("D",f"bu{q}") for q in range(3)]
    m.add(L[0]>=b+3*sc)
    for q in (0,1):
        m.add(U[q]>=L[q]+93*sc);m.add(L[q+1]>=U[q]+sc)
    m.add(last>=L[2]+91*sc);m.add(U[2]>=last+3*sc)
    for q,i in enumerate((which,5-which)):
        m.add(routes[i]["load"]==L[q]);m.add(routes[i]["unload"]==U[q+1])
        if exact:
            r4=27 if q==0 else 28
            m.add(U[q+1]-L[q]==181*sc+r4)
    for ops2,robot in ((atr,"A"),(vtr,"V")):
        for (i,k,loc,a,da),(j,l,pos,b,db) in combinations(ops2,2):
            travel=(0 if loc==pos else 3 if robot=="A" else 2)
            lag_ab=6 if loc=="LL" and l==0 else travel
            lag_ba=6 if pos=="LL" and k==0 else travel
            sync=(0<=i<2 and 0<=j<2 and k==l and k in (3,4,7,8))
            sep(a,b,da+lag_ab,db+lag_ba,sync)
    C=t("C")
    m.add_max_equality(C,[r["origin_put"]+4*sc for r in routes]);m.minimize(C)
    return m,sc,routes,ops


def main():
    OUT.mkdir(exist_ok=True,parents=True)
    signature=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    jobs=[(side,exact) for exact in (False,True) for side in (2,3)]
    start=time.monotonic()
    for idx,(which,exact) in enumerate(jobs):
        f=OUT/f"{which}_{int(exact)}.json"
        if f.exists() and json.loads(f.read_bytes())["implementation"]==signature:
            continue
        print(f"four-wafer bound {idx}/4, elapsed={time.monotonic()-start:.1f}s, remaining budget<={(4-idx)*30}s",flush=True)
        m,scale,routes,ops=projection(which,exact)
        solver=cp_model.CpSolver(); solver.parameters.num_workers=2;solver.parameters.max_time_in_seconds=30
        with f.with_suffix(".log").open("w",encoding="utf8") as log:
            solver.parameters.log_search_progress=True;solver.parameters.log_to_stdout=False
            solver.log_callback=lambda line:log.write(line.rstrip()+"\n")
            status=solver.solve(m)
        record=dict(status=solver.status_name(status),lower=solver.best_objective_bound/scale,
                    wall=solver.wall_time,scale=scale,first_dual_product_index=which,exact_global_B_residences=exact,implementation=signature)
        if status in (cp_model.FEASIBLE,cp_model.OPTIMAL):
            record.update(C=solver.objective_value/scale,routes=[{k:solver.value(v)/scale for k,v in r.items()} for r in routes],
                          chamber_ops={str(k):solver.value(v)/scale for k,v in ops.items()})
        tmp=f.with_suffix(".tmp");tmp.write_text(json.dumps(record,indent=2),encoding="utf8");tmp.replace(f)
        print(record["status"],record["lower"],flush=True)


if __name__=="__main__":
    main()

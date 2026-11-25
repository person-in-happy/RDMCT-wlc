"""Eight-wafer makespan lower bound. Keep product routes, omit dummy and terminal clean transfers."""
import argparse
import hashlib
import itertools
import json
from pathlib import Path
import sys
import time

from ortools.sat.python import cp_model


HORIZON = 554
STEPS = ("origin_pick", "al_put", "al_pick", "upper_put", "source_pick", "load",
         "unload", "destination_put", "lower_pick", "origin_put")
DUR = (4, 4, 4, 4, 1, 1, 1, 1, 4, 4)


def model(schedule, cap, fix=False):
    cfg = schedule["config"]
    assert cfg["chambers"] == [2, 3] and len(cfg["pjobs"]) == 2
    assert (cfg["full_time"], cfg["mix_time"], cfg["handling"], cfg["rotation"],
            cfg["atr_handling"], cfg["alignment"], cfg["pump"], cfg["vent"],
            cfg["upper_reset"], cfg["lower_reset"], cfg["atr_travel"],
            cfg["vtr_travel"], cfg["atr_empty_ll_to_lp"]) == (180,90,1,2,4,20,30,25,30,25,3,2,6)
    assert cfg["cleaning_time"] > cap - 76 - 40
    # Every productive cycle includes a real wafer and starts >=76 and ends <=cap-40.
    # Hence a chamber has at most four productive cycles, all before any cleaning.
    assert (cap - 76 - 40) // 90 == 4
    m = cp_model.CpModel()
    def integer(name, low=0, high=HORIZON):
        return m.new_int_var(low,high,name)
    def hint(var, value):
        value = int(round(value))
        m.add_hint(var,value)
        if fix:
            m.add(var == value)
    def interval(start,end,name):
        length=integer("duration_"+name,0,HORIZON+70)
        return m.new_interval_var(start,length,end,name)

    cycles = {(cy["chamber"]-2,cy["index"]):cy for cy in schedule["cycles"] if cy["mode"]!="clean"}
    S, active, types = {}, {}, {}
    for c in range(2):
        for q in range(4):
            key=c,q
            active[key]=m.new_bool_var(f"use{key}")
            types[key]=m.new_bool_var(f"full{key}")
            S[key]=integer(f"start{key}")
            m.add(types[key] <= active[key])
            m.add(S[key]>=76).only_enforce_if(active[key])
            m.add(S[key]+90+90*types[key] <= cap-40).only_enforce_if(active[key])
            m.add(S[key]==0).only_enforce_if(active[key].Not())
            if q:
                prev=c,q-1
                m.add(active[key] <= active[prev])
                m.add(S[key] >= S[prev]+90+90*types[prev]+4).only_enforce_if(active[key])
            cy=cycles.get(key)
            hint(active[key],cy is not None)
            hint(types[key],bool(cy and cy["mode"]=="4x1"))
            hint(S[key],cy["start"] if cy else 0)
    # Each slot corresponds to a physical pair. Full products may occupy either side.
    # Each newly entered 2x2 product must be front in q, then back in q+1.
    slots = {}
    def slot(c,q,side):
        k=(c,q,side)
        slots.setdefault(k,[])
        return slots[k]
    by_name = {(e["job"],e["kind"]):e for e in schedule["events"] if "job" in e}
    wafers = sorted((w for w in schedule["jobs"] if w["product"]),key=lambda w:(w["pjob"],w["pjob_index"]))
    assert len(wafers)==8
    actual_pairs = {p["id"]:p for p in schedule["pairs"]}
    routes, robots, capacities, end_home = [], {"A":[],"V":[]}, {}, []
    for i,w in enumerate(wafers):
        mode=actual_pairs[w["pair"]]["mode"]
        orig=w["origin"]
        route={k:integer(f"{i}_{k}") for k in STEPS}
        for name,t in route.items():
            time_value = w[name+"_start"] if name in ("load","unload") else by_name[w["name"],name]["start"]
            hint(t,time_value)
        ch=integer(f"ch{i}",0,1)
        real_c=actual_pairs[w["pair"]]["chamber"]-2
        hint(ch,real_c)
        real_q=min(q for (c,q),cy in cycles.items() if c==real_c and w["pair"] in cy["pairs"])
        real_side=int(cycles[real_c,real_q]["front"]==w["pair"])
        choices=[]
        for c,q in S:
            for side in (0,1):
                if mode=="2x2" and (q==3 or not side):
                    continue
                choice=m.new_bool_var(f"w{i}_{c}_{q}_{side}")
                choices.append(choice)
                hint(choice,(c,q,side)==(real_c,real_q,real_side))
                m.add(ch==c).only_enforce_if(choice)
                m.add(active[c,q]==1).only_enforce_if(choice)
                m.add(types[c,q]==int(mode=="4x1")).only_enforce_if(choice)
                slot(c,q,side).append(choice)
                if side:
                    m.add(route["load"]+1==S[c,q]).only_enforce_if(choice)
                else:
                    m.add(route["load"]+4<=S[c,q]).only_enforce_if(choice)
                if mode=="4x1":
                    m.add(route["unload"]>=S[c,q]+180+(0 if side else 3)).only_enforce_if(choice)
                else:
                    slot(c,q+1,0).append(choice)
                    m.add(active[c,q+1]==1).only_enforce_if(choice)
                    m.add(types[c,q+1]==0).only_enforce_if(choice)
                    m.add(route["unload"]>=S[c,q+1]+92).only_enforce_if(choice)
        m.add_exactly_one(choices)
        for k in range(9):
            # Minimum processing / module durations and compulsory travel for this wafer.
            lag=(7,24,7,34,3,181,3,26,7)[k]
            m.add(route[STEPS[k+1]]>=route[STEPS[k]]+lag)
        for name,first,last,delta in (("AL","al_put","al_pick",4),("U","upper_put","source_pick",31),
                ("L","destination_put","lower_pick",29),("ATR","origin_pick","al_put",4),
                ("ATR","al_pick","upper_put",4),("ATR","lower_pick","origin_put",4),
                ("Vin","source_pick","load",1),("Vout","unload","destination_put",1)):
            capacities.setdefault(name,[]).append(interval(route[first],route[last]+delta,f"{name}{i}{first}"))
        for k,(name,loc) in enumerate(zip(STEPS,(orig,"AL","AL","U","U","CH","CH","L","L",orig))):
            robot = "V" if 4<=k<=7 else "A"
            robots[robot].append((i,mode,name,loc,route[name],DUR[k],ch))
        if i and w["pjob"]==wafers[i-1]["pjob"]:
            m.add(route["origin_pick"]>=routes[-1]["origin_pick"])
        end_home.append(route["origin_put"]+4)
        routes.append(route)
    for entries in slots.values():
        m.add(sum(entries)<=2)
    for name,intervals in capacities.items():
        m.add_cumulative(intervals,[1]*len(intervals),1 if name=="AL" else 2)
    for robot,ops in robots.items():
        for (i,mi,ni,li,ti,di,ci),(j,mj,nj,lj,tj,dj,cj) in itertools.combinations(ops,2):
            if i==j:
                continue
            # Omit a disjunction only when the native rules could synchronize two events.
            if mi==mj and ni==nj and li==lj and ni not in ("al_put","al_pick"):
                continue
            order=m.new_bool_var(f"o{i}{ni}_{j}{nj}")
            if li==lj or {li,lj}<={"U","L"}:
                travel=0
            else:
                travel=3 if robot=="A" else 2
            ab=6 if li in ("U","L") and nj=="origin_pick" else travel
            ba=6 if lj in ("U","L") and ni=="origin_pick" else travel
            m.add(tj>=ti+di+ab).only_enforce_if(order)
            m.add(ti>=tj+dj+ba).only_enforce_if(order.Not())
    finish=integer("makespan",519,cap)
    m.add_max_equality(finish,end_home)
    m.minimize(finish)
    return m


if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--source",type=Path,required=True)
    p.add_argument("--out",type=Path,required=True)
    p.add_argument("--budget",type=int,default=300)
    p.add_argument("--workers",type=int,default=2)
    p.add_argument("--cap",type=int,default=547)
    a=p.parse_args()
    a.out.mkdir(parents=True,exist_ok=True)
    doc=json.loads(a.source.read_bytes())
    tag=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    checkpoint=a.out/"result.json"
    if checkpoint.exists():
        prev=json.loads(checkpoint.read_bytes())
        if prev["code_sha256"]==tag and prev["cap"]==a.cap and prev["status"] in ("INFEASIBLE","OPTIMAL"):
            print(prev,flush=True)
            sys.exit(0)
    witness=cp_model.CpSolver()
    witness.parameters.max_time_in_seconds=20
    assert witness.solve(model(doc,round(doc["cmax"]),True)) in (cp_model.FEASIBLE,cp_model.OPTIMAL)
    solver=cp_model.CpSolver()
    solver.parameters.num_workers=a.workers
    solver.parameters.max_time_in_seconds=a.budget
    solver.parameters.log_search_progress=True
    solver.parameters.log_to_stdout=False
    started=time.perf_counter()
    with (a.out/"cp.log").open("w",encoding="utf8",buffering=1) as log:
        solver.log_callback=lambda s:log.write(s.rstrip()+"\n")
        def bound(b):
            spent=time.perf_counter()-started
            print(f"lower={b:.0f}, elapsed={spent:.0f}s, budget remaining={max(0,a.budget-spent):.0f}s",flush=True)
        solver.best_bound_callback=bound
        status=solver.solve(model(doc,a.cap))
    result=dict(status=solver.status_name(status),cap=a.cap,code_sha256=tag,
                source_sha256=hashlib.sha256(a.source.read_bytes()).hexdigest(),
                lower=a.cap+1 if status==cp_model.INFEASIBLE else solver.best_objective_bound,
                upper=solver.objective_value if status in (cp_model.OPTIMAL,cp_model.FEASIBLE) else None,
                native_upper=doc["cmax"],wall_seconds=solver.wall_time,branches=solver.num_branches)
    checkpoint.write_text(json.dumps(result,indent=2),encoding="utf8")
    print(result,flush=True)

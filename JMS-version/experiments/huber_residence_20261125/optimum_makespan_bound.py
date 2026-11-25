"""Eight-wafer makespan lower bound. Keep product routes, omit dummy and terminal clean transfers."""
import argparse
import hashlib
import itertools
import json
from pathlib import Path
import sys
import time

from ortools.sat.python import cp_model


HORIZON = 610
SLOTS = 5
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
    # Hence a chamber has at most five productive cycles, all before any cleaning.
    assert (cap-76-40+4)//94 <= SLOTS
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
        for q in range(SLOTS):
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
                if mode=="2x2" and (q==SLOTS-1 or not side):
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


def conditioned(data,cap):
    from google.protobuf import text_format
    from ortools.sat import cp_model_pb2
    original=model(data,cap)
    scale=8
    proto=text_format.Parse(str(original.proto),cp_model_pb2.CpModelProto())
    indices={v.name:i for i,v in enumerate(proto.variables)}
    times={i for i,v in enumerate(proto.variables) if v.name.startswith(("duration_","ch_","start(","makespan"))
           or (v.name and v.name[0].isdigit())}
    def scaled(n):
        if n in (-(2**63),2**63-1):
            return n
        return scale*n
    def duration(expr):
        if any(i in times for i in expr.vars):
            for k,i in enumerate(expr.vars):
                if i not in times:
                    expr.coeffs[k]*=scale
            expr.offset*=scale
        else:
            if expr.vars:
                raise ValueError("Unexpected discrete variable in a time expression")
            expr.offset*=scale
    for i in times:
        v=proto.variables[i]
        v.domain[:]=[scaled(x) for x in v.domain]
    for c in proto.constraints:
        kind=c.WhichOneof("constraint")
        if kind=="linear":
            row=c.linear
            if not any(i in times for i in row.vars):
                continue
            row.domain[:]=[scaled(n) for n in row.domain]
            for k,i in enumerate(row.vars):
                if i not in times:
                    row.coeffs[k]*=scale
        elif kind=="interval":
            for t in (c.interval.start,c.interval.end,c.interval.size):
                duration(t)
        elif kind=="lin_max" and any(i in times for i in c.lin_max.target.vars):
            for t in (c.lin_max.target,*c.lin_max.exprs):
                duration(t)
        elif kind not in ("exactly_one","cumulative","lin_max"):
            raise ValueError(kind)

    proto.ClearField("solution_hint")
    proto.ClearField("objective")
    m=cp_model.CpModel()
    m.proto.parse_text_format(str(proto))
    vv={v.name:m.get_int_var_from_proto_index(i) for i,v in enumerate(m.proto.variables)}
    # A C<=610 optimum has exactly two full front pairs on one chamber. One
    # mixed chain of >=4 cycles is confined to the other. Sharing it with one
    # full cycle would take at least 540 seconds within the 494s product window.
    # Three full cycles in one chamber are impossible by the same calculation.
    # The sole terminal mixed wafer requires three or four pairs in the chain.
    # For symmetry fix the full chamber to code 0.
    for i in range(8):
        m.add(vv[f"ch{i}"]==(0 if i<4 else 1))
    for q in range(SLOTS):
        for i in range(4):
            m.add(vv[f"w{i}_0_{q}_0"]==0)
        m.add(sum(vv[f"w{i}_0_{q}_1"] for i in range(4))==2*vv[f"full{0,q}"])
        m.add(vv[f"use{0,q}"]==int(q<2));m.add(vv[f"full{0,q}"]==int(q<2))
        m.add(vv[f"full{1,q}"]==0)
        if q<4:m.add(vv[f"use{1,q}"]==1)
        if q and q<4:m.add(vv[f"start{1,q}"]>=vv[f"start{1,q-1}"]+94*8)
    m.add(vv["start(0, 1)"]>=vv["start(0, 0)"]+188*8)
    last=[]
    for i in range(8):
        residence=vv[f"{i}_unload"]-vv[f"{i}_load"]-181*8
        if i<4:m.add(residence==0)
        else:
            flag=m.new_bool_var(f"mixed_last_{i}")
            m.add(residence==53+3*flag);last.append(flag)
            for q in range(4):
                if q<2:m.add(flag==0).only_enforce_if(vv[f"w{i}_1_{q}_1"])
                if q==2:m.add(flag==1).only_enforce_if([vv[f"w{i}_1_{q}_1"],vv["use(1, 4)"].Not()])
                if q==3:m.add(flag==1).only_enforce_if(vv[f"w{i}_1_{q}_1"])
    m.add(sum(last)==1)
    return m

if __name__=="__main__":
    import argparse
    p=argparse.ArgumentParser();p.add_argument("--seconds",type=int,default=40);p.add_argument("--cap",type=int,default=610);p.add_argument("--optimize",action="store_true")
    a=p.parse_args()
    root=Path(__file__).resolve().parents[2]/"results/huber_residence_20261125"
    src=root/"witnesses/D_n8_H10_mixed_dual/schedule.json"
    doc=json.loads(src.read_bytes())
    out=root/"frontier"/(f"H10_attainment_min_to_{a.cap}" if a.optimize else f"H10_attainment_cap_{a.cap}");out.mkdir(exist_ok=True,parents=True)
    s=cp_model.CpSolver();s.parameters.num_workers=1;s.parameters.max_time_in_seconds=a.seconds
    s.parameters.log_search_progress=True;s.parameters.log_to_stdout=False
    m=conditioned(doc,a.cap);m.clear_objective()
    if a.optimize:
        C=next(m.get_int_var_from_proto_index(i) for i,v in enumerate(m.proto.variables) if v.name=="makespan");m.minimize(C)
    with (out/"cp.log").open("w",encoding="utf8",buffering=1) as f:
        s.log_callback=lambda l:f.write(l.rstrip()+"\n")
        status=s.solve(m)
    r=dict(status=s.status_name(status),cap=a.cap,scale=8,seconds=s.wall_time,workers=1,
           guaranteed_minimum_C=a.cap+.125 if status==cp_model.INFEASIBLE else s.best_objective_bound/8 if a.optimize else None,projected_feasible_C=s.objective_value/8 if a.optimize and status in (cp_model.OPTIMAL,cp_model.FEASIBLE) else None,
           code_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),source_sha256=hashlib.sha256(src.read_bytes()).hexdigest())
    (out/"result.json").write_text(json.dumps(r,indent=2));print(r,flush=True)

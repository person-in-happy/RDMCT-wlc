"""Equal-size sub-MIP neighborhoods of a physical timetable."""
from collections import defaultdict
from dataclasses import asdict, replace
import time

from common import metrics, TOL
from native import Native
from seed import constrain_seed
from validate import validate
from witness import sparse_witness


def critical_events(data):
    jobs = {j["name"]:j for j in data["jobs"]}
    by_job = defaultdict(dict)
    for e in data["events"]:
        if "job" in e:
            by_job[e["job"]][e["kind"]] = e
    cfg = data["config"]
    delays = defaultdict(float)
    for name,es in by_job.items():
        j = jobs[name]
        delays[j["pair"]] = max(delays[j["pair"]],j["load_start"]-es["source_pick"]["end"]-cfg["vtr_travel"],
                                es["destination_put"]["start"]-j["unload_end"]-cfg["vtr_travel"])
        if j["product"]:
            for a,b,dt in (("al_pick","upper_put","atr_travel"),("upper_put","source_pick","pump"),
                           ("destination_put","lower_pick","vent")):
                delays[j["pair"]] = max(delays[j["pair"]],es[b]["start"]-es[a]["end"]-cfg[dt])
    target = max((j["pair"] for j in jobs.values() if j["product"]),key=delays.__getitem__)
    related = {target}
    for cy in data["cycles"]:
        if target in cy["pairs"]:
            related.update(cy["pairs"])
    def relation(e):
        p = jobs[e["job"]]["pair"] if "job" in e else e.get("pair")
        return 2 if p==target else int(p in related)
    return {e["name"]:relation(e) for e in data["events"]},target


def improve(cfg, parent, partner, goal, cap, deadline, rng, coupled, fraction, weight):
    data = parent["data"]
    compact = replace(cfg,max_pairs=1+max(p["id"] for p in data["pairs"]),
                      max_cycles=1+max(c["index"] for c in data["cycles"]))
    solver = Native(compact,1,weight)
    try:
        m = solver.m
        constrain_seed(solver.x,data,times=False)
        values = sparse_witness(cfg,data)
        other = sparse_witness(cfg,partner["data"])
        important,target = critical_events(data)
        candidates = {}
        for robot in ("VTR","ATR"):
            actions = [e["name"] for e in data["events"] if e["robot"]==robot]
            for i,a in enumerate(actions):
                for b in actions[i+1:]:
                    score = important[a]+important[b]
                    for left,right in ((a,b),(b,a)):
                        candidates["order_"+left+"_"+right] = score
                        candidates["sync_"+left+"_"+right] = score
        pool = [v for v in solver.variables if v.name in candidates]
        how_many = max(1,round(len(pool)*fraction))
        tie = {v.name:rng.random() for v in pool}
        def priority(v):
            diff = values.get(v.name,0)!=other.get(v.name,0)
            return (candidates[v.name] if coupled else 0,diff,tie[v.name])
        pool.sort(key=priority,reverse=True)
        for v in pool[how_many:]:
            value = float(values.get(v.name,0))
            m.chgVarLb(v,value)
            m.chgVarUb(v,value)
        result,info = solver.query(goal,cap,False,[parent],deadline)
        for d in result:
            d["config"] = asdict(cfg)
            d["validation"] = validate(d)
            if not d["validation"]["valid"]:
                raise ValueError(d["validation"])
        return result,info | {"scope":"fixed topology, local robot orders","released_orders":min(how_many,len(pool)),
                              "eligible_orders":len(pool),"target_pair":target}
    finally:
        solver.close()

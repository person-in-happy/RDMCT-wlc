"""Refine a small active-phase archive with its compatible two-chamber disjunctions.

The validated split-oracle domain is specific to nominal S1. Search caps, archive
coordinates and initial witnesses come exclusively from the current active-phase run.
"""
import argparse
import gzip
import json
from pathlib import Path
import time

from active_phase import extend, productive
from certify import recipe
from split_oracle import PATTERNS, SplitOracle
from common import JMS, TOL, config, digest, dominates, lower_bound, metrics, save
from native import Native
from validate import validate


def refine(source, target, seconds):
    target.mkdir(parents=True, exist_ok=False)
    initial = json.loads((source/"result.json").read_text(encoding="utf-8"))
    start = time.monotonic()
    deadline = start+seconds
    cfg = config("S1")
    full = Native(cfg,1,25)
    front,log = [],[]
    def admit(data, origin):
        mm=metrics(data,25)
        ab=mm["cmax"],mm["secondary"]
        if not validate(data)["valid"] or not full.warm(data):
            raise ValueError("Active event schedule failed the full original-model check")
        if time.monotonic()>deadline:
            return None
        if not any(dominates(r["ab"],ab) or max(abs(a-b) for a,b in zip(r["ab"],ab))<=TOL for r in front):
            front[:]=[r for r in front if not dominates(ab,r["ab"])]
            name=f"candidate_{len(list(target.glob('candidate_*')))+1:03d}.json.gz"
            with gzip.open(target/name,"wt",encoding="utf-8") as f:
                json.dump(data,f,separators=(",",":"),allow_nan=False)
            front.append(dict(ab=ab,origin=origin,schedule=name,sha256=digest(target/name)))
        return ab

    def find(goal, a_cap, b_cap):
        candidates=[]
        for pattern in PATTERNS:
            if deadline-time.monotonic()<.25:
                break
            # The existing oracle checks its model domain in its constructor.
            # Do not silently clip an input to a previously certified objective value.
            try:
                reduced=SplitOracle(cfg,pattern,a_cap+1e-7,b_cap+1e-7)
            except AssertionError:
                log.append(dict(goal=goal,A_cap=a_cap,B_cap=b_cap,pattern=pattern,
                                status="outside_validated_event_model_domain"))
                continue
            try:
                row=reduced.solve((goal,),min(7.,max(.05,deadline-time.monotonic())))
            finally:
                reduced.model.freeProb()
            detail={k:v for k,v in row.items() if k!="times"}
            if "times" in row and time.monotonic()<deadline-.2:
                part=productive(cfg,False,a_cap+1e-6)
                try:
                    recipe(part.x,row["times"])
                    part.m.setObjective(0)
                    part.m.setRealParam("limits/time",min(5.,max(.05,deadline-time.monotonic())))
                    part.m.optimize()
                    sol=part.m.getBestSol()
                    detail["equipment_completion"]=str(part.m.getStatus())
                    if sol is not None and part.m.checkSol(sol,original=True,completely=True):
                        actual=admit(extend(cfg,part.x.result(solution=sol)),f"{pattern} {goal}")
                        if actual is not None:
                            if actual[0]>a_cap+TOL or actual[1]>b_cap+TOL:
                                raise ValueError("Completed objective lies outside the requested rectangle")
                            candidates.append(actual)
                            detail["full_original_feasible"]=actual
                finally:
                    part.close()
            log.append(dict(goal=goal,A_cap=a_cap,B_cap=b_cap,pattern=pattern)|detail)
        save(target/"queries.json",log)
        return candidates

    try:
        pp,split=[],[]
        for item in initial["front"]:
            with gzip.open(source/item["file"],"rt",encoding="utf-8") as f:
                data=json.load(f)
            point=admit(data,"charged active-phase run")
            direct=any(sum(w.startswith("LP") for w in p["members"])==2 for p in data["pairs"])
            (pp if direct else split).append(point)
        b_ceiling=min(b for a,b in pp)
        a_trial=min(a for a,b in split if b<b_ceiling)
        floor=lower_bound(cfg,2,0)
        floor_points=find("A",a_trial,floor)
        ceiling=min((a for a,b in floor_points),default=a_trial)
        cap=b_ceiling-.01
        for k in range(12):
            if deadline-time.monotonic()<.3:
                break
            candidates=find("A",ceiling,cap)
            if not candidates:
                break
            a_best=min(a for a,b in candidates)
            tied=[b for a,b in candidates if abs(a-a_best)<TOL]
            refined=find("B",a_best+1e-7,cap)
            b_best=min(tied+[b for a,b in refined if a<=a_best+TOL])
            print(f"更新 {k+1} | 已复验 ({a_best:.4f}, {b_best:.4f}) | "
                  f"保留 {len(front)} 点 | 失败 0 | 预计剩余 {max(0,deadline-time.monotonic()):.0f}s",flush=True)
            if b_best<=floor+TOL:
                break
            cap=b_best-.01
    finally:
        full.close()
    total=time.monotonic()-start
    save(target/"result.json",dict(case="S1",input_sha256=digest(source/"result.json"),input_seconds=initial["seconds_used"],
         refinement_seconds=total,combined_seconds=total+initial["seconds_used"],budget_seconds=seconds,
         first_verified_pair_rectangle=[a_trial,b_ceiling],derived_A_ceiling=ceiling,analytic_floor=floor,
         domain="nominal two PD pairs in distinct chambers, equipment checks on original model",
         B_resolution=.01,full_original_accepted=True,front=sorted(front,key=lambda p:p["ab"]),calls=len(log),
         event_oracle_sha256=digest(JMS/"experiments/pareto_front_20261118/split_oracle.py"),
         event_completion_sha256=digest(JMS/"experiments/pareto_front_20261118/certify.py")))


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source",type=Path)
    parser.add_argument("target",type=Path)
    parser.add_argument("--seconds",type=int,default=150)
    args=parser.parse_args()
    refine(args.source.resolve(),args.target.resolve(),args.seconds)

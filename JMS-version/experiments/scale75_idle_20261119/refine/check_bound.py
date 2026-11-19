"""Check the final resource order in continuous time under the original product-return cap."""
from pathlib import Path
import sys

import extend
from scip_imports import scip


def certify(out):
    first, old = extend.first, extend.old
    extend.verify(out)
    summary = old.read(out/"summary.json")
    cfg, blocks, seed = first.restore_seed()
    starts = old.restore(out/"checkpoint.json",summary["protocol_sha256"])["starts"]
    timing = first.fixed_timing(cfg, blocks, starts)
    base = summary["baseline"]
    actual = summary["new"]
    model = scip.Model("D75_continuous_fixed_order_chamber_idle")
    model.hideOutput()
    try:
        model.setIntParam("parallel/maxnthreads", 1)
        model.setIntParam("lp/threads", 1)
        model.setRealParam("limits/memory", 256)
        model.setRealParam("limits/time", 90)
        model.setRealParam("limits/gap", first.GAP)
        x = [model.addVar(f"t{i}",ub=base["equipment_end"]-tail) for i,tail in enumerate(timing.tails)]
        horizon = model.addVar("last_return_or_later", lb=summary["global_primary_lower_bound"], ub=base["cmax"])
        for a, b, lag in sorted(timing.edges):
            model.addCons(x[b] >= x[a]+lag)
        for i in timing.returns:
            model.addCons(horizon >= x[i]+timing.actions[i].duration)
        # At any fixed physical schedule, moving the observation endpoint back to the true
        # last return can only decrease idle and holding. Hence the epigraph has the same minimum.
        sol = model.createSol()
        for var, t in zip(x,starts):
            model.setSolVal(sol,var,t)
        model.setSolVal(sol,horizon,actual["cmax"])
        engine = extend.OrderMix(cfg,blocks)
        idle_vars = []
        for chamber, groups in engine.groups.items():
            key = str(chamber)
            last_product = max(j for j,(mode,_) in enumerate(groups) if mode != "clean")
            occupied, action_lengths, previous_flag = [], [], None
            for j,(_, ops) in enumerate(groups):
                bounds = {}
                for i in ops:
                    duration = int(timing.actions[i].duration)
                    if j < last_product:
                        bounds[i,0], bounds[i,duration] = x[i], x[i]+duration
                        action_lengths.append(duration)
                        continue
                    for offset in (0,duration):
                        v = x[i]+offset
                        ref = starts[i]+offset
                        # y=min(v,horizon). Endpoints on a chamber are chronological.
                        y = model.addVar(ub=base["cmax"])
                        before = model.addVar(vtype="B")
                        model.addCons(y <= v)
                        model.addCons(y <= horizon)
                        model.addCons(y >= v-base["equipment_end"]*(1-before))
                        model.addCons(y >= horizon-base["equipment_end"]*before)
                        if previous_flag is not None:
                            model.addCons(before <= previous_flag)
                        previous_flag = before
                        model.setSolVal(sol,y,min(ref,actual["cmax"]))
                        model.setSolVal(sol,before,int(ref <= actual["cmax"]))
                        bounds[i,offset] = y
                    action_lengths.append(bounds[i,duration]-bounds[i,0])
                occupied.append(bounds[ops[-1],int(timing.actions[ops[-1]].duration)]-bounds[ops[0],0])
            idle = model.addVar(f"idle_CH{chamber}",ub=base["chambers"][key]["idle"])
            busy = scip.quicksum(occupied)
            model.addCons(idle == horizon-busy)
            model.addCons(busy-scip.quicksum(action_lengths) <= base["chambers"][key]["held"])
            model.setSolVal(sol,idle,actual["chambers"][key]["idle"])
            idle_vars.append(idle)
        model.setObjective(scip.quicksum(idle_vars),"minimize")
        if not model.checkSol(sol,printreason=True,completely=True,original=True):
            raise ValueError("Continuous-time formulation rejected the plotted witness")
        model.addSol(sol)
        model.optimize()
        best = model.getBestSol()
        if not model.checkSol(best,printreason=True,completely=True,original=True):
            raise ValueError("Invalid continuous-time timing solution")
        bound = model.getDualbound()
        upper = actual["idle"]
        gap = (upper-bound)/max(1,abs(bound))
        if gap < -1e-7:
            raise ValueError("Invalid bound above the available feasible upper bound")
        record = dict(scope="continuous event times; fixed grouping, chamber and resource orders; original 6217 s cap",
                      status=str(model.getStatus()), solver_gap_limit=model.getParam("limits/gap"),
                      product_return_cap=base["cmax"], feasible_plotted_idle=upper, lower_bound=bound,
                      solver_primal=model.getPrimalbound(), plotted_relative_gap=max(0,gap),
                      plotted_target_met=gap <= first.GAP+1e-9, solve_s=model.getSolvingTime(),
                      code_sha256=old.digest(Path(__file__)), protocol_sha256=summary["protocol_sha256"],
                      result_sha256=old.digest(out/"result.json"), resources=first.sample())
        old.dump(out/"continuous_timing_certificate.json",record)
        print(record,flush=True)
    finally:
        model.freeProb()


if __name__ == "__main__":
    case = Path(sys.argv[1]).resolve() if len(sys.argv)>1 else extend.OUT
    if case.parent != extend.old.JMS/"results" or case in (extend.old.DEFAULT, extend.first.BASE, extend.first.OUT):
        raise SystemExit("Use a separate completed final idle case")
    handle = extend.limit_process()
    extend.wait_for_headroom()
    certify(case)

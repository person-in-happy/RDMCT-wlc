"""Lower-bound the continuous joint objective with an outward integer projection."""
from fractions import Fraction
from pathlib import Path
from dataclasses import replace
import gc
import math
import sys
import time
from ortools.sat.python import cp_model
from primal import OUT, Config, TAU, case_id, cell, endpoint, product, read, sha, store_primary, validate
from inputs import Integrated, JMS, certified_capacity, save
from project import export

SCALE=10**8


def expression(expr, vm):
    terms=[]
    for term,value in expr.terms.items():
        variables=list(term)
        assert len(variables)<=1 and value==round(value)
        terms.append(int(value)*(vm[variables[0].name] if variables else 1))
    return sum(terms)


def joint_relaxation(x,raw,a0,b0):
    cp,v,audit=export(x,raw)
    cfg=x.cfg
    waits=[]
    for j in x.jobs.values():
        if j["product"] is None:
            continue
        legs=[(j["load_s"],j["source_pick"]["e"],cfg.vtr_travel),
              (j["destination_put"]["s"],j["unload_e"],cfg.vtr_travel)]
        for a,b,due in (("first","al_put",cfg.atr_travel),("al_put","al_pick",cfg.alignment),
                     ("al_pick","upper_put",cfg.atr_travel),("upper_put","source_pick",cfg.pump),
                     ("destination_put","lower_pick",cfg.vent),("lower_pick","last",cfg.atr_travel)):
            legs.append((j[b]["s"],j[a]["e"],due))
        for end,start,delay in legs:
            w=cp.new_int_var(0,int(cfg.horizon),"lower_wait")
            # Flooring the two timestamps can increase their difference by less than 1.
            cp.add(w>=expression(end-start-delay*j["active"],v)-1)
            waits.append(w)
    peak=cp.new_int_var(0,int(cfg.horizon),"lower_peak")
    for w in waits:
        cp.add(peak>=w)
    rhythm=[]
    for c in cfg.chambers:
        for q in range(2,x.Q):
            z=cp.new_int_var(0,2*int(cfg.horizon),"lower_rhythm")
            delta=sum(k*v[x.cy.start[c,i].name] for k,i in ((1,q),(-2,q-1),(1,q-2)))
            active=[v[x.keep[c,i].name] for i in (q,q-1)]
            # The flooring error of (+1,-2,+1) has magnitude less than 2.
            for sign in (-1,1):
                cp.add(z>=sign*delta-2).only_enforce_if(active)
            rhythm.append(z)
    score=cp.new_int_var(0,(len(waits)+10+50*len(rhythm))*int(cfg.horizon),"lower_process")
    cp.add(score>=sum(waits)+10*peak+25*sum(rhythm))
    # Two products loaded as a pair have AL puts separated by at least one full
    # AL occupation. Their four post-AL waits end at the same pair-loading time.
    # The earlier wafer accumulates that difference, at least one leg takes >= 1/4.
    doubles=[v[x.pair.product[p,1].name] for p in range(min(x.N,x.P))]
    any_double=cp.new_bool_var("any_two_product_pair")
    cp.add_max_equality(any_double,doubles)
    separation=int(2*cfg.atr_handling+cfg.alignment)
    cp.add(4*score>=4*separation*sum(doubles)+10*separation*any_double)
    factor_a=math.floor(SCALE/Fraction.from_float(float(a0)))
    factor_b=math.floor(SCALE/(10*Fraction.from_float(float(b0))))
    cp.minimize(factor_a*v[x.cmax.name]+factor_b*score)
    assert not cp.validate()
    return cp,v,dict(export=audit,scale=SCALE,weights=[factor_a,factor_b],wait_roundoff=1,
                     rhythm_roundoff=2,AL_occupation=separation)


def run(n,h,seed,decision=False):
    key=case_id(n,h)
    src=OUT/"inputs"/key
    spec=read(src/"input.json")
    cfg=Config(**spec["config"])
    folder=OUT/("portfolio/decision" if decision else "portfolio/runs")/f"{key}__s{seed}"/"J"
    folder.mkdir(parents=True,exist_ok=True)
    if (folder/"endpoint.json").exists():
        return
    start=spec["metrics"]
    a0,b0=start["cmax"],start["secondary"]
    def cost(metrics):
        return metrics["cmax"]/a0+.1*metrics["secondary"]/b0
    raw=cell.values(src/"assignment.json.gz")
    original=read(src/"schedule.json")
    best=cell.certify_start(cfg,original,raw)
    upper=cost(start)
    origin="common input"
    # Archived schedules supply primal hints only. Rebuild under this exact config.
    candidates=[]
    if n==4:
        candidates.append(JMS/"results/mixed_controls_20261122/grid4/mixed__1pct/0p01pct/runs/endpoint")
    candidates.extend([OUT/"runs"/f"{key}__s{seed}"/arm for arm in ("A","AB/runs/endpoint","J/warm/runs/endpoint")])
    for source in candidates:
        if not (source/"assignment.json.gz").exists():
            continue
        data=read(source/"schedule.json")
        if any(data["config"][k]!=spec["config"][k] for k in spec["config"]
               if k not in ("horizon","cleaning_interval")):
            continue
        data["config"]=spec["config"]
        if not validate(data)["valid"] or cost(product.product_metrics(data))>=upper:
            continue
        checked=cell.lift(cfg,cell.values(source/"assignment.json.gz"),None,rebuild=True)
        if checked:
            price=cost(product.product_metrics(checked[0]))
            if price<upper:
                best,upper,origin=checked,price,str(source)
    target=upper/(1+TAU)+1e-8
    cap=min(cfg.horizon,math.ceil(a0*(target if decision else upper)+1e-8))
    plan=certified_capacity(cfg,cap)
    compact=replace(cfg,max_pairs=plan["pairs"],max_cycles=plan["cycles"])
    x=Integrated(compact)
    if decision:
        # A witness outside the decision cap need not use its inferred chamber orientation.
        plan=dict(plan,separated=False)
    cell.strengthen(x,plan,best[0],cap)
    cp,v,audit=joint_relaxation(x,best[1]["nonzero"],a0,b0)
    if decision:
        coeff=cp.proto.objective
        terms=[cp.get_int_var_from_proto_index(i) for i in coeff.vars]
        cp.add(cp_model.LinearExpr.weighted_sum(terms,list(coeff.coeffs))<=math.ceil(SCALE*target))
        cp.clear_objective()
    x.model.freeProb()
    del x
    gc.collect()
    solver=cp_model.CpSolver()
    solver.parameters.num_search_workers=1
    solver.parameters.random_seed=seed
    solver.parameters.log_search_progress=True
    solver.parameters.log_to_stdout=False
    lower=cell.lock_bound(cfg)["lower"]/a0
    started=time.monotonic()
    q=plan["cycles"]
    def report():
        save(folder/"bounds.json",dict(upper=upper,lower=lower,origin=origin,seconds=time.monotonic()-started,
                                      scale=SCALE,cap=cap))
    def reached():
        return upper>=lower-1e-8 and upper<=lower*(1+TAU)+1e-10
    def bound(new):
        nonlocal lower
        # Use floor on the solver's integer objective bound to stay outward.
        lower=max(lower,math.floor(new)/SCALE)
        assert lower<=upper+1e-8
        report()
        if reached():
            solver.stop_search()
    if not decision:
        solver.best_bound_callback=bound
    class Witness(cp_model.CpSolverSolutionCallback):
        def on_solution_callback(self):
            nonlocal best,upper,origin
            if reached():
                self.stop_search()
                return
            vals={name:self.value(z) for name,z in v.items() if self.value(z)}
            checked=cell.lift(cfg,vals,q,rebuild=True)
            if checked:
                price=cost(product.product_metrics(checked[0]))
                if price<upper:
                    best,upper,origin=checked,price,"replayed continuous-model assignment from CP proposal"
                    report()
                    if reached():
                        self.stop_search()
    report()
    with (folder/"projection.log").open("w",encoding="utf8",buffering=1) as stream:
        solver.log_callback=lambda s:stream.write(s.rstrip()+"\n")
        status=solver.solve(cp,Witness())
    if decision and status==cp_model.INFEASIBLE:
        lower=target
    elif status in (cp_model.INFEASIBLE,cp_model.MODEL_INVALID):
        raise ValueError(solver.status_name(status))
    elif not decision:
        lower=max(lower,math.floor(solver.best_objective_bound)/SCALE)
    report()
    if not reached():
        # The projected optimum itself may be below the requested native gap.
        # Keep this bound and witness; the native continuous search remains eligible.
        store_primary(folder/"best",best,dict(upper=upper,lower=lower))
        return
    record=dict(status="verified_gap",engine="continuous joint objective, outward CP bound and full D witness",
                upper=upper,lower=lower,seconds=time.monotonic()-started,relaxation=audit,origin=origin,
                decision_target=target if decision else None,projection_status=solver.status_name(status))
    store_primary(folder,best,record)
    endpoint(folder,folder,"J",spec,seed,record)


if __name__=="__main__":
    run(*map(int,sys.argv[1:4]),decision="--decision" in sys.argv)

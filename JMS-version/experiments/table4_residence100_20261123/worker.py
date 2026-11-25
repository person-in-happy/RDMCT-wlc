"""One fixed-gap comparison on the frozen 100 s physical model."""
from dataclasses import replace
import math
import sys

from inputs import Config, Integrated, OUT, TAU, case_id, cell, certified_capacity, product
from inputs import product_solve, read, save, sha, store_primary, validate


def gap(upper,lower):
    if upper == lower == 0:
        return 0.
    if not math.isfinite(lower) or not math.isfinite(upper) or lower > upper+1e-7 or upper*lower<=0:
        return math.inf
    return abs(upper-lower)/min(abs(upper),abs(lower))


def endpoint(folder, path, arm, spec, seed, record, **extra):
    data = read(path/"schedule.json")
    scores = product.product_metrics(data)
    assert data["config"] == spec["config"] and validate(data)["valid"]
    a,b = scores["cmax"],scores["secondary"]
    ref = spec["metrics"]
    cost = {"A":a,"B":b,"AB":b,"J":a/ref["cmax"]+.1*b/ref["secondary"]}[arm]
    tolerance = cell.EPS if arm!="J" else cell.EPS*(1/ref["cmax"]+.1/ref["secondary"])
    assert abs(cost-record["upper"]) <= tolerance
    actual = gap(record["upper"],record["lower"])
    assert actual <= TAU+1e-9
    save(folder/"endpoint.json",dict(case=spec["case"],arm=arm,seed=seed,target=TAU,actual_gap=actual,
         record=record,metrics=scores,start=spec["assignment_sha256"],path=path.relative_to(OUT).as_posix(),
         schedule_sha256=sha(path/"schedule.json"),assignment_sha256=sha(path/"assignment.json.gz"),**extra))


def primary(folder, src, spec, seed):
    cfg = Config(**spec["config"])
    task = dict(n=spec["n"],seed=seed,train=1,seconds=None,gap=TAU,structure="free",
                kind="cp",method="default",bounds=True)
    # The 16-wafer comparison was registered on a finite candidate domain.
    # Intersect its original label limits with the count-relaxation limits.
    original_capacity = cell.capacity
    def capacity(config,upper):
        plan = original_capacity(replace(config,max_pairs=0,max_cycles=0),upper)
        for k,cap in (("pairs",config.max_pairs),("cycles",config.max_cycles)):
            if cap:
                plan[k]=min(plan[k],cap)
        return plan
    cell.capacity = capacity
    try:
        checked,r=cell.primary(task,cfg,read(src/"schedule.json"),cell.values(src/"assignment.json.gz"),
                               folder,spec["assignment_sha256"])
    finally:
        cell.capacity=original_capacity
    assert checked and r["gate"]
    store_primary(folder,checked,r)
    endpoint(folder,folder,"A",spec,seed,r)


def secondary(folder, source, spec, seed):
    parent = read(source/"endpoint.json")
    res = product_solve(folder,source/"schedule.json",source/"assignment.json.gz","D",
                        spec["n"],seed,"fixed",gap=TAU)
    assert res["eligible"] and res["replay"]["valid"]
    assert res["job"]["assignment_sha256"]==parent["assignment_sha256"]
    assert res["measured"]["cmax"]<=parent["metrics"]["cmax"]+cell.EPS
    endpoint(folder,folder/"runs/endpoint","AB",spec,seed,res["record"],parent=sha(source/"endpoint.json"))


def free_objective(folder,src,spec,seed,arm):
    cfg = Config(**spec["config"])
    start = spec["metrics"]
    a0,b0 = start["cmax"],start["secondary"]
    # A fixed-structure retiming supplies only an extra primal witness. Its dual
    # bound is never transferred to the free B or J problem.
    warm_dir = folder/"warm"
    warm = product_solve(warm_dir,src/"schedule.json",src/"assignment.json.gz","D",
                         spec["n"],seed,"fixed",gap=TAU)
    assert warm["eligible"] and warm["replay"]["valid"]
    original = read(src/"schedule.json")
    alt = warm_dir/"runs/endpoint"
    def cost(metrics):
        return metrics["secondary"] if arm=="B" else metrics["cmax"]/a0+.1*metrics["secondary"]/b0
    best_cost = min(cost(start),cost(warm["measured"]))
    # f_B is nonnegative. A J incumbent implies an f_A bound. A B
    # incumbent gives no makespan bound. Use the original horizon for B.
    cap = cfg.horizon if arm=="B" else min(cfg.horizon, math.ceil(a0*best_cost+1e-8))
    plan = certified_capacity(cfg,cap)
    compact=replace(cfg,max_pairs=plan["pairs"],max_cycles=plan["cycles"])
    x=Integrated(compact)
    m=x.model
    cell.scip_settings(m,dict(n=spec["n"],seed=seed,seconds=None,gap=TAU),folder)
    m.setRealParam("numerics/feastol",1e-8)
    # Strengthening can select a chamber orientation only when the small
    # candidate window certifies recipe separation. Both supplied witnesses
    # share the same discrete decisions.
    cell.strengthen(x,plan,original,cap)
    native_vars=m.getVars(transformed=False)
    def warm_values(path):
        vals=cell.values(path/"assignment.json.gz")
        for chamber in cfg.chambers:
            for q in range(2,x.Q):
                active=all(vals.get(x.keep[chamber,i].name,0)>.5 for i in (q,q-1))
                a,b,c=(vals.get(x.cy.start[chamber,i].name,0.) for i in (q,q-1,q-2))
                vals[f"rhythm_{chamber}_{q}"]=max(0.,abs(a-2*b+c)-(0 if active else x.M))
        return vals
    values=warm_values(src)
    score,maximum,extra=product.objective_terms(x,values,False,25)
    obj=score if arm=="B" else x.cmax/a0+.1*score/b0
    m.setObjective(obj,"minimize")
    m.addCons(obj<=best_cost+1e-7)
    lower_a=cell.lock_bound(cfg)["lower"]
    bcap=best_cost if arm=="B" else b0/.1*(best_cost-lower_a/a0)
    # The physical sum includes the maximal product wait and all terms are nonnegative.
    m.addCons(maximum<=bcap/11+1e-5)
    admissible=0
    for path,metrics in ((src,start),(alt,warm["measured"])):
        if cost(metrics)>best_cost+1e-7:
            continue
        vals=warm_values(path)
        extra={f"product_pitch_{chamber}_{q}":max(0.,vals[f"rhythm_{chamber}_{q}"]-
               cfg.horizon*(2-vals.get(x.keep[chamber,q].name,0.)-vals.get(x.keep[chamber,q-1].name,0.)))
               for chamber in cfg.chambers for q in range(2,x.Q)}
        candidate=cell.attach(x,vals|extra|{maximum.name:metrics["wait_max"],x.cmax.name:metrics["cmax"]})
        assert abs(m.getSolObjVal(candidate)-cost(metrics))<cell.EPS
        m.addSol(candidate)
        admissible+=1
    assert admissible
    save(folder/"acceleration.json",dict(cap=cap,cap_source="physical horizon" if arm=="B" else "joint incumbent and nonnegative process cost",
         count_relaxation=plan,feasible_cutoff=best_cost,initial=start,warm=warm["measured"],global_A_lower=lower_a,
         max_product_wait_upper=bcap/11,domain=spec["config"],fractional_times=True,threads=1,gap=TAU))
    m.optimize()
    r=dict(upper=m.getPrimalbound(),lower=m.getDualbound(),nodes=m.getNNodes(),seconds=m.getSolvingTime(),
           status=str(m.getStatus()))
    save(folder/"last_stop.json",r)
    if r["status"] not in ("optimal","gaplimit") or gap(r["upper"],r["lower"])>TAU+1e-9:
        raise ValueError(f"No verified native gap: {r}")
    best=m.getBestSol()
    vals={v.name:m.getSolVal(best,v) for v in native_vars}
    q=x.Q
    m.freeProb()
    checked=cell.lift(cfg,vals,q,rebuild=True)
    assert checked and checked[3]["valid"]
    store_primary(folder,checked,r)
    endpoint(folder,folder,arm,spec,seed,r)


def run(n,h,seed,arm):
    key=case_id(n,h)
    src=OUT/"inputs"/key
    spec=read(src/"input.json")
    assert spec["schedule_sha256"]==sha(src/"schedule.json") and spec["assignment_sha256"]==sha(src/"assignment.json.gz")
    assert spec["config"]["module_residency"]==spec["config"]["robot_residency"]==100
    assert spec["config"]["chamber_residency_basis"]=="nonprocessing"
    group=OUT/"runs"/f"{key}__s{seed}"
    folder=group/arm
    folder.mkdir(parents=True,exist_ok=True)
    if not (folder/"endpoint.json").exists():
        if arm=="A":
            primary(folder,src,spec,seed)
        else:
            free_objective(folder,src,spec,seed,arm)
    if arm=="A" and not (group/"AB/endpoint.json").is_file():
        secondary(group/"AB",folder,spec,seed)


if __name__=="__main__":
    n,h,s,a=sys.argv[1:]
    run(int(n),int(h),int(s),a)

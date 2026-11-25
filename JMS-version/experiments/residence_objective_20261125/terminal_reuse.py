"""Rebuild the best archived 553 s handoff under each finite-batch cleaning rule."""
from copy import deepcopy
from pathlib import Path
import sys

from compose import Config, HERE, cell, metrics, normalize_schedule, physical_lower
from compose import read, save, sha, sparse_witness, validate
from solver import run


def rebuild(h, destination):
    results=HERE.parents[1]/"results"
    source=results/"table4_one_percent_20261124/runs/D_n8_H10_mixed_dual__s1/A/witness_1795510889586998400"
    certificate=read(source/"primary.json")
    original=read(source/"schedule.json")
    if not certificate["replay"]["valid"] or sha(source/"schedule.json")!=certificate["schedule_sha256"]:
        raise ValueError("Unverified source")
    config_path=results/f"table4_one_percent_20261124/inputs/D_n8_H{h}_mixed_dual/input.json"
    cfg=Config(**read(config_path)["config"])
    assert all(original["config"][k]==v for k,v in read(config_path)["config"].items() if k!="cleaning_interval")
    data=deepcopy(original)
    clean,=[c for c in data["cycles"] if c["mode"]=="clean"]
    old_ch,old_q=clean["chamber"],clean["index"]
    assert not any(c["index"]>old_q and c["chamber"]==old_ch for c in data["cycles"])
    members=set(clean["pairs"])
    selected_jobs=[j for j in data["jobs"] if j["pair"] in members]
    assert all(not j["product"] for j in selected_jobs) and len(selected_jobs)==4
    job_names={j["name"] for j in selected_jobs}
    def cleaning_event(e):
        return e.get("pair") in members or e.get("job") in job_names or (e.get("chamber"),e.get("cycle"))==(old_ch,old_q)
    clean_events=[e for e in data["events"] if cleaning_event(e)]
    productive=[c for c in data["cycles"] if c!=clean]
    counters={ch:sum(c["chamber"]==ch for c in productive) for ch in cfg.chambers}
    if max(counters.values())>h:
        raise ValueError("Production would cross a mandatory cleaning boundary")
    mandatory=[ch for ch,n in counters.items() if n==h]
    if mandatory:
        # This input has exactly one mandatory tail. Use the old auxiliary-only
        # clean as a temporal block after all outstanding product and dummy actions.
        ch,=mandatory
        begin=max(e["end"] for e in data["events"] if not cleaning_event(e))+max(cfg.upper_reset,cfg.lower_reset)
        delta=begin-min(e["start"] for e in clean_events)
        clean.update(chamber=ch,index=counters[ch],start=clean["start"]+delta,end=clean["end"]+delta)
        for p in data["pairs"]:
            if p["id"] in members:
                p["chamber"]=ch
        for e in clean_events:
            e["start"]+=delta
            e["end"]+=delta
            if e["location"].startswith("CH"):
                e["location"]=f"CH{ch}"
            if "cycle" in e:
                tag="rot_before" if e["name"].startswith("rot_before") else "rot_after"
                e.update(cycle=counters[ch],chamber=ch,name=f"{tag}_{ch}_{counters[ch]}")
        for j in selected_jobs:
            for k in ("loan_start","loan_end","load_start","load_end","unload_start","unload_end"):
                j[k]+=delta
    else:
        data["cycles"]=productive
        data["pairs"]=[p for p in data["pairs"] if p["id"] not in members]
        data["jobs"]=[j for j in data["jobs"] if j["name"] not in job_names]
        data["events"]=[e for e in data["events"] if not cleaning_event(e)]
    data=normalize_schedule(cfg,data)
    valid=validate(data)
    if not valid["valid"]:
        raise ValueError(valid["errors"][:12])
    checked=cell.lift(cfg,sparse_witness(cfg,data),None,rebuild=True)
    if not checked or not checked[3]["valid"]:
        raise ValueError("Native rows failed")
    output,vals,_,replay,rows=checked
    f=metrics(output)
    assert abs(f["cmax"]-553)<1e-6 and abs(f["secondary"]-4.25)<1e-6
    def product_times(s):
        return {w["identity"]:tuple(w[k] for k in ("loan_start","load_end","unload_start","loan_end"))
                for w in s["jobs"] if w["product"]}
    assert product_times(original)==product_times(output)
    start=destination/"retained_product_times"
    save(start/"schedule.json",output)
    save(start/"assignment.json.gz",vals)
    save(start/"primary.json",dict(source=str(source.relative_to(results)),source_sha256=certificate["schedule_sha256"],
         config_sha256=sha(config_path),metrics=f,replay=replay,rows=rows,
         schedule_sha256=sha(start/"schedule.json"),assignment_sha256=sha(start/"assignment.json.gz"),
         fixed_product_times=True,productive_counts=counters,mandatory_cleaning_chambers=mandatory))
    out=run("fixed",start,destination/"retimed",seed=1,gap=0)
    print(dict(H=h,retained=f,retimed=out["measured"],physical_lower=physical_lower(cfg)),flush=True)


def ideal(h,destination,order_window=None,cap=None,resource_slots=False,projected_slack=None):
    """Minimize product-return time while attaining the certified global secondary bound."""
    from model import Integrated
    start=destination/"retained_product_times"
    data=read(start/"schedule.json")
    cfg=Config(**data["config"])
    vals=cell.values(start/"assignment.json.gz")
    x=Integrated(cfg)
    m=x.model
    tag="ideal_fixed" if order_window is None else f"ideal_order_{order_window}"
    if resource_slots:
        tag+="_slots"
    if projected_slack is not None:
        tag+=f"_projection{projected_slack}"
    result_dir=destination/tag
    result_dir.mkdir(parents=True,exist_ok=True)
    cell.scip_settings(m,dict(n=8,seed=1,seconds=60 if order_window is not None else None,gap=0),result_dir)
    m.setRealParam("numerics/feastol",1e-8)
    native=list(m.getVars(transformed=False))
    released=set()
    if order_window is not None:
        from itertools import combinations
        for robot in ("ATR","VTR"):
            events=[e for e in data["events"] if e["robot"]==robot]
            for a,b in combinations(events,2):
                if abs(a["start"]-b["start"])<=order_window:
                    released.update((f"order_{a['name']}_{b['name']}",f"order_{b['name']}_{a['name']}"))
    if resource_slots:
        for v in native:
            if v.name.startswith(("order_AL_","order_U_","order_L_","order_VTR_hand_","order_identity_","slot_","code_")):
                released.add(v.name)
    for v in native:
        if v.vtype()!="CONTINUOUS" and not v.name.startswith("sync_") and v.name not in released:
            b=round(vals.get(v.name,0))
            m.chgVarLb(v,b)
            m.chgVarUb(v,b)
    pairs={p["id"]:p["mode"] for p in data["pairs"]}
    durations={"4x1":cfg.full_time,"2x2":2*cfg.mix_time+2*cfg.rotation+3*cfg.handling}
    for w in data["jobs"]:
        if w["product"]:
            j=x.jobs[w["name"]]
            m.addCons(j["unload_s"]-j["load_e"]==durations[pairs[w["pair"]]])
    if projected_slack is not None:
        projected=read(destination.parents[1]/"joint_candidate/result.json")["projected_only"]
        products=sorted((w for w in data["jobs"] if w["product"]),key=lambda w:(w["pjob"],w["pjob_index"]))
        by_job={(e.get("job"),e["kind"]):e["s"] for e in x.events if "job" in e}
        for i,w in enumerate(products):
            for name in ("origin_pick","al_put","al_pick","upper_put","source_pick","load","unload",
                         "destination_put","lower_pick","origin_put"):
                target=projected[f"{i}_{name}"]
                v=x.jobs[w["name"]][name+"_s"] if name in ("load","unload") else by_job[w["name"],name]
                m.addCons(v>=target-projected_slack)
                m.addCons(v<=target+projected_slack)
    if cap is not None:
        m.addCons(x.cmax<=cap)
    m.addCons(x.cmax>=553)
    m.setObjective(x.cmax,"minimize")
    m.optimize()
    sol=m.getBestSol()
    proof=dict(H=h,engine_status=str(m.getStatus()),native_lower=m.getDualbound(),seconds=m.getSolvingTime(),
               search_nodes=m.getNNodes(),source_sha256=sha(start/"assignment.json.gz"),
               within_objective="Cmax minimized, every product has r_4x1=0 or r_2x2=7",
               robot_order_window=order_window,unfixed_resource_variables=sum(v.name in released for v in native),
               reassign_slots=resource_slots,projected_event_window=projected_slack,cap=cap)
    if sol:
        answer={v.name:m.getSolVal(sol,v) for v in native}
    m.freeProb()
    if sol:
        checked=cell.lift(cfg,answer,None,rebuild=True)
        assert checked and checked[3]["valid"]
        final,vs,_,replay,rows=checked
        f=metrics(final)
        assert abs(f["secondary"]-physical_lower(cfg))<cell.EPS
        save(result_dir/"schedule.json",final)
        save(result_dir/"assignment.json.gz",vs)
        proof.update(metrics=f,rows=rows,replay=replay,schedule_sha256=sha(result_dir/"schedule.json"),
                     assignment_sha256=sha(result_dir/"assignment.json.gz"))
    save(result_dir/"primary.json",proof)
    print(proof.get("metrics"),proof["engine_status"],flush=True)


def midpoint(h, destination):
    from model import Integrated
    cap,ideal=(destination/k for k in ("retained_product_times","ideal_fixed"))
    cfg=Config(**read(cap/"schedule.json")["config"])
    a,b=(cell.values(k/"assignment.json.gz") for k in (cap,ideal))
    x=Integrated(cfg)
    integral=[v.name for v in x.model.getVars(transformed=False) if v.vtype()!="CONTINUOUS"]
    if any(round(a.get(k,0))!=round(b.get(k,0)) for k in integral):
        raise ValueError("Endpoints do not share all discrete decisions")
    x.model.freeProb()
    values={k:(a.get(k,0)+b.get(k,0))/2 for k in a.keys()|b.keys()}
    checked=cell.lift(cfg,values,None,rebuild=True)
    if not checked or not checked[3]["valid"]:
        raise ValueError("Original continuous midpoint rejected")
    data,assignment,_,replay,rows=checked
    f=metrics(data)
    assert abs(f["cmax"]-553.5)<1e-6 and abs(f["secondary"]-3.875)<1e-6
    out=destination/"midpoint"
    save(out/"schedule.json",data)
    save(out/"assignment.json.gz",assignment)
    save(out/"primary.json",dict(H=h,metrics=f,replay=replay,rows=rows,same_integer_variables=len(integral),
         endpoints={k.name:sha(k/"assignment.json.gz") for k in (cap,ideal)},
         schedule_sha256=sha(out/"schedule.json"),assignment_sha256=sha(out/"assignment.json.gz")))
    print(f,flush=True)


if __name__=="__main__":
    h=int(sys.argv[1])
    out=HERE.parents[1]/f"results/residence_objective_20261125/best_reuse/n8_H{h}"
    if len(sys.argv)==2:
        rebuild(h,out)
    elif sys.argv[2]=="midpoint":
        midpoint(h,out)
    else:
        ideal(h,out,int(sys.argv[3]) if len(sys.argv)>3 else None,int(sys.argv[4]) if len(sys.argv)>4 else None,
              len(sys.argv)>5,int(sys.argv[6]) if len(sys.argv)>6 else None)

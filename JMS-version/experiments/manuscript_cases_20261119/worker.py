"""One foreground campaign worker. Each cell imports precisely its D or E backend."""
import argparse
import os
from pathlib import Path
import sys
import time

from cases import BACKENDS, HERE, JMS, ROOT, dump, read, sha

for name in ("OMP_NUM_THREADS","OPENBLAS_NUM_THREADS","MKL_NUM_THREADS","NUMEXPR_NUM_THREADS"):
    os.environ[name]="1"
os.environ["CUDA_VISIBLE_DEVICES"]=""


def prepare_backend(family):
    sys.path[:0]=[str(BACKENDS[family]),str(HERE.parent/"scale75_repack_20261118"),
                  str(HERE.parent/"scale75_20261118"),str(JMS/"tools"),
                  str(HERE.parent/"finite_budget_20261116"),str(ROOT)]
    import model, validate, seed, pjob_order, grippers, joint_chamber_cycle_model, joint_pairing_model
    for m in (model,validate,seed,pjob_order,grippers,joint_chamber_cycle_model,joint_pairing_model):
        if Path(m.__file__).resolve().parent!=BACKENDS[family]:
            raise RuntimeError(f"Wrong {family} backend for {m.__name__}")
    import improve
    return model.Config,validate.validate,improve.SWEEPS,improve.STRATUM_WIDTH


def lane_metrics(data):
    finish=data["cmax"]
    chambers={}
    by_pair={p["id"]:p["chamber"] for p in data["pairs"]}
    for ch in data["config"]["chambers"]:
        intervals={(j["load_start"],j["unload_end"]) for j in data["jobs"] if by_pair[j["pair"]]==ch}
        intervals.update((e["start"],e["end"]) for e in data["events"] if e["location"]==f"CH{ch}")
        intervals.update((c["start"],c["end"]) for c in data["cycles"] if c["chamber"]==ch)
        holes,last=[],0.
        for a,b in sorted(intervals):
            if a>=finish: break
            if a>last+1e-6: holes.append([last,a])
            last=max(last,min(b,finish))
        if finish>last+1e-6: holes.append([last,finish])
        chambers[str(ch)]=dict(idle=sum(b-a for a,b in holes),longest=max((b-a for a,b in holes),default=0),
                               longest_interval=max(holes,key=lambda h:h[1]-h[0],default=None))
    ends=[c["end"] for c in data["cycles"]]+[e["end"] for e in data["events"]]
    for e in data["events"]:
        if e["kind"]=="lower_pick":
            ends.append(e["end"]+data["config"]["lower_reset"])
        if e["kind"]=="source_pick" and e["location"]=="U":
            ends.append(e["end"]+data["config"]["upper_reset"])
    return dict(chambers=chambers,equipment_end=max(ends),idle=sum(x["idle"] for x in chambers.values()))


def execute(case,dest,token):
    Config,validate,sweeps,width=prepare_backend(case["backend"])
    from archived import ArchivedOrder
    from certificate import refine
    from finite_budget import physical_metrics
    from grouping import GAP,InstanceSearch,WindowSearch,flexible_blocks,fixed_timing,grouped_schedule,include_atmospheric_store,solve_fixed,solve_window
    from neighborhood import window_sequence
    from resources import limit_process,sample,wait_for_headroom
    from search import workload_bound

    job=limit_process()
    wait_for_headroom()
    started=time.monotonic()
    dest.mkdir(parents=True,exist_ok=True)
    def progress(phase,**fields):
        dump(dest/"progress.json",dict(phase=phase,**fields))

    progress("inputs")
    source=ROOT/case["source"]
    if sha(source)!=case["source_sha256"] or sha(ROOT/case["assignment"])!=case["assignment_sha256"]:
        raise ValueError("Frozen manuscript input changed")
    data=read(source)
    cfg=Config(**case["config"])
    if cfg.source=="single":
        include_atmospheric_store()
    if data["config"]!=case["config"] or not validate(data)["valid"]:
        raise ValueError(f"Invalid source schedule for {case['id']}")
    original=physical_metrics(data)
    lower=workload_bound(cfg)
    packing=InstanceSearch(cfg)
    archive=ArchivedOrder(cfg,data)
    file=dest/"windows.json"
    def real(blocks,starts,origin):
        row=archive.schedule(starts) if origin=="archive" else grouped_schedule(fixed_timing(cfg,blocks,starts),starts)
        proof=validate(row)
        if not proof["valid"]:
            raise ValueError(str(proof["errors"][:4]))
        row["validation"]=proof
        return row

    if file.exists():
        state=read(file)
        if state["protocol"]!=token:
            raise ValueError("Incompatible saved window checkpoint")
    else:
        layer=dest/"groups.json"
        if layer.exists():
            group=read(layer)
            if group["protocol"]!=token: raise ValueError("Incompatible grouping checkpoint")
            depth,beam=group["depth"],[tuple(map(tuple,p)) for p in group["beam"]]
        else:
            depth,beam=0,[()]
        while depth<packing.n:
            beam=packing.next_layer(beam,width)
            depth+=1
            dump(layer,dict(protocol=token,depth=depth,beam=beam))
            progress("grouping",depth=depth,total=packing.n)
        archive_times=archive.integer_times()
        candidates=[]
        archive_info={}
        try:
            graph=fixed_timing(cfg,[archive],archive_times)
            refined=solve_fixed(graph,"A",archive_times)
            starts=[round(t) for t in refined["starts"]]
            if max(abs(t-v) for t,v in zip(starts,refined["starts"]))>1e-5:
                raise ValueError("Nonintegral archived makespan witness")
            incumbent=real([archive],starts,"archive")
            candidates.append((incumbent["cmax"],0,"archive",[],starts))
            archive_info={k:v for k,v in refined.items() if k!="starts"}
        except ValueError as exc:
            archive_info={"unavailable_on_integer_grid":str(exc)}
        group_info=[]
        for plan in beam:
            if packing.extent(plan)>cfg.horizon:
                continue
            blocks=flexible_blocks(packing,plan)
            s=[at+t for (_,_,at),p in zip(plan,blocks) for t in p.times]
            result=solve_fixed(fixed_timing(cfg,blocks,s),"A",s)
            starts=[round(t) for t in result["starts"]]
            if max(abs(t-v) for t,v in zip(starts,result["starts"]))>1e-5:
                raise ValueError("Nonintegral grouping witness")
            witness=real(blocks,starts,"group")
            candidates.append((witness["cmax"],1,"group",plan,starts))
            group_info.append(dict(plan=plan,cmax=witness["cmax"],relative_gap_limit=result["relative_gap_limit"]))
        if not group_info:
            raise ValueError("No feasible grouped schedule")
        best=min(candidates,key=lambda item:(item[0],item[1]))
        value,_,origin,plan,starts=best
        state=dict(protocol=token,origin=origin,plan=plan,starts=starts,initial_cmax=value,records=[],
                   windows=[],index=0,sweep=0,archive_seed=archive_info,beam_candidates=group_info)
        dump(file,state)
    origin=state["origin"]
    blocks=[archive] if origin=="archive" else flexible_blocks(packing,state["plan"])
    engine=WindowSearch(cfg,blocks)
    while state["sweep"]<len(sweeps) and engine.finish(state["starts"])>lower["seconds"]*(1+GAP):
        no=state["sweep"]
        width_s,band,seconds,reverse=sweeps[no]
        if not state["windows"]:
            state["windows"]=window_sequence(engine.finish(state["starts"]),width_s,reverse)
        for i in range(state["index"],len(state["windows"])):
            lo,hi=state["windows"][i]
            proposed,record=solve_window(engine,state["starts"],lo,hi,band,seconds)
            if record["upper_after"]<record["upper_before"]:
                try:
                    real(blocks,proposed,origin)
                except ValueError as exc:
                    record["replay_rejection"]=str(exc)
                else:
                    state["starts"]=proposed
            record["retained_cmax"]=engine.finish(state["starts"])
            state["records"].append(dict(sweep=no+1,**record))
            state["index"]=i+1
            dump(file,state)
            progress("windows",sweep=no+1,window=i+1,total=len(state["windows"]),cmax=record["retained_cmax"])
            if record["retained_cmax"]<=lower["seconds"]*(1+GAP):
                break
        state.update(sweep=no+1,index=0,windows=[])
        dump(file,state)
    selected_file=dest/"selected.json"
    if selected_file.exists():
        selected=read(selected_file)
        if selected["protocol"]!=token: raise ValueError("Incompatible primary checkpoint")
        chosen=read(dest/"selected_schedule.json")
        if sha(dest/"selected_schedule.json")!=selected["sha256"]: raise ValueError("Primary checkpoint changed")
    else:
        starts=state["starts"]
        post=solve_fixed(fixed_timing(cfg,blocks,starts),"A",starts)
        tested=[(real(blocks,starts,origin),origin+"_windows"),(data,"archived_incumbent")]
        try:
            tested.append((real(blocks,post["starts"],origin),origin+"_fixed_time"))
        except ValueError as exc:
            post["replay_rejection"]=str(exc)
        # Physical objective breaks matches within the model's comparison tolerance.
        ceiling=min(physical_metrics(d)["cmax"] for d,_ in tested)
        chosen,label=min(((d,n) for d,n in tested if physical_metrics(d)["cmax"]<=ceiling+1e-6),
                         key=lambda item:physical_metrics(item[0])["secondary"])
        chosen=dict(chosen,cmax=physical_metrics(chosen)["cmax"])
        dump(dest/"selected_schedule.json",chosen)
        selected=dict(protocol=token,sha256=sha(dest/"selected_schedule.json"),origin=label,
                      fixed_time={k:v for k,v in post.items() if k!="starts"})
        dump(selected_file,selected)
    progress("paper_objective_and_full_audit",cmax=chosen["cmax"])
    a,b,record=refine(cfg,chosen,dest)
    for tag,sched in (("primary",a),("final",b)):
        dump(dest/(tag+".json"),sched)
    dump(dest/"certificate.json",record)
    primary=physical_metrics(a)
    final=physical_metrics(b)
    for tag,metrics in (("primary",primary),("final",final)):
        if metrics["cmax"]<lower["seconds"]-2e-4:
            raise ValueError(f"Invalid workload bound in {tag}")
    reference=data
    if case.get("dimension_source"):
        path=ROOT/case["dimension_source"]
        if sha(path)!=case["dimension_sha256"]: raise ValueError("Model-dimension reference changed")
        reference=read(path)
    dims=(reference.get("variables"),reference.get("constraints"))
    for key in ("primary_certificate","final_certificate"):
        checked=record[key]
        if all(dims) and dims!=(checked["variables"],checked["rows"]):
            raise ValueError(f"Full model dimensions differ from the archive {dims}: {checked['variables']},{checked['rows']}")
    names=("primary.json","final.json","primary_assignment.json.gz","final_assignment.json.gz","windows.json",
           "groups.json","certificate.json","selected.json","selected_schedule.json")
    evidence=dict(protocol=token,case=case["id"],backend=case["backend"],n=case["n"],mix=case["mix"],
                  source_sha256=case["source_sha256"],seed=1,workers=1,A_gap=GAP,B_gap=record["gap_limit"],
                  beam_width=width,sweeps=sweeps,initial=original,primary=primary,final=final,
                  primary_lanes=lane_metrics(a),final_lanes=lane_metrics(b),group_candidates=len(state["beam_candidates"]),
                  window_count=len(state["records"]),window_origin=origin,selected_origin=selected["origin"],
                  replay_rejections=sum("replay_rejection" in row for row in state["records"]),
                  primary_lower_bound=lower,primary_global_gap_upper=max(0,(primary["cmax"]-lower["seconds"])/lower["seconds"]),
                  primary_analytical_target_met=primary["cmax"]<=lower["seconds"]*(1+GAP),
                  secondary_status=record["status"],secondary_upper=record["primal"],secondary_lower=record["dual"],
                  secondary_relative_gap=record["relative_gap"],secondary_scope=record["scope"],
                  full_model_rows=record["final_certificate"]["rows"],replay_checks=b["validation"]["checks"],
                  resources=sample(),worker_wall_s=time.monotonic()-started,files={n:sha(dest/n) for n in names})
    dump(dest/"evidence.json",evidence)
    progress("completed",primary=primary["cmax"],secondary=final["secondary"])
    print(f"{case['id']} complete | A={primary['cmax']:.3f} B={final['secondary']:.3f}",flush=True)


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("output",type=Path)
    parser.add_argument("cell")
    args=parser.parse_args()
    spec=read(args.output/"campaign.json")
    cell=next(c for c in spec["cases"] if c["id"]==args.cell)
    execute(cell,args.output/"cases"/args.cell,sha(args.output/"campaign.json"))

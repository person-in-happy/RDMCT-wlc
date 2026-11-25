"""Compose verified chamber blocks to realize the finite-batch quota lower bounds."""
from dataclasses import asdict
from pathlib import Path
import sys

from solver import HERE, cell, read, save, sha
from score import metrics, physical_lower

sys.path.insert(0,str(cell.BACKENDS["D"]))
sys.path.insert(0,str(HERE.parent/"pareto_rl_dmct_20261119"))
from model import Config
from seed import normalize_schedule
from validate import validate
from witness import sparse_witness


def construct(n,h):
    results=HERE.parents[1]/"results"
    name=f"D_n{n}_H{h}_mixed_dual"
    dest=results/"quota_objective_20261125/witnesses"/name
    config_path=results/"table4_one_percent_20261124/inputs"/name/"input.json"
    cfg=Config(**read(config_path)["config"])
    singleton=results/"residence_objective_20261125/reuse/transfers/D_n2_H3_mixed_dual/schedule.json"
    pair=results/"residence_objective_20261125/reuse/transfers/D_n4_H3_mixed_dual/schedule.json"
    chain=results/"table4_one_percent_20261124/runs/D_n8_H10_mixed_dual__s1/A/witness_1795510889586998400/schedule.json"
    sources={config_path}
    out=dict(config=asdict(cfg),schema=1,solutions=1,pairs=[],jobs=[],events=[],cycles=[])
    counts={c:0 for c in cfg.chambers}
    cycle_indices={c:0 for c in cfg.chambers}
    spare=max(cfg.upper_reset,cfg.lower_reset,cfg.vtr_travel,cfg.atr_travel)

    def append_block(data, selected, labels, chambers):
        pairs = [p for p in data["pairs"] if p["id"] in selected]
        pair_map = {p["id"]: len(out["pairs"])+i for i,p in enumerate(pairs)}
        cycles = [c for c in data["cycles"] if set(c["pairs"]).issubset(selected)]
        cycles.sort(key=lambda r:(r["chamber"],r["index"]))
        jobs = [w for w in data["jobs"] if w["pair"] in selected]
        prefix = f"block{len(out['pairs'])}_"
        job_map = {w["name"]: prefix+w["name"] for w in jobs}
        origins = {w["name"]:labels.get(w["identity"],w["identity"]).split("_")[0] for w in jobs if w["product"]}
        cycle_map = {}
        for c in cycles:
            chamber = chambers[c["chamber"]]
            cycle_map[c["chamber"],c["index"]] = cycle_indices[chamber]
            cycle_indices[chamber] += 1
        events = [e for e in data["events"] if e.get("job") in job_map or e.get("pair") in pair_map
                  or (e.get("chamber"),e.get("cycle")) in cycle_map]
        offset = (max(e["end"] for e in out["events"])+spare if out["events"] else 0) - min(e["start"] for e in events)
        for p in pairs:
            out["pairs"].append(dict(p,id=pair_map[p["id"]],members=[labels.get(w,w) for w in p["members"]],
                                     chamber=chambers[p["chamber"]]))
        for w in jobs:
            j=dict(w,name=job_map[w["name"]],pair=pair_map[w["pair"]],identity=labels.get(w["identity"],w["identity"]))
            if w["product"]:
                j["origin"]=origins[w["name"]]
            for k in ("loan_start","loan_end","load_start","load_end","unload_start","unload_end"):
                j[k]+=offset
            out["jobs"].append(j)
        for old in events:
            e=dict(old,start=old["start"]+offset,end=old["end"]+offset)
            if "pair" in e:
                e["pair"]=pair_map[e["pair"]]
            if "job" in e:
                e["job"]=job_map[old["job"]]
                if e["location"].startswith("LP"):
                    e["location"]=origins[old["job"]]
            if e["location"].startswith("CH"):
                e["location"]="CH"+str(chambers[int(old["location"][2:])])
            if "cycle" in e:
                e["chamber"]=chambers[old["chamber"]]
                e["cycle"]=cycle_map[old["chamber"],old["cycle"]]
                tag="rot_before" if old["name"].startswith("rot_before") else "rot_after"
                e["name"]=f"{tag}_{e['chamber']}_{e['cycle']}"
            out["events"].append(e)
        for c in cycles:
            chamber=chambers[c["chamber"]]
            counts[chamber]=0 if c["mode"]=="clean" else counts[chamber]+1
            out["cycles"].append(dict(c,chamber=chamber,index=cycle_map[c["chamber"],c["index"]],
                pairs=[pair_map[p] for p in c["pairs"]],front=pair_map[c["front"]],counter=counts[chamber],
                start=c["start"]+offset,end=c["end"]+offset))

    def block(path,mode,target,labels):
        data=read(path)
        sources.add(path)
        cycles=[c for c in data["cycles"] if c["mode"]==mode]
        chamber=cycles[0]["chamber"]
        assert all(c["chamber"]==chamber for c in cycles)
        selected={i for c in cycles for i in c["pairs"]}
        products=sorted((w for w in data["jobs"] if w["pair"] in selected and w["product"]),key=lambda w:w["loan_start"])
        assert len(products)==len(labels)
        append_block(data,selected,{w["identity"]:label for w,label in zip(products,labels)},{chamber:target})

    full,mixed=(next(p["wafers"] for p in cfg.pjobs if p["mode"]==mode) for mode in ("4x1","2x2"))
    if (n,h)==(8,3):
        block(chain,"2x2",2,mixed)
        block(chain,"clean",2,[])
        for j,label in enumerate(full):
            block(singleton,"4x1",2+(j//2),[label])
    else:
        for j,label in enumerate(full):
            block(singleton,"4x1",2 if h==3 else 2+j%2,[label])
        if (n,h)==(4,3):
            block(pair,"2x2",3,mixed)
        else:
            for j,label in enumerate(mixed):
                block(singleton,"2x2",3 if h==3 else 2+j%2,[label])
    for group,fields in (("jobs",("loan_start","loan_end","load_start","load_end","unload_start","unload_end")),("cycles",("start","end")),("events",("start","end"))):
        for row in out[group]:
            for f in fields:
                if abs(row[f]-round(row[f]))<2.e-6:
                    row[f]=float(round(row[f]))
    out["cmax"]=max(w["loan_end"] for w in out["jobs"] if w["product"])
    out=normalize_schedule(cfg,out)
    replay=validate(out)
    if not replay["valid"]:
        raise ValueError(replay["errors"][:20])
    checked=cell.lift(cfg,sparse_witness(cfg,out),None,rebuild=True)
    if not checked or not checked[3]["valid"]:
        raise ValueError("Original model rejected composed assignment")
    data,values,_,replay,rows=checked
    f=metrics(data)
    lb=physical_lower(cfg)
    if abs(f["secondary"]-lb)>cell.EPS:
        raise ValueError((f,lb))
    save(dest/"schedule.json",data)
    save(dest/"assignment.json.gz",values)
    save(dest/"primary.json",dict(metrics=f,lower=lb,replay=replay,rows=rows,
        schedule_sha256=sha(dest/"schedule.json"),assignment_sha256=sha(dest/"assignment.json.gz"),
        origins={str(p.relative_to(results)):sha(p) for p in sources},
        construction="serial independent chamber blocks, quota counter checked after each operation"))
    print(name,f,flush=True)


if __name__=="__main__":
    construct(int(sys.argv[1]),int(sys.argv[2]))

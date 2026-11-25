"""Transfer a short H=10 four-wafer optimum to H=3 by a terminal clean on its mixed chamber."""
from dataclasses import asdict
from pathlib import Path
import sys
from solver import cell,HERE,read,save,sha
from score import metrics,physical_lower
sys.path.insert(0,str(cell.BACKENDS["D"]))
sys.path.insert(0,str(HERE.parent/"pareto_rl_dmct_20261119"))
from model import Config
from seed import normalize_schedule
from validate import validate
from witness import sparse_witness


def transfer():
    root=HERE.parents[1]/"results";home=root/"huber_residence_20261125"
    cfgpath=root/"table4_one_percent_20261124/inputs/D_n4_H3_mixed_dual/input.json"
    cfg=Config(**read(cfgpath)["config"])
    source=home/"witnesses_tight/D_n4_H10_mixed_dual/schedule.json"
    clean=root/"residence_objective_20261125/best_reuse/n8_H3/retained_product_times/schedule.json"
    data=read(source); cleaning=read(clean)
    out=dict(config=asdict(cfg),schema=1,solutions=1,pairs=[],jobs=[],events=[],cycles=[])
    counts={c:0 for c in cfg.chambers};cycle_indices={c:0 for c in cfg.chambers}
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

    append_block(data,{p["id"] for p in data["pairs"]},{},{2:2,3:3})
    rec=next(c for c in cleaning["cycles"] if c["mode"]=="clean")
    ch=next(c["chamber"] for c in data["cycles"] if c["mode"]=="2x2")
    append_block(cleaning,set(rec["pairs"]),{},{rec["chamber"]:ch})
    out["cmax"]=max(w["loan_end"] for w in out["jobs"] if w["product"])
    out=normalize_schedule(cfg,out);check=validate(out)
    if not check["valid"]:raise ValueError(check["errors"][:4])
    checked=cell.lift(cfg,sparse_witness(cfg,out),None,rebuild=True)
    assert checked
    d,values,_,replay,rows=checked
    f=metrics(d);assert abs(f["secondary"]-physical_lower(cfg))<1e-7
    dest=home/"witnesses_transferred/D_n4_H3_mixed_dual"
    save(dest/"schedule.json",d);save(dest/"assignment.json.gz",values)
    save(dest/"primary.json",dict(metrics=f,lower=physical_lower(cfg),rows=rows,replay=replay,
        origins={str(p.relative_to(root)):sha(p) for p in (cfgpath,source,clean)},code_sha256=sha(Path(__file__)),
        schedule_sha256=sha(dest/"schedule.json"),assignment_sha256=sha(dest/"assignment.json.gz")))
    print(f)
transfer()

"""Construct an eight-product global B witness from two verified four-product schedules."""
from dataclasses import asdict
from pathlib import Path
import sys

from solver import HERE, cell, read, save, sha
from score import metrics, physical_lower

sys.path.insert(0, str(cell.BACKENDS["D"]))
sys.path.insert(0, str(HERE.parent / "pareto_rl_dmct_20261119"))
from model import Config
from seed import normalize_schedule
from validate import validate
from witness import sparse_witness


def compose(h, dest):
    results = HERE.parents[1]/"results"
    config_path = results/f"table4_one_percent_20261124/inputs/D_n8_H{h}_mixed_dual/input.json"
    template_path = results/"four_gap_ablation_20261123/runs/s2_projection/0p01pct/B/runs/endpoint/schedule.json"
    clean_path = results/"table4_one_percent_20261124/inputs/D_n8_H3_mixed_dual/A/schedule.json"
    cfg = Config(**read(config_path)["config"])
    template, old_clean = read(template_path),read(clean_path)
    if not validate(template)["valid"] or abs(metrics(template)["secondary"]-3.5)>cell.EPS:
        raise ValueError("Unexpected four-product template")
    out = dict(config=asdict(cfg),schema=1,solutions=1,pairs=[],jobs=[],events=[],cycles=[])
    counts = {c:0 for c in cfg.chambers}
    cycle_indices = {c:0 for c in cfg.chambers}
    spare = max(cfg.upper_reset,cfg.lower_reset,cfg.vtr_travel,cfg.atr_travel)
    parents = [config_path, template_path]

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

    for i in (0,1):
        labels={f"LP{j+1}_W1": f"LP{2*i+j%2+1}_W{1+j//2}" for j in range(4)}
        mapping={2:2,3:3} if i==0 else {2:3,3:2}
        append_block(template,{p["id"] for p in template["pairs"]},labels,mapping)
    if h==3:
        parents.append(clean_path)
        for chamber in cfg.chambers:
            c=next(c for c in old_clean["cycles"] if c["mode"]=="clean" and c["chamber"]==chamber)
            append_block(old_clean,set(c["pairs"]),{},{2:2,3:3})
    out["cmax"]=max(j["loan_end"] for j in out["jobs"] if j["product"])
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
         origins={str(p.relative_to(results)):sha(p) for p in parents},
         construction="two four-product blocks with complementary chamber assignments and required terminal cleans"))
    print(h,f,flush=True)


if __name__=="__main__":
    compose(int(sys.argv[1]),Path(sys.argv[2]))

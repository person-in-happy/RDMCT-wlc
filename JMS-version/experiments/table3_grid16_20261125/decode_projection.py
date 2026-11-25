"""Assign anonymous projection products to input wafer IDs as a native search hint."""
import argparse
import json
from collections import defaultdict
from pathlib import Path


def decode(projection,source):
    v=json.loads(projection.read_bytes())
    cfg=json.loads(source.read_bytes())["config"]
    keys=sorted(int(k.split("_")[1]) for k in v if k.startswith("kind_"))
    kinds={g:{1:"4x1",2:"2x2"}[v[f"kind_{g}"]] for g in keys if v[f"kind_{g}"]}
    roles={i:kinds[keys[v[f"batch_{i}"]]] for i in range(16)}
    ids={}
    for pjob in cfg["pjobs"]:
        labeled="port_0" in v
        order=sorted((i for i in roles if roles[i]==pjob["mode"]),
                     key=lambda i:(v[f"port_{i}"],v[f"origin_pick_{i}"],v[f"al_{i}"]) if labeled else v[f"al_{i}"])
        assert len(order)==len(pjob["wafers"])
        ids.update(zip(order,pjob["wafers"]))
    groups=defaultdict(list)
    times={}
    names={"al":"al_put","ap":"al_pick","up":"upper_put","sp":"source_pick","ld":"load",
           "ul":"unload","dp":"destination_put","lp":"lower_pick"}
    for i,name in ids.items():
        g=keys[v[f"batch_{i}"]]
        groups[g,v[f"front_{i}"]].append(name)
        times[name]={st:v[f"{short}_{i}"] for short,st in names.items()}
        if f"origin_pick_{i}" in v:
            assert int(name.split("_")[0][2:])==v[f"port_{i}"]+1
            times[name].update(origin_pick=v[f"origin_pick_{i}"],origin_put=v[f"origin_put_{i}"])
    cycles={}
    for c in (0,1):
        chamber=[]
        pending=None
        for g,k in kinds.items():
            if g//10!=c:
                continue
            if k=="4x1":
                if pending is not None:
                    chamber.append(dict(mode="2x2",back=pending,front=[],first_start_hint=None))
                    pending=None
                back,front=groups[g,0],groups[g,1]
            else:
                back,front=pending or [],groups[g,1]
                pending=front
            chamber.append(dict(mode=k,back=back,front=front,first_start_hint=v[f"start_{g}"]))
        if pending is not None:
            chamber.append(dict(mode="2x2",back=pending,front=[],first_start_hint=None))
        cycles[c+2]=chamber
    return dict(cycles=cycles,product_event_hints=times,relaxed_makespan=v.get("true_C",v["C"]),
                mapping=("Use projected origin LP and origin-pick order within each recipe." if labeled else
                         "Within each recipe, map first aligner access order to the input Pjob order."))


if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("projection",type=Path)
    p.add_argument("source",type=Path)
    a=p.parse_args()
    path=a.projection.parent/"native_hint.json"
    doc=decode(a.projection,a.source)
    path.write_text(json.dumps(doc,indent=2),encoding="utf8")
    print(doc["cycles"])

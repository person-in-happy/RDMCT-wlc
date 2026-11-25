"""Convert an audited native schedule to a product-chamber and timing hint."""
from pathlib import Path
import argparse
import json
import itertools
from campaign import OUT,read,save,sha


def export(source,destination,sequence):
    doc=read(source)
    pairs={p["id"]:p for p in doc["pairs"]}
    cycles={}
    for c,rows in itertools.groupby(sorted(doc["cycles"],key=lambda q:(q["chamber"],q["index"])),key=lambda q:q["chamber"]):
        part=[]
        for q in rows:
            assert q["mode"]!="clean"
            front=q["front"];back=next(p for p in q["pairs"] if p!=front)
            choose=lambda p:[w for w in pairs[p]["members"] if w.startswith("LP")]
            part.append(dict(mode=q["mode"],front=choose(front),back=choose(back),first_start_hint=q["start"]))
        cycles[str(c)]=part
    jobs={j["name"]:j for j in doc["jobs"] if j["product"]}
    events={j["identity"]:dict(load=j["load_start"],unload=j["unload_start"]) for j in jobs.values()}
    for e in doc["events"]:
        j=e.get("job")
        if j in jobs:events[jobs[j]["identity"]][e["kind"]]=e["start"]
    if sequence:
        order=[]
        for p in sequence:
            recipe=doc["config"]["pjobs"][p//4]
            order.extend(recipe["wafers"][2*(p%4):2*(p%4)+2])
        assert set(order)==set(events)
        for kind in ("al_put","al_pick"):
            old=sorted(e[kind] for e in events.values())
            for w,t in zip(order,old):events[w][kind]=t
    save(destination,dict(cycles=cycles,product_event_hints=events,source=str(source),sha256=sha(source),
                          intended_aligner_order=sequence or "unchanged"))


if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("source",type=Path);p.add_argument("destination",type=Path);p.add_argument("sequence",nargs="?",default="")
    args=p.parse_args()
    args.destination.parent.mkdir(exist_ok=True,parents=True)
    export(args.source,args.destination,[int(k) for k in args.sequence])

"""Recheck the same-instance archive, recompute event scores, and retain the joint nondominated coordinates."""
import csv
import os
from collections import Counter
from pathlib import Path
from native_caps import JMS,SQ,OUT,fixed
from support import read,write,digest

def table(path):
    with path.open(encoding="utf-8-sig",newline="") as stream:return list(csv.DictReader(stream))


def emit(path,rows):
    tmp=path.with_suffix(f".{os.getpid()}.tmp")
    with tmp.open("w",encoding="utf-8-sig",newline="") as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    tmp.replace(path)


def pareto(rows):
    ids={}
    for p in rows:
        k=(round(p["fa"],4),round(p["fb"],4))
        if k not in ids or p["fa"]<ids[k]["fa"]:ids[k]=p
    best=float("inf");res=[]
    for k,r in sorted(ids.items()):
        if k[1]<best:
            res.append(r);best=k[1]
    return res


def main():
    config=read(JMS/"results/table3_mixed16_20261125/input.json")["config"]
    prev=read(SQ/"validation.json");assert digest(SQ/"all_observations.csv")==prev["archive_sha256"]
    entries=[]
    for old in table(SQ/"all_observations.csv"):
        entries.append((JMS/old["schedule"],old["sha256"],"baseline",int(old["rows"]),old["origin"]))
    for group in ("fixed","native","neighbors","curves"):
        for path in sorted((OUT/group).glob("*/*/result.json")):
            r=read(path)
            if r.get("files"):
                origin="interpolated" if group=="curves" else "new"
                entries.append((path.parent/"schedule.json",r["files"]["schedule.json"],origin,r["original_rows"],group+"/"+path.parent.parent.name))
    rows=[]
    for path,h,origin,native,how in entries:
        assert digest(path)==h and native>0
        doc=read(path);assert doc["config"]==config
        m=fixed.metrics(doc);z=fixed.sweep.validate(doc)
        assert z["valid"] and abs(m["cmax"]-z["product_return_cmax"])<1e-5
        assert abs(m["secondary"]-(m["mean_residence"]+.5*m["residence_range"]**2+m["clean_deficit"]))<1e-8
        c=m["cmax"];b=m["secondary"];t=c-810
        certified=810-1e-7<=c<=811+1e-7 and abs(b-7.625+.125*t-.5*(30-t)**2)<3e-5
        rows.append(dict(fa=c,fb=b,mean_r=m["mean_residence"],D=m["residence_range"],E=m["clean_deficit"],
                         origin=origin,method=how,scope="certified" if certified else "feasible_sample",
                         model_checked=True,physical_valid=True,original_rows=native,replay_checks=z["checks"],
                         schedule=path.relative_to(JMS).as_posix(),schedule_sha256=h))
    solved=[r for r in rows if r["origin"]!="interpolated"]
    emit(OUT/"optimization_observations.csv",solved)
    frontier=pareto(rows);original=pareto([r for r in rows if r["origin"]=="baseline"])
    keys=lambda rr:{(round(r["fa"],4),round(r["fb"],4)) for r in rr}
    emit(OUT/"observations_union.csv",rows)
    emit(OUT/"frontier_union.csv",[dict(p,scope="certified" if p["scope"]=="certified" else "archive_nondominated") for p in frontier])
    keys_old=keys(original);keys_new=keys(frontier)
    data=dict(instance_config_sha256=digest(JMS/"results/table3_mixed16_20261125/input.json"),
              observations=len(rows),original_observations=sum(r["origin"]=="baseline" for r in rows),
              new_observations=sum(r["origin"]=="new" for r in rows),interpolated_observations=len(rows)-len(solved),
              optimization_observations=len(solved),optimization_front_coordinates=len(pareto(solved)),distinct_coordinates=len(keys(rows)),
              union_nondominated=len(frontier),old_front=len(original),new_front_coordinates=sorted(keys_new-keys_old),
              retired_baseline_coordinates=sorted(keys_old-keys_new),certified_interval=[810,811],
              all_hash=digest(OUT/"observations_union.csv"),front_hash=digest(OUT/"frontier_union.csv"))
    groups={}
    all_caps=set()
    for group,pattern in (("fixed","*/*/result.json"),("neighbors","*/*/result.json"),("search","*/result.json")):
        tasks=[read(f) for f in (OUT/group).glob(pattern)]
        elapsed_key={"fixed":"wall_seconds","neighbors":"seconds_used","search":"used"}[group]
        caps={r["cap"] for r in tasks}
        groups[group]=dict(cells=len(tasks),different_caps=len(caps),sum_cell_wall_seconds=sum(r[elapsed_key] for r in tasks),
                           statuses=dict(Counter(r["status"] for r in tasks)))
        all_caps.update(caps)
    data.update(search_cells=groups,total_search_cells=sum(q["cells"] for q in groups.values()),different_caps=len(all_caps))
    validation=OUT/"curves/families.json"
    if validation.exists():
        data["family_certificate_sha256"]=digest(validation)
    replay=read(OUT/"search_replay.json")
    data["projected_replay"]=dict(distinct_valid_coordinates=replay["unique_valid_coordinates"],rejected=len(replay["rejected"]))
    write(OUT/"validation.json",data);print(data,flush=True)


if __name__=="__main__":main()

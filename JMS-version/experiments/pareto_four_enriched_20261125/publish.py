"""Independently score decoded events and identify per-configuration sample nondominance."""
from collections import defaultdict
import csv
from pathlib import Path
from probe import OUT,JMS,sweep,fixed

def write(path,rows):
    tmp=path.with_suffix(".tmp")
    with tmp.open("w",encoding="utf-8-sig",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    tmp.replace(path)

def check(p,doc):
    ds=defaultdict(int);g=defaultdict(list);unused=0;cfg=doc["config"]
    for ch in cfg["chambers"]:
        count=0
        for c in sorted((c for c in doc["cycles"] if c["chamber"]==ch),key=lambda c:c["index"]):
            if c["mode"]=="clean":
                unused+=cfg["cleaning_interval"]-count;count=0
            else:
                count+=1
                for j in c["pairs"]:ds[j]+=c["end"]-c["start"]
    groups={ta["id"]:ta["mode"] for ta in cfg["pjobs"]};jobs=[w for w in doc["jobs"] if w["product"]]
    assert len(jobs)==4
    for w in jobs:g[groups[w["pjob"]]].append(w["unload_start"]-w["load_end"]-ds[w["pair"]])
    D=max(max(r)-min(r) for r in g.values());avg=sum(map(sum,g.values()))/4
    fa=max(w["loan_end"] for w in jobs);fb=avg+D**2/2+unused
    return dict(schedule=p.relative_to(JMS).as_posix(),schedule_sha256=sweep.sha(p),fa=fa,fb=fb,
                mean_residence=avg,residence_range=D,E=unused)

def main():
    rows=defaultdict(list)
    dirs={"cells/*/*/cap_*/result.json":lambda p:p.parents[2].name,"long/*/*/result.json":lambda p:"double_only",
          "partitions/*/result.json":lambda p:"double_only","historical/*/result.json":lambda p:"double_only",
          "continuation/*/cap_*/result.json":lambda p:"double_only","certified_tail/*/result.json":lambda p:"double_only",
          "alternate/*/result.json":lambda p:"double_only","mid_continuation/*/cap_*/result.json":lambda p:"double_only",
          "certified_middle/*/result.json":lambda p:"double_only","certified_short/*/result.json":lambda p:"double_only",
          "original_mixed_long/H*/cap_*/result.json":lambda p:("separated" if p.parent.parent.name=="H10" else "separated_H3")}
    for pattern,case in dirs.items():
        for f in sorted(OUT.glob(pattern)):
            rec=sweep.read(f)
            if "metrics" not in rec:continue
            d=f.parent/"schedule.json"
            assert rec["files"]["schedule.json"]==sweep.sha(d)
            doc=sweep.read(d);r=check(d,doc)
            assert abs(r["fa"]-rec["metrics"]["cmax"])<1e-4 and abs(r["fb"]-rec["metrics"]["secondary"])<1e-4
            assert rec.get("original_rows",0)>0
            if "replay" in rec:assert rec["replay"]["valid"]
            else:assert rec["checks"]>0
            r["cell"]=f.relative_to(JMS).as_posix();r["original_rows"]=rec["original_rows"]
            rows[case(f)].append(r)
    summary={}
    for case,allrows in rows.items():
        best=float("inf");front=[]
        seen={}
        for r in allrows:
            key=(round(r["fa"],4),round(r["fb"],5))
            if key not in seen or any(x in r["schedule"] for x in ("/certified_tail/","/certified_middle/","/certified_short/")):seen[key]=r
        for (fa,fb),r in sorted(seen.items()):
            if fb<best-1e-5:best=fb;front.append(r)
        name="pure4" if case=="double_only" else case
        write(OUT/(name+"_observations.csv"),allrows)
        write(OUT/(name+"_sample_front.csv"),front)
        summary[case]=dict(checked=len(allrows),points=[(r["fa"],r["fb"]) for r in front])
    sweep.atomic(OUT/"summary.json",summary)
    plan={}
    for slug in sorted((OUT/"cells").iterdir()):
        if not slug.is_dir():continue
        names=sorted(slug.glob("*/cap_*/result.json"))
        if slug.name=="double_only":
            names+=sorted(OUT.glob("continuation/*/cap_*/result.json"))+sorted(OUT.glob("mid_continuation/*/cap_*/result.json"))
            names+=sorted(OUT.glob("long/*/*/result.json"))
        if slug.name=="separated":names+=sorted(OUT.glob("original_mixed_long/H10/cap_*/result.json"))
        zs=[sweep.read(f) for f in names]
        caps=sorted(set(z["cap"] for z in zs))
        plan[slug.name]=dict(unique_caps=caps,distinct_caps=len(caps),distinct_caps_over_417=sum(c>417 for c in caps),calls=len(zs),feasible=sum("metrics" in z for z in zs),max_cap=max(caps))
    caps3=[sweep.read(f) for f in OUT.glob("original_mixed_long/H3/cap_*/result.json")]
    plan["separated_H3_loose"]=dict(unique_caps=sorted(z["cap"] for z in caps3),calls=len(caps3),actual_returns=[z["metrics"]["cmax"] for z in caps3],
                                    objective_values=[z["metrics"]["secondary"] for z in caps3])
    sweep.atomic(OUT/"sweep_summary.json",plan)
    print({k:(v["checked"],len(v["points"])) for k,v in summary.items()},flush=True)

if __name__=="__main__":main()

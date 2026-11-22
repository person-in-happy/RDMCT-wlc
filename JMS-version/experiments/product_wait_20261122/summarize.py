"""Aggregate checked product-only endpoints under the original paired comparison rules."""
import csv
from itertools import product
from statistics import mean
from run import OUT, R, MATCH, PRIMARY, COMP, PROJ, TUNING, LEVELS, ROOT, read, save, sha
from design import pick


def main():
    names=("cmax","wait_sum","wait_max","rhythm","rhythm_centers","secondary")
    records={}
    by_attempt=[]
    retry_folders = sorted((OUT/"joint_retries").glob("joint__*"))
    for base in (OUT,OUT/"original_controls",*retry_folders):
        for file in sorted((base/"runs").glob("*/result.json")):
            k=file.parent.name
            e=read(file)
            assert e["replay"]["valid"] and e["original_rows"]>0
            for name,h in e["files"].items():
                assert sha(file.parent/name)==h
            t=e["job"]
            if sha(ROOT/t["schedule"])!=t["schedule_sha256"] or sha(ROOT/t["assignment"])!=t["assignment_sha256"]:
                raise ValueError("Changed original handoff: "+k)
            score=e["measured"]
            assert abs(score["secondary"]-score["wait_sum"]-10*score["wait_max"]-25*score["rhythm"])<2e-4
            e["source_record"]=file.relative_to(ROOT).as_posix()
            by_attempt.append({"job":k,"source":e["source_record"],"eligible":e["eligible"],
                               **e["record"],**score})
            if k not in records or (e["eligible"] and not records[k]["eligible"]):
                records[k]=e
    def avg(rows):
        if not rows:return None
        return {n:mean(r[n] for r in rows) for n in names}
    totals={}
    grid={}
    for c,a,b in product(TUNING,LEVELS,LEVELS):
        k=f"grid__{c}__{a}__{b}"
        if k in records:
            e=records[k]
            assert e["eligible"]
            grid[c,a,b]={"metrics":e["measured"]}
    choice=pick(grid)
    totals["selected"]=choice
    if choice:
        a,b=choice
        components={}
        for case in TUNING:
            methods={}
            for arm in ("full","no_spbs","hem_spbs","feature_only","no_rerank","greedy"):
                k=f"grid__{case}__{a}__{b}" if arm=="full" else f"component__{case}__{arm}__{b}"
                if k not in records:continue
                e=records[k]
                parent=read((ROOT/e["job"]["assignment"]).parent/"evidence.json")
                if not parent["gate"]["accepted"] or parent["threshold"]!=LEVELS[a]:raise ValueError(k)
                methods[arm]=dict(metrics=e["measured"],initial=e["initial"],gap_B=e["record"]["gap"],
                                 seconds_A=parent["record"]["seconds"],seconds_B=e["record"]["seconds"],
                                 status=e["record"]["status"])
            components[case]=methods
        totals["components"]=components
    matched={}
    for case in ("E_n4_H10_mixed_dual","E_n8_H10_mixed_dual","D_n16_4x1","E_n16_2x2"):
        small=case.startswith(("E_n4","E_n8"))
        arms=("A","B","AB") if small else ("full","plain_full","default","hem_spbs","no_rerank","greedy","feature_only","cp")
        groups={}
        for seed in (1,2,3):
            keys=[f"matched__{case}__s{seed}__{arm}" for arm in arms]
            if not all(k in records and records[k]["eligible"] for k in keys):continue
            orig=[read(MATCH/k.split("__",1)[1]/"result.json") for k in keys]
            assert len({s["input_sha256"] for s in orig})==1
            if not small:
                assert len({s["stages"][0]["schedule_sha256"] for s in orig if s["arm"]!="plain_full"})==1
            groups[seed]={arm:records[k] for arm,k in zip(arms,keys)}
        matched[case]=dict(seeds=list(groups),arms={arm:avg([g[arm]["measured"] for g in groups.values()]) for arm in arms},
                           starts={arm:avg([g[arm]["initial"] for g in groups.values()]) for arm in arms})
    totals["matched"]=matched
    def fixed_groups(prefix):
        keys=sorted({k.rsplit("__s",1)[0] for k in records if k.startswith(prefix+"__")})
        groups={}
        for name in keys:
            rows=[(s,records.get(f"{name}__s{s}")) for s in (1,2,3)]
            rows=[(s,e) for s,e in rows if e and e["eligible"]]
            groups[name]=dict(seeds=[s for s,e in rows],initial=avg([e["initial"] for s,e in rows]),
                             final=avg([e["measured"] for s,e in rows]),
                             wait_reductions=[e["initial"]["wait_sum"]-e["measured"]["wait_sum"] for s,e in rows])
        return groups
    totals["refinement"]=fixed_groups("refine")
    totals["projected"]=fixed_groups("projected")
    joint={}
    for case in ("D_n4_mixed_H10","D_n16_4x1","E_n16_2x2"):
        joint[case]={}
        for rho in (.01,.1,1):
            pairs=[]
            for seed in (1,2,3):
                p=records.get(f"projected__{case}__s{seed}");j=records.get(f"joint__{case}__s{seed}__{rho:g}")
                if p and j and p["eligible"] and j["eligible"]:
                    parent=read((ROOT/p["job"]["assignment"]).parent/"evidence.json")
                    assert parent["input_sha256"]==j["job"]["assignment_sha256"]
                    pairs.append((seed,p["measured"],j["measured"]))
            joint[case][str(rho)]=dict(seeds=[s for s,_,_ in pairs],two=avg([p for _,p,_ in pairs]),joint=avg([j for _,_,j in pairs]))
    totals["joint"]=joint
    rhythm={}
    for prefix in ("original_rhythm","rhythm__E_n16_2x2"):
        arrays=[]
        for seed in (1,2,3):
            rows=[records.get(f"{prefix}__s{seed}__{w}") for w in (0,5,25,100)]
            if all(e and e["eligible"] for e in rows):
                assert len({e["job"]["assignment_sha256"] for e in rows})==1
                arrays.append((seed,rows))
        rhythm[prefix]=dict(seeds=[s for s,_ in arrays],weights={str(w):avg([row[i]["measured"] for _,row in arrays])
                           for i,w in enumerate((0,5,25,100))})
    totals["rhythm"]=rhythm
    save(OUT/"comparisons.json",totals)
    with (OUT/"corrected_results.csv").open("w",newline="",encoding="utf-8-sig") as stream:
        fields=list(dict.fromkeys(k for row in by_attempt for k in row))
        writer=csv.DictWriter(stream,fieldnames=fields); writer.writeheader(); writer.writerows(by_attempt)
    print(len(records),"cells;",len(by_attempt),"attempts;",choice,flush=True)


if __name__=="__main__":
    main()

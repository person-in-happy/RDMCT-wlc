"""Recompute manuscript values from physical schedules without importing the solver or its scorer."""
import argparse
import csv
import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path
from statistics import mean

JMS = Path(__file__).resolve().parents[2]
OUT = JMS / "results/quota_objective_20261125"
MANUSCRIPT = JMS / "revisions/20261125_quota_objective/含末段余额的对照稿.tex"


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def csv_rows(path):
    with path.open(encoding="utf-8-sig",newline="") as stream:
        return list(csv.DictReader(stream))


def independent(schedule, closed=False):
    cfg=schedule["config"]
    cycles=defaultdict(list)
    for item in schedule["cycles"]:
        for pair in item["pairs"]:
            cycles[pair].append(item["mode"])
    products=[w for w in schedule["jobs"] if w["product"]]
    assert len(products)==sum(sum(p.values()) for p in cfg["load_ports"].values())
    all_r=[]
    per_mode=defaultdict(list)
    for wafer in products:
        exposures=cycles[wafer["pair"]]
        assert exposures in (["4x1"],["2x2","2x2"])
        duration=sum(cfg["full_time"] if mode=="4x1" else cfg["mix_time"] for mode in exposures)
        r=wafer["unload_start"]-wafer["load_end"]-duration
        assert r>=-2e-4
        all_r.append(max(r,0))
        per_mode[exposures[0]].append(max(r,0))
    quota=0
    clean_deficit=0
    total_cleans=0
    total_prod=0
    for chamber in cfg["chambers"]:
        events=[c for c in schedule["cycles"] if c["chamber"]==chamber]
        # Add the remainder at each actual clean and at the physical end of the batch.
        counter=0
        for event in sorted(events,key=lambda e:e["index"]):
            if event["mode"]=="clean":
                quota+=cfg["cleaning_interval"]-counter
                clean_deficit+=cfg["cleaning_interval"]-counter
                counter=0
                total_cleans+=1
            else:
                counter+=1
                total_prod+=1
            assert 0<=counter<=cfg["cleaning_interval"]
        quota+=cfg["cleaning_interval"]-counter
    spread=max(max(x)-min(x) for x in per_mode.values())
    return dict(cmax=max(w["loan_end"] for w in products),mean_residence=mean(all_r),
                residence_range=spread,quota_unused=quota,clean_deficit=clean_deficit,clean_count=total_cleans,
                production_count=total_prod,secondary=mean(all_r)+(spread+clean_deficit if closed else quota))


def check_fields(computed,row,mapping,epsilon=2e-4):
    for source,dest in mapping.items():
        difference=abs(float(row[dest])-computed[source])
        if difference>epsilon:
            raise ValueError((source,dest,row[dest],computed[source]))


def table_lines(tex,label):
    start=tex.index(r"\label{"+label+"}")
    end=tex.index(r"\bottomrule",start)
    return [line.split(r"\\")[0].split("&") for line in tex[start:end].splitlines()
            if "&" in line and r"\\" in line and r"\midrule" not in line.split(r"\\")[0]
            and "$f_A$" not in line and r"\multicolumn" not in line]


def check_values(values,expected,precision=.00501):
    assert len(values)==len(expected),(values,expected)
    for a,b in zip(values,expected):
        assert abs(float(a)-float(b))<precision,(values,expected)


def main(partial,closed=False,*,extra_grid=(),extra_cases=(),display_cases=None,with_hit_column=True,validation_path=None):
    tex=MANUSCRIPT.read_text(encoding="utf8")
    t4=csv_rows(OUT/"table4_seeds.csv")
    assert len(t4)==len({(r["seed"],r["arm"],r["level"],r["n"],r["H"]) for r in t4})==81
    for row in t4:
        path=JMS/row["source"]
        schedule=path/"schedule.json" if path.is_dir() else path.parent/"B/schedule.json"
        score=independent(read(schedule),closed)
        check_fields(score,row,{k:k for k in score if k in row})
    reps=csv_rows(OUT/("free_B_shortest_verified.csv" if closed else "reuse/free_B_representatives.csv"))
    assert len(reps)==5
    for row in reps:
        path=(JMS if closed else JMS.parent)/row["source"]
        assert hashlib.sha256(path.read_bytes()).hexdigest()==row["schedule_sha256" if closed else "source_sha256"]
        if closed:
            score=independent(read(path),True)
            check_fields(score,row,{k:k for k in score if k in row})
            row.update(instance=f"D_n{row['n']}_H{row['H']}_mixed_dual",C_at_min_B_best_verified=row["cmax"],fB=row["secondary"])
        else:
            check_fields(independent(read(path)),row,dict(cmax="C_at_min_B_best_verified",secondary="fB",
                         quota_unused="U",residence_range="D",mean_residence="mean",clean_count="K",production_count="P"))
    primary={(int(r["n"]),int(r["H"]),r["arm"]):r for r in csv_rows(OUT/"table4_means.csv") if r["level"]=="1"}
    grid=csv_rows(OUT/"supplement/threshold_cells.csv")+list(extra_grid)
    struct=csv_rows(OUT/"supplement/structure_cells.csv")
    assert (len(grid),len(struct))==(54+9*len(extra_cases),9)
    for row in grid+struct:
        schedule_path=JMS/row["schedule_path"] if row.get("schedule_path") else OUT/"supplement"/row["source"]/"schedule.json"
        score=independent(read(schedule_path),closed)
        fields=dict(cmax="f_A",secondary="f_B",quota_unused="quota",residence_range="spread",
                    mean_residence="mean",clean_count="cleans",production_count="production",clean_deficit="clean_deficit")
        check_fields(score,row,{k:v for k,v in fields.items() if v in row})
    cells={(r["case"],r["gA"],r["gB"]):r for r in grid}
    cases=("D_n2_4x1_scenario1","D_n2_pure_2x2","D_n2_mixed_scenario3","pure","D_n4_pure_2x2","mixed",*extra_cases)
    levels=("10pct","1pct","0p01pct")
    lines=table_lines(tex,"tab:certified-grid-cn")
    lines=[line for line in lines if len(line)==7 and re.fullmatch(r"[\d.]+",line[2].strip())]
    assert len(cells)==9*len(cases)
    visible=cases if display_cases is None else display_cases
    assert len(lines)==3*len(visible)
    for i,line in enumerate(lines):
        case,ga=visible[i//3],levels[i%3]
        rows=[cells[case,ga,gb] for gb in levels]
        check_values([line[2]],[("10","1","0.01")[i%3]])
        check_values([line[-4]]*3,[r["f_A"] for r in rows])
        check_values(line[-4:],[rows[0]["f_A"]]+[r["f_B"] for r in rows])
    t4_lines=table_lines(tex,"tab:matched-objectives-cn")
    t4_lines=[line for line in t4_lines if line[0].strip().isdigit()]
    assert len(t4_lines)==5
    for line,row in zip(t4_lines,reps):
        n,h=map(int,line[:2])
        assert row["instance"]==f"D_n{n}_H{h}_mixed_dual"
        a,ab=primary[n,h,"A"],primary[n,h,"AB"]
        check_values(line[2:],[a["cmax"],a["secondary"],row["C_at_min_B_best_verified"],row["fB"],ab["cmax"],ab["secondary"]])
    t5=csv_rows(OUT/"table5_seeds.csv")
    assert len(t5)==len({(r["seed"],r["arm"]) for r in t5})
    references={r["seed"]:r for r in t5 if r["arm"]=="full"}
    assert len(references)==3
    for row in t5:
        root=(JMS/row["source"]).parent
        ref=references[row["seed"]]
        endpoint=root/("B/schedule.json" if row["arm"]=="full" else "endpoint/schedule.json")
        m=independent(read(endpoint),closed)
        check_fields(m,row,dict(cmax="f_A",secondary="f_B"))
        if row["arm"]!="full":
            reached=m["cmax"]<=float(ref["f_A"])+2e-4 and m["secondary"]<=float(ref["f_B"])+2e-4
            assert reached==(row["reason"]=="target")
            if not reached: check_values([row["observed_s"]],[ref["observed_s"]],.001)
    if not partial:
        assert len(t5)==15
        lines=table_lines(tex,"tab:mixed-ablation-cn")
        offset=2 if with_hit_column else 1
        lines=[line for line in lines if len(line)==offset+4 and re.fullmatch(r"\d+(\.\d+)?",line[offset].strip())]
        assert len(lines)==5
        for line,arm in zip(lines,("full","no_rerank","no_spbs","hem","scip_default")):
            records=[r for r in t5 if r["arm"]==arm]
            assert len(records)==3
            if with_hit_column and arm!="full": assert line[1].strip()==f"{sum(r['reason']=='target' for r in records)}/3"
            check_values(line[offset:],[mean(float(r[k]) for r in records) for k in ("f_A","f_B","observed_s","calls")])
    result=dict(threshold_cells=len(grid),printed_threshold_cells=9*len(visible),structure_cells=len(struct),table4_seed_cells=len(t4),
                table4_shorter_witnesses=len(reps),table5_seed_runs=len(t5),
                final_table5_compared=not partial,source_sha256=hashlib.sha256(MANUSCRIPT.read_bytes()).hexdigest())
    print(json.dumps(result))
    if not partial:
        (validation_path or OUT/"manuscript_validation.json").write_text(json.dumps(result,indent=2),encoding="utf8")


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--partial",action="store_true")
    main(parser.parse_args().partial)

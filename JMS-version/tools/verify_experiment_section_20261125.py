"""Check the published threshold, objective, ablation and schedule figures against physical events."""
import csv
from hashlib import sha256
import itertools
import json
from pathlib import Path
from statistics import mean, stdev
import sys

JMS = Path(__file__).resolve().parents[1]
RESULTS = JMS / "results"
HUBER = RESULTS / "huber_residence_20261125"
FRONT = RESULTS / "pareto_scales_20261125"
EXTENDED = RESULTS / "table4_extended16_20261125"
sys.path.insert(0, str(JMS / "experiments/table3_grid16_20261125"))
from verify_table import CASES, g, new_cells
from table_rows import render


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def records(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def close(left, right, tol=0.00002):
    assert abs(float(left)-float(right)) <= tol, (left, right, tol)


def scored(path, expected=None):
    actual = g.independent(read(path))
    if expected:
        for key in ("cmax","secondary","mean_residence","residence_range","clean_deficit","huber_penalty"):
            if key in expected:
                close(actual[key],expected[key])
    return actual


def compare_thresholds(tex):
    grid = g.get_grid() | new_cells()
    assert set(grid) == set(itertools.product(CASES,g.LEVELS,g.LEVELS))
    copy = render(grid)
    assert copy.strip() in tex
    for case, ga in itertools.product(CASES, g.LEVELS):
        assert len({grid[case,ga,gb]["primary_schedule_sha256"] for gb in g.LEVELS}) == 1
    _, choice, tradeoffs = g.summarize(grid,CASES)
    return dict(cells=len(grid),selected=choice,tradeoffs=tradeoffs)


def compare_single_objectives(tex):
    seeds = records(HUBER/"table4_seeds.csv")
    families = {}
    for row in seeds:
        source = JMS/row["source"]
        path = source/"schedule.json" if source.is_dir() else source.parent/"B/schedule.json"
        s = scored(path,row)
        if row["level"]=="1" and row["arm"] in ("A","AB"):
            key = int(row["n"]),int(row["H"]),row["arm"]
            families.setdefault(key,[]).append((s["cmax"],s["secondary"]))
    representatives = {}
    for row in records(HUBER/"free_B_shortest_verified.csv"):
        n,h = int(row["n"]),int(row["H"])
        path = (FRONT/f"four_native_H{h}/417_pinned/schedule.json" if n==4 else JMS/row["source"])
        if n==4:
            meta=read(path.parent/"result.json")
            assert meta["replay"]["valid"] and meta["files"]["schedule.json"]==digest(path)
        else:
            assert digest(path)==row["schedule_sha256"]
        s=scored(path)
        close(s["secondary"],row["B_lower"])
        representatives[n,h]=(s["cmax"],s["secondary"])
    for h in (3,10):
        directory = EXTENDED/f"H{h}"
        for seed,arm in itertools.product((1,2,3),("A","AB")):
            info = read(directory/f"s{seed}/{arm}.json")
            path = JMS/info["source"]/"schedule.json"
            if arm=="A":
                assert info["schedule_sha256"]==digest(path)
                assert info["lower_sha256"]==digest(JMS/info["lower_source"])
            else:
                cert = JMS/info["certificate"]
                assert info["certificate_sha256"]==digest(cert)
                parent = read(directory/f"s{seed}/A.json")
                assert read(cert)["parents"][0]["schedule_sha256"]==parent["schedule_sha256"]
            assert info["upper"]-info["lower"]<=.01*info["lower"]+2e-5
            s=scored(path,info["metrics"])
            families.setdefault((16,h,arm),[]).append((s["cmax"],s["secondary"]))
        scores=[]
        for filename in directory.rglob("schedule.json"):
            report = filename.parent/"result.json"
            if not report.exists():
                continue
            cert = read(report)
            if cert.get("H")!=h or "upper" not in cert or "lower" not in cert or "metrics" not in cert:
                continue
            bmin = 3.451171875 if h==3 else 3.404296875
            if abs(cert["lower"]-bmin)>1e-6 or abs(cert["upper"]-bmin)>1e-6:
                continue
            assert cert["schedule_sha256"]==digest(filename)
            assert cert["rows"]>0 and cert["replay"]["valid"]
            s=scored(filename,cert["metrics"])
            scores.append((s["cmax"],s["secondary"]))
        assert scores
        representatives[16,h]=min(scores)
    published=read(EXTENDED/"publication.json")
    for r in published["records"]:
        for name in ("certificate","schedule","assignment"):
            path=JMS/r["certificate" if name=="certificate" else name+"_path"]
            assert r[name+"_sha256"]==digest(path)
        scored(JMS/r["schedule_path"],r["physical_metrics"])
    lines=[row for row in g.audit.table_lines(tex,"tab:matched-objectives-cn") if row[0].strip().isdigit()]
    assert len(lines)==len(representatives)==7
    for row in lines:
        n,h=map(int,row[:2])
        a,b=families[n,h,"A"],families[n,h,"AB"]
        assert len(a)==len(b)==3
        numbers=[*map(mean,zip(*a)),*representatives[n,h],*map(mean,zip(*b))]
        for printed,actual in zip(row[2:],numbers,strict=True):
            close(printed,actual,0.00501)
    return dict(rows=len(lines),new_stage_records=12)


def compare_ablation(tex):
    arms=("full","no_rerank","no_spbs","hem","scip_default")
    source=records(HUBER/"table5_seeds.csv")
    assert len(source)==len({(r["seed"],r["arm"]) for r in source})==15
    for r in source:
        folder=(JMS/r["source"]).parent
        position="B" if r["arm"]=="full" else "endpoint"
        s = scored(folder/position/"schedule.json")
        close(r["f_A"],s["cmax"])
        close(r["f_B"],s["secondary"])
        own=next(q for q in source if q["arm"]=="full" and q["seed"]==r["seed"])
        close(own["observed_s"],r["observed_s"])
        if r["arm"]!="full":
            hit=(s["cmax"]<=float(own["f_A"])+.0002 and s["secondary"]<=float(own["f_B"])+.0002)
            assert (r["reason"]=="target")==hit
    lines=[r for r in g.audit.table_lines(tex,"tab:mixed-ablation-cn") if len(r)==5 and r[1].strip().startswith("$")]
    assert len(lines)==5
    for arm,row in zip(arms,lines,strict=True):
        group=[r for r in source if r["arm"]==arm]
        for col,k in ((1,"f_A"),(2,"f_B")):
            sample=[float(r[k]) for r in group]
            a,b=row[col].strip(" $").split(r"\pm")
            close(a,mean(sample),.00501)
            close(b,stdev(sample),.00501)
        close(row[3],mean(float(r["used_s"]) for r in group),.00501)
        close(row[4],mean(float(r["calls"]) for r in group),.00501)
    return len(source)


def compare_figures(tex):
    gantt=JMS/"figures/huber_gantt_20261125"
    charts=[]
    for r in read(gantt/"manifest.json"):
        source = JMS/r["source"]
        path=gantt/r["chart"]
        assert r["chart_sha256"]==digest(path) and r["source_sha256"]==digest(source)
        assert path.relative_to(JMS).as_posix() in tex
        s=scored(source,r)
        schedule=read(source)
        releases=[e["end"] for e in schedule["events"]]
        for e in schedule["events"]:
            if e["kind"]=="lower_pick":
                releases.append(e["end"]+schedule["config"]["lower_reset"])
            if e["kind"]=="source_pick" and e.get("job","").startswith("LP"):
                releases.append(e["end"]+schedule["config"]["upper_reset"])
        close(r["equipment_end"],max(releases))
        charts.append((r["chart"],s["cmax"],s["secondary"]))
    assert len(charts)==3
    front=read(FRONT/"validation.json")
    assert Path(front["figure"]).name in tex
    assert front["figure_sha256"]==digest(JMS/front["figure"])
    assert front["eight_sha256"]==digest(JMS/front["eight_proof"])
    assert (FRONT/front["four_proof"]).is_file()
    for endpoints in front["four_endpoints"].values():
        for row in endpoints:
            path=JMS/row["schedule"]
            assert digest(path)==row["sha256"]
            scored(path,row)
    proof_dir=FRONT/"cap810"
    catalogue=read(proof_dir/"catalogue.json")
    assert catalogue["total"]==35 and len(catalogue["excluded"])==33
    for path,expected in catalogue["excluded"].values():
        assert digest(JMS/path)==expected
    assert read(proof_dir/"p0009.json")["status"]=="INFEASIBLE"
    support=read(proof_dir/"p0020.json")
    assert support["status"]=="OPTIMAL" and support["lower16"]==594
    solution=scored(proof_dir/"p0020_native/schedule.json")
    close(solution["cmax"],810)
    close(solution["secondary"],support["lower16"]/16)
    segment=read(FRONT/"continuous16/certificate.json")
    assert segment["interval"]==[810,811]
    for cap,ev in segment["evidence"].items():
        endpoint=scored(FRONT/f"continuous16/endpoint{cap}/schedule.json",ev["metrics"])
        close(endpoint["secondary"],37.125-1.125*(int(cap)-810))
        for stem,expected in ev["audited_results"].items():
            assert digest(FRONT/f"cap{cap}/{stem}.json")==expected
    at812=FRONT/"cap812"
    inherited=read(at812/"catalogue.json")
    for path,expected in inherited["excluded"].values():
        assert digest(JMS/path)==expected
    cases={str(i):read(at812/f"p{i:04}.json") for i in inherited["remaining"]}
    assert {k for k,v in cases.items() if v["status"]=="OPTIMAL"}=={"20","26"}
    assert cases["20"]["lower16"]/16==31.75
    assert read(at812/"support_1_2/result.json")["lower"]>=22.3125
    jump=scored(at812/"p0026_native/schedule.json")
    close(jump["cmax"],812)
    assert jump["secondary"]<=23.25+1.e-6
    points=records(FRONT/"all_observations.csv")
    plotted=records(FRONT/"sixteen_pareto.csv")
    for r in points:
        path=JMS/r["schedule"]
        assert r["sha256"]==digest(path)
        scored(path,r)
    def coords(r):return tuple(round(float(r[k]),4) for k in ("cmax","secondary"))
    candidates=set(map(coords,points))
    assert {x for x in candidates if not any(y!=x and all(a<=b for a,b in zip(y,x)) for y in candidates)}==set(map(coords,plotted))
    assert len(plotted)==front["sixteen_pareto_points"]
    return dict(gantts=charts,frontier_figure_sha256=front["figure_sha256"],
                certified_16_interval=segment["interval"],sampled_nondominated_16_points=len(plotted))


def main():
    source=JMS/"JMS_Review_CN.tex"
    tex=source.read_text(encoding="utf8")
    results=dict(threshold=compare_thresholds(tex),table4=compare_single_objectives(tex),
                 table5_runs=compare_ablation(tex),figures=compare_figures(tex),
                 source_sha256=digest(source),pdf_sha256=digest(JMS/"JMS_Review_CN.pdf"))
    target=JMS/"revisions/20261125_experiment_section/validation.json"
    target.write_text(json.dumps(results,indent=2)+"\n",encoding="utf8")
    print(json.dumps(results,indent=2))


if __name__=="__main__":
    main()

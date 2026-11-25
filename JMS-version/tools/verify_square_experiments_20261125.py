"""Cross-check square-objective tables, source figures, native witnesses and final manuscript."""
import csv
from collections import defaultdict
from functools import lru_cache
from hashlib import sha256
import itertools
import json
from math import sqrt
from pathlib import Path
import re
from statistics import mean, stdev
import sys

JMS = Path(__file__).resolve().parents[1]
RESULTS = JMS / "results"
GRID = RESULTS / "square_grid_20261125"
TABLE4 = RESULTS / "square_table4_20261125"
BASE = RESULTS / "square_residence_20261125"
FRONT = RESULTS / "pareto_square_20261125"
sys.path.insert(0,str(JMS/"experiments/table3_grid16_20261125"))
from verify_table import CASES, g

def read(p):
    return json.loads(p.read_text(encoding="utf-8-sig"))

def records(p):
    with p.open(encoding="utf-8-sig",newline="") as stream:
        return list(csv.DictReader(stream))

def digest(p):
    return sha256(p.read_bytes()).hexdigest()

def close(x,y,atol=2e-5):
    assert abs(float(x)-float(y))<=atol,(x,y)

@lru_cache(maxsize=None)
def physical(p):
    v=g.independent(read(p))
    return v["cmax"],v["mean_residence"],v["residence_range"],v["clean_deficit"],v["mean_residence"]+0.5*v["residence_range"]**2+v["clean_deficit"]

def check_grid(tex):
    raw=records(GRID/"threshold_cells.csv")
    entries={}
    for r in raw:
        key=(r["case"],r["gA"],r["gB"])
        assert key not in entries
        folder=JMS/r["cell"]
        cert=read(folder)
        p=JMS/r["schedule_path"]
        assert digest(p)==r["schedule_sha256"]==cert["schedule_sha256"]
        c,m,d,e,fb=physical(p)
        for x,y in ((c,r["f_A"]),(fb,r["f_B"]),(m,r["mean"]),(d,r["spread"]),(e,r["clean_deficit"])):
            close(x,y)
        assert float(r["A_gap"])<=g.LEVELS[key[1]]+2e-6 and float(r["B_gap"])<=g.LEVELS[key[2]]+2e-6
        close(cert["B_lower"],r["B_lower"])
        assert fb>=float(r["B_lower"])-2e-5 and cert["config"]["A_sha256"]==r["primary_schedule_sha256"]
        entries[key]=dict(f_A=c,f_B=fb)
    assert set(entries)==set(itertools.product(CASES,g.LEVELS,g.LEVELS))
    lines=[x for x in g.audit.table_lines(tex,"tab:certified-grid-cn") if len(x)==7 and x[2].strip() in ("10","1","0.01")]
    assert len(lines)==36
    for row,(case,ga) in zip(lines,itertools.product(CASES,g.LEVELS),strict=True):
        levels=[entries[case,ga,b] for b in g.LEVELS]
        for x,y in zip(row[3:],[levels[0]["f_A"],*(k["f_B"] for k in levels)],strict=True):
            close(x,y,0.00052)
    rank,choice,rises=g.summarize(entries,CASES)
    assert f"{choice['f_B']:.6f}" in tex
    return dict(cells=len(entries),selection=choice,rises=rises)

def check_comparisons(tex):
    data=read(TABLE4/"publication.json")
    cases=defaultdict(list)
    for r in data["records"]:
        for file,hash_field in (("schedule_path","schedule_sha256"),("assignment_path","assignment_sha256"),("certificate","certificate_sha256")):
            assert digest(JMS/r[file])==r[hash_field]
        c,m,d,e,b=physical(JMS/r["schedule_path"])
        for x,y in zip((c,m,d,e,b),(r["f_A"],r["mean"],r["spread"],r["E"],r["f_B"]),strict=True):
            close(x,y)
        assert r["native_rows"]>0
        if r["arm"]=="B":close(b,r["analytic_lower"])
        else:
            value=c if r["arm"]=="A" else b
            assert value-r["lower"]<=.01*r["lower"]+.0002
        cases[r["n"],r["H"],r["arm"]].append((c,b))
    lines=[r for r in g.audit.table_lines(tex,"tab:matched-objectives-cn") if r[0].strip().isdigit()]
    assert len(lines)==7 and len(data["records"])==49
    for r in lines:
        n,h=map(int,r[:2]); expected=[]
        for arm in ("A","B","AB"):
            v=cases[n,h,arm]
            assert len(v)==(1 if arm=="B" else 3)
            expected.extend(map(mean,zip(*v)))
        for x,y in zip(r[2:],expected,strict=True):
            close(x,y,0.00052)
    return data["counts"]

def check_ablation(tex):
    rows=records(BASE/"table5/table5_seeds.csv")
    assert len(rows)==len(set((r["seed"],r["arm"]) for r in rows))==15
    for r in rows:
        path=JMS/r["source"]/"schedule.json"
        assert digest(path)==r["schedule_sha256"]
        c,m,d,e,b=physical(path)
        close(c,r["f_A"]);close(b,r["f_B"])
    lines=[r for r in g.audit.table_lines(tex,"tab:mixed-ablation-cn") if len(r)==5 and r[1].strip().startswith("$")]
    assert len(lines)==5
    for line,arm in zip(lines,("full","no_rerank","no_spbs","hem","scip_default"),strict=True):
        samples=[r for r in rows if r["arm"]==arm]
        assert len(samples)==3
        for col,key in [(1,"f_A"),(2,"f_B")]:
            a,b=line[col].strip(" $").split(r"\pm")
            v=[float(r[key]) for r in samples]
            close(a,mean(v),.00501);close(b,stdev(v),.00501)
        for col,key in ((3,"used_s"),(4,"cut_rounds")):
            close(line[col],mean(float(r[key]) for r in samples),.00501)
    structure=records(GRID/"structure_cells.csv")
    assert len(structure)==9
    for r in structure:
        s=JMS/r["schedule"]; assert r["schedule_sha256"]==digest(s)
        c,m,d,e,b=physical(s);close(c,r["f_A"]);close(b,r["f_B"])
    return dict(paired=15,structure_cells=9)

def check_extended_frontier(tex):
    folder = RESULTS/"pareto_publication_20261125"
    summary = read(folder/"validation.json")
    figure = JMS/summary["figure"]
    assert figure.name in tex and digest(figure) == summary["figure_sha256"]
    for filename, sig in summary["source_hashes"].items():
        assert digest(JMS/filename) == sig
    for filename, sig in summary["outputs"].items():
        assert digest(folder/filename) == sig
    pure_certificate = RESULTS/"pareto_four_enriched_20261125/pure4_certificate.json"
    pure = read(pure_certificate)
    assert digest(pure_certificate) == summary["pure4_certificate_sha256"]
    assert pure["interval"] == [491, 491.25] and pure["earliest_minimum"] == 491.25
    for cert, knots, base, j in [(pure["branch_408"],"verified_knots",409,1),
                                  (pure["branch_425"],"knots",426,2),(pure,"knots",492,3)]:
        for filename, sig in cert["source_hashes"].items():
            assert digest(JMS/filename) == sig
        for knot in cert[knots]:
            row = read(JMS/knot["result"])
            d = base-knot["cap"]
            close(row["metrics"]["secondary"], 7-j*d/4+d*d/2)
            assert row["replay"]["valid"] and row["original_rows"] == pure["native_rows"]
    curves = read(folder/"displayed_curves.json")
    assert curves["isolated_observations_drawn"]==0
    for filename, sig in curves["source_hashes"].items():
        assert digest(JMS/filename)==sig
    arcs = {r["label"]:r for r in curves["curves"]}
    assert len(arcs)==9 and len(curves["curves"])==9
    for name, item in zip(("4p_408","4p_425","4p_491"),pure["complete_front"]["arcs"],strict=True):
        q=arcs[name]
        assert [q["low"],q["high"]] == item["interval"] and (q["left_open"],q["right_open"])==(item["left_open"],item["right_open"])
    for name,c,b in (("16m_873",874.25,3.4296875),("16m_986",987.125,3.404296875)):
        q=arcs[name]
        assert q["scope"]=="archive" and q["left_open"] and not q["right_open"]
        close(q["high"],c);close(q["high_score"],b)
        close(q["low_score"], b+(c-q["low"])**2/8)
    middle = read(RESULTS/"pareto_enriched_20261125/curves/families.json")["families"]["middle"]
    tail = read(RESULTS/"square_reverse16_20261125/continuous/proof.json")
    assert middle["support"]["min_C_plus_2D"] == [875,875]
    assert tail["support"]["min_C_plus_2D_lower"] == tail["support"]["upper"] == 988
    for end in tail["endpoints"]:
        assert digest(JMS/end["assignment"]) == end["assignment_sha256"]
    assert all(r["all_original_rows_verified"] and r["physical_replay_checks"]>0 for r in tail["samples"])
    tol = summary["dominance_tolerance"]
    assert tol == 1e-5 and summary["certificate_sha256"] == digest(FRONT/"certificate.json")
    archive = records(folder/"sample_union.csv")
    for group in ("pure4", "mixed16"):
        group_rows = [r for r in archive if r["group"] == group]
        vectors = []
        for row in group_rows:
            path = JMS/row["schedule"]
            assert digest(path) == row["sha256"]
            c,m,d,e,b = physical(path)
            for field,num in (("fA",c),("fB",b),("mean_residence",m),("residence_range",d),("unused_cycles",e)):
                close(row[field],num)
            vectors.append((c,b))
        front = records(folder/(group+"_front.csv"))
        assert len(front) == summary[group]["nondominated"]
        selected = []
        for row in front:
            c,b = float(row["fA"]),float(row["fB"])
            p = JMS/row["schedule"]
            assert int(row["model_rows"]) == (108396 if group == "pure4" else 1109436)
            assert int(row["physical_checks"]) > 0 and digest(p.with_name("assignment.json.gz")) == row["assignment_sha256"]
            assert (c,b) in vectors and all(not (a<=c+tol and z<=b+tol and
                (a<c-tol or z<b-tol)) for a,z in vectors)
            selected.append((c,b))
        assert all(any(a <= c+tol and z <= b+tol for a,z in selected) for c,b in vectors)
    return {"chart":summary["figure"], "sha256":summary["figure_sha256"], "sample_counts":
            {g:summary[g]["nondominated"] for g in ("pure4","mixed16")}, "above_811":summary["mixed16"]["above_811"]}

def check_figures(tex):
    figdir=JMS/"figures/square_gantt_20261125"
    gs=[]
    for row in read(figdir/"manifest.json"):
        p=JMS/row["source"];chart=figdir/row["chart"]
        assert digest(p)==row["source_sha256"] and digest(chart)==row["chart_sha256"]
        assert digest(JMS/row["certificate"])==row["certificate_sha256"]
        assert chart.relative_to(JMS).as_posix() in tex
        c,_,_,_,b=physical(p);close(c,row["cmax"]);close(b,row["secondary"])
        schedule=read(p)
        end=[e["end"] for e in schedule["events"]]
        for e in schedule["events"]:
            if e["kind"]=="lower_pick":
                end.append(e["end"]+schedule["config"]["lower_reset"])
            if e["kind"]=="source_pick" and e.get("job","").startswith("LP"):
                end.append(e["end"]+schedule["config"]["upper_reset"])
        close(max(end),row["equipment_end"])
        gs.append([row["n"],c,b,max(end)])
    assert [k[0] for k in gs]==[4,16,75]
    gap_dir = GRID/"gantt75_gap"
    timings = read(gap_dir/"original_events.json")
    earliest = read(gap_dir/"absolute_event_bounds.json")
    assert earliest["failed"] == 0
    for rel, value in earliest["signature"].items():
        assert digest(JMS/rel) == value
    for chamber, row in timings.items():
        sequence = row["first"], row["second"]
        assert all(cycle["mode"] == "4x1" for cycle in sequence)
        assert sequence[0]["index"] + 1 == sequence[1]["index"]
        start = sequence[1]["start"]
        close(start-sequence[0]["end"], row["gap"])
        close(earliest["results"][chamber]["minimum"], start)
        close(row["pump_complete"]-row["upper_load_end"], 30)
        close(row["last_vtr_load"][1], start)
        assert all(abs(k["actual"][0]-k["earliest"])<1e-6 for k in earliest["results"][chamber]["last_wafer_route"])
        printed = start if chamber == "3" else row["gap"]
        assert f"{printed}~s" in tex
    close(read(gap_dir/"cmax_physical.json")["objective"], gs[-1][1])
    f=read(FRONT/"certificate.json")
    assert f["four_complete"].keys()=={"3","10"}
    for rows in f["four_complete"].values():
        points = [(r["metrics"]["cmax"],r["metrics"]["secondary"]) for r in rows]
        assert points==[(397.,3.5),(417.,3.46875)]
    s=f["eight"]
    assert s["H10_complete_front"] and s["H3_complete_front"] and s["left_open"]
    assert f["sixteen"]["interval"][:2]==[810,811]
    checked=read(FRONT/"validation.json")
    for file,field in (("certificate.json","proof_sha256"),("all_observations.csv","archive_sha256"),
                       ("sixteen_pareto.csv","observed_frontier_sha256"),("search_design.csv","grid_sha256")):
        assert checked[field]==digest(FRONT/file)
    assert checked["figure_sha256"]==digest(JMS/checked["figure"])
    timeline=set(checked["sixteen_pure_C_caps"])
    added=set(checked["sixteen_caps_additional_to_prior_16_sweep"])
    assert len(timeline)==51 and len(added)==44 and added<=timeline
    assert len(checked["sixteen_D_levels"])==8
    close(checked["left_to_812_drop_at_least"],158.6875)
    close(f["sixteen"]["cap812_squared_lower_by_pattern"]["20"]-checked["real_bound_at812"][1],158.6875)
    close(s["tail_interval"][0],577-(3+sqrt(5))/8)
    close(s["tail_interval"][1],576.625)
    observations=records(FRONT/"all_observations.csv")
    front=records(FRONT/"sixteen_pareto.csv")
    def coordinates(row):
        return tuple(round(float(row[k]),4) for k in ("cmax","secondary"))
    for row in observations:
        p=JMS/row["schedule"]
        assert digest(p)==row["sha256"] and int(row["rows"])>0 and int(row["checks"])>0
        c,m,d,e,b=physical(p)
        for key,val in zip(("cmax","mean_residence","residence_range","clean_deficit","secondary"),(c,m,d,e,b),strict=True):
            close(row[key],val,.0002)
    pool=set(map(coordinates,observations))
    nondominated={a for a in pool if not any(b!=a and b[0]<=a[0] and b[1]<=a[1] for b in pool)}
    assert len(pool)==110 and len(nondominated)==18 and nondominated==set(map(coordinates,front))
    for row in front:
        if row["scope"]=="certified_continuous_curve":
            t=float(row["cmax"])-810
            assert -1e-6<=t<=1+1e-6
            close(row["secondary"],7.625-.125*t+.5*(30-t)**2,.0001)
    displayed_dir = RESULTS/"pareto_certified_20261125"
    displayed = read(displayed_dir/"validation.json")
    chart = JMS/displayed["figure"]
    assert chart.name not in tex and Path(checked["figure"]).name not in tex
    assert digest(chart) == displayed["figure_sha256"]
    assert displayed["certificate_sha256"] == digest(FRONT/"certificate.json")
    sets = displayed["displayed_sets"]
    assert sets["n4_H3_H10"]["points"] == checked["four_global_points"]
    for key in ("n8_H3", "n8_H10"):
        assert sets[key]["closed_interval"] == s["short_interval"]
    assert sets["n8_H10"]["left_open_right_closed"] == s["tail_interval"]
    exact = sets["n16_H10"]
    assert exact["closed_interval"] == f["sixteen"]["interval"]
    close(exact["maximum_distance_below_secant_in_secondary_units"], .125)
    for c, b in exact["endpoints"]:
        u = c - 810
        close(b, 457.625 - 30.125*u + .5*u*u)
    decisions_path = displayed_dir/"archive_decisions.csv"
    assert digest(decisions_path) == displayed["archive_decisions_sha256"]
    decisions = records(decisions_path)
    shown = {coordinates(r) for r in decisions if r["lies_on_displayed_set"] == "True"}
    assert shown == {coordinates(r) for r in front if r["scope"]=="certified_continuous_curve"}
    assert len(decisions)==len(observations)
    assert displayed["n16_archive"]["unqualified_samples_drawn"]==0
    assert displayed["n16_archive"]["excluded_archive_nondominated_coordinates"] == len(nondominated-shown)
    enriched=check_extended_frontier(tex)
    return dict(gantt=gs,displayed_frontier_sha256=enriched["sha256"],extended_frontier=enriched,
                frontier_certificate_sha256=digest(FRONT/"certificate.json"),
                sixteen_caps=len(timeline),new_caps=len(added),archive_nondominated=len(nondominated),
                certified_samples=checked["independently_solved_points_on_certified_16_curve"])

def main():
    path=JMS/"JMS_Review_CN.tex";tex=path.read_text(encoding="utf8")
    for stale in ("曝光", "暴露时长", "空心点为所得排程", r"\appendix",r"\ref{app:frontier",r"\rho_\delta(", "Huber", "huber_"):
        assert stale not in tex,stale
    summary=dict(table3=check_grid(tex),table4=check_comparisons(tex),table5=check_ablation(tex),figures=check_figures(tex))
    chart=next(q for q in re.findall(r"\\includegraphics\[[^]]*\]\{([^}]+)\}",tex) if "pareto" in q)
    matches=[p for p in (JMS/"figures").rglob(Path(chart).name)]
    assert len(matches)==1
    summary.update(frontier_chart=matches[0].relative_to(JMS).as_posix(),frontier_chart_sha256=digest(matches[0]),
                   source_sha256=digest(path),pdf_sha256=digest(JMS/"JMS_Review_CN.pdf"),preferences_sha256=digest(BASE/"sensitivity.json"))
    out=BASE/"manuscript_validation.json"
    out.write_text(json.dumps(summary,indent=2),encoding="utf8")
    print(json.dumps(summary,indent=2))

if __name__=="__main__":
    main()

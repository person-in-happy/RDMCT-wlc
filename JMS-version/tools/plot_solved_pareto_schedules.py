"""Plot selected continuous Pareto branches and directly solved schedule witnesses."""
from hashlib import sha256
import json
from pathlib import Path
import sys

import matplotlib as mpl
mpl.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
import numpy as np

PAPER = Path(__file__).resolve().parents[1]
RESULTS = PAPER / "results"
sys.path.insert(0, str(PAPER / "experiments/pareto_publication_20261125"))
from archive import OUT, read, records
from figure import branch_sets
from verify_square_experiments_20261125 import physical

TOL = 1e-5  # Same coordinate/dominance tolerance as the publication archive.


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def publication_candidates(size):
    group = {4:"pure4",16:"mixed16"}[size]
    frontier = records(OUT / f"{group}_front.csv")
    for r in records(OUT / "sample_union.csv"):
        if r["group"]!=group:
            continue
        a,b = float(r["fA"]),float(r["fB"])
        if any(abs(a-float(f["fA"]))<=TOL and abs(b-float(f["fB"]))<=TOL for f in frontier):
            yield PAPER/r["schedule"],r["sha256"]


def eight_wafer_candidates():
    short = RESULTS / "huber_residence_20261125/reuse/epsilon_summary.csv"
    for r in records(short):
        if r["structure"]=="short" and r["status"]=="optimal":
            p = PAPER.parent/r["record"]
            assert digest(p)==r["sha256"]
            yield p.with_name("schedule.json"),read(p)["files"]["schedule.json"]
    for p in sorted((RESULTS/"pareto_square_20261125/fixed/long8").glob("cap_*/result.json")):
        result = read(p)
        if result.get("status")=="optimal":
            yield p.with_name("schedule.json"),result["files"]["schedule.json"]


def contains_solution(curve,a,b):
    lo,hi = curve["low"],curve["high"]
    if a < lo-TOL or a > hi+TOL:
        return False
    if (curve["left_open"] and a<=lo+TOL) or (curve["right_open"] and a>=hi-TOL):
        return False
    return abs(float(curve["func"](a))-b)<=TOL


def collect_solved_points(groups):
    points = []
    for size,windows in zip((4,8,16),groups,strict=True):
        branches = [c for window in windows for c in window]
        candidates = eight_wafer_candidates() if size==8 else publication_candidates(size)
        for path,expected_hash in candidates:
            record = path.with_name("result.json")
            if not record.is_file():
                continue
            result = read(record)
            if result.get("status")!="optimal":
                continue
            # Constructed schedule families also have physical witnesses. Only
            # mark separate solver records that bind this particular schedule.
            assert result["files"]["schedule.json"] == digest(path) == expected_hash
            a,mean,spread,unused,b = physical(path)
            curve = next((c for c in branches if contains_solution(c,a,b)),None)
            if curve is None:
                continue
            checks = result.get("checks") or result.get("replay", {}).get("checks")
            assert checks and result.get("replay",{}).get("valid", True)
            schedule = read(path)
            threshold = schedule["config"]["cleaning_interval"]
            assert size==sum(sum(port.values()) for port in schedule["config"]["load_ports"].values())
            assert threshold in ((3,10) if curve["label"]=="8m_553" else (10,))
            matching = next((p for p in points if p["size"]==size
                             and abs(p["fA"]-a)<=TOL and abs(p["fB"]-b)<=TOL), None)
            if matching is None:
                matching = {"size":size,"branch":curve["label"],"fA":a,"fB":b,"witnesses":[]}
                points.append(matching)
            if threshold not in [w["H"] for w in matching["witnesses"]]:
                matching["witnesses"].append({"H":threshold,"schedule":path.relative_to(PAPER).as_posix(),
                    "schedule_sha256":expected_hash,"result_sha256":digest(record),"physical_checks":checks,
                    "mean_residence":mean,"residence_range":spread,"unused_cycles":unused})
    return sorted(points,key=lambda p:(p["size"],p["fA"]))


PANELS = (
    ("4p_425", (425.1,425.3,425.5), (6.875,6.92,6.965)),
    ("4p_491", (491,491.125,491.25), (6.72,6.735,6.75)),
    ("8m_553", (553,553.375,553.75), (3.47,3.60,3.75)),
    ("8m_576", (576.35,576.5,576.625), (3.43,3.45,3.47)),
    ("16m_873", (873.55,873.9,874.25), (3.43,3.46,3.49)),
    ("16m_986", (986.7,986.9,987.125), (3.405,3.415,3.425)),
)


def selected_branches():
    groups,proof_hashes = branch_sets(records(OUT/"mixed16_front.csv"))
    declared = read(OUT/"displayed_curves.json")
    assert declared["source_hashes"]==proof_hashes
    records_by_label = {c["label"]:c for c in declared["curves"]}
    curves = {c["label"]:c for row in groups for window in row for c in window}
    selected = []
    for label,_,_ in PANELS:
        curve,known = curves[label],records_by_label[label]
        assert all(curve[k]==known[k] for k in ("low","high","scope","left_open","right_open"))
        selected.append(curve)
    return selected


def plot_solved(target):
    curves = selected_branches()
    groups = [[[c] for c in curves[i:i+2]] for i in (0,2,4)]
    points = collect_solved_points(groups)
    counts = [[sum(p["branch"]==w[0]["label"] for p in points) for w in row] for row in groups]
    report = {"basis":"Distinct objective coordinates from individually solved physical schedules on the six displayed "
              "continuous branches. One witness per cleaning threshold at coincident coordinates. Open endpoints, "
              "dominated points, and schedules produced only by interpolation are excluded from the filled symbols.",
              "coordinates_tolerance":TOL,"marker_count":len(points),"window_counts":counts,
              "panel_branches":[c["label"] for c in curves],
              "source_files":{p.relative_to(PAPER).as_posix():digest(p) for p in (
                OUT/"displayed_curves.json",OUT/"sample_union.csv",OUT/"pure4_front.csv",OUT/"mixed16_front.csv",
                RESULTS/"huber_residence_20261125/reuse/epsilon_summary.csv")},"markers":points}
    assert counts==[[7,5],[5,4],[3,11]]
    draw_panels(target,report,"zh")
    target.with_name("pareto_solved_schedules.json").write_text(json.dumps(report,indent=2)+"\n",encoding="utf8")


def draw_panels(target,report,language):
    curves = selected_branches()
    assert [c["label"] for c in curves]==report["panel_branches"]
    zh = language=="zh"
    front_color,witness_color = "#225b7a","#a43913"
    with mpl.rc_context({"font.family":"sans-serif","font.sans-serif":["Microsoft YaHei" if zh else "Arial"],
                         "pdf.fonttype":42,"axes.linewidth":.58,"axes.unicode_minus":False,"font.size":6.6}):
        fig,axes = plt.subplots(3,2,figsize=(90/25.4,107/25.4))
        fig.subplots_adjust(left=.146,right=.940,top=.910,bottom=.122,wspace=.72,hspace=1.06)
        handles = [Line2D([],[],ls="none",marker="o",mfc=witness_color,mec="white",mew=.32,ms=3.6,
                          label="已求得的排程" if zh else "Solved schedules"),
                   Line2D([],[],ls="none",marker="o",mfc="white",mec=front_color,mew=.75,ms=3.3,
                          label="排除的端点" if zh else "Excluded endpoint")]
        for n,(axis,curve,(_,xt,yt)) in enumerate(zip(axes.flat,curves,PANELS,strict=True)):
            xx = np.linspace(curve["low"],curve["high"],181)
            yy = curve["func"](xx)
            assert np.all(np.diff(yy)<0)
            axis.plot(xx,yy,lw=1.08,ls="-",color=front_color)
            rows = [p for p in report["markers"] if p["branch"]==curve["label"]]
            assert all(contains_solution(curve,p["fA"],p["fB"]) for p in rows)
            axis.plot([p["fA"] for p in rows],[p["fB"] for p in rows],ls="none",marker="o",
                      ms=3.15,mfc=witness_color,mec="white",mew=.32,zorder=3)
            for idx,end in ((0,"left_open"),(-1,"right_open")):
                if curve[end]:
                    axis.plot(xx[idx],yy[idx],ls="none",marker="o",ms=3.25,mfc="white",
                              mec=front_color,mew=.72,zorder=4)
            title = (("4 片，纯 2×2","8 片，混合","16 片，混合") if zh else
                     ("4 wafers, 2×2 only","8 wafers, mixed","16 wafers, mixed"))[n//2]
            threshold = "H = 3, 10" if curve["label"]=="8m_553" else "H = 10"
            axis.set_title(f"({chr(97+n)}) {title}\n{threshold}",loc="left",fontsize=6.75,
                           pad=2.7,linespacing=1.1)
            axis.spines[["top","right"]].set_visible(False)
            axis.grid(axis="y",color="#dce0e3",lw=.45)
            axis.set(xticks=xt,yticks=yt)
            axis.set_xticklabels([f"{t:.3f}".rstrip("0").rstrip(".") for t in xt])
            axis.set_yticklabels([f"{t:.3f}".rstrip("0").rstrip(".") for t in yt])
            axis.tick_params(length=2.1,pad=1.55,labelsize=5.9,width=.5)
            axis.margins(x=.065,y=.095)
            axis.set_xlabel("总加工时间（s）" if zh else "Batch makespan (s)",fontsize=6.4,labelpad=1.3)
            axis.set_ylabel("工艺目标（等效秒）" if zh else "Process objective (equiv. s)",fontsize=6.15,labelpad=1.75)
        fig.legend(handles=handles,loc="lower center",bbox_to_anchor=(.52,.005),ncol=2,fontsize=6.45,
                   frameon=False,handlelength=1.1,columnspacing=1.6,handletextpad=.3,borderaxespad=0)
        fig.savefig(target,metadata={"Title":"Pareto trade-offs and solved schedules","CreationDate":None,"ModDate":None})
        plt.close(fig)



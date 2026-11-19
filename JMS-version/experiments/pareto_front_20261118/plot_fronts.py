"""Render the S1 certified outcome set and the mixed-instance search evidence."""
import csv
import hashlib
import json
from fractions import Fraction
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.ticker import ScalarFormatter

ROOT = Path(__file__).resolve().parents[3]
BASE = ROOT / "JMS-version/results/pareto_front_20261118_r1"
OUT = ROOT / "JMS-version/review/pareto_objectives_20261118"
INK = "#203548"
TEAL = "#00796E"
BLUE = "#345A9D"
ORANGE = "#A55321"
MUTED = "#526678"


def read(path):
    return path.read_text(encoding="utf-8-sig")


def load(path):
    return json.loads(read(path))


def write_csv(name, rows):
    with (OUT / name).open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def label(number):
    return f"{number:.2f}".rstrip("0").rstrip(".")


def prepare_axis(ax):
    ax.set_axisbelow(True)
    ax.grid(axis="y", color="#E0E7EB", linewidth=0.8)
    for side in ["left", "bottom"]:
        ax.spines[side].set_color("#A2B0BA")
        ax.spines[side].set_linewidth(0.8)
    for side in ["top", "right"]:
        ax.spines[side].set_visible(False)
    ax.tick_params(color="#A2B0BA", labelcolor=MUTED, labelsize=10, length=3, pad=5)


def front_s1():
    cert = load(BASE / "n2/independent_r2/validation.json")
    assert cert["all_highs_or_temporal_exclusions"] and len(cert["checks"]) == 17
    points = cert["physical_points"]
    rows = []
    for point in points:
        m = point["metrics"]
        path = ROOT / point["source"]
        assert point["original_model_check"] and hashlib.sha256(path.read_bytes()).hexdigest() == point["sha256"]
        paired = sum(j["product"] for j in load(path)["jobs"] if j["pair"] == 0) == 2
        rows.append(dict(Cmax_s=m["cmax"], B_weighted_s=m["secondary"],
                         B_fraction=str(Fraction(m["secondary"]).limit_denominator(1000)),
                         wait_sum_s=m["wait_sum"], wait_max_s=m["wait_max"], rhythm_s=m["rhythm"],
                         rhythm_centers=m["rhythm_centers"], pairing="PP" if paired else "PD+PD",
                         physical_checks=point["physical_checks"], witness_path=point["source"],
                         witness_sha256=point["sha256"]))
    assert [r["pairing"] for r in rows] == ["PP"] * 3 + ["PD+PD"] * 4
    write_csv("certified_s1_frontier.csv", rows)
    fig, axes = plt.subplots(1, 2, sharey=True, figsize=(10.0, 5.35))
    fig.subplots_adjust(left=.105, right=.969, top=.765, bottom=.216, wspace=.14)
    fig.text(.085,.927,"两片 S1 实例的完整 Pareto 前沿",fontsize=19,weight="bold",color=INK)
    fig.text(.085,.858,"两片 2×2 产品片，同一 Pjob   ·   4 片辅助片   ·   清洁阈值 H = 2",color=MUTED,fontsize=11)
    names = ["两片产品组成一对", "每片产品各与一片辅助片配对"]
    for ax, group, color, marker, name in zip(axes, [rows[:3], rows[3:]], [BLUE, TEAL], ["o", "D"], names):
        prepare_axis(ax)
        ax.set_title(name, loc="left", fontsize=11.5, color=color, pad=12, weight="bold")
        for p in group:
            a,b = p["Cmax_s"],p["B_weighted_s"]
            ax.scatter(a,b,s=78,marker=marker,edgecolor="white",linewidth=1.3,color=color,zorder=4)
            offset = {331:(8,4),334:(7,-16),340:(-4,9),514:(-1,11),516:(-3,-18),517:(8,-1),519:(8,-1)}[int(a)]
            ax.annotate(f"({label(a)}, {label(b)})",(a,b),xytext=offset,textcoords="offset points",
                        ha="right" if a in (340,516) else "left",fontsize=10,color=INK)
    axes[0].set(xlim=(329.5,342), xticks=[330,332,334,336,338,340,342],
                ylim=(34,152), yticks=[40,60,80,100,120,140])
    axes[0].set_ylabel("综合等待与节拍指标  B（加权秒）", fontsize=11.5, labelpad=12)
    axes[1].set(xlim=(512.9,521.0),xticks=[513,514,515,516,517,518,519,520,521])
    axes[1].spines["left"].set_visible(False)
    axes[1].tick_params(axis="y",left=False)
    for ax, x in zip(axes,[1,0]):
        ax.plot([x-.009,x+.009],[-.012,.012],transform=ax.transAxes,color=MUTED,clip_on=False,lw=1.2)
    fig.text(.544,.104,"批次完工时间  Cmax（秒）",ha="center",fontsize=12,color=INK)
    fig.text(.085,.031,"横轴分段显示。340 秒至 514 秒之间没有其他非支配点。两个目标均取最小值。",fontsize=10,color=MUTED)
    fig.savefig(OUT / "certified_s1_frontier_CN.png", dpi=200, facecolor="white")
    plt.close(fig)


def mixed_points():
    out = []
    with (OUT / "observed_points.csv").open(encoding="utf-8-sig", newline="") as stream:
        for row in csv.DictReader(stream):
            if row["case"] == "n4_H10_mixed_dual":
                out.append((float(row["A_s"]), float(row["B_weighted_s"]), "archive", row["representative_evidence"]))
    n4 = BASE / "n4"
    for i, run in enumerate(load(n4 / "slices.json")["slices"]):
        for j, (a,b) in enumerate(run["vertices"]):
            out.append((a,b,"retimed",(n4/f"slice_{i:03}.npz").relative_to(ROOT).as_posix()+f"#vertex={j}"))
    for section, filename in [("probes","probes.json"),("secondary_endpoint","results.json"),("fast_topologies","results.json")]:
        for row in load(n4 / section / filename):
            if "metrics" in row:
                tag = row.get("tag",row.get("topology",""))
                if section == "fast_topologies":
                    tag += "_" + row["goal"]
                src = n4 / section / (tag + "_schedule.json")
                m = row["metrics"]
                out.append((m["cmax"],m["secondary"],"search",src.relative_to(ROOT).as_posix()))
    for row in load(n4 / "endpoint_search/results.json"):
        for item in row["vertices"]:
            m = item["metrics"]
            src = n4 / "endpoint_search" / item["schedule"]
            out.append((m["cmax"],m["secondary"],"search",src.relative_to(ROOT).as_posix()))
    for row in load(n4 / "floor_certificate/results.json"):
        if "metrics" in row:
            m=row["metrics"]
            src=n4/"floor_certificate"/(row["name"]+"_schedule.json")
            out.append((m["cmax"],m["secondary"],"search",src.relative_to(ROOT).as_posix()))
    return out


def verified_segments():
    n4=BASE/"n4"
    first=load(n4/"chain_slice_replay/results.json")[0]
    assert (n4/"chain_slice_replay/chain_orders_variables.npz").is_file()
    vertices=[(p["metrics"]["cmax"], p["metrics"]["secondary"]) for p in first["vertices"]]
    pieces=[(vertices, [(p["metrics"],n4/"chain_slice_replay"/p["schedule"]) for p in first["midpoints"]])]
    for entry in load(n4/"verified_segments/segments.json"):
        directory=n4/"verified_segments"
        assert hashlib.sha256((directory/entry["assignment"]).read_bytes()).hexdigest()==entry["sha256"]
        pieces.append((entry["vertices"],[(p["metrics"],directory/p["file"]) for p in entry["midpoints"]]))
    assert sum(len(vertices)-1 for vertices,_ in pieces)==3
    return pieces


def front_mix():
    raw = mixed_points()
    pieces=verified_segments()
    for vertices,midpoints in pieces:
        assert len(midpoints)==len(vertices)-1
        for m,src in midpoints:
            raw.append((m["cmax"],m["secondary"],"segment_midpoint",src.relative_to(ROOT).as_posix()))
    tol = 2e-5
    # Retain repeated points in the table so each schedule is traceable.
    rows = []
    for a,b,kind,source in raw:
        assert (ROOT/source.split("#")[0]).is_file()
        nd = not any(c<=a+tol and d<=b+tol and (c<a-tol or d<b-tol) for c,d,_,_ in raw)
        rows.append(dict(Cmax_s=a,B_weighted_s=b,evidence=kind,sample_nondominated=nd,source=source))
    write_csv("mixed_feasible_points.csv", rows)
    fig,ax=plt.subplots(figsize=(9.1,5.25))
    fig.subplots_adjust(left=.12,right=.963,top=.728,bottom=.20)
    fig.text(.095,.925,"四片混合实例的可行排程",fontsize=19,weight="bold",color=INK)
    fig.text(.095,.857,"2 片 4×1 产品片与 2 片 2×2 产品片   ·   8 片辅助片   ·   清洁阈值 H = 10",fontsize=11,color=MUTED)
    prepare_axis(ax)
    ax.set_yscale("log")
    ax.minorticks_off()
    ax.set(xlim=(420,553),ylim=(42,2400),yticks=[54,100,200,500,1000,2000])
    ax.yaxis.set_major_formatter(ScalarFormatter())
    ax.set_ylabel("综合等待与节拍指标  B（加权秒）",fontsize=11.5,labelpad=12)
    ax.set_xlabel("批次完工时间  Cmax（秒）",fontsize=11.5,labelpad=9)
    ax.axhline(54,color=ORANGE,ls=(0,(5,4)),lw=1.2)
    for vertices,_ in pieces:
        for (a,b),(c,d) in zip(vertices,vertices[1:]):
            frac=[i/80 for i in range(81)]
            ax.plot([a+(c-a)*t for t in frac],[b+(d-b)*t for t in frac],c=TEAL,lw=1.4,zorder=3)
    seen=set()
    colors={"archive":"#98A5B1","retimed":"#889BAB","search":"#57778A"}
    for row in sorted(rows,key=lambda r:r["sample_nondominated"]):
        a,b=row["Cmax_s"],row["B_weighted_s"]
        key=round(a,4),round(b,4)
        if key in seen:continue
        seen.add(key)
        if row["evidence"]=="segment_midpoint":
            continue
        nd=row["sample_nondominated"]
        ax.scatter(a,b,s=65 if nd else 38,marker="D" if nd else "o",
                   c=TEAL if nd else colors[row["evidence"]],edgecolors="white",linewidths=.7,zorder=4)
        if nd:
            shift={429:(6,6),459:(6,6),476:(5,7),494:(4,12),497:(8,1)}.get(round(a),(5,7))
            ax.annotate(f"({label(a)}, {label(b)})",(a,b),xytext=shift,textcoords="offset points",fontsize=9.4,
                        ha="right" if shift[0]<0 else "left",color=INK)
    handles=[
        Line2D([],[],marker="D",linestyle="none",color=TEAL,label="样本非支配顶点",markersize=6.5),
        Line2D([],[],marker="o",linestyle="none",color="#95A5AF",label="已被支配的排程",markersize=6),
        Line2D([],[],color=TEAL,linewidth=1.4,label="固定离散决策的可行线段"),
        Line2D([],[],color=ORANGE,linewidth=1.2,ls="--",label="全局下界 B = 54")]
    fig.legend(handles=handles,loc="center left",bbox_to_anchor=(.095,.785),ncol=4,
               frameon=False,fontsize=8.8,handlelength=1.65,columnspacing=1.5)
    fig.text(.095,.035,"纵轴采用对数刻度。实线各点均有可行排程，四片实例的完整前沿仍待确定。",fontsize=10,color=MUTED)
    fig.savefig(OUT/"mixed_feasible_points_CN.png",dpi=200,facecolor="white")
    plt.close(fig)


if __name__=="__main__":
    plt.rcParams.update({"font.family":"Microsoft YaHei","axes.unicode_minus":False,
                         "text.color":INK,"axes.labelcolor":INK, "figure.facecolor":"white"})
    front_s1()
    front_mix()

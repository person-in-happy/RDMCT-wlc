"""Publish only the Pareto sets established by the archived cross-structure certificates."""
import csv
import hashlib
import json
import math
from pathlib import Path

import matplotlib as mpl
mpl.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pymupdf

JMS = Path(__file__).resolve().parents[2]
ARCHIVE = JMS / "results" / "pareto_square_20261125"
LEGACY = JMS / "results" / "pareto_scales_20261125"
OUT = JMS / "results" / "pareto_certified_20261125"
FIG = JMS / "figures/rolling_refinement_20261119/fig_pareto_scales_certified_cn.pdf"
BLUE = "#20598a"
ORANGE = "#ad531d"


def read_json(path):
    return json.loads(path.read_bytes())


def read_csv(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def b8_short(t):
    return 3.75 - .75*t + .5*t**2


def b8_long(u):
    return 3.625 - .625*u + .5*u**2


def b16(t):
    return 7.625 - .125*t + .5*(30 - t)**2


def certify_display():
    source = read_json(ARCHIVE/"certificate.json")
    previous = read_json(ARCHIVE/"validation.json")
    for name, key in (("certificate.json", "proof_sha256"), ("all_observations.csv", "archive_sha256"),
                      ("sixteen_pareto.csv", "observed_frontier_sha256")):
        assert sha(ARCHIVE/name) == previous[key]
    assert [source["delta"], source["gamma"]] == [1, 1]
    four = [[397, 3.5], [417, 3.46875]]
    for threshold, records in source["four_complete"].items():
        assert [[r["metrics"]["cmax"], r["metrics"]["secondary"]] for r in records] == four
        for record, stage in zip(records, ("short397", "417_pinned")):
            assert sha(LEGACY/f"four_native_H{threshold}"/stage/"schedule.json") == record["schedule_sha256"]
    assert sha(LEGACY/"four_bound/proof.md") == source["four_source_proof_sha256"]
    eight = source["eight"]
    start = (5-math.sqrt(5))/8
    assert eight["H10_complete_front"] and eight["H3_complete_front"] and eight["left_open"]
    assert eight["short_interval"] == [553, 553.75] and eight["tail_interval"] == [576+start,576.625]
    assert math.isclose(b8_long(start), b8_short(.75)) and math.isclose(b8_long(.625), 3.4296875)
    assert source["eight_short_proof_sha256"] == sha(JMS/"results/huber_residence_20261125/frontier/certificate.json")
    for member in (0, 1):
        result = read_json(ARCHIVE/f"eight_tail/pair{member}/result.json")
        assert result["status"] == "OPTIMAL" and result["bound"] == 570
    for point in eight["native_interpolation"].values():
        m = point["metrics"]
        assert math.isclose(m["secondary"], b8_long(m["cmax"]-576))
    sixteen = source["sixteen"]
    assert sixteen["interval"] == [810, 811] and sixteen["binding_objectives"] == [b16(0), b16(1)]
    assert sha(LEGACY/"continuous16/certificate.json") == sixteen["native_interpolation_sha256"]
    for c in (810, 811):
        source_end = sixteen["supports"][str(c)]
        assert sha(LEGACY/f"cap{c}/p0020.json") == source_end["slope1_source_sha256"]
        assert sha(ARCHIVE/f"support/{c}_20_30_0_0/result.json") == source_end["slope30_source_sha256"]
        assert sha(LEGACY/f"continuous16/endpoint{c}/schedule.json") == source_end["native_schedule_sha256"]
    return four, start, previous


def classify_archive(previous):
    observations = read_csv(ARCHIVE/"all_observations.csv")
    retained = read_csv(ARCHIVE/"sixteen_pareto.csv")
    def key(row):
        return round(float(row["cmax"]), 4), round(float(row["secondary"]), 4)
    keys = {key(row) for row in observations}
    best = {p for p in keys if not any(q != p and q[0] <= p[0] and q[1] <= p[1] for q in keys)}
    assert best == {key(row) for row in retained}
    rows = []
    certified = set()
    for row in observations:
        c, b = key(row)
        assert sha(JMS/row["schedule"]) == row["sha256"]
        on_curve = 810 <= c <= 811 and abs(float(row["secondary"]) - b16(float(row["cmax"])-810)) < 3e-5
        if on_curve:
            assert (c,b) in best
            certified.add((c,b))
            rule = "certified_curve_endpoint" if c in (810,811) else "certified_curve_interior"
        elif (c,b) not in best:
            rule = "dominated_in_verified_archive"
        elif c == 812:
            rule = "cap812_bound_open"
        elif abs(b-3.4043) < .00005:
            rule = "global_minimum_secondary_earliest_attainment_open"
        else:
            rule = "cross_structure_nondominance_open"
        rows.append(dict(cmax=row["cmax"], secondary=row["secondary"], schedule=row["schedule"],
                         schedule_sha256=row["sha256"], archived_nondominated=(c,b) in best,
                         lies_on_displayed_set=on_curve, reason=rule))
    assert len(best) == previous["nondominated_schedule_coordinates"]
    assert len(certified) == previous["independently_solved_points_on_certified_16_curve"]
    with (OUT/"archive_decisions.csv").open("w", newline="", encoding="utf-8-sig") as stream:
        out = csv.DictWriter(stream, fieldnames=list(rows[0]))
        out.writeheader()
        out.writerows(rows)
    return len(observations), len(keys), len(best), len(certified)


def draw(four, start):
    mpl.rcParams.update({"font.sans-serif":["Microsoft YaHei","DejaVu Sans"],"axes.unicode_minus":False,
                         "font.size":8,"axes.linewidth":.65,"pdf.fonttype":42,"mathtext.fontset":"stix",
                         "xtick.labelsize":7.3,"ytick.labelsize":7.3})
    fig = plt.figure(figsize=(7.25, 2.44))
    columns = fig.add_gridspec(1,3, width_ratios=(.85,2.22,1.10),
                               left=.082, right=.979, bottom=.27, top=.78, wspace=.42)
    ax4 = fig.add_subplot(columns[0])
    eight = columns[1].subgridspec(1,2, width_ratios=(1,1),wspace=.52)
    ax8 = fig.add_subplot(eight[0])
    tail = fig.add_subplot(eight[1])
    ax16 = fig.add_subplot(columns[2])
    for axis in (ax4,ax8,tail,ax16):
        axis.spines[["top","right"]].set_visible(False)
        axis.tick_params(length=2.5, width=.65, pad=2)
        axis.grid(axis="y", color="#e4e7e9", linewidth=.4)
    def header(first, last, label):
        center = .5*(first.get_position().x0 + last.get_position().x1)
        fig.text(center,.90,label, fontsize=9.5, ha="center", va="center")
    ax4.set_ylabel(r"工艺目标 $f_B$（等效 s）",labelpad=2)
    ax4.plot(*zip(*four), ls="none", marker="o", ms=3.8, color=BLUE)
    ax4.set(xlim=(393,421), ylim=(3.461,3.509), xticks=[397,417],yticks=[3.47,3.48,3.49,3.50])
    header(ax4,ax4,r"(a) 4 片，$H=3,10$")
    def segment(axis, offset, begin, end, value, color, open_left=False):
        grid = np.linspace(begin,end,161)
        axis.plot(offset+grid,value(grid), lw=1.5, color=color, solid_capstyle="butt")
        axis.plot(offset+begin,value(begin), "o", ms=3.8, mfc="white" if open_left else color,
                  mec=color, mew=.9)
        axis.plot(offset+end,value(end), "o", ms=3.8, color=color)
    segment(ax8,553,0,.75,b8_short,BLUE)
    segment(tail,576,start,.625,b8_long,ORANGE,open_left=True)
    ax8.set(xlim=(552.94,553.81), ylim=(3.44,3.79),xticks=(553,553.75),
            xticklabels=("553","553.75"),yticks=(3.47,3.60,3.75))
    tail.set(xlim=(576.318,576.65),ylim=(3.421,3.474),xticks=(576.35,576.625),
             xticklabels=("576.35","576.625"),yticks=(3.43,3.45,3.47))
    for axis, label, color in ((ax8,r"$H=3,10$",BLUE),(tail,r"$H=10$",ORANGE)):
        axis.text(.93,.90,label,transform=axis.transAxes,ha="right",va="center",fontsize=7.4,color=color)
    header(ax8,tail,"(b) 8 片")
    segment(ax16,810,0,1,b16,BLUE)
    ax16.set(xlim=(809.92,811.08),ylim=(424.8,461.3),xticks=(810,810.5,811),
             xticklabels=("810","810.5","811"),yticks=(428,443,458))
    header(ax16,ax16,r"(c) 16 片，$H=10$")
    fig.text(.525,.085,r"完工时间 $f_A$（s）",fontsize=8.6,ha="center",va="center")
    fig.savefig(FIG, metadata={"Title":"混合工艺算例的 Pareto 前沿","CreationDate":None,"ModDate":None})
    plt.close(fig)
    with pymupdf.open(FIG) as pdf:
        assert len(pdf)==1 and pdf[0].get_drawings()
        pdf[0].get_pixmap(matrix=pymupdf.Matrix(2.3,2.3),alpha=False).save(OUT/"preview.png")


def main():
    OUT.mkdir(exist_ok=True,parents=True)
    four, start, previous = certify_display()
    n, distinct, best, certified = classify_archive(previous)
    draw(four,start)
    data = {
        "figure":str(FIG.relative_to(JMS)).replace(chr(92),"/"),"figure_sha256":sha(FIG),
        "evidence":str(ARCHIVE.relative_to(JMS)).replace(chr(92),"/"),
        "certificate_sha256":previous["proof_sha256"],
        "objectives":{"makespan":"product return", "process":"mean_r + D^2/(2 delta) + gamma E", "delta":1,"gamma":1},
        "displayed_sets":{"n4_H3_H10":{"scope":"complete","points":four},
            "n8_H3":{"scope":"complete","closed_interval":[553,553.75]},
            "n8_H10":{"scope":"complete","closed_interval":[553,553.75],"left_open_right_closed":[576+start,576.625]},
            "n16_H10":{"scope":"certified local Pareto set","closed_interval":[810,811],
                       "endpoints":[[810,b16(0)],[811,b16(1)]],"maximum_distance_below_secant_in_secondary_units":.125}},
        "n16_archive":{"records":n,"unique_coordinates":distinct,"archive_nondominated_coordinates":best,
                       "on_displayed_curve":certified,"excluded_archive_nondominated_coordinates":best-certified,
                       "unqualified_samples_drawn":0},
        "excluded_n16_cap812":{"objective_interval":previous["real_bound_at812"],"gap_in_secondary_units":.75},
        "excluded_n16_global_secondary_minimum":{"value":3.404296875,"shortest_verified_attainment":1446.125,
                                               "earliest_attainment_proven":False},
        "circled_open_boundary":[8,10,576+start,3.46875],
        "archive_decisions_sha256":sha(OUT/"archive_decisions.csv"),"export_code_sha256":sha(Path(__file__))}
    (OUT/"validation.json").write_text(json.dumps(data,indent=2,ensure_ascii=False),encoding="utf-8")
    print(json.dumps(data["n16_archive"]),data["figure_sha256"])


if __name__ == "__main__":
    main()

"""Rebuild the corrected topology labels and the single-column Pareto panels."""

from pathlib import Path
import json
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import FixedLocator, FuncFormatter
import numpy as np
import pymupdf

PAPER = Path(__file__).resolve().parents[1]
OUTPUT = PAPER / "figures/axes_20261126"
TOPOLOGIES = ("fig_system_pjob_cn.pdf", "fig_single_source_pjob_cn.pdf")
PANELS = (
    ("a", 4, "2×2", "10", (("4p_408",), ("4p_425",)), (6.88, 6.94, 7)),
    ("b", 4, "2×2", "10", (("4p_491",),), (6.72, 6.735, 6.75)),
    ("c", 8, "mixed", "3,10", (("8m_553",),), (3.48, 3.61, 3.74)),
    ("d", 8, "mixed", "10", (("8m_576",),), (3.43, 3.45, 3.47)),
    ("e", 16, "mixed", "10", (("16m_810", "16m_811"),), (400, 428, 456)),
    ("f", 16, "mixed", "10", (("16m_873",), ("16m_986",)), (3.405, 3.45, 3.49)),
)
TICKS = {
    "4p_408": (408.5, 408.7), "4p_425": (425.1, 425.5),
    "4p_491": (491, 491.12, 491.25),
    "8m_553": (553, 553.38, 553.75), "8m_576": (576.35, 576.49, 576.62),
    "16m_810": (810, 811, 812), "16m_873": (873.6, 874.2), "16m_986": (986.7, 987.1),
}
COLORS = {"exact": "#16597a", "archive": "#a14a21"}


def correct_aligner(source):
    """Center the label in the aligner module at the left end of the ATR rail."""
    with pymupdf.open(source) as doc:
        page = doc[0]
        box, = [path["rect"] for path in page.get_drawings()
                if path["type"] == "fs" and path["fill"] == (1, 1, 1)
                and 24 < path["rect"].x0 < 26 and 103 < path["rect"].y0 < 105
                and 25 < path["rect"].width < 28]
        old, = [s for b in page.get_text("dict")["blocks"] for l in b.get("lines", [])
                for s in l["spans"] if s["text"] == "AL"]
        font = pymupdf.Font("helv")
        size = old["size"]
        page.add_redact_annot(pymupdf.Rect(old["bbox"]), fill=None)
        page.apply_redactions(images=0, graphics=0)
        center_x, center_y = (box.x0 + box.x1)/2, (box.y0 + box.y1)/2
        width = font.text_length("AL", fontsize=size)
        # Cap-height centering keeps the short uppercase label optically centered.
        y = center_y + 0.5 * font.glyph_bbox(ord("A")).height * size
        page.insert_text((center_x - width/2, y), "AL", fontsize=size, fontname="helv",
                         color=pymupdf.sRGB_to_pdf(old["color"]))
        assert len(page.search_for("AL")) == 1 and box.contains(page.search_for("AL")[0]), source
        doc.save(OUTPUT / source.name, garbage=4, deflate=True, no_new_id=True)


def checked_curves():
    sys.path.insert(0, str(PAPER / "experiments/pareto_publication_20261125"))
    from archive import OUT, records, sha
    from figure import branch_sets

    published = json.loads((OUT / "displayed_curves.json").read_text("utf8"))
    groups, sources = branch_sets(records(OUT / "mixed16_front.csv"))
    assert sources == published["source_hashes"]
    for relative, digest in sources.items():
        assert sha(PAPER / relative) == digest
    curves = {c["label"]: c for row in groups for window in row for c in window}
    labels = [k for _, _, _, _, windows, _ in PANELS for keys in windows for k in keys]
    assert sorted(labels) == sorted(curves) == sorted(c["label"] for c in published["curves"])
    for record in published["curves"]:
        c = curves[record["label"]]
        for field in ("scope", "left_open", "right_open", "low", "high"):
            assert c[field] == record[field]
        for end in ("low", "high"):
            assert abs(c["func"](c[end]) - record[end + "_score"]) < 1e-8
    return curves, sha(OUT / "displayed_curves.json")


def tick(x, _):
    return f"{x:.3f}".rstrip("0").rstrip(".")


def pareto(curves, cn):
    chart = plt.figure(figsize=(3.51, 4.94))
    # Dimensions are those of the final two-column article's single column.
    grid = chart.add_gridspec(3, 2, left=.154, right=.985, bottom=.083, top=.954,
                              wspace=.70, hspace=.88)
    for index, (letter, n, recipe, threshold, windows, yticks) in enumerate(PANELS):
        panel = grid[index // 2, index % 2]
        split = len(windows) > 1
        segments = panel.subgridspec(1, len(windows), wspace=.30)
        ydata = [curves[key]["func"](curves[key][side]) for group in windows
                 for key in group for side in ("low", "high")]
        pad = .10 * (max(ydata) - min(ydata))
        for j, names in enumerate(windows):
            ax = chart.add_subplot(segments[j])
            ax.spines[["top", "right"]].set_visible(False)
            if j:
                ax.spines["left"].set_visible(False)
                ax.tick_params(axis="y", left=False, labelleft=False)
            else:
                ax.set_ylabel("工艺目标（等效 s）" if cn else "Process objective (equiv. s)",
                              labelpad=1.6)
            ax.tick_params(length=2, pad=1, width=.55)
            ax.grid(axis="y", lw=.32, color="#d5dce0")
            ax.set_ylim(min(ydata) - pad, max(ydata) + pad)
            ax.yaxis.set_major_locator(FixedLocator(yticks))
            ax.yaxis.set_major_formatter(FuncFormatter(tick))
            ax.xaxis.set_major_locator(FixedLocator(TICKS[names[0]]))
            ax.xaxis.set_major_formatter(FuncFormatter(tick))
            x0, x1 = curves[names[0]]["low"], curves[names[-1]]["high"]
            margin = (.075 if split else .055) * (x1 - x0)
            ax.set_xlim(x0 - margin, x1 + margin)
            for name in names:
                c = curves[name]
                x = np.linspace(c["low"], c["high"], 151)
                y = c["func"](x)
                assert np.all(np.diff(y) < 0)
                color = COLORS[c["scope"]]
                ax.plot(x, y, color=color, lw=1.10, linestyle="-" if c["scope"]=="exact" else (0,(3,1.4)))
                for side, k in (("left_open", 0), ("right_open", -1)):
                    ax.plot(x[k], y[k], marker="o", markersize=2.4, markeredgewidth=.57,
                            markerfacecolor="white" if c[side] else color, markeredgecolor=color)
            if split:
                # A diagonal slash at both endpoints of the discontinuous time axis.
                bx = 1 - j
                ax.plot([bx], [0], marker=[(-.6,-1),(.6,1)], markersize=3.8,
                        linestyle="none", markeredgewidth=.65, color="#303438",
                        transform=ax.transAxes, clip_on=False)
        rect = panel.get_position(chart)
        if recipe == "mixed":
            material = "混合" if cn else "mixed"
        else:
            material = recipe
        title = (f"({letter}) {n} 片{material}，H={threshold}" if cn else
                 f"({letter}) {n} wafers, {material}, H={threshold}")
        chart.text(rect.x0, rect.y1+.011, title, va="bottom", size=6.45)
        # Center the x label beneath the data axes of its panel (including a split pair).
        chart.text((rect.x0+rect.x1)/2, rect.y0-.041,
                   "总加工时间（s）" if cn else "Batch makespan (s)", ha="center", va="top",
                   size=6.55)
    target = OUTPUT / ("tradeoffs.pdf" if cn else "tradeoffs_en.pdf")
    chart.savefig(target, metadata={"CreationDate":None,"ModDate":None,
                                   "Title":"Makespan and process objective under conventional unloading"})
    plt.close(chart)


def prepare_sources():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    for name in TOPOLOGIES:
        correct_aligner(PAPER / "figures/review_20261125" / name)
    curves, digest = checked_curves()
    for cn in (True, False):
        with matplotlib.rc_context({"font.family":"sans-serif", "font.size":6.55,
                   "font.sans-serif":["Microsoft YaHei" if cn else "DejaVu Sans", "DejaVu Sans"],
                   "xtick.labelsize":5.8, "ytick.labelsize":6.0,
                   "axes.unicode_minus":False, "axes.linewidth":.55, "pdf.fonttype":42}):
            pareto(curves, cn)
    meta = {"curve_source":"results/pareto_publication_20261125/displayed_curves.json",
            "curve_source_sha256":digest,
            "panels": {letter:windows for letter, _, _, _, windows, _ in PANELS}}
    (OUTPUT / "manifest.json").write_text(json.dumps(meta, indent=2)+"\n","utf8")


if __name__ == "__main__":
    prepare_sources()

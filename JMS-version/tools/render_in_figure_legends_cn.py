"""Add self-contained legends to the Chinese manuscript's existing figures.

Only saved and validated intervals are read. No optimization backend is loaded.
Original plots and frozen evidence remain untouched.
"""
from pathlib import Path
import hashlib
import json
import sys

sys.dont_write_bytecode = True
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
import pymupdf

from current_defaults_swimlane import STYLE, build
from render_journal_schedule_examples import cycle_label, LEGEND, LEGEND_LABELS

PAPER = Path(__file__).resolve().parents[1]
OUT = PAPER / "figures/in_figure_legends_20261117"
WIDTH = 3.55


def read(path):
    return json.loads(path.read_text("utf-8-sig"))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(fig, stem):
    for ext in ("pdf", "png", "svg"):
        fig.savefig(OUT / f"{stem}.{ext}", dpi=220, facecolor="white")
    plt.close(fig)


def legend(fig, handles, labels, y, height, columns, fontsize=7.2):
    return fig.legend(handles=handles, labels=labels,
                      loc="lower center", bbox_to_anchor=(.50, y / height),
                      ncol=columns, frameon=False, fontsize=fontsize,
                      columnspacing=1.2, handlelength=1.8, handletextpad=.5,
                      labelspacing=.4, borderpad=.2, borderaxespad=0)


def check_layout(fig, ax, legends, notes=()):
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    artists = [*legends, *notes, ax.xaxis.label]
    boxes = [a.get_window_extent(renderer) for a in artists]
    for i, box in enumerate(boxes):
        assert fig.bbox.contains(box.x0, box.y0), ("Outside figure", i, box)
        assert fig.bbox.contains(box.x1, box.y1), ("Clipped figure", i, box)
        for other in boxes[i + 1:]:
            assert not box.overlaps(other), ("Overlapping legends", i, box, other)
    return {"legend_count": len(legends), "symbol_key_lines": len(notes),
            "legend_clipping": False, "legend_overlap": False}


def draw_coupled():
    old_dir = PAPER / "figures/coupled_schedule_merged_20261112"
    previous = read(old_dir / "manifest.json")
    source = PAPER / previous["source"]
    assert sha(source) == previous["source_sha256"]
    data = read(source)
    products = [j for j in data["jobs"] if j["product"]]
    auxiliaries = [j for j in data["jobs"] if not j["product"]]
    ids = sorted({j["identity"] for j in auxiliaries}, key=lambda s: int(s[1:]))
    pair_mode = {p["id"]: p["mode"] for p in data["pairs"]}
    cycles = sorted(data["cycles"], key=lambda c: c["start"])
    product_cycles = [c for c in cycles
                      if c["mode"] != "clean" and products[0]["pair"] in c["pairs"]]
    loans = [{k: j[k] for k in ("identity", "pair", "loan_start", "loan_end")}
             for j in auxiliaries]
    assert product_cycles == previous["product_processing_cycles"]
    assert loans == previous["auxiliary_loans"]
    cmax = max(j["loan_end"] for j in products)
    end = max(j["loan_end"] for j in data["jobs"])
    assert (cmax, end) == (previous["product_cmax"], previous["occupied_end"])
    height, bottom, top = 3.25, 1.04, .09
    fig, ax = plt.subplots(figsize=(WIDTH, height))
    fig.subplots_adjust(left=.165, right=.985, bottom=bottom / height,
                        top=1 - top / height)
    production, cleaning = "#346995", "#317957"
    lanes = ["产品晶圆"] + ids
    rows = {identity: i + 1 for i, identity in enumerate(ids)}
    for row in range(len(lanes)):
        if row % 2 == 0:
            ax.axhspan(row - .5, row + .5, color="#f5f7fa", zorder=0)
    for c in product_cycles:
        ax.broken_barh([(c["start"], c["end"] - c["start"])],
                       (-.31, .62), facecolors=production, zorder=3)
        ax.text((c["start"] + c["end"]) / 2, 0, "2×2", ha="center",
                va="center", color="white", fontsize=7.2, zorder=4)
    for j in auxiliaries:
        ax.broken_barh([(j["loan_start"], j["loan_end"] - j["loan_start"])],
                       (rows[j["identity"]] - .29, .58),
                       facecolors=cleaning if pair_mode[j["pair"]] == "clean" else production,
                       zorder=3)
    ax.axvline(cmax, color="#a74337", ls="--", lw=.8, zorder=5)
    ax.axvline(end, color="#444444", ls=":", lw=.8, zorder=5)
    ax.set_yticks(range(len(lanes)), lanes, fontsize=7.5)
    ax.set_ylim(len(lanes) - .5, -.65)
    ax.set_xlim(0, 820)
    ax.set_xticks(range(0, 801, 200))
    ax.set_xlabel("时间 / s", fontsize=8, labelpad=4)
    ax.tick_params(axis="x", labelsize=7.2, length=3)
    ax.tick_params(axis="y", length=0, pad=4)
    ax.grid(axis="x", color="#dce1e6", lw=.65)
    ax.set_axisbelow(True)
    ax.spines[["top", "right", "left"]].set_visible(False)
    color_labels = ["生产加工及补位借用", "清洁借用"]
    end_labels = [f"产品完工：{cmax:g} s", f"全部占用结束：{end:g} s"]
    legends = [
        legend(fig, [Patch(facecolor=production), Patch(facecolor=cleaning)],
               color_labels, .43, height, 2),
        legend(fig, [Line2D([], [], color="#a74337", ls="--", lw=.8),
                     Line2D([], [], color="#444444", ls=":", lw=.8)],
               end_labels, .24, height, 2),
    ]
    note = fig.text(.50, .08 / height, "D1–D7：辅助晶圆", ha="center", va="bottom", fontsize=7.2)
    checks = check_layout(fig, ax, legends, [note])
    stem = "fig_coupled_schedule_merged_cn"
    save(fig, stem)
    return {"stem": stem, "source": str(source), "source_sha256": sha(source),
            "previous_manifest": str(old_dir / "manifest.json"),
            "previous_manifest_sha256": sha(old_dir / "manifest.json"),
            "product_processing_cycles": product_cycles, "auxiliary_loans": loans,
            "product_cmax": cmax, "occupied_end": end, "intervals_unchanged": True,
            "legend_labels": color_labels + end_labels,
            "symbol_keys": [note.get_text()], "figure_size_inches": [WIDTH, height], **checks}


def draw_schedule(entry, compact_layout=False):
    source, evidence_path = Path(entry["result"]), Path(entry["evidence"])
    assert sha(source) == entry["result_sha256"]
    assert sha(evidence_path) == entry["evidence_sha256"]
    data, evidence = read(source), read(evidence_path)
    lanes, bars, _, _ = build(data)
    assert lanes == evidence["lanes"] and bars == evidence["bars"]
    assert evidence["explicit_events_covered"] == len(data["events"])
    assert evidence["overlapping_display_states"] == 0
    assert {bar["action"] for bar in bars} <= set(LEGEND)
    horizon = max(bar["end"] for bar in bars)
    cmax = max(j["loan_end"] for j in data["jobs"] if j["product"])
    assert (cmax, horizon) == (entry["cmax"], entry["resource_end"])
    compact = horizon > 400
    row_height, bottom, top = .21, (1.40 if compact_layout else 1.60), .10
    height = len(lanes) * row_height + bottom + top
    fig, ax = plt.subplots(figsize=(WIDTH, height))
    fig.subplots_adjust(left=.23, right=.985, bottom=bottom / height, top=1 - top / height)
    positions = {lane: i for i, lane in enumerate(lanes)}
    for i in range(len(lanes)):
        ax.axhspan(i - .45, i + .45, color="#F7F8FA" if i % 2 == 0 else "white", zorder=0)
        ax.axhline(i + .5, color="#DFE2E6", lw=.45, zorder=0)
    for bar in bars:
        ax.broken_barh([(bar["start"], bar["end"] - bar["start"])],
                       (positions[bar["lane"]] - .34, .68),
                       facecolors=STYLE[bar["action"]], edgecolors="white",
                       linewidth=.08 if compact else .20, zorder=2)
    cycle_texts = []
    for cycle in data["cycles"]:
        y = positions[f"旋转腔 CH{cycle['chamber']}"]
        artist = ax.text((cycle["start"] + cycle["end"]) / 2, y,
                         cycle_label(cycle, data, include_mode=not compact), ha="center", va="center",
                         color="white", fontsize=7.1, zorder=5)
        cycle_texts.append((cycle, y, artist))
    display_lanes = ["真空辅助库 VS" if lane == "VS" else lane for lane in lanes]
    ax.set_yticks(range(len(lanes)), display_lanes, fontsize=7.5)
    ax.set_ylim(len(lanes) - .5, -.5)
    ax.set_xlim(0, horizon * 1.035)
    ax.set_xticks(range(0, int(horizon) + 1, 200 if compact else 50))
    ax.set_xlabel("时间 / s", fontsize=8, labelpad=4)
    ax.tick_params(axis="x", labelsize=7.2, width=.7, length=3)
    ax.tick_params(axis="y", length=0, pad=4)
    ax.grid(axis="x", color="#E0E3E8", lw=.55)
    ax.set_axisbelow(True)
    ax.spines[["top", "right", "left"]].set_visible(False)
    ax.spines["bottom"].set_linewidth(.8)
    ax.axvline(cmax, color="#222222", ls="--", lw=1, zorder=3)
    ax.axvline(horizon, color="#777777", ls=":", lw=1, zorder=3)
    action_legend = fig.legend(
        handles=[Patch(facecolor=STYLE[name], label=LEGEND_LABELS[name]) for name in LEGEND],
        loc="lower center", bbox_to_anchor=(.51, .51 / height),
        ncol=4, frameon=False, fontsize=7.2, columnspacing=.85,
        handlelength=1.2, handletextpad=.5, labelspacing=.4, borderpad=.2, borderaxespad=0)
    end_labels = [f"产品回片：{cmax:g} s", f"全部占用结束：{horizon:g} s"]
    end_legend = legend(fig, [Line2D([], [], color="#222222", ls="--", lw=1),
                              Line2D([], [], color="#777777", ls=":", lw=1)],
                        end_labels, .30, height, 2)
    key = ("P1[i:j]：Pjob1中第i至j片产品" if compact else
           "P1[1:2]：Pjob1的两片产品    D1、D2：辅助片")
    notes = [fig.text(.50, .10 / height, key, ha="center", va="bottom", fontsize=7.2)]
    axis_checks = {}
    if compact_layout:
        from compact_figure_layout import inline_time_label
        axis_checks = inline_time_label(fig, ax, "时间 / s")
    checks = check_layout(fig, ax, [action_legend, end_legend], notes)
    renderer = fig.canvas.get_renderer()
    for cycle, y, artist in cycle_texts:
        box = artist.get_window_extent(renderer)
        left = ax.transData.transform((cycle["start"], y))[0]
        right = ax.transData.transform((cycle["end"], y))[0]
        assert left <= box.x0 and box.x1 <= right, "Processing label exceeds its interval"
    save(fig, entry["stem"])
    return {"stem": entry["stem"], "result": str(source), "result_sha256": sha(source),
            "evidence": str(evidence_path), "evidence_sha256": sha(evidence_path),
            "lanes": len(lanes), "intervals": len(bars), "events_covered": len(data["events"]),
            "cmax": cmax, "resource_end": horizon, "intervals_unchanged": True,
            "action_legend": [LEGEND_LABELS[name] for name in LEGEND],
            "end_marker_legend": end_labels, "symbol_keys": [key],
            "figure_size_inches": [WIDTH, height], "row_height_inches": row_height,
            **axis_checks, **checks}


def add_chain_legend(compact_layout=False):
    source = PAPER / "figures/terminology_cn/fig_chain_cn_nature.pdf"
    doc = pymupdf.open(source)
    page = doc[0]
    # The existing vector drawing ends above y=207; use its blank footer.
    existing_words = page.get_text("words")
    assert max(word[3] for word in existing_words) < 208
    font = pymupdf.Font(fontfile="C:/Windows/Fonts/msyh.ttc")
    label, size = "辅助PW对", 6.8
    label_width = font.text_length(label, fontsize=size)
    total_width = 23 + label_width
    x = (page.rect.width - total_width) / 2
    y, radius = (214.0 if compact_layout else 220.0), 3.9
    page.insert_font(fontname="LegendCN", fontbuffer=font.buffer)
    for dx in (4, 14):
        page.draw_circle((x + dx, y), radius, color=(.17, .17, .17),
                         fill=(1., .82, .36), width=.6, dashes="[2 1] 0")
        dwidth = font.text_length("D", fontsize=6)
        page.insert_text((x + dx - dwidth / 2, y + 2.15), "D", fontsize=6,
                         fontname="LegendCN", color=(0, 0, 0))
    page.insert_text((x + 23, y + 2.5), label, fontsize=size, fontname="LegendCN")
    stem = "fig_chain_cn_nature"
    doc.subset_fonts()
    doc.save(OUT / f"{stem}.pdf", garbage=4, deflate=True)
    page.get_pixmap(matrix=pymupdf.Matrix(3, 3), alpha=False).save(OUT / f"{stem}.png")
    (OUT / f"{stem}.svg").write_text(page.get_svg_image(), "utf-8")
    rect = list(page.rect)
    doc.close()
    original = pymupdf.open(source)
    revised = pymupdf.open(OUT / f"{stem}.pdf")
    clip = pymupdf.Rect(0, 0, rect[2], 209)
    before = original[0].get_pixmap(matrix=pymupdf.Matrix(3, 3), clip=clip, alpha=False)
    after = revised[0].get_pixmap(matrix=pymupdf.Matrix(3, 3), clip=clip, alpha=False)
    assert before.samples == after.samples, "Existing chain drawing changed"
    original.close()
    revised.close()
    return {"stem": stem, "source": str(source), "source_sha256": sha(source),
            "page_size_points": rect[2:], "original_drawing_unchanged": True,
            "legend": {"symbol": "two yellow dashed D circles", "label": label,
                       "center_y_points": y, "fontsize_points": size}}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update({"font.sans-serif": ["Microsoft YaHei", "SimHei", "DejaVu Sans"],
                         "font.size": 8, "axes.unicode_minus": False,
                         "pdf.fonttype": 42, "svg.fonttype": "path"})
    figures = [draw_coupled()]
    old_schedule = read(PAPER / "figures/schedule_examples_unified_20261112/manifest.json")
    figures.extend(draw_schedule(entry) for entry in old_schedule["figures"])
    figures.append(add_chain_legend())
    report = {"renderer": str(Path(__file__)), "renderer_sha256": sha(Path(__file__)),
              "interval_builder_sha256": sha(Path(__file__).with_name("current_defaults_swimlane.py")),
              "optimization_calls": 0, "figures": figures,
              "artifacts": {p.name: sha(p) for p in OUT.iterdir()
                            if p.suffix in (".pdf", ".svg", ".png")}}
    (OUT / "manifest.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", "utf-8")
    print(json.dumps({"output": str(OUT), "figures": [f["stem"] for f in figures],
                      "optimization_calls": 0, "unchanged_intervals": True}, ensure_ascii=False))


if __name__ == "__main__":
    main()

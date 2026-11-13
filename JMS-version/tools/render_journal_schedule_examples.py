"""Render the two certified manuscript examples with one publication style.

Only presentation changes: all resource intervals come from saved, checked
schedule evidence. No solver, experiment, or shared launcher is invoked.
"""
from pathlib import Path
import argparse
import hashlib
import json
import sys

sys.dont_write_bytecode = True
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
from current_defaults_swimlane import STYLE, build

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "JMS-version/figures/schedule_examples_unified_20261112"
LEGEND = [name for name in STYLE if name != "清洁"]
# This saved state also covers alignment-station waiting in the large example.
LEGEND_LABELS = {name: "大气侧等待" if name == "LL大气等待" else name for name in LEGEND}
WIDTH, ROW_HEIGHT, BOTTOM, TOP = 11.0, 0.30, 1.35, 0.12
FONT = {"resource": 12.5, "tick": 12, "axis": 13, "cycle": 11.5, "legend": 12}


def read(path):
    return json.loads(path.read_text("utf-8-sig"))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def cycle_label(cycle, data, include_mode=True):
    jobs = [job for job in data["jobs"] if job["pair"] in cycle["pairs"]]
    products = sorted(job["pjob_index"] for job in jobs if job["product"])
    assert all(job["pjob"] == "Pjob1" for job in jobs if job["product"])
    ids = []
    if products:
        assert products == list(range(products[0], products[-1] + 1))
        ids.append(f"P1[{products[0]}:{products[-1]}]")
    ids.extend(job["identity"] for job in jobs if not job["product"])
    label = "/".join(ids)
    return cycle["mode"].replace("x", "×") + " | " + label if include_mode else label


def draw(data, evidence, stem, single_column=False):
    width, row_height, bottom, top = WIDTH, ROW_HEIGHT, BOTTOM, TOP
    font = dict(FONT)
    left, right, legend_columns = .165, .985, 5
    if single_column:
        width, row_height, bottom, top = 3.55, .21, 1.4, .10
        font = {"resource": 7.5, "tick": 7.2, "axis": 8, "cycle": 7.1, "legend": 7.2}
        left, right, legend_columns = .23, .985, 3
    lanes, bars, _, _ = build(data)
    assert lanes == evidence["lanes"] and bars == evidence["bars"]
    assert evidence["explicit_events_covered"] == len(data["events"])
    assert evidence["overlapping_display_states"] == 0
    assert {bar["action"] for bar in bars} <= set(LEGEND)
    horizon = max(bar["end"] for bar in bars)
    compact_cycle_labels = single_column and horizon > 400
    cmax = max(job["loan_end"] for job in data["jobs"] if job["product"])
    height = len(lanes) * row_height + bottom + top
    fig, ax = plt.subplots(figsize=(width, height))
    fig.subplots_adjust(left=left, right=right, bottom=bottom / height, top=1 - top / height)
    positions = {lane: i for i, lane in enumerate(lanes)}
    for i in range(len(lanes)):
        ax.axhspan(i - .45, i + .45, color="#F7F8FA" if i % 2 == 0 else "white", zorder=0)
        ax.axhline(i + .5, color="#DFE2E6", lw=.45, zorder=0)
    for bar in bars:
        ax.broken_barh([(bar["start"], bar["end"] - bar["start"])],
                       (positions[bar["lane"]] - .34, .68),
                       facecolors=STYLE[bar["action"]], edgecolors="white",
                       linewidth=.08 if compact_cycle_labels else .20, zorder=2)
    cycle_texts = []
    for cycle in data["cycles"]:
        y = positions[f"旋转腔 CH{cycle['chamber']}"]
        artist = ax.text((cycle["start"] + cycle["end"]) / 2, y,
                         cycle_label(cycle, data, include_mode=not compact_cycle_labels), ha="center", va="center",
                         color="white", fontsize=font["cycle"], zorder=5)
        cycle_texts.append((cycle, y, artist))
    display_lanes = ["真空辅助库 VS" if lane == "VS" else lane for lane in lanes]
    ax.set_yticks(range(len(lanes)), display_lanes, fontsize=font["resource"])
    ax.set_ylim(len(lanes) - .5, -.5)
    ax.set_xlim(0, horizon * 1.035)
    tick_step = 50 if horizon <= 400 else (200 if single_column else 100)
    ax.set_xticks(range(0, int(horizon) + 1, tick_step))
    ax.set_xlabel("时间 / s", fontsize=font["axis"], labelpad=4 if single_column else 7)
    ax.tick_params(axis="x", labelsize=font["tick"], width=.7, length=3 if single_column else 4)
    ax.tick_params(axis="y", length=0, pad=4 if single_column else 7)
    ax.grid(axis="x", color="#E0E3E8", lw=.55)
    ax.set_axisbelow(True)
    ax.spines[["top", "right", "left"]].set_visible(False)
    ax.spines["bottom"].set_linewidth(.8)
    ax.axvline(cmax, color="#222222", ls="--", lw=1, zorder=3)
    ax.axvline(horizon, color="#777777", ls=":", lw=1, zorder=3)
    legend = fig.legend(handles=[Patch(facecolor=STYLE[name], label=LEGEND_LABELS[name]) for name in LEGEND],
                        loc="lower center", bbox_to_anchor=(.51 if single_column else .55, .035 / height),
                        ncol=legend_columns, frameon=False, fontsize=font["legend"],
                        columnspacing=.85 if single_column else 1.3,
                        handlelength=1.2 if single_column else 1.5, handletextpad=.5 if single_column else .65,
                        labelspacing=.4, borderpad=.2, borderaxespad=0)
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    legend_box = legend.get_window_extent(renderer)
    assert not legend_box.overlaps(ax.xaxis.label.get_window_extent(renderer)), "Axis/legend overlap"
    assert fig.bbox.contains(legend_box.x0, legend_box.y0)
    assert fig.bbox.contains(legend_box.x1, legend_box.y1), "Legend clipped"
    assert fig.texts == [] and ax.get_title() == "", "Explanatory text belongs in the LaTeX caption"
    for cycle, y, artist in cycle_texts:
        box = artist.get_window_extent(renderer)
        left = ax.transData.transform((cycle["start"], y))[0]
        right = ax.transData.transform((cycle["end"], y))[0]
        assert left <= box.x0 and box.x1 <= right, "Processing label exceeds its interval"
    for ext in ("pdf", "png", "svg"):
        fig.savefig(OUT / f"{stem}.{ext}", dpi=220, facecolor="white")
    plt.close(fig)
    return {"stem": stem, "cmax": cmax, "resource_end": horizon,
            "lanes": len(lanes), "intervals": len(bars), "intervals_unchanged": True,
            "events_covered": len(data["events"]), "legend": [LEGEND_LABELS[name] for name in LEGEND],
            "figure_size_inches": [width, height], "row_height_inches": row_height,
            "fonts_points": font, "plot_titles_and_notes": 0,
            "single_column": single_column, "legend_columns": legend_columns,
            "cycle_labels": [cycle_label(cycle, data, include_mode=not compact_cycle_labels)
                             for cycle in data["cycles"]],
            "cycle_modes": [cycle["mode"] for cycle in data["cycles"]]}


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--only", choices=("n2", "n16", "both"), default="both")
    args = parser.parse_args()
    plt.rcParams.update({"font.sans-serif": ["Microsoft YaHei", "SimHei", "DejaVu Sans"],
                         "font.size": 13, "axes.unicode_minus": False,
                         "pdf.fonttype": 42, "svg.fonttype": "path"})
    small_manifest = read(ROOT / "JMS-version/figures/current_defaults_20261103/manifest.json")
    large_manifest = read(ROOT / "JMS-version/figures/current_d_n16_20261111/manifest.json")
    entries = [
        (Path(small_manifest["result"]), small_manifest["result_sha256"],
         ROOT / "JMS-version/figures/current_defaults_20261103/swimlane_actions.json", "fig_schedule_n2_cn"),
        (Path(large_manifest["source"]), large_manifest["source_sha256"],
         ROOT / "JMS-version/review/gantt_current_model_20261111/n16_current_D_920/figure_evidence.json", "fig_schedule_n16_cn"),
    ]
    OUT.mkdir(parents=True, exist_ok=True)
    previous = read(OUT / "manifest.json") if (OUT / "manifest.json").exists() else {"figures": []}
    figures_by_stem = {info["stem"]: info for info in previous["figures"]}
    regenerated = []
    for result_path, result_hash, evidence_path, stem in entries:
        if args.only != "both" and stem != f"fig_schedule_{args.only}_cn":
            continue
        assert sha(result_path) == result_hash, "Source schedule changed"
        data, evidence = read(result_path), read(evidence_path)
        info = draw(data, evidence, stem, single_column=True)
        info.update({"result": str(result_path), "result_sha256": result_hash,
                     "evidence": str(evidence_path), "evidence_sha256": sha(evidence_path)})
        figures_by_stem[stem] = info
        regenerated.append(stem)
    figures = [figures_by_stem[entry[3]] for entry in entries if entry[3] in figures_by_stem]
    assert all(info["legend"] == figures[0]["legend"] for info in figures)
    report = {"renderer": str(Path(__file__)), "renderer_sha256": sha(Path(__file__)),
              "interval_builder_sha256": sha(Path(__file__).with_name("current_defaults_swimlane.py")),
              "figures": figures, "regenerated_figures": regenerated, "optimization_calls": 0,
              "artifacts": {p.name: sha(p) for p in OUT.iterdir() if p.suffix in (".pdf", ".svg", ".png")}}
    (OUT / "manifest.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), "utf-8")
    print(json.dumps({"output": str(OUT), "figures": regenerated,
                      "identical_legends": True, "unchanged_intervals": [f["intervals"] for f in figures]}, ensure_ascii=False))


if __name__ == "__main__":
    main()

"""Render the three single-column Gantt charts from their validated schedule records."""

from collections import defaultdict
from itertools import combinations
import json
import os
from pathlib import Path

from matplotlib.patches import Patch
from matplotlib.transforms import Bbox

from render_journal_schedule_examples import LEGEND, LEGEND_LABELS, STYLE, build, cycle_label, plt, read, sha


JMS = Path(__file__).resolve().parents[1]
ARCHIVE = JMS / "results/gantt_huber_comparison_20261125"
OUTPUT = JMS / "figures/huber_gantt_20261125"


def time_axis(ax, finish, release, step):
    """Anchor labels to actual times; give the two nearby terminal ticks separate rows."""
    ax.set_xlim(0, release * 1.035)
    ax.tick_params(axis="x", labelsize=7.2, width=.7, length=3, pad=2.5)
    ax.tick_params(axis="y", length=0, pad=4)
    ax.grid(axis="x", color="#E0E3E8", lw=.55)
    ax.set_axisbelow(True)
    ax.spines[["top", "right", "left"]].set_visible(False)
    ax.spines["bottom"].set_linewidth(.8)
    axis_trace = ax.get_xaxis_transform()
    labels = []
    for t, name, style, color, offset in (
        (finish, "完工", "--", "#222222", 5.5),
        (release, "释放", ":", "#5C5C5C", 15.5),
    ):
        ax.axvline(t, color=color, ls=style, lw=.8, zorder=3)
        ax.annotate("", xy=(t, 0), xycoords=axis_trace, xytext=(0, -offset + 1.6),
                    textcoords="offset points", annotation_clip=False,
                    arrowprops={"arrowstyle": "-", "color": color, "lw": .65,
                                "linestyle": style, "shrinkA": 0, "shrinkB": 0})
        labels.append(ax.annotate(f"{name} {t:g}", xy=(t, 0), xycoords=axis_trace,
                                  xytext=(0, -offset), textcoords="offset points",
                                  ha="right", va="top", fontsize=6.6, color=color))
    labels.append(ax.annotate("时间 / s", xy=(0, 0), xycoords="axes fraction",
                              xytext=(-8, -5.1), textcoords="offset points",
                              ha="right", va="top", fontsize=7.4))
    labels.append(ax.annotate("资源", xy=(0, 1), xycoords="axes fraction",
                              xytext=(-4, 1.6), textcoords="offset points",
                              ha="right", va="bottom", fontsize=7.4))
    regular = list(range(0, int(release) + 1, step))
    ax.set_xticks(regular)
    fig = ax.get_figure()
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    occupied = labels[0].get_window_extent(renderer).padded(2)
    ax.set_xticks([t for t, text in zip(regular, ax.get_xticklabels())
                   if not occupied.overlaps(text.get_window_extent(renderer))])
    return labels


def draw(record):
    info = record["summary"]
    source, certificate = (JMS / info[key] for key in ("source", "certificate"))
    assert sha(source) == info["source_sha256"] and sha(certificate) == info["certificate_sha256"]
    data = read(source)
    lanes, bars, _, _ = build(data)
    finish = max(j["loan_end"] for j in data["jobs"] if j["product"])
    release = max(bar["end"] for bar in bars)
    assert (finish, release) == (info["cmax"], info["equipment_end"])
    assert record["replay"]["valid"] and len(bars) == record["display"]["intervals"]
    n = info["n"]
    colors = dict(STYLE)
    legend = list(LEGEND)
    spans = defaultdict(list)
    batches = defaultdict(list)
    for cycle in data["cycles"]:
        batches[f"旋转腔 CH{cycle['chamber']}"].append(cycle)
    if n == 75:
        colors.update({"4×1加工": STYLE["腔室加工"], "2×2加工": "#DB8970"})
        position = legend.index("腔室加工")
        legend[position:position + 1] = ["4×1加工", "2×2加工"]
        legend.append("清洁")
    for bar in bars:
        action, lane = bar["action"], bar["lane"]
        if n == 75 and action == "腔室加工":
            cycle, = [c for c in batches[lane] if c["start"] <= bar["start"] and bar["end"] <= c["end"]]
            action = cycle["mode"].replace("x", "×") + "加工"
        spans[lane, action].append((bar["start"], bar["end"] - bar["start"]))
    assert {k[1] for k in spans} <= set(legend)

    width, bottom, top = 3.55, 1.10, .18
    height = len(lanes) * .21 + bottom + top
    fig, ax = plt.subplots(figsize=(width, height))
    fig.subplots_adjust(left=.23, right=.985, bottom=bottom / height, top=1 - top / height)
    interior = []
    for y, lane in enumerate(lanes):
        ax.axhspan(y - .45, y + .45, color="#F7F8FA" if y % 2 == 0 else "white", zorder=0)
        ax.axhline(y + .5, color="#DFE2E6", lw=.45, zorder=0)
        for action in legend:
            if (lane, action) in spans:
                ax.broken_barh(spans[lane, action], (y - .34, .68), facecolors=colors[action],
                               edgecolors="none" if n == 75 else "white", linewidth=.08, zorder=2)
        if n != 75:
            for cycle in batches[lane]:
                artist = ax.text((cycle["start"] + cycle["end"]) / 2, y, cycle_label(cycle, data, False),
                                 color="white", fontsize=7.1, ha="center", va="center", zorder=5)
                interior.append((artist, cycle["start"], cycle["end"]))
    ax.set_yticks(range(len(lanes)), ["真空辅助库 VS" if s == "VS" else s for s in lanes], fontsize=7.5)
    ax.set_ylim(len(lanes) - .5, -.5)
    labels = time_axis(ax, finish, release, {4: 100, 16: 200, 75: 1000}[n])
    key = fig.legend(handles=[Patch(facecolor=colors[action], label=LEGEND_LABELS.get(action, action))
                              for action in legend], loc="lower center", bbox_to_anchor=(.51, .035 / height),
                     ncol=4, frameon=False, fontsize=7.2, columnspacing=.85, handlelength=1.2,
                     handletextpad=.5, labelspacing=.4, borderpad=.2, borderaxespad=0)
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    layout = [t.get_window_extent(renderer) for t in [*labels, *ax.get_xticklabels(), *ax.get_yticklabels(), key]]
    for a, b in combinations(layout, 2):
        assert not a.overlaps(b), "Overlapping axis, lane or legend text"
    box = Bbox.union(layout)
    assert fig.bbox.contains(box.x0, box.y0) and fig.bbox.contains(box.x1, box.y1)
    for artist, start, end in interior:
        box = artist.get_window_extent(renderer)
        assert ax.transData.transform((start, 0))[0] <= box.x0 <= box.x1 <= ax.transData.transform((end, 0))[0]
    target = OUTPUT / f"fig_schedule_n{n}_huber_cn.pdf"
    fig.savefig(target, facecolor="white", metadata={"CreationDate": None, "ModDate": None})
    plt.close(fig)
    return dict(n=n, source=info["source"], source_sha256=sha(source), certificate=info["certificate"],
                certificate_sha256=sha(certificate), cmax=finish, equipment_end=release,
                secondary=info["secondary"], lanes=lanes, intervals=len(bars), events=len(data["events"]),
                chart=target.name, chart_sha256=sha(target))


def main():
    os.environ["SOURCE_DATE_EPOCH"] = "0"
    plt.rcParams.update({"font.sans-serif": ["Microsoft YaHei", "SimHei", "DejaVu Sans"],
                         "axes.unicode_minus": False, "pdf.fonttype": 42})
    OUTPUT.mkdir(exist_ok=True)
    records = [draw(r) for r in read(ARCHIVE / "comparison.json") if r["summary"]["variant"] == "huber"]
    assert [r["n"] for r in records] == [4, 16, 75]
    (OUTPUT / "manifest.json").write_text(json.dumps(records, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()

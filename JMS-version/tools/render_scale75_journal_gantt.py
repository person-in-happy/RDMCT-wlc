"""Render the verified 75-product schedule in the single-column journal style."""
from collections import defaultdict
from pathlib import Path

from render_journal_schedule_examples import LEGEND, LEGEND_LABELS, STYLE, build, plt, read, sha
from matplotlib.patches import Patch


JMS = Path(__file__).resolve().parents[1]
RUN = JMS / "results/scale75_mixed_A0p001pct_B0p001pct_D_20261119"
EXAMPLES = JMS / "results/manuscript_cases_A0p001pct_B0p001pct_20261119/figures"
DESTINATION = JMS / "figures/rolling_refinement_20261119/fig_schedule_n75_cn.pdf"


def render():
    report = read(RUN / "report.json")
    source = RUN / "final/result.json"
    certificate = read(RUN / "final/original_row_audit/certificate.json")
    if (sha(source) != report["final_result_sha256"] or
            certificate["result_sha256"] != report["final_result_sha256"] or
            certificate["status"] != "all_original_rows_satisfied" or not report["replay"]["valid"]):
        raise ValueError("No matching validated assignment for the 75-product figure")

    data = read(source)
    lanes, bars, traces, _ = build(data)
    finish = max(job["loan_end"] for job in data["jobs"] if job["product"])
    end = max(bar["end"] for bar in bars)
    archived = read(RUN / "final/summary.json")["figures"]
    if (lanes != archived["lanes"] or len(traces) != archived["wafer_routes"]
            or len(data["events"]) != archived["explicit_events"]
            or (finish, end) != (archived["product_return"], archived["resource_end"])):
        raise ValueError("Display coverage differs from the audited schedule")

    by_lane = defaultdict(list)
    for cycle in data["cycles"]:
        by_lane[f"旋转腔 CH{cycle['chamber']}"].append(cycle)
    spans = defaultdict(list)
    for bar in bars:
        lane, action = bar["lane"], bar["action"]
        start, stop = bar["start"], bar["end"]
        if action == "腔室加工":
            cycle, = [c for c in by_lane[lane] if c["start"] <= start and stop <= c["end"]]
            action = {"4x1": "4×1加工", "2x2": "2×2加工"}[cycle["mode"]]
        spans[lane, action].append((start, stop - start))
    for chamber, measured in report["idle_after"]["chambers"].items():
        lane = f"旋转腔 CH{chamber}"
        occupied = sum(max(0, min(finish, start + width) - start)
                       for (resource, _), intervals in spans.items() if resource == lane
                       for start, width in intervals)
        if abs(finish - occupied - measured["idle"]) > 1e-6:
            raise ValueError(f"Displayed occupancy differs from the certificate for {lane}")

    example = next(f for f in read(EXAMPLES / "manifest.json")["figures"]
                   if f["stem"] == "fig_schedule_n2_cn")
    fonts = example["fonts_points"]
    legend = [name for name in LEGEND if name != "腔室加工"]
    position = LEGEND.index("腔室加工")
    legend[position:position] = ["4×1加工", "2×2加工"]
    legend.append("清洁")
    colors = {**STYLE, "4×1加工": STYLE["腔室加工"], "2×2加工": "#DB8970"}
    width = example["figure_size_inches"][0]
    bottom, top = 1.10, .10
    height = len(lanes) * example["row_height_inches"] + bottom + top
    plt.rcParams.update({"font.sans-serif": ["Microsoft YaHei", "SimHei", "DejaVu Sans"],
                         "axes.unicode_minus": False, "pdf.fonttype": 42})
    fig, ax = plt.subplots(figsize=(width, height))
    fig.subplots_adjust(left=.23, right=.985, bottom=bottom / height, top=1 - top / height)
    for y, lane in enumerate(lanes):
        ax.axhspan(y - .45, y + .45, color="#F7F8FA" if y % 2 == 0 else "white", zorder=0)
        ax.axhline(y + .5, color="#DFE2E6", lw=.45, zorder=0)
        for name in legend:
            intervals = spans.get((lane, name))
            if intervals:
                # At this time scale an outline would conceal a one-second transfer.
                ax.broken_barh(intervals, (y - .34, .68), facecolors=colors[name],
                               edgecolors="none", zorder=2)
    if set(action for _, action in spans) != set(legend):
        raise ValueError("Resource states and legend disagree")
    ax.set_yticks(range(len(lanes)), ["真空辅助库 VS" if lane == "VS" else lane for lane in lanes],
                  fontsize=fonts["resource"])
    ax.set_ylim(len(lanes) - .5, -.5)
    ax.set_xlim(0, end * 1.035)
    ax.set_xticks(range(0, int(end) + 1, 1000))
    ax.set_xlabel("时间 / s", fontsize=fonts["axis"], labelpad=4)
    ax.tick_params(axis="x", labelsize=fonts["tick"], width=.7, length=3)
    ax.tick_params(axis="y", length=0, pad=4)
    ax.grid(axis="x", color="#E0E3E8", lw=.55)
    ax.set_axisbelow(True)
    ax.spines[["top", "right", "left"]].set_visible(False)
    ax.spines["bottom"].set_linewidth(.8)
    ax.axvline(finish, color="#222222", ls="--", lw=1, zorder=3)
    ax.axvline(end, color="#777777", ls=":", lw=1, zorder=3)
    key = fig.legend(handles=[Patch(facecolor=colors[name], label=LEGEND_LABELS.get(name, name))
                              for name in legend], loc="lower center", bbox_to_anchor=(.51, .035 / height),
                     ncol=example["legend_columns"], frameon=False, fontsize=fonts["legend"],
                     columnspacing=.85, handlelength=1.2, handletextpad=.5, labelspacing=.4,
                     borderpad=.2, borderaxespad=0)
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    box = key.get_window_extent(renderer)
    if (not fig.bbox.contains(box.x0, box.y0) or not fig.bbox.contains(box.x1, box.y1)
            or box.overlaps(ax.xaxis.label.get_window_extent(renderer))):
        raise ValueError("Clipped legend or overlapping time-axis label")
    fig.savefig(DESTINATION, facecolor="white", metadata={"CreationDate": None, "ModDate": None})
    plt.close(fig)
    print(f"{len(lanes)} lanes, {len(bars)} intervals, {len(data['events'])} events, "
          f"return {finish:g} s, resource end {end:g} s")


if __name__ == "__main__":
    render()

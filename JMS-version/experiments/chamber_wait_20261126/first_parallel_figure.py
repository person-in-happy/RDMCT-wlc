"""Plot the first two parallel-recipe cycles on the absolute batch time axis."""
import json
from pathlib import Path
import sys

import matplotlib.pyplot as plt
from matplotlib.patches import Patch

PAPER = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PAPER / "tools"))
from current_defaults_swimlane import build
from render_huber_gantt_cn import sha

OUTPUT = PAPER / "results/chamber_wait_20261126/figures"
STYLES = {
    "腔室加工": ("#23656c", "4×1 工艺加工"),
    "VTR取放": ("#ba5f26", "机械手装卸"),
    "腔室旋转": ("#675382", "腔室旋转"),
    "腔内等待": ("#ecc76d", "有片等待"),
    "清洁": ("#39946b", "清洁"),
    "空腔": ("#d9dfe6", "空腔"),
}


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def selected_window(schedule, bars, chamber):
    cycles = sorted((c for c in schedule["cycles"] if c["chamber"] == chamber
                     and c["mode"] == "4x1"), key=lambda c: c["start"])[:2]
    first, second = cycles
    inside = [b for b in bars if b["lane"] == f"旋转腔 CH{chamber}"
              and b["end"] > first["start"] and b["start"] < second["end"]]
    cursor = first["start"]
    intervals = []
    for bar in sorted(inside, key=lambda b: b["start"]):
        start, end = max(bar["start"], first["start"]), min(bar["end"], second["end"])
        assert start >= cursor and end > start
        if start > cursor:
            intervals.append((cursor, start, "空腔"))
        intervals.append((start, end, bar["action"]))
        cursor = end
    assert cursor == second["end"]
    return first, second, intervals


def main(endpoint):
    certificate = read(endpoint.with_name("evidence.json"))
    reference = PAPER / certificate["source"]
    ref_proof = read(reference.with_name("evidence.json"))
    assert certificate["original_rows_valid"] and certificate["physical_validation"]["valid"]
    assert sha(endpoint) == certificate["schedule_sha256"]
    assert sha(reference) == ref_proof["schedule_sha256"]
    schedules = [read(p) for p in (reference, endpoint)]
    bars = [build(d)[1] for d in schedules]
    plt.rcParams.update({"font.sans-serif": ["Microsoft YaHei", "SimHei", "DejaVu Sans"],
                         "pdf.fonttype": 42, "axes.unicode_minus": False})
    fig, axes = plt.subplots(2, 1, figsize=(9.0, 5.1))
    fig.subplots_adjust(left=.168, right=.97, top=.88, bottom=.205, hspace=.72)
    fig.suptitle("75 片混合工艺排程中各腔室最先执行的两个 4×1 加工周期",
                 x=.025, y=.985, ha="left", fontsize=13, weight="bold")
    used = set()
    for chamber, ax in zip((2, 3), axes):
        extents, labels = [], []
        for index, (schedule, decoded) in enumerate(zip(schedules, bars)):
            first, second, intervals = selected_window(schedule, decoded, chamber)
            gap = second["start"] - first["end"]
            observed = certificate[("intervals_before", "intervals_after")[index]][str(chamber)]
            assert gap == observed["gap"]
            assert sum(b-a for a,b,k in intervals if k=="空腔") == observed["empty"]
            y = 1 - index
            labels.append(("原排程" if index == 0 else "新排程") + f"   间隔 {gap:g} s")
            extents.extend((first["start"], second["end"]))
            for start, end, state in intervals:
                used.add(state)
                ax.broken_barh([(start, end-start)], (y-.23, .46),
                               facecolor=STYLES[state][0], edgecolor="none")
            for number, cycle in enumerate((first, second), 1):
                a, b = cycle["start"], cycle["end"]
                ax.text((a+b)/2, y, f"第 {number} 次   {a:g}–{b:g}", color="white",
                        va="center", ha="center", fontsize=8)
            a, b = first["end"], second["start"]
            ax.plot([a,a,b,b], [y+.27,y+.37,y+.37,y+.27], lw=.75, color="#394650")
        ax.set_xlim(min(extents)-15, max(extents)+15)
        ax.set_ylim(-.5, 1.52)
        ax.set_yticks([1,0], labels, fontsize=9)
        ax.tick_params(axis="y", length=0)
        ax.set_axisbelow(True)
        ax.grid(axis="x", color="#e4e7eb", lw=.7)
        ax.spines[["left","right","top"]].set_visible(False)
        ax.set_title(f"CH{chamber}", loc="left", fontsize=10, weight="bold", pad=1)
    axes[-1].set_xlabel("自批次开始的时间 / s", fontsize=9)
    handles = [Patch(facecolor=color, label=label) for state,(color,label) in STYLES.items() if state in used]
    fig.legend(handles=handles, ncol=len(handles), loc="lower center",
               bbox_to_anchor=(.52,.015), frameon=False, fontsize=9)
    OUTPUT.mkdir(exist_ok=True)
    name = OUTPUT / "n75_first_parallel_intervals"
    fig.savefig(name.with_suffix(".pdf"), metadata={"CreationDate": None, "ModDate": None})
    fig.savefig(name.with_suffix(".png"), dpi=190)
    plt.close(fig)


if __name__ == "__main__":
    from render_submission_gantts import SCHEDULES
    main(SCHEDULES[75])

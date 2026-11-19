"""Overview and consecutive 600-second detail pages from the checked D event log."""
from collections import defaultdict
from math import ceil

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.patches import Patch
from matplotlib.ticker import MaxNLocator

from current_defaults_swimlane import STYLE, build


def draw(data, dest):
    dest.mkdir(exist_ok=True)
    lanes, bars, traces, _ = build(data)
    horizon = max(b["end"] for b in bars)
    cmax = data["cmax"]
    colors = dict(STYLE)
    del colors["腔室加工"]
    colors.update({"4×1 加工": STYLE["腔室加工"], "2×2 加工": "#CB6955"})
    segments = defaultdict(list)
    cycles = data["cycles"]
    for b in bars:
        kind = b["action"]
        if kind == "腔室加工":
            middle = (b["start"] + b["end"])/2
            cy = next(c for c in cycles if b["lane"] == f"旋转腔 CH{c['chamber']}" and c["start"] <= middle < c["end"])
            kind = cy["mode"].replace("x", "×") + " 加工"
        segments[b["lane"], kind].append((b["start"], b["end"]))
    legend = [Patch(facecolor=color, label=("大气侧等待" if name == "LL大气等待" else name))
              for name, color in colors.items() if any(k == name for _, k in segments)]
    plt.rcParams.update({"font.sans-serif": ["Microsoft YaHei", "SimHei", "DejaVu Sans"], "axes.unicode_minus": False,
                         "pdf.fonttype": 42, "svg.fonttype": "path"})
    product_jobs = [j for j in data["jobs"] if j["product"]]
    def page(lo, hi, detail=False):
        fig, ax = plt.subplots(figsize=(14, 6.4))
        fig.subplots_adjust(left=.125, right=.975, top=.86, bottom=.22)
        title = f"{len(product_jobs)} 片混合配方排程"
        fig.text(.125, .941, title + ("  /  局部时序" if detail else "  /  全资源"), fontsize=20, weight="bold", color="#233442")
        fig.text(.975, .949, f"产品全部返回 {cmax:g} s     设备占用结束 {horizon:g} s",
                 ha="right", fontsize=11, color="#334956")
        for i, lane in enumerate(lanes):
            ax.axhspan(i-.46, i+.46, color="#F3F5F7" if i%2 == 0 else "#FFFFFF", lw=0, zorder=0)
            ax.axhline(i+.5, color="#DFE2E6", lw=.45, zorder=0)
            for kind, color in colors.items():
                parts = [(max(a, lo), min(b, hi)-max(a, lo)) for a, b in segments.get((lane, kind), ())
                         if a < hi and b > lo]
                if parts:
                    ax.broken_barh(parts, (i-.33, .66), facecolors=color, edgecolors="none")
        if detail:
            for c in cycles:
                left, right = max(lo, c["start"]), min(hi, c["end"])
                if right-left < 55:
                    continue
                products = sorted(j["pjob_index"] for j in product_jobs if j["pair"] in c["pairs"])
                task = next((j["pjob"].replace("Pjob", "P") for j in product_jobs if j["pair"] in c["pairs"]), "")
                numbers = ",".join(map(str, products))
                label = f"{task}[{numbers}]" if products else "清洁"
                ax.text((left+right)/2, lanes.index(f"旋转腔 CH{c['chamber']}"), label,
                        ha="center", va="center", color="white", fontsize=8.3, clip_on=True)
        if lo <= cmax <= hi:
            ax.axvline(cmax, ls="--", lw=1.1, color="#263540")
        if lo <= horizon <= hi:
            ax.axvline(horizon, ls=":", lw=1.1, color="#697782")
        display = ["真空辅助库 VS" if name == "VS" else name for name in lanes]
        ax.set_yticks(range(len(lanes)), display, fontsize=9.5)
        ax.set_ylim(len(lanes)-.5, -.5)
        ax.set_xlim(lo, hi)
        ax.xaxis.set_major_locator(MaxNLocator(nbins=12, integer=True))
        ax.tick_params(length=0, pad=5)
        ax.grid(axis="x", lw=.5, color="#DEE3E7")
        ax.set_axisbelow(True)
        ax.set_xlabel("时间 / s", fontsize=10)
        ax.spines[["top", "right", "left"]].set_visible(False)
        fig.legend(handles=legend, loc="lower center", bbox_to_anchor=(.54, .036), ncol=8,
                   frameon=False, fontsize=9, handlelength=1.2, columnspacing=1.25, labelspacing=.8)
        return fig

    fig = page(0, ceil(horizon*1.012))
    for ext in ("pdf", "svg", "png"):
        fig.savefig(dest / f"gantt_resources.{ext}", dpi=180, facecolor="white")
    plt.close(fig)
    pages = ceil(horizon/600)
    with PdfPages(dest/"gantt_details.pdf") as pdf:
        for index in range(pages):
            fig = page(index*600, (index+1)*600, detail=True)
            pdf.savefig(fig, facecolor="white")
            plt.close(fig)
    return dict(resource_end=horizon, cmax=cmax, lanes=lanes, explicit_events_covered=len(data["events"]),
                route_traces=len(traces), resource_intervals=len(bars), detail_pages=pages, seconds_per_page=600)

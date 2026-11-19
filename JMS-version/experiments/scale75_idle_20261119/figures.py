"""Overview and consecutively labelled 600-second pages on the verified resource lanes."""
from collections import defaultdict
from math import ceil

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.patches import Patch

from current_defaults_swimlane import STYLE, build
from idle import GAP


def draw(data, lanes_report, dest):
    dest.mkdir(exist_ok=True)
    lanes, bars, traces, _ = build(data)
    finish = data["cmax"]
    end = max(b["end"] for b in bars)
    total_idle = sum(v["idle_s"] for v in lanes_report.values())
    colors = {k:v for k, v in STYLE.items() if k != "腔室加工"}
    colors.update({"4×1 加工": STYLE["腔室加工"], "2×2 加工": "#CB6955"})
    groups = defaultdict(list)
    cycles = data["cycles"]
    for bar in bars:
        action = bar["action"]
        if action == "腔室加工":
            mid = (bar["start"] + bar["end"])/2
            cycle = next(c for c in cycles if f"旋转腔 CH{c['chamber']}" == bar["lane"] and c["start"] <= mid < c["end"])
            action = cycle["mode"].replace("x", "×") + " 加工"
        groups[bar["lane"], action].append((bar["start"], bar["end"]))
    products = defaultdict(list)
    for job in data["jobs"]:
        if job["product"]:
            products[job["pair"]].append(str(job["wafer_number"]))
    plt.rcParams.update({"font.sans-serif":["Microsoft YaHei", "SimHei", "DejaVu Sans"],
                         "pdf.fonttype":42, "svg.fonttype":"path", "axes.unicode_minus":False})
    used = {kind for _, kind in groups}
    legend = [Patch(facecolor=color, label={"LL大气等待":"大气侧等待"}.get(k,k))
              for k, color in colors.items() if k in used]
    count = ceil(end/600)

    def page(left, right, number=0):
        fig, ax = plt.subplots(figsize=(14, 6.6))
        fig.subplots_adjust(left=.13, right=.978, top=.82, bottom=.20)
        title = f"75 片混合配方排程  /  {'局部时序' if number else '全资源'}"
        fig.text(.13, .941, title, fontsize=19, weight="bold", color="#233442")
        page_label = f"第 {number} / {count} 页" if number else "全程"
        fig.text(.978, .948, f"{page_label}     末片返回 {finish:g} s     设备占用结束 {end:g} s",
                 fontsize=11, ha="right", color="#355266")
        fig.text(.13, .88, f"空闲优化求解间隙 {100*GAP:g}%     末片返回前 CH2 空闲 {lanes_report['2']['idle_s']:g} s"
                 f"     CH3 空闲 {lanes_report['3']['idle_s']:g} s     双腔平均空闲率 {100*total_idle/(2*finish):.2f}%",
                 fontsize=11, color="#355266")
        for index, lane in enumerate(lanes):
            ax.axhspan(index-.47, index+.47, color="#f3f5f7" if index%2 == 0 else "white", zorder=0)
            ax.axhline(index+.5, color="#dbe1e5", lw=.45, zorder=0)
            for kind in colors:
                spans = [(max(a,left), min(b,right)-max(a,left)) for a,b in groups.get((lane,kind), ())
                         if a < right and b > left]
                if spans:
                    ax.broken_barh(spans, (index-.32,.64), facecolors=colors[kind], edgecolors="none", zorder=2)
        if number:
            for cycle in cycles:
                a, b = max(left, cycle["start"]), min(right, cycle["end"])
                if b-a < 45:
                    continue
                ids = [n for pair in cycle["pairs"] for n in products.get(pair, ())]
                task = "P1" if cycle["mode"] == "4x1" else "P2"
                label = f"{task}[{','.join(ids)}]" if ids else "清洁"
                ax.text((a+b)/2, lanes.index(f"旋转腔 CH{cycle['chamber']}"), label, fontsize=7.1,
                        color="white", ha="center", va="center", clip_on=True)
        for bound, style in ((finish, "--"), (end, ":")):
            if left <= bound <= right:
                ax.axvline(bound, color="#263540", lw=.95, ls=style, zorder=3)
        ax.set_xlim(left, right)
        ax.set_ylim(len(lanes)-.45, -.52)
        ax.set_yticks(range(len(lanes)), ["真空辅助库 VS" if v=="VS" else v for v in lanes], fontsize=9)
        ax.tick_params(axis="both", length=0, pad=5, labelsize=9)
        ax.spines[["left","top","right"]].set_visible(False)
        ax.grid(axis="x", color="#cbd3d9", lw=.5)
        ax.set_axisbelow(True)
        ax.set_xlabel("时间 / s", fontsize=10)
        fig.legend(handles=legend, loc="lower center", bbox_to_anchor=(.55,.015), ncol=8,
                   frameon=False, fontsize=9, handlelength=1.25, columnspacing=1.2)
        return fig

    filenames = ["gantt_resources.png", "gantt_resources.pdf", "gantt_resources.svg", "gantt_details.pdf"]
    fig = page(0, end+max(30, .012*end))
    for filename in filenames[:3]:
        fig.savefig(dest/filename, dpi=180, facecolor="white")
    plt.close(fig)
    with PdfPages(dest/filenames[-1]) as pdf:
        for i in range(count):
            fig = page(600*i, 600*(i+1), i+1)
            pdf.savefig(fig)
            plt.close(fig)
    return dict(files=filenames, detail_pages=count, seconds_per_page=600, resource_end=end,
                product_return=finish, explicit_events=len(data["events"]), wafer_routes=len(traces), lanes=lanes)

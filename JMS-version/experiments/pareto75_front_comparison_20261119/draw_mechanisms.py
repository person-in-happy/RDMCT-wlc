"""Engineering choices and paired ablation effects, drawn from checked schedules."""
from collections import defaultdict
from statistics import median

import matplotlib.pyplot as plt
from matplotlib.ticker import MaxNLocator
from PIL import Image

from draw_lines import CASE_LABEL, CASES, FIG, REPORT, csvrows, finish, prettify, setup
from case_setup import read


def engineering():
    by_case = defaultdict(list)
    for row in csvrows(REPORT / "engineering_fronts.csv"):
        by_case[row["case"]].append((float(row["A"]), float(row["B"])))
    verified = read(REPORT / "mechanism_verified.json")["combined_points"]
    fig, axes = plt.subplots(1, 2, figsize=(8.05, 3.1))
    for ax, case in zip(axes, CASES):
        points = sorted(by_case[case])
        assert len(points) == verified[case]
        x, y = zip(*points)
        gap = max(x) - min(x)
        dy = max(y) - min(y)
        ax.step([*x, x[-1] + .06 * gap], [*y, y[-1]], where="post",
                color="#1d6259", lw=1.65, zorder=2)
        ax.plot(x, y, ls="", marker="o", ms=3.6, mfc="white", mec="#1d6259", mew=.9, zorder=3)
        ax.set(xlim=(x[0] - .06 * gap, x[-1] + .07 * gap),
               ylim=(y[-1] - .13 * dy, y[0] + .22 * dy), xlabel="交付期限 A（s）")
        prettify(ax)
        ax.set_title(f"{CASE_LABEL[case]}（{len(points)} 点）", fontsize=10)
        for a, b, off, ha in [(x[0], y[0], (4, 7), "left"), (x[-1], y[-1], (0, 9), "right")]:
            ax.annotate(f"({a:.11g}, {b:.11g})", (a, b), xytext=off, textcoords="offset points",
                        color="#223e3a", ha=ha, fontsize=8)
    axes[0].set_ylabel("期限内最低 B（加权秒）")
    fig.subplots_adjust(left=.09, right=.985, top=.87, bottom=.18, wspace=.23)
    finish(fig, "engineering75")


def ablations():
    by_key = {(r["case"], r["method"], int(r["seed"])): float(r["HV"])
              for r in csvrows(REPORT / "ablation_runs.csv")}
    cases = [("mix37", "#00705b", "o"), ("mix50", "#725197", "s")]
    seeds = sorted({s for _, _, s in by_key})
    fig, axes = plt.subplots(1, 2, figsize=(8.0, 3.15), sharey=True)
    for ax, (opponent, name) in zip(axes, (("no_blocks", "（a）保留局部生产块调整"),
                                          ("random_init", "（b）使用六类预设初始结构"))):
        ax.axhline(0, color="#4e5658", lw=.85)
        for ix, (case, color, mark) in enumerate(cases):
            vals = [by_key[case, "full", s] - by_key[case, opponent, s] for s in seeds]
            xs = [ix + (i-5.5)*.021 for i in range(len(vals))]
            ax.scatter(xs, vals, c=color, s=22, marker=mark, alpha=.8, zorder=3)
            middle = median(vals)
            ax.hlines(middle, ix-.22, ix+.22, lw=2.2, color=color, zorder=2)
        ax.set_xlim(-.53, 1.53)
        ax.set_xticks([0,1], ["37＋38 片", "50＋25 片"])
        ax.set_title(name, loc="left", fontsize=10)
        ax.grid(axis="y",color="#dde5e6",lw=.65)
        ax.yaxis.set_major_locator(MaxNLocator(nbins=6))
        ax.spines[["top", "right"]].set_visible(False)
        ax.tick_params(labelsize=9)
    axes[0].set_ylabel("配对 HV 差（完整方法减去消融方法）", fontsize=9)
    fig.subplots_adjust(left=.11, right=.985, top=.88, bottom=.15, wspace=.17)
    finish(fig, "paired75_ablation")


if __name__ == "__main__":
    setup()
    engineering()
    ablations()
    preview = REPORT / "visual"
    preview.mkdir(exist_ok=True)
    for file in FIG.glob("*.png"):
        with Image.open(file) as img:
            img.thumbnail((890, 570))
            img.convert("RGB").save(preview / (file.stem+".jpg"), quality=89)

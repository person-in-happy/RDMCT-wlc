"""Generate bilingual, publication-ready vector result figures.

The numerical values in this script are transcribed from the frozen experiment
records used by JMS_Review_CN.tex, the authors' canonical manuscript.  The
visual style uses compact grayscale multi-panel layouts, sans-serif text,
redundant line/marker/hatch encodings, minimal framing, and direct value labels.
"""

from __future__ import annotations

import csv
import re
import sys
from pathlib import Path

import matplotlib as mpl
mpl.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.lines import Line2D
from matplotlib.transforms import ScaledTranslation


OUT = Path(__file__).resolve().parent
QA = OUT / "qa_nature"
NATURE_SKILL_SCRIPTS = (
    Path(__file__).resolve().parents[3]
    / "nature-skills"
    / "skills"
    / "nature-figure"
    / "scripts"
)
sys.path.insert(0, str(NATURE_SKILL_SCRIPTS))
from audit_panel_alignment import require_matplotlib_panel_alignment

BLUE = "#0F4D92"
ORANGE = "#B64342"
CYAN = "#B4C0E4"
TEAL = "#42949E"
PURPLE = "#9A4D8E"
GREY = "#767676"
LIGHT_GREY = "#D8D8D8"
PALE_GREY = "#EEF3F8"
PALE_ORANGE = "#F6E7E5"
BLACK = "#272727"


def configure(lang: str) -> None:
    fonts = (
        ["Noto Sans CJK JP", "Microsoft YaHei", "SimHei", "Arial", "DejaVu Sans"]
        if lang == "cn"
        else ["Arial", "Helvetica", "DejaVu Sans"]
    )
    mpl.rcParams.update(
        {
            "font.family": "sans-serif",
            "font.sans-serif": fonts,
            "font.size": 7,
            "axes.titlesize": 8,
            "axes.labelsize": 7,
            "xtick.labelsize": 6.5,
            "ytick.labelsize": 6.5,
            "legend.fontsize": 6.5,
            "svg.fonttype": "none",
            "axes.linewidth": 0.55,
            "xtick.major.width": 0.55,
            "ytick.major.width": 0.55,
            "xtick.major.size": 3,
            "ytick.major.size": 3,
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
            "axes.unicode_minus": False,
            "savefig.facecolor": "white",
            "figure.facecolor": "white",
        }
    )


def clean_axis(ax: plt.Axes) -> None:
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.tick_params(direction="out", color=BLACK, labelcolor=BLACK)
    ax.xaxis.label.set_color(BLACK)
    ax.yaxis.label.set_color(BLACK)
    ax.title.set_color(BLACK)


def panel(ax: plt.Axes, letter: str) -> None:
    offset = ScaledTranslation(-4 / 72, 11 / 72, ax.figure.dpi_scale_trans)
    ax.text(
        0,
        1,
        letter,
        transform=ax.transAxes + offset,
        fontsize=9,
        fontweight="bold",
        va="top",
        ha="left",
        color=BLACK,
    )


def save(fig: plt.Figure, stem: str) -> None:
    QA.mkdir(exist_ok=True)
    nature_stem = f"{stem}_nature"
    require_matplotlib_panel_alignment(
        fig,
        json_out=QA / f"{nature_stem}.alignment.json",
        overlay_svg=QA / f"{nature_stem}.alignment.svg",
        require_panel_labels=True,
        strict=True,
    )
    fig.savefig(OUT / f"{nature_stem}.svg", bbox_inches="tight", pad_inches=0.025)
    fig.savefig(OUT / f"{nature_stem}.pdf", bbox_inches="tight", pad_inches=0.025)
    fig.savefig(OUT / f"{nature_stem}.png", dpi=600, bbox_inches="tight", pad_inches=0.025)
    plt.close(fig)


def annotate_bars(ax: plt.Axes, bars, labels: list[str], log: bool = False) -> None:
    for bar, label in zip(bars, labels):
        height = bar.get_height()
        y = height * 1.12 if log else height + max(ax.get_ylim()[1] * 0.018, 0.01)
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            y,
            label,
            ha="center",
            va="bottom",
            fontsize=6.2,
            color=BLACK,
        )


def _mode_efficiency_data() -> tuple[np.ndarray, dict[str, np.ndarray]]:
    """Load the exact equal-wafer-count mode comparison from frozen raw runs."""
    raw_path = (
        OUT.parents[1]
        / "cie"
        / "results"
        / "main"
        / "cie_main_600s_mem2048_repro_v1"
        / "combined"
        / "cie_combined_20260817_141536_raw.csv"
    )
    groups: dict[tuple[int, str], list[dict[str, str]]] = {}
    pattern = re.compile(r"_n(?P<n>\d+)_f(?P<f>\d+)_m(?P<m>\d+)_proc100\.lp$")
    with raw_path.open("r", encoding="utf-8-sig", newline="") as stream:
        for row in csv.DictReader(stream):
            if row.get("method") != "proposed":
                continue
            match = pattern.search(row.get("instance", ""))
            if not match:
                continue
            n = int(match.group("n"))
            full = int(match.group("f"))
            mixed = int(match.group("m"))
            if n not in (8, 16):
                continue
            if full == n and mixed == 0:
                mode = "pure41"
            elif full == 0 and mixed == n:
                mode = "pure22"
            elif full == mixed == n // 2:
                mode = "mixed11"
            else:
                continue
            groups.setdefault((n, mode), []).append(row)

    sizes = np.array([8, 16], dtype=int)
    values: dict[str, list[float]] = {"pure41": [], "pure22": [], "mixed11": []}
    for n in sizes:
        for mode in values:
            rows = groups.get((int(n), mode), [])
            if len(rows) != 25:
                raise RuntimeError(f"Expected 25 frozen runs for n={n}, mode={mode}; found {len(rows)}")
            if any(row.get("status") != "optimal" or abs(float(row.get("gap") or 0.0)) > 1e-8 for row in rows):
                raise RuntimeError(f"Mode comparison is not exact for n={n}, mode={mode}")
            objectives = np.array([float(row["best_objective"]) for row in rows], dtype=float)
            if float(np.ptp(objectives)) > 1e-3:
                raise RuntimeError(f"Inconsistent exact makespans for n={n}, mode={mode}")
            values[mode].append(float(np.mean(objectives)))
    return sizes, {key: np.asarray(item) for key, item in values.items()}


def validation(lang: str) -> None:
    """Experiment 1: controlled mode efficiency at identical wafer counts."""
    configure(lang)
    sizes, cmax = _mode_efficiency_data()
    throughput = {mode: 3600.0 * sizes / values for mode, values in cmax.items()}
    overhead = {
        mode: 100.0 * (cmax[mode] / cmax["pure41"] - 1.0)
        for mode in ("pure22", "mixed11")
    }
    labels = (
        {"pure41": "纯4×1", "pure22": "纯2×2", "mixed11": "1:1混跑"}
        if lang == "cn"
        else {"pure41": "Pure 4×1", "pure22": "Pure 2×2", "mixed11": "1:1 mixed"}
    )
    titles = (
        ["最优最大完工时间 Cmax (s)", "等效吞吐率 (片/h)", "相对纯4×1的完工时间增幅 (%)"]
        if lang == "cn"
        else ["Optimal makespan, Cmax (s)", "Effective throughput (wafers/h)", "Makespan increase over pure 4×1 (%)"]
    )
    banner = (
        "实验1｜相同晶圆数与时间参数下，纯4×1取得最短完工时间和最高吞吐率"
        if lang == "cn"
        else "Experiment 1 | At equal wafer counts and timing, pure 4×1 gives the shortest makespan and highest throughput"
    )
    style = {
        "pure41": dict(color=BLACK, linestyle="-", marker="o", markerfacecolor=BLACK),
        "pure22": dict(color="#666666", linestyle="--", marker="s", markerfacecolor="white"),
        "mixed11": dict(color="#999999", linestyle=":", marker="^", markerfacecolor="white"),
    }
    style['pure41'].update(color=BLUE, markerfacecolor=BLUE)
    style['pure22'].update(color=ORANGE, markerfacecolor='white')
    style['mixed11'].update(color=TEAL, markerfacecolor='white')
    fig, axes = plt.subplots(3, 1, figsize=(3.5, 5.6))

    offsets_a = {"pure41": (0, -13), "pure22": (-7, 8), "mixed11": (8, 8)}
    offsets_b = {"pure41": (0, 8), "pure22": (-7, 8), "mixed11": (8, -13)}
    for mode in ("pure41", "pure22", "mixed11"):
        axes[0].plot(sizes, cmax[mode], linewidth=1.25, markersize=4.8, markeredgecolor=BLACK,
                     markeredgewidth=0.65, label=labels[mode], **style[mode])
        axes[1].plot(sizes, throughput[mode], linewidth=1.25, markersize=4.8, markeredgecolor=BLACK,
                     markeredgewidth=0.65, label=labels[mode], **style[mode])
        for xv, yv in zip(sizes, cmax[mode]):
            axes[0].annotate(f"{yv:.0f}", (xv, yv), xytext=offsets_a[mode], textcoords="offset points",
                             ha="center", fontsize=6.2, fontweight="bold" if mode == "pure41" else "normal")
        for xv, yv in zip(sizes, throughput[mode]):
            axes[1].annotate(f"{yv:.2f}", (xv, yv), xytext=offsets_b[mode], textcoords="offset points",
                             ha="center", fontsize=6.2, fontweight="bold" if mode == "pure41" else "normal")
    for idx in (0, 1):
        axes[idx].set_xticks(sizes)
        axes[idx].set_xlabel("晶圆数" if lang == "cn" else "Wafers")
        axes[idx].set_ylim(0, max(max(series) for series in (cmax if idx == 0 else throughput).values()) * 1.18)
        axes[idx].set_title(titles[idx], loc="left", fontweight="bold", pad=5)
        clean_axis(axes[idx])
        panel(axes[idx], "ab"[idx])

    x = np.arange(len(sizes))
    width = 0.34
    bars22 = axes[2].bar(x - width / 2, overhead["pure22"], width, facecolor="white",
                         edgecolor=BLACK, linewidth=0.7, label=labels["pure22"])
    barsmix = axes[2].bar(x + width / 2, overhead["mixed11"], width, facecolor="#B8B8B8",
                          edgecolor=BLACK, linewidth=0.7, label=labels["mixed11"])
    for item in bars22:
        item.set_facecolor(PALE_ORANGE)
        item.set_edgecolor(ORANGE)
    for item in barsmix:
        item.set_facecolor('#DDF3EA')
        item.set_edgecolor(TEAL)
    axes[2].set_xticks(x, [str(value) for value in sizes])
    axes[2].set_xlabel("晶圆数" if lang == "cn" else "Wafers")
    axes[2].set_ylim(0, max(max(overhead["pure22"]), max(overhead["mixed11"])) * 1.24)
    axes[2].set_title(titles[2], loc="left", fontweight="bold", pad=5)
    annotate_bars(axes[2], bars22, [f"{value:.2f}" for value in overhead["pure22"]])
    annotate_bars(axes[2], barsmix, [f"{value:.2f}" for value in overhead["mixed11"]])
    clean_axis(axes[2])
    panel(axes[2], "c")

    handles = [
        Line2D([0], [0], color=style[mode]["color"], linestyle=style[mode]["linestyle"],
               marker=style[mode]["marker"], markerfacecolor=style[mode]["markerfacecolor"],
               markeredgecolor=BLACK, markersize=5, linewidth=1.2, label=labels[mode])
        for mode in ("pure41", "pure22", "mixed11")
    ]
    fig.legend(handles=handles, loc="lower center", ncol=3, frameon=False, bbox_to_anchor=(0.5, 0.005))
    fig.subplots_adjust(left=0.18, right=0.98, bottom=0.10, top=0.91, hspace=0.55)
    save(fig, f"fig01_validation_{lang}")

def dot_panel(
    ax: plt.Axes,
    values: list[float],
    labels: list[str],
    title: str,
    decimals: int,
    best_index: int,
    show_ylabels: bool,
    claim: str | None = None,
    primary: bool = False,
    baseline_indices: tuple[int, ...] = (0, 2),
) -> None:
    """Draw a publication-safe grayscale comparison with direct labels."""
    y = np.arange(len(labels))
    span = max(values) - min(values)
    pad = span * 0.14 if span else max(abs(values[0]) * 0.05, 1)
    focus_index = len(values) - 1
    ax.axhspan(focus_index - 0.38, focus_index + 0.38, color=PALE_GREY, zorder=0)
    ax.hlines(y, min(values) - pad * 0.2, values, color=LIGHT_GREY, linewidth=0.7, zorder=1)
    for idx, (xv, yv) in enumerate(zip(values, y)):
        is_focus = idx == focus_index
        is_baseline = idx in baseline_indices
        marker = "D" if is_focus else "o"
        face = BLACK if is_focus else ("white" if is_baseline else "#A7A7A7")
        if is_focus:
            face = BLUE
        elif is_baseline:
            face = GREY if idx == baseline_indices[0] else ORANGE
        else:
            face = CYAN
        ax.scatter(
            [xv],
            [yv],
            marker=marker,
            c=[face],
            s=48 if is_focus else (38 if is_baseline else 23),
            edgecolors=BLACK,
            linewidths=1.05 if is_baseline else (0.8 if is_focus else 0.35),
            zorder=4 if is_focus else 3,
        )
        ax.annotate(
            f"{xv:.{decimals}f}",
            xy=(xv, yv),
            xytext=(6.5 if is_focus else 5.5, 0),
            textcoords="offset points",
            va="center",
            ha="left",
            fontsize=6.35 if is_focus else 6.0,
            fontweight="bold" if (is_focus or is_baseline) else "normal",
            color=BLACK,
        )
    ax.set_xlim(min(values) - pad * 0.35, max(values) + pad * 1.8)
    ax.set_ylim(-0.65, len(labels) + (0.65 if claim else -0.35))
    ax.set_yticks(y, labels if show_ylabels else [""] * len(labels))
    if show_ylabels:
        for baseline_index in baseline_indices:
            ax.get_yticklabels()[baseline_index].set_fontweight("bold")
        ax.get_yticklabels()[-1].set_fontweight("bold")
    ax.invert_yaxis()
    ax.set_title(title, loc="left", fontweight="bold", pad=5, color=BLACK)
    clean_axis(ax)

def nominal(lang: str) -> None:
    configure(lang)
    labels = (
        ["纯SCIP基线", "ACS组件消融", "HEM基线", "HEM+Beam消融", "仅23D角色消融", "结构+贪心消融", "完整RDMCT-HBS"]
        if lang == "cn"
        else ["Pure SCIP baseline", "ACS ablation", "HEM baseline", "HEM+Beam ablation", "23D-role ablation", "Struct.+Greedy ablation", "Full RDMCT-HBS"]
    )
    titles = (
        ["与HEM基线比较｜平均PDI（越低越好）", "与HEM基线比较｜平均求解时间 (s)", "与HEM基线比较｜SCIP终止相对gap (%)", "与HEM基线比较｜证明最优率 (%)"]
        if lang == "cn"
        else ["Against HEM | Mean PDI (lower is better)", "Against HEM | Mean solve time (s)", "Against HEM | SCIP terminal relative gap (%)", "Against HEM | Proven optimal (%)"]
    )
    datasets = [
        ([16919.01, 16854.87, 16823.18, 16829.59, 16620.91, 16598.11, 16585.70], 2, 6),
        ([226.05, 222.34, 219.65, 219.95, 219.42, 218.44, 218.32], 2, 6),
        ([119.54, 127.18, 127.24, 127.19, 125.33, 126.03, 126.01], 2, 0),
        ([64.0, 62.0, 62.4, 62.4, 62.6, 63.2, 63.2], 1, 0),
    ]
    claims = (
        ["相对HEM：PDI降低1.41%", "相对HEM：时间降低0.61%", "相对HEM：gap降低0.97%", "相对HEM：提高0.80个百分点"]
        if lang == "cn"
        else ["vs HEM: 1.41% lower PDI", "vs HEM: 0.61% less time", "vs HEM: 0.97% lower gap", "vs HEM: +0.80 percentage points"]
    )
    fig, axes = plt.subplots(4, 1, figsize=(3.5, 7.0))
    for idx, (ax, title, data) in enumerate(zip(axes.flat, titles, datasets)):
        values, decimals, best_idx = data
        dot_panel(
            ax, values, labels, title, decimals, best_idx,
            show_ylabels=True, claim=claims[idx], primary=idx < 2, baseline_indices=(0, 2),
        )
        panel(ax, "abcd"[idx])
    legend = [
        Line2D([0], [0], marker="o", color="none", markerfacecolor="white", markeredgecolor=BLACK, markeredgewidth=1.0, markersize=6,
               label="基线：纯SCIP / HEM" if lang == "cn" else "Baselines: pure SCIP / HEM"),
        Line2D([0], [0], marker="o", color="none", markerfacecolor="#A7A7A7", markeredgecolor=BLACK, markersize=6,
               label="本方法组件消融" if lang == "cn" else "Proposed-method component ablations"),
        Line2D([0], [0], marker="D", color="none", markerfacecolor=BLACK, markeredgecolor=BLACK, markersize=6,
               label="完整RDMCT-HBS" if lang == "cn" else "Complete RDMCT-HBS"),
    ]
    fig.legend(handles=legend, loc="lower center", ncol=1, frameon=False, bbox_to_anchor=(0.5, -0.004))
    fig.subplots_adjust(left=0.39, right=0.98, bottom=0.16, top=0.98, hspace=0.50)
    save(fig, f"fig02_nominal_{lang}")


def spbs(lang: str) -> None:
    configure(lang)
    labels = ["SPBS", "无初始解"] if lang == "cn" else ["SPBS", "No start"]
    titles = (
        ["可行incumbent获得率 (%)", "平均PDI（越低越好）"]
        if lang == "cn"
        else ["Feasible-incumbent availability (%)", "Mean PDI (lower is better)"]
    )
    datasets = [([100.00, 51.67], ["100.00", "51.67"]), ([20278.78, 27473.05], ["20278.78", "27473.05"])]
    callouts = (
        ["+48.33 个百分点", "PDI降低26.19%"]
        if lang == "cn"
        else ["+48.33 percentage points", "26.19% lower PDI"]
    )
    banner = (
        "SPBS：完整可行排程获得率达到100%，且显著降低求解窗口内PDI"
        if lang == "cn"
        else "SPBS: 100% complete-schedule availability with substantially lower in-window PDI"
    )
    fig, axes = plt.subplots(2, 1, figsize=(3.5, 3.8))
    for idx, (ax, title, data) in enumerate(zip(axes, titles, datasets)):
        values, texts = data
        bars = ax.bar(np.arange(2), values, width=0.58, color=["white", "#D0D0D0"],
                      edgecolor=BLACK, linewidth=0.7)
        bars[0].set_facecolor(BLUE)
        bars[0].set_edgecolor(BLUE)
        bars[1].set_facecolor(PALE_ORANGE)
        bars[1].set_edgecolor(ORANGE)
        ax.set_xticks(np.arange(2), labels)
        ax.get_xticklabels()[0].set_fontweight("bold")
        ax.set_ylim(0, max(values) * 1.26)
        ax.set_title(title, loc="left", fontweight="bold", pad=5)
        annotate_bars(ax, bars, texts)
        clean_axis(ax)
        panel(ax, "ab"[idx])
    fig.subplots_adjust(left=0.18, right=0.98, bottom=0.10, top=0.97, hspace=0.50)
    save(fig, f"fig03_spbs_{lang}")


def workflow(lang: str) -> None:
    configure(lang)
    labels = ["完整两阶段", "二次目标", "单阶段"] if lang == "cn" else ["Full two-stage", "Quadratic", "Single-stage"]
    titles = (
        ["路线总等待", "路线最大等待", "节拍变异系数", "节拍偏差"]
        if lang == "cn"
        else ["Route-total wait", "Route-maximum wait", "Cadence CV", "Cadence deviation"]
    )
    datasets = [
        ([2596.01, 2469.47, 5398.60], ["2596.01", "2469.47", "5398.60"]),
        ([296.33, 293.27, 952.57], ["296.33", "293.27", "952.57"]),
        ([0.130, 0.134, 0.216], ["0.130", "0.134", "0.216"]),
        ([22.04, 60.18, 370.41], ["22.04", "60.18", "370.41"]),
    ]
    reductions = ["↓ 51.91%", "↓ 68.89%", "↓ 39.70%", "↓ 94.05%"]
    banner = (
        "同为600 s总预算：完整两阶段工作流在四项运行指标上均优于单阶段"
        if lang == "cn"
        else "Same 600-s budget: the full two-stage workflow improves all four operational metrics over single-stage"
    )
    fig, axes = plt.subplots(2, 2, figsize=(3.5, 4.5))
    for idx, (ax, title, data) in enumerate(zip(axes.flat, titles, datasets)):
        values, texts = data
        bars = ax.bar(np.arange(3), values, width=0.62, color=["white", "#A0A0A0", "#D6D6D6"],
                      edgecolor=BLACK, linewidth=0.7)
        for bar, face, edge in zip(
            bars, (BLUE, TEAL, PALE_ORANGE), (BLUE, TEAL, ORANGE)
        ):
            bar.set_facecolor(face)
            bar.set_edgecolor(edge)
        ax.set_xticks(np.arange(3), labels)
        plt.setp(
            ax.get_xticklabels(), rotation=32, ha="right",
            rotation_mode="anchor", fontsize=5.6,
        )
        ax.get_xticklabels()[0].set_fontweight("bold")
        ax.set_ylim(0, max(values) * 1.29)
        ax.set_title(title, loc="left", fontweight="bold", pad=5)
        annotate_bars(ax, bars, texts)
        clean_axis(ax)
        panel(ax, "abcd"[idx])
    fig.subplots_adjust(left=0.16, right=0.98, bottom=0.14, top=0.97, wspace=0.34, hspace=0.58)
    save(fig, f"fig04_workflow_{lang}")


def line_panel(ax: plt.Axes, x, y, title: str, texts: list[str]) -> None:
    ax.plot(x, y, color=BLACK, linewidth=1.2, marker="o", markersize=4.2,
            markerfacecolor="white", markeredgecolor=BLACK, markeredgewidth=0.7)
    for line in ax.lines:
        line.set_color(BLUE)
        line.set_markerfacecolor('white')
        line.set_markeredgecolor(BLUE)
    for xv, yv, text_value in zip(x, y, texts):
        ax.annotate(text_value, (xv, yv), xytext=(0, 12), textcoords="offset points", ha="center", fontsize=6.0)
    ax.set_xticks(x)
    ax.set_ylim(0, max(y) * 1.35)
    ax.set_title(title, loc="left", fontweight="bold", pad=5)
    clean_axis(ax)


def doe(lang: str) -> None:
    configure(lang)
    x = [8, 16, 24, 32]
    titles = (
        ["平均PDI", "证明最优率 (%)", "平均求解时间 (s)"]
        if lang == "cn"
        else ["Mean PDI", "Proven optimal (%)", "Mean solve time (s)"]
    )
    datasets = [
        ([28.13, 1876.54, 31155.94, 32959.89], ["28.13", "1876.54", "31155.94", "32959.89"]),
        ([100, 100, 36, 20], ["100", "100", "36", "20"]),
        ([0.34, 33.86, 408.55, 433.20], ["0.34", "33.86", "408.55", "433.20"]),
    ]
    fig, axes = plt.subplots(3, 1, figsize=(3.5, 4.8))
    for idx, (ax, title, data) in enumerate(zip(axes, titles, datasets)):
        line_panel(ax, x, data[0], title, data[1])
        ax.set_xlabel("晶圆数" if lang == "cn" else "Wafers")
        panel(ax, "abc"[idx])
    fig.subplots_adjust(left=0.20, right=0.98, bottom=0.09, top=0.98, hspace=0.55)
    save(fig, f"fig05_doe_{lang}")


def ood(lang: str) -> None:
    configure(lang)
    labels = (
        ["纯SCIP基线", "ACS组件消融", "HEM基线", "HEM+Beam消融", "仅23D角色消融", "结构+贪心消融", "完整RDMCT-HBS"]
        if lang == "cn"
        else ["Pure SCIP baseline", "ACS ablation", "HEM baseline", "HEM+Beam ablation", "23D-role ablation", "Struct.+Greedy ablation", "Full RDMCT-HBS"]
    )
    titles = (
        ["分布外平均PDI", "SCIP分布外终止相对gap (%)"]
        if lang == "cn"
        else ["OOD mean PDI", "SCIP OOD terminal relative gap (%)"]
    )
    datasets = [
        ([73670.99, 70915.54, 73003.59, 73165.58, 74187.22, 73507.76, 73919.15], 2, 1),
        ([171.35, 160.78, 165.88, 167.04, 169.96, 168.54, 170.02], 2, 1),
    ]
    banner = (
        "规模扩展证据：40-64片的729次分布外运行全部返回经检查的可行排程"
        if lang == "cn"
        else "Scale-up evidence: all 729 OOD runs with 40-64 wafers return checked feasible schedules"
    )
    fig, axes = plt.subplots(2, 1, figsize=(3.5, 4.7))
    for idx, (ax, title, data) in enumerate(zip(axes, titles, datasets)):
        values, decimals, best_idx = data
        dot_panel(ax, values, labels, title, decimals, best_idx, show_ylabels=True, baseline_indices=(0, 2))
        panel(ax, "ab"[idx])
    legend = [
        Line2D([0], [0], marker="o", color="none", markerfacecolor="white", markeredgecolor=BLACK, markeredgewidth=1.0, markersize=6,
               label="基线：纯SCIP / HEM" if lang == "cn" else "Baselines: pure SCIP / HEM"),
        Line2D([0], [0], marker="o", color="none", markerfacecolor="#A7A7A7", markeredgecolor=BLACK, markersize=6,
               label="本方法组件消融" if lang == "cn" else "Proposed-method component ablations"),
        Line2D([0], [0], marker="D", color="none", markerfacecolor=BLACK, markeredgecolor=BLACK, markersize=6,
               label="完整RDMCT-HBS" if lang == "cn" else "Complete RDMCT-HBS"),
    ]
    fig.legend(handles=legend, loc="lower center", ncol=1, frameon=False, bbox_to_anchor=(0.5, -0.002))
    fig.subplots_adjust(left=0.40, right=0.98, bottom=0.14, top=0.97, hspace=0.50)
    save(fig, f"fig06_ood_{lang}")

def main() -> None:
    for lang in ("cn", "en"):
        nominal(lang)
        spbs(lang)
        workflow(lang)
        doe(lang)
        ood(lang)


if __name__ == "__main__":
    main()

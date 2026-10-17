"""Rebuild resource Gantt figures as editable vectors.

The source SVGs are parsed for resource, start, finish, and action identity.
Each representative figure retains one continuous time axis from release to
the last product-wafer return.  Post-production terminal cleaning is excluded
from this product-performance horizon.
The legacy Gantt assets are never overwritten; new files use ``_nature``.
"""

from __future__ import annotations

from dataclasses import dataclass
from html import unescape
from pathlib import Path
import re
import sys
import xml.etree.ElementTree as ET

import matplotlib as mpl

mpl.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.font_manager import FontProperties
from matplotlib.patches import Patch


JMS = Path(__file__).resolve().parents[1]
SOURCE = JMS / "results" / "wafer_multiscale_gantt" / "gantt"
REPRESENTATIVE_CASES = (
    (
        JMS
        / "results"
        / "wafer_multiscale_gantt"
        / "gantt"
        / "wafer16_41_clean10_20260826",
        "fig_resource_gantt_cleanH10_w16_41",
        1632.0,
    ),
    (
        JMS
        / "results"
        / "wafer_multiscale_gantt"
        / "gantt_cycle_mapping_20260907"
        / "wafer16_22_clean10",
        "fig_resource_gantt_cleanH10_w16_22",
        492.0,
    ),
    (
        JMS
        / "results"
        / "wafer_multiscale_gantt"
        / "3xclean"
        / "gantt"
        / "wafer16_41_clean3_20260826",
        "fig_resource_gantt_cleanH3_w16_41",
        1632.0,
    ),
    (
        JMS
        / "results"
        / "wafer_multiscale_gantt"
        / "gantt_cycle_mapping_20260907"
        / "wafer16_22_clean3_productcmax_20260903",
        "fig_resource_gantt_cleanH3_w16_22",
        536.0,
    ),
)
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


CASES = {
    8: (("41", "wafer8_41_clean10_20260826"), ("22", "wafer8_22_clean10_20260826"), ("mix", "wafer8_mix_4_4_clean10_20260826")),
    16: (("41", "wafer16_41_clean10_20260826"), ("22", "wafer16_22_clean10_20260826"), ("mix", "wafer16_mix_8_8_clean10_20260826")),
    17: (("41", "wafer17_41_20260825"), ("22", "wafer17_22_20260825"), ("mix", "wafer17_mix_9_8_20260825")),
    20: (("41", "wafer20_41_20260825"), ("22", "wafer20_22_20260825"), ("mix", "wafer20_mix_10_10_20260825")),
}

# Original action colors are stable identifiers in the frozen SVGs.  The new
# colors retain those identities while reducing saturation and separating
# related ATR, LL, VTR, chamber, and empty-move families.
ACTION_STYLE = (
    ("#4C78A8", "#0F4D92", "ATR pick", "ATR抓取"),
    ("#72B7B2", "#5B8FD6", "ATR loaded move", "ATR带片搬运"),
    ("#9C755F", "#9A4D8E", "ATR place / AL", "ATR放片/AL校准"),
    ("#D37295", "#C45AD6", "AL wafer exchange", "AL换片"),
    ("#59A14F", "#4E8A65", "LL pump", "LL抽气"),
    ("#8CD17D", "#AADCA9", "LL vacuum wait", "LL真空等待"),
    ("#B279A2", "#B86F6F", "LL vent", "LL放气"),
    ("#D4A6C8", "#E4CCD8", "LL atmosphere wait", "LL大气等待"),
    ("#F58518", "#E28E2C", "VTR / LL load", "VTR/LL装片"),
    ("#76B7B2", "#33B5A5", "VTR loaded / bridge", "VTR带片/桥接搬运"),
    ("#FF9DA6", "#D9544D", "VTR unload", "VTR卸片"),
    ("#E45756", "#B64342", "PM process / PEC support", "腔室加工"),
    ("#2A9D8F", "#188977", "Chamber clean", "腔室清洁"),
    ("#F2A09A", "#F6CFCB", "Chamber wait", "腔室等待"),
    ("#BAB0AC", "#A8A8A8", "Empty move / reset / exchange", "空载移动/复位/交换"),
)
COLOR_MAP = {source.upper(): target for source, target, _, _ in ACTION_STYLE}

LANE_CN = {
    "ATR robot": "ATR机械手",
    "AL": "对准器 AL",
    "LLupper slot 1": "上装载锁槽1",
    "LLupper slot 2": "上装载锁槽2",
    "VTR robot": "VTR机械手",
    "CH2 PM": "旋转腔 CH2",
    "CH3 PM": "旋转腔 CH3",
    "LLlower slot 1": "下装载锁槽1",
    "LLlower slot 2": "下装载锁槽2",
}


@dataclass(frozen=True)
class Task:
    lane: str
    start: float
    end: float
    source_color: str
    source_y: float


@dataclass(frozen=True)
class Metrics:
    horizon: float
    cmax: float
    wph: float
    completed: int


def configure(language: str) -> None:
    fonts = (
        ["Microsoft YaHei", "Noto Sans CJK JP", "Arial", "DejaVu Sans"]
        if language == "cn"
        else ["Arial", "Helvetica", "DejaVu Sans"]
    )
    mpl.rcParams.update({
        "font.family": "sans-serif",
        "font.sans-serif": fonts,
        "font.size": 6,
        "axes.labelsize": 6,
        "xtick.labelsize": 5.2,
        "ytick.labelsize": 5.2,
        "axes.linewidth": 0.65,
        "xtick.major.width": 0.55,
        "xtick.major.size": 2.5,
        "legend.frameon": False,
        "pdf.fonttype": 42,
        "ps.fonttype": 42,
        "svg.fonttype": "none",
        "figure.facecolor": "white",
        "savefig.facecolor": "white",
    })


def source_path(case_dir: Path) -> Path:
    stem = case_dir.name
    resource = case_dir / f"{stem}_resources_gantt.svg"
    if resource.exists():
        return resource
    candidates = sorted(case_dir.glob("*_resources_gantt.svg"))
    if len(candidates) == 1:
        return candidates[0]
    raise FileNotFoundError(resource)


def parse_source(path: Path) -> tuple[list[Task], list[str], Metrics]:
    source = path.read_text(encoding="utf-8")
    root = ET.fromstring(source)
    ns = {"svg": "http://www.w3.org/2000/svg"}
    tasks: list[Task] = []
    lane_positions: dict[str, float] = {}
    for group in root.findall(".//svg:g[@class='task']", ns):
        tooltip = unescape(group.attrib.get("data-tooltip", ""))
        lane_match = re.search(r"(?:^|\n)lane:\s*(.+)", tooltip)
        start_match = re.search(r"(?:^|\n)start:\s*([-+0-9.eE]+)", tooltip)
        end_match = re.search(r"(?:^|\n)end:\s*([-+0-9.eE]+)", tooltip)
        rect = group.find("svg:rect", ns)
        if rect is None or not (lane_match and start_match and end_match):
            continue
        lane = lane_match.group(1).strip()
        source_y = float(rect.attrib.get("y", "0"))
        lane_positions.setdefault(lane, source_y)
        tasks.append(Task(
            lane=lane,
            start=float(start_match.group(1)),
            end=float(end_match.group(1)),
            source_color=rect.attrib.get("fill", "#BAB0AC").upper(),
            source_y=source_y,
        ))
    if not tasks:
        raise RuntimeError(f"No resource tasks parsed from {path}")
    lanes = [name for name, _ in sorted(lane_positions.items(), key=lambda item: item[1])]

    horizon_match = re.search(r"horizon=([-+0-9.eE]+)", source)
    cmax_match = re.search(r"c_max=([-+0-9.eE]+)", source)
    wph_match = re.search(r"WPH=([-+0-9.eE]+)", source)
    completed_match = re.search(r"completed=(\d+)", source)
    if not (cmax_match and wph_match and completed_match):
        raise RuntimeError(f"Missing Cmax/WPH metrics in {path}")
    horizon = float(horizon_match.group(1)) if horizon_match else max(task.end for task in tasks)
    metrics = Metrics(
        horizon=horizon,
        cmax=float(cmax_match.group(1)),
        wph=float(wph_match.group(1)),
        completed=int(completed_match.group(1)),
    )
    return tasks, lanes, metrics


def draw_gantt(axis, tasks: list[Task], lanes: list[str], start: float, end: float, language: str) -> None:
    y_lookup = {lane: len(lanes) - 1 - index for index, lane in enumerate(lanes)}
    for task in tasks:
        left = max(task.start, start)
        right = min(task.end, end)
        if right <= left:
            continue
        axis.barh(
            y_lookup[task.lane],
            right - left,
            left=left,
            height=0.62,
            color=COLOR_MAP.get(task.source_color, "#A8A8A8"),
            edgecolor="white",
            linewidth=0.18,
            align="center",
        )
    axis.set_xlim(start, end)
    axis.set_ylim(-0.6, len(lanes) - 0.4)
    axis.set_yticks(
        [y_lookup[lane] for lane in lanes],
        [LANE_CN.get(lane, lane) if language == "cn" else lane for lane in lanes],
    )
    ticks = np.linspace(start, end, 5)
    axis.set_xticks(ticks)
    axis.set_xticklabels([f"{value:.0f}" for value in ticks])
    tick_labels = axis.get_xticklabels()
    tick_labels[0].set_ha("left")
    tick_labels[-1].set_ha("right")
    axis.set_xlabel("时间 (s)" if language == "cn" else "Time (s)", labelpad=1.5)
    axis.spines["top"].set_visible(False)
    axis.spines["right"].set_visible(False)
    axis.spines["left"].set_visible(False)
    axis.tick_params(axis="y", length=0, pad=2)
    axis.tick_params(axis="x", direction="out", pad=1.5)


def compose(size: int) -> None:
    for mode, folder in CASES[size]:
        tasks, lanes, metrics = parse_source(source_path(SOURCE / folder))
        for language in ("cn", "en"):
            configure(language)
            fig, axis = plt.subplots(1, 1, figsize=(3.50, 3.50))
            draw_gantt(axis, tasks, lanes, 0.0, metrics.horizon, language)
            axis.axvline(metrics.cmax, color="#272727", linewidth=0.7, linestyle=(0, (3, 2)))
            axis.text(
                metrics.cmax,
                len(lanes) - 0.28,
                "Cmax",
                ha="right",
                va="bottom",
                fontsize=5.2,
                fontweight="bold",
            )

            family = "Microsoft YaHei" if language == "cn" else "Arial"
            handles = [
                Patch(
                    facecolor=target,
                    edgecolor="none",
                    label=cn_label if language == "cn" else en_label,
                )
                for _, target, en_label, cn_label in ACTION_STYLE
            ]
            metric_text = (
                f"WPH {metrics.wph:.2f} 片/h   |   完成 {metrics.completed} 片   |   Cmax {metrics.cmax:.0f} s"
                if language == "cn"
                else f"WPH {metrics.wph:.2f} wafers/h   |   {metrics.completed} completed   |   Cmax {metrics.cmax:.0f} s"
            )
            fig.text(0.54, 0.245, metric_text, ha="center", va="center", fontsize=7.0, fontweight="bold")
            fig.legend(
                handles=handles,
                loc="lower center",
                ncol=3,
                frameon=False,
                prop=FontProperties(family=family, size=5.0),
                handlelength=1.25,
                handleheight=0.75,
                columnspacing=0.60,
                labelspacing=0.40,
                bbox_to_anchor=(0.53, 0.012),
            )
            fig.subplots_adjust(left=0.30, right=0.985, top=0.96, bottom=0.36)

            QA.mkdir(exist_ok=True)
            stem = f"fig_resource_gantt_w{size}_{mode}_{language}_nature"
            require_matplotlib_panel_alignment(
                fig,
                axes=[axis],
                panel_ids=["a"],
                require_panel_labels=False,
                json_out=QA / f"{stem}.alignment.json",
                overlay_svg=QA / f"{stem}.alignment.svg",
                strict=True,
            )
            fig.savefig(OUT / f"{stem}.svg")
            fig.savefig(OUT / f"{stem}.pdf")
            fig.savefig(OUT / f"{stem}.png", dpi=600)
            plt.close(fig)


def compose_representative(case_dir: Path, base_stem: str, route_total_wait: float) -> None:
    """Render one validated product-horizon schedule in both languages."""
    tasks, lanes, metrics = parse_source(source_path(case_dir))
    for language in ("cn", "en"):
        configure(language)
        fig, axis = plt.subplots(1, 1, figsize=(3.50, 3.65))
        draw_gantt(axis, tasks, lanes, 0.0, metrics.cmax, language)
        axis.axvline(metrics.cmax, color="#272727", linewidth=0.7, linestyle=(0, (3, 2)))
        axis.text(
            metrics.cmax,
            len(lanes) - 0.28,
            "Cmax",
            ha="right",
            va="bottom",
            fontsize=5.2,
            fontweight="bold",
        )
        family = "Microsoft YaHei" if language == "cn" else "Arial"
        handles = [
            Patch(
                facecolor=target,
                edgecolor="none",
                label=cn_label if language == "cn" else en_label,
            )
            for _, target, en_label, cn_label in ACTION_STYLE
        ]
        metric_text = (
            f"WPH {metrics.wph:.2f} 片/h   |   Cmax {metrics.cmax:.0f} s   |   路线总等待 {route_total_wait:.0f} s"
            if language == "cn"
            else f"WPH {metrics.wph:.2f} wafers/h   |   Cmax {metrics.cmax:.0f} s   |   Total route wait {route_total_wait:.0f} s"
        )
        fig.text(0.54, 0.255, metric_text, ha="center", va="center", fontsize=7.0, fontweight="bold")
        fig.legend(
            handles=handles,
            loc="lower center",
            ncol=3,
            frameon=False,
            prop=FontProperties(family=family, size=5.0),
            handlelength=1.25,
            handleheight=0.75,
            columnspacing=0.60,
            labelspacing=0.40,
            bbox_to_anchor=(0.53, 0.012),
        )
        fig.subplots_adjust(left=0.30, right=0.985, top=0.96, bottom=0.39)
        QA.mkdir(exist_ok=True)
        stem = f"{base_stem}_{language}_nature"
        require_matplotlib_panel_alignment(
            fig,
            axes=[axis],
            panel_ids=["a"],
            require_panel_labels=False,
            json_out=QA / f"{stem}.alignment.json",
            overlay_svg=QA / f"{stem}.alignment.svg",
            strict=True,
        )
        fig.savefig(OUT / f"{stem}.svg")
        fig.savefig(OUT / f"{stem}.pdf")
        fig.savefig(OUT / f"{stem}.png", dpi=600)
        fig.savefig(OUT / f"{stem}.tiff", dpi=600)
        plt.close(fig)


if __name__ == "__main__":
    for wafer_count in CASES:
        compose(wafer_count)
    for representative_dir, representative_stem, route_total_wait in REPRESENTATIVE_CASES:
        compose_representative(representative_dir, representative_stem, route_total_wait)

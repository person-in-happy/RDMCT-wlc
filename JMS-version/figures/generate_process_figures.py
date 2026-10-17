"""Generate editable bilingual process schematics for the JMS manuscript.

The manuscript includes the generated PDF files.  Matching SVG files retain
individual text and geometry objects so that later topology or label changes
can be made without editing the manuscript source.
"""

from __future__ import annotations

from pathlib import Path
import sys

import matplotlib as mpl
mpl.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Circle, FancyArrowPatch, FancyBboxPatch, Polygon, Rectangle


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

BLACK = "#272727"
DARK = "#4D4D4D"
MID = "#A8A8A8"
LIGHT = "#E0F0F0"
PALE = "#F0E0D0"
WHITE = "#FFFFFF"
PRODUCT = "#0F4D92"
PRODUCT_RETURN = "#5B8FD6"
DUMMY = "#E28E2C"
DUMMY_RETURN = "#D24B40"
CHAIN_P2 = "#42949E"
CHAIN_P3 = "#9A4D8E"


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
            "axes.linewidth": 0.8,
            "legend.frameon": False,
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
            "svg.fonttype": "none",
            "axes.unicode_minus": False,
            "figure.facecolor": WHITE,
            "savefig.facecolor": WHITE,
        }
    )


def new_canvas(width: float, height: float, xlim, ylim):
    fig, ax = plt.subplots(figsize=(width, height))
    ax.set_xlim(*xlim)
    ax.set_ylim(*ylim)
    ax.set_aspect("equal")
    ax.axis("off")
    return fig, ax


def save(fig: plt.Figure, stem: str) -> None:
    QA.mkdir(exist_ok=True)
    nature_stem = f"{stem}_nature"
    require_matplotlib_panel_alignment(
        fig,
        json_out=QA / f"{nature_stem}.alignment.json",
        overlay_svg=QA / f"{nature_stem}.alignment.svg",
        require_panel_labels=False,
        strict=True,
    )
    fig.savefig(OUT / f"{nature_stem}.svg", bbox_inches="tight", pad_inches=0.025)
    fig.savefig(OUT / f"{nature_stem}.pdf", bbox_inches="tight", pad_inches=0.025)
    fig.savefig(OUT / f"{nature_stem}.png", dpi=600, bbox_inches="tight", pad_inches=0.025)
    plt.close(fig)


def rounded_box(ax, xy, width, height, text, *, face=WHITE, edge=DARK, size=7.2, weight="normal"):
    patch = FancyBboxPatch(
        xy,
        width,
        height,
        boxstyle="round,pad=0.02,rounding_size=0.035",
        linewidth=0.75,
        edgecolor=edge,
        facecolor=face,
        zorder=3,
    )
    ax.add_patch(patch)
    ax.text(
        xy[0] + width / 2,
        xy[1] + height / 2,
        text,
        ha="center",
        va="center",
        fontsize=size,
        fontweight=weight,
        color=BLACK,
        zorder=4,
    )
    return patch


def directed(
    ax,
    start,
    end,
    *,
    dashed=False,
    connection="arc3",
    width=0.9,
    color=BLACK,
    z=5,
    style=None,
):
    arrow = FancyArrowPatch(
        start,
        end,
        arrowstyle="-|>",
        mutation_scale=8,
        linewidth=width,
        linestyle=style if style is not None else ((0, (4, 2.5)) if dashed else "solid"),
        color=color,
        connectionstyle=connection,
        shrinkA=1,
        shrinkB=1,
        zorder=z,
    )
    ax.add_patch(arrow)
    return arrow


def orthogonal(ax, points, *, dashed=False, width=0.9, color=BLACK, z=5):
    """Draw an arrow using only horizontal and vertical line segments."""
    style = (0, (4, 2.5)) if dashed else "solid"
    for start, end in zip(points[:-2], points[1:-1]):
        ax.plot(
            [start[0], end[0]],
            [start[1], end[1]],
            color=color,
            linewidth=width,
            linestyle=style,
            solid_capstyle="butt",
            zorder=z,
        )
    return directed(
        ax,
        points[-2],
        points[-1],
        dashed=dashed,
        connection="arc3",
        width=width,
        color=color,
        z=z,
    )


def chamber(ax, center, name, label_xy):
    x, y = center
    ax.add_patch(Circle((x, y), 1.03, facecolor=WHITE, edgecolor=DARK, linewidth=0.8, zorder=2))
    for dx, dy in ((-0.4, 0.4), (0.4, 0.4), (-0.4, -0.4), (0.4, -0.4)):
        ax.add_patch(Circle((x + dx, y + dy), 0.27, facecolor=LIGHT, edgecolor=DARK, linewidth=0.65, zorder=3))
    ax.text(*label_xy, name, ha="center", va="center", fontsize=8, fontweight="bold", color=BLACK)


def robot(ax, center, label: str, hands: int, radius: float) -> None:
    """Draw an articulated transfer robot whose fork grippers face upward."""
    x, y = center
    ax.add_patch(Circle((x, y), radius, facecolor=PALE, edgecolor=DARK, linewidth=0.85, zorder=3))
    ax.add_patch(
        Polygon(
            (
                (x - 0.20 * radius, y - 0.36 * radius),
                (x + 0.20 * radius, y - 0.36 * radius),
                (x + 0.13 * radius, y + 0.08 * radius),
                (x - 0.13 * radius, y + 0.08 * radius),
            ),
            closed=True,
            facecolor=DARK,
            edgecolor=BLACK,
            linewidth=0.55,
            zorder=4,
        )
    )
    ax.add_patch(Circle((x, y + 0.02 * radius), 0.18 * radius, facecolor=WHITE, edgecolor=DARK, linewidth=0.65, zorder=5))

    target_offsets = (-0.40, 0.40) if hands == 2 else (-0.62, -0.22, 0.22, 0.62)
    for target_offset in target_offsets:
        shoulder = (x + 0.10 * target_offset * radius, y + 0.06 * radius)
        elbow = (x + 0.68 * target_offset * radius, y + 0.43 * radius)
        wrist = (x + target_offset * radius, y + 0.72 * radius)
        ax.plot(
            [shoulder[0], elbow[0], wrist[0]],
            [shoulder[1], elbow[1], wrist[1]],
            color=DARK,
            linewidth=1.6 if hands == 2 else 1.35,
            solid_capstyle="round",
            solid_joinstyle="round",
            zorder=5,
        )
        for joint in (shoulder, elbow):
            ax.add_patch(
                Circle(
                    joint,
                    0.050 * radius,
                    facecolor=WHITE,
                    edgecolor=DARK,
                    linewidth=0.55,
                    zorder=6,
                )
            )

        # All fork openings face the chamber/access direction, matching the
        # physical orientation used in the equipment reference drawing.
        fork_base_y = wrist[1] + 0.03 * radius
        fork_tip_y = wrist[1] + 0.18 * radius
        half_width = 0.075 * radius
        ax.plot(
            [wrist[0], wrist[0]],
            [wrist[1], fork_base_y],
            color=BLACK,
            linewidth=0.9,
            zorder=7,
        )
        ax.plot(
            [wrist[0] - half_width, wrist[0] + half_width],
            [fork_base_y, fork_base_y],
            color=BLACK,
            linewidth=0.9,
            zorder=7,
        )
        for sign in (-1, 1):
            ax.plot(
                [wrist[0] + sign * half_width, wrist[0] + sign * half_width],
                [fork_base_y, fork_tip_y],
                color=BLACK,
                linewidth=0.9,
                solid_capstyle="round",
                zorder=7,
            )
    ax.text(
        x,
        y - 0.55 * radius,
        label,
        ha="center",
        va="center",
        fontsize=6.6 if hands == 2 else 7.1,
        fontweight="bold",
        color=BLACK,
        zorder=8,
    )


def system_topology_v13(lang: str) -> None:
    configure(lang)
    fig, ax = new_canvas(7.15, 4.45, (-0.45, 10.85), (-1.25, 6.4))
    cn = lang == "cn"
    text = {
        "atm": "大气域：产品晶圆源" if cn else "Atmospheric domain: product-wafer source",
        "vac": "真空域" if cn else "Vacuum domain",
        "aligner": "对准器" if cn else "Aligner",
        "track": "大气机械手轨道" if cn else "Atmospheric robot track",
        "storage": "辅助晶圆存储" if cn else "Dummy-wafer storage",
        "product": "产品晶圆路线" if cn else "Product-wafer route",
        "dummy": "可复用辅助晶圆路线" if cn else "Reusable dummy-wafer route",
    }

    ax.add_patch(FancyBboxPatch((-0.2, -1.05), 10.75, 2.53, boxstyle="round,pad=0.02,rounding_size=0.16", facecolor="#FAFAFA", edgecolor="none"))
    ax.add_patch(FancyBboxPatch((-0.2, 1.62), 10.75, 4.56, boxstyle="round,pad=0.02,rounding_size=0.16", facecolor="#EFEFEF", edgecolor="none"))
    ax.text(0.0, 1.20, text["atm"], ha="left", va="center", fontsize=8, fontweight="bold")
    ax.text(0.0, 5.92, text["vac"], ha="left", va="center", fontsize=8, fontweight="bold")

    ax.add_patch(FancyBboxPatch((0.65, -0.05), 7.70, 1.10, boxstyle="round,pad=0.02,rounding_size=0.10", facecolor=WHITE, edgecolor=DARK, linewidth=0.75))
    ax.text(0.79, 0.94, "AL", ha="left", va="top", fontweight="bold")
    ax.plot([1.30, 8.00], [0.40, 0.40], color=MID, linewidth=1.15, zorder=1)
    rounded_box(ax, (0.95, 0.10), 1.50, 0.60, text["aligner"])
    ax.add_patch(Circle((5.00, 0.40), 0.45, facecolor=WHITE, edgecolor=DARK, linewidth=0.75, zorder=3))
    ax.text(5.00, 0.40, "ATR", ha="center", va="center", fontsize=7.2, zorder=4)
    ax.text(5.55, 0.40, text["track"], ha="left", va="center", fontsize=6.8, color=DARK)

    ax.add_patch(FancyBboxPatch((2.62, -1.08), 4.76, 0.80, boxstyle="round,pad=0.02,rounding_size=0.06", facecolor="none", edgecolor=MID, linewidth=0.7, zorder=2))
    ax.text(2.72, -0.31, "LP", ha="left", va="bottom", fontsize=6.6, fontweight="bold", color=DARK)
    lp_centres = {"LP1": 3.20, "LP2": 4.40, "LP3": 5.60, "LP4": 6.80}
    for label, x in lp_centres.items():
        rounded_box(ax, (x - 0.40, -1.00), 0.80, 0.60, label, size=6.8)

    ax.add_patch(FancyBboxPatch((2.86, 1.36), 4.62, 0.84, boxstyle="round,pad=0.02,rounding_size=0.06", facecolor="none", edgecolor=MID, linewidth=0.7, zorder=2))
    ax.text(2.96, 2.18, "LL", ha="left", va="bottom", fontsize=6.6, fontweight="bold", color=DARK)
    ll_centres = {"LLupper1": 3.42, "LLupper2": 4.58, "LLlower1": 5.76, "LLlower2": 6.92}
    for label, x in ll_centres.items():
        rounded_box(ax, (x - 0.51, 1.48), 1.02, 0.60, label, face=LIGHT, size=5.5)

    ax.add_patch(Circle((5.20, 3.25), 0.80, facecolor=LIGHT, edgecolor=DARK, linewidth=0.8, zorder=3))
    ax.text(5.20, 3.25, "VTR", ha="center", va="center", fontsize=8, zorder=4)
    rounded_box(ax, (0.55, 3.10), 1.80, 0.72, text["storage"], face=PALE, size=6.7)
    for x in (1.05, 1.85):
        ax.add_patch(Circle((x, 2.68), 0.25, facecolor=MID, edgecolor=DARK, linewidth=0.65, zorder=3))
        ax.text(x, 2.68, "D", ha="center", va="center", fontsize=6.6, color=WHITE, zorder=4)

    chamber(ax, (5.20, 5.05), "CH1\n四工位" if cn else "CH1\n4 spaces", (5.20, 6.02))
    chamber(ax, (8.65, 3.55), "CH2\n四工位" if cn else "CH2\n4 spaces", (9.87, 3.55))
    ax.plot([5.20, 5.20], [4.05, 4.02], color=MID, linewidth=1.0, zorder=1)
    ax.plot([6.00, 7.62, 7.62], [3.25, 3.25, 3.55], color=MID, linewidth=1.0, zorder=1)

    directed(ax, (5.00, -0.28), (5.00, -0.05))
    directed(ax, (2.45, 0.40), (4.53, 0.40))
    directed(ax, (5.00, 0.85), (5.00, 1.36))
    directed(ax, (5.20, 2.20), (5.20, 2.45))
    directed(ax, (5.20, 4.05), (5.20, 4.02))
    orthogonal(ax, ((6.00, 3.25), (7.62, 3.25), (7.62, 3.55)))

    orthogonal(ax, ((2.35, 3.46), (3.35, 3.46), (3.35, 3.28), (4.40, 3.28)), dashed=True)
    orthogonal(ax, ((1.30, 2.68), (3.70, 2.68), (3.70, 3.05), (4.43, 3.05)), dashed=True)
    orthogonal(ax, ((4.74, 3.88), (4.74, 4.30), (5.20, 4.30), (5.20, 4.65)), dashed=True)
    orthogonal(ax, ((5.98, 3.55), (6.80, 3.55), (6.80, 3.95), (8.18, 3.95)), dashed=True)

    directed(ax, (7.65, -0.48), (8.45, -0.48))
    ax.text(8.62, -0.48, text["product"], ha="left", va="center", fontsize=6.8)
    directed(ax, (7.65, -0.83), (8.45, -0.83), dashed=True)
    ax.text(8.62, -0.83, text["dummy"], ha="left", va="center", fontsize=6.8)
    save(fig, f"fig_system_{lang}")


def system_topology(lang: str, *, single_source: bool = False) -> None:
    configure(lang)
    fig, ax = new_canvas(3.50, 3.45, (-0.45, 11.20), (-2.72, 7.05))
    cn = lang == "cn"
    text = {
        "atm": "大气域" if cn else "Atmospheric domain",
        "vac": "真空域" if cn else "Vacuum domain",
        "aligner": "对准器" if cn else "Aligner",
        "track": "ATR轨道" if cn else "ATR rail",
        "storage": "辅助晶圆存储" if cn else "Dummy-wafer\nstorage",
        "put": "放片" if cn else "Put",
        "take": "取片" if cn else "Take",
        "product_out": "产品进" if cn else "Product out",
        "product_return": "产品回" if cn else "Product return",
        "dummy_out": "辅助进" if cn else "Dummy out",
        "dummy_return": "辅助回" if cn else "Dummy return",
    }
    product_out = "solid"
    product_return = (0, (6, 2, 1, 2))
    dummy_out = (0, (4, 2.5))
    dummy_return = (0, (1.1, 2.0))
    product_out_color = PRODUCT
    product_return_color = PRODUCT_RETURN
    dummy_out_color = DUMMY
    dummy_return_color = DUMMY_RETURN

    ax.plot([-0.10, 10.70], [1.38, 1.38], color=MID, linewidth=0.65, linestyle=(0, (3, 2)), zorder=0)
    ax.text(8.62, 1.08, text["atm"], ha="left", va="top", fontsize=6.3, fontweight="bold")
    ax.text(0.0, 6.47, text["vac"], ha="left", va="center", fontsize=6.3, fontweight="bold")

    # Atmospheric section. The LP bank is centred directly below the
    # vertically aligned ATR/VTR, and the rail remains visible on both sides.
    ax.add_patch(FancyBboxPatch((0.65, -0.02), 7.85, 1.08, boxstyle="round,pad=0.02,rounding_size=0.10", facecolor=WHITE, edgecolor=DARK, linewidth=0.75))
    rounded_box(ax, (0.95, 0.16), 1.55, 0.58, "AL")
    ax.plot([2.52, 4.60], [0.42, 0.42], color=MID, linewidth=1.20, zorder=2)
    ax.plot([5.80, 8.10], [0.42, 0.42], color=MID, linewidth=1.20, zorder=2)
    robot(ax, (5.20, 0.42), "ATR", hands=2, radius=0.48)
    ax.text(7.02, 0.60, text["track"], ha="center", va="bottom", fontsize=5.5, color=DARK)

    ax.add_patch(FancyBboxPatch((2.66, -1.69), 5.08, 1.02, boxstyle="round,pad=0.02,rounding_size=0.06", facecolor="none", edgecolor=MID, linewidth=0.7, zorder=2))
    if not single_source:
        ax.text(7.86, -1.18, "LP", ha="left", va="center", fontsize=6.8, fontweight="bold", color=DARK)
    for label, x in {"LP1": 3.30, "LP2": 4.57, "LP3": 5.84, "LP4": 7.11}.items():
        rounded_box(ax, (x - 0.46, -1.58), 0.92, 0.78, "", size=6.8)
        ax.text(x, -0.92, label, ha="center", va="center", fontsize=6.4, fontweight="bold", zorder=5)
        ax.add_patch(Circle((x, -1.42), 0.16, facecolor=LIGHT, edgecolor=DARK, linewidth=0.65, zorder=5))
        ax.text(x, -1.42, "P", ha="center", va="center", fontsize=5.6, color=BLACK, zorder=6)

    ax.add_patch(FancyBboxPatch((2.66, 1.42), 5.08, 0.90, boxstyle="round,pad=0.02,rounding_size=0.06", facecolor="none", edgecolor=MID, linewidth=0.7, zorder=2))
    ax.text(4.45, 2.40, "LL (U=上/L=下)" if cn else "LL (U=upper/L=lower)", ha="right", va="bottom", fontsize=5.6, fontweight="bold", color=DARK)
    for label, x in {"U1": 3.27, "U2": 4.55, "L1": 5.85, "L2": 7.13}.items():
        rounded_box(ax, (x - 0.50, 1.55), 1.00, 0.62, label, face=LIGHT, size=5.5)

    robot(ax, (5.20, 3.55), "VTR", hands=4, radius=0.82)
    if single_source:
        # Reuse Figure 1 geometry; move only dummy storage beside LP4.
        ax.add_patch(FancyBboxPatch((8.05, -1.69), 2.35, 1.02,
            boxstyle="round,pad=0.03,rounding_size=0.08", facecolor=PALE,
            edgecolor=DARK, linewidth=0.75, zorder=3))
        ax.text(9.225, -0.97, text["storage"], ha="center", va="center",
                fontsize=5.2, linespacing=1.08, color=BLACK, zorder=4)
        for x in (8.85, 9.60):
            ax.add_patch(Circle((x, -1.43), 0.16, facecolor=DUMMY,
                edgecolor=DARK, linewidth=0.65, zorder=4))
            ax.text(x, -1.43, "D", ha="center", va="center", fontsize=5.6,
                    color=WHITE, zorder=5)
    else:
        ax.add_patch(FancyBboxPatch((0.48, 2.87), 2.05, 1.28, boxstyle="round,pad=0.03,rounding_size=0.08", facecolor=PALE, edgecolor=DARK, linewidth=0.75, zorder=3))
        ax.text(1.505, 3.82, text["storage"], ha="center", va="center", fontsize=5.2, linespacing=1.08, color=BLACK, zorder=4)
        for x in (1.10, 1.91):
            ax.add_patch(Circle((x, 3.28), 0.27, facecolor=DUMMY, edgecolor=DARK, linewidth=0.7, zorder=4))
            ax.text(x, 3.28, "D", ha="center", va="center", fontsize=7.0, fontweight="bold", color=WHITE, zorder=5)

    chamber(ax, (5.20, 5.78), "CH1", (5.20, 5.78))
    chamber(ax, (8.95, 3.55), "CH2", (8.95, 3.55))

    # Separate parallel arrows show product outbound and return directions.
    directed(ax, (5.05, -0.80), (5.05, -0.07), style=product_out, color=product_out_color)
    directed(ax, (5.38, -0.07), (5.38, -0.80), style=product_return, color=product_return_color)
    directed(ax, (4.72, 0.55), (2.52, 0.55), style=product_out, color=product_out_color)
    directed(ax, (2.52, 0.29), (4.72, 0.29), style=product_out, color=product_out_color)
    ax.text(3.70, 1.14 if single_source else 0.65, text["put"], ha="center", va="bottom", fontsize=5.9, color=DARK)
    ax.text(3.70, -0.16 if single_source else 0.19, text["take"], ha="center", va="top", fontsize=5.9, color=DARK)

    directed(ax, (5.05, 0.90), (5.05, 1.42), style=product_out, color=product_out_color)
    directed(ax, (5.38, 1.42), (5.38, 0.90), style=product_return, color=product_return_color)
    directed(ax, (5.05, 2.32), (5.05, 2.73), style=product_out, color=product_out_color)
    directed(ax, (5.38, 2.73), (5.38, 2.32), style=product_return, color=product_return_color)

    if single_source:
        # A separate dummy bypasses AL. A companion remains on ATR near AL.
        ax.plot([8.40, 8.40], [-0.67, 0.18], color=dummy_out_color,
                linestyle=dummy_out, linewidth=0.9, zorder=5)
        directed(ax, (8.40, 0.18), (5.78, 0.18), style=dummy_out, color=dummy_out_color)
        ax.plot([5.78, 9.65], [0.02, 0.02], color=dummy_return_color,
                linestyle=dummy_return, linewidth=0.9, zorder=5)
        directed(ax, (9.65, 0.02), (9.65, -0.67), style=dummy_return, color=dummy_return_color)
        # Conditional excursion to the AL vicinity; never enters the AL box.
        accompany_style = (0, (4, 1.5, 1, 1.5))
        directed(ax, (4.72, 0.90), (2.85, 0.90), style=accompany_style, color=DARK)
        directed(ax, (2.85, 0.05), (4.72, 0.05), style=accompany_style, color=DARK)
        ax.plot([2.85, 2.85], [0.90, 0.05], color=DARK, linestyle=accompany_style,
                linewidth=0.65, zorder=5)
        # Explain the branch outside the physical drawing to avoid line overlap.
        ax.text(0.35, -2.93, "随行：辅助片留在ATR，产品对准后共同入LL" if cn
                else "Accompanied entry: dummy held on ATR during product alignment",
                ha="left", va="center", fontsize=5.1, color=DARK)
        directed(ax, (-0.30, -2.93), (0.20, -2.93), style=accompany_style, color=DARK)
        ax.set_ylim(-3.20, 7.05)
        for low, high in ((0.90, 1.42), (2.32, 2.73)):
            directed(ax, (4.76, low), (4.76, high), style=dummy_out, color=dummy_out_color)
            directed(ax, (5.67, high), (5.67, low), style=dummy_return, color=dummy_return_color)
    else:
        # Vacuum storage has distinct outbound and return legs.
        directed(ax, (2.53, 3.28), (4.36, 3.28), style=dummy_out, color=dummy_out_color)
        directed(ax, (4.36, 3.79), (2.53, 3.79), style=dummy_return, color=dummy_return_color)

    # Every VTR-to-chamber connection carries four straight, parallel routes.
    for x, style, color, outward in (
        (4.84, product_out, product_out_color, True),
        (5.08, product_return, product_return_color, False),
        (5.32, dummy_out, dummy_out_color, True),
        (5.56, dummy_return, dummy_return_color, False),
    ):
        start, end = ((x, 4.37), (x, 4.72)) if outward else ((x, 4.72), (x, 4.37))
        directed(ax, start, end, style=style, width=0.9, color=color)
    for y, style, color, outward in (
        (3.18, product_out, product_out_color, True),
        (3.42, product_return, product_return_color, False),
        (3.67, dummy_out, dummy_out_color, True),
        (3.91, dummy_return, dummy_return_color, False),
    ):
        start, end = ((6.02, y), (7.92, y)) if outward else ((7.92, y), (6.02, y))
        directed(ax, start, end, style=style, width=0.9, color=color)

    for x, y, label, style in (
        (0.25, -2.05, text["product_out"], product_out),
        (5.55, -2.05, text["product_return"], product_return),
        (0.25, -2.45, text["dummy_out"], dummy_out),
        (5.55, -2.45, text["dummy_return"], dummy_return),
    ):
        directed(
            ax, (x, y), (x + 0.82, y), style=style, width=0.9,
            color={
                product_out: product_out_color,
                product_return: product_return_color,
                dummy_out: dummy_out_color,
                dummy_return: dummy_return_color,
            }[style],
        )
        ax.text(x + 1.02, y, label, ha="left", va="center", fontsize=5.8)
    for artist in ax.texts:
        artist.set_fontsize(max(4.2, artist.get_fontsize() - 1.0))
    if single_source:
        for ext in ("pdf", "svg", "png"):
            fig.savefig(OUT / f"fig_single_source_{lang}.{ext}", dpi=600,
                        bbox_inches="tight", pad_inches=0.025)
        plt.close(fig)
    else:
        save(fig, f"fig_system_{lang}")


FILL = {"P1": "#E4E4E4", "P2": "#BDBDBD", "P3": "#858585", "D": WHITE, "": WHITE}


FILL.update({
    'P1': '#56B4E9',
    'P2': CHAIN_P2,
    'P3': CHAIN_P3,
    'D': '#F6C85F',
})


def wafer(ax, x: float, y: float, label: str) -> None:
    dashed = label in {"D", ""}
    ax.add_patch(
        Circle(
            (x, y),
            0.22,
            facecolor=FILL[label],
            edgecolor=BLACK if label else MID,
            linewidth=0.7,
            linestyle=(0, (3, 2)) if dashed else "solid",
            zorder=3,
        )
    )
    if label:
        ax.text(x, y, label, ha="center", va="center", fontsize=6.3, color=WHITE if label == "P3" else BLACK, zorder=4)


def process_state(ax, center, state, step: int, caption: str, *, process=False, label_y=-1.04):
    x, y = center
    ax.add_patch(
        FancyBboxPatch(
            (x - 0.72, y - 0.72),
            1.44,
            1.44,
            boxstyle="round,pad=0.02,rounding_size=0.05",
            facecolor="#ECECEC" if process else "#FAFAFA",
            edgecolor=BLACK if process else DARK,
            linewidth=1.15 if process else 0.7,
            zorder=1,
        )
    )
    coords = ((-0.32, 0.32), (0.32, 0.32), (-0.32, -0.32), (0.32, -0.32))
    for (dx, dy), label in zip(coords, state):
        wafer(ax, x + dx, y + dy, label)
    ax.text(x, y + 0.91, str(step), ha="center", va="center", fontsize=7.2, fontweight="bold")
    ax.text(x, y + label_y, caption, ha="center", va="top", fontsize=6.5, linespacing=1.05)


def chain_process(lang: str) -> None:
    configure(lang)
    cn = lang == "cn"
    fig, ax = new_canvas(
        3.50, 4.50 if cn else 4.70,
        (-1.75, 6.95), (-3.70 if cn else -4.00, 6.65)
    )
    captions = (
        [
            "放入辅助PW对D\n腔室自转\n装入P1",
            "腔室加工\nD + P1\nP1第1次",
            "腔室自转+链式滑动\nP1 + P2",
            "腔室加工\nP1第2次 / P2第1次",
            "腔室自转+链式滑动\nP2 + P3",
            "腔室加工\nP2第2次 / P3第1次",
            "腔室自转+链式滑动\nP3 + D",
            "腔室加工\nP3第2次",
            "全部取出\n腔室空闲",
        ]
        if cn
        else [
            "Load dummy PW pair D\nrotate chamber\nload P1",
            "Chamber\nprocessing\nD + P1\nP1 exposure 1",
            "Chamber rotation\n+ chain slide\nP1 + P2",
            "Chamber\nprocessing\nP1 exp. 2 / P2 exp. 1",
            "Chamber rotation\n+ chain slide\nP2 + P3",
            "Chamber\nprocessing\nP2 exp. 2 / P3 exp. 1",
            "Chamber rotation\n+ chain slide\nP3 + D",
            "Chamber\nprocessing\nP3 exposure 2",
            "Unload all\nchamber empty",
        ]
    )
    captions = list(captions)
    captions[1] = (
        '腔室加工/自转\nD + P1\nP1第1次'
        if cn else
        'Process / rotation\nD + P1\nP1 exposure 1'
    )
    states = [
        ("D", "D", "P1", "P1"),
        ("D", "D", "P1", "P1"),
        ("P1", "P1", "P2", "P2"),
        ("P1", "P1", "P2", "P2"),
        ("P2", "P2", "P3", "P3"),
        ("P2", "P2", "P3", "P3"),
        ("P3", "P3", "D", "D"),
        ("P3", "P3", "D", "D"),
        ("", "", "", ""),
    ]
    centres = [
        (0.00, 5.45),
        (2.70, 5.45),
        (5.40, 5.45),
        (5.40, 2.30),
        (2.70, 2.30),
        (0.00, 2.30),
        (0.00, -0.85),
        (2.70, -0.85),
        (5.40, -0.85),
    ]
    for i, (center, state, caption) in enumerate(zip(centres, states, captions), 1):
        process_state(ax, center, state, i, caption, process=i in {2, 4, 6, 8}, label_y=-1.02)
    for start, end in (((0.78, 5.45), (1.92, 5.45)), ((3.48, 5.45), (4.62, 5.45))):
        directed(ax, start, end, color=DARK)
    directed(ax, (6.55, 5.45), (6.55, 2.30), color=DARK, connection="arc3,rad=-0.24")
    for start, end in (((4.62, 2.30), (3.48, 2.30)), ((1.92, 2.30), (0.78, 2.30))):
        directed(ax, start, end, color=DARK)
    directed(ax, (-1.25, 2.30), (-1.25, -0.85), color=DARK, connection="arc3,rad=0.16")
    for start, end in (((0.78, -0.85), (1.92, -0.85)), ((3.48, -0.85), (4.62, -0.85))):
        directed(ax, start, end, color=DARK)
    save(fig, f"fig_chain_{lang}")


def parallel_process(lang: str) -> None:
    configure(lang)
    fig, ax = new_canvas(3.50, 3.65, (-1.15, 6.55), (-2.70, 3.05))
    cn = lang == "cn"
    captions = (
        ["装入P1\n前侧", "自转\n空出访问侧", "装入P2\n四槽满片", "并行加工\n四空间占用", "卸出P2\n后入先出", "自转/卸出P1\n周期完成"]
        if cn
        else ["Load P1\nfront side", "Rotate\nopen access side", "Load P2\nfour slots full", "Process\nfour spaces", "Unload P2\nlast in, first out", "Rotate / unload P1\ncycle complete"]
    )
    states = [
        ("", "", "P1", "P1"),
        ("P1", "P1", "", ""),
        ("P1", "P1", "P2", "P2"),
        ("P1", "P1", "P2", "P2"),
        ("P1", "P1", "", ""),
        ("", "", "", ""),
    ]
    centres = [(0.00, 2.00), (2.65, 2.00), (5.30, 2.00),
               (5.30, -1.05), (2.65, -1.05), (0.00, -1.05)]
    for i, (center, state, caption) in enumerate(zip(centres, states, captions), 1):
        process_state(ax, center, state, i, caption, process=i == 4, label_y=-1.02)
    directed(ax, (0.80, 2.00), (1.85, 2.00), color=DARK)
    directed(ax, (3.45, 2.00), (4.50, 2.00), color=DARK)
    directed(ax, (6.10, 2.00), (6.10, -1.05), color=DARK, connection="arc3,rad=-0.22")
    directed(ax, (4.50, -1.05), (3.45, -1.05), color=DARK)
    directed(ax, (1.85, -1.05), (0.80, -1.05), color=DARK)
    save(fig, f"fig_parallel_{lang}")


def implementation_framework(lang: str) -> None:
    from generate_cim_framework import implementation_framework as render_cim
    render_cim(lang)


def main() -> None:
    for lang in ("cn", "en"):
        implementation_framework(lang)
        system_topology(lang)
        chain_process(lang)
        parallel_process(lang)


if __name__ == "__main__":
    main()

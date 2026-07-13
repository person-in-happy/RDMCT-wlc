"""Create the compact pipeline figure used by the AAAI-27 draft."""

from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

plt.rcParams["pdf.fonttype"] = 42
plt.rcParams["ps.fonttype"] = 42


def box(ax, xy, width, height, text, face, edge="#31363b", fontsize=8):
    patch = FancyBboxPatch(
        xy,
        width,
        height,
        boxstyle="round,pad=0.02,rounding_size=0.025",
        linewidth=1.0,
        edgecolor=edge,
        facecolor=face,
    )
    ax.add_patch(patch)
    ax.text(
        xy[0] + width / 2,
        xy[1] + height / 2,
        text,
        ha="center",
        va="center",
        fontsize=fontsize,
    )


def arrow(ax, start, end):
    ax.add_patch(
        FancyArrowPatch(
            start,
            end,
            arrowstyle="-|>",
            mutation_scale=10,
            linewidth=1.0,
            color="#3f454b",
        )
    )


def main():
    output = Path(__file__).resolve().parents[1] / "products" / "rdmct_pipeline.pdf"
    output.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(7.0, 1.75))
    ax.set_xlim(0, 12)
    ax.set_ylim(0, 2.8)
    ax.axis("off")

    box(
        ax,
        (0.15, 0.85),
        1.35,
        1.15,
        "Product + PEC\n(two stores)",
        "#dceeff",
        fontsize=7.5,
    )
    box(
        ax,
        (1.9, 0.7),
        1.75,
        1.45,
        "Rotary-tool MIP\n4x1 / 2x2\nrobots + cleaning",
        "#e8f5e9",
        fontsize=7.5,
    )
    box(
        ax,
        (4.05, 0.7),
        1.45,
        1.45,
        "SCIP\ncandidate cuts",
        "#eeeeee",
        fontsize=7.5,
    )
    box(ax, (5.9, 1.48), 1.75, 0.67, "13 generic features", "#e7e1f8", fontsize=7.2)
    box(
        ax,
        (5.9, 0.7),
        1.75,
        0.67,
        "10 role features",
        "#f8e1ee",
        fontsize=7.2,
    )
    box(
        ax,
        (8.05, 0.7),
        1.55,
        1.45,
        "Hierarchical policy\nbudget + order",
        "#fff7cc",
        fontsize=7.5,
    )
    box(
        ax,
        (10.0, 0.7),
        1.65,
        1.45,
        "Role-aware\nsubmodular completion",
        "#ffdede",
        fontsize=7.5,
    )

    arrow(ax, (1.52, 1.42), (1.88, 1.42))
    arrow(ax, (3.67, 1.42), (4.03, 1.42))
    arrow(ax, (5.52, 1.42), (5.88, 1.80))
    arrow(ax, (5.52, 1.30), (5.88, 1.03))
    arrow(ax, (7.67, 1.80), (8.03, 1.65))
    arrow(ax, (7.67, 1.03), (8.03, 1.22))
    arrow(ax, (9.62, 1.42), (9.98, 1.42))

    ax.text(
        10.8,
        0.38,
        "valid SCIP cuts only",
        ha="center",
        va="center",
        fontsize=7.0,
        color="#555555",
    )
    fig.tight_layout(pad=0.1)
    fig.savefig(output, bbox_inches="tight", pad_inches=0.03)
    plt.close(fig)
    print(output)


if __name__ == "__main__":
    main()

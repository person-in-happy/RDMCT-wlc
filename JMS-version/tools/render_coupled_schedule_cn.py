"""Render Figure 5 from frozen events, without loading an optimization backend."""
from pathlib import Path
import hashlib
import json

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


PAPER = Path(__file__).resolve().parents[1]
SOURCE = PAPER / "results/current_defaults_small_prepared_20261103/runs/n1_H2_2x2_dual__s1__scip/result.json"
EVIDENCE = PAPER / "revisions/20261109_coupling_transfer/witness_evidence.json"
OUTPUT = PAPER / "figures/coupled_schedule_merged_20261112"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    evidence = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    record = next(r for r in evidence["records"] if Path(r["source"]).name == "result.json")
    source_hash = digest(SOURCE)
    if source_hash != record["sha256"]:
        raise RuntimeError("Frozen schedule differs from its validated record")
    data = json.loads(SOURCE.read_text(encoding="utf-8"))
    products = [j for j in data["jobs"] if j["product"]]
    auxiliaries = [j for j in data["jobs"] if not j["product"]]
    identities = sorted({j["identity"] for j in auxiliaries}, key=lambda s: int(s[1:]))
    pair_mode = {p["id"]: p["mode"] for p in data["pairs"]}
    cycles = sorted(data["cycles"], key=lambda c: c["start"])
    assert len(products) == 1 and {c["chamber"] for c in cycles} == {2}
    assert len(cycles) == 3 and len(auxiliaries) == 9 and len(identities) == 7
    product_cycles = [c for c in cycles
                      if c["mode"] != "clean" and products[0]["pair"] in c["pairs"]]
    assert len(product_cycles) == 2
    product_cmax = max(j["loan_end"] for j in products)
    occupied_end = max(j["loan_end"] for j in data["jobs"])

    plt.rcParams.update({"font.family": "Microsoft YaHei", "font.size": 8,
                         "axes.unicode_minus": False, "pdf.fonttype": 42,
                         "ps.fonttype": 42})
    figure_size = (3.55, 2.5)
    fig, ax = plt.subplots(figsize=figure_size, layout="constrained")
    production, cleaning = "#346995", "#317957"
    lanes = ["产品晶圆"] + identities
    rows = {identity: i + 1 for i, identity in enumerate(identities)}
    for row in range(len(lanes)):
        if row % 2 == 0:
            ax.axhspan(row - .5, row + .5, color="#f5f7fa", zorder=0)
    for cycle in product_cycles:
        ax.broken_barh([(cycle["start"], cycle["end"] - cycle["start"])],
                       (-.31, .62), facecolors=production, zorder=3)
        ax.text((cycle["start"] + cycle["end"]) / 2, 0,
                "2×2",
                ha="center", va="center", color="white", fontsize=7.2, zorder=4)
    plotted_loans = []
    for job in auxiliaries:
        clean = pair_mode[job["pair"]] == "clean"
        ax.broken_barh([(job["loan_start"], job["loan_end"] - job["loan_start"])],
                       (rows[job["identity"]] - .29, .58),
                       facecolors=cleaning if clean else production, zorder=3)
        plotted_loans.append({k: job[k] for k in ("identity", "pair", "loan_start", "loan_end")})
    ax.axvline(product_cmax, color="#a74337", ls="--", lw=.8, zorder=5)
    ax.axvline(occupied_end, color="#444444", ls=":", lw=.8, zorder=5)
    ax.set_yticks(range(len(lanes)), lanes)
    ax.set_ylim(len(lanes) - .5, -.65)
    ax.set_xlim(0, 820)
    ax.set_xticks(range(0, 801, 200))
    ax.set_xlabel("时间 / s", fontsize=8)
    ax.tick_params(axis="x", labelsize=7.5, length=3)
    ax.tick_params(axis="y", length=0, pad=4)
    ax.grid(axis="x", color="#dce1e6", lw=.65)
    ax.set_axisbelow(True)
    ax.spines[["top", "right", "left"]].set_visible(False)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    target = OUTPUT / "fig_coupled_schedule_merged_cn"
    for ext in ("pdf", "png"):
        fig.savefig(target.with_suffix("." + ext), dpi=220, bbox_inches="tight", pad_inches=.035)
    plt.close(fig)
    manifest = dict(source=str(SOURCE.relative_to(PAPER)), source_sha256=source_hash,
                    validation_record=str(EVIDENCE.relative_to(PAPER)),
                    solver_started=False, axes_count=1, lane_labels=lanes,
                    product_loan_lane_rendered=False, cleaning_cycle_lane_rendered=False,
                    product_identity=products[0]["identity"],
                    product_processing_cycles=product_cycles, source_cycles=cycles,
                    single_column=True, figure_size_inches=figure_size,
                    auxiliary_loans=plotted_loans, product_cmax=product_cmax,
                    occupied_end=occupied_end,
                    outputs={ext: digest(target.with_suffix("." + ext)) for ext in ("pdf", "png")})
    (OUTPUT / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"axes": 1, "lanes": len(lanes), "product_cycles": len(product_cycles),
                      "auxiliary_loans": len(plotted_loans), "solver_started": False}))


if __name__ == "__main__":
    main()

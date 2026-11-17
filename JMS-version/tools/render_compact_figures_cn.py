"""Compact the six current Chinese figures from saved vector/data sources."""
from pathlib import Path
import json
import shutil

from compact_figure_layout import crop_vector_figure
import render_in_figure_legends_cn as source

PAPER = Path(__file__).resolve().parents[1]
OUT = PAPER / "figures/compact_20261117"


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    source.OUT = OUT
    source.plt.rcParams.update({"font.sans-serif": ["Microsoft YaHei", "SimHei", "DejaVu Sans"],
                               "font.size": 8, "axes.unicode_minus": False,
                               "pdf.fonttype": 42, "svg.fonttype": "path"})
    copies = [("pjob_sequence_cn", "fig_system_pjob_cn"),
              ("pjob_sequence_cn", "fig_single_source_pjob_cn"),
              ("terminology_cn", "fig_parallel_cn_nature")]
    copied = []
    for folder, stem in copies:
        path = PAPER / "figures" / folder / (stem + ".pdf")
        shutil.copyfile(path, OUT / path.name)
        copied.append({"source": str(path.relative_to(PAPER)), "source_sha256": source.sha(path)})
    chain = source.add_chain_legend(compact_layout=True)
    entries = source.read(PAPER / "figures/schedule_examples_unified_20261112/manifest.json")["figures"]
    schedules = [source.draw_schedule(entry, compact_layout=True) for entry in entries]
    cropping = {path.stem: crop_vector_figure(path) for path in sorted(OUT.glob("*.pdf"))}
    report = {"renderer": str(Path(__file__)), "renderer_sha256": source.sha(Path(__file__)),
              "optimization_calls": 0, "copied_sources": copied, "chain": chain,
              "schedules": schedules, "cropping": cropping,
              "artifacts": {p.name: source.sha(p) for p in OUT.iterdir()
                            if p.suffix in (".pdf", ".svg", ".png")}}
    (OUT / "manifest.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", "utf-8")
    print("Six compact Chinese figures rendered; original schedule intervals preserved.")


if __name__ == "__main__":
    main()

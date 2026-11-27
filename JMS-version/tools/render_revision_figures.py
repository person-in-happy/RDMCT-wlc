"""Prepare corrected topology labels and the bilingual six-panel Pareto plot."""
from pathlib import Path
import json
import shutil

import pymupdf

PAPER = Path(__file__).resolve().parents[1]
REVISION = PAPER / "figures/revision_20261127"
ORIGINAL = PAPER / "figures/review_20261125"


def center_aligner(source, target):
    with pymupdf.open(source) as doc:
        page = doc[0]
        # The AL is the rounded rectangle to the left of the ATR, between the two
        # opposing arrows. Locate its physical outline in the source vector file.
        aligner, = [shape["rect"] for shape in page.get_drawings()
                    if shape["type"] == "fs" and shape["fill"] == (1, 1, 1)
                    and 24 < shape["rect"].x0 < 26 and 103 < shape["rect"].y0 < 105]
        slots = sorted([d["rect"] for d in page.get_drawings() if d["type"]=="fs"
                        and 78<d["rect"].y0<82 and 16<d["rect"].width<19],key=lambda b:b.x0)
        assert len(slots)==4
        # The original text-show command starts with a -12000 advance (74.4 pt
        # in the 6.2 pt AL font). The text matrix already uses the box center.
        displaced = b"[-12000<0041004C>]TJ"
        normal = b"[<0041004C>]TJ"
        contents = page.get_contents()
        stream, = [xref for xref in contents if displaced in doc.xref_stream(xref)]
        before = [(s["text"],s["bbox"]) for block in page.get_text("dict")["blocks"]
                  for line in block.get("lines",[]) for s in line["spans"] if s["text"]!="AL"]
        data = doc.xref_stream(stream)
        assert data.count(displaced)==1
        doc.update_stream(stream,data.replace(displaced,normal))
        after = [(s["text"],s["bbox"]) for block in page.get_text("dict")["blocks"]
                 for line in block.get("lines",[]) for s in line["spans"] if s["text"]!="AL"]
        assert before == after
        for name,rect in [("AL",aligner), *zip(("U1","U2","L1","L2"),slots,strict=True)]:
            moved, = page.search_for(name)
            assert rect.contains(moved), (name,rect,moved)
        doc.save(target, garbage=4, deflate=True, no_new_id=True)


def main():
    from render_submission_figures_en import OUTPUT, SOURCES, TOPOLOGY, TRADEOFFS, digest, render
    from plot_solved_pareto_schedules import plot_solved

    REVISION.mkdir(parents=True,exist_ok=True)
    for name in ("fig_system_pjob_cn.pdf","fig_single_source_pjob_cn.pdf"):
        center_aligner(ORIGINAL/name,REVISION/name)
    plot_solved(REVISION/"tradeoffs.pdf")
    updated = {n:render(n,SOURCES[n-1],labels) for n,labels in ((1,TOPOLOGY),(2,TOPOLOGY),(6,TRADEOFFS))}
    mirror = PAPER.parent / "cie/products/figures_current"
    file = OUTPUT / "manifest.json"
    report = json.loads(file.read_bytes())
    for n,entry in updated.items():
        report["figures"][n-1]=entry
        for ext in (".pdf",".svg",".png"):
            asset = OUTPUT / f"Figure{n}{ext}"
            report["artifacts"][asset.name] = digest(asset)
        for asset in (SOURCES[n-1],OUTPUT/f"Figure{n}.pdf"):
            shutil.copyfile(asset,mirror/asset.name)
    report["renderer_sha256"] = digest(Path(__file__).with_name("render_submission_figures_en.py"))
    file.write_text(json.dumps(report,indent=2)+"\n",encoding="utf8")


if __name__ == "__main__":
    main()

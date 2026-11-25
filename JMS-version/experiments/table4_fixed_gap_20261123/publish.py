"""Append the checked fixed-gap panel to table 4, preserving its cited 300 s panel."""
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from tempfile import TemporaryDirectory
import csv
import hashlib
import json
import re
import shutil

import pymupdf

JMS = Path(__file__).resolve().parents[2]
OUT = JMS / "results/table4_fixed_gap_20261123"
SOURCE = JMS / "JMS_Review_CN.tex"
REVISION = JMS / "revisions/20261123_table4_fixed_gap"
LABEL = r"\label{tab:matched-objectives-cn}"
NEW_LABEL = r"\label{tab:matched-objectives-gaps-cn}"


def candidate(before, panel):
    text = before.decode("utf8")
    if text.count(LABEL) != 1:
        raise ValueError("The current manuscript needs a review of the table anchor")
    end = r"\end{table}"
    pos = text.index(end, text.index(LABEL)) + len(end)
    newline = "\r\n" if "\r\n" in text else "\n"
    insert = newline*2 + panel.replace("\n", newline)
    if NEW_LABEL in text:
        if text.count(NEW_LABEL) == 1 and text[pos:].startswith(insert):
            return before
        raise ValueError("A different fixed-gap panel is already present at the table anchor")
    return (text[:pos] + insert + text[pos:]).encode("utf8")


def render(panel, directory):
    before = SOURCE.read_bytes()
    revised = candidate(before, panel)
    paper, scratch = directory / "paper", directory / "scratch"
    paper.mkdir()
    scratch.mkdir()
    spec = spec_from_file_location("jms_build", JMS / "tools/build_model4_cn.py")
    builder = module_from_spec(spec)
    spec.loader.exec_module(builder)
    for figure in builder.flat_figures(revised.decode("utf8").replace("\r\n", "\n")):
        shutil.copy2(figure, paper / figure.name)
    builder.PAPER, builder.MAIN, builder.BUILD = paper, paper / SOURCE.name, paper / "build"
    builder.MAIN.write_bytes(revised)
    builder.build(scratch)
    aux = (scratch / SOURCE.with_suffix(".aux").name).read_text("utf8")
    labels = [re.search(r"\\newlabel\{" + key + r"\}\{\{([^}]+)\}", aux)[1] for key in
              ("tab:matched-objectives-cn", "tab:matched-objectives-gaps-cn")]
    if labels != ["4", "4"]:
        raise ValueError(f"Original and continued table numbers: {labels}")
    pdf = builder.MAIN.with_suffix(".pdf")
    with pymupdf.open(pdf) as doc:
        found = [page.number for page in doc if "固定相对间隙下" in "".join(page.get_text().split())]
        assert len(found) == 1, found
        page = doc[found[0]]
        page.get_pixmap(matrix=pymupdf.Matrix(1.7,1.7)).save(directory / "table4.png")
        compact = "".join(page.get_text().split())
        for percent in ("10%", "1%", "0.01%"):
            assert percent in compact, percent
        for value in set(re.findall(r"(?<= & )\d+\.\d\d(?= & |\\\\)", panel)):
            assert value in compact, value
    return before, revised, pdf, builder.BUILD / "build_report.json"


def main():
    with (OUT / "table4_means.csv").open(encoding="utf-8-sig", newline="") as stream:
        means = list(csv.DictReader(stream))
    assert len(means) == 15
    with (OUT / "endpoints.csv").open(encoding="utf-8-sig", newline="") as stream:
        assert len(list(csv.DictReader(stream))) == 180
    panel = (OUT / "table4_gap.tex").read_text("utf8")
    with TemporaryDirectory(dir=OUT) as tmp:
        work = Path(tmp)
        before, revised, pdf, report = render(panel, work)
        assert SOURCE.read_bytes() == before, "Manuscript changed during verification"
        REVISION.mkdir(parents=True, exist_ok=True)
        backup = REVISION / "before.tex"
        if before != revised and not backup.exists():
            backup.write_bytes(before)
        shutil.copy2(report, REVISION / report.name)
        shutil.copy2(work / "table4.png", REVISION / "table4.png")
        for src, dst in ((pdf, JMS / "output/pdf" / pdf.name), (pdf, SOURCE.with_suffix(".pdf")),
                         (pdf.with_suffix(".tex"), SOURCE)):
            tmp = dst.with_suffix(dst.suffix + ".table4.tmp")
            shutil.copy2(src, tmp)
            tmp.replace(dst)
        assert SOURCE.read_bytes() == revised
        receipt = dict(verified_endpoints=180, table_rows=len(means), table_number=4,
                       source_sha256=hashlib.sha256(revised).hexdigest(),
                       pdf_sha256=hashlib.sha256(pdf.read_bytes()).hexdigest())
        (OUT / "published.json").write_text(json.dumps(receipt, indent=2), encoding="utf8")


if __name__ == "__main__":
    main()

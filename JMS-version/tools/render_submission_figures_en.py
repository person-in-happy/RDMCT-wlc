"""Translate the labels of the manuscript's vector artwork, retaining its physical data."""
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import re

import pymupdf
from render_revision_figures import REVISION

PAPER = Path(__file__).resolve().parents[1]
FIGURES = PAPER / "figures"
REVIEW = FIGURES / "review_20261125"
GANTTS = FIGURES / "gantt_20261126"
COMPACT = FIGURES / "compact_20261117"
OUTPUT = FIGURES / "submission_en"
SOURCES = [
    REVISION / "fig_system_pjob_cn.pdf", REVISION / "fig_single_source_pjob_cn.pdf",
    COMPACT / "fig_chain_cn_nature.pdf", REVIEW / "terminal_choices.pdf",
    COMPACT / "fig_parallel_cn_nature.pdf", REVISION / "tradeoffs.pdf",
    *(GANTTS / f"fig_schedule_n{n}_square_cn.pdf" for n in (4, 16, 75)),
]
# English labels are placed over the corresponding original text, in PDF points.
# Alignment follows the associated symbol: legend swatch, row edge, or plot center.
TOPOLOGY = {
    "大气域": "Atmosphere", "真空域": "Vacuum", "ATR轨道": "ATR rail",
    "LL (U=上/L=下)": "LL (U=upper, L=lower)", "放片": "Place", "取片": "Pick",
    "辅助晶圆存储": "Auxiliary store", "产品供片": "Product supply",
    "产品回片": "Product return", "辅助片借出": "Auxiliary checkout", "辅助片归还": "Auxiliary return",
    "随行：辅助片留在ATR，产品对准后共同入LL":
        "The auxiliary stays on the ATR during product alignment. Both enter the LL together.",
}
PROCESS = {
    "放入辅助PW对D": "Load auxiliary pair D", "装入P1": "Load P1", "装入P2": "Load P2",
    "腔室旋转": "Rotate chamber", "工艺处理": "Process",
    "P1第1次": "P1 pass 1", "P1第2次 / P2第1次": "P1 pass 2 / P2 pass 1",
    "P2第2次 / P3第1次": "P2 pass 2 / P3 pass 1", "P3第2次": "P3 pass 2",
    "全部取出": "Unload all", "腔室空闲": "Empty chamber",
    "腔室旋转+链式换片": "Rotate and exchange", "辅助PW对": "Auxiliary PW pair",
    "前侧": "Front side", "空出访问侧": "Clear access side", "四槽满片": "All four slots full",
    "四空间占用": "All four slots occupied", "卸出P2": "Unload P2", "后入先出": "Last in, first out",
    "周期完成": "Cycle complete", "旋转": "Rotate", "并行生产": "Parallel processing",
    "旋转/卸出P1": "Rotate / unload P1",
}
TERMINAL = {
    "半周旋转": "Half-turn", "卸产品对": "Product out", "卸辅助对": "Auxiliary out",
    "产品优先": "Product first", "常规卸片": "Front first",
    "3 s 开始卸产品": "Product unloading starts at 3 s",
    "2 s 开始卸产品": "Product unloading starts at 2 s",
    "可延后": "May defer", "距末次加工结束的时间（s）": "Time since final processing ended (s)",
}
TRADEOFFS = {
    "已求得的排程": "Solved schedules",
    "工艺分（等效 s）": "Process objective (equivalent s)",
    "末片产品回片时刻（s）": "Time of last product return (s)",
    "(a) 4 片纯 2×2，H = 10": "(a) Four wafers, 2×2 recipe only, H = 10",
    "(b) 8 片混合": "(b) Eight wafers, mixed recipes",
    "(c) 16 片混合，H = 10": "(c) Sixteen wafers, mixed recipes, H = 10",
}
LANES = {
    "ATR机械手": "ATR", "VTR机械手": "VTR", "对准器 AL": "Aligner (AL)",
    "上装载锁槽1": "Upper LL slot 1", "上装载锁槽2": "Upper LL slot 2",
    "下装载锁槽1": "Lower LL slot 1", "下装载锁槽2": "Lower LL slot 2",
    "旋转腔 CH2": "CH2", "旋转腔 CH3": "CH3", "真空辅助库 VS": "Vacuum store",
    "时间 / s": "Time (s)", "资源": "Resource",
}
ACTIONS = {
    "ATR取片": "ATR pick", "ATR放片": "ATR place", "带片移动": "Loaded move",
    "承片等待": "Wafer hold", "AL对准": "Align", "LL抽气": "LL pump",
    "LL真空等待": "LL vacuum wait", "LL放气": "LL vent", "大气侧等待": "Atm. wait",
    "VTR取放": "VTR transfer", "4×1加工": "4×1 process", "2×2加工": "2×2 process",
    "腔室加工": "Process", "腔内等待": "Chamber wait", "腔室旋转": "Rotate",
    "空载移动/复位": "Empty move/reset", "清洁": "Clean",
    "ATR取出": "ATR pick", "ATR放入": "ATR place", "持片等待": "Wafer hold",
    "VTR取出/放入": "VTR pick/place", "工艺加工": "Process",
}
FONT = pymupdf.Font("helv")


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def spans(page):
    return [(span, line["dir"]) for block in page.get_text("dict")["blocks"]
            for line in block.get("lines", []) for span in line["spans"]]


def label_layout(number, span, labels):
    """Return label, anchor alignment and available width for a translated span."""
    old = span["text"]
    rect = pymupdf.Rect(span["bbox"])
    if old in labels:
        new = labels[old]
    elif old.startswith("末片回片 "):
        new = "Return " + old.split()[-1]
    elif old.startswith("设备释放 "):
        new = "Release " + old.split()[-1]
    else:
        raise ValueError(f"Untranslated label in artwork {number}: {old}")
    if number <= 2:
        if old in ("大气域", "真空域"):
            return new, "left", 40
        if old.startswith("随行"):
            return new, "left", 180
        if old in ("产品供片", "产品回片", "辅助片借出", "辅助片归还"):
            return new, "left", 69
        if old.startswith("LL "):
            return new, "center", 40
        return new, "center", max(29, rect.width)
    if number in (3, 5):
        if old == "辅助PW对":
            return new, "left", 77
        return new, "center", 56 if number == 3 else 61
    if number == 4:
        if old in ("半周旋转", "卸产品对", "卸辅助对"):
            return new, "left", 32 if old != "卸辅助对" else 65
        if old in ("常规卸片", "产品优先"):
            return new, "right", 36
        return new, "center", 190 if old.startswith("距") else (42 if old == "可延后" else 118)
    if number == 6:
        if old == "已求得的排程":
            return new, "left", 74
        return new, "center", 101 if old.startswith("工艺分") else 225
    if old in LANES:
        return new, "right", 51
    if old.startswith(("末片回片", "设备释放")):
        return new, "right", rect.width - 1
    # Four legend columns are anchored by the immutable swatches in the original.
    return new, "left", 34 if rect.x0 < 70 else 41 if rect.x0 < 180 else 58


def render(number, source, labels):
    target = OUTPUT / f"Figure{number}.pdf"
    if number == 6:
        from plot_solved_pareto_schedules import draw_panels
        markers = source.with_name("pareto_solved_schedules.json")
        report = json.loads(markers.read_bytes())
        draw_panels(target,report,"en")
        with pymupdf.open(target) as doc:
            page = doc[0]
            assert page.get_text().count("Batch makespan (s)")==6
            assert page.get_text().count("Process objective (equiv. s)")==6
            page.get_pixmap(matrix=pymupdf.Matrix(3,3),alpha=False).save(target.with_suffix(".png"))
            target.with_suffix(".svg").write_text(page.get_svg_image(),encoding="utf-8")
        return {"figure":number,"source":source.relative_to(PAPER).as_posix(),"source_sha256":digest(source),
                "windows_per_row":[2,2,2],"window_counts":report["window_counts"],
                "marker_count":report["marker_count"],"marker_manifest":markers.relative_to(PAPER).as_posix(),
                "marker_manifest_sha256":digest(markers),"panel_branches":report["panel_branches"],
                "branch_manifest":"results/pareto_publication_20261125/displayed_curves.json"}
    with pymupdf.open(source) as doc:
        page = doc[0]
        old_spans = spans(page)
        changed = [(span, direction) for span, direction in old_spans
                   if re.search(r"[\u3400-\u9fff]", span["text"])]
        assert changed, source
        # Remove only text. In the topology PDF several original glyph boxes
        # overlap, so individual redaction strips can also hit a neighbouring label.
        page.add_redact_annot(page.rect, fill=None)
        page.apply_redactions(images=0, graphics=0, text=0)
        assert not page.get_text().strip(), source
        geometry = page.get_pixmap().digest
        page.insert_font(fontname="FigEnglish", fontbuffer=FONT.buffer)
        expected = Counter()
        for span, direction in old_spans:
            if re.search(r"[\u3400-\u9fff]", span["text"]):
                label, align, available = label_layout(number, span, labels)
            else:
                label, align, available = span["text"], "center", pymupdf.Rect(span["bbox"]).width
            expected[label.replace(" ", "")] += 1
            size = min(span["size"], available / FONT.text_length(label, fontsize=1))
            width = FONT.text_length(label, fontsize=size)
            x0, y0, x1, y1 = span["bbox"]
            x, y = span["origin"]
            rotation = 0
            if direction[0] == 0:
                rotation = 90
                y = (y0 + y1 + width) / 2
            elif align == "center":
                x = (x0 + x1 - width) / 2
            elif align == "right":
                x = x1 - width
            page.insert_text((x, y), label, fontname="FigEnglish", fontsize=size, rotate=rotation,
                             color=pymupdf.sRGB_to_pdf(span["color"]))
        assert not re.search(r"[\u3400-\u9fff]", page.get_text()), source
        doc.subset_fonts()
        doc.save(target, garbage=4, deflate=True, no_new_id=True)
    with pymupdf.open(target) as doc:
        page = doc[0]
        actual = Counter(s["text"].replace(" ", "") for s, d in spans(page))
        assert actual == expected, (target, expected-actual, actual-expected)
        # Keep the companion files aligned with the PDF submitted to the journal.
        page.get_pixmap(matrix=pymupdf.Matrix(3, 3), alpha=False).save(target.with_suffix(".png"))
        target.with_suffix(".svg").write_text(page.get_svg_image(), encoding="utf-8")
        page.add_redact_annot(page.rect, fill=None)
        page.apply_redactions(images=0, graphics=0, text=0)
        assert page.get_pixmap().digest == geometry, f"Chart geometry changed in {target}"
    return {"figure": number, "source": source.relative_to(PAPER).as_posix(),
              "source_sha256": digest(source), "translated_labels": len(changed)}


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    dictionaries = (TOPOLOGY, TOPOLOGY, PROCESS, TERMINAL, PROCESS, TRADEOFFS,
                    *([LANES | ACTIONS] * 3))
    figures = [render(i, path, mapping) for i, (path, mapping) in
               enumerate(zip(SOURCES, dictionaries, strict=True), 1)]
    schedule_catalogue = json.loads((GANTTS / "manifest.json").read_bytes())
    schedules = []
    for record, translated in zip(schedule_catalogue, figures[-3:], strict=True):
        assert Path(translated["source"]).name == record["chart"]
        assert translated["source_sha256"] == record["chart_sha256"]
        assert digest(PAPER / record["source"]) == record["source_sha256"]
        assert digest(PAPER / record["certificate"]) == record["certificate_sha256"]
        schedules.append({key: record[key] for key in
                          ("n", "source", "source_sha256", "certificate", "certificate_sha256",
                           "intervals", "events", "cmax", "equipment_end", "secondary")})
        schedules[-1].update(figure=translated["figure"], intervals_unchanged=True,
                             legend_columns=4, single_column=True)
    report = {"optimization_calls": 0, "figures": figures, "schedules": schedules,
              "renderer_sha256": digest(Path(__file__)), "artifacts": {
                  f.name: digest(f) for f in sorted(OUTPUT.glob("Figure*"))
                  if f.suffix in {".pdf", ".png", ".svg"}}}
    (OUTPUT / "manifest.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()

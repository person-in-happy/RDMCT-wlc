# -*- coding: utf-8 -*-
import re
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

from path_utils import append_date_to_filename


ROOT = Path(__file__).resolve().parent
TEMPLATE = ROOT / "template_patent.docx"
MD_INPUT = ROOT / "docs" / "how_to_run_and_get_final_mip_solution.md"
DOCX_OUTPUT = ROOT / "docs" / append_date_to_filename("how_to_run_and_get_final_mip_solution.docx")
DOCX_FALLBACK = ROOT / "docs" / append_date_to_filename("how_to_run_and_get_final_mip_solution_fixed.docx")


def extract_sect_pr(document_xml: str) -> str:
    match = re.search(r"(<w:sectPr[\s\S]*</w:sectPr>)\s*</w:body>\s*</w:document>\s*$", document_xml)
    if match:
        return match.group(1)
    return (
        "<w:sectPr>"
        "<w:pgSz w:w=\"11906\" w:h=\"16838\"/>"
        "<w:pgMar w:top=\"1440\" w:right=\"1800\" w:bottom=\"1440\" w:left=\"1800\" "
        "w:header=\"851\" w:footer=\"992\" w:gutter=\"0\"/>"
        "<w:cols w:space=\"425\"/>"
        "<w:docGrid w:type=\"lines\" w:linePitch=\"312\"/>"
        "</w:sectPr>"
    )


def make_paragraph(
    text: str = "",
    *,
    bold: bool = False,
    size: int = 24,
    center: bool = False,
    font_ascii: str = "Calibri",
    font_east: str = "宋体",
) -> str:
    ppr = "<w:pPr><w:jc w:val=\"center\"/></w:pPr>" if center else ""
    rpr_parts = [f"<w:rFonts w:ascii=\"{font_ascii}\" w:eastAsia=\"{font_east}\"/>"]
    if bold:
        rpr_parts.extend(["<w:b/>", "<w:bCs/>"])
    if size != 24:
        rpr_parts.append(f"<w:sz w:val=\"{size}\"/>")
        rpr_parts.append(f"<w:szCs w:val=\"{size}\"/>")
    rpr = f"<w:rPr>{''.join(rpr_parts)}</w:rPr>"
    return f"<w:p>{ppr}<w:r>{rpr}<w:t xml:space=\"preserve\">{escape(text)}</w:t></w:r></w:p>"


def make_code_paragraph(text: str) -> str:
    return make_paragraph(text=text, size=20, font_ascii="Consolas", font_east="等线")


def parse_markdown(md_text: str):
    lines = md_text.splitlines()
    in_code = False
    code_buffer = []

    for raw_line in lines:
        line = raw_line.rstrip("\n")
        stripped = line.strip()

        if stripped.startswith("```"):
            if in_code:
                if code_buffer:
                    for code_line in code_buffer:
                        yield ("code", code_line)
                yield ("blank", "")
                code_buffer = []
                in_code = False
            else:
                in_code = True
                code_buffer = []
            continue

        if in_code:
            code_buffer.append(line)
            continue

        if not stripped:
            yield ("blank", "")
            continue

        if stripped.startswith("# "):
            yield ("title", stripped[2:].strip())
            continue
        if stripped.startswith("## "):
            yield ("h1", stripped[3:].strip())
            continue
        if stripped.startswith("### "):
            yield ("h2", stripped[4:].strip())
            continue
        if stripped.startswith("- "):
            yield ("bullet", stripped[2:].strip())
            continue
        if re.match(r"^\d+\.\s+", stripped):
            yield ("number", stripped)
            continue
        yield ("p", stripped)


def write_docx() -> Path:
    md_text = MD_INPUT.read_text(encoding="utf-8")
    body = []

    for kind, text in parse_markdown(md_text):
        if kind == "title":
            body.append(make_paragraph(text, bold=True, size=32, center=True))
            body.append(make_paragraph(""))
        elif kind == "h1":
            body.append(make_paragraph(text, bold=True, size=28))
        elif kind == "h2":
            body.append(make_paragraph(text, bold=True, size=26))
        elif kind == "code":
            body.append(make_code_paragraph(text))
        elif kind == "bullet":
            body.append(make_paragraph("• " + text, size=24))
        elif kind == "number":
            body.append(make_paragraph(text, size=24))
        elif kind == "p":
            body.append(make_paragraph(text, size=24))
        elif kind == "blank":
            body.append(make_paragraph(""))

    with zipfile.ZipFile(TEMPLATE, "r") as zin:
        template_document = zin.read("word/document.xml").decode("utf-8", errors="replace")
        sect_pr = extract_sect_pr(template_document)
        new_document_xml = (
            "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>"
            "<w:document "
            "xmlns:wpc=\"http://schemas.microsoft.com/office/word/2010/wordprocessingCanvas\" "
            "xmlns:cx=\"http://schemas.microsoft.com/office/drawing/2014/chartex\" "
            "xmlns:mc=\"http://schemas.openxmlformats.org/markup-compatibility/2006\" "
            "xmlns:o=\"urn:schemas-microsoft-com:office:office\" "
            "xmlns:r=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships\" "
            "xmlns:m=\"http://schemas.openxmlformats.org/officeDocument/2006/math\" "
            "xmlns:v=\"urn:schemas-microsoft-com:vml\" "
            "xmlns:wp14=\"http://schemas.microsoft.com/office/word/2010/wordprocessingDrawing\" "
            "xmlns:wp=\"http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing\" "
            "xmlns:w10=\"urn:schemas-microsoft-com:office:word\" "
            "xmlns:w=\"http://schemas.openxmlformats.org/wordprocessingml/2006/main\" "
            "xmlns:w14=\"http://schemas.microsoft.com/office/word/2010/wordml\" "
            "xmlns:w15=\"http://schemas.microsoft.com/office/word/2012/wordml\" "
            "xmlns:wpg=\"http://schemas.microsoft.com/office/word/2010/wordprocessingGroup\" "
            "xmlns:wpi=\"http://schemas.microsoft.com/office/word/2010/wordprocessingInk\" "
            "xmlns:wne=\"http://schemas.microsoft.com/office/word/2006/wordml\" "
            "xmlns:wps=\"http://schemas.microsoft.com/office/word/2010/wordprocessingShape\" "
            "mc:Ignorable=\"w14 w15 wp14\">"
            f"<w:body>{''.join(body)}{sect_pr}</w:body></w:document>"
        )

        target = DOCX_OUTPUT
        try:
            with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as zout:
                for item in zin.infolist():
                    if item.filename == "word/document.xml":
                        continue
                    zout.writestr(item, zin.read(item.filename))
                zout.writestr("word/document.xml", new_document_xml.encode("utf-8"))
        except PermissionError:
            target = DOCX_FALLBACK
            with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as zout:
                for item in zin.infolist():
                    if item.filename == "word/document.xml":
                        continue
                    zout.writestr(item, zin.read(item.filename))
                zout.writestr("word/document.xml", new_document_xml.encode("utf-8"))
    return target


def main() -> None:
    target = write_docx()
    print(MD_INPUT)
    print(target)


if __name__ == "__main__":
    main()

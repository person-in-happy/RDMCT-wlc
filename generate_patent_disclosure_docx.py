# -*- coding: utf-8 -*-

import re
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

from path_utils import append_date_to_filename


ROOT = Path(__file__).resolve().parent
TEMPLATE = ROOT / "template_patent.docx"
SOURCE = ROOT / "docs" / "patent_disclosure_dual_source_rotary_a3c_beam.md"
OUTPUT = ROOT / "docs" / append_date_to_filename("patent_disclosure_dual_source_rotary_a3c_beam.docx")


def make_paragraph(text="", bold=False, size=24, center=False):
    ppr = ""
    if center:
        ppr = '<w:pPr><w:jc w:val="center"/></w:pPr>'
    rpr = ""
    if bold or size != 24:
        rpr_parts = []
        if bold:
            rpr_parts.append("<w:b/>")
            rpr_parts.append("<w:bCs/>")
        if size != 24:
            rpr_parts.append(f'<w:sz w:val="{size}"/>')
            rpr_parts.append(f'<w:szCs w:val="{size}"/>')
        rpr = f"<w:rPr>{''.join(rpr_parts)}</w:rPr>"
    if text == "":
        return f"<w:p>{ppr}<w:r>{rpr}<w:t xml:space=\"preserve\"></w:t></w:r></w:p>"
    return f"<w:p>{ppr}<w:r>{rpr}<w:t xml:space=\"preserve\">{escape(text)}</w:t></w:r></w:p>"


def extract_sect_pr(document_xml):
    match = re.search(r"(<w:sectPr[\s\S]*</w:sectPr>)\s*</w:body>\s*</w:document>\s*$", document_xml)
    if match:
        return match.group(1)
    return (
        "<w:sectPr>"
        '<w:pgSz w:w="11906" w:h="16838"/>'
        '<w:pgMar w:top="1440" w:right="1800" w:bottom="1440" w:left="1800" '
        'w:header="851" w:footer="992" w:gutter="0"/>'
        '<w:cols w:space="425"/>'
        '<w:docGrid w:type="lines" w:linePitch="312"/>'
        "</w:sectPr>"
    )


def parse_markdown(lines):
    blocks = []
    for raw_line in lines:
        line = raw_line.rstrip("\n")
        stripped = line.strip()
        if not stripped:
            blocks.append({"type": "blank", "text": ""})
            continue
        if stripped.startswith("# "):
            blocks.append({"type": "h1", "text": stripped[2:].strip()})
        elif stripped.startswith("## "):
            blocks.append({"type": "h2", "text": stripped[3:].strip()})
        elif stripped.startswith("### "):
            blocks.append({"type": "h3", "text": stripped[4:].strip()})
        else:
            blocks.append({"type": "p", "text": stripped})
    return blocks


def build_document_xml(blocks, sect_pr):
    body = []
    previous_heading = None

    for block in blocks:
        block_type = block["type"]
        text = block["text"]

        if block_type == "blank":
            body.append(make_paragraph(""))
            continue

        if block_type == "h1":
            body.append(make_paragraph(text, bold=True, size=28))
            previous_heading = text
            continue

        if block_type == "h2":
            body.append(make_paragraph(text, bold=True, size=26))
            previous_heading = text
            continue

        if block_type == "h3":
            body.append(make_paragraph(text, bold=True, size=24))
            previous_heading = text
            continue

        if previous_heading == "发明名称":
            body.append(make_paragraph(text, bold=True, size=28, center=True))
        else:
            body.append(make_paragraph(text, size=24))

        previous_heading = None

    body.append(sect_pr)
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:wpc="http://schemas.microsoft.com/office/word/2010/wordprocessingCanvas" '
        'xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006" '
        'xmlns:o="urn:schemas-microsoft-com:office:office" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
        'xmlns:m="http://schemas.openxmlformats.org/officeDocument/2006/math" '
        'xmlns:v="urn:schemas-microsoft-com:vml" '
        'xmlns:wp14="http://schemas.microsoft.com/office/word/2010/wordprocessingDrawing" '
        'xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing" '
        'xmlns:w10="urn:schemas-microsoft-com:office:word" '
        'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
        'xmlns:w14="http://schemas.microsoft.com/office/word/2010/wordml" '
        'xmlns:w15="http://schemas.microsoft.com/office/word/2012/wordml" '
        'xmlns:wpg="http://schemas.microsoft.com/office/word/2010/wordprocessingGroup" '
        'xmlns:wpi="http://schemas.microsoft.com/office/word/2010/wordprocessingInk" '
        'xmlns:wne="http://schemas.microsoft.com/office/word/2006/wordml" '
        'xmlns:wps="http://schemas.microsoft.com/office/word/2010/wordprocessingShape" '
        'mc:Ignorable="w14 w15 wp14">'
        "<w:body>"
        + "".join(body)
        + "</w:body></w:document>"
    )


def main():
    if not TEMPLATE.is_file():
        raise FileNotFoundError(f"Template not found: {TEMPLATE}")
    if not SOURCE.is_file():
        raise FileNotFoundError(f"Source markdown not found: {SOURCE}")

    source_text = SOURCE.read_text(encoding="utf-8").splitlines()
    blocks = parse_markdown(source_text)

    with zipfile.ZipFile(TEMPLATE, "r") as zin:
        template_xml = zin.read("word/document.xml").decode("utf-8")
        sect_pr = extract_sect_pr(template_xml)
        new_document_xml = build_document_xml(blocks, sect_pr).encode("utf-8")

        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(OUTPUT, "w", compression=zipfile.ZIP_DEFLATED) as zout:
            for item in zin.infolist():
                data = zin.read(item.filename)
                if item.filename == "word/document.xml":
                    data = new_document_xml
                zout.writestr(item, data)

    print(f"generated: {OUTPUT}")


if __name__ == "__main__":
    main()

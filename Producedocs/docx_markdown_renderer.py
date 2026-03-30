# -*- coding: utf-8 -*-

from dataclasses import dataclass, field
import re
import zipfile
from pathlib import Path
from typing import Iterable
from xml.sax.saxutils import escape


@dataclass(frozen=True)
class RenderOptions:
    top_level_as_title: bool = False
    center_following_paragraph_after: tuple[str, ...] = field(default_factory=tuple)
    title_size: int = 32
    h1_size: int = 28
    h2_size: int = 26
    h3_size: int = 24
    body_size: int = 24
    code_size: int = 20


def make_paragraph(text: str = "", *, bold: bool = False, size: int = 24, center: bool = False) -> str:
    ppr = '<w:pPr><w:jc w:val="center"/></w:pPr>' if center else ""
    rpr = ""
    if bold or size != 24:
        rpr_parts = []
        if bold:
            rpr_parts.extend(["<w:b/>", "<w:bCs/>"])
        if size != 24:
            rpr_parts.append(f'<w:sz w:val="{size}"/>')
            rpr_parts.append(f'<w:szCs w:val="{size}"/>')
        rpr = f"<w:rPr>{''.join(rpr_parts)}</w:rPr>"
    return f"<w:p>{ppr}<w:r>{rpr}<w:t xml:space=\"preserve\">{escape(text)}</w:t></w:r></w:p>"


def extract_sect_pr(document_xml: str) -> str:
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


def parse_markdown(md_text: str) -> Iterable[tuple[str, str]]:
    in_code = False
    code_buffer = []

    for raw_line in md_text.splitlines():
        line = raw_line.rstrip("\n")
        stripped = line.strip()

        if stripped.startswith("```"):
            if in_code:
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
        elif stripped.startswith("# "):
            yield ("h1", stripped[2:].strip())
        elif stripped.startswith("## "):
            yield ("h2", stripped[3:].strip())
        elif stripped.startswith("### "):
            yield ("h3", stripped[4:].strip())
        elif stripped.startswith("- "):
            yield ("bullet", stripped[2:].strip())
        elif re.match(r"^\d+\.\s+", stripped):
            yield ("number", stripped)
        else:
            yield ("p", stripped)


def _normalize_heading(text: str) -> str:
    return text.replace("：", "").replace(":", "").strip()


def build_document_xml(md_text: str, sect_pr: str, options: RenderOptions) -> str:
    body = []
    previous_heading = None
    center_after = {_normalize_heading(item) for item in options.center_following_paragraph_after}

    for kind, text in parse_markdown(md_text):
        if kind == "blank":
            body.append(make_paragraph(""))
            continue

        if kind == "h1":
            if options.top_level_as_title:
                body.append(make_paragraph(text, bold=True, size=options.title_size, center=True))
                body.append(make_paragraph(""))
                previous_heading = None
            else:
                body.append(make_paragraph(text, bold=True, size=options.h1_size))
                previous_heading = text
            continue

        if kind == "h2":
            body.append(make_paragraph(text, bold=True, size=options.h2_size))
            previous_heading = text
            continue

        if kind == "h3":
            body.append(make_paragraph(text, bold=True, size=options.h3_size))
            previous_heading = text
            continue

        center_after_heading = previous_heading is not None and _normalize_heading(previous_heading) in center_after
        body_text = text
        body_size = options.body_size
        body_bold = False
        body_center = False

        if kind == "code":
            body_size = options.code_size
        elif kind == "bullet":
            body_text = f"- {text}"

        if center_after_heading:
            body_bold = True
            body_center = True
            body_size = options.h1_size

        body.append(make_paragraph(body_text, bold=body_bold, size=body_size, center=body_center))
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


def render_markdown_to_docx(
    *,
    template_path: Path,
    source_path: Path,
    output_path: Path,
    options: RenderOptions,
) -> Path:
    source_text = source_path.read_text(encoding="utf-8")
    with zipfile.ZipFile(template_path, "r") as zin:
        template_xml = zin.read("word/document.xml").decode("utf-8")
        sect_pr = extract_sect_pr(template_xml)
        new_document_xml = build_document_xml(source_text, sect_pr, options).encode("utf-8")

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as zout:
            for item in zin.infolist():
                data = zin.read(item.filename)
                if item.filename == "word/document.xml":
                    data = new_document_xml
                zout.writestr(item, data)
    return output_path

"""Build the Chinese JMS Word manuscript from the canonical LaTeX source.

The conversion keeps the existing V6 DOCX as the style reference, rasterizes
TikZ/result figures and display equations at publication resolution, and lets
Pandoc construct a structured DOCX with editable body text and tables.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt


ROOT = Path(__file__).resolve().parents[2]
JMS = ROOT / "JMS"
SOURCE = JMS / "JMS_Review_CN.tex"
REFERENCE = JMS / "JMS_Revision_V6_CN.docx"
WORK = ROOT / ".tmp" / "jms_cn_docx_build"
ASSETS = WORK / "assets"
OUTPUT = ROOT / "output" / "docx" / "JMS_Revision_V9_CN.docx"


def run(*args: str, cwd: Path | None = None) -> None:
    result = subprocess.run(
        args,
        cwd=cwd or ROOT,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode != 0:
        tail = "\n".join(result.stdout.splitlines()[-80:])
        raise RuntimeError(f"Command failed ({result.returncode}): {' '.join(args)}\n{tail}")


def prepare_workdir() -> None:
    resolved = WORK.resolve()
    expected_parent = (ROOT / ".tmp").resolve()
    if resolved.parent != expected_parent:
        raise RuntimeError(f"Unsafe work directory: {resolved}")
    if resolved.exists():
        shutil.rmtree(resolved)
    ASSETS.mkdir(parents=True)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)


def render_tex_asset(body: str, stem: str, tikz: bool = False) -> Path:
    packages = [r"\usepackage{amsmath,amssymb,mathtools}"]
    if tikz:
        packages.extend(
            [
                r"\usepackage[UTF8,scheme=plain,fontset=windows]{ctex}",
                r"\usepackage{xcolor}",
                r"\usepackage{tikz}",
                r"\usetikzlibrary{arrows.meta,positioning,fit}",
            ]
        )
    wrapper = "\n".join(
        [
            r"\documentclass[varwidth,border=4pt]{standalone}",
            *packages,
            r"\begin{document}",
            body,
            r"\end{document}",
            "",
        ]
    )
    tex_path = WORK / f"{stem}.tex"
    tex_path.write_text(wrapper, encoding="utf-8")
    run(
        "xelatex",
        "-interaction=nonstopmode",
        "-halt-on-error",
        f"-output-directory={WORK}",
        str(tex_path),
        cwd=WORK,
    )
    pdf_path = WORK / f"{stem}.pdf"
    png_stem = ASSETS / stem
    run("pdftoppm", "-png", "-r", "300", "-singlefile", str(pdf_path), str(png_stem))
    png_path = png_stem.with_suffix(".png")
    if not png_path.exists():
        raise RuntimeError(f"Asset render failed: {png_path}")
    return png_path


def replace_display_equations(text: str) -> str:
    pattern = re.compile(
        r"\\begin\{(?P<env>align\*?|equation\*?)\}.*?\\end\{(?P=env)\}",
        re.S,
    )
    blocks = list(pattern.finditer(text))
    if len(blocks) != 14:
        raise RuntimeError(f"Expected 10 display-equation blocks; found {len(blocks)}")
    replacements: list[tuple[int, int, str]] = []
    equation_counter = 0
    for index, match in enumerate(blocks, start=1):
        block = match.group(0)
        numbered_rows = 1
        if match.group("env").startswith("align"):
            numbered_rows = block.count(r"\\") + (0 if re.search(r"\\\\\s*\\end", block) else 1)
        numbered_body = f"\\setcounter{{equation}}{{{equation_counter}}}\n" + block
        asset = render_tex_asset(numbered_body, f"equation_{index:02d}")
        replacement = "\n\\begin{center}\n\\includegraphics{" + asset.as_posix() + "}\n\\end{center}\n"
        replacements.append((match.start(), match.end(), replacement))
        equation_counter += numbered_rows
    if equation_counter != 27:
        raise RuntimeError(f"Expected final equation number 24; found {equation_counter}")
    for start, end, replacement in reversed(replacements):
        text = text[:start] + replacement + text[end:]
    return text


def replace_figures(text: str) -> str:
    pattern = re.compile(r"\\begin\{figure\}\[.*?\\end\{figure\}", re.S)
    figures = list(pattern.finditer(text))
    if len(figures) != 10:
        raise RuntimeError(f"Expected 10 figures; found {len(figures)}")
    replacements: list[tuple[int, int, str]] = []
    for index, match in enumerate(figures, start=1):
        block = match.group(0)
        caption_at = block.find(r"\caption")
        if caption_at < 0:
            raise RuntimeError(f"Figure {index} has no caption")
        caption_tail = block[caption_at:]
        if index <= 0:
            tikz_match = re.search(r"\\begin\{tikzpicture\}.*?\\end\{tikzpicture\}", block, re.S)
            if not tikz_match:
                raise RuntimeError(f"TikZ source missing for Figure {index}")
            asset = render_tex_asset(tikz_match.group(0), f"figure_{index:02d}", tikz=True)
        else:
            inc = re.search(r"\\includegraphics(?:\[[^]]*\])?\{(?P<name>[^}]+)\}", block)
            if not inc:
                raise RuntimeError(f"External graphic missing for Figure {index}")
            name = inc.group("name")
            source_pdf = JMS / "figures" / f"{name}.pdf"
            if not source_pdf.exists():
                raise FileNotFoundError(source_pdf)
            stem = ASSETS / f"figure_{index:02d}"
            run("pdftoppm", "-png", "-r", "300", "-singlefile", str(source_pdf), str(stem))
            asset = stem.with_suffix(".png")
        width = "0.86\\linewidth" if index == 1 else "\\linewidth"
        new_block = (
            "\\begin{figure}[htbp]\n\\centering\n"
            f"\\includegraphics[width={width}]{{{asset.as_posix()}}}\n"
            + caption_tail
        )
        replacements.append((match.start(), match.end(), new_block))
    for start, end, replacement in reversed(replacements):
        text = text[:start] + replacement + text[end:]
    return text


def build_intermediate_tex(source: str) -> tuple[str, str, str]:
    title = re.search(r"\\title\{(?P<value>.*?)\}\s*\\author", source, re.S)
    abstract = re.search(r"\\begin\{abstract\}(?P<value>.*?)\\end\{abstract\}", source, re.S)
    keywords = re.search(r"\\begin\{keyword\}(?P<value>.*?)\\end\{keyword\}", source, re.S)
    main = re.search(r"(?P<value>\\section\{引言\}.*)\\end\{document\}", source, re.S)
    if not all((title, abstract, keywords, main)):
        raise RuntimeError("Could not extract manuscript front matter or body")
    title_text = " ".join(title.group("value").split())
    keyword_text = re.sub(r"\s*\\sep\s*", "；", keywords.group("value").strip())
    body = main.group("value")
    # Let Pandoc/citeproc generate a structured bibliography. Pandoc's LaTeX
    # reader otherwise collapses the hand-written thebibliography environment
    # into one very long Word paragraph.
    body, bibliography_count = re.subn(
        r"\\begin\{thebibliography\}\{[^}]*\}.*?\\end\{thebibliography\}",
        "",
        body,
        flags=re.S,
    )
    if bibliography_count != 1:
        raise RuntimeError(
            f"Expected one thebibliography environment; found {bibliography_count}"
        )
    body = body.replace("pan2018survey", "pan2018clusterreview")
    body = body.replace("gu2024applied", "gu2024multifinger")
    body = body.replace(r"\method{}", "RDMCT-HBS").replace(r"\method", "RDMCT-HBS")
    body = body.replace(r"\cmax", r"C_{\max}").replace(r"\pdi", r"\mathrm{PDI}")
    # Normalize legacy inline math that Pandoc otherwise preserves as raw TeX.
    body = body.replace(r"\mathcal A^{\rm int}", r"\mathcal{A}^{\mathrm{int}}")
    body = body.replace(r"\mathcal J_c^{\rm DW}", r"\mathcal{J}_c^{\mathrm{DW}}")
    body = body.replace(r"\mathcal D_{\rm fix}", r"\mathcal{D}_{\mathrm{fix}}")
    body = replace_figures(body)
    body = replace_display_equations(body)
    front = "\n".join(
        [
            r"\begin{center}",
            "北京科技大学控制科学与工程系，北京市海淀区学院路30号，北京100083，中国\\\\",
            "*通讯作者：lshao@ustb.edu.cn",
            r"\end{center}",
            r"\section*{摘要}",
            abstract.group("value").strip(),
            "",
            r"\noindent\textbf{关键词：}" + keyword_text,
            "",
        ]
    )
    return title_text, front + body, keyword_text


def polish_docx(path: Path) -> None:
    doc = Document(path)
    for style_name in ("Normal", "Body Text", "First Paragraph"):
        if style_name in doc.styles:
            style = doc.styles[style_name]
            style.font.name = "Times New Roman"
            style._element.rPr.rFonts.set(qn("w:eastAsia"), "宋体")
            style.font.size = Pt(10.5)
    for style_name in ("Title", "Heading 1", "Heading 2", "Heading 3"):
        if style_name in doc.styles:
            style = doc.styles[style_name]
            style._element.rPr.rFonts.set(qn("w:eastAsia"), "黑体")
    figure_number = 0
    table_number = 0
    for para in doc.paragraphs:
        if para._p.xpath(".//w:drawing"):
            para.alignment = WD_ALIGN_PARAGRAPH.CENTER
            para.paragraph_format.keep_with_next = True
        if para.style and para.style.name in {"Image Caption", "Caption"}:
            figure_number += 1
            prefix_run = OxmlElement("w:r")
            prefix_text = OxmlElement("w:t")
            prefix_text.text = f"图 {figure_number}. "
            prefix_run.append(prefix_text)
            first_run = para._p.find(qn("w:r"))
            if first_run is None:
                para._p.append(prefix_run)
            else:
                first_run.addprevious(prefix_run)
            para.alignment = WD_ALIGN_PARAGRAPH.CENTER
            para.paragraph_format.keep_with_previous = True
        if para.style and para.style.name == "Table Caption":
            table_number += 1
            prefix_run = OxmlElement("w:r")
            prefix_text = OxmlElement("w:t")
            prefix_text.text = f"表 {table_number}. "
            prefix_run.append(prefix_text)
            first_run = para._p.find(qn("w:r"))
            if first_run is None:
                para._p.append(prefix_run)
            else:
                first_run.addprevious(prefix_run)
            para.alignment = WD_ALIGN_PARAGRAPH.CENTER
            para.paragraph_format.keep_with_next = True
        if para.text == "摘要" and "Heading 2" in doc.styles:
            para.style = doc.styles["Heading 2"]
    if figure_number != 9:
        raise RuntimeError(f"Expected 9 figure captions; found {figure_number}")
    if len(doc.inline_shapes) < 23:
        # Nine figures plus ten rendered display equations are expected.
        raise RuntimeError(f"Expected at least 19 inline shapes; found {len(doc.inline_shapes)}")
    if len(doc.tables) != 1:
        raise RuntimeError(f"Expected one manuscript table; found {len(doc.tables)}")
    if table_number != 1:
        raise RuntimeError(f"Expected one table caption; found {table_number}")
    doc.core_properties.title = "面向旋转腔半导体组合设备的系统级调度：可配置源接口两阶段MILP与结构感知精确搜索"
    doc.core_properties.subject = "Journal of Manufacturing Systems 中文审阅稿"
    doc.core_properties.author = "邵立珍；魏林聪；王蔚"
    doc.save(path)


def main() -> None:
    prepare_workdir()
    source = SOURCE.read_text(encoding="utf-8")
    title, converted, _ = build_intermediate_tex(source)
    intermediate = WORK / "JMS_Review_CN_docx.tex"
    intermediate.write_text(converted, encoding="utf-8")
    raw_docx = WORK / "JMS_Revision_V9_CN_raw.docx"
    run(
        "pandoc",
        str(intermediate),
        "--from=latex",
        "--to=docx",
        "--number-sections",
        "--citeproc",
        f"--bibliography={ROOT / 'cie' / 'products' / 'rdmct_cie_references.bib'}",
        "--metadata=reference-section-title:参考文献",
        f"--metadata=title:{title}",
        "--metadata=author:邵立珍（Lizhen Shao）；魏林聪（Lincong Wei）；王蔚（Wei Wang）",
        "--metadata=date:",
        f"--reference-doc={REFERENCE}",
        f"--resource-path={ASSETS}",
        f"--output={raw_docx}",
        cwd=ROOT,
    )
    shutil.copy2(raw_docx, OUTPUT)
    polish_docx(OUTPUT)
    print(OUTPUT)


if __name__ == "__main__":
    main()

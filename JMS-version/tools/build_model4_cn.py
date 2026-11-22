"""Compile the Chinese review manuscript with its flat submission figure set."""
from pathlib import Path
from tempfile import NamedTemporaryFile, TemporaryDirectory
import hashlib
import json
import re
import shutil
import subprocess

import pymupdf

PAPER = Path(__file__).resolve().parents[1]
BUILD = PAPER/'output/model4_cn_build'
MAIN = PAPER/'JMS_Review_CN.tex'


def flat_figures(source):
    paths = re.search(r'(?m)^\\graphicspath\{(.*)\}$', source)
    dirs = [PAPER]
    if paths:
        dirs += [PAPER / name for name in re.findall(r'\{([^{}]+)\}', paths[1])]
    figures = []
    for name in re.findall(r'\\includegraphics(?:\[[^\]]*\])?\{([^}]+)\}', source):
        if Path(name).name != name:
            raise ValueError(f'Figure must be referenced by its flat filename: {name}')
        names = [name] if Path(name).suffix else [name + ext for ext in ('.pdf','.png','.jpg','.jpeg')]
        found = next((d / n for d in dirs for n in names if (d / n).is_file()), None)
        if found is None:
            raise FileNotFoundError(f'Missing manuscript figure: {name}')
        figures.append(found)
    return figures


def compile_pdf(source_dir, figures):
    for figure in figures:
        shutil.copy2(figure, source_dir/figure.name)
    # The working directory contains only the flat figure files. XeLaTeX
    # reads the single original .tex; aux files from editor builds stay out.
    for iteration in range(1, 4):
        result = subprocess.run(
            ['xelatex', '-interaction=nonstopmode', '-halt-on-error', '-file-line-error',
             '-recorder', str(MAIN)],
            cwd=source_dir, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        (BUILD/f'pass_{iteration}.txt').write_bytes(result.stdout)
        if result.returncode:
            raise RuntimeError(result.stdout[-5000:].decode('utf-8', errors='replace'))
        print(f'XeLaTeX completed={iteration}/3 failed=0', flush=True)


def build(scratch):
    BUILD.mkdir(parents=True, exist_ok=True)
    original = MAIN.read_bytes()
    source = re.sub(r'(?m)(?<!\\)%.*$', '', original.decode('utf-8')).replace('\r\n', '\n')
    if re.search(r'\\(?:input|include|subfile|import)\b', source):
        raise ValueError('The manuscript text must be in the main .tex file')
    figures = flat_figures(source)
    compile_pdf(scratch, figures)
    log = (scratch/MAIN.with_suffix('.log').name).read_text('utf-8', errors='replace')
    problems = [line for line in log.splitlines() if any(term in line for term in
        ('Overfull', 'undefined references', 'undefined on input', 'Float too large', 'multiply defined',
         'Missing character:', 'Rerun to get', 'Label(s) may have changed'))]
    if problems:
        raise RuntimeError('\n'.join(problems))
    labels = re.findall(r'\\label\{([^}]+)\}', source)
    refs = re.findall(r'\\(?:ref|eqref)\{([^}]+)\}', source)
    assert len(labels) == len(set(labels)), 'Duplicate labels'
    assert not(set(refs)-set(labels)), 'Missing labels'
    cited = list(dict.fromkeys(k.strip() for group in re.findall(r'\\cite[pt]?\{([^}]+)\}', source)
                              for k in group.split(',')))
    assert cited == re.findall(r'\\bibitem\{([^}]+)\}', source), 'Check numbered bibliography order'
    pdf = scratch/MAIN.with_suffix('.pdf').name
    doc = pymupdf.open(pdf)
    pages = []
    for index, page in enumerate(doc):
        text = ''.join(page.get_text().split())
        if any(term in text for term in ('输入参数与集合', '主要决策变量与辅助变量',
            '第二阶段求解', '选割组件对照', '全资源可行排程')):
            pages.append(index)
            page.get_pixmap(matrix=pymupdf.Matrix(1.7,1.7)).save(BUILD/f'review_page_{index+1:02d}.png')
    from PIL import Image, ImageDraw
    for begin in range(0, len(doc), 6):
        canvas = Image.new('RGB',(1200,1500),'#dddddd')
        draw = ImageDraw.Draw(canvas)
        for pos,index in enumerate(range(begin,min(begin+6,len(doc)))):
            pix = doc[index].get_pixmap(matrix=pymupdf.Matrix(.65,.65))
            im = Image.frombytes('RGB',(pix.width,pix.height),pix.samples)
            im.thumbnail((380,710))
            x=(pos%3)*400+10; y=(pos//3)*750+30
            canvas.paste(im,(x,y));draw.text((x,y-20),f'Page {index+1}',fill='black')
        canvas.save(BUILD/f'contact_{begin+1:02d}.jpg')
    count = len(doc)
    doc.close()
    if MAIN.read_bytes() != original:
        raise RuntimeError('Manuscript changed during compilation; rebuild the latest source')
    for ext in ('.log', '.fls', '.aux', '.out'):
        name = MAIN.with_suffix(ext).name
        shutil.copy2(scratch/name, BUILD/name)
    for target in (BUILD/pdf.name, MAIN.with_suffix('.pdf'), PAPER/'output/pdf'/pdf.name):
        target.parent.mkdir(parents=True,exist_ok=True)
        with NamedTemporaryFile(dir=target.parent, suffix='.tmp', delete=False) as stage:
            staged = Path(stage.name)
        try:
            shutil.copy2(pdf, staged)
            staged.replace(target)
        finally:
            staged.unlink(missing_ok=True)
    report=dict(pages=count, reviewed_page_candidates=[p+1 for p in pages],
        source_sha256=hashlib.sha256(original).hexdigest(), flat_figures=[p.name for p in figures],
        pdf_sha256=hashlib.sha256(pdf.read_bytes()).hexdigest(), undefined_references=0,
        overfull_boxes=0, duplicate_labels=0, compilation_passes=3)
    (BUILD/'build_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf-8')
    print(json.dumps(report,ensure_ascii=False),flush=True)


def main():
    with TemporaryDirectory(prefix='jms-cn-') as folder:
        build(Path(folder))


if __name__ == '__main__':
    main()

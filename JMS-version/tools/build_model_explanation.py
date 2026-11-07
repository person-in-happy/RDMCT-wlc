"""Build the standalone current-model formula guide; leave manuscripts untouched."""
from pathlib import Path
import hashlib
import json
import re
import shutil
import subprocess

PAPER = Path(__file__).resolve().parents[1]
SOURCE = PAPER / 'MODEL_EXPLANATION_CN.md'
BUILD = PAPER / 'output/model_explanation_build'
OUTPUT = PAPER / 'output/pdf/MODEL_EXPLANATION_CN.pdf'


def main():
    BUILD.mkdir(parents=True, exist_ok=True)
    header = BUILD / 'header.tex'
    header.write_text(r'''\usepackage{xurl}
\emergencystretch=3em
\setlength{\parskip}{4pt}
\let\originaltexttt\texttt
\renewcommand{\texttt}[1]{{\small\originaltexttt{#1}}}
''', 'utf-8')
    tex = BUILD / 'MODEL_EXPLANATION_CN.tex'
    cmd = ['pandoc', str(SOURCE), '-s', '-t', 'latex', '--toc', '--toc-depth=2',
           '-V', 'documentclass=ctexart', '-V', 'fontsize=10pt',
           '-V', 'geometry:margin=22mm', '-V', 'colorlinks=true',
           '-V', 'mainfont=Times New Roman', '-V', 'monofont=Consolas',
           '-V', 'CJKmainfont=SimSun', '--include-in-header='+str(header), '-o', str(tex)]
    subprocess.run(cmd, check=True)
    for iteration in range(2):
        p = subprocess.run(['xelatex', '-interaction=nonstopmode', '-halt-on-error',
                            '-file-line-error', tex.name], cwd=BUILD,
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        (BUILD/f'pass_{iteration+1}.log').write_bytes(p.stdout)
        if p.returncode:
            raise RuntimeError(p.stdout[-5000:].decode('utf-8', errors='replace'))
        print(f'Formula PDF compile {iteration+1}/2', flush=True)
    log = tex.with_suffix('.log').read_text('utf-8', errors='replace')
    problems = [line for line in log.splitlines() if any(x in line for x in
                ('Overfull', 'Missing character', 'undefined references', 'multiply defined'))]
    if problems:
        raise RuntimeError('\n'.join(problems))
    import pymupdf
    from PIL import Image, ImageDraw
    pdf = tex.with_suffix('.pdf')
    doc = pymupdf.open(pdf)
    for index, page in enumerate(doc):
        page.get_pixmap(matrix=pymupdf.Matrix(1.3, 1.3)).save(BUILD/f'page_{index+1:02d}.png')
    for begin in range(0, len(doc), 6):
        sheet = Image.new('RGB', (1350, 1380), '#dddddd')
        draw = ImageDraw.Draw(sheet)
        for slot, index in enumerate(range(begin, min(begin+6, len(doc)))):
            im = Image.open(BUILD/f'page_{index+1:02d}.png').convert('RGB')
            im.thumbnail((430, 640))
            x, y = (slot%3)*450+10, (slot//3)*690+30
            sheet.paste(im, (x,y)); draw.text((x,y-20), f'Page {index+1}', fill='black')
        sheet.save(BUILD/f'contact_{begin+1:02d}.png')
    text = SOURCE.read_text('utf-8')
    tags = [int(n) for n in re.findall(r'\\tag\{(\d+)\}', text)]
    assert tags == list(range(1,32)), tags
    assert '\ufffd' not in text
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(pdf, OUTPUT)
    paths = [SOURCE, PAPER/'JMS_Review_CN.tex'] + [PAPER/'model4_pjob_nondecreasing_20261102'/n
             for n in ('model.py','pjob_order.py','pjobs.py','joint_pairing_model.py',
                       'joint_chamber_cycle_model.py','run_experiments.py','validate.py','physical_validate.py')]
    paths += [PAPER/'experiments'/n for n in ('nondecreasing_strengthening_20261102/strengthen_models.py',
              'nondecreasing_followup_20261102/followup_models.py',
              'nondecreasing_review_20261102/review_experiments.py')]
    report = dict(pages=len(doc), formulas=len(tags), overfull_boxes=0,
                  source_hashes={str(p.relative_to(PAPER)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},
                  pdf_sha256=hashlib.sha256(OUTPUT.read_bytes()).hexdigest(),
                  visual_review='pending', model_scope='pjob_global_nondecreasing_v1',
                  release_order_rule='global_pjob_index_nondecreasing_lp_pickup')
    (BUILD/'build_report.json').write_text(json.dumps(report, indent=2), 'utf-8')
    print(json.dumps(dict(pages=len(doc), formulas=len(tags), output=str(OUTPUT))), flush=True)


if __name__ == '__main__':
    main()

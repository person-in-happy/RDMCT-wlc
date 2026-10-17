"""Compile only the revised Chinese manuscript and render relevant pages."""
from pathlib import Path
import subprocess
import shutil
import hashlib
import json
import pymupdf

HERE = Path(__file__).resolve().parent
PAPER = HERE.parents[1]
BUILD = HERE / 'build'
BUILD.mkdir(exist_ok=True)
source = PAPER / 'JMS_Review_CN.tex'
for run in range(3):
    result = subprocess.run(
        ['xelatex', '-interaction=nonstopmode', '-halt-on-error',
         '-file-line-error', '-output-directory=' + str(BUILD), source.name],
        cwd=PAPER, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    (BUILD / f'pass_{run + 1}.txt').write_bytes(result.stdout)
    if result.returncode:
        raise RuntimeError(result.stdout[-4000:].decode('utf-8', errors='replace'))
log = (BUILD / 'JMS_Review_CN.log').read_text('utf-8', errors='replace')
issues = [line for line in log.splitlines() if any(word in line for word in
          ['Overfull', 'undefined references', 'undefined on input', 'Float too large', 'Missing character'])]
print('Build issues:', json.dumps(issues, ensure_ascii=False))
if issues:
    raise RuntimeError('Resolve build issues before publishing PDF')
pdf = BUILD / 'JMS_Review_CN.pdf'
doc = pymupdf.open(pdf)
needles = ['保守容量上界', '候选PW对集合容量', '核心集合与输入参数',
           '清洁自身不占用', '提前清洁', '并不要求准备']
pages = []
for i, page in enumerate(doc):
    compact = ''.join(page.get_text().split())
    if any(needle in compact for needle in needles):
        pages.append(i + 1)
        page.get_pixmap(matrix=pymupdf.Matrix(1.4, 1.4)).save(HERE / f'page_{i + 1:02}.png')
report = dict(pages=len(doc), rendered_pages=pages, issues=issues,
              source_sha256=hashlib.sha256(source.read_bytes()).hexdigest())
(HERE / 'build_report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
for target in [PAPER / 'JMS_Review_CN.pdf', PAPER / 'output/pdf/JMS_Review_CN.pdf']:
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(pdf, target)
print(json.dumps(report, ensure_ascii=False))

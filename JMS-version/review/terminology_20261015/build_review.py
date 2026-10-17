"""Validate the editorial scope, compile the CN source, and render every page."""
from pathlib import Path
import subprocess
import shutil
import hashlib
import json
import re
import difflib
import pymupdf
from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
PAPER = HERE.parents[1]
BUILD = HERE / 'build'
BUILD.mkdir(exist_ok=True)
source = PAPER / 'JMS_Review_CN.tex'
old = (HERE/'JMS_Review_CN.before.tex').read_text(encoding='utf-8')
new = source.read_text(encoding='utf-8')
eq = lambda s: re.findall(r'\\begin\{equation\}.*?\\end\{equation\}',s,re.S)
assert eq(old)==eq(new), 'Mathematical formulas changed'
assert re.findall(r'\\label\{[^}]*\}',old)==re.findall(r'\\label\{[^}]*\}',new)
assert re.findall(r'\\cite[pt]?\{[^}]*\}',old)==re.findall(r'\\cite[pt]?\{[^}]*\}',new)
results = lambda s: s[s.index(r'\section{计算实验与结果分析}'):s.index(r'\section*{CRediT')]
numbers = lambda s: re.findall(r'(?<![A-Za-z])\d+(?:\.\d+)?',s)
assert numbers(results(old))==numbers(results(new)), 'Experimental numerical content changed'
assert all(c in '\n\r\t' or ord(c)>=32 for c in new), 'Control character in LaTeX'
assert new.count('物料') == 1
assert not any(x in new for x in ['校准','混跑','的。','的，不另增','并不要求准备'])
baseline_pdf = HERE / 'JMS_Review_CN.before.pdf'
if not baseline_pdf.exists() and (PAPER/'JMS_Review_CN.pdf').exists():
    shutil.copy2(PAPER/'JMS_Review_CN.pdf', baseline_pdf)
for run in range(3):
    result = subprocess.run(['xelatex','-interaction=nonstopmode','-halt-on-error',
                             '-file-line-error','-output-directory='+str(BUILD),source.name],
                            cwd=PAPER,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
    (BUILD/f'pass_{run+1}.txt').write_bytes(result.stdout)
    if result.returncode:
        raise RuntimeError(result.stdout[-5000:].decode('utf-8',errors='replace'))
log = (BUILD/'JMS_Review_CN.log').read_text('utf-8',errors='replace')
issues = [x for x in log.splitlines() if any(k in x for k in [
    'Overfull','undefined references','undefined on input','Float too large','Missing character'])]
if issues:
    raise RuntimeError('\n'.join(issues))
pdf = BUILD/'JMS_Review_CN.pdf'
doc = pymupdf.open(pdf)
pngs = []
for i,page in enumerate(doc):
    p = HERE/f'page_{i+1:02}.png'
    page.get_pixmap(matrix=pymupdf.Matrix(1.3,1.3)).save(p)
    pngs.append(p)
for i in range(0,len(pngs),4):
    sheet = Image.new('RGB',(1100,1600),'#cccccc')
    draw = ImageDraw.Draw(sheet)
    for j,p in enumerate(pngs[i:i+4]):
        im=Image.open(p).convert('RGB')
        im.thumbnail((540,765))
        x=(j%2)*550+(550-im.width)//2
        y=(j//2)*800+25
        sheet.paste(im,(x,y))
        draw.text((x,y-20),f'Page {i+j+1}',fill='black')
    sheet.save(HERE/f'contact_{i//4+1}.png')
report={'pages':len(doc),'equations_unchanged':len(eq(new)),
        'experimental_numbers_unchanged':True,'labels_citations_unchanged':True,
        'compile_issues':issues,'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest()}
(HERE/'build_report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
(HERE/'revision.diff').write_text(''.join(difflib.unified_diff(old.splitlines(True),new.splitlines(True),fromfile='before',tofile='after')),encoding='utf-8')
for target in [PAPER/'JMS_Review_CN.pdf',PAPER/'output/pdf/JMS_Review_CN.pdf']:
    target.parent.mkdir(exist_ok=True,parents=True)
    shutil.copy2(pdf,target)
print(json.dumps(report))

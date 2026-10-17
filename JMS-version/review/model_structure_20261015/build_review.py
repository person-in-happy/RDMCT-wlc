"""Audit scope, compile the reorganized manuscript, and render all pages."""
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
BUILD = HERE/'build'
BUILD.mkdir(exist_ok=True)
source = PAPER/'JMS_Review_CN.tex'
old = (HERE/'JMS_Review_CN.before_reorganization.tex').read_text(encoding='utf-8')
new = source.read_text(encoding='utf-8')
start = r'\section{问题描述与两阶段调度模型}'
end = r'\section{结构感知MILP求解框架}'
assert old.split(start)[0] == new.split(start)[0]
assert old.split(end)[1] == new.split(end)[1]
def equations(s):
    return {re.search(r'\\label\{([^}]+)\}',m[0])[1]:m[0]
            for m in re.finditer(r'\\begin\{equation\}.*?\\end\{equation\}',s,re.S)}
a,b = equations(old),equations(new)
assert len(a)==38 and len(b)==42
for label in a:
    if label!='eq:secondary-objective-cn':
        assert a[label]==b[label],label
def canonical(s):
    s=re.sub(r'\\(?:begin|end)\{[^}]+\}|\\label\{[^}]+\}','',s)
    s=re.sub(r'\\qquad|\\quad|\\,|\\\\','',s)
    return re.sub(r'[\s.,&]','',s)
parts=['domain','wait','rhythm','softwait','objective']
assert canonical(a['eq:secondary-objective-cn'])==canonical(''.join(b[f'eq:secondary-{p}-cn'] for p in parts))
labels = re.findall(r'\\label\{([^}]+)\}',new)
refs = re.findall(r'\\(?:eqref|ref)\{([^}]+)\}',new)
assert len(labels)==len(set(labels))
assert set(refs)<=set(labels)
assert all(c in '\n\r\t' or ord(c)>=32 for c in new)
baseline = HERE/'JMS_Review_CN.before.pdf'
if not baseline.exists():
    shutil.copy2(PAPER/'JMS_Review_CN.pdf',baseline)
for run in range(3):
    result=subprocess.run(['xelatex','-interaction=nonstopmode','-halt-on-error',
        '-file-line-error','-output-directory='+str(BUILD),source.name],
        cwd=PAPER,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
    (BUILD/f'pass_{run+1}.txt').write_bytes(result.stdout)
    if result.returncode:
        raise RuntimeError(result.stdout[-5000:].decode('utf-8',errors='replace'))
log=(BUILD/'JMS_Review_CN.log').read_text('utf-8',errors='replace')
issues=[line for line in log.splitlines() if any(k in line for k in
    ['Overfull','undefined references','undefined on input','Float too large','Missing character'])]
assert not issues,'\n'.join(issues)
pdf=BUILD/'JMS_Review_CN.pdf'
doc=pymupdf.open(pdf)
pngs=[]
for i,page in enumerate(doc):
    p=HERE/f'page_{i+1:02}.png'
    page.get_pixmap(matrix=pymupdf.Matrix(1.3,1.3)).save(p)
    pngs.append(p)
for i in range(0,len(pngs),4):
    sheet=Image.new('RGB',(1100,1600),'#cccccc')
    draw=ImageDraw.Draw(sheet)
    for j,p in enumerate(pngs[i:i+4]):
        im=Image.open(p).convert('RGB')
        im.thumbnail((540,765))
        x=(j%2)*550+(550-im.width)//2
        y=(j//2)*800+25
        sheet.paste(im,(x,y))
        draw.text((x,y-20),f'Page {i+j+1}',fill='black')
    sheet.save(HERE/f'contact_{i//4+1}.png')
report={'pages':len(doc),'total_equation_blocks':len(b),
    'unchanged_equation_blocks':37,'secondary_split_equivalent':True,
    'outside_model_unchanged':True,'references_resolved':True,
    'compile_issues':issues,'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest()}
(HERE/'build_report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
(HERE/'revision.diff').write_text(''.join(difflib.unified_diff(old.splitlines(True),new.splitlines(True),fromfile='before',tofile='after')),encoding='utf-8')
print(json.dumps(report))

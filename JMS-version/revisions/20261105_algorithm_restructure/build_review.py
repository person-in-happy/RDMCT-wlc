from pathlib import Path
import re, json, shutil, subprocess, hashlib, difflib
import pymupdf
from PIL import Image, ImageDraw
from simplify_algorithm import OUTSIDE_EDITS

HERE = Path(__file__).resolve().parent
PAPER = HERE.parents[1]
BUILD = HERE / 'build'
BUILD.mkdir(exist_ok=True)
source = (PAPER/'JMS_Review_CN.tex').read_text('utf-8')
old = (HERE/'before/JMS_Review_CN.tex').read_text('utf-8')
expected = old
for a,b in OUTSIDE_EDITS.items():
    expected = expected.replace(a,b)
assert source[:source.index(r'\section{初始排程')] == expected[:expected.index(r'\section{批次任务编码、两阶段求解与晶圆解码}')]
def split_experiments(s):
    s = s[s.index(r'\section{计算实验与结果分析}'):]
    pattern = r'\\begin\{(?:table\*|figure\*)\}.*?\\end\{(?:table\*|figure\*)\}'
    floats = re.findall(pattern,s,re.S)
    prose = re.sub(pattern,'',s,flags=re.S)
    return re.sub(r'\n{2,}','\n\n',prose),floats
assert split_experiments(source) == split_experiments(expected)
labels = re.findall(r'\\label\{([^}]+)\}', source)
refs = re.findall(r'\\(?:ref|eqref)\{([^}]+)\}', source)
assert len(labels) == len(set(labels))
assert not (set(refs)-set(labels))
shutil.copy2(PAPER/'JMS_Review_CN.tex', BUILD/'JMS_Review_CN.tex')
for name in re.findall(r'\\includegraphics(?:\[[^\]]*\])?\{([^}]+)\}', source):
    matches = [p for p in (PAPER/'figures').rglob(name+'.*') if p.suffix.lower() in ('.pdf','.png','.jpg','.jpeg','.eps')]
    assert matches, name
    for fig in matches:
        target = BUILD/fig.relative_to(PAPER)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(fig,target)
for index in range(3):
    result = subprocess.run(['xelatex','-interaction=nonstopmode','-halt-on-error','-file-line-error','JMS_Review_CN.tex'],cwd=BUILD,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
    (BUILD/f'pass_{index+1}.txt').write_bytes(result.stdout)
    if result.returncode:
        raise RuntimeError(result.stdout[-5000:].decode('utf-8',errors='replace'))
    print(f'XeLaTeX completed={index+1}/3 failed=0',flush=True)
log = (BUILD/'JMS_Review_CN.log').read_text('utf-8',errors='replace')
fatal = [line for line in log.splitlines() if any(t in line for t in ('undefined references','undefined on input','multiply defined','Float too large','Missing character'))]
assert not fatal, fatal
overfull = [line for line in log.splitlines() if 'Overfull' in line]
doc = pymupdf.open(BUILD/'JMS_Review_CN.pdf')
algorithm_pages = []
for i,p in enumerate(doc):
    s = ''.join(p.get_text().split())
    if any(t in s for t in ('初始排程构造','将PW对排入','沿完整物理路径','保持基本结构','从初始排程到','收尾动作的时序压缩','晶圆身份恢复','从批次任务到具体晶圆排程')):
        algorithm_pages.append(i+1)
        p.get_pixmap(matrix=pymupdf.Matrix(1.6,1.6)).save(BUILD/f'page_{i+1:02}.png')
for start in range(0,len(doc),6):
    canvas = Image.new('RGB',(1440,1500),'#ddd')
    draw = ImageDraw.Draw(canvas)
    for k,i in enumerate(range(start,min(start+6,len(doc)))):
        pix=doc[i].get_pixmap(matrix=pymupdf.Matrix(.75,.75))
        im=Image.frombytes('RGB',(pix.width,pix.height),pix.samples)
        im.thumbnail((460,710))
        x=(k%3)*480+10; y=(k//3)*750+30
        canvas.paste(im,(x,y));draw.text((x,y-20),f'Page {i+1}',fill='black')
    canvas.save(BUILD/f'contact_{start+1:02}.jpg')
(HERE/'manuscript.diff').write_text(''.join(difflib.unified_diff(old.splitlines(True),source.splitlines(True),fromfile='before/JMS_Review_CN.tex',tofile='JMS_Review_CN.tex')),encoding='utf-8')
report = dict(pages=len(doc),algorithm_pages=algorithm_pages,compilation_passes=3,undefined_references=0,duplicate_labels=0,overfull_warnings=overfull,source_sha256=hashlib.sha256((PAPER/'JMS_Review_CN.tex').read_bytes()).hexdigest(),pdf_sha256=hashlib.sha256((BUILD/'JMS_Review_CN.pdf').read_bytes()).hexdigest(),scope='Section 3 restructured and condensed; defensive prose in abstract/results removed per user steering; unchanged section 4 floats moved for page flow. Model, data, numerical results and other text preserved.',experiments_run=False,visual_review='pending')
(HERE/'review.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf-8')
print(json.dumps(report,ensure_ascii=False),flush=True)

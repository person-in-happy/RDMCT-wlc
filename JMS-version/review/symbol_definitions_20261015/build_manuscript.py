from pathlib import Path
import re,json,subprocess,hashlib
import pymupdf
from PIL import Image,ImageDraw

HERE=Path(__file__).resolve().parent
PAPER=HERE.parents[1]
BUILD=HERE/'manuscript_build'
BUILD.mkdir(exist_ok=True)
source=PAPER/'JMS_Review_CN.tex'
old=(HERE/'JMS_Review_CN.before.tex').read_text(encoding='utf-8')
new=source.read_text(encoding='utf-8')
eq=lambda s:re.findall(r'\\begin\{equation\}.*?\\end\{equation\}',s,re.S)
assert eq(old)==eq(new) and len(eq(new))==42
assert re.findall(r'\\label\{[^}]+\}',old)==re.findall(r'\\label\{[^}]+\}',new)
assert re.findall(r'\\cite[pt]?\{[^}]+\}',old)==re.findall(r'\\cite[pt]?\{[^}]+\}',new)
# Numerical experiment tables and figures must remain identical.
floats=lambda s:re.findall(r'\\begin\{(?:table\*?|figure\*?)\}.*?\\end\{(?:table\*?|figure\*?)\}',s[s.index(r'\section{计算实验与结果分析}'):],re.S)
assert floats(old)==floats(new)
for run in range(3):
    res=subprocess.run(['xelatex','-interaction=nonstopmode','-halt-on-error','-file-line-error',
        '-output-directory='+str(BUILD),source.name],cwd=PAPER,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
    (BUILD/f'pass_{run+1}.txt').write_bytes(res.stdout)
    if res.returncode: raise RuntimeError(res.stdout[-6000:].decode('utf-8',errors='replace'))
log=(BUILD/'JMS_Review_CN.log').read_text(encoding='utf-8',errors='replace')
issues=[line for line in log.splitlines() if any(k in line for k in ['Overfull','Float too large','undefined references','undefined on input','Missing character'])]
doc=pymupdf.open(BUILD/'JMS_Review_CN.pdf')
paths=[]
for i,page in enumerate(doc):
    p=HERE/f'manuscript_{i+1:02}.png'; page.get_pixmap(matrix=pymupdf.Matrix(1.3,1.3)).save(p); paths.append(p)
for i in range(0,len(paths),4):
    sheet=Image.new('RGB',(1100,1600),'#ddd'); draw=ImageDraw.Draw(sheet)
    for j,p in enumerate(paths[i:i+4]):
        im=Image.open(p).convert('RGB'); im.thumbnail((540,765))
        x=j%2*550+(550-im.width)//2; y=j//2*800+25
        sheet.paste(im,(x,y)); draw.text((x,y-20),f'Page {i+j+1}',fill='black')
    sheet.save(HERE/f'manuscript_contact_{i//4+1}.png')
report={'pages':len(doc),'equations_unchanged':42,'experiment_tables_figures_unchanged':True,
        'compile_issues':issues,'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest()}
(HERE/'manuscript_report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report))

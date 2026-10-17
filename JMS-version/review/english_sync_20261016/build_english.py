from pathlib import Path
import re,json,subprocess,hashlib
import pymupdf
from PIL import Image,ImageDraw
HERE=Path(__file__).resolve().parent; PAPER=HERE.parents[1]
BUILD=HERE/'english_build';BUILD.mkdir(exist_ok=True)
source=PAPER/'JMS_Submission_EN.tex'
for i in range(3):
    res=subprocess.run(['xelatex','-interaction=nonstopmode','-halt-on-error','-file-line-error','-output-directory='+str(BUILD),source.name],cwd=PAPER,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
    (BUILD/f'pass_{i+1}.txt').write_bytes(res.stdout)
    if res.returncode:raise RuntimeError(res.stdout[-6000:].decode('utf-8',errors='replace'))
log=(BUILD/'JMS_Submission_EN.log').read_text(encoding='utf-8',errors='replace')
issues=[s for s in log.splitlines() if any(k in s for k in ['Overfull','Float too large','undefined references','undefined on input','Missing character'])]
doc=pymupdf.open(BUILD/'JMS_Submission_EN.pdf');paths=[]
for i,page in enumerate(doc):
    path=HERE/f'english_{i+1:02}.png';page.get_pixmap(matrix=pymupdf.Matrix(1.4,1.4)).save(path);paths.append(path)
for i in range(0,len(paths),4):
    sheet=Image.new('RGB',(1100,1600),'#ddd');draw=ImageDraw.Draw(sheet)
    for j,path in enumerate(paths[i:i+4]):
        im=Image.open(path).convert('RGB');im.thumbnail((540,765));x=j%2*550+(550-im.width)//2;y=j//2*800+25
        sheet.paste(im,(x,y));draw.text((x,y-20),f'Page {i+j+1}',fill='black')
    sheet.save(HERE/f'english_contact_{i//4+1}.png')
report={'pages':len(doc),'issues':issues,'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest()}
(HERE/'english_build_report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report))

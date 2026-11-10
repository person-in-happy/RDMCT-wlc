from pathlib import Path
import subprocess,shutil,json,re,hashlib
import pymupdf
from PIL import Image,ImageDraw
HERE=Path(__file__).resolve().parent
P=HERE.parents[1]/'products'
B=HERE/'build';B.mkdir(exist_ok=True)
name='rdmct_cie_analysis_focused_zh'
for file in [P/(name+'.tex'),P/'rdmct_cie_current_references.bib',P/'title_page.tex',P/'cover_letter_draft.tex']+list(P.glob('fig_*_cn*.pdf')):
    shutil.copy2(file,B/file.name)
commands=[['xelatex','-interaction=nonstopmode','-halt-on-error',f'-output-directory={B}',name+'.tex'],
          ['biber','--input-directory',str(B),'--output-directory',str(B),name]]
commands += [commands[0]]*3
for i,cmd in enumerate(commands):
    r=subprocess.run(cmd,cwd=B,capture_output=True,text=True,encoding='utf-8',errors='replace')
    (B/f'pass_{i+1}.log').write_text(r.stdout+'\n'+r.stderr,encoding='utf-8')
    print(i+1,cmd[0],r.returncode,flush=True)
    if r.returncode:print(r.stdout[-2400:]+r.stderr[-1200:]);raise SystemExit(r.returncode)
log=(B/(name+'.log')).read_text('utf-8',errors='replace')
issues=[line for line in log.splitlines() if any(x in line for x in ('Overfull','undefined','multiply defined','Missing character','LaTeX Error'))]
pdf=B/(name+'.pdf');doc=pymupdf.open(pdf)
render=HERE/'rendered';render.mkdir(exist_ok=True)
for i,page in enumerate(doc):
    page.get_pixmap(matrix=pymupdf.Matrix(1.2,1.2)).save(render/f'page-{i+1:02d}.png')
for base in range(0,len(doc),12):
    sheet=Image.new('RGB',(1200,4*430),'#dddddd');draw=ImageDraw.Draw(sheet)
    for offset in range(min(12,len(doc)-base)):
        im=Image.open(render/f'page-{base+offset+1:02d}.png');im.thumbnail((390,400))
        x=(offset%3)*400;y=(offset//3)*430
        sheet.paste(im,(x,y+23));draw.text((x+5,y+3),str(base+offset+1),fill='black')
    sheet.save(render/f'contact-{base+1:02d}.png')
for target in (P/pdf.name,HERE.parents[1]/'output/pdf'/pdf.name):
    target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(pdf,target)
for stem in ('title_page','cover_letter_draft'):
    r=subprocess.run(['xelatex','-interaction=nonstopmode','-halt-on-error',f'-output-directory={B}',stem+'.tex'],cwd=B,capture_output=True,text=True,encoding='utf-8',errors='replace')
    (B/(stem+'_console.log')).write_text(r.stdout+r.stderr,encoding='utf-8')
    if r.returncode:raise RuntimeError(r.stdout[-2000:])
    shutil.copy2(B/(stem+'.pdf'),P/(stem+'.pdf'))
report=dict(pages=len(doc),issues=issues,passes=5,pdf_sha256=hashlib.sha256(pdf.read_bytes()).hexdigest(),
            source_sha256=hashlib.sha256((P/(name+'.tex')).read_bytes()).hexdigest(),solver_started=False)
(HERE/'build_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(report,ensure_ascii=False,indent=2))

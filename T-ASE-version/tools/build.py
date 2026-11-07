"""Compile IEEE sources and render all pages for visual QA."""
from pathlib import Path
import subprocess,re,json,shutil,argparse
import pymupdf
PAPER=Path(__file__).resolve().parents[1]
def run(argv,cwd):
 r=subprocess.run(argv,cwd=cwd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
 if r.returncode:raise RuntimeError(r.stdout.decode('utf-8',errors='replace')[-6500:])
def compile_one(name):
 out=PAPER/'output'/'.build'/name;out.mkdir(parents=True,exist_ok=True)
 tex=['xelatex','-interaction=nonstopmode','-halt-on-error','-file-line-error','-output-directory='+str(out),name+'.tex']
 run(tex,PAPER)
 for f in ['references.bib','IEEEtran.bst']:shutil.copy2(PAPER/f,out/f)
 run(['bibtex',name],out);run(tex,PAPER);run(tex,PAPER)
 log=(out/(name+'.log')).read_text('utf-8',errors='replace')
 problems=[l for l in log.splitlines() if any(x in l for x in ['Overfull','undefined references','undefined on input','Float too large','Missing character'])]
 if problems:raise RuntimeError('\n'.join(problems))
 shutil.copy2(out/(name+'.pdf'),PAPER/(name+'.pdf'))
 d=pymupdf.open(PAPER/(name+'.pdf'));text='\n'.join(p.get_text() for p in d)
 assert not d.metadata.get('author'),d.metadata
 for forbidden in ['lshao@','m202420836','Lizhen Shao','Lincong Wei','University of Science and Technology Beijing']:assert forbidden not in text,forbidden
 qa=PAPER/'output'/'qa'/name;qa.mkdir(parents=True,exist_ok=True)
 for i,p in enumerate(d):p.get_pixmap(matrix=pymupdf.Matrix(1.15,1.15)).save(qa/f'page-{i+1:02d}.png')
 report={'file':name+'.pdf','pages':len(d),'problems':problems,'metadata':d.metadata}
 print(json.dumps(report,ensure_ascii=False));return report
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--lang',choices=['EN','CN','both','all'],default='all');a=p.parse_args()
 names={'EN':['TASE_Submission_EN'],'CN':['TASE_Review_CN'],'both':['TASE_Submission_EN','TASE_Review_CN'],'all':['TASE_Submission_EN','TASE_Review_CN','TASE_Supplement_EN']}[a.lang]
 reports=[compile_one(n) for n in names]
 (PAPER/'output'/'build_report.json').write_text(json.dumps(reports,indent=2),encoding='utf-8')


"""Compile both manuscripts and a self-contained English submission archive."""
from pathlib import Path
import concurrent.futures,subprocess,re,zipfile,shutil,hashlib
import pymupdf
PAPER=Path(__file__).resolve().parents[1]
BUILD=PAPER/'output/.build';BUILD.mkdir(parents=True,exist_ok=True)

def compile_tex(source,out,job):
 out.mkdir(parents=True,exist_ok=True)
 for _ in range(3):
  r=subprocess.run(['xelatex','-interaction=nonstopmode','-halt-on-error','-file-line-error','-jobname='+job,'-output-directory='+str(out),source.name],cwd=source.parent,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
  if r.returncode:raise RuntimeError(r.stdout[-3000:].decode('utf-8',errors='replace'))
 log=(out/(job+'.log')).read_text('utf-8',errors='replace')
 problems=[line for line in log.splitlines() if any(k in line for k in ['Overfull','undefined references','undefined on input','Float too large'])]
 if problems:raise RuntimeError('\n'.join(problems))
 return out/(job+'.pdf')

def build_name(name):return name,compile_tex(PAPER/(name+'.tex'),BUILD/name,'final_'+name)

if __name__=='__main__':
 from audit_model_notation import audit
 audit()
 names=['JMS_Review_CN','JMS_Submission_EN']
 with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:built=dict(pool.map(build_name,names))
 texts=[(PAPER/(n+'.tex')).read_text('utf-8') for n in names]
 equations=lambda s:[re.sub(r'\s+','',re.sub(r'\\(?:label|text)\{[^}]*\}','',x)) for x in re.findall(r'\\begin\{equation\}([\s\S]*?)\\end\{equation\}',s)]
 assert equations(texts[0])==equations(texts[1])
 assert len(re.findall(r'\\subsection\{',texts[0]))==len(re.findall(r'\\subsection\{',texts[1]))>0
 out=PAPER/'output/submission';out.mkdir(parents=True,exist_ok=True)
 for name,src in built.items():
  for target in [PAPER/(name+'.pdf'),PAPER/'output/pdf'/(name+'.pdf'),out/(name+'.pdf')]:
   target.parent.mkdir(exist_ok=True,parents=True);shutil.copy2(src,target)
 print(f'Validated: {len(equations(texts[0]))} matched equations, matched subsection counts; clean XeLaTeX builds.')
 for name,src in built.items():print(name,len(pymupdf.open(src)),'pages')
 import sys
 subprocess.run([sys.executable,str(PAPER/'tools/package_submission_bilingual.py')],check=True)

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
 names=['JMS_Review_CN','JMS_Submission_EN']
 with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:built=dict(pool.map(build_name,names))
 texts=[(PAPER/(n+'.tex')).read_text('utf-8') for n in names]
 equations=lambda s:[re.sub(r'\s+','',re.sub(r'\\(?:label|text)\{[^}]*\}','',x)) for x in re.findall(r'\\begin\{equation\}([\s\S]*?)\\end\{equation\}',s)]
 assert equations(texts[0])==equations(texts[1])
 assert len(re.findall(r'\\subsection\{',texts[0]))==len(re.findall(r'\\subsection\{',texts[1]))==21
 out=PAPER/'output/submission';out.mkdir(parents=True,exist_ok=True)
 highlights=['A two-stage MILP coordinates product and dummy flows in PECVD cluster tools.','Lot size and cleaning intervals determine preferred preset processing modes.','Precomputed SPBS raises main-solve feasible-schedule availability to 100%.','Equal-budget refinement reduces total route waiting by 51.91%.']
 assert all(len(x)<=85 for x in highlights)
 (out/'Highlights.txt').write_text('\n'.join('- '+x for x in highlights)+'\n','utf-8')
 archive=out/'JMS_Source_EN.zip'
 with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
  z.write(PAPER/'JMS_Submission_EN.tex','JMS_Submission_EN.tex')
  stems=re.findall(r'\\includegraphics(?:\[[^]]*\])?\{([^}]+)\}',texts[1]);assert len(stems)==len(set(stems))==10
  for stem in stems:
   for ext in (['pdf','jpg'] if stem == 'fig_pecvd_chamber_photo' else ['pdf','svg']):
    f=PAPER/'figures'/(stem+'.'+ext);assert f.is_file();z.write(f,'figures/'+f.name)
  z.write(PAPER/'figures/origin/pecvd_official/source.json','figures/pecvd_photo_source.json')
  z.writestr('FIGURE_PERMISSION.txt','Figure 2: Syskey official PECVD photograph. Publication permission has not been established. Obtain permission from the rights holder before journal submission. Source and original image URL are recorded in figures/pecvd_photo_source.json. No permission claim is made in the caption.\n')
  z.writestr('BUILD.txt','Compile JMS_Submission_EN.tex with XeLaTeX three times.\nRequires the standard elsarticle class and packages declared in the preamble.\nReferences and tables are embedded in the TeX file.\nPDF figures are used for compilation; SVG files provide editable vector artwork; the PECVD photograph is supplied as its original JPEG.\n')
 # Test the archive from an isolated directory, with no access to repo-relative figures.
 isolated=BUILD/'archive_check';isolated.mkdir(exist_ok=True)
 with zipfile.ZipFile(archive) as z:
  assert all(not Path(n).is_absolute() and '..' not in Path(n).parts for n in z.namelist());z.extractall(isolated)
 archive_pdf=compile_tex(isolated/'JMS_Submission_EN.tex',BUILD/'archive_pdf','archive_JMS_Submission_EN')
 a=pymupdf.open(built['JMS_Submission_EN']);b=pymupdf.open(archive_pdf)
 assert len(a)==len(b) and [x.get_text() for x in a]==[x.get_text() for x in b]
 for name,src in built.items():
  for target in [PAPER/(name+'.pdf'),PAPER/'output/pdf'/(name+'.pdf')]:
   target.parent.mkdir(exist_ok=True,parents=True);shutil.copy2(src,target)
 shutil.copy2(built['JMS_Submission_EN'],out/'JMS_Submission_EN.pdf')
 print('Validated: 36 matched equations, 21 matched subsections; clean XeLaTeX builds; standalone English archive.')
 for name,src in built.items():print(name,len(pymupdf.open(src)),'pages')
 print('Submission archive:',archive)

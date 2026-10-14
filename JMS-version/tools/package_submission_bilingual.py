"""Prepare flat LaTeX archives per Elsevier's official author instructions."""
from pathlib import Path
import re,zipfile,subprocess,shutil,concurrent.futures
import pymupdf
P=Path(__file__).resolve().parents[1];OUT=P/'output/submission';WORK=P/'output/.package_check'
H={
'CN':['联合优化晶圆配对、辅助借用、腔室分配与事件时序。','模型显式协调VTR洁净手、脏手及辅助晶圆复用。','固定产品结构下，辅助身份调整将4片完工时间缩短24.25%。','六组等预算精修将运输等待降低8.40%–29.21%。'],
'EN':['Pairing, dummy allocation, chamber assignment, and timing are jointly optimized.','The model coordinates clean and dirty VTR hands with dummy-wafer reuse.','Reassigning dummy identities cuts a four-product makespan by 24.25%.','Equal-budget refinement cuts transport waiting by 8.40%–29.21% in six cases.']}

def build(lang):
 name='JMS_Review_CN' if lang=='CN' else 'JMS_Submission_EN';text=(P/(name+'.tex')).read_text('utf-8');stems=re.findall(r'\\includegraphics(?:\[[^]]*\])?\{([^}]+)\}',text)
 assert len(stems)==len(set(stems))==10
 assert all(len(x)<=85 for x in H[lang])
 text=re.sub(r'\\graphicspath\{[^\n]*',lambda m:r'\graphicspath{{./}}',text)
 files={}
 for i,stem in enumerate(stems,1):
  dest=f'Figure{i}.pdf';text=text.replace('{'+stem+'}','{'+dest+'}');files[dest]=(P/'figures'/(stem+'.pdf')).read_bytes()
 files[name+'.tex']=text.encode('utf-8');files[name+'.pdf']=(P/(name+'.pdf')).read_bytes()
 files['Highlights.txt']=('\n'.join('- '+x for x in H[lang])+'\n').encode('utf-8')
 coi=('作者声明不存在可能影响本文工作的已知财务利益或个人关系。' if lang=='CN' else 'The authors declare that they have no known competing financial interests or personal relationships that could have appeared to influence the work reported in this paper.')
 files['Declaration_of_Interest.txt']=(coi+'\n').encode('utf-8')
 out=OUT/f'JMS_Submission_{lang}.zip'
 with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
  for n,b in files.items():z.writestr(n,b)
 stage=WORK/lang;stage.mkdir(parents=True,exist_ok=True)
 with zipfile.ZipFile(out) as z:
  assert z.testzip() is None
  assert all('/' not in n and '\\' not in n and len(n)<80 for n in z.namelist())
  assert len(z.namelist())==14
  z.extractall(stage)
 for _ in range(3):
  r=subprocess.run(['xelatex','-interaction=nonstopmode','-halt-on-error','-file-line-error',name+'.tex'],cwd=stage,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
  if r.returncode:raise RuntimeError(r.stdout[-2500:].decode('utf-8',errors='replace'))
 log=(stage/(name+'.log')).read_text('utf-8',errors='replace');bad=[x for x in log.splitlines() if any(k in x for k in ['Overfull','undefined references','undefined on input','Float too large'])];assert not bad,bad
 original=pymupdf.open(P/(name+'.pdf'));rebuilt=pymupdf.open(stage/(name+'.pdf'))
 assert len(original)==len(rebuilt) and [x.get_text() for x in original]==[x.get_text() for x in rebuilt]
 print(f'{lang}: flat archive, 14 files, 10 figures, {len(original)} pages; independently compiled text identical.',flush=True)
 return out
if __name__=='__main__':
 OUT.mkdir(parents=True,exist_ok=True)
 with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:list(pool.map(build,['CN','EN']))
 assert WORK.resolve()==P.resolve()/'output/.package_check'
 shutil.rmtree(WORK)

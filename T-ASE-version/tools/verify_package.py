from pathlib import Path
import json,re,hashlib,zipfile
import pymupdf
from PIL import Image,ImageDraw
P=Path(__file__).resolve().parents[1];R=P.parent
report={'checked_at':'2026-09-15','source_unchanged':{},'pdfs':[],'historical_audits':{}}
for n,h in json.loads((P/'evidence/source_hashes.json').read_text('utf-8')).items():
 ok=hashlib.sha256((R/'JMS-version'/n).read_bytes()).hexdigest()==h
 assert ok,n;report['source_unchanged'][n]=ok
for stage,budget in [('main',600),('stability',600),('doe',600),('spbs',600),('sensitivity',600),('ood',1200)]:
 mem=4096 if stage=='ood' else 2048
 d=json.loads((R/f'cie/results/{stage}/cie_{stage}_{budget}s_mem{mem}_repro_v1/submission_analysis/submission_audit.json').read_text('utf-8-sig'))
 assert d['ok'];report['historical_audits'][stage]={k:d[k] for k in ['expected_rows','csv_rows','incumbent_rows','ok']}
for name in ['TASE_Submission_EN','TASE_Review_CN','TASE_Supplement_EN']:
 source=(P/(name+'.tex')).read_text('utf-8')
 d=pymupdf.open(P/(name+'.pdf'))
 log=(P/f'output/.build/{name}/{name}.log').read_text('utf-8',errors='replace')
 problems=[l for l in log.splitlines() if any(v in l for v in ['Overfull','undefined references','undefined on input','Float too large','Missing character'])]
 assert not problems,problems
 t='\n'.join(p.get_text() for p in d)
 for forbidden in ['lshao@','m202420836','Lizhen Shao','Lincong Wei','University of Science and Technology Beijing','D:\\git']:
  assert forbidden not in t,forbidden
 assert not d.metadata.get('author')
 entry={'name':name,'pages':len(d),'compile_problems':problems,'anonymous':True}
 if name=='TASE_Submission_EN':
  abstract=re.search(r'\\begin\{abstract\}(.*?)\\end\{abstract\}',source,re.S)[1]
  ntp=source.split(r'\textit{Note to Practitioners}---')[1].split(r'\par}')[0]
  entry['abstract_words']=len(abstract.split());entry['ntp_words']=len(ntp.split())
  assert 150<=entry['abstract_words']<=200
  assert 100<=entry['ntp_words']<=300
  entry['figure_min_text_pt']={}
  for m in re.finditer(r'\\includegraphics\[width=([^]]+)\]\{([^}]+)\}',source):
   width=m[1];f=m[2];width_pt=252 if width==r'\linewidth' else float(width.replace(r'\textwidth',''))*516
   fd=pymupdf.open(P/'figures'/(f+'.pdf'));pg=fd[0]
   sizes=[span['size']*width_pt/pg.rect.width for b in pg.get_text('dict')['blocks'] if 'lines' in b for l in b['lines'] for span in l['spans'] if len(span['text'].strip())>2]
   entry['figure_min_text_pt'][f]=round(min(sizes),2)
   assert min(sizes)>=7.95,(f,min(sizes))
 report['pdfs'].append(entry)
 qa=P/'output/qa'/name;qa.mkdir(parents=True,exist_ok=True)
 for start in range(0,len(d),6):
  grid=Image.new('RGB',(1200,1120),'#ddd')
  for n in range(start,min(start+6,len(d))):
   pix=d[n].get_pixmap(matrix=pymupdf.Matrix(1,1))
   im=Image.frombytes('RGB',(pix.width,pix.height),pix.samples);im.thumbnail((390,530))
   x=(n-start)%3*400;y=(n-start)//3*560;grid.paste(im,(x+(400-im.width)//2,y+8))
   ImageDraw.Draw(grid).text((x+12,y+542),f'{name} / {n+1}',fill='black')
  grid.save(qa/f'contact-{start//6+1}.jpg',quality=55,optimize=True)
(P/'evidence/verification.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report,indent=2))
out=P/'output/submission';out.mkdir(parents=True,exist_ok=True)
for name in ['TASE_Submission_EN','TASE_Supplement_EN']:
 source=(P/(name+'.tex')).read_text('utf-8')
 figs=re.findall(r'\\includegraphics\[[^]]*\]\{([^}]+)\}',source)
 files=[name+'.tex',name+'.pdf','references.bib','IEEEtran.cls','IEEEtran.bst']+['figures/'+f+'.pdf' for f in dict.fromkeys(figs)]
 with zipfile.ZipFile(out/(name+'_source.zip'),'w',zipfile.ZIP_DEFLATED) as z:
  for f in files:z.write(P/f,f)
 print('Archive:',name,len(files),'files')


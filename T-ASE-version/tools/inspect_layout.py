from pathlib import Path
import re,pymupdf
P=Path('T-ASE-version');s=(P/'TASE_Submission_EN.tex').read_text('utf-8')
d=pymupdf.open(P/'TASE_Submission_EN.pdf')
for i,p in enumerate(d):print(i+1,len(p.get_text()),p.get_text()[:65].replace('\n',' '))
for f in re.findall(r'\\includegraphics\[[^]]*\]\{([^}]+)\}',s):
 p=pymupdf.open(P/'figures'/(f+'.pdf'))[0]
 spans=[z for b in p.get_text('dict')['blocks'] if 'lines' in b for l in b['lines'] for z in l['spans'] if len(z['text'].strip())>2]
 sizes=sorted(set(round(z['size']*252/p.rect.width,2) for z in spans))
 print(f,round(p.rect.width),sizes[:8])


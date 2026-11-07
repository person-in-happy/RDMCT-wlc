from pathlib import Path
from build import compile_one
import json
P=Path(__file__).resolve().parents[1]
reports=[]
for n in ['TASE_Submission_EN','TASE_Review_CN','TASE_Supplement_EN']:
 p=P/(n+'.tex');s=p.read_text('utf-8')
 s=s.replace(r'\begin{document}\n\raggedbottom\n\interdisplaylinepenalty=2500', '\\begin{document}\n\\raggedbottom\n\\interdisplaylinepenalty=2500')
 p.write_text(s,encoding='utf-8')
 reports.append(compile_one(n))
(P/'output/build_report.json').write_text(json.dumps(reports,indent=2),encoding='utf-8')


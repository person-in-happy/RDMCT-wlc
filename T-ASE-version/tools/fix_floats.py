from pathlib import Path
P=Path(__file__).resolve().parents[1]
for name in ['TASE_Submission_EN','TASE_Review_CN','TASE_Supplement_EN']:
 s=(P/(name+'.tex')).read_text('utf-8')
 s=s.replace('\\begin{document}','\\begin{document}\\n\\raggedbottom\\n\\interdisplaylinepenalty=2500')
 s=s.replace('\\usepackage{flafter}','')
 (P/(name+'.tex')).write_text(s,encoding='utf-8')


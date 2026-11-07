from pathlib import Path
import re
from build import compile_one
P=Path(__file__).resolve().parents[1];p=P/'TASE_Submission_EN.tex';s=p.read_text('utf-8')
for block in re.findall(r'\\begin\{figure\*\}.*?\\end\{figure\*\}',s,flags=re.S):
 if 'fig_resource_gantt' in block:s=s.replace(block,block.replace('width=0.94','width=0.825'))
p.write_text(s,encoding='utf-8')
compile_one('TASE_Submission_EN')


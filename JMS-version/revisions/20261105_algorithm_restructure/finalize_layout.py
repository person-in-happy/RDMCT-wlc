from pathlib import Path
import re

paper = Path(__file__).resolve().parents[2]
p = paper/'JMS_Review_CN.tex'
s = p.read_text('utf-8')
start = s.index(r'\section{计算实验与结果分析}')
body = s[start:]
blocks = re.findall(r'\\begin\{(table\*|figure\*)\}.*?\\end\{\1\}',body,re.S)
assert len(blocks)==2
pattern = r'\\begin\{(?:table\*|figure\*)\}.*?\\end\{(?:table\*|figure\*)\}'
floats = re.findall(pattern,body,re.S)
assert len(floats)==2
for f in floats:
    body=body.replace(f+'\n\n','',1)
anchor = r'\label{sec:experiments-cn}'
body = body.replace(anchor,anchor+'\n\n'+'\n\n'.join(floats),1)
p.write_text(s[:start]+body,encoding='utf-8',newline='\n')
print('Moved unchanged experiment floats ahead of section 4 prose for page flow.')

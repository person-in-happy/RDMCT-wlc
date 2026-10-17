"""Add explicitly named strict-4s variants without replacing waiting-allowed figures."""
from pathlib import Path
import json,sys,hashlib
sys.path.insert(0,str(Path(__file__).resolve().parent))
import render_temp_ll_release as r
out=r.OUT
saved=out/'manifest_4s.json'
rows=[x for x in json.loads(saved.read_text('utf-8')) if x['suite'].endswith('pure22')]
assert len(rows)==4
protected={p:hashlib.sha256(p.read_bytes()).hexdigest() for d in [out,out/'en'] for p in d.glob('fig_resource_gantt*') if '_4s.' not in p.name}
audits=[]
for row in rows:
 assert '4 s' in row['constraint']
 tasks,lanes,reset,audit=r.prepare(row)
 for lang in ['cn','en']:r.render(row,tasks,lanes,reset,audit,lang,suffix='_4s')
 audits.append(audit);print(row['suite'],audit['cmax'],flush=True)
assert all(hashlib.sha256(p.read_bytes()).hexdigest()==digest for p,digest in protected.items())
(out/'manifest_4s.json').write_text(json.dumps(rows,indent=2),encoding='utf-8')
(out/'checks_4s.json').write_text(json.dumps(audits,indent=2),encoding='utf-8')
p=out/'README.md';s=p.read_text('utf-8');marker='\n## 独立4s版本\n'
s=s.split(marker)[0]+marker+'\n文件名以 `_nature_4s` 结尾，包含8片/24片、H=3/H=10的纯2×2图，中英文各4张，均无局部放大。4 s约束指同一清洁区段内相邻加工的总间隔；清洁边界不适用。原有允许等待图保持不变。\n\n|批量|H|Cmax / s|\n|---:|---:|---:|\n|8|3|584|\n|8|10|584|\n|24|3|2220|\n|24|10|1336|\n\n来源及检查见 manifest_4s.json、checks_4s.json；重绘命令：`python JMS-version/figures/render_temp_4s.py`。\n'
p.write_text(s,encoding='utf-8')

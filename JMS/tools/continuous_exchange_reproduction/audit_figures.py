from pathlib import Path
import json,re
import pymupdf as fitz
root=Path('JMS-version/figures/temp');rows=json.loads((root/'manifest.json').read_text());audit=[]
for row in rows:
 if 'constraint' not in row:continue
 checks={'suite':row['suite'],'horizon':row['full_action_horizon'],'clean_count':len(row['cleaning_timeline']),'combined':row['bridge_audit']['combined'],'split':row['bridge_audit']['split'],'text_collisions':[]}
 assert checks['split']==0;assert checks['clean_count']==row['metrics']['clean_count']
 for cl in row['cleaning_timeline']:
  assert abs(cl['clean_end']-cl['clean_start']-500)<1e-5;assert cl['unload_end']<=checks['horizon']+1e-5
 n=int(re.search(r'n(\d+)',row['suite'])[1]);h=int(re.search(r'clean(\d+)',row['suite'])[1])
 for lang in ['cn','en']:
  folder=root if lang=='cn' else root/'en';f=folder/f'fig_resource_gantt_cleanH{h}_w{n}_22_{lang}_nature.pdf';doc=fitz.open(f);lines=[]
  for b in doc[0].get_text('dict')['blocks']:
   for line in b.get('lines',[]):
    t=''.join(s['text'] for s in line['spans']).strip()
    if t:lines.append((fitz.Rect(line['bbox']),t))
  for i,(a,t) in enumerate(lines):
   for b,u in lines[i+1:]:
    r=a&b
    if not r.is_empty and r.width>1 and r.height>.25*min(a.height,b.height):checks['text_collisions'].append([lang,t,u])
 assert not checks['text_collisions'],checks
 audit.append(checks)
(root/'continuous4_layout_audit.json').write_text(json.dumps(audit,indent=2));print(json.dumps(audit,indent=2))

from pathlib import Path
import sys,json,shutil
sys.path.insert(0,str(Path('JMS-version/figures').resolve()));import generate_temp_continuous_exchange as b
backup=b.WORK/'before_replacement';backup.mkdir(exist_ok=True)
for folder in [b.OUT,b.OUT/'en']:
 for f in folder.glob('*_22_*'):
  if not (backup/f.name).exists():shutil.copy2(f,backup/f.name)
selected={}
for f in sorted((b.ROOT/'JMS/results/submission_evidence').glob('temp_continuous4_*/*/result.json')):
 r=json.loads(f.read_text('utf8'))
 if r.get('validated'):selected[r['suite']]=r
rows=[]
for row in json.loads((b.WORK/'source_manifest.json').read_text('utf8')):
 if row['suite'] in selected:row=b.render(row,selected[row['suite']]);print(row['suite'],row['metrics']['cmax'],row['full_action_horizon'],flush=True)
 rows.append(row)
(b.OUT/'manifest.json').write_text(json.dumps(rows,indent=2));(b.OUT/'continuous4_checks.json').write_text(json.dumps([r for r in rows if 'constraint' in r],indent=2))

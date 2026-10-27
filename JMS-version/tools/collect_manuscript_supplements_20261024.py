"""Read-only evidence verification; write a separate manuscript review record."""
from pathlib import Path
import hashlib,json,sys,statistics,collections
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'JMS-version/joint_model'))
from validate import validate
from revalidate import metrics
OUT=ROOT/'JMS-version/review/manuscript_supplements_20261024'
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()
def main():
 OUT.mkdir(exist_ok=True);summary={}
 for name in ['supp_fixed_repeat_20261022_6gb_p2','supp_rhythm_20261021_6gb_p2','supp_cleaning_20261021_6gb_p2','supp_gantt16_auto_v1']:
  base=ROOT/'JMS-version/results'/name;p=sorted((base/'audits').glob('audit_*.json'))[-1];audit=read(p)
  assert audit['coverage_complete']
  for row in audit['rows']:
   folder=base/'runs'/row['id']
   for file,h in row['hashes'].items():assert sha(folder/file)==h,(name,row['id'],file)
   result=read(folder/'result.json');manifest=read(folder/'manifest.json')
   validator_hash=next(h for k,h in manifest['assets'].items() if k.replace('\\','/').endswith('joint_model/validate.py'))
   assert sha(ROOT/'JMS-version/joint_model/validate.py')==validator_hash
   assert result['original_model_check'] and validate(result)['valid']
   measured=metrics(result)
   for k,v in row['metrics'].items():assert abs(measured[k]-v)<2e-4 if isinstance(v,(int,float)) else measured[k]==v
  grouped={}
  for case in sorted({r['case'] for r in audit['rows']}):
   grouped[case]={}
   for variant in sorted({r['variant'] for r in audit['rows'] if r['case']==case}):
    rows=[r for r in audit['rows'] if r['case']==case and r['variant']==variant]
    grouped[case][variant]={k:[min(r[k] for r in rows),max(r[k] for r in rows)] for k in ('upper','lower')}
    grouped[case][variant]['metrics']={k:statistics.mean(r['metrics'][k] for r in rows) for k in rows[0]['metrics']}
  item=dict(audit=str(p.relative_to(ROOT)),audit_sha256=sha(p),verified_rows=len(audit['rows']),
    states=dict(collections.Counter(r['status'] for r in audit['rows'])),
    settings=read(base/'supplement.json')['contract']['settings'],groups=grouped,
    comparisons=audit['comparisons'],rhythm_objective_comparisons=audit['rhythm_objective_comparisons'])
  summary[name]=item
 (OUT/'verified_results.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
 for name,v in summary.items():
  print(name,v['verified_rows'],v['states'],v['settings'])
  if 'cleaning' in name:
   print('CLEAN',collections.Counter(round(c['arm_minus_joint_cmax'],4) for c in v['comparisons']),sum(c['strict_benefit_certified'] for c in v['comparisons']))
  else:print(json.dumps(v['groups'],ensure_ascii=False))
  if 'rhythm' in name:print('CONTROLLED',sum(c['controlled_comparison'] for c in v['rhythm_objective_comparisons']))
if __name__=='__main__':main()

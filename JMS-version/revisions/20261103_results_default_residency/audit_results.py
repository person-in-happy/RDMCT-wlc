from pathlib import Path
from collections import Counter,defaultdict
import sys,json,hashlib,copy
ROOT=Path(__file__).resolve().parents[3];HERE=Path(__file__).resolve().parent
BACKEND=ROOT/'JMS-version/model4_pjob_nonprocessing_20261103';sys.path.insert(0,str(BACKEND))
from validate import validate

def read(p):return json.loads(p.read_text('utf-8-sig'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def newconfig(c):
 c=copy.deepcopy(c);c.update(module_residency=100,robot_residency=100,horizon=10000,chamber_residency_basis='nonprocessing');return c

def main():
 candidates={};campaigns=[]
 for pat in ('pjob_nondecreasing_*','nondecreasing_*'):
  for p in sorted((ROOT/'JMS-version/results').glob(pat)):
   if not p.is_dir():continue
   spec=read(p/'campaign.json');contract=read(p/'supplement.json')['contract'] if (p/'supplement.json').exists() else spec
   coverage=read(p/'summary/coverage.json') if (p/'summary/coverage.json').exists() else {'prepared':len(spec['cells']),'completed':0}
   campaigns.append(dict(path=str(p.relative_to(ROOT)),settings=contract.get('settings'),coverage=coverage,manifest_sha256=sha(p/'campaign.json')))
   if not (p/'runs').exists():continue
   for run in (p/'runs').iterdir():
    for f in ('result.json','phase1.json','phase2.json'):
     if (run/f).exists():candidates[run/f]={'category':p.name,'directory':str(run.relative_to(ROOT)),'result':f}
 previous=read(ROOT/'JMS-version/revisions/20261102_followup_results/newrule_validation.json')
 for row in previous['rows']:
  path=ROOT/row['directory']/row['result'];candidates.setdefault(path,dict(category='existing_paper_'+row['category'],directory=row['directory'],result=row['result'],values=row['values']))
 rows=[]
 for idx,(path,meta) in enumerate(candidates.items(),1):
  d=read(path)
  if not d.get('solutions'):continue
  original=validate(d) if d['config'].get('chamber_residency_basis')=='nonprocessing' else None
  current=copy.deepcopy(d);current['config']=newconfig(d['config']);v=validate(current)
  r=dict(**meta,path=str(path.relative_to(ROOT)),sha256=sha(path),parameters={k:d['config'].get(k) for k in ['module_residency','robot_residency','horizon','chamber_residency_basis']},physical_valid_under_current_defaults=v['valid'],errors=v['errors'],checks=v['checks'],cmax=v.get('product_return_cmax'),old_status=d.get('primary_status',d.get('status')),old_lower=d.get('primary_bound',d.get('dual_bound')),old_scope=d.get('model_scope'),restricted_candidates=d.get('restricted_candidate_bounds'),products=sum(j['product'] for j in d['jobs']))
  rows.append(r)
  if idx%100==0:print(f'Audited {idx}/{len(candidates)} saved schedules',flush=True)
 summary={}
 for group in sorted({r['category'] for r in rows}):
  group_rows=[r for r in rows if r['category']==group];summary[group]={'schedules':len(group_rows),'physical_compatible':sum(r['physical_valid_under_current_defaults'] for r in group_rows),'parameter_match':sum(r['parameters']==dict(module_residency=100,robot_residency=100,horizon=10000,chamber_residency_basis='nonprocessing') for r in group_rows)}
 report=dict(target=dict(module_residency=100,robot_residency=100,horizon=10000,chamber_residency_basis='nonprocessing'),campaigns=campaigns,summary=summary,rows=rows,optimization_calls=0,scope='Physical revalidation only; full original-model assignment check and proof transfer are separate gates')
 (HERE/'saved_schedule_audit.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf-8')
 print(json.dumps(summary,ensure_ascii=False,indent=2))
 print('COMPATIBLE SMALL OPTIMA',[(r['path'],r['cmax'],r['old_lower']) for r in rows if r['physical_valid_under_current_defaults'] and r['old_status']=='optimal' and r['products']<=2])
if __name__=='__main__':main()

from pathlib import Path
import json,sys,copy,hashlib
ROOT=Path(__file__).resolve().parents[3];HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'JMS-version/model4_pjob_nonprocessing_20261103'))
from model import Config,Integrated
from validate import validate
from audit_results import newconfig,read,sha

def main():
 report=read(HERE/'saved_schedule_audit.json');dest=HERE/'validated';dest.mkdir(exist_ok=True);rows=[]
 for index,r in enumerate(report['rows']):
  if not r['physical_valid_under_current_defaults']:continue
  path=ROOT/r['path'];folder=path.parent
  name=r.get('values') or ('variables_phase1.json' if path.name=='phase1.json' else 'variables.json')
  vp=folder/name
  if not vp.exists() and (folder/'solve'/name).exists():vp=folder/'solve'/name
  if not vp.exists():raise FileNotFoundError(vp)
  values=read(vp);values=values.get('values',values)
  data=read(path);cfg=Config(**newconfig(data['config']));x=Integrated(cfg);m=x.model;sol=m.createSol();changes={}
  for v in m.getVars(transformed=False):
   value=values.get(v.name)
   if value is None:raise ValueError('Missing original variable '+v.name)
   if (v.name.startswith(('empty_boundary_','exchange_boundary_','rhythm_')) or v.name=='max_wait') and value>cfg.horizon:
    changes[v.name]={'old':value,'new':cfg.horizon};value=cfg.horizon
   m.setSolVal(sol,v,value)
  valid=bool(m.checkSol(sol,printreason=False,completely=True,original=True))
  exported=x.result(solution=sol) if valid else None
  physical=validate(exported) if valid else None
  record=dict(source=r['path'],source_sha256=sha(path),source_variables=str(vp.relative_to(ROOT)),variables_sha256=sha(vp),original_model_check=valid,physical=physical,boundary_witness_clamps=changes,dimensions=x.original_dimensions)
  if valid:
   key=folder.name+'_'+sha(path)[:10];out=dest/key;out.mkdir(exist_ok=True)
   exported['original_model_check']=True;exported['validation']=physical;exported['status']='revalidated_saved_schedule';exported['source_schedule']=r['path'];exported['optimization_performed']=False
   (out/'result.json').write_text(json.dumps(exported,ensure_ascii=False,indent=2),'utf-8')
   vals={v.name:m.getSolVal(sol,v) for v in m.getVars(transformed=False)}
   (out/'variables.json').write_text(json.dumps({'values':vals},indent=2),'utf-8')
   record['validated_result']=str((out/'result.json').relative_to(ROOT));record['validated_variables']=str((out/'variables.json').relative_to(ROOT))
  rows.append(record);m.freeSol(sol);m.freeProb()
  print(f'Checked {folder.name}/{path.name}: full={valid} physical={physical and physical["valid"]}',flush=True)
 (HERE/'assignment_checks.json').write_text(json.dumps({'optimization_calls':0,'rows':rows},ensure_ascii=False,indent=2),'utf-8')
 assert all(r['original_model_check'] and r['physical']['valid'] for r in rows)
if __name__=='__main__':main()

"""Read-only recertification of saved event schedules under clean/dirty VTR hands."""
from pathlib import Path
import argparse,copy,hashlib,json
from grippers import attach_hands
from validate import validate

def audit(root,output):
    root=Path(root);out=Path(output);out.mkdir(parents=True,exist_ok=False);rows=[]
    for path in sorted(root.rglob('result.json')):
        data=json.loads(path.read_text(encoding='utf-8-sig'))
        if data.get('model_scope')!='joint_event_model' or not data.get('solutions'):continue
        old=validate(data)
        revised=copy.deepcopy(data);revised['config']['vtr_hand_policy']='clean_dirty'
        assigned=attach_hands(revised);new=validate(revised) if assigned else {'valid':False,'errors':['No admissible clean/dirty hand assignment for these fixed timestamps']}
        rows.append(dict(path=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest(),original_valid=old['valid'],hand_assignment_exists=assigned,revised_valid=new['valid'],errors=new['errors'][:20],product_cmax=new.get('product_return_cmax'),hand_witness={j['name']:{leg:j.get('vtr_hand_'+leg) for leg in ('in','out')} for j in revised['jobs']}))
    report=dict(scope='Fixed-event physical recertification only; original search performance is not a new-model benchmark',rows=rows,total=len(rows),original_valid=sum(r['original_valid'] for r in rows),revised_valid=sum(r['revised_valid'] for r in rows),hand_incompatible=sum(not r['hand_assignment_exists'] for r in rows))
    (out/'audit.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k!='rows'}))
    return report
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',required=True);p.add_argument('--output',required=True);a=p.parse_args();audit(a.root,a.output)

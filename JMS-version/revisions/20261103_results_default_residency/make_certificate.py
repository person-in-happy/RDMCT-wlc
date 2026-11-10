from pathlib import Path
import json,hashlib,copy,sys
ROOT=Path(__file__).resolve().parents[3];HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'JMS-version/model4_pjob_nonprocessing_20261103'))
from validate import validate
from model import Config,Integrated

def read(p):return json.loads(p.read_text('utf-8-sig'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
audit=read(HERE/'assignment_checks.json')
r=next(r for r in audit['rows'] if 'n2_H3_4x1_dual_same_lp__pjob' in r['source'])
old=read(ROOT/r['source']);newpath=ROOT/r['validated_result'];new=read(newpath)
assert old['status']=='optimal' and old['original_model_check'] and old['restricted_candidate_bounds'] is False
assert abs(old['dual_bound']-old['cmax'])<2e-4 and abs(old['gap'])<1e-8
assert r['original_model_check'] and validate(new)['valid']
assert new['candidate_pairs']==old['candidate_pairs'] and new['candidate_cycles']==old['candidate_cycles']
a=old['config'];b=new['config'];changed={k for k in set(a)|set(b) if a.get(k)!=b.get(k)}
assert changed=={'module_residency','robot_residency','horizon','chamber_residency_basis'}
assert b['module_residency']+max(b['full_time'],2*b['mix_time'],b['cleaning_time'])<=a['module_residency']
assert b['robot_residency']<=a['robot_residency'] and b['horizon']<=a['horizon']
assert abs(new['cmax']-old['dual_bound'])<2e-4
proof=dict(schema=1,kind='optimality_transfer_from_verified_relaxation',original_objective_globally_optimal=True,
 result=r['validated_result'],result_sha256=sha(newpath),variables=r['validated_variables'],variables_sha256=sha(ROOT/r['validated_variables']),
 source_result=r['source'],source_result_sha256=sha(ROOT/r['source']),source_variables=r['source_variables'],source_variables_sha256=r['variables_sha256'],
 old_lower_bound=old['dual_bound'],new_upper_bound=new['cmax'],gap=0.0,optimization_calls=0,
 proof='Every new feasible schedule obeys the old total chamber bound: nonprocessing <=100 plus at most 500 processing <=600<10000; other residence limits and horizon are tighter; all other physical constraints, qualifications and full candidate capacities coincide. The old certified lower bound remains valid, and the new fully checked schedule attains it.',
 changed_parameters={k:{'old':a.get(k),'new':b.get(k)} for k in sorted(changed)},
 target_config=b,model_sha256=sha(ROOT/'JMS-version/model4_pjob_nonprocessing_20261103/model.py'),validator_sha256=sha(ROOT/'JMS-version/model4_pjob_nonprocessing_20261103/physical_validate.py'))
(HERE/'optimality_certificate.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2),'utf-8')
# Boundary/regression checks without running the optimizer.
checks={}
checks['known_schedule_accepted']=validate(new)['valid']
mut=copy.deepcopy(new);mut['config']['module_residency']=11
checks['nonprocessing_excess_rejected']=not validate(mut)['valid']
mut=copy.deepcopy(new);mut['config']['robot_residency']=97
checks['held_auxiliary_hand_excess_rejected']=not validate(mut)['valid']
mut=copy.deepcopy(new);mut['config']['horizon']=324
checks['reset_tail_beyond_horizon_rejected']=not validate(mut)['valid']
mut=copy.deepcopy(new);mut['config']['chamber_residency_basis']='total'
checks['wrong_rule_rejected']=not validate(mut)['valid']
# The two-exposure product and one-exposure support subtraction are independently
# validated on a saved 2x2 schedule which passed the complete new model check.
r2=next(r for r in audit['rows'] if 'n1_H2_2x2_dual__wafer' in r['source'])
d2=read(ROOT/r2['validated_result']);checks['two_exposure_product_single_exposure_support']=validate(d2)['valid'] and r2['original_model_check']
assert all(checks.values()),checks
(HERE/'regression_checks.json').write_text(json.dumps(dict(checks=checks,optimization_calls=0),indent=2),'utf-8')
print(json.dumps(dict(certified_Cmax=new['cmax'],checks=checks),ensure_ascii=False))

"""Solve isolated continuous-4s variants of the four supplementary 2x2 schedules."""
from pathlib import Path
import argparse,datetime,json,hashlib,re,sys
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from scip_imports import scip
from cie.code.analyze_cie_solutions import _parse_solution,_validate,_metrics
from JMS.analyze_mode_cleaning_crossover import _audit_bridge_solution

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--time-limit',type=float,default=180);p.add_argument('--finish-time-limit',type=float,default=60);p.add_argument('--wafer-count',type=int,default=0);a=p.parse_args()
 source=ROOT/'JMS/results/submission_evidence/continuous_exchange_inputs/source_manifest.json'
 out=ROOT/'JMS/results/submission_evidence'/('temp_continuous4_'+datetime.datetime.now().strftime('%Y%m%d_%H%M%S'));out.mkdir(parents=True)
 (ROOT/'JMS/results/submission_evidence/continuous_exchange_inputs/latest_run.txt').write_text(str(out))
 for row in json.loads(source.read_text('utf8')):
  if not row['suite'].endswith('pure22'):continue
  if a.wafer_count and not row['suite'].startswith(f'mode_n{a.wafer_count:03}_'):continue
  d=out/row['suite'];d.mkdir();inst=Path(row['instance']);original=Path(row['source_solution'])
  assert hashlib.sha256(inst.read_bytes()).hexdigest()==row['instance_sha256']
  assert hashlib.sha256(original.read_bytes()).hexdigest()==row['solution_sha256']
  m=scip.Model();m.hideOutput();m.readProblem(str(inst));removed=[]
  for c in list(m.getConss()):
   if c.name=='schedule_stability_def' or c.name.startswith(('schedule_wait_square_def_','chamber_nonprocess_wait_','schedule_wait_def_','resource_idle_')):removed.append(c.name);m.delCons(c)
  v={x.name:x for x in m.getVars()};bridges=[];cons={c.name:c for c in m.getConss()}
  for name in v:
   match=re.fullmatch(r'mix_bridge_start_(\d+)_(\d+)',name)
   if not match:continue
   c,q=map(int,match.groups());s=f'{c}_{q}'
   activation=m.getValsLinear(cons[f'mix_bridge_start_cap_{s}'])
   if f'mix_active_{c}' not in activation:
    assert len(activation)==1 and m.getRhs(cons[f'mix_bridge_start_cap_{s}'])==0
    continue  # No bridge across this cleaning boundary.
   bridges.append((c,q))
   m.addCons(v[f'mix_cycle_start_{s}']-v[f'mix_cycle_end_{c}_{q-1}']==4*v[f'mix_active_{c}'],name=f'continuous4_gap_{s}')
   m.addCons(v[f'mix_bridge_combined_{s}']==v[f'mix_active_{c}'],name=f'continuous4_combined_{s}')
  frozen=d/'continuous4.lp';m.writeProblem(str(frozen));m.setRealParam('numerics/feastol',1e-8);m.setRealParam('limits/time',a.time_limit);m.setRealParam('limits/memory',4096);m.setIntParam('randomization/randomseedshift',1);m.setLogfile(str(d/'solve.log'))
  warm=m.readSolFile(str(original));warm_ok=m.checkSol(warm,printreason=False)
  if warm_ok:m.addSol(warm)
  if not warm_ok and row['suite'].startswith('mode_n024_'):
   from petri_warm_start import _spbs_role_from_var_name
   repair=scip.Model();repair.hideOutput();repair.readProblem(str(frozen));values=_parse_solution(original)
   for x in repair.getVars():
    if x.vtype()=='BINARY' and _spbs_role_from_var_name(x.name) in ('assignment','activation','cleaning_epoch','loadlock_slot','low_risk_resource_order'):
     z=round(values.get(x.name,0));repair.chgVarLb(x,z);repair.chgVarUb(x,z)
   repair.setRealParam('limits/time',60);repair.setRealParam('numerics/feastol',1e-8);repair.setIntParam('limits/solutions',1);repair.optimize()
   print('REPAIR',row['suite'],str(repair.getStatus()),repair.getNSols(),flush=True)
   if repair.getNSols():
    repaired=d/'repaired_initial.sol';repair.writeSol(repair.getBestSol(),str(repaired));candidate=m.readSolFile(str(repaired));assert m.checkSol(candidate,printreason=False);m.addSol(candidate)
   repair.freeProb()
  report={'suite':row['suite'],'source':row,'constraint':'all within-chain adjacent processing gaps = 4 s, combined exchange','bridge_indices':bridges,'instance':str(frozen),'instance_sha256':hashlib.sha256(frozen.read_bytes()).hexdigest(),'warm_accepted':bool(warm_ok),'time_limit':a.time_limit,'finish_time_limit':a.finish_time_limit}
  (d/'started.json').write_text(json.dumps(report,indent=2));print('START',row['suite'],flush=True);m.optimize()
  report['primary']={'status':str(m.getStatus()),'upper_bound':m.getObjVal() if m.getNSols() else None,'lower_bound':m.getDualbound(),'gap':m.getGap(),'time':m.getSolvingTime()}
  if m.getNSols():
   best=d/'primary.sol';m.writeSol(m.getBestSol(),str(best));cap=m.getObjVal();m.freeTransform()
   m.addCons(v['c_max']<=cap+1e-6,name='preserve_product_makespan')
   finish=m.addVar('supplement_full_completion',lb=0)
   endpoints=[x for name,x in v.items() if name.startswith(('prod_stage_end_','pec_stage_end_','clean_front_unload_end_','clean_back_unload_end_'))]
   for k,x in enumerate(endpoints):m.addCons(finish>=x,name=f'supplement_finish_{k}')
   m.setObjective(finish,'minimize');m.setRealParam('limits/time',a.time_limit+a.finish_time_limit);m.optimize()
   report['finish']={'status':str(m.getStatus()),'objective':m.getObjVal() if m.getNSols() else None}
   if m.getNSols():best=d/'best.sol';m.writeSol(m.getBestSol(),str(best))
   m.freeProb();valid,note=_validate(frozen,best);assert valid,note
   values=_parse_solution(best);audit=_audit_bridge_solution(best,tolerance=1e-5);assert audit['split']==0
   gaps=[values.get(f'mix_cycle_start_{c}_{q}',0)-values.get(f'mix_cycle_end_{c}_{q-1}',0) for c,q in bridges if values.get(f'mix_active_{c}',0)>.5];assert all(abs(x-4)<1e-5 for x in gaps)
   report.update(solution=str(best),validated=valid,validation_note=note,bridge_audit=audit,gaps=gaps,metrics=_metrics({},values),solution_sha256=hashlib.sha256(best.read_bytes()).hexdigest())
  else:m.freeProb()
  (d/'result.json').write_text(json.dumps(report,indent=2));print('RESULT',row['suite'],json.dumps(report['primary']),report.get('metrics',{}).get('cmax'),flush=True)
 print('OUTPUT',out,flush=True)
if __name__=='__main__':main()

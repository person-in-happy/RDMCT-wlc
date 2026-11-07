from pathlib import Path
import sys,json,hashlib,re
sys.path.insert(0,str(Path.cwd()));from scip_imports import scip
from cie.code.analyze_cie_solutions import _parse_solution,_validate,_metrics
from JMS.analyze_mode_cleaning_crossover import _audit_bridge_solution
p=Path('JMS/results/submission_evidence/temp_continuous4_20260909_133332/mode_n024_clean10_pure22');r=json.loads((p/'started.json').read_text());v0=_parse_solution(p/'feasibility.sol')
m=scip.Model();m.hideOutput();m.readProblem(str(p/'continuous4.lp'))
for x in m.getVars():
 if x.vtype()=='BINARY':z=round(v0.get(x.name,0));m.chgVarLb(x,z);m.chgVarUb(x,z)
m.setRealParam('numerics/feastol',1e-10);m.setRealParam('limits/time',30);m.optimize();assert m.getNSols();m.writeSol(m.getBestSol(),str(p/'timing_initial.sol'));print('TIMING',m.getObjVal(),flush=True);m.freeProb()
m=scip.Model();m.hideOutput();m.readProblem(str(p/'continuous4.lp'));warm=m.readSolFile(str(p/'timing_initial.sol'));assert m.checkSol(warm,printreason=False);m.addSol(warm);m.setRealParam('numerics/feastol',1e-8);m.setRealParam('limits/time',180);m.setLogfile(str(p/'makespan_retry.log'));m.optimize()
r['primary']={'status':str(m.getStatus()),'upper_bound':m.getObjVal(),'lower_bound':m.getDualbound(),'gap':m.getGap(),'time':m.getSolvingTime(),'warm_start':'feasibility search followed by fixed-order timing optimization'};m.writeSol(m.getBestSol(),str(p/'optimized.sol'));m.freeProb()
# High-precision final timing with the selected binary order; minimize completion of all actions at preserved Cmax.
v0=_parse_solution(p/'optimized.sol');m=scip.Model();m.hideOutput();m.readProblem(str(p/'continuous4.lp'));v={x.name:x for x in m.getVars()}
for x in v.values():
 if x.vtype()=='BINARY':z=round(v0.get(x.name,0));m.chgVarLb(x,z);m.chgVarUb(x,z)
m.addCons(v['c_max']<=r['primary']['upper_bound']+1e-7);finish=m.addVar('supplement_full_completion',lb=0)
for name,x in v.items():
 if name.startswith(('prod_stage_end_','pec_stage_end_','clean_front_unload_end_','clean_back_unload_end_')):m.addCons(finish>=x)
m.setObjective(finish);m.setRealParam('numerics/feastol',1e-10);m.setRealParam('limits/time',30);m.optimize();assert m.getNSols();m.writeSol(m.getBestSol(),str(p/'best.sol'));m.freeProb()
ok,note=_validate(p/'continuous4.lp',p/'best.sol');assert ok,note;values=_parse_solution(p/'best.sol');audit=_audit_bridge_solution(p/'best.sol',tolerance=1e-5);assert audit['split']==0
gaps=[values[f'mix_cycle_start_{c}_{q}']-values[f'mix_cycle_end_{c}_{q-1}'] for c,q in r['bridge_indices']];assert all(abs(t-4)<1e-5 for t in gaps)
r.update(solution=str((p/'best.sol').resolve()),validated=True,validation_note=note,bridge_audit=audit,gaps=gaps,metrics=_metrics({},values),solution_sha256=hashlib.sha256((p/'best.sol').read_bytes()).hexdigest());(p/'result.json').write_text(json.dumps(r,indent=2));print('FINAL',r['primary'],r['metrics']['cmax'],flush=True)

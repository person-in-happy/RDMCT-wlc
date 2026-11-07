from pathlib import Path
import sys,json,re
sys.path.insert(0,str(Path.cwd()));from scip_imports import scip
from cie.code.analyze_cie_solutions import _parse_solution,_validate,_metrics
from JMS.analyze_mode_cleaning_crossover import _audit_bridge_solution
base=Path('JMS/results/submission_evidence/temp_continuous4_20260909_133332')
p=base/'mode_n024_clean03_pure22';r=json.loads((p/'started.json').read_text());old=_parse_solution(p/'best.sol');m=scip.Model();m.hideOutput();m.readProblem(str(p/'continuous4.lp'))
for x in m.getVars():
 if x.vtype()=='BINARY':z=round(old.get(x.name,0));m.chgVarLb(x,z);m.chgVarUb(x,z)
m.setRealParam('numerics/feastol',1e-10);m.setRealParam('limits/time',30);m.optimize();assert m.getNSols();m.writeSol(m.getBestSol(),str(p/'polished.sol'));m.freeProb();ok,note=_validate(p/'continuous4.lp',p/'polished.sol');assert ok,note;v=_parse_solution(p/'polished.sol')
r.update(solution=str((p/'polished.sol').resolve()),validated=True,validation_note=note,metrics=_metrics({},v),bridge_audit=_audit_bridge_solution(p/'polished.sol',tolerance=1e-5))
import hashlib
r['solution_sha256']=hashlib.sha256((p/'polished.sol').read_bytes()).hexdigest();r['primary']={'status':'timelimit','upper_bound':r['metrics']['cmax'],'note':'Validated polished incumbent; not a claim of unrestricted optimality'}
r['gaps']=[v.get(f'mix_cycle_start_{c}_{q}',0)-v.get(f'mix_cycle_end_{c}_{q-1}',0) for c,q in r['bridge_indices']];assert all(abs(t-4)<1e-5 for t in r['gaps']);(p/'result.json').write_text(json.dumps(r,indent=2));print('H3',r['metrics']['cmax'],flush=True)
p=base/'mode_n024_clean10_pure22';m=scip.Model();m.hideOutput();m.readProblem(str(p/'continuous4.lp'));m.setObjective(0);m.setEmphasis(scip.SCIP_PARAMEMPHASIS.FEASIBILITY);m.setRealParam('limits/time',600);m.setRealParam('limits/memory',4096);m.setIntParam('limits/solutions',1);m.setRealParam('numerics/feastol',1e-8);m.setLogfile(str(p/'feasibility.log'));m.optimize();print('H10',str(m.getStatus()),m.getNSols(),flush=True)
if m.getNSols():m.writeSol(m.getBestSol(),str(p/'feasibility.sol'))
(p/'feasibility_status.json').write_text(json.dumps({'status':str(m.getStatus()),'solutions':m.getNSols(),'time':m.getSolvingTime()}))

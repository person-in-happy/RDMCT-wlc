from pathlib import Path
import sys,json
sys.path.insert(0,str(Path.cwd()));from scip_imports import scip
from petri_warm_start import _spbs_role_from_var_name
from cie.code.analyze_cie_solutions import _parse_solution
root=Path('JMS/results/submission_evidence/temp_continuous4_20260909_133332/mode_n024_clean10_pure22');d=json.loads((root/'started.json').read_text());values=_parse_solution(Path(d['source']['source_solution']))
m=scip.Model();m.hideOutput();m.readProblem(str(root/'continuous4.lp'))
for x in m.getVars():
 if x.vtype()=='BINARY' and _spbs_role_from_var_name(x.name) in ('assignment','activation','cleaning_epoch'):
  z=round(values.get(x.name,0));m.chgVarLb(x,z);m.chgVarUb(x,z)
m.setRealParam('limits/time',60);m.setRealParam('numerics/feastol',1e-8);m.setIntParam('limits/solutions',1);m.setLogfile(str(root/'structure_only_repair.log'));m.optimize();print(str(m.getStatus()),m.getNSols(),flush=True)
if m.getNSols():m.writeSol(m.getBestSol(),str(root/'structure_only_initial.sol'))

from pathlib import Path
import sys,json,hashlib,shutil,datetime
root=Path(__file__).resolve().parents[2];sys.path.insert(0,str(root))
from scip_imports import scip
from cie.code.analyze_cie_solutions import _parse_solution,_validate,_metrics
out=root/'JMS/results/submission_evidence'/('h7_transfer_reproduction_'+datetime.datetime.now().strftime('%Y%m%d_%H%M%S'));out.mkdir(exist_ok=False)
inst=root/'JMS/results/submission_evidence/h7_transfer_feasibility_20260910/mode_n024_clean07_pure22_equal_total180_20260831.lp'
frozen=out/inst.name;shutil.copy2(inst,frozen)
rows=json.loads((root/'JMS/results/submission_evidence/continuous_exchange_inputs/source_manifest.json').read_text('utf-8'));source=next(r for r in rows if r['suite']=='mode_n024_clean10_pure22');v=_parse_solution(Path(source['source_solution']))
m=scip.Model();m.hideOutput();m.readProblem(str(frozen))
for c in list(m.getConss()):
 if c.name=='schedule_stability_def' or c.name.startswith(('schedule_wait_square_def_','chamber_nonprocess_wait_','schedule_wait_def_','resource_idle_')):m.delCons(c)
vs={x.name:x for x in m.getVars()};count=0
for name,x in vs.items():
 if name in v and (name.startswith(('prod_start_','prod_end_','mix_cycle_start_','mix_cycle_end_','mix_bridge_start_','mix_bridge_end_','mix_bridge_load_start_','mix_bridge_unload_end_','mix_head_start_','mix_head_end_','mix_tail_start_','mix_tail_end_'))):
  m.addCons(x>=v[name]-1e-6);m.addCons(x<=v[name]+1e-6);count+=1
m.addCons(vs['c_max']<=1237.00001)
for name,x in vs.items():
 if name.startswith('clean_front_load_start_'):m.addCons(x>=1237.00001)
 if name.startswith('clean_front_unload_end_'):m.addCons(x<=2337.00001)
m.setRealParam('numerics/feastol',1e-9);m.setRealParam('limits/time',120);m.setIntParam('limits/solutions',1);m.setLogfile(str(out/'solve.log'));m.optimize()
r={'suite':'mode_n024_clean07_pure22','purpose':'Feasibility transfer only; constrained-solve bound is not a full-model lower bound','source_solution':source['source_solution'],'instance':str(frozen),'instance_sha256':hashlib.sha256(frozen.read_bytes()).hexdigest(),'fixed_timing_variables':count,'status':str(m.getStatus()),'time':m.getSolvingTime()}
if m.getNSols():
 p=out/'best.sol';m.writeSol(m.getBestSol(),str(p));r.update(solution=str(p),cmax=m.getObjVal());m.freeProb();r['validated'],r['validation_note']=_validate(frozen,p);r['metrics']=_metrics({},_parse_solution(p))
(out/'result.json').write_text(json.dumps(r,indent=2),encoding='utf-8');print(json.dumps(r,indent=2))

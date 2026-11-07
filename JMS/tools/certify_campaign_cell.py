"""Certify one frozen campaign cell; leaves all original runs and instances intact."""
from pathlib import Path
import argparse,csv,datetime,hashlib,json,shutil,sys
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--campaign',required=True);p.add_argument('--suite',required=True)
 p.add_argument('--warm-start',default='',help='Validated solution to reuse instead of the original campaign solution')
 p.add_argument('--time-limit',type=float,default=28800);p.add_argument('--prepare-only',action='store_true')
 a=p.parse_args()
 if a.time_limit<=0:p.error('time-limit must be positive')
 if a.warm_start and not Path(a.warm_start).is_file():p.error('warm-start file does not exist')
 campaign=Path(a.campaign).resolve()
 snapshots=sorted((campaign/'runs').glob('cie_benchmark_*.json'))
 rows=[r for f in snapshots for r in json.loads(f.read_text(encoding='utf-8')).get('rows',[]) if r['suite']==a.suite]
 if len(rows)!=1:raise ValueError('Expected exactly one source result for the selected suite')
 row=rows[0];inst=Path(row['path'])
 hashes=list(csv.DictReader((campaign/'instance_sha256.csv').open(encoding='utf-8-sig')))
 expected=next(x['Hash'] for x in hashes if Path(x['Path'])==inst)
 digest=hashlib.sha256(inst.read_bytes()).hexdigest()
 if digest.lower()!=expected.lower():raise ValueError('Frozen instance SHA256 mismatch')
 out=ROOT/'JMS/results/submission_evidence'/('certificate_'+a.suite+'_'+datetime.datetime.now().strftime('%Y%m%d_%H%M%S_%f'))
 out.mkdir(parents=True,exist_ok=False);frozen=out/inst.name;shutil.copy2(inst,frozen)
 report={'suite':a.suite,'instance_sha256':digest,'time_limit':a.time_limit,'prepared_only':a.prepare_only,'purpose':'standalone optimality certificate, not a paired algorithm benchmark','source_result':row}
 if not a.prepare_only:
  from scip_imports import scip
  from cie.code.analyze_cie_solutions import _validate
  m=scip.Model();m.readProblem(str(frozen));removed=[]
  for c in list(m.getConss()):
   if c.name=='schedule_stability_def' or c.name.startswith(('schedule_wait_square_def_','chamber_nonprocess_wait_','schedule_wait_def_','resource_idle_')):removed.append(c.name);m.delCons(c)
  m.setRealParam('limits/time',a.time_limit);m.setRealParam('limits/memory',4096);m.setIntParam('randomization/randomseedshift',1);m.setLogfile(str(out/'solve.log'))
  warm=a.warm_start or row.get('solution_file')
  if warm and Path(warm).is_file():
   ok,note=_validate(frozen,Path(warm))
   if not ok:raise RuntimeError(note)
   dest=out/'initial.sol';shutil.copy2(warm,dest);report['warm_start_sha256']=hashlib.sha256(dest.read_bytes()).hexdigest();report['warm_start_source']=str(Path(warm).resolve());sol=m.readSolFile(str(dest))
   if not m.checkSol(sol):raise RuntimeError('Warm start failed independent check')
   m.addSol(sol)
  m.optimize();report.update(status=str(m.getStatus()),dual_bound=m.getDualbound(),primal_bound=m.getObjVal() if m.getNSols() else None,gap=m.getGap(),solving_time=m.getSolvingTime(),removed_auxiliaries=removed)
  if m.getNSols():
   dest=out/'best.sol';m.writeSol(m.getBestSol(),str(dest));m.freeProb();report['validated'],report['validation_note']=_validate(frozen,dest)
  else:m.freeProb()
 (out/'result.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(out)
if __name__=='__main__':main()

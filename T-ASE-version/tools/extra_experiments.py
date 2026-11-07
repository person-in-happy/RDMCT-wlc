"""Isolated supplementary experiments. Default: print a plan; --execute runs it."""
from pathlib import Path
import argparse,csv,hashlib,json,shutil,subprocess,sys,time,datetime
ROOT=Path(__file__).resolve().parents[2]
PAPER=ROOT/'T-ASE-version'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def checkpoints():
 rows=list(csv.DictReader((ROOT/'cie/results/repro_manifest/selected_checkpoint_manifest.csv').open(encoding='utf-8-sig')))
 for r in rows:
  p=ROOT/r['checkpoint']
  if sha(p).lower()!=r['checkpoint_sha256'].lower():raise RuntimeError('Checkpoint hash mismatch: '+str(p))
 return {(r['family'],int(r['training_seed'])):str(ROOT/r['checkpoint']) for r in rows}
def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('experiment',choices=['sensitivity','spbs-cost'])
 p.add_argument('--execute',action='store_true')
 p.add_argument('--seeds',default='1,2,3,4,5')
 p.add_argument('--max-instances',type=int,default=0)
 p.add_argument('--construction-limit',type=float,default=180)
 p.add_argument('--device',default='cuda:0')
 a=p.parse_args();seeds=[int(v) for v in a.seeds.split(',')]
 if not seeds or len(set(seeds))!=len(seeds):p.error('Use distinct seeds')
 if a.max_instances<0 or a.construction_limit<=0:p.error('Invalid limit')
 stamp=datetime.datetime.now().strftime('%Y%m%d_%H%M%S_%f')
 out=PAPER/'results'/f'{a.experiment}_{stamp}'
 if a.experiment=='sensitivity':
  models=checkpoints();commands=[]
  common=[sys.executable,str(ROOT/'cie/code/run_cie_benchmarks.py'),'--manifest',str(ROOT/'cie/configs/cie_benchmark_suites.json'),'--suites','cie_sensitivity','--splits','test','--seeds',a.seeds,'--time_limit','600','--memory_limit_mb','2048','--warm_start','auto','--stability_profile','full','--device',a.device,'--acs_weights','0.25,0,0.5,0.25','--fail_on_empty_suite']
  if a.max_instances:common+=['--max_instances_per_suite',str(a.max_instances)]
  commands.append(common+['--methods','scip_default,adaptive_cutsel','--output_dir',str(out/'runs/baselines'),'--solution_dir',str(out/'solutions/baselines')])
  for seed in range(1,6):
   commands.append(common+['--methods','hem,proposed','--training_seed',str(seed),'--hem_model',models[('hem',seed)],'--proposed_model',models[('proposed',seed)],'--output_dir',str(out/f'runs/trainseed_{seed}'),'--solution_dir',str(out/f'solutions/trainseed_{seed}')])
  print(json.dumps({'output':str(out),'runs':min(a.max_instances or 8,8)*len(seeds)*12,'commands':commands},indent=2))
  if not a.execute:return
  out.mkdir(parents=True,exist_ok=False)
  (out/'plan.json').write_text(json.dumps(commands,indent=2),encoding='utf-8')
  for i,cmd in enumerate(commands):
   with (out/f'job_{i}.log').open('w',encoding='utf-8') as log:subprocess.run(cmd,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,check=True)
  for name,extra in [('analyze_cie_solutions.py',['--validate','--fail_on_invalid']),('analyze_cie_submission.py',['--stage','sensitivity','--no_plots'])]:
   subprocess.run([sys.executable,str(ROOT/'cie/code'/name),'--input_dir',str(out/'runs'),'--output_dir',str(out/'analysis')]+extra,cwd=ROOT,check=True)
 elif a.experiment=='spbs-cost':
  files=sorted((ROOT/'cie/data/core/spbs').glob('*.lp'))
  if a.max_instances:files=files[:a.max_instances]
  if not files:raise RuntimeError('No frozen core instances')
  print(json.dumps({'output':str(out),'instances':len(files),'seeds':seeds,'construction_limit_per_attempt_s':a.construction_limit,'jobs':len(files)*len(seeds),'purpose':'Measure fresh SPBS construction plus independent validation; not a solver benchmark or a hard end-to-end deadline.'},indent=2))
  if not a.execute:return
  sys.path.insert(0,str(ROOT))
  from petri_mip_generator import PetriMIPConfig
  from petri_warm_start import write_mixed_warm_start
  from cie.code.analyze_cie_solutions import _validate
  out.mkdir(parents=True,exist_ok=False)
  records=[]
  for source in files:
   cfg=PetriMIPConfig(**json.loads(source.with_suffix('.cie.json').read_text('utf-8-sig'))['config'])
   for seed in seeds:
    case=out/'cases'/source.stem/f'seed_{seed}';case.mkdir(parents=True,exist_ok=False)
    frozen=case/source.name;shutil.copy2(source,frozen);original_hash=sha(source)
    start=time.perf_counter()
    solution=write_mixed_warm_start(str(case),source.name,cfg,time_limit=a.construction_limit,memory_limit_mb=2048,random_seed=seed)
    constructed=time.perf_counter()
    valid,note=_validate(frozen,Path(solution)) if solution else (False,'No incumbent within construction budget')
    elapsed=time.perf_counter()-start
    r={'source_instance':str(source),'sha256':original_hash,'seed':seed,'construction_wall_s':constructed-start,'construction_plus_validation_wall_s':elapsed,'has_solution':bool(solution),'valid':bool(valid),'validation_note':note,'solution':solution}
    if sha(frozen)!=original_hash or sha(source)!=original_hash:raise RuntimeError('Input changed')
    records.append(r);(out/'records.json').write_text(json.dumps(records,indent=2),encoding='utf-8')
    print(json.dumps(r),flush=True)
    if solution and not valid:raise RuntimeError('Generated start does not validate against frozen model; stop and inspect compatibility.')
  with (out/'records.csv').open('w',newline='',encoding='utf-8') as f:
   w=csv.DictWriter(f,fieldnames=list(records[0]));w.writeheader();w.writerows(records)
if __name__=='__main__':main()


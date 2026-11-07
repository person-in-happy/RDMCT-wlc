"""Isolated foreground campaigns for R=100 s nonprocessing chamber residence and B=10000 s.
Preparation never optimizes. Full candidates and nondecreasing Pjob pickup are retained.
"""
from pathlib import Path
from dataclasses import asdict
from datetime import datetime,timezone
import argparse,json,sys,time,subprocess,hashlib,shutil,os
import psutil
from model import Config,ROOT
from revalidate import plan
from evidence_supplement import matrix as original_matrix
from run_experiments import solve,assets,policy_record,dump,digest
from run_matched_supplement import output_lock
HERE=Path(__file__).resolve().parent
AUDIT=ROOT/'JMS-version/revisions/20261103_results_default_residency'
SUITES=('small','gantt','paper','paper_cuts','crossover','scale32')
def read(p):return json.loads(Path(p).read_text('utf-8-sig'))
def canonical(d):return json.dumps(d,sort_keys=True,separators=(',',':'))
def frozen_assets():return assets()|{str(Path(__file__).relative_to(ROOT)):digest(Path(__file__))}
def matrix(suite):
 if suite=='small':
  old=read(ROOT/'JMS-version/results/nondecreasing_followup_exact_20261102_205212/campaign.json')
  cases={c['case']:c['config'] for c in old['cells'] if c['kind']=='exact' and c['arm']=='pjob'}
 elif suite=='gantt':
  allcases,_=plan('crossover');cases={k:v for k,v in allcases.items() if k in {f'n16_H{h}_{m}_dual' for h in (3,10) for m in ('4x1','2x2')}}
 else:
  cases,_=original_matrix('paper' if suite=='paper_cuts' else suite)
  if suite in ('paper','paper_cuts'):cases={k:v for k,v in cases.items() if k.startswith(('n4_','n8_')) and '_mixed_' in k}
 for c in cases.values():c.update(module_residency=100,robot_residency=100,horizon=10000,chamber_residency_basis='nonprocessing',max_pairs=0,max_cycles=0)
 return cases

def ensure_idle():
 names={'paper_defaults.py','evidence_supplement.py','experiment_console.py','review_experiments.py','strengthen.py','followup.py','revalidate.py','run_experiments.py'}
 for p in psutil.process_iter(['pid','name','cmdline']):
  if p.pid==os.getpid() or 'python' not in (p.info['name'] or '').lower():continue
  cmd=p.info['cmdline'] or []
  if any(Path(t).name in names for t in cmd) and any(t in ('run','resume','start','worker','_worker','solve','preflight') for t in cmd):raise RuntimeError(f'Other experiment queue/worker active: PID {p.pid}')

def prepare(a):
 out=Path(a.campaign).resolve();base=ROOT/'JMS-version/results'
 if not out.is_relative_to(base) or out==base:raise ValueError('Use a new isolated JMS-version/results subdirectory')
 if out.exists():raise FileExistsError('Existing campaign retained; use resume or a new name')
 cases=matrix(a.suite);seeds=a.seeds or ([1] if a.suite in ('small','gantt') else [1,2,3])
 methods=['scip','hem','proposed'] if a.suite=='paper_cuts' else ['scip']
 settings=dict(time_limit=a.time_limit,stage2_limit=a.stage2_limit,memory_mb=a.memory_mb,process_memory_mb=a.process_memory_mb,wall_limit=a.wall_limit,reserve_mb=2048,jobs=1,threads=1,cut_profile='root_only' if a.suite=='paper_cuts' else 'standard')
 if not 0<a.memory_mb<a.process_memory_mb:raise ValueError('Require 0 < SCIP memory < process RSS ceiling')
 if a.wall_limit<=a.time_limit+a.stage2_limit:raise ValueError('Wall limit must leave time for building and verification')
 out.mkdir(parents=True);(out/'configs').mkdir();(out/'warm').mkdir();cells=[];warm_by_config={}
 # Previously revalidated assignments are common feasible starts, never fixed structures.
 for r in read(AUDIT/'paper_witnesses.json'):
  d=read(ROOT/r['result']);key=canonical(d['config'])
  if key not in warm_by_config or d['cmax']<warm_by_config[key][0]:warm_by_config[key]=(d['cmax'],ROOT/r['variables'])
 configs={};warms={}
 for key,c in cases.items():
  c=asdict(Config(**c));dump(out/'configs'/f'{key}.json',c);configs[key]=digest(out/'configs'/f'{key}.json')
  if canonical(c) in warm_by_config:
   source=warm_by_config[canonical(c)][1];target=out/'warm'/f'{key}.json';shutil.copy2(source,target);warms[key]=dict(path=str(target.relative_to(out)),sha256=digest(target),source=str(source),source_sha256=digest(source))
  for seed in seeds:
   for method in methods:cells.append(dict(id=f'{key}__s{seed}__{method}',case=key,seed=seed,method=method))
 spec=dict(schema=1,suite=a.suite,created_utc=datetime.now(timezone.utc).isoformat(),model='pjob_nondecreasing_nonprocessing_v1',settings=settings,assets=frozen_assets(),configs=configs,warms=warms,cells=cells,policies={m:policy_record(m,1) for m in methods},scope='Fresh current-default comparison. Revalidated starts, where available, shared byte-identically across methods/seeds; otherwise cold. No historical performance pooling; no SPBS or fixed-skeleton arms.')
 dump(out/'campaign.json',spec);dump(out/'contract.json',{'campaign_sha256':digest(out/'campaign.json')})
 print(json.dumps({'prepared':str(out),'cells':len(cells),'settings':settings,'solves_started':0},ensure_ascii=False),flush=True)

def checked(out):
 s=read(out/'campaign.json')
 if digest(out/'campaign.json')!=read(out/'contract.json')['campaign_sha256'] or frozen_assets()!=s['assets']:raise RuntimeError('Frozen input/code changed; create a new campaign')
 for k,v in s['configs'].items():
  if digest(out/'configs'/f'{k}.json')!=v:raise RuntimeError('Config hash changed: '+k)
 for w in s['warms'].values():
  if digest(out/w['path'])!=w['sha256']:raise RuntimeError('Common start changed')
 for m,p in s['policies'].items():
  if policy_record(m,1)!=p:raise RuntimeError('Frozen policy changed')
 return s

def status(out,verify=True):
 s=checked(out) if verify else read(out/'campaign.json');complete=failed=optimal=0
 for c in s['cells']:
  p=out/'runs'/c['id']
  if (p/'result.json').exists():
   d=read(p/'result.json');complete+=1
   optimal+=int(d.get('primary_status')=='optimal' and d.get('full_candidate_space') is True and d.get('result_eligible') is True)
  elif (p/'failure.json').exists():failed+=1
 return dict(expected=len(s['cells']),complete=complete,failed=failed,pending=len(s['cells'])-complete-failed,certified_primary_optima=optimal)

def run(a):
 out=Path(a.campaign).resolve();ensure_idle()
 with output_lock(out):
  s=checked(out);st=s['settings'];required=st['process_memory_mb']+st['reserve_mb'];available=psutil.virtual_memory().available/1024**2
  if available<required:raise RuntimeError(f'Need {required:.0f} MiB available RAM; currently {available:.0f}. Preserve this campaign and resume after freeing RAM.')
  started=time.monotonic();executed=0
  for c in s['cells']:
   folder=out/'runs'/c['id']
   if (folder/'result.json').exists():continue
   if folder.exists():raise RuntimeError('Incomplete attempt retained at '+str(folder)+'; diagnose before creating an isolated retry')
   log=out/(c['id']+'.log');print('START '+c['id'],flush=True)
   with log.open('wb') as f:
    proc=subprocess.Popen([sys.executable,'-X','utf8','-u',str(Path(__file__)),'worker','--campaign',str(out),'--cell',c['id']],stdout=f,stderr=subprocess.STDOUT)
    stamp=time.monotonic();last=0;failure=None
    try:
     while proc.poll() is None:
      elapsed=time.monotonic()-stamp
      try:
       pp=psutil.Process(proc.pid);rss=sum(p.memory_info().rss for p in [pp]+pp.children(recursive=True) if p.is_running())/1024**2
      except psutil.Error:rss=0
      if rss>st['process_memory_mb']:failure='process_memory_guard'
      if elapsed>st['wall_limit']:failure='wall_limit'
      if failure:proc.terminate();proc.wait();break
      if elapsed-last>=10:
       counts=status(out,verify=False);remaining=counts['expected']-counts['complete']
       eta=((time.monotonic()-started)/executed*remaining if executed else st['wall_limit']*remaining)/3600
       print(f'complete={counts["complete"]} failed={counts["failed"]} running=1 | elapsed={elapsed:.0f}s RSS={rss:.0f}MiB ETA~{eta:.2f}h | {c["id"]}',flush=True);last=elapsed
      time.sleep(1)
    except KeyboardInterrupt:
     proc.terminate();proc.wait();failure='foreground_interrupted';raise
    finally:
     if failure:
      folder.mkdir(parents=True,exist_ok=True);dump(folder/'failure.json',dict(reason=failure,returncode=proc.returncode))
   if proc.returncode!=0:
    folder.mkdir(parents=True,exist_ok=True)
    if not (folder/'failure.json').exists():dump(folder/'failure.json',dict(reason='worker_exit',returncode=proc.returncode))
    raise RuntimeError('Worker stopped; saved log '+str(log))
   executed+=1;print('DONE '+c['id']+' '+json.dumps(status(out)),flush=True)
  dump(out/'finished.json',status(out));print(json.dumps(status(out)),flush=True)

def worker(a):
 out=Path(a.campaign).resolve();s=checked(out);c=next(c for c in s['cells'] if c['id']==a.cell);st=s['settings'];w=s['warms'].get(c['case'])
 solve(out/'configs'/f'{c["case"]}.json',out/'runs'/c['id'],time_limit=st['time_limit'],stage2_limit=st['stage2_limit'],seed=c['seed'],memory_mb=st['memory_mb'],method=c['method'],training_seed=1,initialization='none',initialization_budget=0,warm_start=out/w['path'] if w else None,cut_profile=st['cut_profile'])

def main():
 p=argparse.ArgumentParser(__doc__);p.add_argument('action',choices=['prepare','run','resume','status','worker','inspect']);p.add_argument('--campaign');p.add_argument('--suite',choices=SUITES,default='small');p.add_argument('--cell');p.add_argument('--seeds',type=int,nargs='+');p.add_argument('--time-limit',type=float,default=600);p.add_argument('--stage2-limit',type=float,default=60);p.add_argument('--memory-mb',type=int,default=6000);p.add_argument('--process-memory-mb',type=int,default=8000);p.add_argument('--wall-limit',type=float,default=1800);a=p.parse_args()
 if a.action=='inspect':
  for suite in SUITES:
   cs=matrix(suite);assert all((v['module_residency'],v['robot_residency'],v['horizon'])==(100,100,10000) for v in cs.values());print(suite,len(cs),'cases')
  return
 if not a.campaign:p.error('--campaign is required')
 if a.action=='prepare':prepare(a)
 elif a.action in ('run','resume'):run(a)
 elif a.action=='worker':worker(a)
 else:print(json.dumps(status(Path(a.campaign).resolve())))
if __name__=='__main__':main()

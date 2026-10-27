"""Isolated heterogeneous-duration experiment; full-model evidence only.

Prepare is cheap. Run/Resume refuse to compete with existing research jobs.
Resume preserves attempts and reuses a checked incumbent, never a SCIP tree.
"""
from pathlib import Path
from dataclasses import asdict
from datetime import datetime,timezone
import argparse,gzip,hashlib,json,math,os,platform,shutil,subprocess,sys,time,traceback
import psutil,pyscipopt
from model import Config,Integrated
from seed import construct,constrain_seed
from validate import validate
from joint_pairing_model import products_from_load_ports

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]

def digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):h.update(block)
    return h.hexdigest()
def read(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))
def dump(path,data):
    path=Path(path);tmp=path.with_suffix(path.suffix+'.tmp')
    tmp.write_text(json.dumps(data,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8');tmp.replace(path)
def finite(data):
    if isinstance(data,float) and not math.isfinite(data):return None
    if isinstance(data,dict):return {k:finite(v) for k,v in data.items()}
    if isinstance(data,(list,tuple)):return [finite(v) for v in data]
    return data
def now():return datetime.now(timezone.utc).isoformat()
def inventory():return {p.name:digest(p) for p in sorted(HERE.glob('*.py'))}

def configuration():
    # 50 wafers per mode, round-robin LP allocation, 25 wafers per LP.
    ports={f'LP{i}':{'4x1':0,'2x2':0} for i in range(1,5)}
    for i in range(100):ports[f'LP{i%4+1}']['4x1' if i<50 else '2x2']+=1
    cfg=Config(ports,source='dual',cleaning_interval=3)
    products=products_from_load_ports(ports)
    groups={f'G{i+1}':{'wafers':[],'4x1':d,'2x2':d} for i,d in enumerate((80,180,90))}
    for mode,counts in [('4x1',(17,17,16)),('2x2',(17,16,17))]:
        # Spread each time group across all load ports; keep physical IDs fixed.
        queues={lp:[w.identifier for w in products if w.load_port==lp and w.mode==mode] for lp in range(1,5)}
        wafers=[]
        while any(queues.values()):
            for lp in range(1,5):
                if queues[lp]:wafers.append(queues[lp].pop(0))
        offset=0
        for group,count in zip(groups,counts):groups[group]['wafers']=groups[group]['wafers']+wafers[offset:offset+count];offset+=count
    cfg.processing_groups=groups
    return cfg

def other_jobs():
    ancestors={p.pid for p in psutil.Process().parents()}|{os.getpid()}
    found=[]
    for p in psutil.process_iter(['pid','name','cmdline']):
        if p.pid in ancestors:continue
        try:
            if 'python' not in (p.info['name'] or '').lower():continue
            cmd=p.info['cmdline'] or []
            # Conservatively protect every other Python process running a repo script.
            scripts=[Path(v) for v in cmd if v.lower().endswith('.py')]
            for script in scripts:
                full=script if script.is_absolute() else Path(p.cwd())/script
                if full.resolve().is_relative_to(ROOT):
                    found.append({'pid':p.pid,'script':str(full)});break
        except (psutil.NoSuchProcess,psutil.AccessDenied):continue
    return found

def prepare(out):
    out.mkdir(parents=True,exist_ok=False)
    cfg=configuration();dump(out/'config.json',asdict(cfg))
    products=products_from_load_ports(cfg.load_ports)
    initial=construct(cfg)
    initial.update(experiment_scope='heterogeneous_constructed_witness',full_candidate_space=False,
                   global_optimality_claim=False,original_model_check=False)
    dump(out/'initial_schedule.json',initial)
    manifest=dict(schema=1,created_utc=now(),config_sha256=digest(out/'config.json'),
        seed_sha256=digest(out/'initial_schedule.json'),code=inventory(),
        interpreter=sys.executable,python=sys.version,pyscipopt=pyscipopt.__version__,platform=platform.platform(),
        objective='last product returned to original load port; terminal cleaning still required',
        durations='seconds per exposure; 2x2 products receive two exposures',
        group_counts=[len(g['wafers']) for g in cfg.processing_groups.values()],
        mode_counts={mode:sum(w.mode==mode for w in products) for mode in ('4x1','2x2')},
        shared_cycle_rule='All product wafers in a productive chamber cycle have the same group',
        cleaning_interval=cfg.cleaning_interval,source=cfg.source,seed=1,threads=1,
        state='prepared; exact solve pending',optimality_claim=False)
    frozen=out/'frozen_code';frozen.mkdir()
    for name in manifest['code']:shutil.copy2(HERE/name,frozen/name)
    shutil.copy2(HERE/'base_sources.json',frozen/'base_sources.json')
    productive=sum(1 if w.mode=='4x1' else 2 for w in products)
    pairs=len(products)+3*productive;cycles=2*productive
    dump(out/'size_preflight.json',dict(products=len(products),safe_pairs=pairs,cycles_per_chamber=cycles,
        pair_cycle_occupancy_variables=pairs*cycles*len(cfg.chambers),
        dummy_loan_pair_comparisons=cfg.dummy_count*(2*pairs)*(2*pairs-1)//2,
        warning='Counts are structural only, not a RAM feasibility certificate. No arbitrary candidate truncation is allowed.'))
    dump(out/'manifest.json',manifest)
    print(json.dumps(dict(prepared=str(out),products=len(products),feasible_constructed_cmax=initial['cmax'],
                         physical_valid=initial['validation']['valid'],optimal=False)),flush=True)

def verify(out):
    manifest=read(out/'manifest.json')
    if manifest['code']!=inventory():raise ValueError('Frozen extension changed; create a new experiment directory')
    if manifest['config_sha256']!=digest(out/'config.json') or manifest['seed_sha256']!=digest(out/'initial_schedule.json'):
        raise ValueError('Frozen configuration or initial schedule changed')
    if manifest['interpreter']!=sys.executable or manifest['pyscipopt']!=pyscipopt.__version__ or manifest['python']!=sys.version:
        raise ValueError('Frozen Python/solver environment changed')
    if not validate(read(out/'initial_schedule.json'))['valid']:raise ValueError('Initial schedule failed physical replay')
    return manifest

def checkpoint(x,attempt):
    m=x.model
    if not m.getNSols():return None
    sol=m.getBestSol();result=x.result(sol)
    result['validation']=validate(result)
    result['original_model_check']=bool(m.checkSol(sol,printreason=False,completely=True,original=True))
    result['global_optimality_claim']=False
    if not result['validation']['valid'] or not result['original_model_check']:
        dump(attempt/'rejected.json',finite(result));raise ValueError('Incumbent failed original-model or physical replay')
    values={v.name:m.getSolVal(sol,v) for v in m.getVars(transformed=False)}
    # Each accepted incumbent gets immutable files; pointer is committed last.
    token=str(time.time_ns());rp=attempt/f'checkpoint_{token}.json';vp=attempt/f'variables_{token}.json'
    dump(rp,finite(result));dump(vp,dict(values=values))
    dump(attempt/'latest.json',dict(result=rp.name,variables=vp.name,result_sha256=digest(rp),variables_sha256=digest(vp)))
    return result

def worker(out,attempt,memory_mb,seconds,previous):
    verify(out);cfg=Config(**read(out/'config.json'))
    if cfg.max_pairs or cfg.max_cycles:raise ValueError('Arbitrary candidate truncation forbidden for this experiment')
    print('BUILD full heterogeneous model; proof ETA unknown',flush=True)
    x=Integrated(cfg);m=x.model;m.hideOutput(False)
    m.setIntParam('parallel/maxnthreads',1);m.setIntParam('lp/threads',1);m.setIntParam('randomization/randomseedshift',1)
    m.setRealParam('limits/memory',memory_mb);m.setLogfile(str(attempt/'solver.log'))
    dump(attempt/'build.json',dict(dimensions=x.original_dimensions,safe_bounds=x.safe_bounds))
    m.writeProblem(str(attempt/'model.lp'),verbose=False)
    with (attempt/'model.lp').open('rb') as raw,gzip.open(attempt/'model.lp.gz','wb',compresslevel=1) as compressed:
        shutil.copyfileobj(raw,compressed)
    (attempt/'model.lp').unlink()
    dump(attempt/'model_hash.json',dict(lp_sha256=digest(attempt/'model.lp.gz')))
    if previous:
        pointer=read(previous/'latest.json');vp=previous/pointer['variables'];rp=previous/pointer['result']
        if digest(vp)!=pointer['variables_sha256'] or digest(rp)!=pointer['result_sha256']:raise ValueError('Checkpoint hash changed')
        record=read(rp)
        if record['config']!=asdict(cfg) and json.dumps(record['config'],sort_keys=True)!=json.dumps(asdict(cfg),sort_keys=True):
            raise ValueError('Checkpoint has a different model configuration')
        if not validate(record)['valid']:raise ValueError('Checkpoint failed physical replay')
        values=read(vp)['values'];sol=m.createSol()
        if set(values)!={v.name for v in m.getVars(transformed=False)}:raise ValueError('Checkpoint variable set differs')
        for v in m.getVars(transformed=False):m.setSolVal(sol,v,values[v.name])
        if not m.checkSol(sol,printreason=False,completely=True,original=True):raise ValueError('Checkpoint failed original model')
        m.addSol(sol)
    else:
        fixed=constrain_seed(x,read(out/'initial_schedule.json'))
        m.setObjective(0,'minimize');m.setRealParam('limits/time',120);m.optimize()
        if not m.getNSols():raise RuntimeError('Full-model initial completion failed')
        values={v.name:m.getSolVal(m.getBestSol(),v) for v in m.getVars(transformed=False)}
        m.freeTransform()
        for v,lb,ub in fixed:m.chgVarLb(v,lb);m.chgVarUb(v,ub)
        m.setObjective(x.cmax,'minimize')
        sol=m.createSol()
        for v in m.getVars(transformed=False):m.setSolVal(sol,v,values[v.name])
        if not m.checkSol(sol,printreason=False,completely=True,original=True):raise ValueError('Released initial witness failed')
        m.addSol(sol)
    # Only the complete model is solved; no fixed chamber, pairing or order remains.
    checkpoint(x,attempt)
    class SaveBest(pyscipopt.Eventhdlr):
        def eventinit(self):self.model.catchEvent(pyscipopt.SCIP_EVENTTYPE.BESTSOLFOUND,self)
        def eventexit(self):self.model.dropEvent(pyscipopt.SCIP_EVENTTYPE.BESTSOLFOUND,self)
        def eventexec(self,event):
            checkpoint(x,attempt)
    m.includeEventhdlr(SaveBest(),'save_heterogeneous_best','checked incumbent checkpoints')
    m.setRealParam('limits/time',seconds if seconds else 1e20)
    m.optimize();checkpoint(x,attempt)
    result=x.result();result['validation']=validate(result)
    result['original_model_check']=bool(m.getNSols() and m.checkSol(m.getBestSol(),printreason=False,completely=True,original=True))
    result['full_candidate_space']=not x.bounded
    result['global_optimality_claim']=bool(result['status']=='optimal' and result['full_candidate_space'] and
        result['original_model_check'] and result['validation']['valid'] and result.get('gap',1)<=1e-6 and
        abs(result['cmax']-result['dual_bound'])<=2e-4)
    dump(attempt/'result.json',finite(result))
    dump(attempt/'finished.json',dict(status=result['status'],optimal=result['global_optimality_claim'],
         physical_valid=result['validation']['valid'],original_model_check=result['original_model_check'],
         result_sha256=digest(attempt/'result.json'),ended_utc=now()))
    m.freeProb()

def run(out,memory_mb,seconds,resume):
    verify(out)
    active=other_jobs()
    if active:raise RuntimeError('Existing research jobs are active; no new solver started: '+json.dumps(active))
    required=memory_mb*1024**2+2*1024**3
    if psutil.virtual_memory().available<required:raise RuntimeError('Insufficient available RAM for declared limit plus 2 GiB reserve')
    attempts=sorted(out.glob('attempt_*'))
    if attempts and not resume:raise ValueError('Use resume to preserve existing attempts')
    for attempt in reversed(attempts):
        if (attempt/'finished.json').exists() and read(attempt/'finished.json').get('optimal'):
            final=read(attempt/'finished.json')
            if digest(attempt/'result.json')!=final['result_sha256'] or not validate(read(attempt/'result.json'))['valid']:
                raise ValueError('Completed optimal result failed integrity/physical replay')
            print('Verified optimal result already complete; skipped');return
    previous=next((p for p in reversed(attempts) if (p/'latest.json').exists()),None)
    if attempts:
        last=read(attempts[-1]/'attempt.json')
        if last['memory_mb']!=memory_mb or last['time_limit']!=seconds:raise ValueError('Resume resource settings must match previous attempt')
        if last.get('outcome') not in ('interrupted','time_limit','userinterrupt'):
            raise ValueError('Previous attempt needs review; do not silently retry resource/execution failures')
    attempt=out/f'attempt_{len(attempts)+1:03d}';attempt.mkdir()
    record=dict(started_utc=now(),memory_mb=memory_mb,time_limit=seconds,threads=1,
                previous=str(previous) if previous else None,resume_scope='checked incumbent only; fresh search tree',outcome='running')
    dump(attempt/'attempt.json',record)
    args=[sys.executable,'-X','utf8','-u',str(Path(__file__).resolve()),'_worker','--output',str(out),
          '--attempt',str(attempt),'--memory-mb',str(memory_mb),'--seconds',str(seconds)]
    if previous:args+=['--previous',str(previous)]
    env=os.environ.copy();env.update(OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',MKL_NUM_THREADS='1')
    child=subprocess.Popen(args,cwd=ROOT,env=env)
    begun=time.monotonic();outcome=None
    try:
        while child.poll() is None:
            try:
                proc=psutil.Process(child.pid)
                rss=sum(p.memory_info().rss for p in [proc]+proc.children(recursive=True) if p.is_running())
            except psutil.NoSuchProcess:break
            elapsed=time.monotonic()-begun
            print(f'PROGRESS completed=0 failed=0 running=1 elapsed={elapsed:.0f}s RSS={rss/1024**2:.0f}MiB proof_ETA=unknown',flush=True)
            if rss>memory_mb*1024**2 or psutil.virtual_memory().available<2*1024**3:
                outcome='resource_limit';child.terminate();break
            own={child.pid}|{p.pid for p in proc.children(recursive=True)}
            if any(p['pid'] not in own for p in other_jobs()):
                outcome='interrupted';child.terminate();break
            time.sleep(10)
    except KeyboardInterrupt:
        outcome='interrupted'
        if child.poll() is None:child.terminate()
    finally:
        child.wait();record['exit_code']=child.returncode;record['ended_utc']=now()
        if outcome is None:
            finished=read(attempt/'finished.json') if (attempt/'finished.json').exists() else {}
            outcome='complete' if finished.get('optimal') else 'time_limit' if finished.get('status')=='timelimit' else finished.get('status','execution_failed')
        record['outcome']=outcome;dump(attempt/'attempt.json',record)
    print(json.dumps(record),flush=True)
    if outcome!='complete':raise RuntimeError('Optimality not established; saved attempt retained: '+outcome)

def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('action',choices=['prepare','run','resume','status','_worker'])
    p.add_argument('--output',required=True);p.add_argument('--memory-mb',type=int,default=6000)
    p.add_argument('--seconds',type=float,default=0,help='0 means no main solve time limit; exact proof ETA unknown')
    p.add_argument('--attempt');p.add_argument('--previous')
    a=p.parse_args();out=Path(a.output).resolve()
    if a.memory_mb<=0 or not math.isfinite(a.seconds) or a.seconds<0:p.error('Invalid resource budget')
    if a.action=='prepare':prepare(out)
    elif a.action in ('run','resume'):run(out,a.memory_mb,a.seconds,a.action=='resume')
    elif a.action=='_worker':worker(out,Path(a.attempt),a.memory_mb,a.seconds,Path(a.previous) if a.previous else None)
    else:
        verify(out);print(json.dumps(dict(manifest=read(out/'manifest.json'),attempts=[read(p) for p in sorted(out.glob('attempt_*/attempt.json'))]),ensure_ascii=False,indent=2))

if __name__=='__main__':
    try:main()
    except Exception:
        traceback.print_exc();sys.exit(1)

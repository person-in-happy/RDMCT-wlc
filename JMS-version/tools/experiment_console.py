"""Visible progress and resource-aware parallel scheduling for future campaigns.

watch is read-only and works with the existing serial supervisor.
run can explicitly adopt a stopped serial campaign after checking for live workers.
"""
from pathlib import Path
from datetime import datetime,timezone,timedelta
import argparse,json,os,shutil,statistics,subprocess,sys,time

ROOT=Path(__file__).resolve().parents[2]
JOINT=ROOT/'JMS-version/joint_model'
CHINA=timezone(timedelta(hours=8))

def read(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))

def snapshot(spec,progress,now=None):
    now=now or datetime.now(timezone.utc);done=failed=0;running=[];history={};all_times=[]
    for c in spec['cells']:
        s=progress.get('cells',{}).get(c['id'],{})
        if s.get('ended_utc'):
            duration=(datetime.fromisoformat(s['ended_utc'])-datetime.fromisoformat(s['started_utc'])).total_seconds()
            all_times.append(duration);history.setdefault((c['case'],c['variant']),[]).append(duration)
            if s['state']=='complete':done+=1
            else:failed+=1
        elif s.get('state')=='running':running.append(c['id'])
    seconds=0
    for c in spec['cells']:
        s=progress.get('cells',{}).get(c['id'],{})
        if s.get('ended_utc'):continue
        typical=statistics.median(history.get((c['case'],c['variant']),all_times)) if all_times else spec['time_limit']+15
        elapsed=(now-datetime.fromisoformat(s['started_utc'])).total_seconds() if s.get('started_utc') else 0
        seconds+=max(0,typical-elapsed)
    return dict(done=done,failed=failed,total=len(spec['cells']),running=running,remaining=len(spec['cells'])-done-failed,serial_seconds=seconds)

def display(out,jobs=1,extra=''):
    spec=read(out/'campaign.json');p=read(out/'progress.json') if (out/'progress.json').exists() else {'cells':{}}
    s=snapshot(spec,p);now=datetime.now(CHINA);eta=s['serial_seconds']/max(1,jobs)
    print(f"[{now:%H:%M:%S}] {s['done']+s['failed']}/{s['total']} finished | complete={s['done']} failed={s['failed']} running={len(s['running'])} | ETA ~{eta/3600:.2f} h ({now+timedelta(seconds=eta):%H:%M}) {extra}",flush=True)
    if s['running']:print('  '+', '.join(s['running']),flush=True)
    return s

def watch(args):
    out=Path(args.campaign).resolve()
    print('Read-only monitor. Ctrl+C closes this monitor; experiments continue.',flush=True)
    while True:
        scheduler=read(out/'console_scheduler.json') if (out/'console_scheduler.json').exists() else {}
        s=display(out,scheduler.get('jobs',1))
        if args.once or not s['remaining']:return
        if (out/'stopped.json').exists():print('Supervisor reported a stop; inspect stopped.json.',flush=True)
        time.sleep(args.refresh)

def can_start(cell,active,free_mb,memory_mb,reserve_mb,gpu_slots):
    if any(v['cell']['case']==cell['case'] for v in active.values()):return False
    if cell['learned'] and sum(v['cell']['learned'] for v in active.values())>=gpu_slots:return False
    # Reserve possible growth to each active job's process memory guard.
    growth=sum(max(0,memory_mb*1.15-v.get('rss_mb',0)) for v in active.values())
    return free_mb-growth-reserve_mb>=memory_mb*1.15

def ensure_idle(out):
    """A parent lock alone does not exclude orphan workers from the old runner."""
    import psutil
    for proc in psutil.process_iter(['pid','name','cmdline']):
        if proc.pid==os.getpid():continue
        try:
            info=proc.info
            if 'python' not in (info['name'] or '').lower():continue
            cmd=info['cmdline']
            if cmd is None:raise RuntimeError(f'Cannot inspect Python process {proc.pid}; refusing adoption')
            if not any(Path(arg).name in ('revalidate.py','experiment_console.py') for arg in cmd):continue
            if '--campaign' not in cmd:continue
            target=Path(cmd[cmd.index('--campaign')+1])
            if not target.is_absolute():target=Path(proc.cwd())/target
            if target.resolve()==out and 'watch' not in cmd:
                raise RuntimeError(f'Campaign still has a live process (PID {proc.pid}); wait for it to exit')
        except (psutil.NoSuchProcess,psutil.ZombieProcess):continue
        except psutil.AccessDenied as exc:
            raise RuntimeError(f'Cannot inspect process {proc.pid}; refusing adoption') from exc

def adopt_stopped(out,spec,dump):
    ensure_idle(out)
    if not (out/'stopped.json').exists():
        raise RuntimeError('Adoption requires stopped.json from the failed serial supervisor')
    p=read(out/'progress.json');retained=[]
    for cell in spec['cells']:
        evidence=out/'runs'/cell['id']/'evidence.json'
        if evidence.exists():
            record=read(evidence)
            if not record.get('complete'):raise RuntimeError(f'Incomplete evidence: {evidence}')
            entry=p['cells'].setdefault(cell['id'],{})
            entry.update(state='complete',ended_utc=record['completed_utc'],exit_code=None,
                         completion_source='orphan_worker_evidence')
            entry.setdefault('started_utc',record['completed_utc'])
            retained.append(cell['id'])
        elif p['cells'].get(cell['id'],{}).get('state')=='running':
            p['cells'][cell['id']]['state']='pending'
    archive=out/'scheduler_transitions'/str(time.time_ns());archive.mkdir(parents=True)
    for name in ('progress.json','stopped.json'):
        shutil.copy2(out/name,archive/name)
    dump(archive/'transition.json',dict(at_utc=datetime.now(timezone.utc).isoformat(),
        from_mode='serial_supervisor',to_mode='visible_foreground_parallel',retained_cells=retained,
        note='Retained observations used the previous execution protocol; do not silently pool timing benchmarks.'))
    dump(out/'progress.json',p)
    # Archive the stale stop marker so watch does not report a running campaign stopped.
    (out/'stopped.json').unlink()
    print(f'Adopted stopped campaign; retained {len(retained)} completed observations. Audit: {archive}',flush=True)

def run(args):
    import psutil
    sys.path.insert(0,str(JOINT))
    from revalidate import verify,VARIANTS,summarize
    from run_experiments import dump,digest
    from run_matched_supplement import output_lock
    out=Path(args.campaign).resolve();scheduler=out/'console_scheduler.json'
    # Do not silently change the execution protocol of the active serial run.
    adopting=(out/'progress.json').exists() and not scheduler.exists()
    if adopting and not getattr(args,'adopt_stopped',False):
        raise RuntimeError('Existing serial campaign: use watch, or --adopt-stopped after its workers have exited.')
    with output_lock(out):
        spec=verify(out)
        if adopting:adopt_stopped(out,spec,dump)
        contract=dict(script_sha256=digest(Path(__file__)),campaign_sha256=digest(out/'campaign.json'),
            jobs=args.jobs,gpu_slots=args.gpu_slots,reserve_mb=args.reserve_mb,
            threads_per_worker=1,python=sys.executable,mode='visible_foreground_parallel')
        if scheduler.exists() and read(scheduler)!=contract:raise RuntimeError('Scheduler settings changed; use a new campaign')
        dump(scheduler,contract)
        p=read(out/'progress.json') if (out/'progress.json').exists() else {'cells':{}}
        stamp=lambda:datetime.now(timezone.utc).isoformat()
        active={};queue=[];started=0;completed=0;clock0=time.monotonic()
        for cell in spec['cells']:
            dest=out/'runs'/cell['id']
            if (dest/'evidence.json').exists():continue
            if (dest/'failure.json').exists() and not args.retry_failed:continue
            queue.append(cell|dict(learned=VARIANTS[cell['variant']]['method']!='scip'))
        last_display=0
        print('Foreground parallel scheduler. Ctrl+C stops its workers and preserves outputs.',flush=True)
        print(f"slots={args.jobs}, GPU slots={args.gpu_slots}, per-worker SCIP memory={spec['memory_mb']} MB, RAM reserve={args.reserve_mb} MB",flush=True)
        try:
            while queue or active:
                verify(out)
                for cid,a in list(active.items()):
                    proc=a['process'];reason=None
                    try:a['rss_mb']=psutil.Process(proc.pid).memory_info().rss/1024**2
                    except psutil.NoSuchProcess:a['rss_mb']=0
                    if proc.poll() is None:
                        if a['rss_mb']>spec['memory_mb']*1.15:reason='process_memory_guard'
                        if time.monotonic()-a['start']>spec['wall_limit']:reason='cell_wall_guard'
                        if reason:proc.terminate();proc.wait(timeout=30)
                    code=proc.poll()
                    if code is None:continue
                    a['log'].close();dest=out/'runs'/cid;success=code==0 and (dest/'evidence.json').exists()
                    if not success:
                        dest.mkdir(parents=True,exist_ok=True);dump(dest/'failure.json',dict(reason=reason or f'exit_{code}',ended_utc=stamp()))
                    p['cells'][cid].update(state='complete' if success else 'execution_failed',exit_code=code,ended_utc=stamp())
                    dump(out/'progress.json',p);del active[cid];completed+=1
                    print(('DONE ' if success else 'FAIL ')+cid,flush=True);summarize(out)
                for cell in list(queue):
                    if len(active)>=args.jobs:break
                    free_mb=psutil.virtual_memory().available/1024**2
                    if not can_start(cell,active,free_mb,spec['memory_mb'],args.reserve_mb,args.gpu_slots):continue
                    cid=cell['id'];dest=out/'runs'/cid
                    if dest.exists():
                        resolved=dest.resolve();archive=out/'interrupted_attempts'/(cid+'_'+str(time.time_ns()))
                        if dest.is_symlink() or not resolved.is_relative_to(out) or not archive.resolve().is_relative_to(out):raise RuntimeError('Unsafe archive path')
                        archive.parent.mkdir(exist_ok=True);dest.rename(archive)
                    logs=out/'logs';logs.mkdir(exist_ok=True);log=(logs/(cid+'_'+str(time.time_ns())+'.log')).open('wb')
                    env=os.environ.copy();env.update(OMP_NUM_THREADS='1',MKL_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1')
                    proc=subprocess.Popen([sys.executable,str(JOINT/'revalidate.py'),'worker','--campaign',str(out),'--cell',cid],cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT)
                    active[cid]=dict(process=proc,cell=cell,log=log,start=time.monotonic(),rss_mb=0)
                    p['cells'][cid]=dict(state='running',started_utc=stamp(),pid=proc.pid);dump(out/'progress.json',p)
                    queue.remove(cell);started+=1;print('START '+cid,flush=True)
                if queue and not active:
                    required=spec['memory_mb']*1.15+args.reserve_mb
                    if required>psutil.virtual_memory().total/1024**2:raise RuntimeError('One worker cannot fit memory reservation; prepare a new campaign with a suitable memory limit')
                if time.monotonic()-last_display>=args.refresh:
                    effective=completed*statistics.median([spec['time_limit']+15])/(time.monotonic()-clock0) if completed else max(1,len(active))
                    display(out,max(1,min(args.jobs,effective)),extra=f"queued={len(queue)} RAM_available={psutil.virtual_memory().available/1024**3:.1f}GB")
                    last_display=time.monotonic()
                time.sleep(1)
            report=summarize(out);dump(out/'finished.json',report|dict(ended_utc=stamp(),all_cells_successful='execution_failed' not in report['states'] and 'pending' not in report['states']))
        except BaseException:
            for cid,a in active.items():
                if a['process'].poll() is None:a['process'].terminate();a['process'].wait(timeout=30)
                a['log'].close();dest=out/'runs'/cid;dest.mkdir(parents=True,exist_ok=True)
                dump(dest/'failure.json',dict(reason='foreground_interrupted',ended_utc=stamp()))
                p['cells'][cid].update(state='execution_failed',ended_utc=stamp())
            dump(out/'progress.json',p)
            raise

def main():
    parser=argparse.ArgumentParser(__doc__);sub=parser.add_subparsers(dest='command',required=True)
    for name in ('watch','run'):
        p=sub.add_parser(name);p.add_argument('--campaign',required=True);p.add_argument('--refresh',type=float,default=15)
        if name=='watch':p.add_argument('--once',action='store_true')
        else:
            p.add_argument('--jobs',type=int,default=2);p.add_argument('--gpu-slots',type=int,default=1);p.add_argument('--reserve-mb',type=float,default=4096);p.add_argument('--retry-failed',action='store_true')
            p.add_argument('--adopt-stopped',action='store_true',help='Explicitly adopt a stopped serial campaign; refuse live workers and archive prior supervisor state')
    a=parser.parse_args()
    if a.refresh<=0 or (a.command=='run' and (a.jobs<1 or a.gpu_slots<1 or a.reserve_mb<0)):parser.error('Invalid resource/refresh setting')
    try:watch(a) if a.command=='watch' else run(a)
    except KeyboardInterrupt:print('\nConsole stopped.',flush=True)

if __name__=='__main__':main()

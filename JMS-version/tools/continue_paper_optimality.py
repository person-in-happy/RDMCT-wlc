"""Visible foreground queue for the four n16 global-optimality searches.

No main time limit. Existing interrupted attempts stay immutable. A queue exit
never certifies optimality by itself; final original-model certificates remain
required. Logs and live bounds are displayed even during long root LP solves.
"""
from pathlib import Path
from datetime import datetime,timezone
import argparse,json,os,subprocess,sys,time
import psutil

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'JMS-version/joint_model'))
from run_experiments import dump,digest,assets
from run_matched_supplement import output_lock
from optimality_runtime import certificate_asset_changes,reserve_for_growth

BASE=ROOT/'JMS-version/results/optimality_work_20261021'
CASES={
    'n16_H3_4x1':('manuscript_warm_n16_H3_4x1','original_certificate_n16_H3_4x1'),
    'n16_H10_2x2':('manuscript_warm_n16_H10_2x2_v2','original_certificate_n16_H10_2x2_14gb'),
    'n16_H10_4x1':('manuscript_warm_n16_H10_4x1_transfer','original_certificate_n16_H10_4x1'),
    'n16_H3_2x2':('manuscript_warm_n16_H3_2x2_v2','original_certificate_n16_H3_2x2_14gb'),
}


def read(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def now():return datetime.now(timezone.utc).isoformat()


def process_targets(out):
    found=[]
    for p in psutil.process_iter(['pid','cmdline','name']):
        if p.pid==os.getpid():continue
        try:
            cmd=p.info['cmdline'] or []
            if not any(Path(a).name=='solve_incumbent_sublevel.py' for a in cmd):continue
            if '--output' not in cmd:continue
            path=Path(cmd[cmd.index('--output')+1])
            if not path.is_absolute():path=Path(p.cwd())/path
            if path.resolve().is_relative_to(out):found.append(p.pid)
        except psutil.NoSuchProcess:continue
        except psutil.AccessDenied:raise RuntimeError('Cannot verify worker ownership; retry from the owning account')
    return found


def external_growth(own):
    growth=0
    for p in psutil.process_iter(['pid','cmdline','memory_info']):
        if p.pid in own:continue
        try:
            cmd=p.info['cmdline'] or []
            if 'worker' not in cmd or '--campaign' not in cmd:continue
            path=Path(cmd[cmd.index('--campaign')+1])
            if not path.is_absolute():path=Path(p.cwd())/path
            spec=read(path/'campaign.json')
            budget=spec.get('memory_mb',6000)
            growth+=max(0,float(budget)*1.15-p.info['memory_info'].rss/1048576)
        except psutil.NoSuchProcess:continue
        except (psutil.AccessDenied,OSError,ValueError,KeyError,TypeError):
            growth+=6900
    return growth


def log_line(folder):
    p=folder/'solver.log'
    if not p.exists():return 'building model'
    with p.open('rb') as f:
        f.seek(max(0,p.stat().st_size-8192))
        lines=f.read().decode('utf-8',errors='replace').splitlines()
    rows=[s.strip() for s in lines if '|' in s and 'unknown' in s]
    return rows[-1] if rows else (lines[-1].strip() if lines else 'starting')


def main():
    p=argparse.ArgumentParser(__doc__)
    p.add_argument('--output',required=True)
    p.add_argument('--jobs',type=int,default=2)
    p.add_argument('--memory-mb',type=float,default=6000)
    p.add_argument('--refresh',type=float,default=15)
    p.add_argument('--check-only',action='store_true')
    p.add_argument('--resume-interrupted',action='store_true')
    a=p.parse_args()
    if a.jobs<1 or a.memory_mb<=0 or a.refresh<1:p.error('Invalid resource/progress setting')
    out=Path(a.output).resolve()
    if not out.is_relative_to(ROOT/'JMS-version/results'):p.error('Use an isolated results directory')
    inputs={}
    for case,(warm,certdir) in CASES.items():
        source=BASE/warm/'result.json';certpath=BASE/certdir/'certificate.json';cert=read(certpath)
        if not cert.get('accepted') or not cert.get('full_candidate_space') or cert['source_sha256']!=digest(source):
            raise ValueError('Uncertified starting schedule: '+case)
        changes=certificate_asset_changes(cert['assets'],assets())
        inputs[case]=dict(source=str(source),certificate=str(certpath),source_sha256=digest(source),
                          certificate_sha256=digest(certpath),reporting_helper_changes=changes)
    live=process_targets(out)
    if live:raise RuntimeError('Queue has live workers: '+str(live))
    if a.check_only:
        print(json.dumps(dict(inputs_checked=4,live_workers=live,external_growth_mb=external_growth(set()),
              memory_mb=a.memory_mb,jobs=a.jobs,main_time_limit=None),indent=2));return
    out.mkdir(parents=True,exist_ok=True)
    with output_lock(out):
        statepath=out/'queue.json'
        if statepath.exists():
            state=read(statepath)
            if state['inputs']!=inputs:raise ValueError('Frozen queue inputs changed')
            if not a.resume_interrupted:raise ValueError('Existing queue: inspect it and use --resume-interrupted only after its workers exit')
            if state['jobs']!=a.jobs or state['memory_mb']!=a.memory_mb:raise ValueError('Keep resumed queue resource settings matched')
            for c in state['cases'].values():
                if c['state']=='running':c['state']='interrupted'
        else:
            state=dict(created_utc=now(),inputs=inputs,jobs=a.jobs,memory_mb=a.memory_mb,
                       main_time_limit=None,cases={c:dict(state='pending',attempts=[]) for c in CASES})
        state.update(supervisor_pid=os.getpid(),started_utc=now(),state='running')
        dump(statepath,state)
        active={};last=0
        print('FOREGROUND EXACT SEARCH | 4 cases | no main time limit | Ctrl+C stops this queue\n'
              'ETA unknown: completion requires closed global bounds. Never label this queue complete from elapsed time.',flush=True)
        try:
            while True:
                for case,item in list(active.items()):
                    code=item['process'].poll()
                    if code is None:continue
                    item['stream'].close();folder=item['folder'];c=state['cases'][case]
                    result=read(folder/'finished.json') if (folder/'finished.json').exists() else {}
                    ok=code==0 and result.get('sublevel_optimal') and result.get('physical_valid') and result.get('sublevel_model_check')
                    c.update(state='sublevel_optimal_pending_original_verification' if ok else 'needs_review',
                             exit_code=code,ended_utc=now(),finished=result)
                    del active[case];dump(statepath,state)
                pending=[c for c,s in state['cases'].items() if s['state'] in ('pending','interrupted')]
                if pending and len(active)<a.jobs:
                    free=psutil.virtual_memory().available/1048576
                    rss=[psutil.Process(v['process'].pid).memory_info().rss/1048576 for v in active.values()]
                    ext=external_growth({v['process'].pid for v in active.values()})
                    if reserve_for_growth(rss,free,a.memory_mb,2048,ext):
                        case=pending[0];c=state['cases'][case];attempt=len(c['attempts'])+1
                        folder=out/(case+f'_attempt{attempt:02d}')
                        # Worker creates its output; stdout is a separate durable queue artifact.
                        stream=(out/(case+f'_attempt{attempt:02d}.console.log')).open('wb')
                        cmd=[sys.executable,'-u','-X','utf8',str(Path(__file__).with_name('solve_incumbent_sublevel.py')),
                             '--source',inputs[case]['source'],'--certificate',inputs[case]['certificate'],
                             '--output',str(folder),'--memory-mb',str(a.memory_mb)]
                        proc=subprocess.Popen(cmd,cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT)
                        c['attempts'].append(dict(folder=str(folder),command=cmd,started_utc=now(),pid=proc.pid))
                        c.update(state='running',pid=proc.pid)
                        active[case]=dict(process=proc,stream=stream,folder=folder)
                        dump(statepath,state);print('START '+case+' PID='+str(proc.pid),flush=True)
                if time.monotonic()-last>=a.refresh:
                    last=time.monotonic();states=[v['state'] for v in state['cases'].values()]
                    done=states.count('sublevel_optimal_pending_original_verification')
                    print(f'[{now()}] sublevel_optimal={done}/4 | paper_certified=0/4 | running={len(active)} | '
                          f'needs_review={states.count("needs_review")} | pending={states.count("pending")+states.count("interrupted")} | ETA unknown',flush=True)
                    for case,item in active.items():print('  '+case+' '+log_line(item['folder']),flush=True)
                    if not active and pending:print('  Waiting for RAM reserved for other running experiments.',flush=True)
                if not active and not any(s['state'] in ('pending','interrupted') for s in state['cases'].values()):break
                time.sleep(min(a.refresh,3))
        except BaseException as exc:
            state['state']='interrupted' if isinstance(exc,KeyboardInterrupt) else 'supervisor_error'
            state['error']=str(exc)
            print('Stopping this queue only; preserving completed results and checkpoints.',flush=True)
            for case,item in active.items():
                item['process'].terminate()
                try:item['process'].wait(timeout=10)
                except subprocess.TimeoutExpired:item['process'].kill();item['process'].wait()
                item['stream'].close();state['cases'][case].update(state='interrupted',ended_utc=now())
            dump(statepath,state)
            if isinstance(exc,KeyboardInterrupt):return
            raise
        state.update(state='searches_ended_pending_certification',ended_utc=now());dump(statepath,state)
        print('Search queue ended. Final original-model verification and the complete proof chain are still required.',flush=True)


if __name__=='__main__':main()

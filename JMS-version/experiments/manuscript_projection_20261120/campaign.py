"""Foreground scheduler. Restart the same command to resume completed cells and global bounds."""
import json
import msvcrt
import os
from pathlib import Path
import subprocess
import sys
import time
from collections import Counter
from datetime import datetime,timezone
import psutil
from protocol import HERE,JMS,ROOT,OUT,PYTHON_SCIP,matrix,read,save,sha

GIB=1024**3
def stamp():
    return datetime.now(timezone.utc).isoformat()


def footprint(t):
    if t['n']==16:
        return 6.5 if t['case'].startswith('E_') else 3.5
    if t['kind']=='scip' or (t['kind']=='selected' and t['engine']=='scip'):
        return 1.45
    return .90 if t['n']==4 else .55


def priority(t):
    tag=t['id'].split('__',1)[1]
    if tag.startswith('grid_'): return 0
    if t.get('figure'): return 1
    if t['n']==16 and tag=='budget_A_s1': return 1
    if t['kind']=='selected': return 2
    if t['kind']=='prep': return 3
    if t['n']==16: return 4
    if tag.startswith(('budget_B','rhythm','budget_A','joint_rho')): return 5
    if tag.startswith('structure'): return 6
    if t['kind']=='cp': return 7
    return 8


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    with (OUT/'supervisor.lock').open('a+b') as lock:
        lock.seek(0)
        try: msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
        except OSError: raise SystemExit('A supervisor already owns this campaign')
        if not (OUT/'protocol.json').exists():
            print('Registering manuscript tables, paired starts, solver seeds and budgets',flush=True)
            spec=matrix()
            save(OUT/'protocol.json',spec)
            save(OUT/'contract.json',dict(sha256=sha(OUT/'protocol.json'),created=stamp()))
        spec=read(OUT/'protocol.json')
        if read(OUT/'contract.json')['sha256']!=sha(OUT/'protocol.json'): raise ValueError('Changed experiment contract')
        tasks=spec['tasks']
        completed={k for k in tasks if (OUT/'runs'/k/'evidence.json').is_file()}
        # A resumed supervisor adopts any still-running worker for this directory.
        live={}
        for p in psutil.process_iter(['cmdline']):
            cmd=p.info['cmdline'] or []
            if str(HERE/'cell.py') in cmd and cmd[-1] in tasks:
                live[cmd[-1]]=(p,None,time.monotonic(),True)
        failed={}
        halted=set()
        first=time.monotonic()
        start_complete=len(completed)
        last_log=0.
        spec_tasks=sorted(tasks.values(),key=priority)
        try:
            while len(completed)+len(failed)+len(halted)<len(tasks) or live:
                for key,(proc,log,when,adopted) in list(live.items()):
                    code=(None if proc.is_running() else 0) if adopted else proc.poll()
                    if code is None:continue
                    if log is not None: log.close()
                    del live[key]
                    if code==0 and (OUT/'runs'/key/'evidence.json').is_file():
                        completed.add(key)
                    else: failed[key]=dict(exit_code=code,failed_at=stamp())
                for t in spec_tasks:
                    key=t['id']
                    if key in completed or key in failed or key in halted or key in live: continue
                    if set(t['deps']) & (failed.keys() | halted):
                        halted.add(key)
                        continue
                    if len(live)>=spec['concurrent_processes'] or not set(t['deps'])<=completed: continue
                    if t['n']==16 and sum(tasks[k]['n']==16 for k in live)>=spec['max_16_wafer_processes']: continue
                    # Reserve for existing active jobs and for workers still loading their models.
                    pending=0.
                    for k,(p,_,birth,adopted) in live.items():
                        try:
                            rss=psutil.Process(p.pid).memory_info().rss/GIB
                        except psutil.Error: rss=0.
                        pending+=max(0.,footprint(tasks[k])-rss)
                    if psutil.virtual_memory().available/GIB-pending-footprint(t)<3.0: continue
                    folder=OUT/'runs'/key
                    folder.mkdir(parents=True,exist_ok=True)
                    filename=folder/f'attempt_{time.time_ns()}.log'
                    log=filename.open('w',encoding='utf-8')
                    native=t['kind']=='scip' or (t['kind']=='selected' and t['engine']=='scip')
                    python=PYTHON_SCIP if native else sys.executable
                    args=[str(python),'-B','-X','utf8','-u',str(HERE/'cell.py'),key]
                    proc=subprocess.Popen(args,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
                    live[key]=(proc,log,time.monotonic(),False)
                now=time.monotonic()
                if now-last_log>8 or not live:
                    done_now=len(completed)-start_complete
                    eta=(now-first)*(len(tasks)-len(completed)-len(failed)-len(halted))/done_now if done_now else None
                    progress=dict(updated=stamp(),pid=os.getpid(),expected=len(tasks),completed=len(completed),
                                  failed=failed,dependent_pending=sorted(halted),active={k:p.pid for k,(p,*_) in live.items()},
                                  eta_s_observed_rate=eta,available_gib=round(psutil.virtual_memory().available/GIB,2),
                                  scale75_complete=(OUT/'scale75/evidence.json').is_file())
                    save(OUT/'progress.json',progress)
                    estimate='estimating' if eta is None else f'~{eta/60:.0f} min at observed rate'
                    print(f"{len(completed)}/{len(tasks)} done | {len(failed)} failed | {len(halted)} waiting on failed inputs | "
                          f"{len(live)} active | {progress['available_gib']} GiB free | ETA {estimate}",flush=True)
                    if live: print('  '+', '.join(live),flush=True)
                    last_log=now
                if not live and len(completed)+len(failed)+len(halted)>=len(tasks):break
                time.sleep(1.5)
        except KeyboardInterrupt:
            for proc,_,_,adopted in live.values():
                if not adopted and proc.poll() is None: proc.terminate()
            raise
        final=dict(expected=len(tasks),completed=len(completed),failed=failed,dependent_pending=sorted(halted),
                   archived=stamp(),scale75=(OUT/'scale75/evidence.json').is_file())
        save(OUT/'completion.json',final)
        print(json.dumps({k:(len(v) if k in ('failed','dependent_pending') else v) for k,v in final.items()}),flush=True)
        return int(bool(failed or halted))


if __name__=='__main__': sys.exit(main())

"""Foreground controller for the nine Table 4 reruns, resumed at native endpoint boundaries."""
import argparse
import msvcrt
import os
import subprocess
import sys
import time

import psutil
from publish import HERE,JMS,OUT,prepare,publish,read,sha,write

SOLVER=HERE.parent/'square_residence_20261125/solver.py'
TAG='mean_plus_spread_squared_over_2delta_plus_gamma_E_v1'


def run():
    jobs=prepare();name={j['key']:j for j in jobs}
    lock=(OUT/'controller.lock').open('a+b')
    try:msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
    except OSError:
        print('Another visible controller owns this queue.',flush=True)
        return
    statepath=OUT/'queue.json'
    key={'jobs':sha(OUT/'jobs.json'),'solver':sha(SOLVER),'score':sha(SOLVER.with_name('score.py'))}
    state=read(statepath) if statepath.exists() else dict(signature=key,workers={},success=[],failed=[],elapsed_s=0)
    assert key==state['signature'],'Input or solver changed after campaign start.'
    if state['success'] and len(state['success'])==len(jobs):
        publish();return
    state['failed']=[]
    children={}
    for j in jobs:
        ident=j['key'];target=OUT/'runs'/ident
        if (target/'result.json').is_file():
            r=read(target/'result.json')
            assert r['objective']==TAG and r['eligible'] and r['seed']==j['seed'] and r['parents'][0]['schedule_sha256']==j['origin_schedule_sha256']
            if ident not in state['success']:state['success'].append(ident)
            state['workers'].pop(ident,None)
        elif ident in state['workers']:
            w=state['workers'][ident]
            try:
                p=psutil.Process(w['pid']);args=' '.join(p.cmdline())
                assert str(SOLVER) in args and str(target) in args and abs(p.create_time()-w['birth'])<1
                children[ident]=p
            except (psutil.Error,AssertionError):
                state['workers'].pop(ident)
    wall_start=time.monotonic();carry=state['elapsed_s']
    def completed(ident):
        out=OUT/'runs'/ident/'result.json';j=name[ident]
        if out.exists():
            r=read(out);return r['objective']==TAG and r['eligible'] and r['seed']==j['seed'] and r['parents'][0]['schedule_sha256']==j['origin_schedule_sha256']
        return False
    def elapsed():
        return carry+time.monotonic()-wall_start
    def report():
        pending=[j for j in jobs if j['key'] not in state['success']]
        per={}
        for n in (8,16):
            measured=[read(OUT/'runs'/k/'result.json')['record']['wall_seconds'] for k in state['success'] if name[k]['n']==n]
            per[n]=sum(measured)/len(measured) if measured else (15 if n==8 else 40)
        remaining=sum(max(0.5,per[j['n']]-(time.time()-state['workers'][j['key']]['start_wall'] if j['key'] in state['workers'] else 0)) for j in pending)
        active16=sum(j['n']==16 for j in pending)
        eta=max(per[16]*max(0,active16-len(children)),remaining/2) if pending else 0
        state.update(elapsed_s=elapsed(),remaining_estimate_s=round(eta,1),estimated_total_s=round(elapsed()+eta,1),
                     expected=len(jobs),pending=len(pending),concurrency=2,simultaneous_16_wafer=1,
                     basis='Same-size historical/current native replay times, at most one 16-wafer worker, one auxiliary smaller worker.')
        write(statepath,state)
        print(f'{len(state["success"])}/{len(jobs)} completed, {len(state["failed"])} failed, {list(children)}, elapsed {elapsed():.1f}s, total ~{elapsed()+eta:.0f}s, remaining ~{eta:.0f}s',flush=True)
    while len(state['success'])+len(state['failed'])<len(jobs):
        for ident,obj in list(children.items()):
            ended=(obj.poll() is not None if isinstance(obj,subprocess.Popen) else not obj.is_running())
            if not ended:continue
            if completed(ident):state['success'].append(ident)
            else:state['failed'].append(ident)
            del children[ident];del state['workers'][ident]
        for j in sorted(jobs,key=lambda x:(-x['n'],x['H'],x['seed'])):
            ident=j['key']
            if len(children)>=2:break
            if ident in state['success'] or ident in state['failed'] or ident in children:continue
            if j['n']==16 and any(name[k]['n']==16 for k in children):continue
            ram=psutil.virtual_memory().available/2**30
            if children and ram<(8.5 if j['n']==16 else 5.):continue
            target=OUT/'runs'/ident;target.mkdir(parents=True,exist_ok=True)
            cmd=[sys.executable,'-B','-u','-X','utf8',str(SOLVER),'--mode','fixed','--source',str(JMS/j['source']),
                 '--seed',str(j['seed']),'--gap','.01','--output',str(target)]
            with (target/'console.log').open('ab') as f:p=subprocess.Popen(cmd,stdout=f,stderr=subprocess.STDOUT)
            children[ident]=p;state['workers'][ident]=dict(pid=p.pid,birth=psutil.Process(p.pid).create_time(),start_wall=time.time())
            write(statepath,state)
        report()
        if children:time.sleep(4)
    report()
    if state['failed']:raise RuntimeError('Failed native endpoint(s): '+str(state['failed']))
    publish()


if __name__=='__main__':run()

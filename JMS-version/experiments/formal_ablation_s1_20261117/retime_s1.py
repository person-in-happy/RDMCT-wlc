"""Complete a concrete serial material-flow structure with free event times."""
import argparse
import copy
from dataclasses import asdict
import importlib.util
from itertools import combinations
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

HERE=Path(__file__).resolve().parent
loader=importlib.util.spec_from_file_location('s1_acquisition_base',HERE/'qualify_s1.py')
q=importlib.util.module_from_spec(loader);loader.loader.exec_module(q)
f=q.f
DEFAULT=f.JMS/'results/s1_retiming_20261117_r1'
CASE='n2_mixed_scenario1'
ORIGINAL_FIX=q.fix_configuration


def prepare(out):
    if out.exists():raise FileExistsError('Preserve existing attempts')
    backend,validate=f.backend_modules()
    import physical_seed
    from seed import normalize_schedule
    config_path=f.JMS/'results/journal_d_qualification_20261109_r1/configs'/f'{CASE}.json'
    config=f.read(config_path);cfg=backend.Config(**config)
    pairs,cycles=q.specification(CASE)
    template=dict(pairs=[dict(id=p,mode=mode,chamber=c,members=members+[None]*(2-len(members)))
                         for p,(mode,c,members) in sorted(pairs.items())],
                  cycles=[dict(chamber=c,index=i,mode=mode,pairs=members,front=front)
                          for (c,i),(mode,members,front) in sorted(cycles.items())])
    captured=[]
    original_validate=physical_seed.validate
    def capture(data):
        captured.append(copy.deepcopy(data))
        return original_validate(data)
    physical_seed.validate=capture
    construction_error=None
    try:
        data=physical_seed.construct(cfg,template)
    except ValueError as exc:
        construction_error=str(exc)
        if not captured:raise
        data=captured[-1]
    finally:
        physical_seed.validate=original_validate
    data=normalize_schedule(cfg,data)
    data['validation']=validate(data)
    data['purpose']='Unqualified material-flow ordering template; all times will be recomputed. Never used as a feasible incumbent.'
    out.mkdir(parents=True)
    f.dump(out/'serial_candidate.json',data)
    sources={str(config_path):f.sha(config_path),str(out/'serial_candidate.json'):f.sha(out/'serial_candidate.json')}
    assets=f.inventory()|{str((HERE/name).relative_to(f.ROOT)):f.sha(HERE/name)
                         for name in ('qualify_s1.py','retime_s1.py','retime.ps1')}
    spec=dict(created_utc=f.stamp(),cases=[dict(case=CASE,config=config,config_sha256=f.sha(config_path))],
        assets=assets,sources=sources,construction_error=construction_error,
        settings=dict(min_available_gib=8.,launch_gib=12.,threads=1,workers=1),
        attempts=[dict(name='ordered_retiming',seed=31,seconds=60.,alternative=False,emphasis='default'),
                  dict(name='free_atr_retiming',seed=37,seconds=120.,alternative=False,emphasis='feasibility'),
                  dict(name='fixed_identity_retiming',seed=41,seconds=300.,alternative=False,emphasis='feasibility')],
        selection='First fully validated feasible assignment, independent of any algorithm comparison outcome.',
        scope='Supplementary offline source acquisition after two fixed-structure attempts found no incumbent. Initial serial timestamps are not certified. Repair changes times under the original S1 constraints; all added order/identity/slot bounds are restored before complete-model and independent physical validation.')
    f.dump(out/'campaign.json',spec);f.dump(out/'contract.json',dict(campaign_sha256=f.sha(out/'campaign.json')))
    for rel in assets:
        target=out/'frozen_code'/rel;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(f.ROOT/rel,target)
    print('PREPARED retiming; serial candidate valid=',data['validation']['valid'],'errors=',data['validation'].get('errors'),flush=True)


def fixed_orders(x,pairs,cycles,data,mode,dest):
    extra=ORIGINAL_FIX(x,pairs,cycles)
    m=x.model;variables={v.name:v for v in m.getVars(transformed=False)};fixed_count=0
    def setvar(v,value):
        nonlocal fixed_count
        if hasattr(v,'getLbOriginal'):
            m.chgVarLb(v,value);m.chgVarUb(v,value);fixed_count+=1
        elif isinstance(v,(int,float)) and abs(v-value)>1e-7:
            raise ValueError('Fixed value conflicts with a constant')
    pp={p['id']:p for p in data['pairs']};jobs={j['name']:j for j in data['jobs']}
    events={e['name']:e for e in data['events']}
    by_job={(e.get('job'),e['kind']):e for e in data['events'] if 'job' in e}
    for (identity,p,r),var in x.pair.dummy_identity.items():
        member=pp[p]['members'][r] if p in pp else None
        setvar(var,int(member==identity))
    loans={}
    for j in jobs.values():
        if not j['product']:
            p=j['pair'];r=pp[p]['members'].index(j['identity'])
            loans[f'{p}_{r}']=(int(j['identity'][1:]),j['loan_start'])
    keys=[f'{p}_{r}' for p in range(x.P) for r in (0,1) if not(p<x.N and r==0)]
    for a,b in combinations(keys,2):
        var=variables.get(f'order_identity_{a}_{b}')
        if var is not None:
            value=0
            if a in loans and b in loans:
                ca,ta=loans[a];cb,tb=loans[b];value=int(cb>ca or (cb==ca and ta<=tb))
            setvar(var,value)
    if mode!='fixed_identity_retiming':
        for robot,items in x.robots.items():
            if robot=='ATR' and mode=='free_atr_retiming':continue
            for a,b in combinations(items,2):
                var=variables.get(f'order_{a["name"]}_{b["name"]}')
                if var is not None:
                    setvar(var,int(a['name'] in events and b['name'] in events and
                                   events[a['name']]['start']<=events[b['name']]['start']))
        for name,var in variables.items():
            if name.startswith('sync_'):setvar(var,0)
        intervals={resource:{} for resource in ('AL','U','L','VTR_hand')}
        hands=('D1','D2','C1','C2')
        for name,j in jobs.items():
            def event(kind):return by_job[name,kind]
            if j['origin']!='VS':
                intervals['AL'][name]=(1,event('al_put')['start'])
                intervals['U'][name]=(1,event('upper_put')['start'])
                intervals['L'][name]=(1,event('destination_put')['start'])
            intervals['VTR_hand'][name+'_in']=(hands.index(j['vtr_hand_in'])+1,event('source_pick')['start'])
            intervals['VTR_hand'][name+'_out']=(hands.index(j['vtr_hand_out'])+1,j['unload_start'])
        for resource,known in intervals.items():
            slots={'AL':1,'U':2,'L':2,'VTR_hand':4}[resource]
            items=x.intervals[resource]
            for key,*_ in items:
                for slot in range(slots):
                    var=variables.get(f'slot_{resource}_{key}_{slot}')
                    if var is not None:setvar(var,int(key in known and known[key][0]==slot+1))
            for a,b in combinations(items,2):
                ka,kb=a[0],b[0];var=variables.get(f'order_{resource}_{ka}_{kb}')
                if var is not None:
                    value=0
                    if ka in known and kb in known:
                        ca,ta=known[ka];cb,tb=known[kb];value=int(cb>ca or (ca==cb and ta<=tb))
                    setvar(var,value)
    f.dump(dest/'retiming_bounds.json',dict(mode=mode,fixed_variables=fixed_count,
           scope='temporary order/identity/slot bounds; no original event time fixed'))
    return extra


def worker(out,attempt):
    data=f.read(out/'serial_candidate.json')
    dest=out/'attempts'/CASE/attempt
    q.fix_configuration=lambda x,p,c:fixed_orders(x,p,c,data,attempt,dest)
    q.worker(out,CASE,attempt)


def run(out):
    import psutil
    spec=f.checked(out);own=os.getpid();active=None
    try:
        for attempt in spec['attempts']:
            directory=out/'attempts'/CASE/attempt['name']
            if directory.exists() and not (directory/'evidence.json').exists():q.archive_incomplete(out,directory)
            if not (directory/'evidence.json').exists():
                while True:
                    blocked=q.blockers({own});free=psutil.virtual_memory().available/1024**3
                    if not blocked and free>=spec['settings']['launch_gib']:break
                    f.dump(out/'live_status.json',dict(updated_utc=f.stamp(),supervisor_pid=own,phase='resource_wait',blocked_by_pids=blocked,available_gib=free))
                    print('WAIT',blocked,'RAM',round(free,1),flush=True);time.sleep(5)
                logs=out/'logs';logs.mkdir(exist_ok=True)
                log=(logs/(attempt['name']+'_'+str(time.time_ns())+'.log')).open('wb')
                active=subprocess.Popen([sys.executable,'-X','utf8','-u',str(__file__),'worker','--campaign',str(out),'--attempt',attempt['name']],
                       cwd=f.ROOT,env=dict(os.environ,OMP_NUM_THREADS='1',MKL_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1'),stdout=log,stderr=subprocess.STDOUT)
                started=time.monotonic()
                while active.poll() is None:
                    elapsed=time.monotonic()-started
                    f.dump(out/'live_status.json',dict(updated_utc=f.stamp(),supervisor_pid=own,worker_pid=active.pid,
                           phase='retiming',attempt=attempt['name'],elapsed_seconds=elapsed,remaining_seconds=max(0,attempt['seconds']-elapsed)))
                    print(f'qualified=0/1 attempt={attempt["name"]} elapsed={elapsed:.0f}s remaining~{max(0,attempt["seconds"]-elapsed):.0f}s',flush=True)
                    if elapsed>attempt['seconds']+180:active.terminate();active.wait(timeout=30);break
                    time.sleep(5)
                code=active.returncode;active=None;log.close()
                if code!=0:raise RuntimeError('Retiming worker failed; inspect preserved log')
            evidence=f.read(directory/'evidence.json')
            if evidence['valid']:
                receipt=dict(case=CASE,source=str(directory/'result.json'),values=str(directory/'variables.json'),
                             result_sha256=evidence['result_sha256'],variables_sha256=evidence['variables_sha256'],
                             metrics=evidence['metrics'],selected_attempt=attempt['name'],qualified_utc=f.stamp())
                f.dump(out/'qualified'/CASE/'receipt.json',receipt)
                f.dump(out/'finished.json',dict(valid=1,expected=1,ended_utc=f.stamp(),metrics=evidence['metrics']))
                print('QUALIFIED',CASE,evidence['metrics'],flush=True)
                deadline=time.monotonic()+600
                while not (out/'release_resources.json').exists() and time.monotonic()<deadline:
                    f.dump(out/'live_status.json',dict(updated_utc=f.stamp(),supervisor_pid=own,phase='qualified_waiting_for_ablation_handoff',completed=1,expected=1))
                    print('qualified=1/1; ready for ablation handoff',flush=True);time.sleep(5)
                return
        f.dump(out/'needs_review.json',dict(reason='No fully validated incumbent',ended_utc=f.stamp()))
        raise RuntimeError('Retiming attempts exhausted without qualified assignment')
    finally:
        if active is not None and active.poll() is None:active.terminate();active.wait(timeout=30)


def main():
    parser=argparse.ArgumentParser(__doc__);parser.add_argument('action',choices=('prepare','run','worker'))
    parser.add_argument('--campaign',default=str(DEFAULT));parser.add_argument('--attempt');args=parser.parse_args()
    out=Path(args.campaign).resolve()
    if not out.is_relative_to((f.JMS/'results').resolve()) or out==(f.JMS/'results').resolve():parser.error('Use an isolated result directory')
    if args.action=='prepare':prepare(out)
    elif args.action=='run':run(out)
    else:worker(out,args.attempt)


if __name__=='__main__':main()

"""Reuse the campaign solver for the two missing same-policy, no-SPBS controls."""
import argparse
from datetime import datetime,timezone
import msvcrt
import os
from pathlib import Path
import subprocess
import sys
import time

import psutil
import cell
from protocol import BASE,HERE,LEVELS,OUT,PYTHON_SCIP,ROOT,TUNING,read,rel,save,sha

DEST=OUT/'spbs_policy_control'


def specification():
    main=read(OUT/'protocol.json')
    chosen=cell.selected_levels(main)
    tasks={}
    warm={}
    for case in TUNING:
        seed=case+'/cert_raw'
        prepared=read(BASE/'runs'/case/'prep/evidence.json')
        archived_input=ROOT/prepared['source']
        improvement=read(archived_input.parent/'evidence.json')
        matched=OUT/'runs'/f'{case}__selected_cut_full'/'evidence.json'
        reference=read(matched)
        if (sha(improvement['cell']['values'])!=main['inputs'][seed]['assignment_sha256']
            or not improvement['valid'] or sha(archived_input)!=improvement['variables_sha256']
            or improvement['variables_sha256']!=prepared['input_sha256']
            or abs(improvement['initialization_wall_seconds']-prepared['prep_seconds'])>1.e-6
            or prepared['assignment_sha256']!=reference['input_sha256']
            or reference['record']['selected']!=list(chosen) or not reference['record']['gate']):
            raise ValueError('Mismatched original SPBS transformation or thresholds')
        warm[case]=dict(preparation=rel(BASE/'runs'/case/'prep/evidence.json'),
                        source_preparation=rel(archived_input.parent/'evidence.json'),with_spbs=rel(matched),
                        with_spbs_sha256=sha(matched),reference_prep_seconds=prepared['prep_seconds'])
        a=case+'__no_spbs_A'
        b=case+'__no_spbs_B'
        base=dict(case=case,n=2,backend='D',seed=1,seconds=None,tables=['certified-spbs'])
        tasks[a]=dict(base,id=a,kind='scip',start=seed,deps=[],train=1,bounds=True,structure='free',
                      method='full',gap=LEVELS[chosen[0]])
        tasks[b]=dict(base,id=b,kind='secondary',start=a,deps=[a],weight=25,gap=LEVELS[chosen[1]])
    return dict(cases={c:main['cases'][c] for c in TUNING},inputs={c+'/cert_raw':main['inputs'][c+'/cert_raw'] for c in TUNING},
                tasks=tasks,warm=warm,chosen=list(chosen),main_contract=sha(OUT/'protocol.json'),
                worker_sha256=sha(HERE/'cell.py'),driver_sha256=sha(Path(__file__)),
                fixed_budget_tolerance_s=main['fixed_budget_tolerance_s'],concurrency=1,threads=1,gpu=False)


def pairing(spec):
    sys.path.insert(0,str(cell.BACKENDS['D']))
    from validate import validate
    pairs=[]
    checks=0
    for case in TUNING:
        a,b=(DEST/'runs'/(case+suffix) for suffix in ('__no_spbs_A','__no_spbs_B'))
        first,second=read(a/'evidence.json'),read(b/'evidence.json')
        for d,e in ((a,first),(b,second)):
            if (not e['valid'] or not e['record']['gate'] or e['worker_sha256']!=spec['worker_sha256']
                or sha(d/'schedule.json')!=e['schedule_sha256'] or sha(d/'assignment.json.gz')!=e['assignment_sha256']):
                raise ValueError('Unverified no-SPBS data')
            result=validate(read(d/'schedule.json'))
            if not result['valid']:raise ValueError('Replay failed')
            checks+=result['checks']
        r=spec['warm'][case]
        if sha(ROOT/r['with_spbs'])!=r['with_spbs_sha256']:raise ValueError('Changed warmed reference')
        w=read(ROOT/r['with_spbs'])
        if (first['input_sha256']!=spec['inputs'][case+'/cert_raw']['assignment_sha256']
            or first['assignment_sha256']!=second['input_sha256'] or first['schedule_sha256']!=second['source_sha256']
            or first['record'].get('policy')!=w['record']['primary'].get('policy')
            or second['metrics']['cmax']>first['metrics']['cmax']+2.e-4):
            raise ValueError('No-SPBS control does not pair')
        pairs.append(dict(case=case,common_raw_sha256=first['input_sha256'],warm_input_sha256=w['input_sha256'],
                          with_spbs_cmax=w['metrics']['cmax'],with_spbs_fB=w['metrics']['secondary'],
                          with_spbs_A_s=w['record']['primary']['seconds'],with_spbs_wall_s=w['wall_s']+r['reference_prep_seconds'],
                          with_spbs_calls=w['record']['primary']['policy_calls'],without_spbs_cmax=second['metrics']['cmax'],
                          without_spbs_fB=second['metrics']['secondary'],without_spbs_A_s=first['record']['seconds'],
                          without_spbs_wall_s=first['wall_s']+second['wall_s'],without_spbs_calls=first['record']['policy_calls']))
    save(DEST/'comparison.json',dict(valid=True,tasks=4,pairs=pairs,independent_replay_checks=checks))


def run():
    DEST.mkdir(exist_ok=True)
    with (DEST/'supervisor.lock').open('a+b') as lock:
        lock.seek(0)
        msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
        spec=specification()
        f=DEST/'protocol.json'
        if f.exists():
            if read(f)!=spec or sha(f)!=read(DEST/'contract.json')['sha256']:raise ValueError('Changed control protocol')
        else:
            save(f,spec)
            save(DEST/'contract.json',dict(sha256=sha(f),registered=datetime.now(timezone.utc).isoformat()))
        for index,key in enumerate(spec['tasks']):
            folder=DEST/'runs'/key
            if (folder/'evidence.json').exists():continue
            while psutil.virtual_memory().available<6*2**30:
                print(f'{index}/4 done | reserving memory for active experiments',flush=True)
                time.sleep(10)
            folder.mkdir(parents=True,exist_ok=True)
            progress=read(OUT/'progress.json')
            save(folder/'start_resources.json',dict(available_gib=psutil.virtual_memory().available/2**30,
                 main_active=len(progress['active']),cpus=psutil.cpu_count(),threads=1))
            print(f'{index}/4 done, 0 failed | {key} | stopping on the registered gap',flush=True)
            with (folder/f'attempt_{time.time_ns()}.log').open('w',encoding='utf-8') as log:
                subprocess.run([str(PYTHON_SCIP),'-B','-X','utf8','-u',str(Path(__file__).resolve()),'--cell',key],
                               stdout=log,stderr=subprocess.STDOUT,check=True,cwd=ROOT)
        pairing(spec)
        print('4/4 stages finished | 2 same-policy comparisons independently verified',flush=True)


if __name__=='__main__':
    ap=argparse.ArgumentParser()
    ap.add_argument('--cell')
    args=ap.parse_args()
    if args.cell:
        cell.OUT=DEST
        cell.run(args.cell)
    else:
        for var in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS'):os.environ[var]='1'
        run()

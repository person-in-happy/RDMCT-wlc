"""Run and resume the five-method, two-instance comparison in a visible terminal."""
import csv
import math
import msvcrt
import os
import subprocess
import sys
import time

import psutil

from component import GAP, HERE, JMS, OUT, PARENT, PHYSICAL, POLICIES, ROOT, TUNE_CASES, folders
from design import EPS, read, rel, save, sha

CELLS = [(case, method) for case in TUNE_CASES for method in POLICIES]
REUSED = ('full', 'no_rerank')
MAX_WORKERS = 3
THREADS = {'OMP_NUM_THREADS':'1', 'MKL_NUM_THREADS':'1', 'OPENBLAS_NUM_THREADS':'1'}
TARGET = .0001


def protocol():
    frozen = read(PARENT/'protocol.json')
    original = read(PHYSICAL/'report.json')
    if original['selected'] != {'A': GAP, 'B': GAP} or original['grid_cells_completed'] != 18:
        raise ValueError('Parameter selection differs from the complete tuning grid')
    if sha(PARENT/'protocol.json') != read(PARENT/'contract.json')['sha256']:
        raise ValueError('The primary protocol changed')
    physical = read(PHYSICAL/'protocol.json')
    for name, digest in physical['assets'].items():
        if sha(ROOT/name) != digest:
            raise ValueError('Changed physical B dependency: '+name)
    assets = [HERE/'component.py', HERE.parent/'manuscript_certified_gaps_20261119'/'worker.py',
              HERE.parent/'manuscript_fixed_rhythm_20261119'/'secondary.py', PARENT/'protocol.json',
              PHYSICAL/'protocol.json', ROOT/'cie/code/run_cie_benchmarks.py',
              ROOT/'cie/results/repro_manifest/selected_checkpoint_manifest.csv',
              ROOT/'cutsel_agent_parallel.py', ROOT/'utils.py']
    prior_shared = {}
    for case in TUNE_CASES:
        prep = PARENT/'runs'/case/'prep'
        prior = read(prep/'evidence.json')
        if not prior['valid'] or prior['solver_seed'] != 1 or sha(prep/'assignment.json.gz') != prior['assignment_sha256']:
            raise ValueError('Invalid shared SPBS input '+case)
        assets += [prep/'assignment.json.gz', prep/'evidence.json']
        prior_shared[case] = prior['assignment_sha256']
    # Verify all archived checkpoints before accepting or launching any comparison.
    sys.path.insert(0, str(JMS/'model4_pjob_nonprocessing_20261103'))
    from joint_algorithms import policy_record
    policies = {}
    for method, (identity, dim, decode, post, rerank) in POLICIES.items():
        record = policy_record(identity, 1)
        policies[method] = dict(method=identity, dimensions=dim, decode=decode, rerank=rerank,
                                training_postprocessor=post, checkpoint_sha256=record['sha256'],
                                config_sha256=record['config_sha256'])
    for path in assets:
        expected = frozen['assets'].get(rel(path))
        if expected and sha(path) != expected:
            raise ValueError('Changed original search dependency: '+rel(path))
    doc = dict(cases={case:frozen['cases'][case] for case in TUNE_CASES},
               policies=policies, initialization=prior_shared, seed=1, training_seed=1,
               thresholds={'A':TARGET,'B':TARGET}, time_limits={'A':None,'B':None},
               scope_A='global_product_Cmax',scope_B='fixed_structure_secondary',
               physical_weights=[1,10,25],threads_per_solver=1,workers=MAX_WORKERS,device='cpu',
               assets={rel(path):sha(path) for path in assets})
    dest = OUT/'protocol.json'
    if dest.is_file():
        if read(dest) != doc:
            raise ValueError('The frozen component protocol differs')
    else:
        save(dest,doc)
    return doc


def checked(case, method, folder, phase, config):
    ev = read(folder/'evidence.json')
    expected = config['scope_'+phase]
    if (ev['phase'],ev['case'],ev['arm'],ev['scope'],ev['solver_seed'],ev['training_seed']) != (
            phase,case,method,expected,1,1):
        raise ValueError(f'Unexpected run identity: {folder}')
    rec = ev['record']
    lo,hi = rec['dual_bound'],rec['primal_bound']
    if not all(map(math.isfinite, (lo,hi))) or lo > hi+1.e-6:
        raise ValueError(f'Invalid bounds: {folder}')
    gap = 0. if hi == lo else ((hi-lo)/min(abs(hi),abs(lo)) if lo*hi > 0 else math.inf)
    if not (ev['valid'] and ev['gate']['accepted'] and ev['threshold'] == TARGET and
            gap <= TARGET+1e-9 and abs(gap-ev['gate']['recomputed_gap']) < 1e-8 and
            rec['status'] in ('gaplimit','optimal') and
            abs(ev['metrics']['cmax' if phase=='A' else 'secondary']-hi) <= EPS):
        raise ValueError(f'Uncertified {folder}')
    for name, field in [('assignment.json.gz','assignment_sha256'),('schedule.json','schedule_sha256')]:
        if sha(folder/name) != ev[field]:
            raise ValueError(f'Changed {folder/name}')
    if phase == 'A':
        policy=ev['policy']
        target=config['policies'][method]
        if (ev['input_sha256'],policy['method'],policy['sha256'],policy['config_sha256']) != (
                config['initialization'][case],target['method'],target['checkpoint_sha256'],target['config_sha256']):
            raise ValueError(f'Initialization or selected policy differs: {folder}')
        if method not in REUSED and (policy['feature_dimension'],policy['decode_type'],policy['rerank']) != (
                target['dimensions'],target['decode'],target['rerank']):
            raise ValueError(f'Incorrect component state: {folder}')
    return ev


def paired_row(case, method, config):
    from gap_metrics import replay
    pa,pb = folders(case,method)
    a,b = checked(case,method,pa,'A',config),checked(case,method,pb,'B',config)
    if (b['primary_evidence_sha256'] != sha(pa/'evidence.json') or b['input_sha256'] != a['assignment_sha256']
            or b['metrics']['cmax'] > a['metrics']['cmax']+EPS or b['metrics']['secondary'] > b['initial']['secondary']+EPS):
        raise ValueError(f'Broken physical handoff: {pb}')
    replay(pa,a)
    metrics = replay(pb,b)
    telem = read(pa/'attempts'/a['attempt']/'cutsel.json')
    return dict(case=case,method=method,reused=method in REUSED,cmax=metrics['cmax'],secondary=metrics['secondary'],
                wait_sum=metrics['wait_sum'],wait_max=metrics['wait_max'],rhythm=metrics['rhythm'],
                rhythm_centers=metrics['rhythm_centers'],calls=telem['callback_calls'],
                seconds_A=a['record']['seconds'],seconds_B=b['record']['seconds'],
                lower_A=a['record']['dual_bound'],upper_A=a['record']['primal_bound'],
                lower_B=b['record']['dual_bound'],upper_B=b['record']['primal_bound'],
                gap_A=a['gate']['recomputed_gap'],gap_B=b['gate']['recomputed_gap'],
                evidence_A=rel(pa/'evidence.json'),evidence_B=rel(pb/'evidence.json'),
                evidence_sha_A=sha(pa/'evidence.json'),evidence_sha_B=sha(pb/'evidence.json'))


def publish_rows(cache):
    rows=[cache[cell] for cell in CELLS if cell in cache]
    data=dict(completed=len(rows),planned=len(CELLS),reused=sum(r['reused'] for r in rows),rows=rows)
    save(OUT/'report.json',data)
    if rows:
        temp=OUT/'results.csv.tmp'
        with temp.open('w',encoding='utf-8-sig',newline='') as stream:
            writer=csv.DictWriter(stream,fieldnames=rows[0].keys())
            writer.writeheader()
            writer.writerows(rows)
        try:
            temp.replace(OUT/'results.csv')
        except PermissionError:
            pass


def next_phase(cell):
    pa,pb = folders(*cell)
    if not (pa/'evidence.json').exists():
        return 'A'
    return 'B' if not (pb/'evidence.json').exists() else None


def run():
    OUT.mkdir(parents=True,exist_ok=True)
    with (OUT/'controller.lock').open('a+b') as lock:
        lock.seek(0)
        msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
        config=protocol()
        cache, active, failures = {}, {}, {}
        baseline=read(PHYSICAL/'report.json')['rows']
        estimates={case:sum(r['primary_seconds']+r['secondary_seconds'] for r in baseline
                            if r['case']==case and r['arm'] in REUSED and r['target_A_pct']==.01 and r['target_B_pct']==.01)/2
                   for case in TUNE_CASES}
        last_print=0
        try:
            while True:
                changed=False
                for cell,(proc,started,phase) in list(active.items()):
                    code=proc.poll()
                    if code is None:
                        continue
                    del active[cell]
                    if code not in (0,73):
                        failures[cell]=f'{phase} exited {code}'
                for cell in CELLS:
                    if cell not in cache and next_phase(cell) is None:
                        cache[cell]=paired_row(*cell,config)
                        changed=True
                if changed:
                    publish_rows(cache)
                if len(cache)==len(CELLS):
                    save(OUT/'progress.json',dict(completed=len(cache),planned=len(CELLS),active='',failures={}))
                    print(f'Completed {len(cache)}/{len(CELLS)} | failed 0 | ETA 0',flush=True)
                    return
                # Front-load one long cell, leaving slots for short instances and B handoffs.
                order=sorted(CELLS,key=lambda cell:(next_phase(cell)!='B', CELLS.index(cell)%5, cell[0]))
                for cell in order:
                    if len(active)>=MAX_WORKERS:
                        break
                    if cell in active or cell in cache or cell in failures:
                        continue
                    phase=next_phase(cell)
                    if phase is None:
                        continue
                    if cell[1] in REUSED:
                        raise ValueError('Verified reference missing')
                    if psutil.virtual_memory().available/2**30 < 4.5 + .8*len(active):
                        break
                    primary_folder, secondary_folder = folders(*cell)
                    folder = primary_folder if phase == 'A' else secondary_folder
                    folder.mkdir(parents=True,exist_ok=True)
                    with (folder/f'worker-{time.time_ns()}.log').open('wb') as log:
                        proc=subprocess.Popen([sys.executable,'-B','-X','utf8','-u',str(HERE/'component.py'),phase,*cell],
                                              stdout=log,stderr=subprocess.STDOUT,env={**os.environ,**THREADS})
                    active[cell]=(proc,time.monotonic(),phase)
                    print('START',phase,*cell,flush=True)
                if changed or time.monotonic()-last_print>=25:
                    remaining=sum(max(0.,estimates[cell[0]]-(time.monotonic()-active[cell][1] if cell in active else 0.))
                                  for cell in CELLS if cell not in cache and cell not in failures)
                    workers=', '.join(f'{cell[0][2:]}/{cell[1]}:{v[2]}' for cell,v in active.items())
                    print(f'{len(cache)}/{len(CELLS)} complete | {len(failures)} failed | approx ETA {remaining/MAX_WORKERS/60:.1f} min | {workers}',flush=True)
                    save(OUT/'progress.json',dict(completed=len(cache),planned=len(CELLS),active=workers,
                                                  failures={str(k):v for k,v in failures.items()}))
                    last_print=time.monotonic()
                if failures and not active and len(failures)+len(cache)==len(CELLS):
                    raise RuntimeError(str(failures))
                time.sleep(3)
        finally:
            for proc,_,_ in active.values():
                if proc.poll() is None:
                    proc.terminate()
                proc.wait()


if __name__=='__main__':
    run()

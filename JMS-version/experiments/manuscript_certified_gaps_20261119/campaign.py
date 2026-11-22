"""Foreground, resumable experiment scheduler; run from the project's a3cenv."""
import argparse
import csv
from datetime import datetime, timezone
import itertools
import msvcrt
import os
from pathlib import Path
import subprocess
import sys
import time
import traceback

import psutil
from design import (EXTENSIONS, HERE, JMS, LEVELS, METHODS, OUT, RESULTS, ROOT,
                    SEED, TRAINING_SEED, TUNING, pick, read, rel, save, sha)


def fingerprint():
    files = list(HERE.glob('*.py'))
    for backend in ('model4_pjob_nonprocessing_20261103','model4_pjob_nondecreasing_20261102'):
        files.extend((JMS/backend).glob('*.py'))
    files.extend([HERE.parent/'gap_both_stages_20261118/gap_two_stage.py',
                  HERE.parent/'finite_budget_20261116/finite_budget.py',
                  HERE.parent/'manuscript_cases_20261119/cases.py',
                  ROOT/'cie/code/run_cie_benchmarks.py',ROOT/'cutsel_agent_parallel.py',
                  ROOT/'pointer_net_end_token.py',ROOT/'pointer_net.py',
                  ROOT/'cie/configs/cie_proposed_inference.json',
                  ROOT/'cie/results/repro_manifest/selected_checkpoint_manifest.csv'])
    return {rel(p):sha(p) for p in files}


def prepare(out):
    if (out/'protocol.json').exists():
        return
    sys.path.insert(0,str(HERE.parent/'manuscript_cases_20261119'))
    from cases import catalog
    all_cases = {c['id']:c for c in catalog()[0]}
    selected, hashes = {}, {}
    for name in (*TUNING,*EXTENSIONS):
        c = all_cases[name]
        case = dict(id=name,backend=c['backend'],config=c['config'],n=c['n'])
        if name in TUNING:
            folder = RESULTS/'journal_d_transfer_20261109_r1'/'runs'/(name[2:]+f'__s{SEED}__t1__shared_spbs')
            old = read(folder/'evidence.json')
            if old['cell']['seed'] != SEED or not old['valid'] or read(folder/'result.json')['config'] != c['config']:
                raise ValueError('Mismatch in shared preparation')
            paths = dict(raw=Path(old['cell']['values']),shared=folder/'variables.json',shared_evidence=folder/'evidence.json')
            if sha(paths['shared']) != old['variables_sha256']:
                raise ValueError('Modified SPBS witness')
            if read(Path(old['cell']['source']))['config'] != c['config']:
                raise ValueError('Raw source configuration mismatch')
        else:
            frozen = RESULTS/'manuscript_cases_A0p001pct_B0p001pct_20261119'/'cases'/name
            if read(frozen/'final.json')['config'] != c['config']:
                raise ValueError('Expansion warm start configuration mismatch')
            paths = dict(raw=frozen/'final_assignment.json.gz')
        for key,p in paths.items():
            case[key] = rel(p)
            hashes[case[key]] = sha(p)
        case['scip_memory_mib'] = {2:1600,4:2600,8:4800,16:7800}[c['n']]
        selected[name]=case
    policies = ROOT/'cie/results/repro_manifest/selected_checkpoint_manifest.csv'
    with policies.open(encoding='utf-8-sig') as stream:
        row, = [r for r in csv.DictReader(stream) if r['family']=='proposed' and int(r['training_seed'])==TRAINING_SEED]
    if sha(ROOT/row['checkpoint']) != row['checkpoint_sha256']:
        raise ValueError('Changed training checkpoint')
    hashes[row['checkpoint']] = row['checkpoint_sha256']
    prior = RESULTS/'scale75_mixed_A0p001pct_B0p001pct_D_20261119'
    for p in (prior/'final/figures/gantt_resources.pdf',prior/'report.json'):
        hashes[rel(p)]=sha(p)
    spec=dict(protocol='certified_A_global_then_B_fixed_v1', levels=LEVELS, tuning=TUNING, extensions=EXTENSIONS,
        cases=selected, methods=METHODS, solver_seed=SEED, training_seed=TRAINING_SEED, cpu_threads=1,
        gpu_workers=0, time_limits={'A':None,'B':None}, cached_or_generated_spbs_preparation_seconds=60,
        selection='mean per-instance normalized Cmax, then normalized physical secondary, each rounded to 1e-6; if tied choose looser A then B; requires all 18 valid',
        ablations='same two cases; full from selected grid cells, paired no_spbs and no_rerank at same thresholds',
        checkpoint='restart an unfinished stage from its validated incumbent and scoped dual bound; finished stages never rerun',
        created_utc=datetime.now(timezone.utc).isoformat(), python=sys.executable,
        inputs=hashes, assets=fingerprint(), policy=row)
    save(out/'protocol.json',spec)
    save(out/'contract.json',{'sha256':sha(out/'protocol.json')})


def locate(out, job):
    case,stage,arm,a,b = job
    base = out/'runs'/case
    if stage=='prep': return base/'prep'
    return base/arm/(('A_'+a) if stage=='A' else ('B_'+a+'_'+b))


def evidence(out, job):
    p = locate(out,job)/'evidence.json'
    return read(p) if p.is_file() else None


def grid(out):
    rows = {}
    for c,a,b in itertools.product(TUNING,LEVELS,LEVELS):
        item = evidence(out,(c,'B','full',a,b))
        if item and item['valid']: rows[c,a,b]=item
    return rows


def jobs(out):
    pending = []
    def schedule(c,arm,pairs):
        if METHODS[arm][1]:
            pending.append((c,'prep','full','-','-'))
        for a,b in pairs:
            pending.extend([(c,'A',arm,a,'-'),(c,'B',arm,a,b)])
    pairs = list(itertools.product(LEVELS,repeat=2))
    for c in TUNING: schedule(c,'full',pairs)
    choice = pick(grid(out))
    if choice:
        for c in TUNING:
            for arm in ('no_spbs','no_rerank'): schedule(c,arm,[choice])
        for c in EXTENSIONS: schedule(c,'full',[choice])
    return list(dict.fromkeys(pending)),choice


def ready(out, job):
    c,s,arm,a,b = job
    if s=='A' and METHODS[arm][1]:
        return bool(evidence(out,(c,'prep','full','-','-')))
    return s!='B' or bool(evidence(out,(c,'A',arm,a,'-')))


def report(out):
    tasks, choice = jobs(out)
    rows=[]
    for job in tasks:
        c,s,arm,a,b=job
        ev=evidence(out,job)
        if s!='B' or not ev or not ev['valid']: continue
        first=evidence(out,(c,'A',arm,a,'-'))
        rows.append(dict(case=c, arm=arm, target_A_pct=100*LEVELS[a],target_B_pct=100*LEVELS[b],
             achieved_A_pct=100*first['gate']['recomputed_gap'], achieved_B_pct=100*ev['gate']['recomputed_gap'],
             lower_A=first['record']['dual_bound'],upper_A=first['record']['primal_bound'],
             lower_B=ev['record']['dual_bound'],upper_B=ev['record']['primal_bound'],**ev['metrics'],
             primary_seconds=first['record']['seconds'],secondary_seconds=ev['record']['seconds'],
             evidence=rel(locate(out,job)/'evidence.json')))
    linked=[]
    if choice:
        for c in TUNING:
            p=locate(out,(c,'B','full',*choice))/'evidence.json'
            linked.append(dict(case=c, sections=['SPBS','cut_selection'],evidence=rel(p),sha256=sha(p)))
    summary=dict(completed_cells=len(rows),planned_cells=len(TUNING)*9+len(TUNING)*2+len(EXTENSIONS),
                 grid_cells_completed=len(grid(out)),grid_cells_planned=len(TUNING)*9,
                 selected=None if not choice else dict(A=choice[0],B=choice[1]),reused_full=linked,rows=rows)
    save(out/'report.json',summary)
    if rows:
        p=out/'results.csv'
        temp=p.with_suffix('.csv.tmp')
        with temp.open('w',encoding='utf-8-sig',newline='') as stream:
            writer=csv.DictWriter(stream,fieldnames=rows[0].keys())
            writer.writeheader()
            writer.writerows(rows)
        temp.replace(p)
    return summary


def start(out,job):
    folder=locate(out,job)
    attempt=folder/'attempts'/str(time.time_ns())
    attempt.mkdir(parents=True)
    log=(attempt/'worker.log').open('wb')
    args=[sys.executable,'-B','-X','utf8','-u',str(Path(__file__).resolve()),'worker','--out',str(out),'--job',*job,'--attempt',str(attempt)]
    proc=subprocess.Popen(args,stdout=log,stderr=subprocess.STDOUT)
    log.close()
    return proc


def run(out):
    out.mkdir(parents=True,exist_ok=True)
    with (out/'controller.lock').open('a+b') as lock:
        lock.seek(0)
        msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
        prepare(out)
        spec=read(out/'protocol.json')
        if sha(out/'protocol.json')!=read(out/'contract.json')['sha256'] or fingerprint()!=spec['assets']:
            raise ValueError('Code or protocol differs from the frozen study')
        for name,expected in spec['inputs'].items():
            if sha(ROOT/name)!=expected: raise ValueError('Changed input '+name)
        for p in psutil.process_iter(['pid','cmdline']):
            try:
                args=p.info['cmdline'] or []
                if str(Path(__file__).resolve()) in args and 'worker' in args and str(out) in args:
                    raise RuntimeError(f'Previous worker {p.pid} still owns this experiment')
            except (psutil.NoSuchProcess,psutil.AccessDenied): pass
        active,failed={},set()
        ticks=0
        try:
            while True:
                for job,proc in list(active.items()):
                    rc=proc.poll()
                    if rc is None: continue
                    del active[job]
                    if rc: failed.add(job)
                    print('DONE' if not rc else 'FAILED',job,flush=True)
                    report(out)
                tasks,choice=jobs(out)
                todo=[j for j in tasks if not evidence(out,j) and j not in failed and j not in active and ready(out,j)]
                # Fill short B jobs first. One learned A at a time; never start two large models.
                todo.sort(key=lambda j:({'B':0,'prep':1,'A':2}[j[1]],spec['cases'][j[0]]['n']))
                waiting=False
                for j in todo:
                    if len(active)>=2: break
                    n=spec['cases'][j[0]]['n']
                    if j[1]=='A' and any(k[1]=='A' for k in active): continue
                    if (n>=8 and active) or any(spec['cases'][k[0]]['n']>=8 for k in active): continue
                    avail=psutil.virtual_memory().available/2**30
                    need={2:3.5,4:5.,8:7.,16:10.}[n]
                    if avail<need: waiting=True; continue
                    active[j]=start(out,j)
                    print('START',j,'PID',active[j].pid,flush=True)
                if ticks%3==0:
                    s=report(out)
                    observed=[r['primary_seconds']+r['secondary_seconds'] for r in s['rows']]
                    print(f"Verified {s['completed_cells']}/{s['planned_cells']} | grid {s['grid_cells_completed']}/18 | failed stages {len(failed)} | available {psutil.virtual_memory().available/2**30:.1f} GiB",flush=True)
                    print('ETA: no certified rate for an unfinished global bound' if not observed else f'Observed completed A+B: {min(observed):.1f}--{max(observed):.1f}s; overall ETA unknown (different instance sizes).',flush=True)
                    for j in active:
                        p=locate(out,j)/'progress.json'
                        if p.exists(): print(j,read(p),flush=True)
                if not active and not waiting:
                    if failed: raise RuntimeError(f'{len(failed)} failed stages; inspect attempts and resume')
                    if choice and all(evidence(out,j) for j in tasks): break
                    if not todo: raise RuntimeError('Blocked dependency')
                time.sleep(3)
                ticks+=1
        finally:
            for proc in active.values():
                if proc.poll() is None: proc.terminate()
            for proc in active.values(): proc.wait()
            report(out)


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('action',choices=['run','worker','status'])
    parser.add_argument('--out',type=Path,default=OUT)
    parser.add_argument('--job',nargs=5)
    parser.add_argument('--attempt',type=Path)
    args=parser.parse_args()
    if args.action=='run': run(args.out.resolve())
    elif args.action=='status':
        print(read(args.out/'report.json') | {'rows':'see results.csv'})
    else:
        from worker import solve
        case,stage,arm,a,b=args.job
        try:
            spec=read(args.out/'protocol.json')
            solve(args.out,spec['cases'][case],(stage,arm,a,b),locate(args.out,args.job),args.attempt)
        except BaseException as exc:
            save(args.attempt/'failure.json',dict(reason=str(exc),trace=traceback.format_exc()))
            raise

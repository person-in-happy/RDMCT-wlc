"""Visible, unlimited exact searches followed by independent certification."""
from pathlib import Path
import argparse,json,os,shutil,subprocess,sys,time
import psutil
from continue_paper_optimality import ROOT,BASE,CASES,read,now,external_growth
from run_experiments import dump,digest,assets
from run_matched_supplement import output_lock
from optimality_runtime import certificate_asset_changes

TOOLS=Path(__file__).resolve().parent
STEPS=('search','certify','verify','render')


def next_step(step,code,folder):
    if code:return 'needs_review'
    if step=='search':
        record=read(folder/'finished.json') if (folder/'finished.json').exists() else {}
        return 'certify' if all(record.get(k) is True for k in ('sublevel_optimal','physical_valid','sublevel_model_check')) else 'needs_review'
    if step=='certify':
        record=read(folder/'certificate.json') if (folder/'certificate.json').exists() else {}
        return 'verify' if record.get('accepted') and record.get('full_candidate_space') else 'needs_review'
    if step=='verify':
        record=read(folder) if folder.exists() else {}
        return 'render' if record.get('original_objective_globally_optimal') is True else 'needs_review'
    if step=='render':return 'complete' if (folder/'manifest.json').exists() else 'needs_review'
    raise ValueError(step)


def live_workers(out):
    found=[]
    ancestors={proc.pid for proc in psutil.Process().parents()}|{os.getpid()}
    for proc in psutil.process_iter(['pid','cmdline']):
        if proc.pid in ancestors:continue
        try:
            cmd=proc.info['cmdline'] or []
            names={'run_exact_paper_queue.py','solve_cpsat_sublevel.py','certify_original_schedule.py','verify_exact_optimality.py','render_certified_exact_gantt.py'}
            if not any(Path(v).name in names for v in cmd) or '--output' not in cmd:continue
            path=Path(cmd[cmd.index('--output')+1])
            if not path.is_absolute():path=Path(proc.cwd())/path
            if path.resolve().is_relative_to(out):found.append(proc.pid)
        except psutil.NoSuchProcess:continue
    return found


def inputs():
    items={}
    for case,(warm,cert) in CASES.items():
        source=BASE/warm/'result.json';certificate=BASE/cert/'certificate.json'
        if case=='n16_H3_4x1':
            latest=ROOT/'JMS-version/results/optimality_work_20261022'
            source=latest/'cpsat_labels_probe_H3_4x1/result.json'
            certificate=latest/'original_certificate_920_H3_4x1/certificate.json'
        record=read(certificate)
        if not record.get('accepted') or not record.get('full_candidate_space') or record['source_sha256']!=digest(source):
            raise ValueError('Uncertified initial witness: '+case)
        certificate_asset_changes(record['assets'],assets())
        items[case]=dict(source=str(source),certificate=str(certificate),source_sha256=digest(source),certificate_sha256=digest(certificate))
    return items


def tail(path):
    if not path.exists():return 'building model'
    with path.open('rb') as stream:
        stream.seek(max(0,path.stat().st_size-3000));lines=stream.read().decode('utf-8',errors='replace').splitlines()
    return next((v.strip() for v in reversed(lines) if v.strip()),'starting')


def tree_rss(pid):
    try:
        parent=psutil.Process(pid);processes=[parent]+parent.children(recursive=True)
    except psutil.NoSuchProcess:return 0
    total=0
    for proc in processes:
        try:total+=proc.memory_info().rss/1048576
        except psutil.NoSuchProcess:pass
    return total


def stop_owned_tree(proc):
    # Windows virtual-environment launchers can have a separate Python child.
    try:children=psutil.Process(proc.pid).children(recursive=True)
    except psutil.NoSuchProcess:children=[]
    for child in reversed(children):
        try:child.terminate()
        except psutil.NoSuchProcess:pass
    proc.terminate()
    try:proc.wait(timeout=10)
    except subprocess.TimeoutExpired:proc.kill();proc.wait()
    _,alive=psutil.wait_procs(children,timeout=5)
    for child in alive:
        try:child.kill()
        except psutil.NoSuchProcess:pass


def main():
    parser=argparse.ArgumentParser(__doc__)
    parser.add_argument('--output',required=True);parser.add_argument('--jobs',type=int,default=2)
    parser.add_argument('--workers',type=int,default=2);parser.add_argument('--memory-mb',type=int,default=6000)
    parser.add_argument('--resume-interrupted',action='store_true');parser.add_argument('--check-only',action='store_true')
    a=parser.parse_args();out=Path(a.output).resolve()
    if a.jobs<1 or a.workers<1 or a.memory_mb<1:parser.error('Invalid resource setting')
    if not out.is_relative_to(ROOT/'JMS-version/results') or out==ROOT/'JMS-version/results':parser.error('Use an isolated results subdirectory')
    initial=inputs();live=live_workers(out)
    if live:raise RuntimeError('This queue is already running: '+str(live))
    # Freeze every local tool used in this evidence chain, including imported helpers.
    files=('run_exact_paper_queue.py','continue_paper_optimality.py','solve_cpsat_sublevel.py','certify_original_schedule.py',
           'verify_exact_optimality.py','render_certified_exact_gantt.py','render_optional_cleaning_gantt.py',
           'incumbent_sublevel.py','terminal_cleanup_bound.py','cycle_work_bounds.py','pure2_block_certificate.py',
           'pair_label_symmetry.py','integer_timing_export.py','optimality_runtime.py')
    frozen={name:digest(TOOLS/name) for name in files}
    if a.check_only:
        print(json.dumps(dict(checked_cases=len(initial),jobs=a.jobs,workers_per_search=a.workers,
            memory_mb=a.memory_mb,main_time_limit=None,external_growth_mb=external_growth(set())),indent=2));return
    out.mkdir(parents=True,exist_ok=True)
    with output_lock(out):
        statepath=out/'queue.json'
        if statepath.exists():
            state=read(statepath)
            if not a.resume_interrupted:raise ValueError('Existing queue; use --resume-interrupted after all its processes exit')
            if any(state[k]!=v for k,v in dict(inputs=initial,scripts=frozen,assets=assets(),jobs=a.jobs,workers=a.workers,memory_mb=a.memory_mb).items()):
                raise ValueError('Frozen inputs, code or settings changed; preserve this queue')
            for item in state['cases'].values():
                if item['state']=='running':
                    # Recover a completed step before creating a fresh attempt.
                    previous=item['attempts'][-1];step=previous['step'];folder=Path(previous['output'])
                    recovered=next_step(step,0,folder)
                    item['state']=recovered if recovered!='needs_review' else step
        else:
            snap=out/'scripts';snap.mkdir()
            for name in files:shutil.copy2(TOOLS/name,snap/name)
            state=dict(inputs=initial,scripts=frozen,assets=assets(),jobs=a.jobs,workers=a.workers,memory_mb=a.memory_mb,
                       main_time_limit=None,created_utc=now(),cases={case:dict(state='search',attempts=[]) for case in initial})
        state.update(state='running',supervisor_pid=os.getpid(),started_utc=now());dump(statepath,state)
        active={};last=0
        print('VISIBLE EXACT QUEUE | 4 cases | unlimited main search | Ctrl+C stops this queue only\n'
              'ETA unknown: proof time cannot be reliably predicted. Search -> full original model -> proof -> figures.',flush=True)
        try:
            while True:
                for case,item in list(active.items()):
                    code=item['proc'].poll()
                    if code is None:continue
                    item['stream'].close();entry=state['cases'][case]
                    entry['attempts'][-1].update(exit_code=code,ended_utc=now())
                    entry['state']=next_step(item['step'],code,item['folder'])
                    del active[case];dump(statepath,state)
                    print('END '+case+' '+item['step']+' -> '+entry['state'],flush=True)
                pending=[case for case in initial if state['cases'][case]['state'] in STEPS]
                # Prioritize certification; at most one large certification at a time.
                pending.sort(key=lambda case:state['cases'][case]['state']=='search')
                for case in pending:
                    if len(active)>=a.jobs:break
                    entry=state['cases'][case];step=entry['state']
                    if step=='certify' and any(v['step']=='certify' for v in active.values()):continue
                    budget=(14000 if '2x2' in case else 6000) if step=='certify' else (a.memory_mb if step=='search' else 1000)
                    pids={v['proc'].pid for v in active.values()}
                    growth=sum(max(0,v['budget']*1.15-tree_rss(v['proc'].pid)) for v in active.values())
                    free=psutil.virtual_memory().available/1048576
                    if free-growth-external_growth(pids)-2048 < budget*1.15:continue
                    attempt=1+sum(v['step']==step for v in entry['attempts'])
                    folder=out/case/(step+f'_{attempt:02d}')
                    folder.parent.mkdir(parents=True,exist_ok=True)
                    cmd=[sys.executable,'-u','-X','utf8']
                    if step=='search':
                        cmd += [str(TOOLS/'solve_cpsat_sublevel.py'),'--source',initial[case]['source'],'--certificate',initial[case]['certificate'],
                                '--output',str(folder),'--memory-mb',str(budget),'--workers',str(a.workers)]
                        entry['search']=str(folder)
                    elif step=='certify':
                        cmd += [str(TOOLS/'certify_original_schedule.py'),'--source',str(Path(entry['search'])/'result.json'),
                                '--output',str(folder),'--memory-mb',str(budget)]
                        entry['certificate']=str(folder/'certificate.json')
                    elif step=='verify':
                        folder=folder.with_suffix('.json');entry['proof']=str(folder)
                        cmd += [str(TOOLS/'verify_exact_optimality.py'),'--search',entry['search'],'--original-certificate',entry['certificate'],'--output',str(folder)]
                    else:
                        folder=ROOT/'JMS-version/figures'/out.name/(case+f'_{attempt:02d}');entry['figures']=str(folder)
                        cmd += [str(TOOLS/'render_certified_exact_gantt.py'),'--proof',entry['proof'],'--output',str(folder)]
                    log=out/case/(step+f'_{attempt:02d}.console.log');stream=log.open('wb')
                    proc=subprocess.Popen(cmd,cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT)
                    entry['attempts'].append(dict(step=step,output=str(folder),command=cmd,pid=proc.pid,started_utc=now()))
                    entry.update(state='running',step=step,pid=proc.pid)
                    active[case]=dict(proc=proc,stream=stream,step=step,folder=folder,budget=budget,log=log)
                    dump(statepath,state);print(f'START {case} {step} PID={proc.pid} memory_mb={budget}',flush=True)
                if time.monotonic()-last>=15:
                    last=time.monotonic();states=[v['state'] for v in state['cases'].values()]
                    print(f'[{now()}] complete={states.count("complete")}/4 running={len(active)} failed={states.count("needs_review")} pending={sum(v in STEPS for v in states)} ETA unknown',flush=True)
                    for case,item in active.items():
                        message=tail(item['log'])
                        progress=item['folder']/'progress.json'
                        if item['step']=='search' and progress.exists():
                            try:
                                report=read(progress)
                                message=f'UB={report["upper"]} LB={report["lower"]} search_elapsed_minutes={(time.time()-Path(state["cases"][case]["search"]).stat().st_ctime)/60:.1f}'
                            except (OSError,ValueError,KeyError):pass
                        print('  '+case+' '+item['step']+' '+message,flush=True)
                    if not active and pending:print('  Waiting for RAM reserved for other experiments.',flush=True)
                if not active and not any(v['state'] in STEPS for v in state['cases'].values()):break
                time.sleep(3)
        except BaseException as exc:
            state.update(state='interrupted',error=str(exc))
            for case,item in active.items():
                stop_owned_tree(item['proc'])
                item['stream'].close()
            dump(statepath,state)
            if isinstance(exc,KeyboardInterrupt):return
            raise
        complete=all(v['state']=='complete' for v in state['cases'].values())
        state.update(state='complete' if complete else 'needs_review',ended_utc=now());dump(statepath,state)
        print('ALL FOUR ORIGINAL OPTIMA CERTIFIED AND RENDERED' if complete else 'Queue needs review; no automatic retry of failed proofs.',flush=True)
        if not complete:raise SystemExit(2)


if __name__=='__main__':main()

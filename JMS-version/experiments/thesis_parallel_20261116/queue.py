"""Foreground, memory-admitted CPU queue; existing frozen campaigns are read-only."""
from pathlib import Path
from datetime import datetime, timezone
from types import SimpleNamespace
import argparse
import ctypes
import hashlib
import json
import math
import os
import shutil
import statistics
import subprocess
import sys
import time

import psutil

ENTRY = Path(__file__).resolve()
ROOT = ENTRY.parents[3]
RESULTS = ROOT / 'JMS-version/results'
PREDECESSOR = RESULTS / 'finite_budget_20261116_r1'
GIB = 1024**3


def stamp():
    return datetime.now(timezone.utc).isoformat()


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(8 * 1024**2), b''):
            h.update(chunk)
    return h.hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def dump(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f'.{os.getpid()}.tmp')
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
    tmp.replace(path)


def root_path(value):
    path = Path(value).resolve()
    if path == RESULTS or not path.is_relative_to(RESULTS):
        raise ValueError('Queue outputs must be isolated under JMS-version/results')
    return path


def load_support():
    sys.path.insert(0, str(ROOT / 'JMS-version/tools'))
    sys.path.insert(0, str(ROOT))
    import journal_support_experiments as support
    if not getattr(support, '_parallel_inventory', False):
        original = support.inventory
        support.inventory = lambda: original() | {
            str(ENTRY.relative_to(ROOT)): sha(ENTRY),
            str(ENTRY.with_name('launch.ps1').relative_to(ROOT)): sha(ENTRY.with_name('launch.ps1')),
        }
        support._parallel_inventory = True
    return support


def prepare_stage(out, suite, settings, source=None):
    support = load_support()
    args = SimpleNamespace(suite=suite, source_campaign=str(source) if source else None,
                           time_limit=1200. if suite == 'chain' else 60.,
                           wall_limit=3600. if suite == 'chain' else 1800.,
                           min_available_fraction=.25)
    support.prepare(args, out)
    # This is a newly prepared, never-run protocol. Freeze its actual concurrent
    # execution settings before any worker is permitted to start.
    spec = read(out / 'campaign.json')
    spec['settings'].update(jobs=settings['max_workers'], execution_queue=settings)
    spec['selection'] = ('Eight predefined D configurations, three solver seeds each; '
                         'all 24 outcomes retained. Conditional rhythm input is the '
                         'lowest successful predefined seed per configuration, after '
                         'all chain cells have finished and passed saved hash checks.')
    spec['primary_contrast'] = ('Validated coupled-witness coverage; then conditional '
                                'rhythm-weight comparisons at matched seeds and budgets.')
    dump(out / 'campaign.json', spec)
    dump(out / 'contract.json', dict(campaign_sha256=sha(out / 'campaign.json')))
    support.checked(out)


def prepare(out):
    if out.exists():
        raise FileExistsError('Existing queue is immutable; use run after inspecting it')
    settings = dict(max_workers=4, threads_per_worker=1, gpu_workers=0,
                    min_available_gib=8., launch_available_gib=10.,
                    min_commit_headroom_gib=8., launch_commit_headroom_gib=12.,
                    reservation_gib_n4=3., reservation_gib_n6=5.,
                    max_cpu_percent_to_launch=85., launch_spacing_seconds=15.,
                    refresh_seconds=10., poll_seconds=2.,
                    external_experiments_must_be_idle=True)
    out.mkdir(parents=True)
    prepare_stage(out / 'chain', 'chain', settings)
    plan = dict(schema=1, created_utc=stamp(), settings=settings,
                predecessor=str(PREDECESSOR),
                predecessor_contract_sha256=sha(PREDECESSOR / 'contract.json'),
                predecessor_campaign_sha256=sha(PREDECESSOR / 'campaign.json'),
                queue_code_sha256=sha(ENTRY), launcher_sha256=sha(ENTRY.with_name('launch.ps1')),
                chain_contract_sha256=sha(out / 'chain/contract.json'),
                chain_cells=24, rhythm_cells_per_eligible_configuration=12,
                rhythm_selection='After every chain cell completes; lowest valid solver seed, no objective-based selection',
                failed_cell_policy='Preserve all attempts; no automatic retries; any chain execution failure blocks rhythm',
                predecessor_policy='Wait for process exit and supervisor lock removal; never stop/restart/edit it',
                timing='Solver budgets only. Parallel ETA excludes predecessor wait. Not an end-to-end benchmark.',
                system=dict(cpu_count=psutil.cpu_count(), physical_memory_gib=psutil.virtual_memory().total/GIB,
                            available_gib=psutil.virtual_memory().available/GIB))
    dump(out / 'queue_plan.json', plan)
    dump(out / 'queue_contract.json', dict(plan_sha256=sha(out / 'queue_plan.json')))
    print(json.dumps(dict(prepared=str(out), chain_cells=24, maximum_parallel=4,
                          solver_started=False), ensure_ascii=False), flush=True)


def checked(out):
    plan = read(out / 'queue_plan.json')
    assert sha(out / 'queue_plan.json') == read(out / 'queue_contract.json')['plan_sha256']
    assert sha(ENTRY) == plan['queue_code_sha256'], 'Queue code changed'
    assert sha(ENTRY.with_name('launch.ps1')) == plan['launcher_sha256'], 'Launcher changed'
    assert sha(PREDECESSOR / 'contract.json') == plan['predecessor_contract_sha256']
    assert sha(PREDECESSOR / 'campaign.json') == plan['predecessor_campaign_sha256']
    assert sha(out / 'chain/contract.json') == plan['chain_contract_sha256']
    return plan


def commit_free_gib():
    if os.name != 'nt':
        return psutil.virtual_memory().available / GIB
    class MemoryStatus(ctypes.Structure):
        _fields_ = [('length', ctypes.c_ulong), ('load', ctypes.c_ulong)] + [
            (name, ctypes.c_ulonglong) for name in ('total_phys', 'avail_phys', 'total_page',
                                                   'avail_page', 'total_virtual', 'avail_virtual', 'avail_extended')]
    status = MemoryStatus()
    status.length = ctypes.sizeof(status)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
        raise ctypes.WinError()
    return status.avail_page / GIB


def foreign_workers(owned):
    tokens = ('finite_budget.py', 'journal_support_experiments', 'journal_gap_experiments',
              'thesis_gap_experiments', 'large_schedule_experiments', 'run_experiments.py',
              'paper_defaults.py', 'run_cie_benchmarks.py', 'revalidate.py',
              'strengthen_models.py', 'review_experiments.py')
    found = []
    for p in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            if p.pid in owned or 'python' not in (p.info['name'] or '').lower():
                continue
            cmd = ' '.join(p.info['cmdline'] or []).lower()
            if any(t in cmd for t in tokens) or (ENTRY.name in cmd and 'thesis_parallel_20261116' in cmd):
                found.append(p.pid)
        except psutil.Error:
            continue
    return found


def predecessor_status():
    path = PREDECESSOR / 'live_status.json'
    try:
        state = read(path)
        return {k: state.get(k) for k in ('expected', 'completed', 'failed', 'pending', 'state',
                                         'available_gib', 'estimated_remaining_hours', 'updated_utc')}
    except (OSError, ValueError):
        return None


def gate(own_pids):
    foreign = foreign_workers(own_pids)
    locked = (PREDECESSOR / 'supervisor.lock').exists()
    return dict(allowed=not foreign and not locked, foreign_pids=foreign, predecessor_locked=locked)


def admission(settings, active, reservation, available, commit, cpu):
    if len(active) >= settings['max_workers']:
        return 'parallel_limit'
    growth = sum(max(0., a['reservation_gib'] - a.get('rss_gib', 0.)) for a in active)
    if available - growth - reservation < settings['launch_available_gib']:
        return 'waiting_for_RAM'
    if commit - growth - reservation < settings['launch_commit_headroom_gib']:
        return 'waiting_for_commit_headroom'
    if cpu >= settings['max_cpu_percent_to_launch']:
        return 'waiting_for_CPU'
    return 'ready'


def coverage(stage):
    spec = read(stage / 'campaign.json')
    rows = []
    for cell in spec['cells']:
        dest = stage / 'runs' / cell['id']
        row = dict(id=cell['id'], case=cell['case'], seed=cell['seed'], arm=cell['arm'], execution='pending')
        if (dest / 'failure.json').exists():
            row.update(execution='failed', reason=read(dest / 'failure.json')['reason'])
        elif (dest / 'resources.json').exists() and (dest / 'evidence.json').exists():
            e, resource = read(dest / 'evidence.json'), read(dest / 'resources.json')
            if resource['exit_code'] != 0:
                raise RuntimeError('Nonzero exit without failure record')
            row.update(execution='complete', valid=e['valid'], state=e['state'])
        elif (dest / 'resources.json').exists():
            raise RuntimeError('Resource record without result evidence: ' + str(dest))
        rows.append(row)
    cov = dict(expected=len(rows), **{k:sum(r['execution']==k for r in rows) for k in ('complete','failed','pending')},
               valid=sum(r.get('valid',False) for r in rows))
    dump(stage / 'summary/coverage.json', cov)
    dump(stage / 'summary/queue_cells.json', rows)
    return spec, cov


def verify_finished_cell(dest):
    e = read(dest / 'evidence.json')
    for name, key in (('result.json','result_sha256'), ('variables.json','variables_sha256')):
        if key in e:
            assert sha(dest / name) == e[key], f'Artifact changed: {dest / name}'
    if e['valid']:
        audit = e.get('unrestricted_model_audit') or e.get('full_model_audit')
        assert audit, 'Missing full-domain audit'
    return e


def worker(out, stage_name, cell):
    checked(out)
    stage = out / stage_name
    load_support().worker(stage, cell)


def finalize_process(stage, cid, state):
    process = state['process']
    code = process.wait(timeout=30)
    state['log'].close()
    dest = stage / 'runs' / cid
    dest.mkdir(parents=True, exist_ok=True)
    duration = time.monotonic() - state['start']
    reason = state.get('reason')
    if not reason and (code != 0 or not (dest / 'evidence.json').exists()):
        reason = 'worker_exit_or_missing_evidence'
    if not reason:
        try:
            verify_finished_cell(dest)
        except Exception as exc:
            reason = 'artifact_verification: ' + str(exc)
    dump(dest / 'resources.json', dict(exit_code=code, peak_rss_mib=state['peak_gib']*1024,
         wall_seconds=duration, log=str(state['logpath']), memory_policy='system_available_and_commit_guards',
         min_system_available_gib=state['min_available'], min_commit_headroom_gib=state['min_commit'],
         max_concurrent_workers=state['max_concurrency'], threads=1, gpu=False))
    if reason:
        dump(dest / 'failure.json', dict(reason=reason, exit_code=code, ended_utc=stamp()))
    print(('FAILED ' if reason else 'COMPLETE ') + cid + f' wall={duration:.1f}s' + (f' {reason}' if reason else ''), flush=True)
    return duration


def run_stage(out, stage_name, plan):
    stage, settings = out / stage_name, plan['settings']
    spec, cov = coverage(stage)
    active, durations = {}, []
    last_launch = last_display = -math.inf
    psutil.cpu_percent(None)
    try:
        while True:
            now = time.monotonic()
            available, commit = psutil.virtual_memory().available/GIB, commit_free_gib()
            for cid, state in list(active.items()):
                process = state['process']
                if process.poll() is not None:
                    durations.append(finalize_process(stage, cid, state))
                    del active[cid]
                    continue
                try:
                    proc = psutil.Process(process.pid)
                    state['rss_gib'] = sum(p.memory_info().rss for p in [proc]+proc.children(recursive=True))/GIB
                except psutil.Error:
                    state['rss_gib'] = 0.
                state['peak_gib'] = max(state['peak_gib'], state['rss_gib'])
                state['min_available'] = min(state['min_available'], available)
                state['min_commit'] = min(state['min_commit'], commit)
                state['max_concurrency'] = max(state['max_concurrency'], len(active))
                if now-state['start'] > spec['settings']['wall_limit']:
                    state['reason'] = 'wall_guard'
                    process.terminate()
            if active and (available < settings['min_available_gib'] or commit < settings['min_commit_headroom_gib']):
                state = max(active.values(), key=lambda a:a['start'])
                if state['process'].poll() is None:
                    state['reason'] = 'system_available_memory_guard' if available < settings['min_available_gib'] else 'system_commit_memory_guard'
                    state['process'].terminate()
                    last_launch = now + 30.
            spec, cov = coverage(stage)
            if not cov['pending'] and not active:
                dump(stage / 'finished.json', cov | dict(ended_utc=stamp()))
                return cov
            own = {os.getpid()} | {s['process'].pid for s in active.values()}
            ready = gate(own)
            cpu = psutil.cpu_percent(None)
            reason = 'waiting_for_existing_experiments' if not ready['allowed'] else 'ready'
            if ready['allowed'] and now-last_launch >= settings['launch_spacing_seconds']:
                for cell in spec['cells']:
                    cid, dest = cell['id'], stage / 'runs' / cell['id']
                    if cid in active or (dest / 'resources.json').exists() or (dest / 'failure.json').exists():
                        continue
                    if dest.exists():
                        raise RuntimeError('Incomplete attempt preserved; inspect before resuming: ' + str(dest))
                    reserve = settings['reservation_gib_n6'] if cell['case'].startswith('n6_') else settings['reservation_gib_n4']
                    reason = admission(settings, list(active.values()), reserve, available, commit, cpu)
                    if reason != 'ready':
                        continue
                    logpath = stage / 'logs' / (cid + '.log')
                    logpath.parent.mkdir(exist_ok=True)
                    log = logpath.open('xb')
                    env = dict(os.environ, OMP_NUM_THREADS='1', MKL_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1',
                               NUMEXPR_NUM_THREADS='1', CUDA_VISIBLE_DEVICES='', PYTHONUNBUFFERED='1')
                    proc = subprocess.Popen([sys.executable, '-X', 'utf8', '-u', str(ENTRY), 'worker', '--queue', str(out),
                                             '--stage', stage_name, '--cell', cid], cwd=ROOT, env=env,
                                            stdout=log, stderr=subprocess.STDOUT)
                    active[cid] = dict(process=proc, log=log, logpath=logpath, start=now, reservation_gib=reserve,
                                       rss_gib=0., peak_gib=0., min_available=available, min_commit=commit, max_concurrency=len(active)+1)
                    dump(stage / 'launch_records' / (cid+'.json'), dict(started_utc=stamp(), pid=proc.pid,
                         parallel_cells=list(active), available_gib=available, commit_headroom_gib=commit,
                         cpu_percent=cpu, threads=1, gpu=False, reservation_gib=reserve,
                         foreign_experiment_pids=ready['foreign_pids']))
                    print(f'START {stage_name}/{cid} parallel={len(active)}/{settings["max_workers"]}', flush=True)
                    last_launch = now
                    break
            if now-last_display >= settings['refresh_seconds']:
                nominal = spec['settings']['time_limit']
                observed = statistics.median(durations) if durations else nominal+30.
                remaining_work = sum(max(0., observed-(now-s['start'])) for s in active.values()) + max(0,cov['pending']-len(active))*observed
                # Observed concurrency is a realistic denominator while waiting;
                # the ideal four-lane lower bound is reported separately.
                lanes = max(1, len(active))
                state = dict(updated_utc=stamp(), supervisor_pid=os.getpid(), stage=stage_name,
                             state=reason, coverage=cov, active=list(active), active_pids=[s['process'].pid for s in active.values()],
                             available_gib=available, commit_headroom_gib=commit, cpu_percent=cpu,
                             estimated_remaining_hours=remaining_work/lanes/3600 if ready['allowed'] else None,
                             ideal_four_lane_solver_hours=cov['pending']*nominal/settings['max_workers']/3600,
                             eta_note='Stage-only estimate; excludes resource/predecessor waits and later conditional rhythm cells.',
                             predecessor=predecessor_status(), gate=ready, max_workers=settings['max_workers'])
                dump(out / 'live_status.json', state)
                eta = f'{state["estimated_remaining_hours"]:.2f}h' if state['estimated_remaining_hours'] is not None else 'waiting'
                print(f'{stage_name} complete={cov["complete"]}/{cov["expected"]} failed={cov["failed"]} '
                      f'valid={cov["valid"]} running={len(active)}/{settings["max_workers"]} RAM={available:.1f}GiB '
                      f'CPU={cpu:.0f}% ETA~{eta} | {reason}', flush=True)
                last_display = now
            time.sleep(settings['poll_seconds'])
    finally:
        for cid, state in active.items():
            if state['process'].poll() is None:
                state['reason'] = 'foreground_supervisor_interrupted'
                state['process'].terminate()
            finalize_process(stage, cid, state)


def child_action(out, action, *extra):
    env = dict(os.environ, OMP_NUM_THREADS='1', MKL_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1', CUDA_VISIBLE_DEVICES='')
    return subprocess.run([sys.executable,'-X','utf8','-u',str(ENTRY),action,'--queue',str(out),*extra],
                          cwd=ROOT, env=env, check=True)


def rhythm_prepare(out):
    plan = checked(out)
    support = load_support()
    try:
        sources, provenance = support.parent_sources(out / 'chain', 'chain')
    except ValueError as exc:
        if str(exc).startswith('No qualified inputs.'):
            dump(out / 'rhythm_not_started.json', dict(reason=str(exc), checked_utc=stamp()))
            return
        raise
    dump(out / 'rhythm_selection.json', provenance)
    prepare_stage(out / 'rhythm', 'rhythm', plan['settings'], out / 'chain')


def run(out):
    plan = checked(out)
    lock = out / 'supervisor.lock'
    fd = os.open(lock, os.O_CREAT|os.O_EXCL|os.O_WRONLY)
    os.write(fd, str(os.getpid()).encode())
    os.close(fd)
    try:
        chain = run_stage(out, 'chain', plan)
        if chain['failed']:
            final = dict(state='chain_finished_with_failures', chain=chain,
                 rhythm_started=False, reason='Inspect preserved failures; no automatic retry', ended_utc=stamp())
            dump(out / 'finished.json', final)
            dump(out / 'live_status.json', final | dict(active=[], supervisor_pid=os.getpid()))
            return
        child_action(out, 'report', '--stage', 'chain')
        if not (out / 'rhythm').exists() and not (out / 'rhythm_not_started.json').exists():
            child_action(out, 'prepare-rhythm')
        rhythm = None
        if (out / 'rhythm').exists():
            rhythm = run_stage(out, 'rhythm', plan)
            if not rhythm['failed']:
                child_action(out, 'report', '--stage', 'rhythm')
        final = dict(state='finished_with_rhythm_failures' if rhythm and rhythm['failed'] else 'finished', chain=chain, rhythm=rhythm,
             rhythm_skipped_reason=read(out / 'rhythm_not_started.json') if (out / 'rhythm_not_started.json').exists() else None,
             ended_utc=stamp(), note='Results require interpretation before updating thesis claims.')
        dump(out / 'finished.json', final)
        dump(out / 'live_status.json', final | dict(active=[], supervisor_pid=os.getpid()))
        print('FINISHED ' + json.dumps(read(out / 'finished.json'), ensure_ascii=False), flush=True)
    except BaseException as exc:
        dump(out / 'supervisor_failure.json', dict(error=repr(exc), ended_utc=stamp()))
        raise
    finally:
        lock.unlink()


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('action', choices=('prepare','run','worker','prepare-rhythm','report','status'))
    parser.add_argument('--queue', required=True)
    parser.add_argument('--stage', choices=('chain','rhythm'))
    parser.add_argument('--cell')
    args = parser.parse_args()
    out = root_path(args.queue)
    if args.action == 'prepare':
        prepare(out)
    elif args.action == 'run':
        run(out)
    elif args.action == 'worker':
        assert args.stage and args.cell
        worker(out, args.stage, args.cell)
    elif args.action == 'prepare-rhythm':
        rhythm_prepare(out)
    elif args.action == 'report':
        checked(out)
        assert args.stage
        load_support().report(out / args.stage)
    else:
        print(json.dumps(read(out / 'live_status.json'), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()

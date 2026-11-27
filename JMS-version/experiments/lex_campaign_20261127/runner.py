"""Foreground wall-clock controller for the five prospective lexicographic cases."""
import argparse
import contextlib
import datetime as dt
import importlib.metadata
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time
import traceback
import uuid

import psutil

HERE = Path(__file__).resolve().parent
JMS = HERE.parents[1]
sys.path.insert(0, str(JMS / 'experiments' / 'manuscript_certified_gaps_20261119'))
from design import read, save, sha

DEFAULT_OUT = JMS / 'results' / 'lex_campaign_20261127'
BUDGETS = {'n2_h3': (1200, 1800), 'n4_h3': (3600, 5400),
           'n8_h3': (21600, 28800), 'n16_h3': (21600, 28800),
           'n16_h10': (21600, 28800)}
STAGES = ('A', 'B1', 'B2', 'B3')
DONE = ('completed', 'failed')
GIB = 1024 ** 3
MEMORY_FLOOR = 2.5 * GIB
PROCESS_LIMIT = 20 * GIB
MIXED_ADMISSION = 14 * GIB
MIXED_PAUSE = 4 * GIB
EPS = 1e-6 + 1e-9


def timestamp(epoch):
    return dt.datetime.fromtimestamp(epoch).astimezone().isoformat(timespec='seconds')


def duration(seconds):
    minutes, sec = divmod(max(0, math.ceil(seconds)), 60)
    hours, minute = divmod(minutes, 60)
    return f'{hours:02}:{minute:02}:{sec:02}'


def location(s):
    p = Path(s)
    return p if p.is_absolute() else JMS / p


def load_endpoint(folder, pointer):
    meta_path = folder / pointer
    meta = read(meta_path)
    if meta['key'] != folder.name or meta['record'].get('valid') is not True:
        raise ValueError(f'Endpoint validation flag or key mismatch: {meta_path}')
    for name, digest in meta['hashes'].items():
        if sha(meta_path.parent / name) != digest:
            raise ValueError(f'Endpoint digest mismatch: {meta_path.parent / name}')
    return meta


def witness(folder, pointer, spec):
    if pointer:
        meta = load_endpoint(folder, pointer)
        base = (folder / pointer).parent
        sched = read(base / 'schedule.json.gz')
        assignment = read(base / 'assignment.json.gz') if 'assignment.json.gz' in meta['hashes'] else None
        return sched, assignment
    sched = read(location(spec['start_schedule']))
    assignment = read(location(spec['start_assignment'])) if spec.get('start_assignment') else None
    if assignment is not None:
        assignment = assignment.get('nonzero', assignment.get('values', assignment))
    return sched, assignment


def write_witness(folder, stage, rec, sched, assignment):
    if rec.get('valid') is not True or rec['stage'] != stage:
        raise ValueError('Worker supplied an unvalidated or mismatched stage endpoint')
    metrics = rec['metrics']
    if any(not math.isfinite(float(metrics[k])) for k in ('cmax', 'secondary')):
        raise ValueError('Endpoint contains nonfinite objective')
    pointer = Path('artifacts') / uuid.uuid4().hex / 'endpoint.json'
    base = (folder / pointer).parent
    save(base / 'schedule.json.gz', sched)
    paths = ['schedule.json.gz']
    if assignment is not None:
        save(base / 'assignment.json.gz', assignment)
        paths.append('assignment.json.gz')
    save(base / 'endpoint.json', {'key': folder.name, 'stage': stage, 'record': rec,
                                 'hashes': {p: sha(base / p) for p in paths}})
    return pointer.as_posix()


def worker(folder, token):
    folder = folder.resolve()
    attempt_dir = folder / 'attempts' / token
    plan = read(attempt_dir / 'plan.json')
    proc = psutil.Process()
    save(attempt_dir / 'identity.json', {'pid': proc.pid, 'created': proc.create_time()})
    last = None
    try:
        from solver import solve_stage
        spec = read(folder / 'spec.json')
        spec.update(plan['spec_overrides'])
        schedule, assignment = witness(folder, plan['source'], spec)
        spec.setdefault('cfg', schedule.get('config', {}))
        spec.setdefault('jobs', spec['n'])
        spec.setdefault('holding', spec['h'])

        def checkpoint(record, schedule, assignment):
            nonlocal last
            published = write_witness(folder, plan['stage'], record, schedule, assignment)
            epoch = time.time()
            if epoch <= plan['deadline']:
                last = published
                receipt = {'endpoint': last, 'epoch': epoch}
                save(attempt_dir / 'checkpoints' / (Path(last).parent.name + '.json'), receipt)
                save(attempt_dir / 'latest.json', receipt)

        # Leave time for the native return, independent validation and final atomics.
        available = plan['deadline'] - time.time()
        reserve = min(12., max(0., available * .05))
        deadline = time.monotonic() + max(0., available - reserve)
        result = solve_stage(plan['stage'], schedule, assignment, spec, deadline, checkpoint)
        checkpoint(*result)
        save(attempt_dir / 'finish.json', {'outcome': 'returned', 'endpoint': last, 'ended': time.time()})
    except KeyboardInterrupt:
        save(attempt_dir / 'finish.json', {'outcome': 'interrupted', 'endpoint': last, 'ended': time.time()})
        return 130
    except Exception:
        traceback.print_exc()
        save(attempt_dir / 'finish.json', {'outcome': 'error', 'endpoint': last, 'ended': time.time(),
                                          'detail': traceback.format_exc()[-4000:]})
        return 1
    return 0


@contextlib.contextmanager
def controller_lock(path):
    # Windows releases its file lock if the supervisor is interrupted or crashes.
    import msvcrt
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a+b') as stream:
        if not path.stat().st_size:
            stream.write(b'0')
            stream.flush()
        stream.seek(0)
        try:
            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            yield False
            return
        try:
            yield True
        finally:
            stream.seek(0)
            msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)


def dependencies():
    root = JMS.parent
    backend = JMS / 'model4_pjob_nonprocessing_20261103'
    sys.path.insert(0, str(backend))
    from joint_algorithms import policy_record
    policy = policy_record('proposed', 1)
    paths = [HERE / 'prepare_inputs.py',
             HERE.parent / 'stall_nodes_20261127/phases.py',
             HERE.parent / 'terminal_unload_20261125/extended_model.py',
             HERE.parent / 'terminal_unload_20261125/replay_events.py',
             HERE.parent / 'square_residence_20261125/score.py',
             HERE.parent / 'component_gap_restore_20261119/component.py',
             HERE.parent / 'sublevel_bounds_20261120/bounds.py',
             HERE.parent / 'manuscript_certified_gaps_20261119/design.py']
    paths += [backend / n for n in ('model.py', 'joint_algorithms.py', 'seed.py', 'physical_seed.py',
                                    'joint_pairing_model.py', 'joint_chamber_cycle_model.py',
                                    'physical_validate.py', 'validate.py', 'pjobs.py', 'pjob_order.py',
                                    'grippers.py')]
    paths += [root / n for n in ('scip_imports.py', 'cie/code/run_cie_benchmarks.py',
                                 'cie/results/repro_manifest/selected_checkpoint_manifest.csv',
                                 'cutsel_agent_parallel.py', 'pointer_net.py', 'pointer_net_end_token.py',
                                 'beam_search.py', 'utils.py')]
    paths += [Path(policy[k]) for k in ('checkpoint', 'config')]
    return {p.relative_to(root).as_posix(): sha(p) for p in paths}


def initialize(out, keys, jobs):
    from inputs import case_spec
    specs = {k: case_spec(k) for k in keys}
    manifest = {'version': 1, 'keys': keys, 'jobs': jobs,
                'resources': {'total_jobs_max': jobs, 'simultaneous_16_max': 1,
                              'mixed_admission_gib': MIXED_ADMISSION / GIB,
                              'mixed_pause_small_gib': MIXED_PAUSE / GIB, 'policy_device': 'cpu',
                              'min_available_gib': MEMORY_FLOOR / GIB,
                              'max_worker_rss_gib': PROCESS_LIMIT / GIB, 'worker_native_threads': 1},
                'budgets_A_total_seconds': {k: list(BUDGETS[k]) for k in keys},
                'scripts': {n: sha(HERE / n) for n in ('runner.py', 'solver.py', 'inputs.py')},
                'dependencies': dependencies(),
                'input_program_sources': next(iter(specs.values())).get('program_sources', {}),
                'case_preparation_sha256': {k: s.get('preparation_sha256') for k, s in specs.items()},
                'proof_sources': {k: s.get('proof_sources', []) for k, s in specs.items()},
                'software': {name: importlib.metadata.version(name) for name in
                             ('pyscipopt', 'scipy', 'numpy', 'torch', 'psutil')},
                'inputs': {k: s['input_sha256'] for k, s in specs.items()},
                'recovery': 'Verified stage endpoints and incumbent restarts; native search tree rebuilt. '
                            'Active workers adopted by PID/create-time and attempt token. Missed crash time '
                            'without an exit record is charged up to the attempt deadline.'}
    if (out / 'manifest.json').exists() and read(out / 'manifest.json') != manifest:
        raise RuntimeError('Run fingerprint/settings changed. Use a separate output directory.')
    save(out / 'manifest.json', manifest)
    cases = {}
    for k, spec in specs.items():
        folder = out / k
        if (folder / 'spec.json').exists() and read(folder / 'spec.json') != spec:
            raise RuntimeError(f'{k}: frozen case data differ')
        save(folder / 'spec.json', spec)
        path = folder / 'case.json'
        if path.exists():
            case = read(path)
            for p in {s['endpoint'] for s in case['stages'].values() if s.get('endpoint')}:
                load_endpoint(folder, p)
            if case['final_endpoint']:
                load_endpoint(folder, case['final_endpoint'])
        else:
            prep = spec.get('preparation_seconds', 0.)
            case = {'key': k, 'n': spec['n'], 'state': 'queued', 'stage': 'A', 'stages': {},
                    'budgets': {'latest_A_handoff_s': BUDGETS[k][0], 'case_wall_s': BUDGETS[k][1]},
                    'preparation_seconds': prep, 'elapsed_seconds': prep, 'stage_elapsed_seconds': prep,
                    'active': None, 'primary_cap': None, 'last_stage_endpoint': None,
                    'final_endpoint': None, 'recovery_endpoint': None, 'frontier': [],
                    'exclusive_after_memory_pause': False}
            save(path, case)
        cases[k] = case
    return cases


def stage_allowance(case):
    b = case['budgets']
    if case['stage'] == 'A':
        return b['latest_A_handoff_s'] - case['elapsed_seconds']
    if case['stage'] == 'B3':
        return b['case_wall_s'] - case['elapsed_seconds']
    share = .10 if case['stage'] == 'B1' else .60
    return min(b['case_wall_s'] - case['elapsed_seconds'],
               share * case['B_budget'] - case['stage_elapsed_seconds'])


def launch(folder, case):
    token = uuid.uuid4().hex
    stage = case['stage']
    allowance = max(0., stage_allowance(case))
    start = time.time()
    active = {'token': token, 'started': start, 'deadline': start + allowance}
    base = folder / 'attempts' / token
    changes = {} if case['primary_cap'] is None else {'primary_cap': case['primary_cap']}
    source = case['recovery_endpoint'] or case['last_stage_endpoint']
    if stage == 'A':
        changes['spbs_seconds'] = max(0., 60. - case['stage_elapsed_seconds'] + case['preparation_seconds'])
    if source:
        previous = load_endpoint(folder, source)['record']
        if stage == 'A' and previous.get('spbs_completed'):
            changes['spbs_seconds'] = 0.
        if (stage == 'A') == (previous['stage'] == 'A'):
            bound = previous.get('global_lower')
            if bound is not None and math.isfinite(bound):
                name = 'lb_A' if stage == 'A' else 'lb_B'
                original = read(folder / 'spec.json').get(name)
                changes[name] = max(bound, original) if original is not None else bound
    plan = dict(active, stage=stage, source=source,
                spec_overrides=changes)
    save(base / 'plan.json', plan)
    case.update(active=active, state='running')
    save(folder / 'case.json', case)
    env = os.environ.copy()
    env.update({k: '1' for k in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS',
                                 'NUMEXPR_NUM_THREADS', 'BLIS_NUM_THREADS')})
    with (base / 'worker.log').open('ab') as log:
        p = subprocess.Popen([sys.executable, '-u', str(HERE / 'runner.py'), 'worker', str(folder), token],
                             cwd=HERE, env=env, stdout=log, stderr=subprocess.STDOUT)
    proc = psutil.Process(p.pid)
    save(base / 'identity.json', {'pid': proc.pid, 'created': proc.create_time()})
    return proc


def process_for(folder, a):
    identity = folder / 'attempts' / a['token'] / 'identity.json'
    if identity.exists():
        i = read(identity)
        try:
            p = psutil.Process(i['pid'])
            if abs(p.create_time() - i['created']) < .01 and a['token'] in p.cmdline():
                return p
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    return None


def stop_owned(proc):
    if proc is None:
        return
    try:
        proc.kill()
        proc.wait(timeout=5)
    except psutil.NoSuchProcess:
        pass


def archive(folder, case, pointer):
    if not pointer:
        return
    metrics = read(folder / pointer)['record']['metrics']
    c, b = metrics['cmax'], metrics['secondary']
    points = case['frontier']
    if any(p['cmax'] <= c and p['secondary'] <= b and (p['cmax'], p['secondary']) != (c, b)
           for p in points):
        return
    shortest = min([c] + [p['cmax'] for p in points])
    if c > shortest + EPS:
        return
    points[:] = [p for p in points if p['cmax'] <= shortest + EPS and
                 not (c <= p['cmax'] and b <= p['secondary'])]
    points.append(dict(endpoint=pointer, cmax=c, secondary=b))
    case['shortest_cmax'] = shortest
    case['final_endpoint'] = min(points, key=lambda p: (p['secondary'], p['cmax']))['endpoint']


def complete_stage(folder, case, rec, pointer, reason, detail=None):
    stage = case['stage']
    certified = bool(rec and rec.get('certified_global') is True)
    case['stages'][stage] = {'endpoint': pointer, 'stop_reason': reason,
                             'elapsed_seconds': case['stage_elapsed_seconds'],
                             'certified_global': certified, 'detail': detail}
    if pointer:
        archive(folder, case, pointer)
        case['last_stage_endpoint'] = pointer
    case['recovery_endpoint'] = None
    case['stage_elapsed_seconds'] = 0.
    if reason in ('worker_error', 'worker_lost') or not case['final_endpoint']:
        case['state'] = 'failed'
        return
    if stage == 'A':
        incumbent = load_endpoint(folder, case['final_endpoint'])['record']
        case['primary_cap'] = incumbent['metrics']['cmax']
        case['last_stage_endpoint'] = case['final_endpoint']
        case['B_budget'] = max(0., case['budgets']['case_wall_s'] - case['elapsed_seconds'])
    if (stage != 'A' and certified) or stage == 'B3':
        case['state'] = 'completed'
    else:
        case.update(state='queued', stage=STAGES[STAGES.index(stage) + 1])


def settle(folder, case, proc, reason=None):
    a = case['active']
    base = folder / 'attempts' / a['token']
    if reason:
        stop_owned(proc)
    finish = read(base / 'finish.json') if (base / 'finish.json').exists() else None
    if finish and finish['ended'] > a['deadline'] and reason != 'paused':
        reason = 'wall_limit'
    natural = finish is not None and reason is None
    ended = finish['ended'] if finish else time.time()
    charged = min(max(0., ended - a['started']), a['deadline'] - a['started'])
    case['elapsed_seconds'] += charged
    case['stage_elapsed_seconds'] += charged
    latest = read(base / 'latest.json') if (base / 'latest.json').exists() else None
    # A solver may finish writing just after the hard deadline on an unattended orphan.
    # Only the last candidate whose publication preceded that deadline may enter results.
    pointer = latest['endpoint'] if latest and latest['epoch'] <= a['deadline'] else None
    receipts = [read(path) for path in (base / 'checkpoints').glob('*.json')]
    for receipt in sorted(receipts, key=lambda x: x['epoch']):
        if receipt['epoch'] <= a['deadline']:
            archive(folder, case, receipt['endpoint'])
            pointer = receipt['endpoint']
    pointer = pointer or case['recovery_endpoint']
    rec = load_endpoint(folder, pointer)['record'] if pointer else None
    outcome = finish['outcome'] if natural else None
    if outcome == 'interrupted':
        reason = 'paused'
    if outcome == 'error':
        reason = 'worker_error'
    if outcome == 'returned' and rec:
        reason = rec['stop_reason']
    reason = reason or 'worker_lost'
    case['active'] = None
    save(base / 'accounting.json', {'charged_seconds': charged, 'reason': reason, 'endpoint': pointer})
    if reason in ('paused', 'memory_pause'):
        case.update(state='queued', recovery_endpoint=pointer)
        if reason == 'memory_pause':
            case['exclusive_after_memory_pause'] = True
    else:
        complete_stage(folder, case, rec, pointer, reason, (finish or {}).get('detail'))
    save(folder / 'case.json', case)


def effective(case, now):
    a = case['active']
    return case['elapsed_seconds'] + (max(0., min(now, a['deadline']) - a['started']) if a else 0.)


def expected_left(cases, jobs, now):
    t = 0.
    pending = [c for c in cases.values() if c['state'] not in DONE and not c['active']]
    running = [(max(0., c['budgets']['case_wall_s'] - effective(c, now)), c)
               for c in cases.values() if c['active']]
    available = psutil.virtual_memory().available
    while running or pending:
        for c in list(pending):
            if len(running) < jobs and compatible(c, [e[1] for e in running], available):
                running.append((t + max(0., c['budgets']['case_wall_s'] - effective(c, now)), c))
                pending.remove(c)
        if running:
            t = min(e[0] for e in running)
            running = [e for e in running if e[0] > t]
    return t


def compatible(case, running, available):
    if not running:
        return True
    others_large = any(r['n'] >= 16 for r in running)
    if case['exclusive_after_memory_pause'] or any(r['exclusive_after_memory_pause'] for r in running):
        return False
    if case['n'] >= 16 and others_large:
        return False
    floor = MIXED_ADMISSION if others_large or case['n'] >= 16 else 12 * GIB
    return available >= floor


def report(out, cases, jobs, elapsed, now, mode):
    left = expected_left(cases, jobs, now)
    summary = {k: {'state': c['state'], 'stage': c['stage'], 'elapsed_seconds': effective(c, now),
                   'case_wall_s': c['budgets']['case_wall_s'],
                   'remaining_allowance_s': max(0., c['budgets']['case_wall_s'] - effective(c, now)),
                   'active_stage_deadline': timestamp(c['active']['deadline']) if c['active'] else None,
                   'final_endpoint': c['final_endpoint']}
               for k, c in cases.items()}
    counts = {s: sum(c['state'] == s for c in cases.values()) for s in DONE}
    status = {'mode': mode, 'updated': timestamp(now), 'summary': summary, 'counts': counts,
              'elapsed_seconds': elapsed, 'estimated_remaining_seconds': left,
              'estimated_total_seconds': elapsed + left, 'projected_finish': timestamp(now + left),
              'estimate_basis': 'Remaining declared wall allowances and current memory-based '
                                'admission; at most one 16-wafer case. Proofs can finish sooner.',
              'historical_context': {'exact_protocol_history': False,
                  'n8_A_old_one_percent_H3_seed1_censored_seconds': 19598.5,
                  'source': 'results/table4_one_percent_20261124/progress.json',
                  'difference': 'Older one-percent run, different model and warm start, observed unfinished.'}}
    save(out / 'status.json', status)
    active = ', '.join(f"{k}/{c['stage']} {duration(effective(c, now))}"
                       for k, c in cases.items() if c['active']) or '-'
    print(f"[{status['updated']}] {mode} | done {counts['completed']}/{len(cases)} "
          f"failed {counts['failed']} | {active} | elapsed {duration(elapsed)} "
          f"total~{duration(elapsed + left)} left~{duration(left)} (budget projection)", flush=True)


def controller(out, keys, jobs, retry_failed=False):
    with controller_lock(out / 'controller.lock') as locked:
        if not locked:
            print('The foreground controller already holds this output. See status.json.', flush=True)
            return 0
        cases = initialize(out, keys, jobs)
        if retry_failed:
            for key, case in cases.items():
                if case['state'] == 'failed':
                    stage = case['stage']
                    prior_stage = case['stages'][stage]
                    case.setdefault('failed_stage_history', []).append(dict(stage=stage, **prior_stage))
                    case.update(state='queued', stage_elapsed_seconds=prior_stage['elapsed_seconds'],
                                recovery_endpoint=prior_stage['endpoint'])
                    save(out / key / 'case.json', case)
        previous = read(out / 'status.json') if (out / 'status.json').exists() else {}
        now = time.time()
        prior = previous.get('elapsed_seconds', 0.)
        # Count unattended work while a surviving worker ran without its controller.
        if previous.get('mode') == 'running':
            previous_at = dt.datetime.fromisoformat(previous['updated']).timestamp()
            last_work = previous_at
            for k, case in cases.items():
                a = case['active']
                if a:
                    done = out / k / 'attempts' / a['token'] / 'finish.json'
                    last_work = max(last_work, min(now, a['deadline'],
                                                 read(done)['ended'] if done.exists() else now))
            prior += max(0., last_work - previous_at)
        origin = time.monotonic()
        procs = {}
        pending_since = {}
        last_report = 0.
        try:
            while any(c['state'] not in DONE for c in cases.values()):
                if (out / 'pause.request').exists():
                    (out / 'pause.request').unlink()
                    raise KeyboardInterrupt
                changed = False
                large_active = any(c['active'] and c['n'] >= 16 for c in cases.values())
                for key, c in cases.items():
                    a, folder = c['active'], out / key
                    if not a:
                        continue
                    proc = procs.get(key) or process_for(folder, a)
                    if proc:
                        procs[key] = proc
                    finished = (folder / 'attempts' / a['token'] / 'finish.json').exists()
                    try:
                        alive = proc is not None and proc.is_running() and proc.status() != psutil.STATUS_ZOMBIE
                        over = alive and (proc.memory_info().rss >= PROCESS_LIMIT or
                                          psutil.virtual_memory().available < MEMORY_FLOOR)
                    except psutil.NoSuchProcess:
                        alive = over = False
                    if finished:
                        settle(folder, c, proc)
                    elif time.time() >= a['deadline']:
                        settle(folder, c, proc, 'wall_limit')
                    elif (large_active and c['n'] < 16 and alive and
                          psutil.virtual_memory().available < MIXED_PAUSE):
                        settle(folder, c, proc, 'memory_pause')
                    elif over:
                        settle(folder, c, proc, 'memory_limit')
                    elif not alive and time.time() - a['started'] > 10.:
                        # Unexpected supervisor/worker crashes may be resumed from latest checkpoint.
                        attempts = folder / 'attempts'
                        lost = sum(read(p).get('reason') == 'lost_restart' for p in attempts.glob('*/accounting.json'))
                        settle(folder, c, proc, 'paused' if lost < 2 else 'worker_lost')
                        if lost < 2:
                            path = attempts / a['token'] / 'accounting.json'
                            info = read(path)
                            save(path, dict(info, reason='lost_restart'))
                    else:
                        continue
                    procs.pop(key, None)
                    if c['state'] == 'queued' and not c['exclusive_after_memory_pause']:
                        # Count controller dispatch/validation between phases of a live case.
                        pending_since[key] = time.monotonic()
                    changed = True
                running = [c for c in cases.values() if c['active']]
                for key, c in cases.items():
                    if c['state'] != 'queued' or len(running) >= jobs:
                        continue
                    if not compatible(c, running, psutil.virtual_memory().available):
                        continue
                    if key in pending_since:
                        dispatch = max(0., time.monotonic() - pending_since.pop(key))
                        c['elapsed_seconds'] += dispatch
                        c['stage_elapsed_seconds'] += dispatch
                    if stage_allowance(c) <= .1:
                        pointer = c['recovery_endpoint']
                        rec = load_endpoint(out / key, pointer)['record'] if pointer else None
                        complete_stage(out / key, c, rec, pointer, 'wall_limit')
                        save(out / key / 'case.json', c)
                    else:
                        procs[key] = launch(out / key, c)
                        running.append(c)
                    changed = True
                if changed or time.monotonic() - last_report >= 10:
                    report(out, cases, jobs, prior + time.monotonic() - origin, time.time(), 'running')
                    last_report = time.monotonic()
                if any(c['state'] not in DONE for c in cases.values()):
                    time.sleep(1.)
        except KeyboardInterrupt:
            for key, c in cases.items():
                if c['active']:
                    settle(out / key, c, procs.get(key) or process_for(out / key, c['active']), 'paused')
            report(out, cases, jobs, prior + time.monotonic() - origin, time.time(), 'paused')
            return 130
        failed = any(c['state'] == 'failed' for c in cases.values())
        audit_failed = False
        if not failed and set(keys) == set(BUDGETS):
            audit = subprocess.run([sys.executable, str(HERE / 'campaign_audit.py'),
                                    '--output', str(out), '--require-complete'], check=False)
            audit_failed = audit.returncode != 0
        mode = 'failed' if failed else ('audit_failed' if audit_failed else 'finished')
        report(out, cases, jobs, prior + time.monotonic() - origin, time.time(), mode)
        return int(failed or audit_failed)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    run = sub.add_parser('run')
    run.add_argument('--output', type=Path, default=DEFAULT_OUT)
    run.add_argument('--jobs', type=int, choices=(1, 2), default=2)
    run.add_argument('--retry-failed', action='store_true')
    run.add_argument('--cases', nargs='+', choices=BUDGETS, default=list(BUDGETS))
    status = sub.add_parser('status')
    status.add_argument('--output', type=Path, default=DEFAULT_OUT)
    pause = sub.add_parser('pause')
    pause.add_argument('--output', type=Path, default=DEFAULT_OUT)
    subworker = sub.add_parser('worker')
    subworker.add_argument('folder', type=Path)
    subworker.add_argument('token')
    args = parser.parse_args()
    if args.command == 'worker':
        return worker(args.folder, args.token)
    if args.command == 'status':
        print(json.dumps(read(args.output / 'status.json'), indent=2))
        return 0
    if args.command == 'pause':
        if read(args.output / 'status.json')['mode'] == 'running':
            (args.output / 'pause.request').touch()
            print('Requested a checkpointed pause in the foreground controller.')
        return 0
    return controller(args.output.resolve(), list(dict.fromkeys(args.cases)), args.jobs, args.retry_failed)


if __name__ == '__main__':
    sys.exit(main())

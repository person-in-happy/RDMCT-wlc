"""Preregistered supplements: serial reference gates, foreground runs, safe resume.

Does not change existing models, launchers, checkpoints or historical campaigns.
Resume is between cells, NOT a SCIP search-tree checkpoint.
"""
from pathlib import Path
from dataclasses import asdict
from types import SimpleNamespace
from datetime import datetime, timezone
import argparse
import hashlib
import json
import math
import os
import subprocess
import sys
import time
import platform
import shutil
from importlib.metadata import version

ROOT = Path(__file__).resolve().parents[2]
JOINT = Path(__file__).resolve().parent
sys.path.insert(0, str(JOINT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from revalidate import (plan, inventory, verify, prepare_reference, metrics,
                        VARIANTS, read)
from run_experiments import dump, digest, ports, assets
from joint_algorithms import policy_record
from model import Config
from validate import validate
from run_matched_supplement import output_lock
from experiment_console import ensure_idle

CONSOLE = Path(__file__).with_name('experiment_console.py')
SUITES = ('fixed', 'mode24', 'scale32', 'gantt16', 'rhythm', 'cleaning', 'doe', 'ood')


def stamp():
    return datetime.now(timezone.utc).isoformat()


def environment_record():
    import psutil
    return dict(platform=platform.platform(), processor=platform.processor(),
                logical_cpus=psutil.cpu_count(), physical_cpus=psutil.cpu_count(logical=False),
                total_ram_bytes=psutil.virtual_memory().total, python_version=sys.version,
                packages={name: version(name) for name in ('pyscipopt', 'psutil', 'torch', 'numpy')})


def matrix(suite):
    """Fixed in advance; never select cases using observed objective values."""
    cases, pairs = {}, []
    def add(key, cfg, arms):
        cases[key] = asdict(cfg)
        pairs.extend((key, arm) for arm in arms)
    if suite == 'fixed':
        source, _ = plan('core')
        for h in (3, 10):
            key = f'n4_H{h}_mixed_dual'
            add(key, Config(**source[key]), ('joint', 'fixed'))
    elif suite in ('mode24', 'scale32', 'gantt16', 'doe', 'ood'):
        base = {'mode24': 'crossover', 'scale32': 'scale', 'gantt16': 'crossover'}.get(suite, suite)
        source, original = plan(base)
        for key, arm in original:
            keep = (suite in ('doe', 'ood') or
                    suite == 'mode24' and key.startswith('n24_') or
                    suite == 'scale32' and key.startswith('n32_') or
                    suite == 'gantt16' and key in {
                        f'n16_H{h}_{recipe}_dual' for h in (3, 10) for recipe in ('4x1', '2x2')})
            if keep:
                cases[key] = source[key]
                pairs.append((key, arm))
    elif suite == 'rhythm':
        # Eight pure-2x2 products produce overlapping exposure triples in the
        # deterministic two-chamber reference. Verify this again after SPBS.
        for source in ('single', 'dual'):
            for h in (5, 10):
                key = f'n8_H{h}_2x2_{source}'
                add(key, Config(ports(8, '2x2'), source=source, cleaning_interval=h),
                    ('joint', 'refined', 'waiting_only', 'quadratic'))
    elif suite == 'cleaning':
        for n in (4, 6):
            for recipe in ('mixed', '2x2'):
                for h in (3, 4):
                    for duration in (100, 500):
                        key = f'n{n}_H{h}_{recipe}_dual_clean{duration}'
                        add(key, Config(ports(n, recipe), cleaning_interval=h, cleaning_time=duration),
                            ('joint', 'legacy'))
    else:
        raise ValueError(suite)
    return cases, pairs


def defaults(suite):
    large = suite in ('mode24', 'scale32', 'gantt16', 'doe', 'ood')
    return dict(memory_mb=24000 if large else 6000, jobs=1 if large else 2,
                time_limit=7200 if suite == 'gantt16' else 300,
                wall_limit=14400 if suite == 'gantt16' else 3600 if large else 1800,
                spbs_budget=0 if suite == 'cleaning' else 300 if suite == 'gantt16' else 20,
                seeds=[1] if suite == 'gantt16' else [1, 2, 3])


def campaign_path(value):
    path = Path(value).resolve()
    allowed = (ROOT / 'JMS-version/results').resolve()
    if path == allowed or not path.is_relative_to(allowed):
        raise ValueError('Use a new subdirectory of JMS-version/results')
    return path


def prepare(args):
    out = campaign_path(args.campaign)
    d = defaults(args.suite)
    for key in ('memory_mb', 'jobs'):
        if getattr(args, key) is not None:
            d[key] = getattr(args, key)
    cases, pairs = matrix(args.suite)
    cells = [dict(id=f'{key}__s{seed}__{arm}', case=key, seed=seed, variant=arm)
             for seed in d['seeds'] for key, arm in pairs]
    if any(c['max_pairs'] or c['max_cycles'] for c in cases.values()):
        raise ValueError('Restricted candidates are not allowed')
    contract = dict(schema=1, suite=args.suite, settings=d, reserve_mb=2048,
                    gpu_slots=1, threads_per_worker=1, python=sys.executable,
                    launcher_sha256=digest(Path(__file__)), console_sha256=digest(CONSOLE),
                    environment=environment_record(),
                    objective='product_return_Cmax',
                    scope='New protocol; no pooling with old budgets or promotion of old failures',
                    resume='Skip audited completed cells; restart interrupted cells, no search-tree resume')
    if out.exists():
        if read(out / 'supplement.json')['contract'] != contract:
            raise RuntimeError('Protocol changed. Use a NEW output directory.')
        checked(out)
        print('REUSE frozen preparation: ' + str(out))
        return
    out.mkdir(parents=True)
    (out / 'configs').mkdir()
    for key, cfg in cases.items():
        dump(out / 'configs' / (key + '.json'), cfg)
    methods = {VARIANTS[arm]['method'] for _, arm in pairs}
    spec = dict(schema=1, suite=args.suite, created_utc=stamp(), assets=inventory(),
                policies={m: policy_record(m, 1) for m in methods}, training_seed=1,
                **{k: v for k, v in d.items() if k != 'jobs'}, cut_profile='standard',
                case_hashes={k: digest(out / 'configs' / (k + '.json')) for k in cases},
                cells=cells, accounting='Main solve or 90% primary + 10% refinement; offline preparation separate')
    dump(out / 'campaign.json', spec)
    dump(out / 'supplement.json', dict(contract=contract, campaign_sha256=digest(out / 'campaign.json')))
    for relative in list(spec['assets']) + [str(Path(__file__).relative_to(ROOT)), str(CONSOLE.relative_to(ROOT))]:
        snapshot = out / 'frozen_code' / relative
        snapshot.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / relative, snapshot)
    print(json.dumps(dict(campaign=str(out), cases=len(cases), cells=len(cells), settings=d)))


def checked(out):
    meta = read(out / 'supplement.json')
    c = meta['contract']
    if (c['launcher_sha256'] != digest(Path(__file__)) or
            c['console_sha256'] != digest(CONSOLE) or c['python'] != sys.executable or
            c['environment'] != environment_record() or
            meta['campaign_sha256'] != digest(out / 'campaign.json')):
        raise RuntimeError('Frozen launcher, interpreter or manifest changed; use a new campaign')
    return verify(out), c


def no_other_queue():
    import psutil
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        if proc.pid == os.getpid():
            continue
        try:
            if 'python' not in (proc.info['name'] or '').lower():
                continue
            cmd = proc.info['cmdline']
            if cmd is None:
                raise RuntimeError(f'Cannot inspect Python PID {proc.pid}')
            runners = {'revalidate.py', 'experiment_console.py', 'evidence_supplement.py',
                       'run_experiments.py', 'run_matched_supplement.py'}
            if any(Path(a).name in runners for a in cmd) and any(
                    a in ('start', 'run', 'resume', 'preflight', 'worker', '_reference', 'solve') for a in cmd):
                raise RuntimeError(f'Another experiment queue/worker is active: PID {proc.pid}')
        except (psutil.NoSuchProcess, psutil.ZombieProcess):
            continue


def reference_receipt(out, key, spec):
    folder = out / 'references' / key
    cert = read(folder / 'certificate.json')
    if not cert['valid']:
        raise RuntimeError('Reference certificate failed: ' + key)
    for name, sha in cert['files'].items():
        if digest(folder / name) != sha:
            raise RuntimeError('Reference changed: ' + key)
    result = read(folder / 'reference.json')
    if not validate(result)['valid'] or result.get('restricted_candidate_bounds') is not False:
        raise RuntimeError('Reference is invalid or restricted: ' + key)
    measured = metrics(result)
    if spec['suite'] == 'rhythm' and measured['rhythm_centers'] <= 0:
        raise RuntimeError('No effective rhythm center; batch is NOT ready: ' + key)
    if spec['suite'] == 'cleaning' and not measured['legacy_rule_feasible']:
        raise RuntimeError('Common start is not feasible for BOTH cleaning rules: ' + key)
    return dict(certificate_sha256=digest(folder / 'certificate.json'), metrics=measured)


def preflight(out):
    import psutil
    no_other_queue()
    with output_lock(out):
        spec, contract = checked(out)
        required = spec['memory_mb'] * 1.15 * contract['settings']['jobs'] + contract['reserve_mb']
        if psutil.virtual_memory().available / 1024**2 < required:
            raise RuntimeError(f'Preflight needs {required:.0f} MiB available RAM; close other workloads or use another host')
        (out / 'preflight_logs').mkdir(exist_ok=True)
        for index, key in enumerate(spec['case_hashes'], 1):
            if (out / 'references' / key / 'certificate.json').exists():
                reference_receipt(out, key, spec)
                print(f'REUSE reference {index}/{len(spec["case_hashes"])} {key}', flush=True)
                continue
            previous = out / 'preflight_logs' / (key + '.failure.json')
            if previous.exists() and read(previous)['reason'] != 'foreground_interrupted':
                raise RuntimeError('Known failed preflight retained; diagnose it before a NEW protocol: ' + str(previous))
            logpath = out / 'preflight_logs' / (key + '_' + str(time.time_ns()) + '.log')
            print(f'PREPARE reference {index}/{len(spec["case_hashes"])} {key}', flush=True)
            start = time.monotonic()
            peak = 0
            with logpath.open('wb') as log:
                env = os.environ.copy()
                env.update(OMP_NUM_THREADS='1', MKL_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1')
                proc = subprocess.Popen([sys.executable, '-u', str(Path(__file__)), '_reference',
                                         '--campaign', str(out), '--case', key], cwd=ROOT,
                                        stdout=log, stderr=subprocess.STDOUT, env=env)
                reason = None
                try:
                    last = 0
                    while proc.poll() is None:
                        try:
                            rss = psutil.Process(proc.pid).memory_info().rss / 1024**2
                        except psutil.NoSuchProcess:
                            rss = 0
                        peak = max(peak, rss)
                        elapsed = time.monotonic() - start
                        if rss > spec['memory_mb'] * 1.15:
                            reason = 'process_memory_guard'
                        elif elapsed > spec['wall_limit']:
                            reason = 'reference_wall_guard'
                        if reason:
                            proc.terminate()
                            proc.wait(timeout=30)
                            break
                        if elapsed - last >= 15:
                            print(f'  elapsed={elapsed:.0f}s RSS={rss:.0f}MiB; serial reference preparation', flush=True)
                            last = elapsed
                        time.sleep(1)
                except BaseException:
                    if proc.poll() is None:
                        proc.terminate()
                        proc.wait(timeout=30)
                    dump(previous, dict(reason='foreground_interrupted', log=str(logpath), at_utc=stamp()))
                    raise
            if proc.returncode != 0:
                dump(previous, dict(reason=reason or f'exit_{proc.returncode}', log=str(logpath),
                                    sampled_peak_rss_mb=peak, at_utc=stamp()))
                raise RuntimeError('Preflight failed; batch NOT started. Inspect ' + str(logpath))
            reference_receipt(out, key, spec)
        receipts = {key: reference_receipt(out, key, spec) for key in spec['case_hashes']}
        dump(out / 'preflight_passed.json', dict(campaign_sha256=digest(out / 'campaign.json'),
                                               references=receipts, completed_utc=stamp()))
        print('REFERENCE GATE PASSED. This does not certify main-solve performance or optimality.')


def eligible_interruption(failure):
    return failure.get('reason') == 'foreground_interrupted'


def check_cell(out, cell):
    folder = out / 'runs' / cell['id']
    evidence = read(folder / 'evidence.json')
    result = read(folder / 'result.json')
    primary = read(folder / 'phase1.json')
    manifest = read(folder / 'manifest.json')
    spec = read(out / 'campaign.json')
    arm = VARIANTS[cell['variant']]
    if not evidence['complete'] or digest(folder / 'result.json') != evidence['result_sha256']:
        raise RuntimeError('Incomplete or changed evidence: ' + cell['id'])
    if (manifest['seed'] != cell['seed'] or manifest['method'] != arm['method'] or
            manifest['config'] != read(out / 'configs' / (cell['case'] + '.json')) or
            manifest['assets'] != assets() or
            manifest['time_limit'] != spec['time_limit'] * (.9 if arm.get('refine') else 1) or
            manifest['stage2_limit'] != spec['time_limit'] * (.1 if arm.get('refine') else 0)):
        raise RuntimeError('Run protocol mismatch: ' + cell['id'])
    if digest(folder / 'model.lp.gz') != manifest['lp_sha256']:
        raise RuntimeError('Model hash mismatch: ' + cell['id'])
    if result.get('restricted_candidate_bounds'):
        raise RuntimeError('Restricted candidates: ' + cell['id'])
    physical = validate(result)
    has = bool(result.get('solutions'))
    if has and not (evidence['original_model_check'] and result['original_model_check'] and physical['valid']):
        raise RuntimeError('Failed feasibility: ' + cell['id'])
    if has and read(folder / 'variables.json')['model_sha256'] != manifest['lp_sha256']:
        raise RuntimeError('Assignment model mismatch: ' + cell['id'])
    measured = metrics(result) if has else {}
    if has and arm.get('cleaning_rule') == 'legacy' and not measured['legacy_rule_feasible']:
        raise RuntimeError('Legacy replay failed: ' + cell['id'])
    ref = out / 'references' / cell['case']
    reference_receipt(out, cell['case'], spec)
    if (evidence['common_warm_sha256'] != digest(ref / 'common.json') or
            manifest['warm_start_sha256'] != digest(ref / 'common.json') or
            not read(folder / 'warm_start_check.json')['accepted']):
        raise RuntimeError('Common warm start mismatch: ' + cell['id'])
    bound = result.get('primary_bound')
    if not isinstance(bound, (int, float)) or not math.isfinite(bound) or abs(bound) >= 1e19:
        bound = None
    if has and bound is not None and bound > physical['product_return_cmax'] + 2e-4:
        raise RuntimeError('Lower bound exceeds validated upper bound: ' + cell['id'])
    return dict(**cell, status=primary['status'], has_solution=has,
                upper=physical.get('product_return_cmax') if has else None, lower=bound,
                gap=result.get('primary_gap'), full_candidate_space=result.get('full_candidate_space', False),
                metrics=measured, phase1_metrics=metrics(primary) if primary.get('solutions') else {},
                warm_sha256=evidence['common_warm_sha256'],
                primary_assignment_sha256=digest(folder / 'variables_phase1.json') if has else None,
                hashes={name: digest(folder / name) for name in
                        ('result.json', 'phase1.json', 'evidence.json', 'manifest.json', 'model.lp.gz')})


def run(out, resume=False):
    no_other_queue()
    # A separate controller lock spans handoff to the unchanged console lock.
    with output_lock(out / 'controller'):
        spec, contract = checked(out)
        ensure_idle(out)
        gate = read(out / 'preflight_passed.json')
        if gate['campaign_sha256'] != digest(out / 'campaign.json'):
            raise RuntimeError('Reference gate belongs to a different protocol')
        for key in spec['case_hashes']:
            if reference_receipt(out, key, spec) != gate['references'][key]:
                raise RuntimeError('Reference gate changed: ' + key)
        if resume:
            # Never retry a memory guard, validation failure or time limit as an interruption.
            for cell in spec['cells']:
                dest = out / 'runs' / cell['id']
                if (dest / 'evidence.json').exists():
                    check_cell(out, cell)
                elif (dest / 'failure.json').exists() and eligible_interruption(read(dest / 'failure.json')):
                    archive = out / 'interrupted_attempts' / (cell['id'] + '_resume_' + str(time.time_ns()))
                    if dest.is_symlink() or not dest.resolve().is_relative_to(out):
                        raise RuntimeError('Unsafe interrupted path')
                    archive.parent.mkdir(exist_ok=True)
                    dest.rename(archive)
                    print('PRESERVED interruption ' + str(archive), flush=True)
        else:
            for cell in spec['cells']:
                if (out / 'runs' / cell['id'] / 'evidence.json').exists():
                    check_cell(out, cell)
        # Recover the narrow crash window between evidence write and supervisor
        # progress write; preserve the old supervisor snapshot for auditing.
        progress_path = out / 'progress.json'
        if progress_path.exists():
            progress = read(progress_path)
            recovered = []
            for cell in spec['cells']:
                evidence_path = out / 'runs' / cell['id'] / 'evidence.json'
                entry = progress.get('cells', {}).get(cell['id'], {})
                if evidence_path.exists() and entry.get('state') != 'complete':
                    evidence = read(evidence_path)
                    entry.update(state='complete', ended_utc=evidence['completed_utc'],
                                 completion_source='verified_saved_evidence')
                    entry.setdefault('started_utc', evidence['completed_utc'])
                    progress.setdefault('cells', {})[cell['id']] = entry
                    recovered.append(cell['id'])
            if recovered:
                transitions = out / 'controller' / ('recovery_' + str(time.time_ns()))
                transitions.mkdir()
                dump(transitions / 'progress.before.json', read(progress_path))
                dump(transitions / 'recovered.json', recovered)
                dump(progress_path, progress)
        command = [sys.executable, '-u', str(CONSOLE), 'run', '--campaign', str(out),
                   '--jobs', str(contract['settings']['jobs']), '--gpu-slots', '1',
                   '--reserve-mb', str(contract['reserve_mb'])]
        code = subprocess.call(command, cwd=ROOT)
        if code:
            raise RuntimeError(f'Foreground console exited {code}; inspect saved state')
        report = audit(out)
        if not report['coverage_complete']:
            raise RuntimeError('Queue ended with failed or pending cells. Audit retained; do not silently retry failures.')


def certified_optimal(row):
    return bool(row.get('has_solution') and row.get('full_candidate_space') and
                row['status'] == 'optimal' and row.get('lower') is not None and
                abs(row['upper'] - row['lower']) <= 2e-4 and
                row.get('gap') is not None and 0 <= row['gap'] <= 1e-6)


def audit(out):
    spec, _ = checked(out)
    rows, missing = [], []
    for cell in spec['cells']:
        dest = out / 'runs' / cell['id']
        if (dest / 'evidence.json').exists():
            rows.append(check_cell(out, cell))
        else:
            missing.append(cell | dict(failure=read(dest / 'failure.json') if (dest / 'failure.json').exists() else 'pending'))
    by = {(r['case'], r['seed'], r['variant']): r for r in rows}
    comparisons = []
    for r in rows:
        if r['variant'] != 'joint' or not r['has_solution']:
            continue
        for variant in ('fixed', 'legacy', 'refined', 'waiting_only', 'quadratic', 'hem', 'proposed'):
            other = by.get((r['case'], r['seed'], variant))
            if not other or not other['has_solution']:
                continue
            rec = dict(case=r['case'], seed=r['seed'], arm=variant,
                       arm_minus_joint_cmax=other['upper'] - r['upper'],
                       same_warm_start=other['warm_sha256'] == r['warm_sha256'])
            if variant in ('fixed', 'legacy'):
                rec['strict_benefit_certified'] = bool(other['lower'] is not None and r['upper'] < other['lower'] - 2e-4)
            if variant in ('refined', 'waiting_only', 'quadratic'):
                rec.update(wait_reduction=r['metrics']['route_wait_sum'] - other['metrics']['route_wait_sum'],
                           rhythm_reduction=r['metrics']['rhythm_deviation'] - other['metrics']['rhythm_deviation'],
                           effective_rhythm=other['metrics']['rhythm_centers'] > 0 and r['metrics']['rhythm_centers'] > 0,
                           cmax_preserved=abs(other['upper'] - r['upper']) <= 2e-4)
            comparisons.append(rec)
    rhythm_pairs = []
    if spec['suite'] == 'rhythm':
        for (case, seed, variant), base in by.items():
            if variant != 'waiting_only' or not base['has_solution']:
                continue
            for arm in ('refined', 'quadratic'):
                other = by.get((case, seed, arm))
                if not other or not other['has_solution']:
                    continue
                eligible = (base['primary_assignment_sha256'] == other['primary_assignment_sha256'] and
                            base['metrics']['rhythm_centers'] > 0 and other['metrics']['rhythm_centers'] > 0 and
                            abs(base['upper'] - other['upper']) <= 2e-4)
                rhythm_pairs.append(dict(case=case, seed=seed, arm=arm, controlled_comparison=eligible,
                    rhythm_reduction=base['metrics']['rhythm_deviation'] - other['metrics']['rhythm_deviation'],
                    wait_change=other['metrics']['route_wait_sum'] - base['metrics']['route_wait_sum']))
    winners = []
    if spec['suite'] == 'mode24':
        for h in range(3, 11):
            for seed in spec['seeds']:
                group = [by.get((f'n24_H{h}_{recipe}_dual', seed, 'joint')) for recipe in ('4x1', '2x2', 'mixed')]
                for candidate in group:
                    if candidate and candidate['has_solution'] and all(
                            other and other['lower'] is not None and candidate['upper'] < other['lower'] - 2e-4
                            for other in group if other is not candidate):
                        winners.append(candidate['id'])
    report = dict(created_utc=stamp(), expected=len(spec['cells']), observed=len(rows),
                  feasible=sum(r['has_solution'] for r in rows), missing_or_failed=missing,
                  coverage_complete=not missing, certified_unrestricted_optima=[r['id'] for r in rows if certified_optimal(r)],
                  certified_mode_winners=winners, comparisons=comparisons,
                  rhythm_objective_comparisons=rhythm_pairs, rows=rows,
                  interpretation='Negative and inconclusive observations retained. No automatic significance or superiority claim.')
    folder = out / 'audits'
    folder.mkdir(exist_ok=True)
    path = folder / ('audit_' + str(time.time_ns()) + '.json')
    dump(path, report)
    print(json.dumps(dict(report=str(path), expected=report['expected'], observed=len(rows),
                          feasible=report['feasible'], coverage_complete=not missing,
                          unrestricted_optima=len(report['certified_unrestricted_optima']),
                          certified_mode_winners=winners)))
    return report


def main():
    p = argparse.ArgumentParser(__doc__)
    p.add_argument('action', choices=('start', 'prepare', 'preflight', 'run', 'resume', 'audit', 'status', '_reference'))
    p.add_argument('--campaign', required=True)
    p.add_argument('--suite', choices=SUITES)
    p.add_argument('--memory-mb', type=int)
    p.add_argument('--jobs', type=int)
    p.add_argument('--case')
    args = p.parse_args()
    if args.action in ('start', 'prepare') and not args.suite:
        p.error('start/prepare requires --suite')
    if any(v is not None and v <= 0 for v in (args.memory_mb, args.jobs)):
        p.error('Resource limits must be positive')
    if args.action not in ('start', 'prepare') and (args.memory_mb is not None or args.jobs is not None):
        p.error('Resources are frozen; only start/prepare accept resource options')
    out = campaign_path(args.campaign)
    if out.exists() and args.suite and (out / 'supplement.json').exists():
        if read(out / 'supplement.json')['contract']['suite'] != args.suite:
            p.error('Suite differs from the frozen campaign')
    if args.action == 'start':
        prepare(args)
        preflight(out)
        run(out)
    elif args.action == 'prepare':
        prepare(args)
    elif args.action == 'preflight':
        preflight(out)
    elif args.action in ('run', 'resume'):
        if args.action == 'resume' and not (out / 'preflight_passed.json').exists():
            preflight(out)
        run(out, args.action == 'resume')
    elif args.action == 'audit':
        audit(out)
    elif args.action == '_reference':
        spec, _ = checked(out)
        prepare_reference(out, args.case, spec)
    else:
        from experiment_console import display
        _, contract = checked(out)
        display(out, contract['settings']['jobs'])


if __name__ == '__main__':
    main()

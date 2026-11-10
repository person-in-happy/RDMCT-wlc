"""Journal D algorithm diagnostics with no fixed SCIP/process memory quota.

plan/prepare/check do not optimize. New campaigns only; frozen old campaigns
are intentionally incompatible. System available RAM fraction is monitored.
Forked from thesis_gap_experiments.py SHA256 0e96a7e6e00f6bb6f7a0d8039480e037a6074b1e350c07fa24b61e544f9dcbf5.
Only conditional algorithm tests are exposed; no new algorithm is implemented.

Uses the unchanged 100 s nonprocessing backend. Old review helpers are reused
only after binding their imports to this backend and checking the binding.
"""
from pathlib import Path
from datetime import datetime, timezone
from dataclasses import asdict
import argparse
import importlib
import json
import math
import os
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
JMS = ROOT / 'JMS-version'
BACKEND = JMS / 'model4_pjob_nonprocessing_20261103'
RESULTS = JMS / 'results'
sys.path.insert(0, str(BACKEND))
# Load every backend module used by the reusable helpers before their imports.
for name in ('model', 'run_experiments', 'revalidate', 'validate', 'seed',
             'reference_completion', 'run_matched_supplement', 'paper_defaults'):
    importlib.import_module(name)
import model as backend
from run_experiments import assets, digest, dump, finite, incumbent_checks, ports, fix_structure, solve
from joint_algorithms import improve_skeleton, policy_record, install
from validate import validate
from run_matched_supplement import output_lock
from paper_defaults import ensure_idle
from revalidate import read
for folder in ('nondecreasing_review_20261102', 'nondecreasing_strengthening_20261102',
               'nondecreasing_followup_20261102'):
    sys.path.insert(0, str(JMS / 'experiments' / folder))
import review_experiments as review
import strengthen_models as strengthening
import followup_models as followup
assert review.Integrated is backend.Integrated
assert strengthening.backend is backend and followup.backend is backend
for name in ('model', 'run_experiments', 'validate', 'revalidate', 'seed', 'reference_completion'):
    assert Path(sys.modules[name].__file__).resolve().parent == BACKEND

SUITES = ('algorithm', 'standard')
SMALL = RESULTS / 'current_defaults_small_prepared_20261103'
PAPER = RESULTS / 'current_defaults_paper_20261104_075634'
CASES = [
    (SMALL, 'n2_H3_4x1_dual'),
    (SMALL, 'n2_H3_4x1_dual_same_lp'),
    (SMALL, 'n2_H3_mixed_dual'),
    (PAPER, 'n4_H10_mixed_dual'),
]


def stamp():
    return datetime.now(timezone.utc).isoformat()


def inventory():
    paths = [Path(__file__), Path(review.__file__), Path(strengthening.__file__),
             Path(followup.__file__), BACKEND / 'revalidate.py',
             BACKEND / 'run_matched_supplement.py', BACKEND / 'supplement_protocol.py',
             BACKEND / 'paper_defaults.py']
    return assets() | {str(p.relative_to(ROOT)): digest(p) for p in paths}


def environment():
    from importlib.metadata import version
    return dict(python=sys.executable, version=sys.version,
                packages={k: version(k) for k in ('pyscipopt', 'psutil', 'numpy', 'torch')})


def config_check(cfg):
    assert (cfg['module_residency'], cfg['robot_residency'], cfg['horizon']) == (100, 100, 10000)
    assert cfg['chamber_residency_basis'] == 'nonprocessing'
    assert cfg['max_pairs'] == cfg['max_cycles'] == 0


def source_check(source, values, rhythm=False):
    d = read(source)
    config_check(d['config'])
    if not d.get('solutions') or not d.get('original_model_check') or not validate(d)['valid']:
        raise ValueError('Source lacks a validated incumbent: ' + str(source))
    if not read(values).get('values'):
        raise ValueError('Missing complete assignment: ' + str(values))
    if rhythm and review.physical_metrics(d)['rhythm_centers'] < 2:
        raise ValueError('Need at least two active rhythm centers')
    return d


def plan(a):
    if not a.training_seeds or len(set(a.training_seeds)) != len(a.training_seeds):
        raise ValueError('Use distinct training seeds')
    arms = [('scip', False), ('hem', False), ('proposed', False),
            ('scip', True), ('hem', True), ('proposed', True)]
    if a.suite == 'algorithm':
        arms += [('feature_only', False), ('proposed_no_structure', False),
                 ('proposed_greedy', False)]
    cells = []
    for campaign, case in CASES:
        run = campaign / 'runs' / (case + '__s1__scip')
        source, values = run / 'phase1.json', run / 'variables_phase1.json'
        source_check(source, values)
        for seed in (1, 2, 3):
            for method, spbs in arms:
                # Never replicate deterministic SCIP as extra training samples.
                for training_seed in ([1] if method == 'scip' else a.training_seeds):
                    record = policy_record(method, training_seed)
                    arm = method + ('_spbs' if spbs else '_plain')
                    cells.append(dict(id=f'{case}__s{seed}__t{training_seed}__{arm}',
                        case=case, seed=seed, training_seed=training_seed,
                        method=method, spbs=spbs, arm=arm,
                        cut_profile='root_only' if a.suite == 'algorithm' else 'standard',
                        policy=record, source=str(source), values=str(values)))
    return cells


def campaign_path(value):
    p = Path(value).resolve()
    if p == RESULTS or not p.is_relative_to(RESULTS):
        raise ValueError('Use an isolated subdirectory of JMS-version/results')
    return p


def prepare(a, out):
    import psutil
    if out.exists():
        raise FileExistsError('Campaign exists; use resume without changing settings')
    cells = plan(a)
    available = psutil.virtual_memory().available / 1024**2
    if not 0 < a.min_available_fraction < .5:
        raise ValueError('System available-RAM fraction must be between 0 and 0.5')
    # SCIP's native default is its unlimited-memory sentinel, not a RAM quota.
    # Retaining the numeric setting lets unchanged helpers use their existing API.
    from scip_imports import scip
    probe = scip.Model()
    try:
        memory = probe.getParam('limits/memory')
    finally:
        probe.freeProb()
    if memory < 1e12:
        raise RuntimeError('SCIP native memory default is unexpectedly capped')
    settings = dict(time_limit=a.time_limit, stage2_limit=a.stage2_limit,
        cleanup_limit=a.stage2_limit, memory_mb=memory, process_memory_mb=None,
        memory_policy='scip_native_unlimited_system_available_fraction',
        min_available_fraction=a.min_available_fraction,
        available_at_prepare_mib=available, wall_limit=a.wall_limit,
        threads=1, jobs=1, hybrid_fixed_fraction=.2)
    if a.time_limit <= 0 or a.stage2_limit != 0 or a.wall_limit <= a.time_limit + a.stage2_limit:
        raise ValueError('Positive main budget, stage2=0 and additional build/validation wall time required')
    out.mkdir(parents=True)
    (out / 'configs').mkdir()
    sources = {}
    for c in cells:
        cfg = c.pop('config_data', None)
        if cfg is None:
            cfg = read(c['source'])['config']
            for key in ('source', 'values'):
                sources[c[key]] = digest(Path(c[key]))
        target = out / 'configs' / (c['case'] + '.json')
        dump(target, cfg)
        c['config'] = str(target)
        sources[str(target)] = digest(target)
    for c in cells:
        if c['policy']:
            for key in ('checkpoint', 'config'):
                sources[c['policy'][key]] = digest(Path(c['policy'][key]))
    provenance = None
    if a.source_campaign:
        parent = Path(a.source_campaign).resolve()
        provenance = dict(path=str(parent), campaign_sha256=digest(parent / 'campaign.json'),
                          selection='Lowest successful seed per case with >=2 rhythm centers; all weights retained')
    spec = dict(schema=1, created_utc=stamp(), suite=a.suite, cells=cells,
        settings=settings, sources=sources, assets=inventory(), environment=environment(),
        backend=str(BACKEND), source_campaign=provenance,
        scope='D: optional cleaning; homogeneous process times; nonprocessing residence 100 s; horizon including resets 10000 s',
        input_selection='Four previously validated D cases, seed1 common assignment shared by all arms and solver seeds; conditional on available incumbents',
        timing_accounting='Common supplied input; SPBS .2T plus primary .8T versus primary T; no refinement or cleanup. SPBS and primary-call wall time recorded; primary-call wall includes build/export/policy loading/validation. Not an end-to-end wall-budget comparison.',
        inference='Four incumbent-selected D cases; frozen CIE policy transfer, not new training or constructive success. Separate training/solver seeds; no automatic superiority claim.')
    dump(out / 'campaign.json', spec)
    dump(out / 'contract.json', dict(campaign_sha256=digest(out / 'campaign.json')))
    for rel in spec['assets']:
        target = out / 'frozen_code' / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / rel, target)
    print(json.dumps(dict(prepared=str(out), cells=len(cells), settings=settings, solver_started=False)), flush=True)


def checked(out):
    spec = read(out / 'campaign.json')
    if spec['settings'].get('memory_policy') != 'scip_native_unlimited_system_available_fraction':
        raise RuntimeError('This entry only accepts new uncapped campaigns; old frozen runs stay unchanged')
    if digest(out / 'campaign.json') != read(out / 'contract.json')['campaign_sha256']:
        raise RuntimeError('Protocol changed')
    if spec['assets'] != inventory() or spec['environment'] != environment():
        raise RuntimeError('Code/environment changed; preserve campaign and use a new protocol')
    for path, expected in spec['sources'].items():
        if digest(Path(path)) != expected:
            raise RuntimeError('Input changed: ' + path)
    return spec


def algorithm_run(c, dest, settings, check_only=False):
    source = read(c['source'])
    build_started = time.monotonic()
    x = backend.Integrated(backend.Config(**source['config']))
    m = x.model
    build_seconds = time.monotonic() - build_started
    values = None
    levels = []
    warm = c['values']
    init_seconds = 0.0
    try:
        values = review.canonical_warm(x, read(warm)['values'])
        if check_only:
            started = time.monotonic()
            agent, policy = install(m, c['method'], c['training_seed'])
            return dict(valid=True, solver_started=False, policy_loaded=policy,
                        policy_load_seconds=time.monotonic()-started,
                        source_metrics=review.physical_metrics(source))
        if c['spbs']:
            m.setIntParam('parallel/maxnthreads', 1)
            m.setIntParam('randomization/randomseedshift', c['seed'])
            # SPBS identical across cut methods; learning is a primary-solve module.
            if c['cut_profile'] == 'root_only':
                m.setIntParam('separating/maxroundsroot', 1)
                m.setIntParam('separating/maxrounds', 0)
            m.setRealParam('limits/memory', settings['memory_mb'])
            m.setLogfile(str(dest / 'spbs.log'))
            started = time.monotonic()
            values, levels = improve_skeleton(x, values, settings['time_limit'] * .2)
            init_seconds = time.monotonic() - started
            check = strengthening.assignment_solution(x, values)
            if not validate(x.result(solution=check))['valid']:
                raise RuntimeError('SPBS physical validation failed')
            m.freeSol(check)
            warm = str(dest / 'spbs_variables.json')
            dump(warm, dict(values=values))
    finally:
        m.freeProb()
    dump(dest / 'spbs_levels.json', levels)
    primary = dest / 'primary'
    started = time.monotonic()
    solve(c['config'], primary,
          time_limit=settings['time_limit'] * (.8 if c['spbs'] else 1),
          stage2_limit=0, seed=c['seed'], warm_start=warm,
          memory_mb=settings['memory_mb'], initialization='none',
          method=c['method'], training_seed=c['training_seed'],
          cut_profile=c['cut_profile'])
    primary_wall = time.monotonic() - started
    data = read(primary / 'result.json')
    if not data['original_model_check'] or not validate(data)['valid'] or not read(primary / 'warm_start_check.json')['accepted']:
        raise RuntimeError('Primary pipeline validation failed')
    # Recheck saved full assignment in a fresh, unrestricted original model.
    assignment = read(primary / 'variables.json')['values']
    audit = strengthening.audit_full(backend.Config(**source['config']), assignment, data)
    shutil.copy2(primary / 'result.json', dest / 'result.json')
    shutil.copy2(primary / 'variables.json', dest / 'variables.json')
    telemetry_path = primary / 'cutsel_telemetry.json'
    telemetry = read(telemetry_path) if telemetry_path.exists() else None
    return dict(valid=True, state=data['primary_status'],
        metrics=review.physical_metrics(data), source_metrics=review.physical_metrics(source),
        primary_bound=data['primary_bound'], primary_gap=data.get('primary_gap'),
        primary_only_pdi=data.get('primary_primal_dual_integral'),
        primary_wall_seconds=primary_wall, initialization_wall_seconds=init_seconds,
        initial_check_build_seconds=build_seconds, spbs_levels=levels,
        telemetry=telemetry, full_model_audit=audit,
        common_input_sha256=digest(Path(c['values'])),
        scope='Conditional module/transfer test, not constructive end-to-end performance')


def worker(out, identifier, check_only=False):
    spec = checked(out)
    c = next(c for c in spec['cells'] if c['id'] == identifier)
    if c['policy'] != policy_record(c['method'], c['training_seed']):
        raise RuntimeError('Frozen policy changed')
    dest = out / ('checks' if check_only else 'runs') / (identifier + ('_' + str(time.time_ns()) if check_only else ''))
    dest.mkdir(parents=True, exist_ok=False)
    record = algorithm_run(c, dest, spec['settings'], check_only)
    record.update(cell=c, ended_utc=stamp(), backend=str(BACKEND))
    if not check_only:
        record['result_sha256'] = digest(dest / 'result.json')
        record['variables_sha256'] = digest(dest / 'variables.json')
    dump(dest / ('check.json' if check_only else 'evidence.json'), finite(record))
    print(json.dumps(finite(record)), flush=True)


def summarize(out):
    spec = read(out / 'campaign.json')
    rows = []
    for c in spec['cells']:
        p = out / 'runs' / c['id']
        row = dict(id=c['id'], case=c['case'], seed=c['seed'], arm=c['arm'], execution='pending')
        if (p / 'evidence.json').exists() and (p / 'resources.json').exists() and read(p / 'resources.json')['exit_code'] == 0 and not (p / 'failure.json').exists():
            e = read(p / 'evidence.json')
            if digest(p / 'result.json') != e['result_sha256']:
                raise RuntimeError('Result changed: ' + c['id'])
            if 'variables_sha256' in e and digest(p / 'variables.json') != e['variables_sha256']:
                raise RuntimeError('Assignment changed: ' + c['id'])
            row.update(execution='complete', valid=e['valid'], state=e['state'], metrics=e.get('metrics'),
                       source_metrics=e.get('source_metrics'))
        elif (p / 'failure.json').exists():
            row.update(execution='failed', reason=read(p / 'failure.json')['reason'])
        rows.append(row)
    coverage = dict(expected=len(rows), **{k: sum(r['execution'] == k for r in rows) for k in ('complete', 'failed', 'pending')},
                    valid=sum(r.get('valid', False) for r in rows))
    (out / 'summary').mkdir(exist_ok=True)
    dump(out / 'summary/coverage.json', coverage)
    dump(out / 'summary/cells.json', rows)
    return coverage


def run(out, retry_failed=False):
    import psutil
    ensure_idle()
    spec = checked(out)
    st = spec['settings']
    with output_lock(RESULTS / '.default_gap_queue'), output_lock(out):
        durations = []
        for c in spec['cells']:
            rows = summarize(out)
            dest = out / 'runs' / c['id']
            states = read(out / 'summary/cells.json')
            state = next(r['execution'] for r in states if r['id'] == c['id'])
            if state == 'complete':
                continue
            if dest.exists():
                reason = read(dest / 'failure.json').get('reason') if (dest / 'failure.json').exists() else None
                if reason != 'foreground_interrupted' and not retry_failed:
                    raise RuntimeError('Incomplete/failed attempt preserved; inspect logs before explicit --retry-failed')
                archive = out / 'interrupted_attempts' / (c['id'] + '_' + str(time.time_ns()))
                if dest.is_symlink() or not dest.resolve().is_relative_to(out) or not archive.resolve().is_relative_to(out):
                    raise ValueError('Unsafe archive path')
                archive.parent.mkdir(exist_ok=True)
                dest.rename(archive)
            available = psutil.virtual_memory().available / 1024**2
            vm = psutil.virtual_memory()
            if vm.available / vm.total < st['min_available_fraction']:
                raise RuntimeError('Low system available RAM; no cell started. Resume after releasing RAM.')
            (out / 'logs').mkdir(exist_ok=True)
            logpath = out / 'logs' / (c['id'] + '_' + str(time.time_ns()) + '.log')
            begin = time.monotonic()
            peak = last = 0
            minimum_available_fraction = 1.0
            reason = None
            print('START ' + c['id'], flush=True)
            env = os.environ.copy()
            env.update(OMP_NUM_THREADS='1', MKL_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1')
            with logpath.open('wb') as log:
                child = subprocess.Popen([sys.executable, '-X', 'utf8', '-u', str(Path(__file__)),
                    '_worker', '--campaign', str(out), '--cell', c['id']], cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
                try:
                    while child.poll() is None:
                        elapsed = time.monotonic() - begin
                        try:
                            p = psutil.Process(child.pid)
                            rss = sum(q.memory_info().rss for q in [p] + p.children(recursive=True)) / 1024**2
                        except psutil.Error:
                            rss = 0
                        peak = max(peak, rss)
                        vm = psutil.virtual_memory()
                        fraction = vm.available / vm.total
                        minimum_available_fraction = min(minimum_available_fraction, fraction)
                        if fraction < st['min_available_fraction']:
                            reason = 'system_available_memory_guard'
                        if elapsed > st['wall_limit']:
                            reason = 'wall_guard'
                        if reason:
                            child.terminate()
                            break
                        if elapsed - last >= 10:
                            eta = (sum(durations) / len(durations) * (rows['expected'] - rows['complete']) - elapsed) / 3600 if durations else None
                            print(f'complete={rows["complete"]} failed={rows["failed"]} running=1 elapsed={elapsed:.0f}s RSS={rss:.0f}MiB ETA~{max(0, eta):.2f}h' if eta is not None else f'complete={rows["complete"]} failed={rows["failed"]} running=1 elapsed={elapsed:.0f}s RSS={rss:.0f}MiB ETA=estimating', flush=True)
                            last = elapsed
                        time.sleep(1)
                except KeyboardInterrupt:
                    reason = 'foreground_interrupted'
                    child.terminate()
                finally:
                    code = child.wait(timeout=30)
            dest.mkdir(parents=True, exist_ok=True)
            durations.append(time.monotonic() - begin)
            dump(dest / 'resources.json', dict(exit_code=code, peak_rss_mib=peak, wall_seconds=durations[-1], log=str(logpath),
                memory_policy=st['memory_policy'], min_system_available_fraction=minimum_available_fraction))
            if reason or code != 0 or not (dest / 'evidence.json').exists():
                dump(dest / 'failure.json', dict(reason=reason or 'worker_exit', exit_code=code, log=str(logpath)))
                summarize(out)
                raise RuntimeError('Attempt retained; inspect ' + str(logpath))
            print(json.dumps(summarize(out)), flush=True)
        dump(out / 'finished.json', summarize(out) | dict(ended_utc=stamp()))


def main():
    p = argparse.ArgumentParser(__doc__)
    p.add_argument('action', choices=('plan', 'prepare', 'start', 'resume', 'status', 'check', '_worker'))
    p.add_argument('--suite', choices=SUITES)
    p.add_argument('--campaign')
    p.add_argument('--source-campaign', help=argparse.SUPPRESS)
    p.add_argument('--training-seeds', type=int, nargs='+', default=[1])
    p.add_argument('--cell')
    p.add_argument('--time-limit', type=float, default=300)
    p.add_argument('--stage2-limit', type=float, default=0, help='Must be zero: isolate primary algorithms')
    p.add_argument('--min-available-fraction', type=float, default=.10,
                   help='System-wide available RAM safety threshold; no fixed solver or RSS cap')
    p.add_argument('--wall-limit', type=float, default=1800)
    p.add_argument('--retry-failed', action='store_true')
    a = p.parse_args()
    if a.action in ('plan', 'prepare', 'start') and not a.suite:
        p.error('--suite required')
    if a.action not in ('plan', 'prepare', 'start'):
        frozen = ('--training-seeds', '--suite', '--source-campaign', '--time-limit', '--stage2-limit', '--min-available-fraction', '--wall-limit')
        if any(v.split('=')[0] in frozen for v in sys.argv[1:]):
            p.error('Settings frozen; resume/status/check take only campaign and cell')
    if a.retry_failed and a.action != 'resume':
        p.error('--retry-failed only valid with resume')
    if a.action == 'plan':
        cells = plan(a)
        print(json.dumps(dict(suite=a.suite, cells=len(cells), cell_ids=[c['id'] for c in cells], solver_started=False), indent=2))
        return
    if not a.campaign:
        p.error('--campaign required')
    out = campaign_path(a.campaign)
    if a.action in ('prepare', 'start'):
        prepare(a, out)
        if a.action == 'start':
            run(out)
    elif a.action == 'resume':
        run(out, a.retry_failed)
    elif a.action == 'status':
        checked(out)
        print(json.dumps(summarize(out)))
    else:
        if not a.cell:
            p.error('--cell required')
        worker(out, a.cell, a.action == 'check')


if __name__ == '__main__':
    main()

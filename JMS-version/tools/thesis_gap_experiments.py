"""Thesis D gap experiments with no fixed SCIP/process memory quota.

plan/prepare/check do not optimize. New campaigns only; frozen old campaigns
are intentionally incompatible. System available RAM fraction is monitored.
Forked from default_gap_experiments.py SHA256 0126f320dae698a346d0322f9133eef3a5f3d44d302bf090a87885d2742daba0.

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
from joint_algorithms import improve_skeleton
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

SUITES = ('encoding', 'structure', 'cleanup', 'spbs', 'rhythm_search', 'rhythm')
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
                packages={k: version(k) for k in ('pyscipopt', 'psutil', 'numpy')})


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
    cells = []
    if a.suite == 'rhythm_search':
        for n, recipe in ((4, '2x2'), (6, '2x2'), (6, 'mixed')):
            cfg = asdict(backend.Config(ports(n, recipe), cleaning_interval=10))
            config_check(cfg)
            case = f'n{n}_H10_{recipe}_dual'
            for seed in (1, 2, 3):
                cells.append(dict(id=f'{case}__s{seed}', case=case, seed=seed,
                                  arm='rhythm_search', config_data=cfg))
        return cells
    sources = []
    if a.suite == 'rhythm':
        if not a.source_campaign:
            raise ValueError('--source-campaign is required for rhythm')
        parent = Path(a.source_campaign).resolve()
        spec = checked(parent)
        if spec['suite'] != 'rhythm_search':
            raise ValueError('Use a rhythm_search campaign')
        status = summarize(parent)
        if status['complete'] != status['expected']:
            raise ValueError('Finish all witness-search cells before selecting inputs')
        # Prespecified selection: lowest successful seed per case, never best gain.
        selected = set()
        for c in sorted(spec['cells'], key=lambda c: (c['case'], c['seed'])):
            run = parent / 'runs' / c['id']
            evidence = read(run / 'evidence.json')
            if c['case'] in selected or not evidence['valid']:
                continue
            source_check(run / 'result.json', run / 'variables.json', rhythm=True)
            selected.add(c['case'])
            sources.append((c['case'], run / 'result.json', run / 'variables.json'))
        if not sources:
            raise ValueError('Search completed with no eligible rhythm witness; no ablation launched')
    else:
        for campaign, case in CASES:
            run = campaign / 'runs' / (case + '__s1__scip')
            source = run / ('result.json' if a.suite == 'cleanup' else 'phase1.json')
            values = run / ('variables.json' if a.suite == 'cleanup' else 'variables_phase1.json')
            source_check(source, values)
            sources.append((case, source, values))
    arms = {'encoding': ('pjob', 'wafer'), 'structure': ('joint', 'fixed', 'fixed_then_joint'),
            'cleanup': ('cleanup',), 'spbs': ('no_spbs', 'spbs'), 'rhythm': (0, 5, 25, 100)}[a.suite]
    for case, source, values in sources:
        for seed in (1, 2, 3):
            for arm in arms:
                cells.append(dict(id=f'{case}__s{seed}__{arm}', case=case, seed=seed,
                    arm='refinement' if a.suite == 'rhythm' else arm,
                    weight=arm if a.suite == 'rhythm' else 25,
                    source=str(source), values=str(values)))
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
    if min(a.time_limit, a.stage2_limit) <= 0 or a.wall_limit <= a.time_limit + a.stage2_limit:
        raise ValueError('Positive budgets and additional build/validation wall time required')
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
        timing_accounting='structure: joint T, fixed T, hybrid .2T+.8T; encoding T; cleanup/rhythm stage2 limit; spbs: .2T initialization + .8T primary vs T primary, both + refinement + cleanup; construction and input provenance separate',
        inference='Aggregate solver seeds within case. No automatic superiority/significance claim. Rhythm search adds a witness constraint and cannot certify unrestricted optimality.')
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


def encoding_run(c, dest, settings, check_only=False, fixed_check=False):
    source = read(c['source'])
    cfg = backend.Config(**source['config'])
    begin_build = time.monotonic()
    x = followup.build_fair(cfg, c['arm'] if not fixed_check else 'pjob')
    build_seconds = time.monotonic() - begin_build
    m = x.model
    begin = time.monotonic()
    saved = None
    try:
        warm = strengthening.lift_start(x, c['arm'] if not fixed_check else 'pjob', source, read(c['values'])['values'])
        if fixed_check:
            fix_structure(x, source)
        sol = strengthening.assignment_solution(x, warm)
        replay = x.result(solution=sol)
        strengthening.assert_wafer_decode(x, sol, replay)
        if not validate(replay)['valid']:
            raise RuntimeError('Mapped input failed replay')
        # Measure the original formulation before SCIP transforms constraint types.
        model_dimensions = followup.dimensions(x)
        if check_only:
            m.freeSol(sol)
            return dict(valid=True, solver_started=False, dimensions=model_dimensions,
                        backend=str(BACKEND), fixed_structure_checked=fixed_check)
        m.addSol(sol)
        m.setIntParam('parallel/maxnthreads', 1)
        m.setIntParam('randomization/randomseedshift', c['seed'])
        m.setRealParam('limits/time', settings['time_limit'])
        m.setRealParam('limits/memory', settings['memory_mb'])
        m.setLogfile(str(dest / 'solver.log'))
        m.optimize()
        data = x.result()
        data.update(incumbent_checks(m), full_candidate_space=not x.bounded)
        data['validation'] = validate(data)
        if not data['original_model_check'] or not data['validation']['valid']:
            raise RuntimeError('Encoding solution failed original model / physical checks')
        strengthening.assert_wafer_decode(x, m.getBestSol(), data)
        saved = followup.save_assignment(x, m.getBestSol())
        dump(dest / 'result.json', finite(data))
        dump(dest / 'variables.json', dict(values=saved))
        record = dict(valid=True, state=str(m.getStatus()), metrics=review.physical_metrics(data),
            lower_bound=followup.finite_bound(m.getDualbound()), dimensions=model_dimensions,
            solve_seconds=m.getSolvingTime(), source_metrics=review.physical_metrics(source),
            build_seconds=build_seconds, common_warm_sha256=digest(Path(c['values'])))
    finally:
        m.freeProb()
    record['full_model_audit'] = strengthening.audit_full(cfg, saved, data)
    record['postbuild_wall_seconds'] = time.monotonic() - begin
    return record


def spbs_run(c, dest, settings, check_only=False):
    # Controlled SPBS module comparison beginning at the same checked assignment.
    # This does not test unconditional constructive initialization success.
    source = read(c['source'])
    x = backend.Integrated(backend.Config(**source['config']))
    m = x.model
    warm = c['values']
    budget = settings['time_limit']
    levels = []
    init_seconds = 0
    try:
        values = review.canonical_warm(x, read(warm)['values'])
        if check_only:
            return dict(valid=True, solver_started=False, source_metrics=review.physical_metrics(source))
        if c['arm'] == 'spbs':
            m.setIntParam('parallel/maxnthreads', 1)
            m.setIntParam('randomization/randomseedshift', c['seed'])
            m.setIntParam('separating/maxroundsroot', 1)
            m.setIntParam('separating/maxrounds', 0)
            m.setRealParam('limits/memory', settings['memory_mb'])
            m.setLogfile(str(dest / 'spbs.log'))
            started = time.monotonic()
            values, levels = improve_skeleton(x, values, budget * .2)
            init_seconds = time.monotonic() - started
            check = strengthening.assignment_solution(x, values)
            if not validate(x.result(solution=check))['valid']:
                raise RuntimeError('SPBS physical validation failed')
            m.freeSol(check)
            warm = str(dest / 'spbs_variables.json')
            dump(warm, dict(values=values))
            budget *= .8
    finally:
        m.freeProb()
    dump(dest / 'spbs_levels.json', levels)
    primary = dest / 'primary_refinement'
    solve(c['config'], primary, time_limit=budget, stage2_limit=settings['stage2_limit'],
          seed=c['seed'], warm_start=warm, memory_mb=settings['memory_mb'],
          initialization='none', cut_profile='root_only')
    data = read(primary / 'result.json')
    if not data['original_model_check'] or not validate(data)['valid'] or not read(primary / 'warm_start_check.json')['accepted']:
        raise RuntimeError('SPBS pipeline failed validation')
    cleanup_cell = c | dict(arm='cleanup', source=str(primary / 'result.json'), values=str(primary / 'variables.json'))
    final = review.refine(cleanup_cell, dest, settings)
    final.update(scope='Matched SPBS module plus primary/refinement/cleanup from a supplied feasible input; construction excluded',
        source_metrics=review.physical_metrics(source), before_cleanup_metrics=final['source_metrics'],
        spbs_levels=levels, initialization_wall_seconds=init_seconds,
        primary_status=data['primary_status'], primary_bound=followup.finite_bound(data['primary_bound']),
        common_input_sha256=digest(Path(c['values'])))
    return final


def witness_run(c, dest, settings):
    x = backend.Integrated(backend.Config(**read(c['config'])))
    m = x.model
    try:
        centers = [x.and_(x.keep[ch, q], x.keep[ch, q-1], f'gap_center_{ch}_{q}')
                   for ch in x.cfg.chambers for q in range(2, x.Q)]
        m.addCons(sum(centers) >= 2, name='diagnostic_need_two_rhythm_centers')
        m.setIntParam('parallel/maxnthreads', 1)
        m.setIntParam('randomization/randomseedshift', c['seed'])
        m.setRealParam('limits/time', settings['time_limit'])
        m.setRealParam('limits/memory', settings['memory_mb'])
        m.setLogfile(str(dest / 'solver.log'))
        m.optimize()
        data = x.result()
        data.update(incumbent_checks(m), full_candidate_space=False,
                    experiment_scope='rhythm_witness_search_restricted_domain')
        data['validation'] = validate(data)
        valid = bool(m.getNSols())
        record = dict(valid=valid, state=str(m.getStatus()), solve_seconds=m.getSolvingTime(),
                      primary_optimality_claim=False)
        if valid:
            met = review.physical_metrics(data)
            if not data['original_model_check'] or not data['validation']['valid'] or met['rhythm_centers'] < 2:
                raise RuntimeError('Witness failed validation or center threshold')
            values = followup.save_assignment(x, m.getBestSol())
            dump(dest / 'variables.json', dict(values=values))
            record['metrics'] = met
        dump(dest / 'result.json', finite(data))
    finally:
        m.freeProb()
    if valid:
        record['unrestricted_model_audit'] = strengthening.audit_full(x.cfg, values, data)
    return record


def worker(out, identifier, check_only=False):
    spec = checked(out)
    c = next(c for c in spec['cells'] if c['id'] == identifier)
    dest = out / ('checks' if check_only else 'runs') / (identifier + ('_' + str(time.time_ns()) if check_only else ''))
    dest.mkdir(parents=True, exist_ok=False)
    suite, settings = spec['suite'], spec['settings']
    if suite == 'encoding':
        record = encoding_run(c, dest, settings, check_only)
    elif suite == 'structure':
        record = encoding_run(c, dest, settings, True, True) if check_only else review.baseline(c, dest, settings)
    elif suite in ('cleanup', 'rhythm'):
        record = review.refine(c, dest, settings, check_only)
    elif suite == 'spbs':
        record = spbs_run(c, dest, settings, check_only)
    elif check_only:
        raise ValueError('Witness search has no saved assignment to check')
    else:
        record = witness_run(c, dest, settings)
    record.update(cell=c, ended_utc=stamp(), backend=str(BACKEND))
    if not check_only:
        record['result_sha256'] = digest(dest / 'result.json')
        if (dest / 'variables.json').exists():
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
    p.add_argument('--source-campaign')
    p.add_argument('--cell')
    p.add_argument('--time-limit', type=float, default=300)
    p.add_argument('--stage2-limit', type=float, default=60)
    p.add_argument('--min-available-fraction', type=float, default=.10,
                   help='System-wide available RAM safety threshold; no fixed solver or RSS cap')
    p.add_argument('--wall-limit', type=float, default=1800)
    p.add_argument('--retry-failed', action='store_true')
    a = p.parse_args()
    if a.action in ('plan', 'prepare', 'start') and not a.suite:
        p.error('--suite required')
    if a.action not in ('plan', 'prepare', 'start'):
        frozen = ('--suite', '--source-campaign', '--time-limit', '--stage2-limit', '--min-available-fraction', '--wall-limit')
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

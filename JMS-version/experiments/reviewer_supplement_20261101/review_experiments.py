"""Targeted review experiments from immutable FIFO campaign inputs.

plan/prepare/check never optimize. Formal runs use a visible foreground queue.
"""
from pathlib import Path
from datetime import datetime, timezone
import argparse
import csv
import json
import shutil
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
BACKEND = ROOT / 'JMS-version/model4_pjob_fifo_20261029'
sys.path.insert(0, str(BACKEND))
from model import Config, Integrated
from run_experiments import assets, digest, dump, finite, solve, incumbent_checks
from revalidate import read, metrics
from validate import validate
from run_matched_supplement import output_lock

RESULTS = ROOT / 'JMS-version/results'
PAPER = RESULTS / 'pjob_fifo_paper_all_20261030_075555'
CROSSOVER = RESULTS / 'pjob_fifo_crossover_all_20261030_190540'
QUALIFICATION = RESULTS / 'pjob_fifo_qualification_all_20261030_120650'
RHYTHM = RESULTS / 'pjob_fifo_rhythm_all_20261030_124059'
SUITES = ('baseline', 'rhythm', 'cleanup')


def stamp():
    return datetime.now(timezone.utc).isoformat()


def inventory():
    return assets() | {str(p.relative_to(ROOT)): digest(p) for p in (
        Path(__file__), HERE / 'run_review.ps1', BACKEND / 'revalidate.py',
        BACKEND / 'run_matched_supplement.py', BACKEND / 'supplement_protocol.py')}


def environment():
    from importlib.metadata import version
    return dict(python=sys.executable, version=sys.version,
                packages={n: version(n) for n in ('pyscipopt', 'psutil', 'numpy')})


def resolve_campaign(value):
    out = Path(value).resolve()
    if out == RESULTS.resolve() or not out.is_relative_to(RESULTS.resolve()):
        raise ValueError('Use a new subdirectory of JMS-version/results')
    return out


def physical_metrics(data):
    report = metrics(data)
    report['cleanings'] = sum(c['mode'] == 'clean' for c in data['cycles'])
    ends = [e['end'] for e in data['events']] + [c['end'] for c in data['cycles']]
    for e in data['events']:
        if e['kind'] == 'source_pick' and e['location'] == 'U':
            ends.append(e['end'] + data['config']['upper_reset'])
        if e['kind'] == 'lower_pick':
            ends.append(e['end'] + data['config']['lower_reset'])
    report['modeled_completion'] = max(ends, default=0)
    report['product_cmax'] = validate(data)['product_return_cmax']
    return report


def make_plan(suite, seeds):
    cells = []
    if suite == 'baseline':
        for n in (4, 8):
            for h in (3, 10):
                key = f'n{n}_H{h}_mixed_dual'
                ref = PAPER / 'references' / key
                for seed in seeds:
                    for arm in ('joint', 'fixed', 'fixed_then_joint'):
                        cells.append(dict(id=f'{key}__s{seed}__{arm}', case=key,
                            seed=seed, arm=arm, config=str(PAPER / 'configs' / (key + '.json')),
                            source=str(ref / 'reference.json'), values=str(ref / 'common.json')))
    elif suite == 'rhythm':
        for key in ('n16_H10_2x2_dual', 'n24_H5_2x2_dual', 'n24_H5_mixed_dual'):
            for seed in seeds:
                src = CROSSOVER / 'runs' / f'{key}__s{seed}__joint'
                for weight in (0, 5, 25, 100):
                    cells.append(dict(id=f'{key}__s{seed}__w{weight}', case=key, seed=seed,
                        arm='refinement', weight=weight, source=str(src / 'result.json'),
                        values=str(src / 'variables_phase1.json')))
    else:
        # Full-objective refinements reported in the manuscript: 24 + 6 + 12.
        for campaign in (PAPER, QUALIFICATION, RHYTHM):
            for old in read(campaign / 'campaign.json')['cells']:
                if old['variant'] != 'refined' or old['seed'] not in seeds:
                    continue
                src = campaign / 'runs' / old['id']
                cells.append(dict(id=old['id'], case=old['case'], seed=old['seed'],
                    arm='cleanup', weight=25, source=str(src / 'result.json'),
                    values=str(src / 'variables.json')))
    return cells


def check_source(cell, suite):
    data = read(cell['source'])
    check = validate(data)
    if not data.get('solutions') or not check['valid']:
        raise ValueError('Invalid saved source: ' + cell['source'])
    measured = physical_metrics(data)
    if suite == 'rhythm':
        if measured['rhythm_centers'] < 2:
            raise ValueError('No meaningful rhythm chain: ' + cell['id'])
        if '_H5_' in cell['case'] and measured['cleanings'] < 1:
            raise ValueError('Cleaning scenario did not activate cleaning: ' + cell['id'])
    if not Path(cell['values']).is_file():
        raise FileNotFoundError(cell['values'])
    return measured


def prepare(args):
    out = resolve_campaign(args.campaign)
    if out.exists():
        raise FileExistsError('Use a new campaign, or resume the existing one: ' + str(out))
    cells = make_plan(args.suite, args.seeds)
    sources, measurements = {}, {}
    for cell in cells:
        if cell['source'] not in measurements:
            measurements[cell['source']] = check_source(cell, args.suite)
        for key in ('source', 'values', 'config'):
            if key in cell and cell[key] not in sources:
                sources[cell[key]] = digest(Path(cell[key]))
    settings = dict(time_limit=args.time_limit, stage2_limit=args.stage2_limit,
        cleanup_limit=args.cleanup_limit, memory_mb=args.memory_mb,
        process_memory_mb=args.process_memory_mb, wall_limit=args.wall_limit,
        seeds=args.seeds, jobs=1, threads=1, reserve_mb=2048,
        hybrid_fixed_fraction=0.2)
    spec = dict(schema=1, created_utc=stamp(), suite=args.suite, cells=cells,
        settings=settings, assets=inventory(), sources=sources,
        source_metrics=measurements, environment=environment(),
        baseline_accounting='joint T; fixed T; fixed_then_joint 0.2T + 0.8T; historical SPBS preparation separate',
        refinement_accounting='Common saved first-stage assignment; only timing and synchronization switches released',
        cleanup_accounting='All discrete choices fixed; preserve product Cmax and full secondary upper bounds; minimize completion including LL resets')
    out.mkdir(parents=True)
    dump(out / 'campaign.json', spec)
    dump(out / 'contract.json', dict(campaign_sha256=digest(out / 'campaign.json')))
    for relative in spec['assets']:
        dest = out / 'frozen_code' / relative
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / relative, dest)
    print(json.dumps(dict(prepared=str(out), cells=len(cells), settings=settings,
                          solver_started=False)), flush=True)


def checked(out, cell=None):
    if digest(out / 'campaign.json') != read(out / 'contract.json')['campaign_sha256']:
        raise RuntimeError('Frozen campaign changed')
    spec = read(out / 'campaign.json')
    if inventory() != spec['assets'] or environment() != spec['environment']:
        raise RuntimeError('Code or environment changed; prepare a new campaign')
    names = spec['sources'] if cell is None else [cell[k] for k in ('source', 'values', 'config') if k in cell]
    for name in names:
        if digest(Path(name)) != spec['sources'][name]:
            raise RuntimeError('Source input changed: ' + name)
    return spec


def canonical_warm(x, values):
    """Tighten epigraph values without changing any scheduled event."""
    m = x.model
    sol = m.createSol()
    for v in m.getVars(transformed=False):
        if v.name not in values:
            raise ValueError('Incomplete source assignment: ' + v.name)
        m.setSolVal(sol, v, values[v.name])
    val = lambda e: float(e) if isinstance(e, (int, float)) else m.getSolVal(sol, e)
    m.setSolVal(sol, x.cmax, max(val(j['last']['e']) for j in x.jobs.values() if j['product'] is not None))
    m.setSolVal(sol, x.max_wait, max(0, *(val(w) for w in x.waits)))
    for i, c in enumerate(x.cfg.chambers):
        for q in range(2, x.Q):
            active = val(x.keep[c, q]) > .5 and val(x.keep[c, q - 1]) > .5
            diff = abs(val(x.cy.start[c, q]) - 2 * val(x.cy.start[c, q - 1]) + val(x.cy.start[c, q - 2])) if active else 0
            m.setSolVal(sol, x.rhythm[i * (x.Q - 2) + q - 2], diff)
    result = {v.name: m.getSolVal(sol, v) for v in m.getVars(transformed=False)}
    if not m.checkSol(sol, printreason=True, completely=True, original=True):
        raise RuntimeError('Source assignment failed original MILP constraints')
    m.freeSol(sol)
    return result


def refine(cell, dest, settings, check_only=False):
    source = read(cell['source'])
    source_check = validate(source)
    begin = time.monotonic()
    x = Integrated(Config(**source['config']))
    m = x.model
    try:
        values = canonical_warm(x, read(cell['values'])['values'])
        source_metrics = physical_metrics(source)
        m.setIntParam('parallel/maxnthreads', 1)
        m.setIntParam('randomization/randomseedshift', cell['seed'])
        m.setIntParam('separating/maxroundsroot', 1)
        m.setIntParam('separating/maxrounds', 0)
        m.setRealParam('limits/memory', settings['memory_mb'])
        m.setLogfile(str(dest / 'solver.log'))
        fixed = 0
        for var in m.getVars(transformed=False):
            if var.vtype() != 'CONTINUOUS' and (cell['arm'] == 'cleanup' or not var.name.startswith('sync_')):
                value = round(values[var.name])
                m.chgVarLb(var, value)
                m.chgVarUb(var, value)
                fixed += 1
        upper = source_check['product_return_cmax']
        m.addCons(x.cmax <= upper + 1e-6, name='review_preserve_product_cmax')
        weight = cell['weight']
        objective = sum(x.waits) + 10 * x.max_wait + weight * sum(x.rhythm)
        if cell['arm'] == 'cleanup':
            secondary_upper = source_metrics['route_wait_sum'] + 10 * source_metrics['route_wait_max'] + 25 * source_metrics['rhythm_deviation']
            m.addCons(objective <= secondary_upper + 1e-6, name='review_preserve_secondary')
            ready = m.addVar(lb=0, ub=x.H + max(x.cfg.upper_reset, x.cfg.lower_reset), name='review_modeled_completion')
            ends = [e['e'] for e in x.events] + list(x.cy.end.values())
            ends += [end for rows in x.intervals.values() for _, _, end, _ in rows]
            temp = m.createSol()
            for v in m.getVars(transformed=False):
                m.setSolVal(temp, v, values.get(v.name, 0))
            values[ready.name] = max(m.getSolVal(temp, end) for end in ends)
            m.freeSol(temp)
            for end in ends:
                m.addCons(ready >= end)
            objective = ready
        m.setObjective(objective, 'minimize')
        warm = m.createSol()
        for v in m.getVars(transformed=False):
            m.setSolVal(warm, v, values[v.name])
        if not m.checkSol(warm, printreason=True, completely=True, original=True):
            raise RuntimeError('Source is not feasible for the requested refinement')
        if check_only:
            replay = x.result(solution=warm)
            m.freeSol(warm)
            if not validate(replay)['valid']:
                raise RuntimeError('Reconstructed assignment failed physical replay')
            return dict(valid=True, solver_started=False, fixed_discrete_variables=fixed,
                        source_metrics=source_metrics, dimensions=x.original_dimensions)
        m.addSol(warm)
        build_seconds = time.monotonic() - begin
        m.setRealParam('limits/time', settings['cleanup_limit'] if cell['arm'] == 'cleanup' else settings['stage2_limit'])
        m.optimize()
        result = x.result()
        result.update(incumbent_checks(m))
        result['validation'] = validate(result)
        if not result['validation']['valid'] or not result['original_model_check']:
            raise RuntimeError('Refined solution failed validation')
        derived = physical_metrics(result)
        if derived['product_cmax'] > upper + 2e-4:
            raise RuntimeError('Product Cmax upper bound violated')
        if cell['arm'] == 'cleanup':
            final_secondary = derived['route_wait_sum'] + 10 * derived['route_wait_max'] + 25 * derived['rhythm_deviation']
            if final_secondary > secondary_upper + 2e-4:
                raise RuntimeError('Secondary upper bound violated')
        result.update(experiment_scope=cell['arm'], full_candidate_space=False,
            source_primary_status=source.get('primary_status', source.get('status')),
            source_primary_bound=source.get('primary_bound', source.get('dual_bound')),
            refinement_weight=weight, fixed_discrete_variables=fixed,
            optimized_objective=m.getObjVal())
        dump(dest / 'result.json', finite(result))
        best = m.getBestSol()
        dump(dest / 'variables.json', dict(values={v.name: m.getSolVal(best, v) for v in m.getVars(transformed=False)}))
        return dict(complete=True, valid=True, state=str(m.getStatus()), source_metrics=source_metrics,
            metrics=derived, build_seconds=build_seconds, solve_seconds=m.getSolvingTime(),
            optimized_objective=m.getObjVal(), original_model_check=True,
            primary_optimality_claim=False, fixed_discrete_variables=fixed)
    finally:
        m.freeProb()


def baseline(cell, dest, settings):
    budget = settings['time_limit']
    common = dict(seed=cell['seed'], stage2_limit=0, initialization='none',
        initialization_budget=0, memory_mb=settings['memory_mb'], method='scip', cut_profile='root_only')
    phases = []
    warm = cell['values']
    if cell['arm'] == 'fixed_then_joint':
        first = dest / 'fixed_start'
        solve(cell['config'], first, time_limit=budget * settings['hybrid_fixed_fraction'],
              warm_start=warm, fixed=cell['source'], **common)
        phases.append(first)
        warm = str(first / 'variables.json')
        budget *= 1 - settings['hybrid_fixed_fraction']
    target = dest / 'solve'
    solve(cell['config'], target, time_limit=budget, warm_start=warm,
          fixed=cell['source'] if cell['arm'] == 'fixed' else None, **common)
    phases.append(target)
    data = read(target / 'result.json')
    for folder in phases:
        r = read(folder / 'result.json')
        if not validate(r)['valid'] or not r['original_model_check'] or not read(folder / 'warm_start_check.json')['accepted']:
            raise RuntimeError('Baseline phase failed validation: ' + str(folder))
    dump(dest / 'result.json', data)
    return dict(complete=True, valid=True, state=data['primary_status'],
        metrics=physical_metrics(data), source_metrics=physical_metrics(read(cell['source'])),
        primary_bound=data['primary_bound'], primary_gap=data['primary_gap'],
        full_candidate_space=data['full_candidate_space'],
        warm_start_sha256=digest(Path(cell['values'])),
        phases=[dict(path=str(p.relative_to(dest)), solve_seconds=read(p / 'phase1.json')['solve_seconds'],
                     build_seconds=read(p / 'build.json')['seconds'],
                     cmax=validate(read(p / 'result.json'))['product_return_cmax']) for p in phases],
        solve_seconds=sum(read(p / 'phase1.json')['solve_seconds'] for p in phases))


def worker(out, cell_id):
    spec = read(out / 'campaign.json')
    cell = next(c for c in spec['cells'] if c['id'] == cell_id)
    checked(out, cell)
    dest = out / 'runs' / cell_id
    dest.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    record = baseline(cell, dest, spec['settings']) if spec['suite'] == 'baseline' else refine(cell, dest, spec['settings'])
    record.update(cell=cell, source_sha256=spec['sources'][cell['source']],
        input_values_sha256=spec['sources'][cell['values']], ended_utc=stamp(),
        worker_wall_seconds=time.monotonic() - started, result_sha256=digest(dest / 'result.json'))
    dump(dest / 'evidence.json', finite(record))


def summarize(out):
    spec = read(out / 'campaign.json')
    rows = []
    for cell in spec['cells']:
        dest = out / 'runs' / cell['id']
        row = dict(id=cell['id'], case=cell['case'], seed=cell['seed'], arm=cell['arm'], weight=cell.get('weight'), state='pending')
        if (dest / 'evidence.json').exists():
            evidence = read(dest / 'evidence.json')
            if digest(dest / 'result.json') != evidence['result_sha256']:
                raise RuntimeError('Saved result changed: ' + cell['id'])
            row.update(state='complete', solver_status=evidence['state'], **evidence['metrics'],
                       source_cmax=evidence['source_metrics']['product_cmax'],
                       solve_seconds=evidence['solve_seconds'], worker_wall_seconds=evidence['worker_wall_seconds'])
        elif (dest / 'failure.json').exists():
            row.update(state='failed', reason=read(dest / 'failure.json')['reason'])
        rows.append(row)
    report = dict(expected=len(rows), complete=sum(r['state'] == 'complete' for r in rows),
                  failed=sum(r['state'] == 'failed' for r in rows), pending=sum(r['state'] == 'pending' for r in rows))
    summary = out / 'summary'
    summary.mkdir(exist_ok=True)
    dump(summary / 'coverage.json', report)
    dump(summary / 'cells.json', rows)
    with (summary / 'cells.csv').open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=sorted(set().union(*(r.keys() for r in rows))))
        writer.writeheader()
        writer.writerows(rows)
    return report


def run(out, retry_failed=False):
    import psutil
    from evidence_supplement import no_other_queue
    spec = checked(out)
    no_other_queue()
    settings = spec['settings']
    required = settings['process_memory_mb'] + settings['reserve_mb']
    with output_lock(HERE), output_lock(out):
        durations = []
        for cell in spec['cells']:
            dest = out / 'runs' / cell['id']
            if (dest / 'evidence.json').exists():
                continue
            if (dest / 'failure.json').exists() and not retry_failed:
                continue
            if dest.exists():
                archive = out / 'interrupted_attempts' / (cell['id'] + '_' + str(time.time_ns()))
                if not dest.resolve().is_relative_to(out) or dest.is_symlink():
                    raise ValueError('Unsafe interrupted output path')
                archive.parent.mkdir(exist_ok=True)
                dest.rename(archive)
            available = psutil.virtual_memory().available / 1024**2
            if available < required:
                raise RuntimeError(f'Need {required:.0f} MiB available RAM; currently {available:.0f} MiB. Prepared campaign retained.')
            logs = out / 'logs'
            logs.mkdir(exist_ok=True)
            print('START ' + cell['id'], flush=True)
            started = time.monotonic()
            peak = 0
            reason = None
            logpath = logs / (cell['id'] + '_' + str(time.time_ns()) + '.log')
            with logpath.open('wb') as log:
                child = subprocess.Popen([sys.executable, '-X', 'utf8', '-u', str(Path(__file__)),
                    '_worker', '--campaign', str(out), '--cell', cell['id']], cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
                try:
                    last_report = 0
                    while child.poll() is None:
                        elapsed = time.monotonic() - started
                        try:
                            rss = psutil.Process(child.pid).memory_info().rss / 1024**2
                        except psutil.NoSuchProcess:
                            rss = 0
                        peak = max(peak, rss)
                        if rss > settings['process_memory_mb']:
                            reason = 'process_memory_guard'
                        if elapsed > settings['wall_limit']:
                            reason = 'cell_wall_guard'
                        if reason:
                            child.terminate()
                            child.wait(timeout=30)
                            break
                        if elapsed - last_report >= 15:
                            progress = summarize(out)
                            remaining = progress['expected'] - progress['complete'] - progress['failed']
                            eta = f'{max(0, sum(durations) / len(durations) * remaining - elapsed) / 3600:.2f}h' if durations else 'estimating'
                            print(f"complete={progress['complete']} failed={progress['failed']} running=1 ETA={eta} elapsed={elapsed:.0f}s RSS={rss:.0f}MiB", flush=True)
                            last_report = elapsed
                        time.sleep(2)
                    code = child.wait()
                except BaseException:
                    if child.poll() is None:
                        child.terminate()
                        child.wait(timeout=30)
                    raise
            elapsed = time.monotonic() - started
            durations.append(elapsed)
            dest.mkdir(parents=True, exist_ok=True)
            dump(dest / 'resources.json', dict(peak_rss_mb=peak, elapsed_seconds=elapsed, exit_code=code, log=str(logpath)))
            if code != 0 or not (dest / 'evidence.json').exists():
                dump(dest / 'failure.json', dict(reason=reason or f'exit_{code}', log=str(logpath), ended_utc=stamp()))
            print(json.dumps(summarize(out)), flush=True)
        coverage = summarize(out)
        if coverage['failed'] or coverage['pending']:
            raise RuntimeError('Queue has failed/pending cells; see summary and worker logs')
        dump(out / 'finished.json', coverage | dict(ended_utc=stamp()))


def main():
    p = argparse.ArgumentParser(__doc__)
    p.add_argument('action', choices=('plan', 'prepare', 'start', 'resume', 'status', 'check', '_worker'))
    p.add_argument('--suite', choices=SUITES)
    p.add_argument('--campaign')
    p.add_argument('--seeds', nargs='+', type=int, default=[1, 2, 3])
    p.add_argument('--time-limit', type=float, default=300)
    p.add_argument('--stage2-limit', type=float, default=60)
    p.add_argument('--cleanup-limit', type=float, default=60)
    p.add_argument('--memory-mb', type=int, default=10000)
    p.add_argument('--process-memory-mb', type=int, default=14000)
    p.add_argument('--wall-limit', type=float, default=3600)
    p.add_argument('--retry-failed', action='store_true')
    p.add_argument('--cell')
    args = p.parse_args()
    if args.action not in ('plan', 'prepare', 'start'):
        frozen = ('--suite', '--seeds', '--time-limit', '--stage2-limit', '--cleanup-limit',
                  '--memory-mb', '--process-memory-mb', '--wall-limit')
        if any(token.split('=')[0] in frozen for token in sys.argv[1:]):
            p.error('Settings are frozen; prepare a new campaign to change them')
    if args.retry_failed and args.action != 'resume':
        p.error('--retry-failed is only valid with resume')
    if args.action in ('plan', 'prepare', 'start') and not args.suite:
        p.error('--suite required')
    if len(set(args.seeds)) != len(args.seeds) or not args.seeds or not set(args.seeds) <= {1, 2, 3}:
        p.error('Saved source campaigns have seeds 1, 2, 3; select a distinct subset')
    if min(args.time_limit, args.stage2_limit, args.cleanup_limit, args.memory_mb, args.process_memory_mb) <= 0:
        p.error('Budgets must be positive')
    if args.wall_limit <= max(args.time_limit, args.stage2_limit, args.cleanup_limit):
        p.error('Wall limit must exceed each solve limit')
    if args.action == 'plan':
        cells = make_plan(args.suite, args.seeds)
        sources = {}
        for c in cells:
            if c['source'] not in sources:
                sources[c['source']] = check_source(c, args.suite)
        print(json.dumps(dict(suite=args.suite, cells=len(cells), sources=sources, solver_started=False), indent=2))
        return
    if not args.campaign:
        p.error('--campaign required')
    out = resolve_campaign(args.campaign)
    if args.action in ('start', 'prepare'):
        prepare(args)
        if args.action == 'start':
            run(out)
    elif args.action == 'resume':
        run(out, args.retry_failed)
    elif args.action == 'status':
        checked(out)
        print(json.dumps(summarize(out)), flush=True)
    elif args.action == 'check':
        spec = checked(out)
        if not args.cell or spec['suite'] == 'baseline':
            p.error('check requires --cell from a rhythm/cleanup campaign')
        cell = next(c for c in spec['cells'] if c['id'] == args.cell)
        dest = out / 'checks' / (cell['id'] + '_' + str(time.time_ns()))
        dest.mkdir(parents=True)
        record = refine(cell, dest, spec['settings'], check_only=True)
        dump(dest / 'check.json', record)
        print(json.dumps(record))
    else:
        if not args.cell:
            p.error('--cell required')
        worker(out, args.cell)


if __name__ == '__main__':
    main()

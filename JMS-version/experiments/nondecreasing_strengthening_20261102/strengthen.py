"""Targeted strengthening from immutable FIFO campaign inputs.

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
BACKEND = ROOT / 'JMS-version/model4_pjob_nondecreasing_20261102'
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
SUITES = ('rhythm_memory', 'representation')
from strengthen_models import run_cell


def stamp():
    return datetime.now(timezone.utc).isoformat()


def inventory():
    return assets() | {str(p.relative_to(ROOT)): digest(p) for p in (
        Path(__file__), HERE / 'run_strengthen.ps1', HERE / 'strengthen_models.py',
        HERE.parent / 'nondecreasing_review_20261102/review_experiments.py', BACKEND / 'revalidate.py',
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
    if suite == 'rhythm_memory':
        key = 'n24_H5_2x2_dual'
        for seed in seeds:
            src = CROSSOVER / 'runs' / f'{key}__s{seed}__joint'
            for weight in (0, 5, 25, 100):
                cells.append(dict(id=f'{key}__s{seed}__w{weight}', case=key, seed=seed,
                    arm='substituted', weight=weight, source=str(src / 'result.json'),
                    values=str(src / 'variables_phase1.json')))
    elif suite == 'representation':
        for n in (8, 16):
            for mode in ('4x1', '2x2', 'mixed'):
                key = f'n{n}_H5_{mode}_dual'
                ref = CROSSOVER / 'references' / key
                for seed in seeds:
                    # Alternate execution order to reduce order-related resource bias.
                    arms = ('pjob', 'wafer') if seed % 2 else ('wafer', 'pjob')
                    for arm in arms:
                        cells.append(dict(id=f'{key}__s{seed}__{arm}', case=key, seed=seed,
                            arm=arm, source=str(ref / 'reference.json'),
                            values=str(ref / 'common.json')))
    return cells


def check_source(cell, suite):
    data = read(cell['source'])
    check = validate(data)
    if not data.get('solutions') or not check['valid']:
        raise ValueError('Invalid saved source: ' + cell['source'])
    measured = physical_metrics(data)
    if suite == 'rhythm_memory':
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
        memory_mb=args.memory_mb,
        process_memory_mb=args.process_memory_mb, wall_limit=args.wall_limit,
        seeds=args.seeds, jobs=1, threads=1, reserve_mb=2048)
    spec = dict(release_order_rule='global_pjob_index_nondecreasing_lp_pickup', schema=1, created_utc=stamp(), suite=args.suite, cells=cells,
        settings=settings, assets=inventory(), sources=sources,
        source_metrics=measurements, environment=environment(),
        baseline_accounting='Pjob inventory versus wafer membership; same full candidate space, FIFO, physical start and primary solve budget; common SPBS preparation separate',
        refinement_accounting='Exact fixed B/I substitution except sync_; same source and objective as historical 12 memory-limited cells; lift and validate in full original MILP')
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


def worker(out, cell_id):
    spec = read(out / 'campaign.json')
    cell = next(c for c in spec['cells'] if c['id'] == cell_id)
    checked(out, cell)
    dest = out / 'runs' / cell_id
    dest.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    record = run_cell(cell, dest, spec['settings'])
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
                       solve_seconds=evidence['solve_seconds'], worker_wall_seconds=evidence['worker_wall_seconds'],
                       build_seconds=evidence['build_seconds'], audit_seconds=evidence['full_model_audit']['seconds'],
                       variables=evidence['dimensions']['variables'], constraints=evidence['dimensions']['constraints'],
                       linear_nonzeros=evidence['dimensions']['linear_nonzeros'], selector_variables=evidence['selector_variables'],
                       build_rss_mb=evidence['build_rss_mb'],
                       dual_bound=evidence.get('dual_bound'), gap=evidence.get('gap'), nodes=evidence.get('nodes'))
            if (dest / 'resources.json').exists():
                resource = read(dest / 'resources.json')
                row['peak_worker_rss_mb'] = resource['peak_rss_mb']
                row['peak_build_solve_rss_mb'] = max(evidence['build_rss_mb'], evidence.get('solve_end_rss_mb', 0),
                    resource.get('phase_peak_rss_mb', {}).get('construction', 0), resource.get('phase_peak_rss_mb', {}).get('solve', 0))
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
    with output_lock(HERE.parent / 'nondecreasing_review_20261102'), output_lock(HERE), output_lock(out):
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
            phase_peak = {}
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
                        phase = read(dest / 'phase.json')['phase'] if (dest / 'phase.json').exists() else 'startup'
                        phase_peak[phase] = max(phase_peak.get(phase, 0), rss)
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
            dump(dest / 'resources.json', dict(peak_rss_mb=peak, phase_peak_rss_mb=phase_peak,
                sampling_seconds=2, elapsed_seconds=elapsed, exit_code=code, log=str(logpath)))
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
    p.add_argument('--memory-mb', type=int, default=10000)
    p.add_argument('--process-memory-mb', type=int, default=14000)
    p.add_argument('--wall-limit', type=float, default=3600)
    p.add_argument('--retry-failed', action='store_true')
    p.add_argument('--cell')
    args = p.parse_args()
    if args.action not in ('plan', 'prepare', 'start'):
        frozen = ('--suite', '--seeds', '--time-limit', '--stage2-limit',
                  '--memory-mb', '--process-memory-mb', '--wall-limit')
        if any(token.split('=')[0] in frozen for token in sys.argv[1:]):
            p.error('Settings are frozen; prepare a new campaign to change them')
    if args.retry_failed and args.action != 'resume':
        p.error('--retry-failed is only valid with resume')
    if args.action in ('plan', 'prepare', 'start') and not args.suite:
        p.error('--suite required')
    if len(set(args.seeds)) != len(args.seeds) or not args.seeds or not set(args.seeds) <= {1, 2, 3}:
        p.error('Saved source campaigns have seeds 1, 2, 3; select a distinct subset')
    if min(args.time_limit, args.stage2_limit, args.memory_mb, args.process_memory_mb) <= 0:
        p.error('Budgets must be positive')
    if args.process_memory_mb <= args.memory_mb:
        p.error('Process RSS limit must exceed SCIP memory budget')
    if args.wall_limit <= max(args.time_limit, args.stage2_limit):
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
        if not args.cell:
            p.error('check requires --cell from the prepared campaign')
        cell = next(c for c in spec['cells'] if c['id'] == args.cell)
        dest = out / 'checks' / (cell['id'] + '_' + str(time.time_ns()))
        dest.mkdir(parents=True)
        record = run_cell(cell, dest, spec['settings'], check_only=True)
        dump(dest / 'check.json', record)
        print(json.dumps(record))
    else:
        if not args.cell:
            p.error('--cell required')
        worker(out, args.cell)


if __name__ == '__main__':
    main()

"""Visible, serial review follow-up queue with immutable inputs and resume."""
from pathlib import Path
from datetime import datetime, timezone
from collections import defaultdict, Counter
from statistics import mean, stdev
import argparse
import csv
import json
import os
import shutil
import subprocess
import sys
import time

from followup_models import ROOT, HERE, RESULTS, SUITES, plan, run_cell, read, dump, digest
from run_experiments import assets
from run_matched_supplement import output_lock


def stamp():
    return datetime.now(timezone.utc).isoformat()


def inventory():
    paths = [HERE / n for n in ('followup.py', 'followup_models.py', 'run_followup.ps1')]
    paths += [HERE.parent / 'nondecreasing_strengthening_20261102/strengthen_models.py',
              HERE.parent / 'nondecreasing_review_20261102/review_experiments.py',
              ROOT / 'JMS-version/model4_pjob_nondecreasing_20261102/revalidate.py',
              ROOT / 'JMS-version/model4_pjob_nondecreasing_20261102/run_matched_supplement.py',
              ROOT / 'JMS-version/model4_pjob_nondecreasing_20261102/supplement_protocol.py']
    return assets() | {str(p.relative_to(ROOT)): digest(p) for p in paths}


def environment():
    from importlib.metadata import version
    return dict(python=sys.executable, version=sys.version,
                packages={n: version(n) for n in ('pyscipopt', 'psutil', 'numpy')})


def campaign_path(value):
    path = Path(value).resolve()
    if path == RESULTS.resolve() or not path.is_relative_to(RESULTS.resolve()):
        raise ValueError('Campaign must be a new subdirectory of JMS-version/results')
    return path


def external_sources(cells):
    from validate import validate
    sources = {}
    for c in cells:
        for key in ('source', 'values'):
            if key in c and c[key] not in sources:
                p = Path(c[key])
                sources[str(p)] = digest(p)
                if key == 'source' and not validate(read(p))['valid']:
                    raise ValueError('Invalid source schedule: ' + str(p))
    return sources


def settings_for(args):
    timing = args.suite == 'timing'
    return dict(time_limit=0 if timing else args.time_limit if args.time_limit is not None else (300 if args.suite == 'residency' else 600),
        stage2_limit=0 if timing else args.stage2_limit, memory_mb=args.memory_mb or (6000 if timing else 3000),
        process_memory_mb=args.process_memory_mb or (8000 if timing else 4500),
        reserve_mb=1024, wall_limit=args.wall_limit, threads=1, jobs=1, repeats=args.repeats)


def prepare(args, out):
    if out.exists():
        raise FileExistsError('Use a new campaign or resume: ' + str(out))
    cells = plan(args.suite, args.repeats)
    sources = external_sources(cells)
    settings = settings_for(args)
    if settings['process_memory_mb'] <= settings['memory_mb']:
        raise ValueError('Process memory cap must exceed SCIP memory limit')
    if settings['wall_limit'] <= settings['time_limit'] + settings['stage2_limit']:
        raise ValueError('Wall limit must exceed primary plus secondary solver budgets')
    spec = dict(release_order_rule='global_pjob_index_nondecreasing_lp_pickup', schema=1, created_utc=stamp(), suite=args.suite, cells=cells, settings=settings,
        sources=sources, assets=inventory(), environment=environment(),
        protocol=dict(timing='No optimize; balanced order; one common constructor statistics pass; final dimensions outside timing',
            parallel='First production cycle in each chamber overlaps by at least 1 s; diagnostic feasibility domain',
            exact='Complete candidates, common physical start, paired Pjob/wafer representation, standard SCIP cuts',
            residency='Same fixed structure, H=10, module/robot limits 10000/500/250 s, primary then timing refinement'))
    out.mkdir(parents=True)
    dump(out / 'campaign.json', spec)
    dump(out / 'contract.json', dict(campaign_sha256=digest(out / 'campaign.json')))
    for relative in spec['assets']:
        target = out / 'frozen_code' / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / relative, target)
    print(json.dumps(dict(prepared=str(out), cells=len(cells), kinds=dict(Counter(c['kind'] for c in cells)),
                          settings=settings, solver_started=False)), flush=True)


def checked(out):
    spec = read(out / 'campaign.json')
    if digest(out / 'campaign.json') != read(out / 'contract.json')['campaign_sha256']:
        raise RuntimeError('Campaign settings changed')
    if inventory() != spec['assets'] or environment() != spec['environment']:
        raise RuntimeError('Implementation/environment changed; prepare a new campaign')
    for path, expected in spec['sources'].items():
        if digest(Path(path)) != expected:
            raise RuntimeError('Source changed: ' + path)
    return spec


def worker(out, identifier):
    spec = checked(out)
    cell = next(c for c in spec['cells'] if c['id'] == identifier)
    dest = out / 'runs' / identifier
    dest.mkdir(parents=True, exist_ok=False)
    begin = time.monotonic()
    record = run_cell(cell, dest, spec['settings'], out)
    record.update(cell=cell, ended_utc=stamp(), wall_seconds=time.monotonic() - begin,
        output_hashes={p.name: digest(p) for p in dest.iterdir() if p.name in ('result.json', 'variables.json', 'full_model_audit.json')})
    dump(dest / 'evidence.json', record)


def completed(dest):
    return ((dest / 'evidence.json').exists() and (dest / 'resources.json').exists()
            and read(dest / 'resources.json')['exit_code'] == 0 and not (dest / 'failure.json').exists())


def summarize(out):
    spec = read(out / 'campaign.json')
    rows, timings, exact = [], defaultdict(list), defaultdict(dict)
    for c in spec['cells']:
        dest = out / 'runs' / c['id']
        row = dict(id=c['id'], case=c['case'], kind=c['kind'], arm=c['arm'], execution='pending')
        if (dest / 'failure.json').exists():
            row.update(execution='failed', reason=read(dest / 'failure.json')['reason'])
        elif completed(dest):
            ev = read(dest / 'evidence.json')
            for name, expected in ev['output_hashes'].items():
                if digest(dest / name) != expected:
                    raise RuntimeError('Output changed: ' + str(dest / name))
            row.update(execution='complete', state=ev['state'], valid=ev['valid'], target_met=ev['target_met'])
            for key in ('build_seconds', 'mapping_and_check_seconds', 'preparation_seconds', 'solve_seconds',
                        'primary_solve_seconds', 'lower_bound', 'upper_bound', 'gap', 'nodes', 'scope', 'wall_seconds'):
                if key in ev:
                    row[key] = ev[key]
            row.update(ev.get('metrics', {}))
            if c['kind'] == 'timing':
                timings[c['case'], c['arm']].append(row)
            if c['kind'] == 'exact':
                exact[c['case']][c['arm']] = row
        rows.append(row)
    timing_groups = []
    for (case, arm), batch in timings.items():
        item = dict(case=case, arm=arm, repeats=len(batch))
        for metric in ('build_seconds', 'mapping_and_check_seconds', 'preparation_seconds'):
            vals = [r[metric] for r in batch]
            item[metric] = dict(mean=mean(vals), sample_sd=stdev(vals) if len(vals) > 1 else None, values=vals)
        timing_groups.append(item)
    exact_pairs = []
    for case, pair in exact.items():
        proven = len(pair) == 2 and all(r['state'] == 'optimal' and r['valid'] for r in pair.values())
        same = proven and abs(pair['pjob']['upper_bound'] - pair['wafer']['upper_bound']) <= 2e-4
        if proven and not same:
            raise RuntimeError('Proven optimum mismatch: ' + case)
        exact_pairs.append(dict(case=case, both_optimal=proven, equal_proven_values=same, arms=pair))
    report = dict(expected=len(rows), complete=sum(r['execution'] == 'complete' for r in rows),
        failed=sum(r['execution'] == 'failed' for r in rows), pending=sum(r['execution'] == 'pending' for r in rows),
        validated_records=sum(r.get('valid', False) for r in rows),
        targets_met=sum(r.get('target_met', False) for r in rows),
        reference_preparations=sum(r['kind'] == 'reference' for r in rows),
        exact_equal_optimum_pairs=sum(r['equal_proven_values'] for r in exact_pairs))
    summary = out / 'summary'
    summary.mkdir(exist_ok=True)
    for name, value in (('coverage', report), ('cells', rows), ('timing_groups', timing_groups), ('exact_pairs', exact_pairs)):
        dump(summary / (name + '.json'), value)
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
    with output_lock(HERE), output_lock(out):
        durations = []
        for cell in spec['cells']:
            dest = out / 'runs' / cell['id']
            if completed(dest):
                continue
            if (dest / 'failure.json').exists() and not retry_failed:
                continue
            if cell['kind'] == 'exact' and not completed(out / 'runs' / (cell['case'] + '__reference')):
                continue
            if dest.exists():
                if not dest.resolve().is_relative_to(out.resolve()) or dest.is_symlink():
                    raise ValueError('Unsafe interrupted run path')
                archive = out / 'interrupted_attempts' / (cell['id'] + '_' + str(time.time_ns()))
                if not archive.resolve().is_relative_to(out.resolve()):
                    raise ValueError('Unsafe archive path')
                archive.parent.mkdir(exist_ok=True)
                dest.rename(archive)
            available = psutil.virtual_memory().available / 1024**2
            required = settings['process_memory_mb'] + settings['reserve_mb']
            if available < required:
                raise RuntimeError(f'Need {required:.0f} MiB available RAM; currently {available:.0f} MiB. Prepared campaign retained; resume it after freeing RAM.')
            logs = out / 'logs'
            logs.mkdir(exist_ok=True)
            logpath = logs / (cell['id'] + '_' + str(time.time_ns()) + '.log')
            print('START ' + cell['id'], flush=True)
            begin, last, peak, reason = time.monotonic(), 0, 0, None
            env = os.environ.copy()
            env.update(OMP_NUM_THREADS='1', MKL_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1')
            with logpath.open('wb') as log:
                child = subprocess.Popen([sys.executable, '-X', 'utf8', '-u', str(Path(__file__)), '_worker',
                    '--campaign', str(out), '--cell', cell['id']], cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
                try:
                    while child.poll() is None:
                        elapsed = time.monotonic() - begin
                        try:
                            rss = psutil.Process(child.pid).memory_info().rss / 1024**2
                        except psutil.NoSuchProcess:
                            rss = 0
                        peak = max(peak, rss)
                        if rss > settings['process_memory_mb']:
                            reason = 'process_memory_guard'
                        elif elapsed > settings['wall_limit']:
                            reason = 'cell_wall_guard'
                        if reason:
                            child.terminate()
                            child.wait(timeout=30)
                            break
                        if elapsed - last >= 15:
                            progress = summarize(out)
                            remaining = progress['expected'] - progress['complete'] - progress['failed']
                            eta = f'{max(0, mean(durations) * remaining - elapsed) / 3600:.2f}h' if durations else 'estimating'
                            print(f"complete={progress['complete']} failed={progress['failed']} running=1 queued={max(0,remaining-1)} ETA={eta} RSS={rss:.0f}MiB", flush=True)
                            last = elapsed
                        time.sleep(2)
                    code = child.wait()
                except BaseException:
                    if child.poll() is None:
                        child.terminate()
                        child.wait(timeout=30)
                    raise
            elapsed = time.monotonic() - begin
            durations.append(elapsed)
            dest.mkdir(parents=True, exist_ok=True)
            dump(dest / 'resources.json', dict(exit_code=code, peak_rss_mb=peak, wall_seconds=elapsed,
                                               sampling_seconds=2, log=str(logpath)))
            if code != 0 or not (dest / 'evidence.json').exists():
                dump(dest / 'failure.json', dict(reason=reason or f'exit_{code}', log=str(logpath), ended_utc=stamp()))
            print(json.dumps(summarize(out)), flush=True)
        coverage = summarize(out)
        if coverage['failed'] or coverage['pending']:
            raise RuntimeError('Execution failures or pending cells remain; inspect summary and logs. Use explicit retry only after diagnosis.')
        dump(out / 'finished.json', coverage | dict(ended_utc=stamp()))
        print(json.dumps(coverage), flush=True)


def main():
    p = argparse.ArgumentParser(__doc__)
    p.add_argument('action', choices=('plan', 'prepare', 'start', 'resume', 'status', '_worker'))
    p.add_argument('--suite', choices=SUITES)
    p.add_argument('--campaign')
    p.add_argument('--repeats', type=int, default=6)
    p.add_argument('--time-limit', type=float)
    p.add_argument('--stage2-limit', type=float, default=60)
    p.add_argument('--memory-mb', type=int)
    p.add_argument('--process-memory-mb', type=int)
    p.add_argument('--wall-limit', type=float, default=1800)
    p.add_argument('--retry-failed', action='store_true')
    p.add_argument('--cell')
    args = p.parse_args()
    if args.action in ('plan', 'prepare', 'start'):
        if not args.suite:
            p.error('--suite required')
        if args.repeats < 2 or args.repeats % 2:
            p.error('--repeats must be even and at least 2 for balanced order')
        for key in ('time_limit', 'memory_mb', 'process_memory_mb'):
            if getattr(args, key) is not None and getattr(args, key) <= 0:
                p.error('Budgets must be positive')
        if args.stage2_limit <= 0 or args.wall_limit <= 0:
            p.error('Budgets must be positive')
    else:
        options = ('--suite', '--repeats', '--time-limit', '--stage2-limit', '--memory-mb', '--process-memory-mb', '--wall-limit')
        if any(token.split('=')[0] in options for token in sys.argv[1:]):
            p.error('Settings are frozen; create a new campaign to change them')
    if args.retry_failed and args.action != 'resume':
        p.error('--retry-failed is only valid with resume')
    if args.action == 'plan':
        cells = plan(args.suite, args.repeats)
        external_sources(cells)
        print(json.dumps(dict(suite=args.suite, cells=len(cells), kinds=dict(Counter(c['kind'] for c in cells)),
                              settings=settings_for(args), solver_started=False), indent=2))
        return
    if not args.campaign:
        p.error('--campaign required')
    out = campaign_path(args.campaign)
    if args.action in ('prepare', 'start'):
        prepare(args, out)
        if args.action == 'start':
            run(out)
    elif args.action == 'resume':
        run(out, args.retry_failed)
    elif args.action == 'status':
        checked(out)
        print(json.dumps(summarize(out)))
    else:
        if not args.cell:
            p.error('--cell required')
        worker(out, args.cell)


if __name__ == '__main__':
    main()

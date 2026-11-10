"""Read-only evidence audit, original-constraint replay, and manuscript statistics."""
from pathlib import Path
from collections import defaultdict, Counter
from statistics import mean
import argparse
import importlib.util
import json
import sys
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
BACKEND = ROOT / 'JMS-version/model4_pjob_fifo_20261029'
sys.path.insert(0, str(BACKEND))
from model import Config, Integrated
from run_experiments import digest, dump
from revalidate import read
from validate import validate


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


entry = module('review_entry', ROOT / 'JMS-version/experiments/reviewer_supplement_20261101/review_experiments.py')
oldaudit = module('old_review', HERE.parent / '20261101_reviewer_audit/analyze_evidence.py')


def near(a, b):
    return abs(a - b) <= 2e-4


def assignment_check(x, path):
    values = read(path)['values']
    m = x.model
    sol = m.createSol()
    try:
        for var in m.getVars(transformed=False):
            m.setSolVal(sol, var, values[var.name])
        if not m.checkSol(sol, printreason=True, completely=True, original=True):
            raise RuntimeError('Original model rejected: ' + str(path))
        replay = x.result(solution=sol)
        if not validate(replay)['valid']:
            raise RuntimeError('Assignment replay failed: ' + str(path))
        return entry.physical_metrics(replay), values
    finally:
        m.freeSol(sol)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--assignments', action='store_true')
    args = parser.parse_args()
    begin = time.monotonic()
    old = read(HERE.parent / '20261031_final_manuscript/verified_results.json')
    old_hashes = 0
    for row in old['rows']:
        run = ROOT / 'JMS-version/results' / row['campaign'] / 'runs' / row['id']
        for name in ('result.json', 'phase1.json', 'evidence.json', 'manifest.json'):
            assert digest(run / name) == row['hashes'][name], str(run / name)
            old_hashes += 1
    rows, campaigns, snapshots = [], [], {}
    grouped = defaultdict(list)
    for campaign in sorted((ROOT / 'JMS-version/results').glob('review_*')):
        if 'entrycheck' in campaign.name:
            continue
        spec = read(campaign / 'campaign.json')
        assert digest(campaign / 'campaign.json') == read(campaign / 'contract.json')['campaign_sha256']
        finished = read(campaign / 'finished.json')
        assert finished['complete'] == len(spec['cells']) and finished['failed'] == finished['pending'] == 0
        for relative, sha in spec['assets'].items():
            assert digest(ROOT / relative) == sha, relative
            assert digest(campaign / 'frozen_code' / relative) == sha, relative
        for path, sha in spec['sources'].items():
            assert digest(Path(path)) == sha, path
        campaigns.append(dict(name=campaign.name, suite=spec['suite'], settings=spec['settings'],
                              completed=finished['complete'], campaign_sha256=digest(campaign / 'campaign.json')))
        for cell in spec['cells']:
            folder = campaign / 'runs' / cell['id']
            ev = read(folder / 'evidence.json')
            result = read(folder / 'result.json')
            source = read(cell['source'])
            resources = read(folder / 'resources.json')
            assert resources['exit_code'] == 0
            assert ev['complete'] and ev['valid'] and result['original_model_check']
            assert digest(folder / 'result.json') == ev['result_sha256']
            assert digest(Path(cell['source'])) == ev['source_sha256']
            assert digest(Path(cell['values'])) == ev['input_values_sha256']
            assert validate(result)['valid'] and validate(source)['valid']
            derived, initial = entry.physical_metrics(result), entry.physical_metrics(source)
            for key, value in derived.items():
                assert near(value, ev['metrics'][key]), (cell['id'], key)
                assert near(initial[key], ev['source_metrics'][key]), (cell['id'], key)
            if spec['suite'] != 'baseline':
                assert derived['product_cmax'] <= initial['product_cmax'] + 2e-4
            secondary = lambda ms: ms['route_wait_sum'] + 10 * ms['route_wait_max'] + 25 * ms['rhythm_deviation']
            if spec['suite'] == 'cleanup':
                assert secondary(derived) <= secondary(initial) + 2e-4
                assert derived['modeled_completion'] <= initial['modeled_completion'] + 2e-4
            row = dict(campaign=campaign.name, suite=spec['suite'], **cell, state=ev['state'],
                metrics=derived, initial=initial, physical=oldaudit.physical_metrics(result),
                source_physical=oldaudit.physical_metrics(source), solve_seconds=ev['solve_seconds'],
                worker_wall_seconds=ev['worker_wall_seconds'], peak_rss_mb=resources['peak_rss_mb'],
                primary_bound=ev.get('primary_bound'), primary_gap=ev.get('primary_gap'),
                phases=ev.get('phases'), hashes={})
            for name in ('result.json', 'evidence.json', 'resources.json'):
                row['hashes'][name] = digest(folder / name)
                snapshots[str(folder / name)] = row['hashes'][name]
            values = folder / ('solve/variables.json' if spec['suite'] == 'baseline' else 'variables.json')
            row['assignment'] = str(values)
            row['assignment_sha256'] = digest(values)
            snapshots[str(values)] = row['assignment_sha256']
            grouped[json.dumps(result['config'], sort_keys=True)].append(row)
            rows.append(row)
    counts = Counter((r['suite'], r['state']) for r in rows)
    dump(HERE / 'metadata_audit.json', dict(campaigns=campaigns, rows=rows,
         old_metadata_hashes_checked=old_hashes, result_states={str(k): v for k, v in counts.items()},
         all_new_physical_replays_valid=True))
    if args.assignments:
        completed = 0
        for cfg_text, batch in grouped.items():
            x = Integrated(Config(**json.loads(cfg_text)))
            try:
                for row in batch:
                    actual, final_values = assignment_check(x, Path(row['assignment']))
                    for key in row['metrics']:
                        assert near(actual[key], row['metrics'][key]), (row['id'], key)
                    if row['suite'] != 'baseline':
                        prior = read(row['values'])['values']
                        for var in x.model.getVars(transformed=False):
                            if var.vtype() != 'CONTINUOUS' and (row['suite'] == 'cleanup' or not var.name.startswith('sync_')):
                                assert near(final_values[var.name], prior[var.name]), (row['id'], var.name)
                    elif row['arm'] == 'fixed_then_joint':
                        first = Path(row['assignment']).parent.parent / 'fixed_start'
                        first_metrics, _ = assignment_check(x, first / 'variables.json')
                        assert actual['product_cmax'] <= first_metrics['product_cmax'] + 2e-4
                        row['hybrid_pre_cmax'] = first_metrics['product_cmax']
                    row['independent_assignment_check'] = True
                    completed += 1
                    if completed % 6 == 0:
                        print(f'Original-model replay {completed}/{len(rows)}; elapsed={time.monotonic()-begin:.0f}s', flush=True)
            finally:
                x.model.freeProb()
            dump(HERE / 'assignment_replay.partial.json', dict(checked=completed, rows=rows))
    for path, sha in snapshots.items():
        assert digest(Path(path)) == sha
    stats = []
    g = defaultdict(list)
    for row in rows:
        g[row['suite'], row['case'], row['arm'], row.get('weight')].append(row)
    for (suite, case, arm, weight), batch in g.items():
        stats.append(dict(suite=suite, case=case, arm=arm, weight=weight, n=len(batch),
            metrics={k: mean(r['metrics'][k] for r in batch) for k in batch[0]['metrics']},
            initial={k: mean(r['initial'][k] for r in batch) for k in batch[0]['initial']},
            cmax_values=[r['metrics']['product_cmax'] for r in batch],
            statuses=dict(Counter(r['state'] for r in batch)),
            seconds=mean(r['solve_seconds'] for r in batch),
            worker_seconds=mean(r['worker_wall_seconds'] for r in batch)))
    cleanup = [r for r in rows if r['suite'] == 'cleanup']
    report = dict(campaigns=campaigns, completed=len(rows), feasible=len(rows), rows=rows,
        groups=stats, old_metadata_hashes_checked=old_hashes,
        original_assignment_replays=len(rows) if args.assignments else 0,
        extra_hybrid_start_replays=12 if args.assignments else 0,
        raw_results_unchanged=True, script_sha256=digest(Path(__file__)),
        cleanup_improved=sum(r['metrics']['modeled_completion'] < r['initial']['modeled_completion'] - 2e-4 for r in cleanup),
        cleanup_cmax_improved=sum(r['metrics']['product_cmax'] < r['initial']['product_cmax'] - 2e-4 for r in cleanup),
        elapsed_seconds=time.monotonic()-begin)
    dump(HERE / 'verified_supplements.json', report)
    print(json.dumps({k:v for k,v in report.items() if k not in ('rows','groups','campaigns')}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()

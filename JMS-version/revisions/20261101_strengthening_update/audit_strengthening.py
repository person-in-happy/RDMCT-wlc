"""Read-only audit of completed strengthening campaigns; never optimize."""
from pathlib import Path
from collections import defaultdict, Counter
from statistics import mean
import gc
import json
import sys
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / 'JMS-version/experiments/strengthening_20261101'))
import strengthen as entry
from strengthen_models import backend, encoding, same_replay
from run_experiments import digest, dump
from revalidate import read
from validate import validate


def near(a, b, tol=2e-4):
    return abs(a - b) <= tol


def check_assignment(x, values):
    m = x.model
    sol = m.createSol()
    try:
        for v in m.getVars(transformed=False):
            m.setSolVal(sol, v, values[v.name])
        assert m.checkSol(sol, printreason=True, completely=True, original=True)
        replay = x.result(solution=sol)
        assert validate(replay)['valid']
        return replay
    finally:
        m.freeSol(sol)


def wafer_assignment(x, values, replay):
    codes = encoding(x.cfg)
    members = {(p['id'], r): w for p in replay['pairs'] for r, w in enumerate(p['members'])}
    jobs = {j['identity']: j for j in replay['jobs'] if j['product']}
    count = 0
    for w in codes:
        total = 0
        for p in range(min(x.N, x.P)):
            for r in (0, 1):
                value = values[f'wafer_y_{w}_{p}_{r}']
                assert near(value, round(value)) and round(value) in (0, 1)
                total += value
                if value > .5:
                    assert members[p, r] == w
                count += 1
        assert near(total, 1)
        assert near(values['wafer_pickup_' + w], jobs[w]['loan_start'])
    for g in x.groups:
        for p in range(min(x.N, x.P)):
            for r in (0, 1):
                assert near(values[f'pj_x_{g.identifier}_{p}_{r}'],
                            sum(values[f'wafer_y_{w}_{p}_{r}'] for w in g.labels))
    return count


def main():
    begin = time.monotonic()
    snapshots = {}
    def remember(path, expected=None):
        sha = digest(Path(path))
        if expected is not None:
            assert sha == expected, str(path)
        snapshots[str(path)] = sha
        return sha

    # Verify the prior review's accepted results and assignments remain intact.
    prior = read(HERE.parent / '20261101_supplement_update/verified_supplements.json')
    old_count = 0
    for row in prior['rows']:
        folder = ROOT / 'JMS-version/results' / row['campaign'] / 'runs' / row['id']
        for name, sha in row['hashes'].items():
            remember(folder / name, sha)
            old_count += 1
        remember(row['assignment'], row['assignment_sha256'])
        old_count += 1
    older = read(HERE.parent / '20261031_final_manuscript/verified_results.json')
    for row in older['rows']:
        folder = ROOT / 'JMS-version/results' / row['campaign'] / 'runs' / row['id']
        for name, sha in row['hashes'].items():
            remember(folder / name, sha)
            old_count += 1

    rows, campaigns = [], []
    grouped = defaultdict(list)
    for name in ('strengthen_rhythm_memory_20261101_161209', 'strengthen_representation_20261101_162725'):
        out = entry.RESULTS / name
        spec = entry.checked(out)
        finished = read(out / 'finished.json')
        assert finished['complete'] == len(spec['cells']) and finished['failed'] == finished['pending'] == 0
        for relative, sha in spec['assets'].items():
            remember(ROOT / relative, sha)
            remember(out / 'frozen_code' / relative, sha)
        for path, sha in spec['sources'].items():
            remember(path, sha)
        for name in ('campaign.json', 'contract.json', 'finished.json'):
            remember(out / name)
        campaigns.append(dict(name=out.name, suite=spec['suite'], settings=spec['settings'],
                              completed=finished['complete'], campaign_sha256=digest(out / 'campaign.json')))
        for cell in spec['cells']:
            folder = out / 'runs' / cell['id']
            ev = read(folder / 'evidence.json')
            data = read(folder / 'result.json')
            resource = read(folder / 'resources.json')
            source = read(cell['source'])
            assert resource['exit_code'] == 0 and ev['complete'] and ev['valid']
            assert data['original_model_check'] and ev['full_model_audit']['valid']
            remember(folder / 'result.json', ev['result_sha256'])
            assert digest(Path(cell['source'])) == ev['source_sha256']
            assert digest(Path(cell['values'])) == ev['input_values_sha256']
            assert validate(data)['valid'] and validate(source)['valid']
            actual, initial = entry.physical_metrics(data), entry.physical_metrics(source)
            for key, value in actual.items():
                assert near(value, ev['metrics'][key]), (cell['id'], key)
                assert near(initial[key], ev['source_metrics'][key])
            if spec['suite'] == 'rhythm_memory':
                assert actual['product_cmax'] <= initial['product_cmax'] + 2e-4
                objective = actual['route_wait_sum'] + 10 * actual['route_wait_max'] + cell['weight'] * actual['rhythm_deviation']
                assert near(objective, ev['optimized_objective'], 1e-3)
            sampled = resource.get('phase_peak_rss_mb', {})
            row = dict(campaign=out.name, suite=spec['suite'], **cell, state=ev['state'],
                actual=actual, initial=initial, dimensions=ev['dimensions'],
                original_dimensions=ev['full_model_audit']['dimensions'],
                selectors=ev['selector_variables'], N=ev['N'], G=ev['G'],
                candidate_pairs=ev['candidate_pairs'], candidate_cycles=ev['candidate_cycles'],
                source_hash=ev['source_sha256'], source_values_hash=ev['input_values_sha256'],
                build_and_start_check_seconds=ev['build_seconds'], solve_seconds=ev['solve_seconds'],
                worker_seconds=ev['worker_wall_seconds'], full_audit_seconds=ev['full_model_audit']['seconds'],
                build_solve_rss_mb=max(ev['build_rss_mb'], ev.get('solve_end_rss_mb', 0),
                                       sampled.get('construction', 0), sampled.get('solve', 0)),
                full_worker_rss_mb=resource['peak_rss_mb'],
                bound=ev['dual_bound'], gap=ev['gap'], nodes=ev['nodes'],
                assignment=str(folder / 'variables.json'), hashes={})
            for name in ('result.json', 'variables.json', 'evidence.json', 'full_model_audit.json', 'resources.json', 'build.json'):
                row['hashes'][name] = remember(folder / name)
            grouped[json.dumps(data['config'], sort_keys=True)].append(row)
            rows.append(row)
    dump(HERE / 'metadata_audit.json', dict(rows=rows, campaigns=campaigns))
    completed, input_checks, wafer_checks = 0, 0, 0
    for cfg_json, batch in grouped.items():
        print('BUILD original model for ' + batch[0]['case'], flush=True)
        x = backend.Integrated(backend.Config(**json.loads(cfg_json)))
        try:
            sources = {}
            for row in batch:
                if row['values'] not in sources:
                    initial_values = read(row['values'])['values']
                    initial_replay = check_assignment(x, initial_values)
                    saved_source = read(row['source'])
                    for field in ('events', 'jobs', 'pairs', 'cycles'):
                        assert same_replay(initial_replay[field], saved_source[field]), field
                    sources[row['values']] = True
                    input_checks += 1
                    del initial_values, initial_replay
                values = read(row['assignment'])['values']
                replay = check_assignment(x, values)
                result = read(Path(row['assignment']).parent / 'result.json')
                for field in ('events', 'jobs', 'pairs', 'cycles'):
                    assert same_replay(replay[field], result[field]), (row['id'], field)
                if row['arm'] == 'substituted':
                    source_values = read(row['values'])['values']
                    for var in x.model.getVars(transformed=False):
                        if var.vtype() != 'CONTINUOUS' and not var.name.startswith('sync_'):
                            assert near(values[var.name], source_values[var.name])
                    del source_values
                elif row['arm'] == 'wafer':
                    assert wafer_assignment(x, values, replay) == row['selectors']
                    wafer_checks += 1
                assert x.original_dimensions == row['original_dimensions']
                row['independent_full_assignment_check'] = True
                completed += 1
                print(f'CHECKED {completed}/{len(rows)} {row["id"]}; elapsed={time.monotonic()-begin:.0f}s', flush=True)
                del values, replay, result
            dump(HERE / 'assignment_replay.partial.json', dict(completed=completed, rows=rows))
        finally:
            x.model.freeProb()
        del x
        gc.collect()

    pairs = defaultdict(dict)
    for row in rows:
        if row['suite'] == 'representation':
            pairs[row['case'], row['seed']][row['arm']] = row
    for pair in pairs.values():
        a, b = pair['pjob'], pair['wafer']
        for key in ('source_hash', 'source_values_hash', 'candidate_pairs', 'candidate_cycles', 'N', 'G'):
            assert a[key] == b[key]
        assert a['selectors'] == 2 * a['G'] * a['N']
        assert b['selectors'] == 2 * b['N']**2
    groups = defaultdict(list)
    for row in rows:
        groups[row['suite'], row['case'], row['arm'], row.get('weight')].append(row)
    summaries = []
    for (suite, case, arm, weight), batch in groups.items():
        assert {r['seed'] for r in batch} == {1, 2, 3}
        summaries.append(dict(suite=suite, case=case, arm=arm, weight=weight,
            n=len(batch), dimensions=batch[0]['dimensions'], selectors=batch[0]['selectors'],
            statuses=dict(Counter(r['state'] for r in batch)),
            actual={k: mean(r['actual'][k] for r in batch) for k in batch[0]['actual']},
            means={k: mean(r[k] for r in batch) for k in ('build_and_start_check_seconds', 'solve_seconds',
                'worker_seconds', 'full_audit_seconds', 'build_solve_rss_mb', 'full_worker_rss_mb')},
            bounds=[r['bound'] for r in batch], nodes=[r['nodes'] for r in batch]))
    for path, sha in snapshots.items():
        assert digest(Path(path)) == sha, path
    report = dict(completed=completed, feasible=completed, input_assignment_checks=input_checks,
        wafer_assignment_checks=wafer_checks, prior_hashes_checked=old_count,
        campaigns=campaigns, rows=rows, groups=summaries, paired_comparisons=len(pairs),
        statuses=dict(Counter(r['state'] for r in rows)), snapshots=snapshots,
        raw_files_unchanged=True, optimization_started=False, seconds=time.monotonic()-begin)
    dump(HERE / 'verified_strengthening.json', report)
    print(json.dumps({k: v for k, v in report.items() if k not in ('rows','groups','snapshots','campaigns')}), flush=True)


if __name__ == '__main__':
    main()

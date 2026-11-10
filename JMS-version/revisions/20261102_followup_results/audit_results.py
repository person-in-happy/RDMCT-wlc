"""Read-only campaign audit; no optimize calls and no campaign mutations."""
from pathlib import Path
from collections import Counter, defaultdict
from statistics import mean, stdev
from datetime import datetime, timezone
import hashlib
import json
import shutil
import sys

HERE = Path(__file__).resolve().parent
PAPER = HERE.parents[1]
ROOT = PAPER.parent
sys.path.insert(0, str(PAPER / 'experiments/review_followup_20261102'))
import followup_models as f


def read(path):
    return json.loads(path.read_text('utf-8'))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class NoOptimize(f.REAL_MODEL):
    def optimize(self, *args, **kwargs):
        raise AssertionError('Optimization is prohibited during audit')


class WaferNoOptimize(f.WaferModel):
    def optimize(self, *args, **kwargs):
        raise AssertionError('Optimization is prohibited during audit')


f.scip.Model = NoOptimize
f.WaferModel = WaferNoOptimize
HERE.mkdir(exist_ok=True)
(HERE / 'original').mkdir(exist_ok=True)
for name in ('JMS_Review_CN.tex', 'JMS_Review_CN.pdf'):
    target = HERE / 'original' / name
    if not target.exists():
        shutil.copy2(PAPER / name, target)

snapshots, suites, checked, rebuilt = {}, {}, [], []
for suite in ('timing', 'parallel', 'exact', 'residency'):
    campaign = PAPER / 'results' / f'review_followup_{suite}_20261102_01'
    spec, contract = read(campaign / 'campaign.json'), read(campaign / 'contract.json')
    assert sha(campaign / 'campaign.json') == contract['campaign_sha256']
    assert spec['suite'] == suite and spec['settings']['threads'] == spec['settings']['jobs'] == 1
    for relative, expected in spec['assets'].items():
        assert sha(ROOT / relative) == expected, relative
        assert sha(campaign / 'frozen_code' / relative) == expected, relative
    for path, expected in spec['sources'].items():
        assert sha(Path(path)) == expected, path
    finished = read(campaign / 'finished.json')
    assert finished['expected'] == finished['complete'] == len(spec['cells'])
    assert finished['failed'] == finished['pending'] == 0
    summaries = {r['id']: r for r in read(campaign / 'summary/cells.json')}
    assert len(summaries) == len(spec['cells'])
    records = []
    for cell in spec['cells']:
        dest = campaign / 'runs' / cell['id']
        ev, resources = read(dest / 'evidence.json'), read(dest / 'resources.json')
        assert resources['exit_code'] == 0 and not (dest / 'failure.json').exists()
        assert ev['cell'] == cell and ev['complete']
        for name, expected in ev['output_hashes'].items():
            assert sha(dest / name) == expected, str(dest / name)
        data = read(dest / 'result.json')
        row = dict(id=cell['id'], case=cell['case'], kind=cell['kind'], arm=cell['arm'],
                   state=ev['state'], valid=ev['valid'], path=str(dest.relative_to(ROOT)))
        assert row['state'] == summaries[cell['id']]['state']
        if ev['valid']:
            physical = f.validate(data)
            assert physical['valid'], (cell['id'], physical)
            metrics = f.numbers(data)
            for name, value in metrics.items():
                if isinstance(value, (int, float)):
                    assert abs(value - ev['metrics'][name]) < 2e-4, (cell['id'], name)
            row.update(metrics=metrics, physical_checks=physical['checks'])
            checked.append(row['id'])
            if cell['kind'] not in ('timing', 'reference'):
                cfg = f.backend.Config(**data['config'])
                values = read(dest / 'variables.json')['values']
                row['rebuilt_original'] = f.audit_full(cfg, values, data)
                assert row['rebuilt_original']['valid']
                if cell['arm'] == 'wafer':
                    x = f.build_fair(cfg, 'wafer')
                    try:
                        sol = f.assignment_solution(x, values)
                        f.assert_wafer_decode(x, sol, data)
                        x.model.freeSol(sol)
                    finally:
                        x.model.freeProb()
                    row['explicit_identity_rechecked'] = True
                rebuilt.append(row['id'])
            if cell['kind'] == 'residency':
                first = read(dest / 'solve/phase1.json')
                assert f.validate(first)['valid']
                row['primary'] = {k: first[k] for k in ('status', 'cmax', 'dual_bound', 'gap')}
                row['primary_metrics'] = f.numbers(first)
                assert data['cmax'] <= first['cmax'] + 2e-4
            row['cmax'] = data['cmax']
        else:
            assert not data.get('solutions'), cell['id']
            assert ev['state'] in ('timelimit', 'infeasible')
        for k in ('lower_bound', 'upper_bound', 'gap', 'solve_seconds', 'primary_state',
                  'primary_lower_bound', 'primary_solve_seconds', 'preparation_seconds',
                  'build_seconds', 'mapping_and_check_seconds', 'full_candidate_space'):
            if k in ev:
                row[k] = ev[k]
        if cell['kind'] == 'exact':
            assert ev['full_candidate_space']
            if ev['state'] == 'optimal':
                assert abs(ev['lower_bound'] - ev['upper_bound']) < 2e-4
        if cell['kind'] == 'timing':
            assert not ev['solver_started'] and not ev['reporting_scan_in_timed_region']
            assert ev['common_constructor_statistics_passes'] == 1
            row.update(repeat=cell['repeat'], shared_source_sha256=ev['shared_source_sha256'])
        records.append(row)
        print(f'{suite}: checked {len(records)}/{len(spec["cells"])} {cell["id"]}', flush=True)
    suites[suite] = dict(settings=spec['settings'], finished=finished, records=records)
    # Hash immutable campaign artifacts, including nested solver phases and logs.
    for path in campaign.rglob('*'):
        if path.is_file() and path.name != '.run.lock':
            snapshots[str(path.relative_to(ROOT))] = sha(path)

groups = defaultdict(dict)
timing_rows = []
for case in dict.fromkeys(r['case'] for r in suites['timing']['records']):
    rows = [r for r in suites['timing']['records'] if r['case'] == case]
    assert len(rows) == 12 and len({r['shared_source_sha256'] for r in rows}) == 1
    assert [r['arm'] for r in rows] == ['pjob', 'wafer', 'wafer', 'pjob'] * 3
    out = {'case': case}
    for arm in ('pjob', 'wafer'):
        vals = [r['preparation_seconds'] for r in rows if r['arm'] == arm]
        out[arm] = dict(mean=mean(vals), sample_sd=stdev(vals), values=vals)
    out['reduction_percent'] = 100 * (1 - out['pjob']['mean'] / out['wafer']['mean'])
    timing_rows.append(out)

witness_dir = PAPER / 'results/review_followup_parallel_20261102_01/runs/n2_4x1_t180_H3_qualified'
witness = read(witness_dir / 'result.json')
production = [c for c in witness['cycles'] if c['mode'] != 'clean']
assert len(production) == 2 and {c['chamber'] for c in production} == {2, 3}
overlap = min(c['end'] for c in production) - max(c['start'] for c in production)
assert abs(overlap - 163) < 2e-4
report = dict(
    audited_utc=datetime.now(timezone.utc).isoformat(),
    source_before_sha256=sha(HERE / 'original/JMS_Review_CN.tex'),
    suites=suites, timing=timing_rows,
    witness=dict(cycles=production, products=[j for j in witness['jobs'] if j['product']], overlap=overlap),
    physical_replays=len(checked), rebuilt_original_models=len(rebuilt),
    explicit_identity_rechecks=6,
    independent_optimization_calls=0, raw_file_hashes=snapshots,
)
(HERE / 'audit_results.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', 'utf-8')
print(json.dumps({'physical_replays':len(checked), 'full_models':len(rebuilt), 'hashed_files':len(snapshots),
                  'timing_reductions':[round(r['reduction_percent'], 4) for r in timing_rows]}, indent=2), flush=True)

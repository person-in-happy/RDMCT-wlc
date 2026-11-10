"""Read-only A/B evidence audit. Rebuild assignments, never optimize or write LPs."""
from pathlib import Path
from collections import Counter, defaultdict
from datetime import datetime, timezone
from statistics import mean
import hashlib
import json
import math
import shutil
import sys
import psutil

OUT = Path(__file__).resolve().parent
JMS = OUT.parents[1]
ROOT = JMS.parent
sys.path.insert(0, str(JMS / 'tools'))
import journal_support_experiments as support
j = support.base
FOLDERS = ('journal_d_standard_t1_20261108_unlimited_r1',
           'journal_d_backfill_standard_20261109_r1',
           'journal_d_mechanism_20261109_r1')
HASHES = {}


def sha(path):
    path = Path(path).resolve()
    if str(path) not in HASHES:
        HASHES[str(path)] = j.digest(path)
    return HASHES[str(path)]


def equal(a, b, label):
    if isinstance(a, dict) and isinstance(b, dict):
        assert a.keys() == b.keys(), (label, a.keys(), b.keys())
        for k in a:
            equal(a[k], b[k], (label, k))
    elif isinstance(a, list) and isinstance(b, list):
        assert len(a) == len(b), label
        for i, (x, y) in enumerate(zip(a, b)):
            equal(x, y, (label, i))
    elif isinstance(a, (int, float)) and isinstance(b, (int, float)):
        assert math.isclose(a, b, abs_tol=2e-4, rel_tol=1e-10), (label, a, b)
    else:
        assert a == b, (label, a, b)


def backup():
    for rel in ('JMS_Review_CN.tex', 'JMS_Review_CN.pdf', 'output/pdf/JMS_Review_CN.pdf',
                'JOURNAL_REVIEW_CN.md', 'JOURNAL_EXPERIMENT_COMMANDS.md'):
        src, dst = JMS / rel, OUT / 'before' / rel
        if not dst.exists():
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
    # The other manuscript copy is intentionally not synchronized.
    sha(ROOT / 'JMS/JMS_Review_CN.tex')


def main():
    backup()
    campaigns, allrows = [], []
    for name in FOLDERS:
        folder = JMS / 'results' / name
        spec = j.read(folder / 'campaign.json')
        assert sha(folder / 'campaign.json') == j.read(folder / 'contract.json')['campaign_sha256']
        for rel, expected in spec['assets'].items():
            assert sha(ROOT / rel) == expected, ('current code', rel)
            assert sha(folder / 'frozen_code' / rel) == expected, ('frozen code', rel)
        for p, expected in spec['sources'].items():
            assert sha(p) == expected, ('input', p)
        done = j.read(folder / 'finished.json')
        assert done['expected'] == done['complete'] == len(spec['cells'])
        assert done['failed'] == done['pending'] == 0
        st = spec['settings']
        assert st['memory_policy'] == 'scip_native_unlimited_system_available_fraction'
        assert st['memory_mb'] > 1e12 and st['process_memory_mb'] is None
        assert st['jobs'] == st['threads'] == 1
        rows = []
        for c in spec['cells']:
            run = folder / 'runs' / c['id']
            e, data, resources = [j.read(run / p) for p in ('evidence.json', 'result.json', 'resources.json')]
            assert e['cell'] == c and resources['exit_code'] == 0 and not (run / 'failure.json').exists()
            assert e['result_sha256'] == sha(run / 'result.json')
            assert data['config'] == j.read(c['config'])
            assert data['config']['max_pairs'] == data['config']['max_cycles'] == 0
            row = dict(campaign=name, suite=spec['suite'], id=c['id'], case=c['case'], arm=c['arm'],
                       seed=c['seed'], training_seed=c['training_seed'], valid=e['valid'], state=e['state'],
                       metrics=None, primary_bound=e['primary_bound'], gap=e.get('primary_gap'),
                       wall_seconds=resources['wall_seconds'], resources=resources,
                       input_sha256=sha(c['values']) if c.get('values') else None,
                       config=data['config'])
            equal(data['primary_status'], e['state'], 'solver state')
            equal(data['primary_bound'], e['primary_bound'], 'solver bound')
            assert bool(data['solutions']) == e['valid']
            p = run / ('solve' if spec['suite'] == 'mechanism' else 'primary')
            manifest, phase = j.read(p / 'manifest.json'), j.read(p / 'phase1.json')
            assert manifest['config'] == data['config']
            assert manifest['seed'] == c['seed'] and manifest['stage2_limit'] == 0
            assert manifest['cut_profile'] == 'standard' and manifest['initialization'] == 'none'
            nominal = st['time_limit'] * (.8 if c.get('spbs') else 1.)
            equal(manifest['time_limit'], nominal, 'budget')
            equal(phase['dual_bound'], e['primary_bound'], 'saved bound')
            row.update(solve_seconds=phase['solve_seconds'], allocated_solver_seconds=nominal,
                       budget_overrun_seconds=max(0., phase['solve_seconds'] - nominal))
            if 'budget_overrun_seconds' in e:
                equal(row['budget_overrun_seconds'], e['budget_overrun_seconds'], 'overrun')
            if spec['suite'] == 'mechanism':
                assert manifest['cleaning_rule'] == c['arm'] and manifest['method'] == 'scip'
            else:
                assert manifest['policy'] == c['policy'] == j.policy_record(c['method'], c['training_seed'])
                assert manifest['method'] == c['method']
                assert j.read(p / 'warm_start_check.json')['accepted']
                assert e['common_input_sha256'] == row['input_sha256']
                row.update(post_initialization_cmax=e['spbs_levels'][-1]['cmax'] if e['spbs_levels'] else e['source_metrics']['product_cmax'],
                           initialization_wall_seconds=e['initialization_wall_seconds'],
                           primary_wall_seconds=e['primary_wall_seconds'],
                           callback_calls=(e.get('telemetry') or {}).get('callback_calls'))
            if c.get('values'):
                assert j.read(p / 'warm_start_check.json')['accepted']
            for mp in run.rglob('manifest.json'):
                m = j.read(mp)
                if m.get('lp_sha256'):
                    assert sha(mp.with_name('model.lp.gz')) == m['lp_sha256']
                for rel, expected in m.get('assets', {}).items():
                    assert sha(ROOT / rel) == expected
            if e['valid']:
                assert data['original_model_check']
                assert sha(run / 'variables.json') == e['variables_sha256']
                replay = j.validate(data)
                assert replay['valid'], (c['id'], replay)
                met = support.metrics(data)
                equal({k: met[k] for k in e['metrics']}, e['metrics'], ('metrics', c['id']))
                if spec['suite'] == 'mechanism' and c['arm'] == 'legacy':
                    assert met['legacy_rule_feasible'], c['id']
                # Avoid pressure on the independently running qualification campaign.
                assert psutil.virtual_memory().available / psutil.virtual_memory().total > .20
                fresh = j.strengthening.audit_full(j.backend.Config(**data['config']),
                                                 j.read(run / 'variables.json')['values'], data)
                assert fresh['valid'] and fresh['original_model_check'] and not fresh['solver_started']
                row.update(metrics=met, replay=replay, fresh_original_audit=fresh)
                if e['state'] == 'optimal':
                    equal(e['primary_bound'], met['product_cmax'], 'closed objective bound')
            else:
                assert spec['suite'] == 'mechanism' and e['state'] == 'timelimit'
                assert not (run / 'variables.json').exists()
            rows.append(row)
            if len(rows) % 12 == 0:
                print(f'{name}: checked={len(rows)}/{len(spec["cells"])} failed=0 solver_started=False', flush=True)
        assert sum(r['valid'] for r in rows) == done['valid']
        # Keep all existing output records, including interrupted attempts, immutable.
        for f in folder.rglob('*'):
            if f.is_file() and ('frozen_code' not in f.parts) and f.suffix in ('.json', '.log', '.gz'):
                sha(f)
        campaigns.append(dict(name=name, suite=spec['suite'], coverage=done, settings=st,
                              states=dict(Counter(r['state'] for r in rows)),
                              min_available_fraction=min(r['resources']['min_system_available_fraction'] for r in rows),
                              interrupted_attempts=[d.name for d in (folder / 'interrupted_attempts').glob('*') if d.is_dir()]))
        allrows.extend(rows)
    a = [r for r in allrows if r['suite'] != 'mechanism']
    b = [r for r in allrows if r['suite'] == 'mechanism']
    assert len(a) == 168 and len(b) == 144 and sum(r['valid'] for r in allrows) == 221
    contrasts = support.contrasts(a)
    equal(contrasts, j.read(JMS / 'results' / FOLDERS[1] / 'summary/analysis.json')['contrasts'], 'A saved contrasts')
    for case in {r['case'] for r in a}:
        assert len({r['input_sha256'] for r in a if r['case'] == case}) == 1
    ag = defaultdict(list)
    for r in a:
        ag[r['case'], r['arm'], r['training_seed']].append(r)
    a_table = [dict(case=k[0], arm=k[1], training_seed=k[2],
                    cmax=[r['metrics']['product_cmax'] for r in rr],
                    mean_cmax=mean(r['metrics']['product_cmax'] for r in rr),
                    post_initialization_cmax=[r['post_initialization_cmax'] for r in rr])
               for k, rr in sorted(ag.items())]
    bg = defaultdict(list)
    for r in b:
        bg[r['case'], r['arm']].append(r)
    b_table = []
    for (case, arm), rr in sorted(bg.items()):
        valid = [r for r in rr if r['valid']]
        b_table.append(dict(case=case, arm=arm, count=len(rr), valid=len(valid),
                            optimal=sum(r['state'] == 'optimal' for r in rr),
                            best_bound=max(r['primary_bound'] for r in rr),
                            best_upper=min((r['metrics']['product_cmax'] for r in valid), default=None),
                            cmax_by_seed={r['seed']: r['metrics']['product_cmax'] if r['valid'] else None for r in rr},
                            cleanings=[r['metrics']['cleanings'] for r in valid],
                            modeled_completion=[r['metrics']['modeled_completion'] for r in valid]))
    for case in {r['case'] for r in b}:
        rr = [r for r in b if r['case'] == case]
        assert len({json.dumps(r['config'], sort_keys=True) for r in rr}) == 1
        assert len({r['input_sha256'] for r in rr}) == 1
    report = dict(checked_utc=datetime.now(timezone.utc).isoformat(), solver_started=False,
                  total=312, fresh_validated=221, campaigns=campaigns, rows=allrows, hashes=HASHES,
                  a_contrasts=contrasts, a_table=a_table, b_table=b_table,
                  b_coupled_witnesses=[r['id'] for r in b if r['valid'] and r['metrics']['coupled_witness']],
                  b_early_cleaning=[r['id'] for r in b if r['valid'] and r['metrics']['early_cleanings']],
                  budget_overruns=[dict(campaign=r['campaign'], id=r['id'], seconds=r['solve_seconds'],
                                       allotted=r['allocated_solver_seconds']) for r in allrows if r['budget_overrun_seconds'] > .001])
    j.dump(OUT / 'evidence.json', j.finite(report))
    j.dump(OUT / 'tables.json', j.finite(dict(a=a_table, b=b_table, contrasts=contrasts)))
    print(json.dumps(dict(total=312, fresh_validated=221, hashes=len(HASHES), solver_started=False,
                          coupled_witnesses=len(report['b_coupled_witnesses']),
                          budget_overruns=len(report['budget_overruns']))), flush=True)


if __name__ == '__main__':
    main()

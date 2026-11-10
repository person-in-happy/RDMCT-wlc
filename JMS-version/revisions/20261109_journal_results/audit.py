"""Read-only audit of all journal supplements; fresh replay and assignment checks.

Never optimize, regenerate LPs or modify campaign files.
"""
from pathlib import Path
from collections import Counter, defaultdict
from statistics import mean
from datetime import datetime, timezone
import hashlib
import json
import math
import shutil
import sys

ROOT = Path(__file__).resolve().parents[3]
JMS = ROOT / 'JMS-version'
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(JMS / 'tools'))
import journal_gap_experiments as j
import thesis_gap_experiments as t

def backup():
    for rel in ('JMS_Review_CN.tex', 'JMS_Review_CN.pdf', 'output/pdf/JMS_Review_CN.pdf',
                'JOURNAL_REVIEW_CN.md', 'JOURNAL_EXPERIMENT_COMMANDS.md'):
        target = OUT / 'before' / rel
        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(JMS / rel, target)

hashes = {}
def sha(path):
    p = Path(path).resolve()
    if str(p) not in hashes:
        hashes[str(p)] = j.digest(p)
    return hashes[str(p)]

def eq(a, b, label):
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        assert math.isclose(a, b, rel_tol=0, abs_tol=2e-4), (label, a, b)
    else:
        assert a == b, (label, a, b)

def metrics_equal(a, b, label):
    for k in a:
        eq(a[k], b[k], (label, k))

def main():
    backup()
    campaigns = []
    all_rows = []
    for folder in sorted((JMS / 'results').glob('journal_d_*')):
        spec = j.read(folder / 'campaign.json')
        assert sha(folder / 'campaign.json') == j.read(folder / 'contract.json')['campaign_sha256']
        for rel, expected in spec['assets'].items():
            assert sha(ROOT / rel) == expected, ('current_asset', rel)
            assert sha(folder / 'frozen_code' / rel) == expected, ('frozen_asset', rel)
        for path, expected in spec['sources'].items():
            assert sha(path) == expected, ('source', path)
        done = j.read(folder / 'finished.json')
        assert done['expected'] == done['complete'] == len(spec['cells']) and done['failed'] == done['pending'] == 0
        st = spec['settings']
        assert st['memory_policy'] == 'scip_native_unlimited_system_available_fraction'
        assert st['memory_mb'] >= 1e12 and st['process_memory_mb'] is None
        assert st['jobs'] == st['threads'] == 1
        rows = []
        for c in spec['cells']:
            run = folder / 'runs' / c['id']
            e, r, res = [j.read(run / n) for n in ('evidence.json', 'result.json', 'resources.json')]
            assert e['cell'] == c and res['exit_code'] == 0 and not (run / 'failure.json').exists()
            assert sha(run / 'result.json') == e['result_sha256']
            assert r['config'] == j.read(c['config'])
            if 'variables_sha256' in e:
                assert sha(run / 'variables.json') == e['variables_sha256']
            row = dict(campaign=folder.name, suite=spec['suite'], id=c['id'], case=c['case'],
                arm=c['arm'], seed=c['seed'], valid=e['valid'], state=e['state'],
                wall_seconds=res['wall_seconds'], resources=res,
                result_sha256=sha(run / 'result.json'), evidence_sha256=sha(run / 'evidence.json'),
                resources_sha256=sha(run / 'resources.json'))
            if e['valid']:
                assert r['original_model_check']
                replay = j.validate(r)
                assert replay['valid'], (c['id'], replay)
                met = j.review.physical_metrics(r)
                metrics_equal(met, e['metrics'], c['id'])
                srcmet = j.review.physical_metrics(j.read(c['source']))
                metrics_equal(srcmet, e['source_metrics'], c['id'])
                varpath = run / ('solve/variables.json' if spec['suite'] == 'structure' else 'variables.json')
                values = j.read(varpath)['values']
                # Rebuild original unrestricted D, check saved complete assignment, no solve.
                audit = j.strengthening.audit_full(j.backend.Config(**r['config']), values, r)
                assert audit['valid'] and audit['original_model_check'] and not audit['solver_started']
                row.update(metrics=met, source_metrics=srcmet, replay=replay, fresh_original_audit=audit,
                    assignment_sha256=sha(varpath), source_sha256=sha(c['source']), warm_sha256=sha(c['values']),
                    bound=e.get('primary_bound'), gap=e.get('primary_gap'))
                if spec['suite'] in ('algorithm', 'standard'):
                    assert e['full_model_audit']['valid'] and e['full_model_audit']['original_model_check']
                    assert e['common_input_sha256'] == sha(c['values'])
                    assert c['policy'] == j.policy_record(c['method'], c['training_seed'])
                    p = run / 'primary'
                    manifest, primary = j.read(p / 'manifest.json'), j.read(p / 'phase1.json')
                    assert manifest['method'] == c['method'] and manifest['cut_profile'] == c['cut_profile']
                    assert manifest['policy'] == c['policy'] and manifest['seed'] == c['seed']
                    assert manifest['initialization'] == 'none' and manifest['stage2_limit'] == 0
                    nominal = st['time_limit'] * (.8 if c['spbs'] else 1)
                    eq(manifest['time_limit'], nominal, 'nominal budget')
                    assert j.read(p / 'warm_start_check.json')['accepted']
                    assert sha(p / 'model.lp.gz') == manifest['lp_sha256']
                    eq(primary['dual_bound'], e['primary_bound'], 'bound')
                    levels = e['spbs_levels']
                    warm_cmax = levels[-1]['cmax'] if levels else srcmet['product_cmax']
                    row.update(method=c['method'], spbs=c['spbs'], training_seed=c['training_seed'],
                        nominal_primary=nominal, primary_seconds=primary['solve_seconds'],
                        primary_wall_seconds=e['primary_wall_seconds'],
                        initialization_wall_seconds=e['initialization_wall_seconds'],
                        spbs_levels=levels, post_initialization_cmax=warm_cmax,
                        telemetry=e['telemetry'], primary_only_pdi=e['primary_only_pdi'])
                    row['budget_overrun_seconds'] = max(0, row['primary_seconds'] - nominal)
                elif spec['suite'] == 'structure':
                    for phase in e['phases']:
                        p = run / phase['path']
                        assert j.read(p / 'warm_start_check.json')['accepted']
                        assert j.read(p / 'result.json')['original_model_check']
                        assert j.validate(j.read(p / 'result.json'))['valid']
                        assert sha(p / 'model.lp.gz') == j.read(p / 'manifest.json')['lp_sha256']
                    row.update(primary_seconds=e['solve_seconds'], phases=e['phases'], full_candidate_space=e['full_candidate_space'])
                else:
                    eq(met['product_cmax'], srcmet['product_cmax'], 'cleanup Cmax')
                    objective = lambda m: m['route_wait_sum'] + 10*m['route_wait_max'] + 25*m['rhythm_deviation']
                    assert objective(met) <= objective(srcmet) + 2e-4
                    row.update(primary_seconds=e['solve_seconds'], optimized_objective=e['optimized_objective'])
            else:
                assert spec['suite'] == 'rhythm_search' and e['state'] == 'timelimit' and not r['solutions']
                assert not (run / 'variables.json').exists()
                row.update(primary_seconds=e['solve_seconds'], budget_overrun_seconds=max(0,e['solve_seconds']-st['time_limit']))
            rows.append(row)
            if len(rows) % 12 == 0:
                print(folder.name, 'audited', len(rows), '/', len(spec['cells']), flush=True)
        assert sum(r['valid'] for r in rows) == done['valid']
        groups = defaultdict(list)
        for r in rows:
            if r['valid']: groups[r['case'], r['arm']].append(r)
        summary = []
        for (case, arm), rr in groups.items():
            assert sorted(x['seed'] for x in rr) == [1,2,3]
            stats = dict(case=case, arm=arm, states=dict(Counter(x['state'] for x in rr)),
                mean_cmax=mean(x['metrics']['product_cmax'] for x in rr),
                cmax_values=[x['metrics']['product_cmax'] for x in rr],
                mean_wall=mean(x['wall_seconds'] for x in rr),
                mean_solve=mean(x['primary_seconds'] for x in rr),
                improved=sum(x['metrics']['product_cmax'] < x['source_metrics']['product_cmax'] - 2e-4 for x in rr),
                mean_bound=mean(x['bound'] for x in rr) if rr[0]['bound'] is not None else None,
                mean_completion=mean(x['metrics']['modeled_completion'] for x in rr))
            if 'telemetry' in rr[0]:
                tt=[x['telemetry'] for x in rr if x['telemetry'] is not None]
                stats.update(mean_initialization=mean(x['initialization_wall_seconds'] for x in rr),
                    mean_spbs_cmax=mean(x['post_initialization_cmax'] for x in rr),
                    mean_callback_calls=mean(x['callback_calls'] for x in tt) if tt else None,
                    mean_callback_seconds=mean(x['callback_time_seconds'] for x in tt) if tt else None)
            summary.append(stats)
        campaigns.append(dict(campaign=folder.name, suite=spec['suite'], expected=len(spec['cells']),
            observed=len(rows), states=dict(Counter(x['state'] for x in rows)), valid=done['valid'],
            settings=st, campaign_sha256=sha(folder / 'campaign.json'), rows=rows, summary=summary))
        all_rows.extend(rows)
    for case in {r['case'] for r in all_rows if r['suite'] in ('algorithm','standard','structure')}:
        assert len({r['warm_sha256'] for r in all_rows if r['case']==case and r['suite'] in ('algorithm','standard','structure')}) == 1
    report=dict(checked_utc=datetime.now(timezone.utc).isoformat(), solver_started=False,
        campaigns=campaigns, hashes=hashes, fresh_validated=sum(r['valid'] for r in all_rows),
        total=len(all_rows), material_budget_overruns=[r['id'] for r in all_rows if r.get('budget_overrun_seconds',0)>1])
    j.dump(OUT / 'evidence.json', report)
    j.dump(OUT / 'tables.json', {c['suite']:c['summary'] for c in campaigns})
    print(json.dumps({k:v for k,v in report.items() if k not in ('campaigns','hashes')}), flush=True)

if __name__ == '__main__': main()

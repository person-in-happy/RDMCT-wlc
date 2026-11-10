"""Recheck selected saved assignments in the current nondecreasing model.

This is assignment verification, not a new optimization experiment.
"""
from pathlib import Path
from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import json
import shutil
import sys

HERE = Path(__file__).resolve().parent
PAPER = HERE.parents[1]
ROOT = PAPER.parent
sys.path.insert(0, str(PAPER / 'experiments/nondecreasing_followup_20261102'))
import followup_models as f
from strengthen_models import same_replay


def read(p):
    return json.loads(p.read_text('utf-8'))


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


class NoOptimize(f.REAL_MODEL):
    def optimize(self, *a, **kw):
        raise AssertionError('No optimization permitted in this audit')


class WaferNoOptimize(f.WaferModel):
    def optimize(self, *a, **kw):
        raise AssertionError('No optimization permitted in this audit')


f.scip.Model = NoOptimize
f.WaferModel = WaferNoOptimize
tasks, snapshots, campaigns = [], {}, {}


def add(category, dest, result='result.json', values='variables.json', **extra):
    tasks.append(dict(category=category, dest=dest, result=result, values=values, **extra))


new = PAPER / 'results/nondecreasing_followup_exact_20261102_205212'
spec = read(new / 'campaign.json')
assert spec['release_order_rule'] == 'global_pjob_index_nondecreasing_lp_pickup'
assert sha(new / 'campaign.json') == read(new / 'contract.json')['campaign_sha256']
assert read(new / 'finished.json')['complete'] == 24
for relative, expected in spec['assets'].items():
    assert sha(ROOT / relative) == expected
    assert sha(new / 'frozen_code' / relative) == expected
for cell in spec['cells']:
    dest = new / 'runs' / cell['id']
    ev = read(dest / 'evidence.json')
    assert ev['valid'] and read(dest / 'resources.json')['exit_code'] == 0
    for name, expected in ev['output_hashes'].items():
        assert sha(dest / name) == expected
    add('new_exact', dest, cell=cell, evidence=ev)
campaigns[new.name] = dict(finished=read(new / 'finished.json'), settings=spec['settings'])
for name, category in (
    ('pjob_fifo_paper_all_20261030_075555', 'basic'),
    ('pjob_fifo_qualification_all_20261030_120650', 'qualification'),
    ('pjob_fifo_rhythm_all_20261030_124059', 'rhythm'),
):
    campaign = PAPER / 'results' / name
    for cell in read(campaign / 'campaign.json')['cells']:
        if cell['variant'] != 'refined' and not (category == 'rhythm' and cell['variant'] in ('waiting_only', 'quadratic')):
            continue
        dest = campaign / 'runs' / cell['id']
        add(category, dest, cell=cell)
        if cell['variant'] == 'refined':
            add(category, dest, 'phase1.json', 'variables_phase1.json', cell=cell)

campaign = PAPER / 'results/review_cleanup_20261101_103259'
for cell in read(campaign / 'campaign.json')['cells']:
    add('cleanup', campaign / 'runs' / cell['id'], cell=cell)
add('qualified_parallel', PAPER / 'results/review_followup_parallel_20261102_01/runs/n2_4x1_t180_H3_qualified')
campaign = PAPER / 'results/review_followup_residency_20261102_01'
for cell in read(campaign / 'campaign.json')['cells']:
    dest = campaign / 'runs' / cell['id']
    if read(dest / 'evidence.json')['valid']:
        add('residency_witness', dest, cell=cell)

groups = defaultdict(list)
for t in tasks:
    data = read(t['dest'] / t['result'])
    t['data'] = data
    key = json.dumps(data['config'], sort_keys=True)
    groups[key].append(t)
    for name in (t['result'], t['values']):
        path = t['dest'] / name
        snapshots[str(path.relative_to(ROOT))] = sha(path)
rows, failures = [], []
for index, (key, group) in enumerate(groups.items(), 1):
    cfg = f.backend.Config(**json.loads(key))
    x = f.backend.Integrated(cfg)
    try:
        for t in group:
            row = {k: v for k, v in t.items() if k not in ('data', 'dest', 'evidence')}
            row['directory'] = str(t['dest'].relative_to(ROOT))
            row['source_sha256'] = snapshots[str((t['dest'] / t['result']).relative_to(ROOT))]
            try:
                values = read(t['dest'] / t['values'])['values']
                sol = f.assignment_solution(x, values)
                data = x.result(solution=sol)
                check = f.validate(data)
                assert check['valid'], check
                assert data['release_order_rule'] == 'global_pjob_index_nondecreasing_lp_pickup'
                for field, keyfield in (('events', 'name'), ('jobs', 'name'), ('pairs', 'id')):
                    assert same_replay({r[keyfield]:r for r in data[field]}, {r[keyfield]:r for r in t['data'][field]}), field
                assert same_replay(data['cycles'], t['data']['cycles']), 'cycles'
                row.update(valid=True, original_model_check=True, physical_validation=check,
                           metrics=f.numbers(data), dimensions=x.original_dimensions)
                if t['category'] == 'new_exact':
                    row['evidence'] = {k: t['evidence'].get(k) for k in ('state','lower_bound','upper_bound','gap','solve_seconds','full_candidate_space','dimensions')}
                    row['picks'] = [{k:j[k] for k in ('identity','pair','loan_start','loan_end','pjob','pjob_index')} for j in data['jobs'] if j['product']]
                    row['cycles'] = data['cycles']
                if t['category'] == 'qualified_parallel':
                    row['cycles'] = data['cycles']
                x.model.freeSol(sol)
            except Exception as error:
                row.update(valid=False, error=str(error))
                failures.append(row)
            rows.append(row)
            print(f'checked {len(rows)}/{len(tasks)} valid={row["valid"]} {t["category"]} {t["dest"].name}/{t["result"]}', flush=True)
    finally:
        x.model.freeProb()
    del x
    # Explicit identity decisions in the new wafer arm are checked separately.
    for t in group:
        if t['category'] == 'new_exact' and t['cell']['kind'] == 'exact' and t['cell']['arm'] == 'wafer':
            x = f.build_fair(cfg, 'wafer')
            try:
                sol = f.assignment_solution(x, read(t['dest'] / t['values'])['values'])
                f.assert_wafer_decode(x, sol, t['data'])
                x.model.freeSol(sol)
            finally:
                x.model.freeProb()

counts = {cat: sum(r['category'] == cat for r in rows) for cat in sorted({r['category'] for r in rows})}
report = dict(audited_utc=datetime.now(timezone.utc).isoformat(),
    model_sha256=sha(PAPER / 'model4_pjob_nondecreasing_20261102/model.py'),
    release_code_sha256=sha(PAPER / 'model4_pjob_nondecreasing_20261102/pjob_order.py'),
    rule='global_pjob_index_nondecreasing_lp_pickup',
    original_models_built=len(groups), assignments_checked=len(rows), counts=counts,
    optimization_calls=0, failures=failures, rows=rows, campaigns=campaigns, hashes=snapshots)
(HERE / 'newrule_validation.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n','utf-8')
assert not failures, [(r['directory'],r['error']) for r in failures]
print(json.dumps(dict(passed=len(rows), models=len(groups), counts=counts, optimization_calls=0), indent=2), flush=True)

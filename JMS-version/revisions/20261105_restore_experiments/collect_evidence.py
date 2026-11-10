"""Read-only audit of saved experiments; never builds or runs a solver."""
import ast
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
JMS = ROOT / 'JMS-version'
PROTOCOL = sys.argv[1]
BACKEND = JMS / ('model4_pjob_nonprocessing_20261103' if PROTOCOL == 'current' else 'model4_pjob_nondecreasing_20261102')
sys.path.insert(0, str(BACKEND))
from validate import validate

# Load only the pure metric function, without importing the solver or launchers.
metric_source = (BACKEND / 'revalidate.py').read_text(encoding='utf-8')
metric_node = next(n for n in ast.parse(metric_source).body if isinstance(n, ast.FunctionDef) and n.name == 'metrics')
exec(compile(ast.Module(body=[metric_node], type_ignores=[]), str(BACKEND / 'revalidate.py'), 'exec'))

def read(p):
    return json.loads(Path(p).read_text(encoding='utf-8-sig'))

def sha(p):
    h = hashlib.sha256()
    with Path(p).open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()

def replay(p):
    d = read(p)
    r = dict(path=str(p.relative_to(ROOT)), sha256=sha(p), status=d.get('status'),
             primary_status=d.get('primary_status', d.get('status')), solutions=d.get('solutions', 0),
             cmax=d.get('cmax'), bound=d.get('primary_bound', d.get('dual_bound')),
             original_model_check=d.get('original_model_check'),
             full_candidate_space=d.get('full_candidate_space', not d.get('restricted_candidate_bounds', True)))
    if r['solutions']:
        v = validate(d)
        r['replay'] = v
        r['metrics'] = metrics(d)
        r['metrics']['product_cmax'] = v.get('product_return_cmax')
        ends = [e['end'] for e in d['events']] + [e['end'] for e in d['cycles']]
        for e in d['events']:
            if e['kind'] == 'source_pick' and e['location'] == 'U':
                ends.append(e['end'] + d['config']['upper_reset'])
            if e['kind'] == 'lower_pick':
                ends.append(e['end'] + d['config']['lower_reset'])
        r['metrics']['modeled_completion'] = max(ends, default=0)
    return r

names = (['current_defaults_small_prepared_20261103', 'current_defaults_paper_20261104_075634',
          'current_defaults_cuts_20261104_100149', 'current_defaults_gantt_20261103_222109',
          'current_defaults_crossover_20261104_163238'] if PROTOCOL == 'current' else
         ['nondecreasing_followup_exact_20261102_205212', 'nondecreasing_review_baseline_20261103_112023',
          'nondecreasing_review_rhythm_20261103_135933', 'pjob_nondecreasing_paper_all_20261102_231102',
          'pjob_nondecreasing_qualification_all_20261103_032308'])
report = dict(created_utc=datetime.now(timezone.utc).isoformat(), protocol=PROTOCOL,
              validation_scope='Fresh physical replay and event metrics; saved original-model certificates and artifact hashes. No optimization.',
              validator_hashes={f.name: sha(f) for f in [BACKEND/'validate.py', BACKEND/'physical_validate.py', BACKEND/'pjobs.py', BACKEND/'pjob_order.py', BACKEND/'revalidate.py']}, campaigns=[])
for name in names:
    folder = JMS / 'results' / name
    spec = read(folder / 'campaign.json')
    cells = spec['cells']
    if PROTOCOL == 'extended' and name.startswith('pjob_nondecreasing'):
        cells = [c for c in cells if c.get('variant') == 'refined']
    if name.startswith('nondecreasing_followup_exact'):
        cells = [c for c in cells if c.get('kind') == 'exact']
    entry = dict(name=name, campaign_sha256=sha(folder/'campaign.json'), settings=spec.get('settings', {k: spec.get(k) for k in ['time_limit','spbs_budget','cut_profile','memory_mb','seeds','accounting']}), expected=len(cells), rows=[], hash_checks=[], hash_errors=[])
    if (folder/'contract.json').exists():
        contract = read(folder/'contract.json')
        expected = contract.get('campaign_sha256')
        if expected:
            entry['hash_checks'].append('campaign contract')
            if expected != entry['campaign_sha256']: entry['hash_errors'].append('campaign contract')
    for key, digest in spec.get('assets', {}).items():
        if not isinstance(digest, str): continue
        source = ROOT / key
        frozen = folder / 'frozen_code' / key
        if source.exists() and sha(source) == digest:
            entry['hash_checks'].append(key)
        elif frozen.exists() and sha(frozen) == digest:
            entry['hash_checks'].append('frozen:' + key)
        else:
            entry['hash_errors'].append('asset:' + key)
    for key, digest in spec.get('configs', spec.get('case_hashes', {})).items():
        p = folder / 'configs' / (key + '.json')
        if sha(p) != digest: entry['hash_errors'].append('config:' + key)
    for c in cells:
        run = folder / 'runs' / c['id']
        p = run / 'result.json'
        row = dict(cell=c, available=p.exists())
        if p.exists():
            row.update(replay(p))
            e = read(run/'evidence.json') if (run/'evidence.json').exists() else {}
            checks = []
            if e.get('result_sha256'): checks.append((p,e['result_sha256']))
            for key, digest in e.get('output_hashes', {}).items(): checks.append((run/key,digest))
            for key, hashkey in [('source','source_sha256'), ('values','input_values_sha256')]:
                if c.get(key) and e.get(hashkey): checks.append((Path(c[key]),e[hashkey]))
            row['checked_artifact_hashes'] = {str(x.relative_to(ROOT)): sha(x) for x,h in checks}
            row['hash_errors'] = [str(x) for x,h in checks if sha(x) != h]
            row['evidence_sha256'] = sha(run/'evidence.json') if e else None
            if e.get('dimensions'): row['dimensions'] = e['dimensions']
            if e.get('full_model_audit'): row['full_model_audit'] = e['full_model_audit']
            if e.get('input_values_sha256'): row['input_values_sha256'] = e['input_values_sha256']
            if (run/'phase1.json').exists(): row['before'] = replay(run/'phase1.json')
            if c.get('source') and row.get('solutions'):
                row['source'] = replay(Path(c['source']))
            if e.get('phase1_metrics'): row['saved_phase1_metrics'] = e['phase1_metrics']
        elif (run/'failure.json').exists(): row['failure'] = read(run/'failure.json')
        entry['rows'].append(row)
    entry['counts'] = dict(expected=len(cells), observed=sum(r['available'] for r in entry['rows']),
                          replay_valid=sum(bool(r.get('replay',{}).get('valid')) for r in entry['rows']),
                          states=dict(Counter(r.get('primary_status','missing') for r in entry['rows'])))
    report['campaigns'].append(entry)
    print(name, json.dumps(entry['counts']), 'hash_errors', len(entry['hash_errors']), flush=True)
out = HERE / (PROTOCOL + '_evidence.json')
out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
print(out)

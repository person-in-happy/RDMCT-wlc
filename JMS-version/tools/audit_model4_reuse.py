"""Read-only campaign projection: certify physical witnesses, never solver performance.

Input eligibility is explicit. --all-eligible preserves the old unrestricted
chamber input; it does not certify the restricted example in gif/kexingyu.
"""
from pathlib import Path
from collections import defaultdict
import argparse, copy, hashlib, importlib.util, json, sys, time

ROOT = Path(__file__).resolve().parents[2]
VALIDATOR = ROOT/'JMS-version/joint_model/validate.py'
sys.path.insert(0, str(VALIDATOR.parent))
spec = importlib.util.spec_from_file_location('reuse_physical_validator', VALIDATOR)
physical = importlib.util.module_from_spec(spec)
spec.loader.exec_module(physical)


def read(path):
    return json.loads(path.read_text('utf-8-sig'))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def dump(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), 'utf-8')


def project(data, eligibility):
    cfg = data['config']
    if cfg.get('vtr_hand_policy') != 'clean_dirty' or cfg.get('dummy_alignment') != 'bypass_or_accompany':
        raise ValueError('Historical physical rules require a separate conversion; no automatic migration')
    if data.get('restricted_candidate_bounds', False):
        raise ValueError('Restricted candidate result requires separate scope review')
    products = {}
    for lp, counts in cfg['load_ports'].items():
        slot = 0
        for mode in ('4x1', '2x2'):
            for _ in range(counts.get(mode, 0)):
                slot += 1
                products[f'{lp}_W{slot}'] = (mode, lp)
    if set(eligibility) != set(products):
        raise ValueError('Eligibility must cover exactly the frozen product inventory')
    eligible = {w: tuple(sorted(set(v))) for w, v in eligibility.items()}
    if any(not v or not set(v) <= set(cfg['chambers']) for v in eligible.values()):
        raise ValueError('Empty or unknown allowed chambers')
    before = physical.validate(data)
    if not before['valid']:
        raise ValueError('Original witness fails physical replay: '+str(before['errors'][:3]))
    horizon = cfg['horizon']
    if any(e['end'] > horizon+physical.TOL for e in data['events']+data['cycles']):
        raise ValueError('Physical event exceeds the frozen time horizon')
    pairs = {p['id']: p for p in data['pairs']}
    picks = {e['job']: e['start'] for e in data['events'] if e['kind'] == 'origin_pick'}
    group = defaultdict(list)
    keys = sorted({(mode, eligible[w]) for w, (mode, lp) in products.items()})
    ids = {key: f'Pjob{i+1}' for i, key in enumerate(keys)}
    for job in data['jobs']:
        if not job['product']:
            continue
        w = job['identity']; mode, lp = products[w]
        if pairs[job['pair']]['chamber'] not in eligible[w]:
            raise ValueError('Frozen eligibility violated: '+w)
        group[mode, eligible[w], lp].append(job)
    mapping, tasks = {}, {}
    for (mode, chambers, lp), jobs in sorted(group.items()):
        pjob = ids[mode, chambers]
        task = tasks.setdefault(pjob, dict(id=pjob, mode=mode, chambers=list(chambers), inventory={}, wafer_ids={}))
        labels = sorted((j['identity'] for j in jobs), key=lambda w: int(w.split('_W')[1]))
        task['inventory'][lp] = len(labels); task['wafer_ids'][lp] = labels
        ordered = sorted(jobs, key=lambda j: (picks[j['name']], j['pair'], pairs[j['pair']]['members'].index(j['identity'])))
        mapping.update((j['identity'], w) for j, w in zip(ordered, labels))
    # Retain only physical data. Model2 bounds, times and statuses stay in source files.
    projected = {k: copy.deepcopy(data[k]) for k in ('config', 'events', 'jobs', 'pairs', 'cycles', 'cmax')}
    projected.update(schema=1, solutions=1, model_scope='model4_physical_projection', pjobs=list(tasks.values()))
    for job in projected['jobs']:
        if job['product']:
            job['identity'] = mapping[job['identity']]
    for pair in projected['pairs']:
        pair['members'] = [mapping.get(w, w) for w in pair['members']]
    after = physical.validate(projected)
    if not after['valid'] or before['product_return_cmax'] != after['product_return_cmax']:
        raise ValueError('Decoded witness failed physical replay or changed objective')
    assert data['events'] == projected['events'] and data['cycles'] == projected['cycles']
    # Job names are stable operation handles; identity is the decoded wafer label.
    for a, b in zip(data['jobs'], projected['jobs']):
        assert {k:v for k,v in a.items() if k!='identity'} == {k:v for k,v in b.items() if k!='identity'}
    return projected, dict(physical=after, identity_map=mapping, pjob_count=len(tasks),
        nonempty_task_lp_groups=len(group), physical_times_unchanged=True,
        model4_milp_constraint_check=None, performance_reused=False, optimality_transferred=False)


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('--campaign', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    eligibility = parser.add_mutually_exclusive_group(required=True)
    eligibility.add_argument('--all-eligible', action='store_true')
    eligibility.add_argument('--eligibility-json', type=Path, help='JSON: case ID -> wafer identity -> allowed chamber list')
    args = parser.parse_args()
    source, out = args.campaign.resolve(), args.output.resolve()
    if not out.is_relative_to(ROOT) or out == source or out.is_relative_to(source):
        parser.error('Use a new workspace output directory outside the source campaign')
    contract = read(source/'campaign.json')
    explicit = read(args.eligibility_json) if args.eligibility_json else None
    out.mkdir(parents=True, exist_ok=False)
    dump(out/'input_contract.json', dict(source=str(source), campaign_sha256=sha(source/'campaign.json'),
        validator_sha256=sha(VALIDATOR), grippers_sha256=sha(VALIDATOR.with_name('grippers.py')),
        auditor_sha256=sha(Path(__file__)),
        qualification='all products eligible for all frozen chambers' if args.all_eligible else explicit,
        eligibility_sha256=sha(args.eligibility_json) if explicit is not None else None,
        scope='Physical projection only; no model4 solve or new performance observations'))
    rows=[]; started=time.monotonic()
    for index, cell in enumerate(contract['cells'], 1):
        row = dict(id=cell['id'], case=cell['case'])
        run = source/'runs'/cell['id']
        try:
            cert = read(run/'evidence.json')
            result = run/'result.json'
            if not cert.get('complete') or not cert.get('original_model_check') or not cert.get('physical', {}).get('valid'):
                row.update(status='not_eligible', reason='No accepted original witness; old failure status retained')
            else:
                if sha(result) != cert['result_sha256']:
                    raise ValueError('Frozen result hash mismatch')
                data=read(result)
                qualification = {j['identity']: data['config']['chambers'] for j in data['jobs'] if j['product']} if args.all_eligible else explicit[cell['case']]
                projected, report = project(data, qualification)
                dest=out/cell['id'];dest.mkdir()
                dump(dest/'physical_witness.json', projected)
                dump(dest/'certificate.json', report|dict(source_result_sha256=sha(result),
                    source_certificate_sha256=sha(run/'evidence.json'), witness_sha256=sha(dest/'physical_witness.json')))
                row.update(status='physical_projection_valid', product_return_cmax=report['physical']['product_return_cmax'],
                    pjobs=report['pjob_count'], groups=report['nonempty_task_lp_groups'])
        except FileNotFoundError:
            row.update(status='not_eligible', reason='No completed original evidence; pending/failure remains unchanged')
        except (ValueError, KeyError, AssertionError) as exc:
            row.update(status='rejected', reason=str(exc))
        rows.append(row)
        elapsed=time.monotonic()-started
        print(f"audited={index}/{len(contract['cells'])} valid={sum(r['status']=='physical_projection_valid' for r in rows)} rejected={sum(r['status']=='rejected' for r in rows)} ETA={elapsed/index*(len(contract['cells'])-index):.1f}s", flush=True)
    report=dict(rows=rows, counts={k:sum(r['status']==k for r in rows) for k in ('physical_projection_valid','not_eligible','rejected')},
        model4_solver_runs=0, original_campaign_modified=False)
    dump(out/'audit.json', report)
    print(json.dumps(report['counts']), flush=True)
    if report['counts']['rejected']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()

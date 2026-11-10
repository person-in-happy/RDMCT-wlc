"""Read-only revalidation and aggregation of completed strict-Pjob campaigns."""
from pathlib import Path
import collections
import hashlib
import json
import sys
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
BACKEND = ROOT / 'JMS-version/model4_pjob_fifo_20261029'
sys.path.insert(0, str(BACKEND))
import evidence_supplement as e
from run_experiments import digest, dump


def main():
    records, campaigns, failures = [], [], []
    start = time.monotonic()
    for folder in sorted((ROOT / 'JMS-version/results').glob('pjob_fifo*')):
        if not (folder / 'campaign.json').exists():
            continue
        spec, contract = e.checked(folder)
        e.ensure_idle(folder)
        audits = sorted((folder / 'audits').glob('audit_*.json'))
        if not audits:
            raise RuntimeError('Missing completed audit: ' + str(folder))
        audit_path = audits[-1]
        audit = e.read(audit_path)
        before = {str(p): digest(p) for p in (folder / 'campaign.json', folder / 'supplement.json', audit_path)}
        configs = {k: e.read(folder / 'configs' / (k + '.json')) for k in spec['case_hashes']}
        summary = dict(name=folder.name, suite=spec['suite'], settings=contract['settings'],
                       environment=contract['environment'], expected=len(spec['cells']),
                       audit=str(audit_path), audit_sha256=digest(audit_path),
                       case_configs=configs, validated=0, feasible=0, failures=0)
        for idx, cell in enumerate(spec['cells'], 1):
            run = folder / 'runs' / cell['id']
            if not (run / 'evidence.json').exists():
                failure = e.read(run / 'failure.json')
                failures.append(dict(campaign=folder.name, **cell, failure=failure,
                                     sha256=digest(run / 'failure.json')))
                summary['failures'] += 1
                continue
            row = e.check_cell(folder, cell)
            result, primary, ev = (e.read(run / name) for name in ('result.json', 'phase1.json', 'evidence.json'))
            row.update(campaign=folder.name, suite=spec['suite'],
                       final_status=result['status'], final_phase=result.get('phase', 'primary'),
                       secondary_solve_seconds=result.get('solve_seconds') if result.get('phase') == 'secondary' else None,
                       phase1_cmax=primary.get('cmax'), initial_cmax=ev['initial_cmax'],
                       structure_changed=ev['structure_changed'],
                       product_count=sum(sum(v.values()) for v in configs[cell['case']]['load_ports'].values()),
                       h=configs[cell['case']]['cleaning_interval'], source=configs[cell['case']]['source'])
            records.append(row)
            summary['validated'] += 1
            summary['feasible'] += int(row['has_solution'])
            if idx % 15 == 0 or idx == len(spec['cells']):
                print(f"{folder.name}: checked={idx}/{len(spec['cells'])}; total={len(records)}; elapsed={time.monotonic()-start:.0f}s", flush=True)
        for path, sha in before.items():
            assert digest(Path(path)) == sha, path
        campaigns.append(summary)
        dump(HERE / 'verified_results.partial.json', dict(campaigns=campaigns, rows=records, failures=failures))
    report = dict(created_utc=e.stamp(), campaigns=campaigns, rows=records, failures=failures,
                  completed=len(records), feasible=sum(r['has_solution'] for r in records),
                  original_attempt_failures=len(failures),
                  primary_states=dict(collections.Counter(r['status'] for r in records)),
                  source_assets_sha256=digest(BACKEND / 'model.py'),
                  audit_script_sha256=digest(Path(__file__)),
                  all_raw_campaigns_read_only=True, elapsed_seconds=time.monotonic()-start)
    dump(HERE / 'verified_results.json', report)
    print(json.dumps({k:v for k,v in report.items() if k not in ('campaigns','rows','failures')},ensure_ascii=False),flush=True)


if __name__ == '__main__':
    main()

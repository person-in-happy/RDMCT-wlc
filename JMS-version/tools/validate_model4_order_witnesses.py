"""Replay existing order witnesses with the current Model4 backend validator.

Only adapts the historical inventory schema to explicit wafer lists. Does not
change schedules, timestamps, identities, original exports or running campaigns.
"""
from pathlib import Path
from datetime import datetime, timezone
import argparse
import gzip
import hashlib
import json
import sys

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / 'JMS-version/model4_pjob_20261027'
sys.path.insert(0, str(BACKEND))
from validate import validate
from pjobs import groups_from_config
from types import SimpleNamespace


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    base = ROOT / 'JMS-version/gif/kexingyu/model4_pjob_20261027'
    manifest = json.loads((base / 'manifest.json').read_text('utf-8'))
    report = dict(checked_utc=datetime.now(timezone.utc).isoformat(),
                  source_manifest_sha256=sha(base / 'manifest.json'),
                  validation='Current Model4 independent physical/Pjob validator; no MILP solve',
                  full_milp_solver_certification=False, records=[],
                  validator_hashes={str(p.relative_to(ROOT)): sha(p) for p in
                      (BACKEND/'validate.py', BACKEND/'physical_validate.py', BACKEND/'pjobs.py')})
    for entry in manifest['files']:
        path = base / entry['representative_witnesses']
        if sha(path) != entry['representative_sha256']:
            raise ValueError('Witness hash mismatch')
        with gzip.open(path, 'rt', encoding='utf-8') as stream:
            for line in stream:
                row = json.loads(line)
                data = row['witness']
                data['config']['pjobs'] = [dict(id=p['id'], mode=p['mode'], chambers=p['chambers'],
                    wafers=[f'{lp}_W{i}' for lp, count in p['inventory'].items()
                            for i in range(1, count+1)]) for p in data['pjobs']]
                groups_from_config(SimpleNamespace(**data['config']))
                verdict = validate(data)
                report['records'].append(dict(n=entry['n'], recipe=row['recipe'], h=row['h'],
                    rank=row['rank'], verdict=verdict))
                if not verdict['valid']:
                    raise ValueError(str(report['records'][-1]))
                print(f"Model4 replay completed={len(report['records'])}/36 failed=0", flush=True)
    if len(report['records']) != 36:
        raise ValueError('Expected 36 representative witnesses')
    report['passed'] = len(report['records'])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), 'utf-8')


if __name__ == '__main__':
    main()

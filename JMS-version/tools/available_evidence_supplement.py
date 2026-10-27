"""Use available RAM once per new campaign, without a preset solver-memory cap.

The frozen executor still reserves 2 GiB plus 15% worker overhead. Check is
read-only; resume reuses the frozen budget and never adopts failed searches.
"""
from pathlib import Path
from types import SimpleNamespace
import argparse
import json
import math
import shutil
import sys

import psutil
import evidence_supplement as e
from supplement_memory_guard import require_unfailed_budget


def allocation(available_mib, jobs=1):
    if not math.isfinite(available_mib) or available_mib <= 0 or jobs < 1:
        raise ValueError('Available memory and jobs must be positive')
    # Match the unchanged preflight and worker scheduler, without a suite cap
    # or the old automatic selector's additional 10% deduction.
    memory = math.floor((available_mib - 2048) / (1.15 * jobs) / 256) * 256
    if memory < 1024:
        raise RuntimeError('Available RAM cannot fit one GiB per worker plus executor reserves')
    return dict(policy='maximum_available_ram_v1', available_mib=available_mib,
                jobs=jobs, memory_mb=memory, cap_mb=None, reserve_mib=2048,
                worker_rss_factor=1.15, rounding_mib=256,
                required_mib=memory * 1.15 * jobs + 2048)


def gate(suite, memory, out=None):
    if out is not None and out.exists():
        spec = e.read(out / 'campaign.json')
        cases = {k: e.read(out / 'configs' / f'{k}.json') for k in spec['case_hashes']}
        assets = spec['assets']
    else:
        cases, _ = e.matrix(suite)
        spec, assets = e.defaults(suite), e.inventory()
    require_unfailed_budget(e.ROOT / 'JMS-version/results', cases, assets, spec, memory)


def select(args):
    out = e.campaign_path(args.campaign) if args.campaign else None
    available = psutil.virtual_memory().available / 1024**2
    if out is not None and out.exists():
        _, contract = e.checked(out)
        if args.suite != contract['suite']:
            raise ValueError('Suite differs from frozen campaign')
        settings = contract['settings']
        if args.jobs is not None and args.jobs != settings['jobs']:
            raise ValueError('Concurrency differs from frozen campaign')
        memory, jobs = settings['memory_mb'], settings['jobs']
        record = dict(policy='reuse_frozen_budget', available_mib=available,
                      memory_mb=memory, jobs=jobs, required_mib=memory * 1.15 * jobs + 2048)
    else:
        record = allocation(available, args.jobs if args.jobs is not None else 1)
    print('MEMORY ' + json.dumps(record), flush=True)
    if available < record['required_mib']:
        raise RuntimeError('Available RAM is below the frozen budget requirement; no resampling or solver launch')
    if out is None or not (out / 'preflight_passed.json').exists():
        gate(args.suite, record['memory_mb'], out)
    return out, record


def prepare(args):
    out, record = select(args)
    if out is None:
        raise ValueError('Prepare/start requires --campaign')
    existed = out.exists()
    e.prepare(SimpleNamespace(campaign=str(out), suite=args.suite,
                              memory_mb=record['memory_mb'], jobs=record['jobs']))
    if not existed:
        record.update(selected_utc=e.stamp(), selector_sha256=e.digest(Path(__file__)),
                      note='Frozen per campaign; no claim that the full model fits')
        e.dump(out / 'memory_selection.json', record)
        for name in ('available_evidence_supplement.py', 'supplement_memory_guard.py'):
            shutil.copy2(Path(__file__).with_name(name), out / 'frozen_code' / name)
    return out


def main():
    if len(sys.argv) > 1 and sys.argv[1] not in ('check', 'prepare', 'start', '-h', '--help'):
        return e.main()
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('action', choices=('check', 'prepare', 'start'))
    parser.add_argument('--suite', required=True, choices=e.SUITES)
    parser.add_argument('--campaign')
    parser.add_argument('--jobs', type=int, help='Defaults to one; existing campaigns reuse frozen concurrency')
    args = parser.parse_args()
    if args.jobs is not None and args.jobs < 1:
        parser.error('--jobs must be positive')
    if args.action != 'check' and not args.campaign:
        parser.error('--campaign is required for prepare/start')
    if args.action == 'check':
        select(args)
        print('MEMORY CHECK PASSED; no files created or solver started. Model fit is unverified.')
        return
    out = prepare(args)
    if args.action == 'start':
        e.preflight(out)
        e.run(out)


if __name__ == '__main__':
    try:
        main()
    except (RuntimeError, ValueError) as exc:
        print('STOP: ' + str(exc), file=sys.stderr, flush=True)
        raise SystemExit(2)

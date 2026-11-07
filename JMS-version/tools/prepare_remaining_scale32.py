"""Prepare only unfinished scale32 cells in a new frozen campaign. Never solve."""
from pathlib import Path
from argparse import ArgumentParser, Namespace
import json
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'JMS-version/model4_pjob_nonprocessing_20261103'))
import paper_defaults as driver


def selection(parent):
    spec = driver.checked(parent)
    if spec['suite'] != 'scale32':
        raise ValueError('Only the scale32 suite is supported')
    remaining, completed, snapshot = [], [], {}
    for cell in spec['cells']:
        run = parent / 'runs' / cell['id']
        result, failure = run / 'result.json', run / 'failure.json'
        if result.exists():
            # A saved timeout is a completed observation, even without an incumbent.
            data = driver.read(result)
            if 'status' not in data:
                raise ValueError('Malformed result: ' + str(result))
            completed.append(cell['id'])
            snapshot[cell['id']] = dict(state='completed', result_sha256=driver.digest(result))
        else:
            remaining.append(cell)
            snapshot[cell['id']] = dict(state='failed' if failure.exists() else 'unfinished')
            if failure.exists():
                snapshot[cell['id']]['failure_sha256'] = driver.digest(failure)
    return spec, remaining, completed, snapshot


def main():
    parser = ArgumentParser(__doc__)
    parser.add_argument('action', choices=['plan', 'prepare'])
    parser.add_argument('--parent', required=True)
    parser.add_argument('--campaign')
    parser.add_argument('--memory-mb', type=int)
    parser.add_argument('--process-memory-mb', type=int)
    args = parser.parse_args()
    parent = Path(args.parent).resolve()
    # Do not take a changing snapshot of a running queue.
    driver.ensure_idle()
    spec, remaining, completed, snapshot = selection(parent)
    report = dict(parent=str(parent), remaining=len(remaining),
                  cells=[c['id'] for c in remaining], excluded_completed=completed,
                  solver_started=False)
    if args.action == 'plan':
        print(json.dumps(report, indent=2))
        return
    if not args.campaign or args.memory_mb is None or args.process_memory_mb is None:
        parser.error('prepare requires --campaign, --memory-mb and --process-memory-mb')
    if not remaining:
        raise ValueError('No unfinished cells; no new campaign needed')
    settings = spec['settings']
    if args.process_memory_mb <= settings['process_memory_mb'] or args.memory_mb < settings['memory_mb']:
        raise ValueError('Require a higher process budget and no lower SCIP budget than the failed protocol')
    if not 0 < args.memory_mb < args.process_memory_mb:
        raise ValueError('Require 0 < SCIP budget < process RSS budget')
    available = driver.psutil.virtual_memory().available / 1024**2
    if available < args.process_memory_mb + settings['reserve_mb']:
        raise ValueError('Available RAM is below process budget plus reserve')
    out = Path(args.campaign).resolve()
    # The standard preparation validates the destination and refuses existing folders.
    parent_hash = driver.digest(parent / 'campaign.json')
    driver.prepare(Namespace(campaign=str(out), suite='scale32',
                             seeds=sorted({c['seed'] for c in spec['cells']}),
                             time_limit=settings['time_limit'], stage2_limit=settings['stage2_limit'],
                             memory_mb=args.memory_mb, process_memory_mb=args.process_memory_mb,
                             wall_limit=settings['wall_limit']))
    # Until filtering succeeds, the standard driver must not run the full generated matrix.
    driver.dump(out / 'contract.json', {'campaign_sha256': 'selection_not_finalized'})
    new_spec = driver.read(out / 'campaign.json')
    if selection(parent)[3] != snapshot or driver.digest(parent / 'campaign.json') != parent_hash:
        raise RuntimeError('Parent changed during preparation; new campaign remains blocked')
    ids = {c['id'] for c in remaining}
    new_spec['cells'] = [c for c in new_spec['cells'] if c['id'] in ids]
    if new_spec['cells'] != remaining:
        raise RuntimeError('Cell matrix changed; new campaign remains blocked')
    cases = {c['case'] for c in remaining}
    for case in cases:
        if new_spec['configs'][case] != spec['configs'][case]:
            raise RuntimeError('Configuration changed: ' + case)
        old_warm, new_warm = spec['warms'].get(case), new_spec['warms'].get(case)
        if (old_warm or {}).get('sha256') != (new_warm or {}).get('sha256'):
            raise RuntimeError('Warm start changed: ' + case)
    new_spec['selection'] = dict(parent=str(parent), parent_campaign_sha256=parent_hash,
                                 parent_cells=snapshot, excluded_completed=completed,
                                 preparation_script_sha256=driver.digest(Path(__file__)),
                                 interpretation='Unfinished cells only; changed resource budget. Do not pool with parent as a matched-budget mode comparison.')
    driver.dump(out / 'campaign.json', new_spec)
    driver.dump(out / 'contract.json', {'campaign_sha256': driver.digest(out / 'campaign.json')})
    driver.checked(out)
    print(json.dumps(report | dict(campaign=str(out), settings=new_spec['settings']), indent=2))


if __name__ == '__main__':
    main()

"""Prepare an isolated retry of memory-guard failures; never launch a solve.

The parent campaign and its reference assignments remain immutable. The new
campaign records its changed memory budget and reuses the exact reference files.
"""
from pathlib import Path
import argparse
import copy
import json
import shutil
import sys

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / 'JMS-version/model4_pjob_fifo_20261029'
sys.path.insert(0, str(BACKEND))

import evidence_supplement as evidence
from run_experiments import digest, dump
from revalidate import read, VARIANTS


def select_memory_failures(spec, audit, parent):
    """Use failure states, never observed objective values, for retry selection."""
    failures = {row['id']: row for row in audit['missing_or_failed']}
    selected = []
    for cell in spec['cells']:
        row = failures.get(cell['id'])
        if not row or row.get('failure', {}).get('reason') != 'process_memory_guard':
            continue
        folder = parent / 'runs' / cell['id']
        if (folder / 'evidence.json').exists():
            raise ValueError('Completed evidence cannot be selected as a failure: ' + cell['id'])
        if read(folder / 'failure.json') != row['failure']:
            raise ValueError('Failure record differs from parent audit: ' + cell['id'])
        selected.append(cell)
    if not selected:
        raise ValueError('No audited process-memory failures to retry')
    return selected


def prepare(args):
    parent = evidence.campaign_path(args.parent)
    out = evidence.campaign_path(args.output)
    audit_path = Path(args.audit).resolve()
    if not audit_path.is_relative_to(parent / 'audits'):
        raise ValueError('Use the saved audit inside the parent campaign')
    if out.exists() or out.is_relative_to(parent) or parent.is_relative_to(out):
        raise ValueError('Use a NEW sibling results directory, separate from the parent')
    if not 0 < args.memory_mb < args.process_memory_mb:
        raise ValueError('Require 0 < SCIP memory < process RSS ceiling')
    evidence.ensure_idle(parent)
    spec, contract = evidence.checked(parent)
    if not (parent / 'finished.json').exists():
        raise ValueError('Parent queue must have finished')
    audit = read(audit_path)
    if audit['expected'] != len(spec['cells']):
        raise ValueError('Parent audit coverage does not match its campaign')
    cells = select_memory_failures(spec, audit, parent)
    cases = list(dict.fromkeys(cell['case'] for cell in cells))
    reference_keys = list(cases)
    for cell in cells:
        if VARIANTS[cell['variant']].get('partition'):
            key = cell['case'] + '_partition'
            if key not in reference_keys:
                reference_keys.append(key)
    for key in cases:
        evidence.reference_receipt(parent, key, spec)

    parent_files = [parent / name for name in ('campaign.json', 'supplement.json', 'finished.json')]
    parent_files += [audit_path]
    parent_files += [parent / 'runs' / cell['id'] / 'failure.json' for cell in cells]
    parent_hashes = {str(path): digest(path) for path in parent_files}
    settings = copy.deepcopy(contract['settings'])
    settings.update(memory_mb=args.memory_mb, process_memory_mb=args.process_memory_mb,
                    jobs=1, seeds=list(dict.fromkeys(cell['seed'] for cell in cells)))
    lineage = dict(
        schema=1, created_utc=evidence.stamp(), reason='isolated_process_memory_retry',
        parent_campaign=str(parent), parent_audit=str(audit_path),
        parent_audit_sha256=digest(audit_path), parent_files=parent_hashes,
        selected_cells=cells, original_settings=contract['settings'], new_settings=settings,
        changed_settings={key: {'old': contract['settings'].get(key), 'new': value}
                          for key, value in settings.items() if contract['settings'].get(key) != value},
        reference_policy='Reuse byte-identical parent certificates and assignments; no new SPBS',
        interpretation='Separate memory-budget follow-up; retain all parent failures and do not pool timing comparisons',
        preparation_script=str(Path(__file__).relative_to(ROOT)),
        preparation_script_sha256=digest(Path(__file__)),
    )
    out.mkdir(parents=True, exist_ok=False)
    dump(out / 'preparation_pending.json', {'parent': str(parent), 'created_utc': evidence.stamp()})
    dump(out / 'continuation.json', lineage)
    new_spec = copy.deepcopy(spec)
    new_spec.update(created_utc=evidence.stamp(), cells=cells,
                    case_hashes={key: spec['case_hashes'][key] for key in cases},
                    continuation_sha256=digest(out / 'continuation.json'))
    new_spec.update({key: value for key, value in settings.items() if key != 'jobs'})
    new_contract = copy.deepcopy(contract)
    new_contract.update(settings=settings, scope=lineage['interpretation'])
    (out / 'configs').mkdir()
    for key in cases:
        shutil.copy2(parent / 'configs' / (key + '.json'), out / 'configs' / (key + '.json'))
    for key in reference_keys:
        shutil.copytree(parent / 'references' / key, out / 'references' / key)
    for relative, sha in spec['assets'].items():
        src = ROOT / relative
        if digest(src) != sha:
            raise RuntimeError('Frozen source changed during preparation: ' + relative)
        dest = out / 'frozen_code' / relative
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
    shutil.copy2(Path(__file__), out / 'prepare_pjob_memory_retry.py')
    dump(out / 'campaign.json', new_spec)
    dump(out / 'supplement.json', dict(contract=new_contract, campaign_sha256=digest(out / 'campaign.json')))
    for path, sha in parent_hashes.items():
        if digest(Path(path)) != sha:
            raise RuntimeError('Parent changed during preparation: ' + path)
    for key in cases:
        evidence.reference_receipt(out, key, new_spec)
    (out / 'preparation_pending.json').unlink()
    evidence.checked(out)
    review = dict(campaign=str(out), prepared_cells=[cell['id'] for cell in cells],
                  expected=len(cells), settings=settings,
                  required_available_memory_mib=settings['process_memory_mb'] + contract['reserve_mb'],
                  parent_files_unchanged=True, references_reused=True, experiments_started=0,
                  reference_gate='Run the existing resume command to recheck RAM and copied reference certificates')
    dump(out / 'prepared_review.json', review)
    print(json.dumps(review, ensure_ascii=False, indent=2))


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('--parent', required=True)
    parser.add_argument('--audit', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--memory-mb', type=int, default=12288)
    parser.add_argument('--process-memory-mb', type=int, default=18432)
    prepare(parser.parse_args())


if __name__ == '__main__':
    main()

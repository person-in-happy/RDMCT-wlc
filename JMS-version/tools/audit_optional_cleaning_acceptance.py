"""Read-only acceptance audit; never rewrites campaigns or reruns optimization."""
from pathlib import Path
from datetime import datetime, timezone
from collections import Counter, defaultdict
import argparse
import gzip
import json
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'JMS-version/joint_model'))
import pyscipopt
from pyscipopt import Model
from model import Config, Integrated
from revalidate import verify
from run_experiments import digest, fix_structure
from validate import validate


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def assign_and_check(model, values):
    variables = model.getVars(transformed=False)
    missing = [v.name for v in variables if v.name not in values]
    if missing:
        raise ValueError(f'Missing {len(missing)} original variables')
    sol = model.createSol()
    try:
        for var in variables:
            model.setSolVal(sol, var, values[var.name])
        return bool(model.checkSol(sol, printreason=False, completely=True))
    finally:
        model.freeSol(sol)


def recertify_fixed(out, cell):
    dest = out / 'runs' / cell['id']
    manifest = read(dest / 'manifest.json')
    exported = read(dest / 'variables.json')
    lp_hash = digest(dest / 'model.lp.gz')
    if lp_hash != manifest['lp_sha256'] or lp_hash != exported['model_sha256']:
        raise ValueError(f"LP provenance mismatch: {cell['id']}")
    reference_path = out / 'references' / cell['case'] / 'reference.json'
    if digest(reference_path) != manifest['fixed_reference_sha256']:
        raise ValueError('Fixed reference changed')
    # Windows SCIP builds may lack a gzip reader. Use a private temporary LP.
    with tempfile.TemporaryDirectory(prefix='acceptance_', dir=ROOT / 'tmp') as temp:
        lp = Path(temp) / 'model.lp'
        lp.write_bytes(gzip.decompress((dest / 'model.lp.gz').read_bytes()))
        model = Model()
        model.hideOutput()
        try:
            model.readProblem(str(lp))
            lp_valid = assign_and_check(model, exported['values'])
        finally:
            model.freeProb()
    config_path = out / 'configs' / (cell['case'] + '.json')
    rebuilt = Integrated(Config(**read(config_path)))
    try:
        fix_structure(rebuilt, read(reference_path))
        rebuilt_valid = assign_and_check(rebuilt.model, exported['values'])
    finally:
        rebuilt.model.freeProb()
    result = read(dest / 'result.json')
    physical = validate(result)
    return dict(id=cell['id'], original_reported_check=result['original_model_check'],
                lp_check=lp_valid, rebuilt_original_check=rebuilt_valid, physical=physical,
                reported_solver_status=result['status'],
                interpretation='Post-hoc feasibility certificate only; original campaign status is unchanged.',
                hashes={name: digest(dest / name) for name in
                        ('model.lp.gz', 'variables.json', 'result.json', 'manifest.json')},
                config_sha256=digest(config_path), reference_sha256=digest(reference_path))


def audit(out):
    spec = verify(out)
    states = Counter()
    failures = []
    certificates = []
    valid_rows = []
    summary_rows = {r['id']: r for r in read(out / 'summary/cells.json')}
    for cell in spec['cells']:
        dest = out / 'runs' / cell['id']
        row = summary_rows[cell['id']]
        states[row['state']] += 1
        evidence_path = dest / 'evidence.json'
        if evidence_path.exists():
            evidence = read(evidence_path)
            if digest(dest / 'result.json') != evidence['result_sha256']:
                raise ValueError(f"Result hash mismatch: {cell['id']}")
            physical = validate(read(dest / 'result.json'))
            if row.get('valid') and not (physical['valid'] and evidence['original_model_check']):
                raise ValueError(f"Validation mismatch: {cell['id']}")
            if row.get('valid'):
                valid_rows.append(row)
        if row['state'] == 'execution_failed':
            logs = sorted((out / 'logs').glob(cell['id'] + '*.log'), key=lambda p: p.stat().st_mtime)
            log = logs[-1] if logs else None
            last_line = log.read_text(encoding='utf-8', errors='replace').strip().splitlines()[-1] if log else ''
            failures.append(dict(id=cell['id'], last_error=last_line,
                                 failure=read(dest / 'failure.json'),
                                 log=str(log.relative_to(ROOT)) if log else None,
                                 log_sha256=digest(log) if log else None))
            if cell['variant'] == 'fixed' and (dest / 'variables.json').exists():
                certificates.append(recertify_fixed(out, cell))
    groups = defaultdict(list)
    for row in valid_rows:
        parts = row['case'].split('_')
        groups[(parts[0], parts[1], parts[-1], row['seed'])].append(row)
    complete_groups = [rows for rows in groups.values()
                       if len(rows) == 3 and {r['case'].split('_')[2] for r in rows} == {'4x1', '2x2', 'mixed'}]
    winners = [r['id'] for rows in complete_groups for r in rows
               if all(other['lower'] is not None and r['upper'] < other['lower'] - 2e-4
                      for other in rows if other is not r)]
    return dict(campaign=str(out.relative_to(ROOT)), campaign_sha256=digest(out / 'campaign.json'),
                expected=len(spec['cells']), states=dict(states), revalidated_feasible=len(valid_rows),
                failures=failures, failure_causes=dict(Counter(f['last_error'] for f in failures)),
                posthoc_fixed_certificates=certificates,
                complete_mode_triples=len(complete_groups), certified_mode_winners=winners,
                runs_with_early_cleaning=sum(r['early_cleanings'] > 0 for r in valid_rows),
                runs_with_structure_change=sum(r['structure_changed'] for r in valid_rows))


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('--output', required=True, help='New JSON report path; existing files are preserved')
    args = parser.parse_args()
    output = Path(args.output).resolve()
    if not output.is_relative_to(ROOT):
        raise ValueError('Audit output must stay in the workspace')
    if output.exists():
        raise FileExistsError(output)
    (ROOT / 'tmp').mkdir(exist_ok=True)
    report = dict(created_utc=datetime.now(timezone.utc).isoformat(), python=sys.executable,
                  pyscipopt_version=pyscipopt.__version__, script_sha256=digest(Path(__file__)),
                  scope='Read-only, no optimization, no mutation or promotion of original results.',
                  campaigns=[audit(ROOT / 'JMS-version/results' / ('optional_cleaning_20261016_' + suite))
                             for suite in ('core', 'crossover')])
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('x', encoding='utf-8') as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2, allow_nan=False)
    print(json.dumps(dict(report=str(output),
                          campaigns=[{k: c[k] for k in ('campaign', 'expected', 'states', 'revalidated_feasible',
                                                        'failure_causes', 'certified_mode_winners')}
                                     for c in report['campaigns']]), ensure_ascii=False))


if __name__ == '__main__':
    main()

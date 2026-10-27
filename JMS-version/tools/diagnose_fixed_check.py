"""Isolated diagnostic replay; never rewrites a frozen experiment.

Reproduce an incumbent check in the live solved model, then explicitly compare
the original-problem check and the default transformed-problem check.
"""
from pathlib import Path
from datetime import datetime, timezone
import argparse
import inspect
import json
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'JMS-version/joint_model'))
from model import Config, Integrated
from run_experiments import digest, dump, fix_structure, finite
from validate import validate


def read(p):
    return json.loads(p.read_text(encoding='utf-8-sig'))


def run(campaign, cell_id, output):
    campaign, output = Path(campaign).resolve(), Path(output).resolve()
    if not output.is_relative_to(ROOT / 'JMS-version/review'):
        raise ValueError('Diagnostic output must be in JMS-version/review')
    output.mkdir(parents=True, exist_ok=False)
    spec = read(campaign / 'campaign.json')
    cell = next(c for c in spec['cells'] if c['id'] == cell_id)
    if cell['variant'] != 'fixed':
        raise ValueError('This diagnostic requires a fixed-structure cell')
    for name, sha in spec['assets'].items():
        if digest(ROOT / name) != sha:
            raise RuntimeError('Frozen source differs: ' + name)
    source = campaign / 'runs' / cell_id
    cfg_path = campaign / 'configs' / (cell['case'] + '.json')
    reference = campaign / 'references' / cell['case'] / 'reference.json'
    warm_path = reference.with_name('common.json')
    before = {str(p.relative_to(campaign)): digest(p) for p in
              (campaign / 'campaign.json', cfg_path, reference, warm_path,
               source / 'result.json', source / 'variables.json', source / 'model.lp.gz')}
    started = time.monotonic()
    print(f'0/1 diagnostic complete; reproduce {cell_id}; main limit={spec["time_limit"]} s; original campaign read-only', flush=True)
    x = Integrated(Config(**read(cfg_path)))
    m = x.model
    try:
        fix_structure(x, read(reference))
        m.setIntParam('randomization/randomseedshift', cell['seed'])
        m.setIntParam('parallel/maxnthreads', 1)
        m.setRealParam('limits/memory', spec['memory_mb'])
        warm = read(warm_path)['values']
        initial = m.createSol()
        for v in m.getVars(transformed=False):
            m.setSolVal(initial, v, warm[v.name])
        if not m.checkSol(initial, printreason=True, completely=True, original=True):
            raise RuntimeError('Frozen warm start failed ORIGINAL model')
        m.addSol(initial)
        m.hideOutput(False)
        m.setLogfile(str(output / 'diagnostic_solver.log'))
        m.setRealParam('limits/time', spec['time_limit'])
        m.optimize()
        if not m.getNSols():
            raise RuntimeError('Diagnostic produced no incumbent')
        best = m.getBestSol()
        checks = {}
        for label, flags in (
            ('default_transformed', {}),
            ('explicit_original', {'original': True}),
            ('transformed_without_lp_rows', {'checklprows': False}),
            ('transformed_without_bounds', {'checkbounds': False}),
        ):
            print('CHECK ' + label, flush=True)
            checks[label] = bool(m.checkSol(best, printreason=True, completely=True, **flags))
            print(f'{label}={checks[label]}', flush=True)
        result = x.result()
        values = {v.name: m.getSolVal(best, v) for v in m.getVars(transformed=False)}
        dump(output / 'diagnostic_result.json', finite(result))
        dump(output / 'diagnostic_variables.json', dict(values=values))
        report = dict(created_utc=datetime.now(timezone.utc).isoformat(),
                      scope='Diagnostic replay only; no promotion of historical status or new benchmark sample',
                      cell=cell, checks=checks, physical=validate(result),
                      status=str(m.getStatus()), cmax=result['cmax'], dual_bound=result['dual_bound'],
                      solve_seconds=m.getSolvingTime(), wall_seconds=time.monotonic()-started,
                      checkSol_signature=str(inspect.signature(m.checkSol)),
                      source_hashes=before, script_sha256=digest(Path(__file__)),
                      source_unchanged=all(digest(campaign / p) == h for p, h in before.items()))
        dump(output / 'report.json', finite(report))
        print('1/1 diagnostic complete: ' + json.dumps(report['checks']), flush=True)
        if not report['source_unchanged']:
            raise RuntimeError('Source files changed during diagnostic')
    finally:
        m.freeProb()


if __name__ == '__main__':
    p = argparse.ArgumentParser(__doc__)
    p.add_argument('--campaign', required=True)
    p.add_argument('--cell', required=True)
    p.add_argument('--output', required=True)
    a = p.parse_args()
    run(a.campaign, a.cell, a.output)

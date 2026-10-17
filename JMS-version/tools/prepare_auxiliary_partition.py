"""Prepare a controlled reference with disjoint dummy pools across chambers.

Product membership, chamber assignment, cycle occupancy and front side remain
unchanged. This is a structural witness, not a learned-algorithm comparison.
"""
from pathlib import Path
import argparse
import copy
import json
import sys
import time
from dataclasses import asdict

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'JMS-version/joint_model'))
from model import Config, Integrated
from seed import construct, constrain_seed
from validate import validate
from run_experiments import assets, digest, dump, finite


def prepare(reference, output):
    start = time.monotonic()
    ref = Path(reference).resolve()
    out = Path(output).resolve()
    old_manifest = json.loads((ref / 'manifest.json').read_text(encoding='utf-8-sig'))
    if old_manifest['assets'] != assets():
        raise RuntimeError('Frozen assets changed')
    original = json.loads((ref / 'reference.json').read_text(encoding='utf-8-sig'))
    cfg = Config(**json.loads((ref / 'config.json').read_text(encoding='utf-8-sig')))
    if cfg.source != 'dual' or cfg.max_pairs or cfg.max_cycles:
        raise ValueError('This diagnostic requires dual source and full candidate bounds')
    template = copy.deepcopy(original)
    mapping = {}
    # Assign labels in first-occurrence order, preserving dummy-label symmetry.
    for pair in sorted(template['pairs'], key=lambda p: p['id']):
        for r, wafer in enumerate(pair['members']):
            if wafer.startswith('D'):
                key = (pair['chamber'], wafer)
                if key not in mapping:
                    mapping[key] = f'D{len(mapping)+1}'
                pair['members'][r] = mapping[key]
    if len(mapping) > cfg.dummy_count:
        raise ValueError('Partition requires more than the configured inventory')
    data = construct(cfg, template)
    x = Integrated(cfg)
    m = x.model
    m.hideOutput()
    bounds = constrain_seed(x, data)
    m.setObjective(0, 'minimize')
    m.setRealParam('limits/time', 30)
    m.setRealParam('limits/memory', 24000)
    m.optimize()
    if not m.getNSols():
        raise RuntimeError('Complete initial assignment could not be certified')
    sol = m.getBestSol()
    values = {v.name: m.getSolVal(sol, v) for v in m.getVars(transformed=False)}
    completed = x.result()
    physical = validate(completed)
    if not physical['valid']:
        raise RuntimeError(physical['errors'])
    m.freeTransform()
    for v, lb, ub in bounds:
        m.chgVarLb(v, lb)
        m.chgVarUb(v, ub)
    sol = m.createSol()
    for v in m.getVars():
        m.setSolVal(sol, v, values[v.name])
    accepted = bool(m.checkSol(sol, printreason=False, completely=True))
    m.freeSol(sol)
    if not accepted:
        raise RuntimeError('Partition reference violates the unrestricted model')
    m.freeProb()
    out.mkdir(parents=True, exist_ok=False)
    dump(out / 'reference.json', data)
    dump(out / 'config.json', asdict(cfg))
    dump(out / 'variables.json', dict(values=values, config_sha256=digest(out / 'config.json')))
    dump(out / 'certificate.json', finite(dict(valid=True, cmax=physical['product_return_cmax'],
         physical=physical, seconds=time.monotonic()-start, full_MILP_valid=accepted)))
    dump(out / 'manifest.json', dict(assets=assets(), protocol_sha256=digest(Path(__file__)),
         original_reference_sha256=digest(ref / 'reference.json'),
         original_reference=str(ref), scope='Controlled auxiliary-identity witness',
         dummy_mapping={f'CH{c}:{d}': new for (c, d), new in mapping.items()}))
    print(json.dumps(dict(output=str(out), cmax=physical['product_return_cmax'],
                         used_dummies=len(mapping), valid=True)))


if __name__ == '__main__':
    p = argparse.ArgumentParser(__doc__)
    p.add_argument('--reference', required=True)
    p.add_argument('--output', required=True)
    a = p.parse_args()
    prepare(a.reference, a.output)

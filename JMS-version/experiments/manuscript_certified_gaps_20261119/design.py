"""Prospective protocol for the three manuscript experiments. Gaps are fractions."""
import gzip
import hashlib
import json
import os
from pathlib import Path

HERE = Path(__file__).resolve().parent
JMS = HERE.parents[1]
ROOT = JMS.parent
RESULTS = JMS / 'results'
OUT = RESULTS / 'manuscript_certified_gaps_20261119_r3'
LEVELS = {'10pct': .1, '1pct': .01, '0p01pct': .0001}
TUNING = ('D_n2_4x1_scenario1', 'D_n2_mixed_scenario3')
EXTENSIONS = ('D_n4_mixed_H10', 'E_n8_H3_mixed_dual', 'D_n16_4x1', 'E_n16_2x2')
METHODS = {'full': ('proposed', True), 'no_spbs': ('proposed', False),
           'no_rerank': ('proposed_no_structure', True)}
SEED = 1
TRAINING_SEED = 1
EPS = 2e-4


def read(path):
    path = Path(path)
    if path.suffix == '.gz':
        with gzip.open(path, 'rt', encoding='utf-8') as stream:
            return json.load(stream)
    return json.loads(path.read_text(encoding='utf-8-sig'))


def save(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + f'.{os.getpid()}.tmp')
    payload = json.dumps(data, ensure_ascii=False, allow_nan=False, indent=None if path.suffix == '.gz' else 2).encode('utf-8')
    temp.write_bytes(gzip.compress(payload, compresslevel=2, mtime=0) if path.suffix == '.gz' else payload)
    os.replace(temp, path)


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def witness(path, variables):
    doc = read(path)
    if 'values' in doc:
        if doc['values'].keys() != {v.name for v in variables}:
            raise ValueError(f'Original assignment coverage mismatch in {path}')
        return doc['values']
    if doc.get('default') != 0 or not doc['nonzero'].keys() <= {v.name for v in variables}:
        raise ValueError(f'Invalid zero-default assignment in {path}')
    return {v.name: doc['nonzero'].get(v.name, 0.) for v in variables}


def sparse(values):
    return {'default': 0, 'nonzero': {k: v for k, v in values.items() if v != 0.}}


def rel(path):
    return Path(path).resolve().relative_to(ROOT).as_posix()


def pick(rows):
    """Choose only after the entire predeclared two-case grid is certified."""
    from itertools import product
    pairs = list(product(LEVELS, repeat=2))
    if any((c, a, b) not in rows for c in TUNING for a, b in pairs):
        return None
    def quality(pair):
        # Equal weight per physical instance, lexicographic manufacturing objectives.
        metrics = []
        for obj in ('cmax', 'secondary'):
            score = sum(rows[c, *pair]['metrics'][obj] / max(1., min(rows[c, a, b]['metrics'][obj] for a, b in pairs)) for c in TUNING) / len(TUNING)
            metrics.append(round(score, 6))
        return (*metrics, -LEVELS[pair[0]], -LEVELS[pair[1]])
    return min(pairs, key=quality)

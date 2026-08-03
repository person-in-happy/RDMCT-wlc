'''Create a resumable variable, constraint, LP-size, and parse-time evidence table.'''

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import statistics
import time
from pathlib import Path

from pyscipopt import Model


CIE_ROOT = Path(__file__).resolve().parents[1]


def _parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        '--manifest', default=str(CIE_ROOT / 'configs' / 'cie_benchmark_suites.json')
    )
    parser.add_argument(
        '--output-dir', default=str(CIE_ROOT / 'results' / 'model_evidence')
    )
    return parser.parse_args()


def _sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def _instances(manifest_path):
    manifest_path = Path(manifest_path).resolve()
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    unique = {}
    for suite in manifest['suites']:
        root = (manifest_path.parent / suite['root']).resolve()
        for path in sorted(root.glob(suite.get('glob', '**/*.lp'))):
            if path.is_file():
                unique[str(path.resolve()).lower()] = path.resolve()
    return sorted(unique.values(), key=str)


def _signature(manifest_path, instances):
    records = [
        {'path': str(Path(manifest_path).resolve()), 'sha256': _sha256(manifest_path)},
        {'path': str(Path(__file__).resolve()), 'sha256': _sha256(__file__)},
    ]
    records.extend(
        {'path': str(path), 'sha256': _sha256(path)} for path in instances
    )
    encoded = json.dumps(
        records, ensure_ascii=False, sort_keys=True, separators=(',', ':')
    ).encode('utf-8')
    return hashlib.sha256(encoded).hexdigest(), records


def _checkpoint_rows(path, signature):
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + '.tmp')
        with temporary.open('w', encoding='utf-8', newline='\n') as stream:
            stream.write(json.dumps({'record_type': 'meta', 'signature': signature}) + '\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        return {}
    rows = {}
    meta_seen = False
    lines = path.read_text(encoding='utf-8').splitlines()
    for index, line in enumerate(lines, start=1):
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            if index == len(lines):
                continue
            raise
        if record.get('record_type') == 'meta':
            meta_seen = True
            if record.get('signature') != signature:
                raise RuntimeError('Model-evidence checkpoint signature mismatch')
        elif record.get('record_type') == 'row':
            rows[record['path']] = record['row']
    if not meta_seen:
        raise RuntimeError('Model-evidence checkpoint metadata is missing')
    return rows


def _append(path, record):
    with path.open('a', encoding='utf-8', newline='\n') as stream:
        stream.write(json.dumps(record, ensure_ascii=False) + '\n')
        stream.flush()
        os.fsync(stream.fileno())


def _measure(path):
    sidecar = path.with_suffix('.cie.json')
    metadata = (
        json.loads(sidecar.read_text(encoding='utf-8'))
        if sidecar.is_file()
        else {}
    )
    model = Model()
    model.hideOutput()
    started = time.perf_counter()
    try:
        model.readProblem(str(path))
        parse_time = time.perf_counter() - started
        variables = model.getVars()
        types = [str(variable.vtype()).upper() for variable in variables]
        return {
            'path': str(path),
            'group': metadata.get('group', path.parent.parent.name),
            'total_wafers': metadata.get('total'),
            'full_wafers': metadata.get('full'),
            'mix_wafers': metadata.get('mix'),
            'lp_bytes': path.stat().st_size,
            'variables': len(variables),
            'binary_variables': sum('BINARY' in item for item in types),
            'integer_variables': sum(
                'INTEGER' in item or 'IMPLINT' in item for item in types
            ),
            'continuous_variables': sum('CONTINUOUS' in item for item in types),
            'constraints': model.getNConss(),
            'parse_time_seconds': parse_time,
            'lp_sha256': _sha256(path),
        }
    finally:
        model.freeProb()


def _write_csv(path, rows, fields):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    try:
        with temporary.open('w', encoding='utf-8-sig', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def main():
    args = _parse_args()
    instances = _instances(args.manifest)
    signature, assets = _signature(args.manifest, instances)
    output_dir = Path(args.output_dir).resolve()
    checkpoint = output_dir / '.checkpoints' / f'model_scale_{signature[:16]}.jsonl'
    rows_by_path = _checkpoint_rows(checkpoint, signature)
    for index, path in enumerate(instances, start=1):
        key = str(path)
        source = 'resume'
        if key not in rows_by_path:
            row = _measure(path)
            rows_by_path[key] = row
            _append(checkpoint, {'record_type': 'row', 'path': key, 'row': row})
            source = 'measure'
        print(f'[{index}/{len(instances)}] {source}: {path}', flush=True)
    rows = [rows_by_path[str(path)] for path in instances]
    raw_fields = list(rows[0])
    _write_csv(output_dir / 'model_scale_raw.csv', rows, raw_fields)
    grouped = {}
    for row in rows:
        key = (row['group'], row['total_wafers'])
        grouped.setdefault(key, []).append(row)
    summary = []
    for (group, total), group_rows in sorted(grouped.items(), key=str):
        record = {'group': group, 'total_wafers': total, 'instances': len(group_rows)}
        for field in (
            'lp_bytes', 'variables', 'binary_variables', 'integer_variables',
            'continuous_variables', 'constraints', 'parse_time_seconds',
        ):
            values = [float(row[field]) for row in group_rows]
            record[field + '_mean'] = statistics.fmean(values)
            record[field + '_max'] = max(values)
        summary.append(record)
    _write_csv(output_dir / 'model_scale_summary.csv', summary, list(summary[0]))
    (output_dir / 'model_scale_manifest.json').write_text(
        json.dumps(
            {'signature': signature, 'assets': assets, 'instances': len(instances)},
            ensure_ascii=False, indent=2,
        ),
        encoding='utf-8',
    )
    print('Raw:', output_dir / 'model_scale_raw.csv')
    print('Summary:', output_dir / 'model_scale_summary.csv')


if __name__ == '__main__':
    main()

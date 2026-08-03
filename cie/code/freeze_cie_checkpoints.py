'''Freeze one auditable epoch-60 checkpoint per CIE family and training seed.'''

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
from pathlib import Path

import torch


CIE_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = CIE_ROOT.parent
FAMILIES = {
    'hem': 13,
    'feature_only': 23,
    'proposed': 23,
}


def _parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--models-root', default=str(CIE_ROOT / 'models'))
    parser.add_argument(
        '--output',
        default=str(
            CIE_ROOT / 'results' / 'repro_manifest'
            / 'selected_checkpoint_manifest.csv'
        ),
    )
    parser.add_argument('--seeds', default='1,2,3,4,5')
    parser.add_argument('--epoch', type=int, default=60)
    return parser.parse_args()


def _sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def _metadata_seed(payload, section, key):
    value = payload.get(section, {}).get(key)
    return None if value is None else int(value)


def _portable_path(path):
    return Path(path).resolve().relative_to(PROJECT_ROOT).as_posix()


def _is_training_path(path):
    normalized = str(path).replace('/', os.sep).replace(chr(92), os.sep)
    suffix = os.path.join('cie', 'data', 'policy_training', 'train')
    return normalized.lower().endswith(suffix.lower())


def _candidate(variant_path, family, seed, epoch):
    try:
        payload = json.loads(variant_path.read_text(encoding='utf-8'))
        experiment_seed = _metadata_seed(payload, 'experiment', 'seed')
        parser_seed = _metadata_seed(payload, 'parser_args', 'seed')
        scip_seed = _metadata_seed(payload, 'parser_args', 'scip_seed')
        training_path = payload.get('env', {}).get('instance_file_path', '')
        if (experiment_seed, parser_seed, scip_seed) != (seed, seed, seed):
            return None
        if not _is_training_path(training_path):
            return None
        checkpoint_path = variant_path.with_name(f'itr_{epoch}.pkl')
        if not checkpoint_path.is_file():
            return None
        checkpoint = torch.load(
            checkpoint_path, map_location='cpu', weights_only=False
        )
        if int(checkpoint.get('epoch', -1)) != epoch:
            return None
        if checkpoint.get('reward_type') != 'primaldualintegral':
            return None
        schema = checkpoint.get('cut_feature_schema') or {}
        dimension = schema.get('dimension') if isinstance(schema, dict) else None
        if dimension is not None and int(dimension) != FAMILIES[family]:
            return None
        if 'pointer_net' not in checkpoint or 'cutsel_percent_net' not in checkpoint:
            return None
        return {
            'family': family,
            'training_seed': seed,
            'checkpoint': _portable_path(checkpoint_path),
            'checkpoint_sha256': _sha256(checkpoint_path),
            'checkpoint_size': checkpoint_path.stat().st_size,
            'variant': _portable_path(variant_path),
            'variant_sha256': _sha256(variant_path),
            'experiment_seed': experiment_seed,
            'parser_seed': parser_seed,
            'scip_seed': scip_seed,
            'training_path': 'cie/data/policy_training/train',
            'epoch': epoch,
            'reward_type': checkpoint.get('reward_type'),
            'feature_dim': FAMILIES[family],
            'modified_ns': checkpoint_path.stat().st_mtime_ns,
        }
    except (OSError, ValueError, TypeError, KeyError, RuntimeError):
        return None


def freeze(models_root, output_path, seeds, epoch):
    models_root = Path(models_root).resolve()
    rows = []
    for family in FAMILIES:
        family_root = models_root / family
        for seed in seeds:
            candidates = []
            if family_root.is_dir():
                for variant_path in family_root.rglob('variant.json'):
                    candidate = _candidate(variant_path, family, seed, epoch)
                    if candidate is not None:
                        candidates.append(candidate)
            if not candidates:
                raise RuntimeError(
                    f'No auditable itr_{epoch}.pkl for {family} seed {seed}'
                )
            candidates.sort(
                key=lambda item: (item['modified_ns'], item['checkpoint'])
            )
            selected = candidates[-1]
            selected['candidate_count'] = len(candidates)
            selected.pop('modified_ns', None)
            rows.append(selected)
    output_path = Path(output_path).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_suffix(output_path.suffix + '.tmp')
    fields = list(rows[0])
    try:
        with temporary.open('w', encoding='utf-8-sig', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, output_path)
    finally:
        if temporary.exists():
            temporary.unlink()
    return rows, output_path


def main():
    args = _parse_args()
    seeds = [int(item) for item in args.seeds.split(',') if item.strip()]
    rows, output = freeze(args.models_root, args.output, seeds, args.epoch)
    print(f'Frozen checkpoints: {len(rows)}/{len(FAMILIES) * len(seeds)}')
    for row in rows:
        family = row['family']
        seed = row['training_seed']
        candidate_count = row['candidate_count']
        checkpoint = row['checkpoint']
        print(
            f'{family} seed={seed} candidates={candidate_count} {checkpoint}'
        )
    print(f'Output: {output}')


if __name__ == '__main__':
    main()

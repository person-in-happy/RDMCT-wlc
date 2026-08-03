"""Tune the four Adaptive Cut Selection weights on validation instances."""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import math
import os
import sys
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

CIE_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = CIE_ROOT.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np

from path_utils import resolve_path
from run_cie_benchmarks import (
    _discover_instances,
    _normalize_acs_weights,
    _run_one,
)


def _parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest",
        default=str(CIE_ROOT / "configs" / "cie_benchmark_suites.json"),
    )
    parser.add_argument(
        "--output_dir",
        default=str(CIE_ROOT / "results" / "acs_tuning"),
    )
    parser.add_argument("--seeds", default="1,2,3")
    parser.add_argument("--time_limit", type=float, default=60.0)
    parser.add_argument("--grid_step", type=float, default=0.25)
    parser.add_argument("--max_instances", type=int, default=0)
    parser.add_argument("--memory_limit_mb", type=float, default=8192.0)
    parser.add_argument("--node_limit", type=int, default=-1)
    parser.add_argument(
        '--no_resume',
        action='store_true',
        help='Disable crash-safe per-evaluation ACS tuning checkpoints.',
    )
    return parser.parse_args()


def _simplex_profiles(step):
    denominator = round(1.0 / step)
    if denominator <= 0 or not math.isclose(
        denominator * step, 1.0, rel_tol=0.0, abs_tol=1e-9
    ):
        raise ValueError("grid_step must divide 1.0 exactly, e.g. 0.5, 0.25, 0.2, 0.1.")
    profiles = []
    for values in itertools.product(range(denominator + 1), repeat=4):
        if sum(values) == denominator:
            profiles.append([value / denominator for value in values])
    return profiles


def _metric(row, time_limit):
    try:
        pdi = float(row["primal_dual_integral"])
        if math.isfinite(pdi):
            return max(pdi, 0.0) + 1e-6
    except (TypeError, ValueError):
        pass
    try:
        gap = min(max(float(row["gap"]), 0.0), 1.0)
    except (TypeError, ValueError):
        gap = 1.0
    try:
        solve_time = min(max(float(row["solving_time"]), 0.0), time_limit)
    except (TypeError, ValueError):
        solve_time = time_limit
    return solve_time + time_limit * gap + 1e-6


def _sha256_file(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def _acs_signature(cli, instances, seeds, profiles):
    ignored = {'output_dir', 'no_resume'}
    arguments = {
        key: value for key, value in vars(cli).items() if key not in ignored
    }
    asset_paths = [
        Path(resolve_path(cli.manifest)),
        Path(__file__).resolve(),
        Path(__file__).with_name('run_cie_benchmarks.py').resolve(),
        PROJECT_ROOT / 'environments.py',
    ]
    asset_paths.extend(Path(item['path']).resolve() for item in instances)
    assets = []
    for path in asset_paths:
        assets.append(
            {
                'path': str(path),
                'size': path.stat().st_size,
                'sha256': _sha256_file(path),
            }
        )
    payload = {
        'checkpoint_version': 1,
        'arguments': arguments,
        'seeds': seeds,
        'profiles': profiles,
        'instances': instances,
        'assets': assets,
    }
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(',', ':'),
        default=str,
    ).encode('utf-8')
    return hashlib.sha256(encoded).hexdigest()


def _acs_evaluation_key(kind, instance_path, seed, weights):
    return json.dumps(
        [
            str(kind),
            os.path.normcase(str(Path(instance_path).resolve())),
            int(seed),
            weights,
        ],
        ensure_ascii=False,
        sort_keys=True,
        separators=(',', ':'),
    )


def _write_acs_checkpoint_header(path, signature):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    record = {
        'record_type': 'meta',
        'checkpoint_version': 1,
        'signature': signature,
        'created_at': datetime.now().isoformat(timespec='seconds'),
    }
    with temporary.open('w', encoding='utf-8', newline='\n') as stream:
        stream.write(json.dumps(record, ensure_ascii=False) + '\n')
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def _load_acs_checkpoint(path, signature):
    if not path.exists():
        _write_acs_checkpoint_header(path, signature)
        return {}
    rows = {}
    meta_seen = False
    lines = path.read_text(encoding='utf-8').splitlines()
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            if line_number == len(lines):
                print(
                    f'Ignoring incomplete final ACS checkpoint line: {path}',
                    file=sys.stderr,
                )
                continue
            raise RuntimeError(
                f'Corrupt ACS checkpoint record: {path}:{line_number}'
            )
        if record.get('record_type') == 'meta':
            meta_seen = True
            if record.get('signature') != signature:
                raise RuntimeError(f'ACS checkpoint signature mismatch: {path}')
        elif record.get('record_type') == 'row':
            rows[record['key']] = record['row']
    if not meta_seen:
        raise RuntimeError(f'ACS checkpoint metadata is missing: {path}')
    return rows


def _append_acs_checkpoint(path, record):
    with path.open('a', encoding='utf-8', newline='\n') as stream:
        stream.write(json.dumps(record, ensure_ascii=False, default=str) + '\n')
        stream.flush()
        os.fsync(stream.fileno())


def _atomic_json_dump(path, payload):
    temporary = path.with_suffix(path.suffix + '.tmp')
    try:
        with temporary.open('w', encoding='utf-8', newline='\n') as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2, default=str)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def main():
    cli = _parse_args()
    seeds = [int(item) for item in cli.seeds.split(',') if item.strip()]
    _, instances, empty = _discover_instances(
        cli.manifest, cli.max_instances, {'validation'}
    )
    if not instances:
        raise RuntimeError(
            'No validation instances found. Generate the MILP families first '
            f'or fix the manifest. Empty suites: {empty}'
        )
    args = SimpleNamespace(
        time_limit=cli.time_limit,
        node_limit=cli.node_limit,
        memory_limit_mb=cli.memory_limit_mb,
        training_seed=-1,
        run_label='acs_validation',
        warm_start='none',
        solution_dir='',
        scip_verbosity=0,
        cutsel_max_candidates=128,
        cutsel_max_selected_cuts=16,
        sel_cuts_percent=0.2,
        decode_type='greedy',
        policy_type='with_token',
    )
    profiles = _simplex_profiles(cli.grid_step)
    signature = _acs_signature(cli, instances, seeds, profiles)
    output_dir = Path(resolve_path(cli.output_dir))
    output_dir.mkdir(parents=True, exist_ok=True)
    checkpoint_path = (
        output_dir / '.checkpoints' / f'acs_grid_{signature[:16]}.jsonl'
    )
    rows = (
        {}
        if cli.no_resume
        else _load_acs_checkpoint(checkpoint_path, signature)
    )
    total = len(instances) * len(seeds) * (1 + len(profiles))
    completed = 0

    def evaluate(kind, instance, seed, weights):
        nonlocal completed
        key = _acs_evaluation_key(kind, instance['path'], seed, weights)
        resumed = key in rows
        if resumed:
            row = rows[key]
        else:
            method = 'scip_default' if kind == 'default' else 'adaptive_cutsel'
            row = _run_one(method, instance, seed, args, {}, weights, {})
            rows[key] = row
            if not cli.no_resume:
                _append_acs_checkpoint(
                    checkpoint_path,
                    {'record_type': 'row', 'key': key, 'row': row},
                )
        completed += 1
        source = 'resume' if resumed else 'solve'
        display_path = instance['path']
        print(
            f'[{completed}/{total}] {kind} {display_path} '
            f'seed={seed} source={source}',
            flush=True,
        )
        return row

    default_weights = _normalize_acs_weights('0,1,0,0')
    defaults = {}
    for instance in instances:
        for seed in seeds:
            row = evaluate('default', instance, seed, default_weights)
            defaults[(instance['path'], seed)] = _metric(row, cli.time_limit)

    profile_results = []
    for profile_index, profile in enumerate(profiles, start=1):
        weights = _normalize_acs_weights(profile)
        ratios = []
        failures = 0
        for instance in instances:
            for seed in seeds:
                row = evaluate(
                    f'profile_{profile_index}', instance, seed, weights
                )
                if row.get('error'):
                    failures += 1
                ratios.append(
                    _metric(row, cli.time_limit)
                    / defaults[(instance['path'], seed)]
                )
        profile_results.append(
            {
                'weights': weights,
                'mean_normalized_metric': float(np.mean(ratios)),
                'std_normalized_metric': float(np.std(ratios, ddof=1))
                if len(ratios) > 1
                else 0.0,
                'failures': failures,
                'runs': len(ratios),
            }
        )
    profile_results.sort(
        key=lambda item: (item['mean_normalized_metric'], item['failures'])
    )
    best = profile_results[0]
    output_path = output_dir / f'acs_grid_{signature[:16]}.json'
    payload = {
        'best_weights': best['weights'],
        'selection_rule': (
            'minimum mean validation metric normalized by SCIP default'
        ),
        'grid_step': cli.grid_step,
        'seeds': seeds,
        'validation_instances': [item['path'] for item in instances],
        'profiles': profile_results,
        'resume_signature': signature,
        'resume_checkpoint': str(checkpoint_path),
        'evaluations': total,
    }
    _atomic_json_dump(output_path, payload)
    if not cli.no_resume:
        _append_acs_checkpoint(
            checkpoint_path,
            {
                'record_type': 'complete',
                'output': str(output_path),
                'completed_at': datetime.now().isoformat(timespec='seconds'),
            },
        )
    best_weights = best['weights']
    print(f'Best weights: {best_weights}')
    print(f'Output: {output_path}')


def _legacy_main():
    cli = _parse_args()
    seeds = [int(item) for item in cli.seeds.split(",") if item.strip()]
    _, instances, empty = _discover_instances(
        cli.manifest,
        cli.max_instances,
        {"validation"},
    )
    if not instances:
        raise RuntimeError(
            "No validation instances found. Generate the MILP families first or "
            f"fix the manifest. Empty suites: {empty}"
        )
    args = SimpleNamespace(
        time_limit=cli.time_limit,
        node_limit=cli.node_limit,
        memory_limit_mb=cli.memory_limit_mb,
        training_seed=-1,
        run_label="acs_validation",
        warm_start="none",
        solution_dir="",
        scip_verbosity=0,
        cutsel_max_candidates=128,
        cutsel_max_selected_cuts=16,
        sel_cuts_percent=0.2,
        decode_type="greedy",
        policy_type="with_token",
    )

    defaults = {}
    total_default = len(instances) * len(seeds)
    count = 0
    for instance in instances:
        for seed in seeds:
            count += 1
            print(f"[default {count}/{total_default}] {instance['path']} seed={seed}")
            row = _run_one(
                "scip_default",
                instance,
                seed,
                args,
                {},
                _normalize_acs_weights("0,1,0,0"),
                {},
            )
            defaults[(instance["path"], seed)] = _metric(row, cli.time_limit)

    profile_results = []
    profiles = _simplex_profiles(cli.grid_step)
    for profile_index, profile in enumerate(profiles, start=1):
        weights = _normalize_acs_weights(profile)
        ratios = []
        failures = 0
        print(f"[profile {profile_index}/{len(profiles)}] {profile}")
        for instance in instances:
            for seed in seeds:
                row = _run_one(
                    "adaptive_cutsel",
                    instance,
                    seed,
                    args,
                    {},
                    weights,
                    {},
                )
                if row["error"]:
                    failures += 1
                ratios.append(
                    _metric(row, cli.time_limit)
                    / defaults[(instance["path"], seed)]
                )
        profile_results.append(
            {
                "weights": weights,
                "mean_normalized_metric": float(np.mean(ratios)),
                "std_normalized_metric": float(np.std(ratios, ddof=1))
                if len(ratios) > 1
                else 0.0,
                "failures": failures,
                "runs": len(ratios),
            }
        )
    profile_results.sort(key=lambda item: (item["mean_normalized_metric"], item["failures"]))
    best = profile_results[0]
    output_dir = Path(resolve_path(cli.output_dir))
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / (
        f"acs_grid_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    )
    with open(output_path, "w", encoding="utf-8") as stream:
        json.dump(
            {
                "best_weights": best["weights"],
                "selection_rule": "minimum mean validation metric normalized by SCIP default",
                "grid_step": cli.grid_step,
                "seeds": seeds,
                "validation_instances": [item["path"] for item in instances],
                "profiles": profile_results,
            },
            stream,
            ensure_ascii=False,
            indent=2,
        )
    print(f"Best weights: {best['weights']}")
    print(f"Output: {output_path}")


if __name__ == "__main__":
    main()

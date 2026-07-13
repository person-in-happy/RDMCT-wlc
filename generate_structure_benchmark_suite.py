"""Generate disjoint current-formulation train and holdout Petri MIP suites."""

import argparse
import json
from pathlib import Path

from petri_mip_generator import PetriMIPConfig, generate_petri_mip_instance
from petri_warm_start import write_mixed_warm_start
from path_utils import resolve_path


TRAIN_CASES = [
    ("train_balanced_24", 12, 12),
    ("train_full_heavy_24", 16, 8),
    ("train_mix_heavy_24", 8, 16),
    ("train_balanced_28", 14, 14),
    ("train_full_heavy_28", 18, 10),
    ("train_mix_heavy_28", 10, 18),
]

HOLDOUT_CASES = [
    ("holdout_balanced_30", 15, 15),
    ("holdout_full_heavy_30", 20, 10),
    ("holdout_mix_heavy_30", 10, 20),
    ("holdout_balanced_34", 17, 17),
    ("holdout_full_heavy_34", 22, 12),
    ("holdout_mix_heavy_34", 12, 22),
]


def _parse_args():
    parser = argparse.ArgumentParser(
        description="Generate separate training and held-out suites for structure-aware A3C."
    )
    parser.add_argument("--output_root", default="generated_instances/structure_benchmark")
    parser.add_argument("--warm_start_time_limit", type=float, default=120.0)
    parser.add_argument("--pec_pool_size", type=int, default=8)
    parser.add_argument("--cleaning_interval", type=int, default=10)
    parser.add_argument("--cleaning_process_time", type=float, default=0.0)
    return parser.parse_args()


def _generate_group(output_dir, cases, args):
    output_dir.mkdir(parents=True, exist_ok=True)
    records = []
    for case_name, full_wafers, mix_wafers in cases:
        cfg = PetriMIPConfig(
            full_mode_wafers=full_wafers,
            mix_mode_wafers=mix_wafers,
            pec_pool_size=args.pec_pool_size,
            cleaning_interval=args.cleaning_interval,
            cleaning_process_time=args.cleaning_process_time,
        )
        lp_path = Path(
            generate_petri_mip_instance(
                str(output_dir),
                f"{case_name}.lp",
                cfg,
                warm_start_time_limit=0,
            )
        )
        warm_start = ""
        if args.warm_start_time_limit > 0:
            warm_start = write_mixed_warm_start(
                str(output_dir),
                lp_path.name,
                cfg,
                time_limit=args.warm_start_time_limit,
            ) or ""
        records.append(
            {
                "case": case_name,
                "instance": str(lp_path),
                "warm_start": str(warm_start),
                "full_mode_wafers": full_wafers,
                "mix_mode_wafers": mix_wafers,
            }
        )
        print(f"generated {case_name}: {lp_path}")
    return records


def main():
    args = _parse_args()
    output_root = resolve_path(args.output_root)
    train_records = _generate_group(output_root / "train", TRAIN_CASES, args)
    holdout_records = _generate_group(output_root / "holdout", HOLDOUT_CASES, args)
    manifest_path = output_root / "manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as handle:
        json.dump(
            {
                "train": train_records,
                "holdout": holdout_records,
                "protocol": {
                    "train_instances": len(train_records),
                    "holdout_instances": len(holdout_records),
                    "holdout_used_for_training": False,
                },
            },
            handle,
            ensure_ascii=False,
            indent=2,
        )
    print(f"benchmark manifest: {manifest_path}")


if __name__ == "__main__":
    main()

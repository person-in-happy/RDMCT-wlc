"""Generate leakage-free Petri scheduling train/validation/test size suites."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

AAAI_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = AAAI_ROOT.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from path_utils import resolve_path
from petri_mip_generator import PetriMIPConfig, generate_petri_mip_instance
from petri_warm_start import write_mixed_warm_start


DEFAULT_SPECS = {
    "train": [(4, 0), (0, 4), (4, 4), (8, 4), (4, 8)],
    "validation": [(8, 8), (12, 4), (4, 12)],
    "test": [(12, 12), (16, 8), (8, 16), (16, 16)],
}

QUICK_SPECS = {
    "train": [(4, 0)],
    "validation": [(0, 4)],
    "test": [(4, 4)],
}


def _parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output_dir", default=str(AAAI_ROOT / "data" / "petri"))
    parser.add_argument("--spec_file", default="")
    parser.add_argument(
        "--profile",
        choices=("full", "quick"),
        default="full",
        help="full creates the paper split; quick creates three tiny smoke-test instances.",
    )
    parser.add_argument("--num_pm", type=int, default=2)
    parser.add_argument(
        "--warm_start_time_limit",
        type=float,
        default=0.0,
        help="Build a fingerprinted shared incumbent for mixed instances; 0 disables it.",
    )
    parser.add_argument(
        "--pec_pool_size",
        type=int,
        default=8,
        help="Reusable PEC tokens; the current equipment storage capacity is 10.",
    )
    return parser.parse_args()


def _load_specs(path, profile):
    if not path:
        return QUICK_SPECS if profile == "quick" else DEFAULT_SPECS
    with open(resolve_path(path), "r", encoding="utf-8") as stream:
        payload = json.load(stream)
    return {
        split: [
            (int(item["mode_4x1_wafers"]), int(item["mode_2x2_wafers"]))
            for item in items
        ]
        for split, items in payload.items()
    }


def main():
    args = _parse_args()
    output_root = Path(resolve_path(args.output_dir))
    specs = _load_specs(args.spec_file, args.profile)
    generated = []
    for split, combinations in specs.items():
        split_dir = output_root / split
        split_dir.mkdir(parents=True, exist_ok=True)
        for full_wafers, mix_wafers in combinations:
            total = full_wafers + mix_wafers
            name = f"petri_f{full_wafers}_m{mix_wafers}.lp"
            config = PetriMIPConfig(
                num_batches=max(4, (total + 3) // 4 + 2),
                num_pm=args.num_pm,
                total_wafers=total,
                full_mode_wafers=full_wafers,
                mix_mode_wafers=mix_wafers,
                pec_pool_size=args.pec_pool_size,
                process_mode="auto",
            )
            path = generate_petri_mip_instance(
                str(split_dir),
                name,
                config,
                warm_start_time_limit=0,
            )
            warm_start = ""
            if mix_wafers > 0 and args.warm_start_time_limit > 0:
                warm_start = write_mixed_warm_start(
                    str(split_dir),
                    Path(path).name,
                    config,
                    time_limit=args.warm_start_time_limit,
                ) or ""
            generated.append(
                {
                    "split": split,
                    "mode_4x1_wafers": full_wafers,
                    "mode_2x2_wafers": mix_wafers,
                    "total_wafers": total,
                    "path": str(path),
                    "warm_start": str(warm_start),
                }
            )
            print(path, flush=True)
    manifest_path = output_root / "generated_suite.json"
    with open(manifest_path, "w", encoding="utf-8") as stream:
        json.dump(generated, stream, ensure_ascii=False, indent=2)
    print(f"Suite manifest: {manifest_path}")


if __name__ == "__main__":
    main()

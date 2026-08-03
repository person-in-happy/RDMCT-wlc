"""Generate the frozen C&IE manufacturing experiment suites and SPBS starts."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from petri_mip_generator import PetriMIPConfig, generate_petri_mip_instance
from petri_warm_start import (
    find_compatible_mixed_warm_start,
    repair_incompatible_mixed_warm_start,
    write_mixed_warm_start,
)


RATIOS = {
    "pure41": (4, 0),
    "3to1": (3, 1),
    "1to1": (1, 1),
    "1to3": (1, 3),
    "pure22": (0, 4),
}


def _counts(total: int, ratio: str) -> tuple[int, int]:
    full_part, mix_part = RATIOS[ratio]
    denominator = full_part + mix_part
    full = total * full_part // denominator
    return full, total - full


def _specs(profile: str) -> list[dict]:
    specs: list[dict] = []
    if profile in {"validation", "all"}:
        for full, mix in ((4, 0), (0, 4), (4, 4), (8, 8)):
            specs.append(
                dict(group="validation", total=full + mix, full=full, mix=mix,
                     process_scale=1.0, motion_scale=1.0, pec=8, cleaning=5)
            )
    if profile in {"core", "all"}:
        # 4 sizes x 5 recipe mixes x 3 processing regimes = 60 independent
        # manufacturing scenarios. Solver-seed repetitions are not counted as
        # independent instances in the paper statistics.
        for process_scale in (0.9, 1.0, 1.1):
            for total in (8, 16, 24, 32):
                for ratio in RATIOS:
                    full, mix = _counts(total, ratio)
                    specs.append(
                        dict(group="core", total=total, full=full, mix=mix,
                             ratio=ratio, process_scale=process_scale,
                             motion_scale=1.0, pec=8, cleaning=5)
                    )
    if profile in {"sensitivity", "all"}:
        # One-factor-at-a-time around the nominal n=24, 1:1 case. PEC may only
        # be 8 or 10 in the current two-PM physical configuration.
        settings = [
            ("nominal", 1.0, 1.0, 8, 5),
            ("motion080", 1.0, 0.8, 8, 5),
            ("motion120", 1.0, 1.2, 8, 5),
            ("pec10", 1.0, 1.0, 10, 5),
            ("clean03", 1.0, 1.0, 8, 3),
            ("clean10", 1.0, 1.0, 8, 10),
            ("process080", 0.8, 1.0, 8, 5),
            ("process120", 1.2, 1.0, 8, 5),
        ]
        for label, process_scale, motion_scale, pec, cleaning in settings:
            specs.append(
                dict(group="sensitivity", label=label, total=24, full=12, mix=12,
                     ratio="1to1", process_scale=process_scale,
                     motion_scale=motion_scale, pec=pec, cleaning=cleaning)
            )
    if profile in {"ood", "all"}:
        for total in (40, 48, 64):
            for ratio in ("3to1", "1to1", "1to3"):
                full, mix = _counts(total, ratio)
                specs.append(
                    dict(group="ood", total=total, full=full, mix=mix,
                         ratio=ratio, process_scale=1.0, motion_scale=1.0,
                         pec=8, cleaning=5)
                )
    return specs


def _name(spec: dict) -> str:
    if spec["group"] == "sensitivity":
        suffix = spec["label"]
    else:
        suffix = f"proc{round(100 * spec['process_scale']):03d}"
    return (
        f"cie_{spec['group']}_n{spec['total']:03d}_f{spec['full']:03d}_"
        f"m{spec['mix']:03d}_{suffix}.lp"
    )


def _config(spec: dict) -> PetriMIPConfig:
    process = 180.0 * float(spec["process_scale"])
    motion = float(spec["motion_scale"])
    return PetriMIPConfig(
        num_batches=max(4, (int(spec["total"]) + 3) // 4 + 2),
        total_wafers=int(spec["total"]),
        full_mode_wafers=int(spec["full"]),
        mix_mode_wafers=int(spec["mix"]),
        pec_pool_size=int(spec["pec"]),
        cleaning_interval=int(spec["cleaning"]),
        pm_transfer_gap=1.0 * motion,
        pm_rotation_time_180=2.0 * motion,
        pair_transfer_time=4.0 * motion,
        atr_transfer_time=3.0 * motion,
        atr_return_time=3.0 * motion,
        full_process_time=process,
        mix_boundary_process_time=process,
        mix_internal_process_time=process,
        max_module_residency_time=500.0,
        process_mode="auto",
    )


def _directory(root: Path, spec: dict) -> Path:
    subgroup = "pure41" if int(spec["mix"]) == 0 else "spbs"
    return root / spec["group"] / subgroup


def _parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--action", choices=("generate", "warm-start"), default="generate")
    parser.add_argument(
        "--profile",
        choices=("validation", "core", "sensitivity", "ood", "all"),
        default="all",
    )
    parser.add_argument("--output_dir", default=str(PROJECT_ROOT / "cie" / "data"))
    parser.add_argument("--warm_start_time_limit", type=float, default=180.0)
    parser.add_argument("--memory_limit_mb", type=float, default=2048.0)
    parser.add_argument("--allow_missing_warm_start", action="store_true")
    return parser.parse_args()


def main():
    args = _parse_args()
    root = Path(args.output_dir).resolve()
    records = []
    failures = []
    specs = _specs(args.profile)
    total_specs = len(specs)
    for spec_index, spec in enumerate(specs, start=1):
        cfg = _config(spec)
        folder = _directory(root, spec)
        folder.mkdir(parents=True, exist_ok=True)
        name = _name(spec)
        instance_path = folder / name
        if args.action == "generate":
            # The LP contains numeric timing and residency bounds. Rebuild it
            # even when the deterministic filename already exists so a frozen
            # suite cannot silently retain an obsolete configuration.
            generate_petri_mip_instance(
                str(folder), name, cfg, warm_start_time_limit=0.0,
                append_date=False,
            )
            status = "generated" if instance_path.is_file() else "missing"
            warm_start = ""
        else:
            if not instance_path.is_file():
                raise FileNotFoundError(
                    f"Generate instances before warm starts: {instance_path}"
                )
            if not cfg.mix_wafer_ids:
                status, warm_start = "not_applicable_pure41", ""
            else:
                warm_start = find_compatible_mixed_warm_start(str(folder), name) or ""
                if not warm_start:
                    warm_start = repair_incompatible_mixed_warm_start(
                        str(folder),
                        name,
                        cfg,
                        time_limit=min(
                            600.0,
                            float(args.warm_start_time_limit),
                        ),
                        memory_limit_mb=float(args.memory_limit_mb),
                    ) or ''
                    if warm_start:
                        print(
                            f'repaired compatible SPBS start: {warm_start}',
                            flush=True,
                        )
                if warm_start:
                    print(f"reusing compatible SPBS start: {warm_start}", flush=True)
                else:
                    warm_start = write_mixed_warm_start(
                        str(folder), name, cfg,
                        time_limit=float(args.warm_start_time_limit),
                        memory_limit_mb=float(args.memory_limit_mb),
                    ) or ""
                status = "generated" if warm_start else "failed"
                if not warm_start:
                    failures.append(str(instance_path))
        record = {
            **spec,
            "instance": str(instance_path),
            "warm_start": str(warm_start),
            "status": status,
            "config": asdict(cfg),
        }
        records.append(record)
        with (folder / f"{instance_path.stem}.cie.json").open(
            "w", encoding="utf-8"
        ) as stream:
            json.dump(record, stream, ensure_ascii=False, indent=2)
        print(f"[{spec_index}/{total_specs}] {status}: {instance_path}", flush=True)

    report_path = root / f"{args.action}_{args.profile}_report.json"
    with report_path.open("w", encoding="utf-8") as stream:
        json.dump(
            {"action": args.action, "profile": args.profile,
             "records": records, "failures": failures},
            stream, ensure_ascii=False, indent=2,
        )
    print(f"Report: {report_path}")
    if failures and not args.allow_missing_warm_start:
        raise RuntimeError(
            f"{len(failures)} SPBS starts failed; inspect {report_path}. "
            "Use --allow_missing_warm_start only for diagnostics."
        )


if __name__ == "__main__":
    main()

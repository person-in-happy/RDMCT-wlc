from __future__ import annotations

import argparse
import csv
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Stitch multiple training run progress.csv files into a single CSV for "
            "plotting/reporting, and check whether the runs form a real resume chain."
        )
    )
    parser.add_argument(
        "--runs",
        nargs="+",
        required=True,
        help="Run directories or progress.csv paths, in the order you want to stitch.",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="",
        help=(
            "Output CSV path. Defaults to <first_run_dir>/stitched_progress.csv when omitted."
        ),
    )
    parser.add_argument(
        "--prefer",
        choices=("later", "earlier"),
        default="later",
        help="When duplicate Epoch rows exist, keep the later or earlier run.",
    )
    return parser.parse_args()


def resolve_progress_path(path_like: str) -> Path:
    path = Path(path_like).expanduser().resolve()
    if path.is_dir():
        path = path / "progress.csv"
    if not path.exists():
        raise FileNotFoundError(f"progress.csv not found: {path}")
    return path


def resolve_run_dir(progress_path: Path) -> Path:
    return progress_path.parent.resolve()


def parse_epoch(text: Optional[str], fallback: int) -> int:
    if text is None:
        return fallback
    stripped = text.strip()
    if not stripped:
        return fallback
    try:
        value = float(stripped)
    except ValueError:
        return fallback
    if not math.isfinite(value):
        return fallback
    return int(value)


@dataclass
class RunInfo:
    progress_path: Path
    run_dir: Path
    variant_path: Optional[Path]
    base_log_dir: Optional[Path]
    start_epoch: Optional[int]
    rows: List[Dict[str, str]]
    fieldnames: List[str]
    epochs: List[int]


def load_variant(run_dir: Path) -> Tuple[Optional[Path], Optional[int], Optional[Path]]:
    variant_path = run_dir / "variant.json"
    if not variant_path.exists():
        return None, None, None
    with variant_path.open("r", encoding="utf-8-sig") as file_obj:
        payload = json.load(file_obj)
    experiment = payload.get("experiment", {})
    base_log_dir_raw = experiment.get("base_log_dir")
    base_log_dir = Path(base_log_dir_raw).expanduser().resolve() if base_log_dir_raw else None
    start_epoch_raw = payload.get("start_epoch")
    start_epoch = int(start_epoch_raw) if start_epoch_raw is not None else None
    return variant_path, start_epoch, base_log_dir


def load_run(path_like: str) -> RunInfo:
    progress_path = resolve_progress_path(path_like)
    run_dir = resolve_run_dir(progress_path)
    with progress_path.open("r", encoding="utf-8-sig", newline="") as file_obj:
        reader = csv.DictReader(file_obj)
        fieldnames = list(reader.fieldnames or [])
        rows = list(reader)
    epochs = [parse_epoch(row.get("Epoch"), index + 1) for index, row in enumerate(rows)]
    variant_path, start_epoch, base_log_dir = load_variant(run_dir)
    return RunInfo(
        progress_path=progress_path,
        run_dir=run_dir,
        variant_path=variant_path,
        base_log_dir=base_log_dir,
        start_epoch=start_epoch,
        rows=rows,
        fieldnames=fieldnames,
        epochs=epochs,
    )


def default_output_path(first_run: RunInfo) -> Path:
    return first_run.run_dir / "stitched_progress.csv"


def merge_runs(
    runs: Sequence[RunInfo], prefer: str
) -> Tuple[List[str], List[Dict[str, str]], List[str]]:
    fieldnames: List[str] = []
    merged_by_epoch: Dict[int, Dict[str, str]] = {}
    warnings: List[str] = []

    for run in runs:
        for name in run.fieldnames:
            if name not in fieldnames:
                fieldnames.append(name)
    if "source_run" not in fieldnames:
        fieldnames.append("source_run")

    for run in runs:
        for index, row in enumerate(run.rows):
            epoch = run.epochs[index]
            stitched_row = {name: row.get(name, "") for name in fieldnames if name != "source_run"}
            stitched_row["source_run"] = str(run.run_dir)

            if epoch in merged_by_epoch:
                existing_source = merged_by_epoch[epoch]["source_run"]
                warnings.append(
                    f"duplicate epoch {epoch}: {existing_source} vs {run.run_dir}"
                )
                if prefer == "later":
                    merged_by_epoch[epoch] = stitched_row
            else:
                merged_by_epoch[epoch] = stitched_row

    merged_rows = [merged_by_epoch[epoch] for epoch in sorted(merged_by_epoch)]
    return fieldnames, merged_rows, warnings


def continuity_warnings(runs: Sequence[RunInfo]) -> List[str]:
    warnings: List[str] = []

    for index, run in enumerate(runs):
        if not run.epochs:
            warnings.append(f"{run.run_dir}: progress.csv is empty")
            continue

        min_epoch = min(run.epochs)
        max_epoch = max(run.epochs)

        if run.start_epoch is not None and min_epoch != run.start_epoch + 1:
            warnings.append(
                f"{run.run_dir}: start_epoch={run.start_epoch}, but first logged Epoch is {min_epoch}"
            )

        if index == 0:
            continue

        prev_run = runs[index - 1]
        prev_max_epoch = max(prev_run.epochs) if prev_run.epochs else None
        cur_min_epoch = min(run.epochs) if run.epochs else None

        if prev_max_epoch is not None and cur_min_epoch is not None and cur_min_epoch != prev_max_epoch + 1:
            warnings.append(
                f"{run.run_dir}: epoch sequence jumps from previous max {prev_max_epoch} to current min {cur_min_epoch}"
            )

        if run.base_log_dir is None:
            warnings.append(f"{run.run_dir}: variant.json missing experiment.base_log_dir")
        elif run.base_log_dir != prev_run.run_dir:
            warnings.append(
                f"{run.run_dir}: base_log_dir points to {run.base_log_dir}, expected previous run {prev_run.run_dir}"
            )

    return warnings


def missing_epochs(rows: Sequence[Dict[str, str]]) -> List[int]:
    epochs = sorted({parse_epoch(row.get("Epoch"), index + 1) for index, row in enumerate(rows)})
    if not epochs:
        return []
    expected = set(range(epochs[0], epochs[-1] + 1))
    return sorted(expected.difference(epochs))


def print_run_summary(runs: Sequence[RunInfo]) -> None:
    print("Run summary:")
    for run in runs:
        if run.epochs:
            epoch_summary = f"{min(run.epochs)} -> {max(run.epochs)} ({len(run.epochs)} rows)"
        else:
            epoch_summary = "empty"
        print(f"- run_dir: {run.run_dir}")
        print(f"  progress: {run.progress_path}")
        if run.variant_path is not None:
            print(f"  variant: {run.variant_path}")
        if run.base_log_dir is not None:
            print(f"  base_log_dir: {run.base_log_dir}")
        if run.start_epoch is not None:
            print(f"  start_epoch: {run.start_epoch}")
        print(f"  epochs: {epoch_summary}")


def write_csv(output_path: Path, fieldnames: Sequence[str], rows: Sequence[Dict[str, str]]) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8-sig", newline="") as file_obj:
        writer = csv.DictWriter(file_obj, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def main() -> None:
    args = parse_args()
    runs = [load_run(path_like) for path_like in args.runs]
    output_path = (
        Path(args.output).expanduser().resolve()
        if args.output
        else default_output_path(runs[0]).resolve()
    )

    print_run_summary(runs)

    chain_warnings = continuity_warnings(runs)
    fieldnames, merged_rows, duplicate_warnings = merge_runs(runs, prefer=args.prefer)
    gap_epochs = missing_epochs(merged_rows)

    write_csv(output_path, fieldnames, merged_rows)

    print()
    print(f"stitched rows: {len(merged_rows)}")
    print(f"output: {output_path}")

    if duplicate_warnings:
        print()
        print("Duplicate epoch warnings:")
        for warning in duplicate_warnings:
            print(f"- {warning}")

    if chain_warnings:
        print()
        print("Resume-chain warnings:")
        for warning in chain_warnings:
            print(f"- {warning}")

    if gap_epochs:
        print()
        print(f"Missing epochs in stitched CSV: {gap_epochs}")
    else:
        print()
        print("No missing epochs in stitched CSV.")

    print()
    print(
        "Note: this script only stitches logs for plotting/reporting. "
        "It does not merge model weights or optimizer states."
    )


if __name__ == "__main__":
    main()

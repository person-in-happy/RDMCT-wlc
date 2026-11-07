"""Summarize exact 4x1/2x2 cleaning-interval crossover experiments."""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
from collections import defaultdict
from pathlib import Path


SUITE_RE = re.compile(
    r"^mode_n(?P<wafers>\d{3})_clean(?P<clean>\d{2})_"
    r"(?P<mode>pure41|pure22|mixed11)$"
)
VALUE_RE = re.compile(
    r"^(\S+)\s+([-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?)"
)
BRIDGE_START_RE = re.compile(r"^mix_bridge_start_(\d+)_(\d+)$")


def _parse_int_spec(text: str, *, minimum: int = 1) -> list[int]:
    values: set[int] = set()
    for raw in str(text).split(","):
        token = raw.strip()
        if not token:
            continue
        match = re.fullmatch(r"(\d+)\s*-\s*(\d+)", token)
        if match:
            left, right = (int(item) for item in match.groups())
            if right < left:
                raise ValueError(f"Descending range is not allowed: {token}")
            values.update(range(left, right + 1))
        else:
            values.add(int(token))
    if not values or min(values) < minimum:
        raise ValueError(f"Expected integers >= {minimum}: {text}")
    return sorted(values)


def _parse_solution(path: Path) -> dict[str, float]:
    values: dict[str, float] = {}
    with path.open("r", encoding="utf-8", errors="replace") as stream:
        for raw in stream:
            match = VALUE_RE.match(raw.strip())
            if match and not match.group(1).endswith(":"):
                values[match.group(1)] = float(match.group(2))
    return values


def _audit_bridge_solution(
    path: Path, expected_transfer_time: float = 4.0, tolerance: float = 1.0e-6
) -> dict[str, int]:
    """Verify the combined 4 s exchange and both 4 s split transfer legs."""

    values = _parse_solution(path)
    combined_count = 0
    split_count = 0
    active_count = 0
    for name, start in values.items():
        match = BRIDGE_START_RE.match(name)
        if not match:
            continue
        chamber, cycle = match.groups()
        suffix = f"{chamber}_{cycle}"
        end = values.get(f"mix_bridge_end_{suffix}", start)
        if end <= start + tolerance:
            continue
        active_count += 1
        unload_end = values.get(f"mix_bridge_unload_end_{suffix}")
        load_start = values.get(f"mix_bridge_load_start_{suffix}")
        if unload_end is None or load_start is None:
            raise ValueError(f"Bridge {suffix} lacks split-schema times in {path}")
        combined = values.get(f"mix_bridge_combined_{suffix}", 0.0) >= 0.5
        unload_duration = unload_end - start
        load_duration = end - load_start
        if abs(unload_duration - expected_transfer_time) > tolerance:
            raise ValueError(
                f"Bridge {suffix} unload duration is {unload_duration}, expected "
                f"{expected_transfer_time}: {path}"
            )
        if abs(load_duration - expected_transfer_time) > tolerance:
            raise ValueError(
                f"Bridge {suffix} load duration is {load_duration}, expected "
                f"{expected_transfer_time}: {path}"
            )
        if combined:
            combined_count += 1
            if abs(load_start - start) > tolerance or abs(
                end - start - expected_transfer_time
            ) > tolerance:
                raise ValueError(
                    f"Combined bridge {suffix} is not one {expected_transfer_time}s "
                    f"four-gripper exchange: {path}"
                )
        else:
            split_count += 1
            if load_start + tolerance < unload_end + expected_transfer_time:
                raise ValueError(
                    f"Split bridge {suffix} omits the empty reposition interval: {path}"
                )
    if active_count == 0:
        raise ValueError(f"No active 2x2 bridge was found in {path}")
    return {
        "active": active_count,
        "combined": combined_count,
        "split": split_count,
    }


def _winner(cmax_41: float, cmax_22: float, tolerance: float = 1.0e-3) -> str:
    delta = cmax_22 - cmax_41
    if delta < -tolerance:
        return "2x2"
    if delta > tolerance:
        return "4x1"
    return "tie"


def _write_csv(path: Path, rows: list[dict]) -> None:
    fields = sorted({key for row in rows for key in row}) if rows else ["note"]
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--metrics", required=True)
    parser.add_argument("--output_dir", required=True)
    parser.add_argument("--wafer_counts", default="16,17,20")
    parser.add_argument("--cleaning_intervals", default="2-10")
    parser.add_argument("--solver_seeds", default="1")
    parser.add_argument("--training_seeds", default="1")
    parser.add_argument("--gap_tolerance", type=float, default=1.0e-8)
    parser.add_argument("--objective_tolerance", type=float, default=1.0e-3)
    parser.add_argument("--bridge_time", type=float, default=4.0)
    parser.add_argument("--require_exact", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    wafers = _parse_int_spec(args.wafer_counts)
    intervals = _parse_int_spec(args.cleaning_intervals, minimum=2)
    solver_seeds = _parse_int_spec(args.solver_seeds)
    training_seeds = _parse_int_spec(args.training_seeds)
    expected_seed_pairs = {
        (solver_seed, training_seed)
        for solver_seed in solver_seeds
        for training_seed in training_seeds
    }
    metrics_path = Path(args.metrics).resolve()
    payload = json.loads(metrics_path.read_text(encoding="utf-8"))
    grouped: dict[tuple[int, int, str], list[dict]] = defaultdict(list)
    for row in payload.get("rows", []):
        match = SUITE_RE.match(str(row.get("suite") or ""))
        if not match:
            continue
        key = (
            int(match.group("wafers")),
            int(match.group("clean")),
            match.group("mode"),
        )
        grouped[key].append(row)

    errors: list[str] = []
    cell_rows: dict[tuple[int, int, str], dict] = {}
    for wafer_count in wafers:
        for interval in intervals:
            for mode in ("pure41", "pure22", "mixed11"):
                key = (wafer_count, interval, mode)
                rows = grouped.get(key, [])
                seed_pairs = {
                    (int(row.get("solver_seed")), int(row.get("training_seed")))
                    for row in rows
                    if row.get("solver_seed") is not None
                    and row.get("training_seed") is not None
                }
                if seed_pairs != expected_seed_pairs:
                    errors.append(
                        f"{key}: seed pairs {sorted(seed_pairs)} != "
                        f"{sorted(expected_seed_pairs)}"
                    )
                if len(rows) != len(expected_seed_pairs):
                    errors.append(
                        f"{key}: expected {len(expected_seed_pairs)} rows, "
                        f"found {len(rows)} (missing or duplicate seed cell)"
                    )
                exact_rows = []
                bridge_counts = {"active": 0, "combined": 0, "split": 0}
                for row in rows:
                    gap = row.get("gap")
                    exact = (
                        str(row.get("status")) == "optimal"
                        and gap is not None
                        and math.isfinite(float(gap))
                        and float(gap) <= args.gap_tolerance
                        and row.get("physically_feasible") is True
                        and row.get("cmax_matches_last_product_return") is True
                    )
                    if not exact:
                        errors.append(
                            f"{key}: non-certificate row status={row.get('status')}, "
                            f"gap={gap}, physical={row.get('physically_feasible')}, "
                            "product-return-Cmax="
                            f"{row.get('cmax_matches_last_product_return')}"
                        )
                        continue
                    if mode in {"pure22", "mixed11"}:
                        try:
                            counts = _audit_bridge_solution(
                                Path(row["solution_file"]), args.bridge_time
                            )
                        except (OSError, ValueError) as exc:
                            errors.append(f"{key}: {exc}")
                            continue
                        else:
                            for count_name, count in counts.items():
                                bridge_counts[count_name] += count
                    exact_rows.append(row)
                objectives = [float(row["cmax"]) for row in exact_rows]
                if not objectives:
                    continue
                internal_cleanings = [
                    int(row.get("clean_internal_count", 0)) for row in exact_rows
                ]
                terminal_cleanings = [
                    int(row.get("clean_terminal_count", 0)) for row in exact_rows
                ]
                spread = max(objectives) - min(objectives)
                if spread > args.objective_tolerance:
                    errors.append(f"{key}: certified Cmax spread is {spread}")
                if len(set(internal_cleanings)) > 1 or len(set(terminal_cleanings)) > 1:
                    errors.append(f"{key}: inconsistent internal/terminal cleaning counts")
                cell_rows[key] = {
                    "wafer_count": wafer_count,
                    "cleaning_interval": interval,
                    "mode": {
                        "pure41": "4x1",
                        "pure22": "2x2",
                        "mixed11": "mixed11",
                    }[mode],
                    "replicates": len(exact_rows),
                    "cmax": sum(objectives) / len(objectives),
                    "cmax_spread": spread,
                    "clean_internal_count": internal_cleanings[0],
                    "clean_terminal_count": terminal_cleanings[0],
                    "bridge_active": bridge_counts["active"],
                    "bridge_combined": bridge_counts["combined"],
                    "bridge_split": bridge_counts["split"],
                }

    comparisons: list[dict] = []
    for wafer_count in wafers:
        for interval in intervals:
            full = cell_rows.get((wafer_count, interval, "pure41"))
            pure_22 = cell_rows.get((wafer_count, interval, "pure22"))
            mixed = cell_rows.get((wafer_count, interval, "mixed11"))
            if full is None or pure_22 is None or mixed is None:
                errors.append(
                    f"n={wafer_count}, clean={interval}: missing one or more "
                    "exact three-mode cells"
                )
                continue
            cmax_41 = float(full["cmax"])
            cmax_22 = float(pure_22["cmax"])
            cmax_mixed = float(mixed["cmax"])
            mode_objectives = {
                "4x1": cmax_41,
                "2x2": cmax_22,
                "mixed11": cmax_mixed,
            }
            best_value = min(mode_objectives.values())
            best_modes = [
                name
                for name, value in mode_objectives.items()
                if abs(value - best_value) <= args.objective_tolerance
            ]
            comparisons.append(
                {
                    "wafer_count": wafer_count,
                    "cleaning_interval": interval,
                    "cmax_4x1": cmax_41,
                    "cmax_2x2": cmax_22,
                    "cmax_mixed11": cmax_mixed,
                    "delta_cmax_2x2_minus_4x1": cmax_22 - cmax_41,
                    "pure_mode_winner": _winner(
                        cmax_41, cmax_22, args.objective_tolerance
                    ),
                    "best_of_three": "+".join(best_modes),
                    "wph_4x1": 3600.0 * wafer_count / cmax_41,
                    "wph_2x2": 3600.0 * wafer_count / cmax_22,
                    "wph_mixed11": 3600.0 * wafer_count / cmax_mixed,
                    "clean_internal_4x1": full["clean_internal_count"],
                    "clean_terminal_4x1": full["clean_terminal_count"],
                    "clean_internal_2x2": pure_22["clean_internal_count"],
                    "clean_terminal_2x2": pure_22["clean_terminal_count"],
                    "clean_internal_mixed11": mixed["clean_internal_count"],
                    "clean_terminal_mixed11": mixed["clean_terminal_count"],
                    "replicates_4x1": full["replicates"],
                    "replicates_2x2": pure_22["replicates"],
                    "replicates_mixed11": mixed["replicates"],
                    "combined_bridges_2x2": pure_22["bridge_combined"],
                    "split_bridges_2x2": pure_22["bridge_split"],
                    "combined_bridges_mixed11": mixed["bridge_combined"],
                    "split_bridges_mixed11": mixed["bridge_split"],
                }
            )

    transitions: list[dict] = []
    for wafer_count in wafers:
        rows = sorted(
            (
                row
                for row in comparisons
                if row["wafer_count"] == wafer_count
            ),
            key=lambda row: row["cleaning_interval"],
        )
        switches = []
        for previous, current in zip(rows, rows[1:]):
            if previous["pure_mode_winner"] != current["pure_mode_winner"]:
                switches.append(
                    f"{previous['cleaning_interval']}:"
                    f"{previous['pure_mode_winner']} -> "
                    f"{current['cleaning_interval']}:"
                    f"{current['pure_mode_winner']}"
                )
        transitions.append(
            {
                "wafer_count": wafer_count,
                "first_2x2_win_interval": next(
                    (
                        row["cleaning_interval"]
                        for row in rows
                        if row["pure_mode_winner"] == "2x2"
                    ),
                    None,
                ),
                "last_4x1_win_interval": next(
                    (
                        row["cleaning_interval"]
                        for row in reversed(rows)
                        if row["pure_mode_winner"] == "4x1"
                    ),
                    None,
                ),
                "winner_switches": "; ".join(switches),
                "monotone_single_switch": len(switches) <= 1,
            }
        )

    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    cells_csv = output_dir / "mode_cleaning_cells.csv"
    comparison_csv = output_dir / "mode_cleaning_comparison.csv"
    transition_csv = output_dir / "mode_cleaning_transitions.csv"
    summary_json = output_dir / "mode_cleaning_crossover.json"
    report_md = output_dir / "mode_cleaning_crossover.md"
    _write_csv(cells_csv, list(cell_rows.values()))
    _write_csv(comparison_csv, comparisons)
    _write_csv(transition_csv, transitions)
    summary_json.write_text(
        json.dumps(
            {
                "metrics": str(metrics_path),
                "wafer_counts": wafers,
                "cleaning_intervals": intervals,
                "solver_seeds": solver_seeds,
                "training_seeds": training_seeds,
                "bridge_time": args.bridge_time,
                "exact": not errors,
                "errors": errors,
                "comparisons": comparisons,
                "transitions": transitions,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    focus_rows = [
        row for row in comparisons if row["cleaning_interval"] in {3, 10}
    ]
    report_lines = [
        "# Equal-total-time mode/cleaning crossover",
        "",
        "- Recipe convention: `4x1=180 s`; `2x2=90+90 s`.",
        "- Modes: pure 4x1, pure 2x2, and 1:1 mixed; for odd N, "
        "4x1 receives the extra product wafer.",
        f"- Required bridge exchange: `{args.bridge_time:g} s` when combined.",
        "- Cmax cutoff: last product-wafer return to LP; terminal cleaning with no later process is excluded.",
        f"- Exact certificate set complete: `{not errors}`.",
        "",
        "## Clean3 and clean10",
        "",
        "| Wafers | Cleaning interval | Cmax 4x1 | Cmax 2x2 | "
        "Cmax mixed | Best of three | Pure-mode winner |",
        "| ---: | ---: | ---: | ---: | ---: | --- | --- |",
    ]
    for row in focus_rows:
        report_lines.append(
            f"| {row['wafer_count']} | {row['cleaning_interval']} | "
            f"{row['cmax_4x1']:.6g} | {row['cmax_2x2']:.6g} | "
            f"{row['cmax_mixed11']:.6g} | {row['best_of_three']} | "
            f"{row['pure_mode_winner']} |"
        )
    report_lines.extend(
        [
            "",
            "## Switches",
            "",
            "| Wafers | Last 4x1 win | First 2x2 win | Observed switches |",
            "| ---: | ---: | ---: | --- |",
        ]
    )
    for row in transitions:
        report_lines.append(
            f"| {row['wafer_count']} | {row['last_4x1_win_interval']} | "
            f"{row['first_2x2_win_interval']} | {row['winner_switches']} |"
        )
    if errors:
        report_lines.extend(["", "## Incomplete/invalid cells", ""])
        report_lines.extend(f"- {error}" for error in errors)
    report_md.write_text("\n".join(report_lines) + "\n", encoding="utf-8")
    print(f"Cells CSV: {cells_csv}")
    print(f"Comparison CSV: {comparison_csv}")
    print(f"Transition CSV: {transition_csv}")
    print(f"Summary JSON: {summary_json}")
    print(f"Report: {report_md}")
    if errors and args.require_exact:
        raise RuntimeError(
            f"Crossover conclusion is blocked by {len(errors)} incomplete or invalid checks"
        )


if __name__ == "__main__":
    main()

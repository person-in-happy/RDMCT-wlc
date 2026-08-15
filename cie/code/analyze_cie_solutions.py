"""Validate C&IE SCIP solutions and extract manufacturing-system metrics."""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
import statistics
import sys
from collections import defaultdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scip_imports import scip


VALUE_RE = re.compile(r"^(\S+)\s+([-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?)")
WAFER_RE = re.compile(r"^wafer_completion_(\d+)$")
PROD_STAGE_RE = re.compile(r"^prod_stage_(start|end)_(\d+)_(.+)$")
CH_RE = re.compile(r"^(full|mix_cycle|clean)_(start|end)_(\d+)_(\d+)$")
PEC_STAGE_RE = re.compile(r"^pec_stage_(start|end)_(.+)_(vtr_load|pm|vtr_unload)$")
FULL_USED_RE = re.compile(r"^full_batch_used_(\d+)_(\d+)$")
MIX_USED_RE = re.compile(r"^mix_cycle_used_(\d+)_(\d+)$")
BENCHMARK_META_FIELDS = frozenset({
    "methods", "seeds", "time_limit", "instance_count",
})
BENCHMARK_ROW_FIELDS = frozenset({
    "suite",
    "path",
    "instance",
    "method",
    "seed",
    "training_seed",
    "status",
    "solution_file",
})

# SCIP solves the original in-memory model with a 1e-6 feasibility tolerance.
# Re-reading a text .sol file can move a value by a few last-place decimal
# digits. Keep the solver tolerance and add only a 1e-12 absolute serialization
# allowance; violations above this bound still fail closed.
SCIP_FEASIBILITY_TOLERANCE = 1.0e-6
SOLUTION_SERIALIZATION_ALLOWANCE = 1.0e-12
SOLUTION_FEASIBILITY_TOLERANCE = (
    SCIP_FEASIBILITY_TOLERANCE + SOLUTION_SERIALIZATION_ALLOWANCE
)


def _parse_solution(path: Path) -> dict[str, float]:
    values: dict[str, float] = {}
    with path.open("r", encoding="utf-8", errors="replace") as stream:
        for raw in stream:
            match = VALUE_RE.match(raw.strip())
            if not match or match.group(1).endswith(":"):
                continue
            values[match.group(1)] = float(match.group(2))
    return values


def _union_length(intervals):
    valid = sorted((float(a), float(b)) for a, b in intervals if b > a + 1e-9)
    if not valid:
        return 0.0
    total = 0.0
    left, right = valid[0]
    for next_left, next_right in valid[1:]:
        if next_left <= right + 1e-9:
            right = max(right, next_right)
        else:
            total += right - left
            left, right = next_left, next_right
    return total + right - left


def _peak_overlap(intervals):
    events = []
    for start, end in intervals:
        if end > start + 1e-9:
            events.extend(((float(start), 1), (float(end), -1)))
    active = peak = 0
    for _, delta in sorted(events, key=lambda item: (item[0], item[1])):
        active += delta
        peak = max(peak, active)
    return peak


def _validate(instance_path: Path, solution_path: Path) -> tuple[bool, str]:
    model = scip.Model()
    try:
        model.hideOutput(True)
        model.readProblem(str(instance_path))
        model.setRealParam(
            'numerics/feastol', SOLUTION_FEASIBILITY_TOLERANCE
        )
        # The benchmark environment removes these secondary-objective-only
        # auxiliaries before the primary makespan solve.  Reproduce that exact
        # active model here; routing, resource, timing, and capacity constraints
        # remain untouched and are checked independently by SCIP.
        inactive_prefixes = (
            "schedule_wait_square_def_", "chamber_nonprocess_wait_",
            "schedule_wait_def_", "resource_idle_",
        )
        removable = [
            constraint for constraint in model.getConss()
            if constraint.name == "schedule_stability_def"
            or constraint.name.startswith(inactive_prefixes)
        ]
        for constraint in removable:
            model.delCons(constraint)
        solution = model.readSolFile(str(solution_path))
        feasible = bool(model.checkSol(solution, printreason=False, completely=True))
        note = (
            "checked active primary model at feasibility tolerance "
            f"{SOLUTION_FEASIBILITY_TOLERANCE:.12g}; removed "
            f"{len(removable)} inactive auxiliaries"
        )
        return feasible, note if feasible else f"SCIP checkSol returned false; {note}"
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"
    finally:
        model.freeProb()


def _metrics(row: dict, values: dict[str, float]) -> dict:
    cmax = float(values.get("c_max", row.get("best_objective") or 0.0))
    completions = {
        int(match.group(1)): value
        for name, value in values.items()
        if (match := WAFER_RE.match(name))
    }
    product_stages = defaultdict(dict)
    for name, value in values.items():
        match = PROD_STAGE_RE.match(name)
        if match:
            edge, wafer, stage = match.groups()
            product_stages[(int(wafer), stage)][edge] = value

    cycle_times = []
    for wafer, completion in completions.items():
        release = product_stages.get((wafer, "atr_lp_al"), {}).get("start", 0.0)
        cycle_times.append(max(0.0, completion - release))

    # Reconstruct route waiting directly from physical event times. Do not
    # read schedule_wait_* or optional gap slacks: those auxiliaries are
    # deliberately removed or can float when stage two is disabled.
    route_waits = []
    route_wait_pairs = (
        ("al", "atr_lp_al"),
        ("atr_al_llupper", "al"),
        ("vtr_load", "llupper"),
        ("pm", "vtr_load"),
        ("vtr_unload", "pm"),
        ("atr_lllower_lp", "lllower"),
    )
    for wafer in sorted(completions):
        for later_stage, earlier_stage in route_wait_pairs:
            later = product_stages.get((wafer, later_stage), {}).get("start", 0.0)
            earlier = product_stages.get((wafer, earlier_stage), {}).get("end", 0.0)
            route_waits.append(max(0.0, later - earlier))

    cadence_gaps = []
    cadence_deviations = []
    for mode, used_pattern, start_template, epoch_prefix in (
        ("full", FULL_USED_RE, "full_start", "full_batch_epoch"),
        ("mix", MIX_USED_RE, "mix_cycle_start", "mix_cycle_epoch"),
    ):
        grouped = defaultdict(list)
        for name, value in values.items():
            match = used_pattern.match(name)
            if not match or value < 0.5:
                continue
            chamber, position = (int(item) for item in match.groups())
            epoch = 0
            marker = f"{epoch_prefix}_{chamber}_{position}_"
            for candidate, candidate_value in values.items():
                if candidate.startswith(marker) and candidate_value >= 0.5:
                    epoch = int(candidate.rsplit("_", 1)[-1])
                    break
            start = values.get(f"{start_template}_{chamber}_{position}", 0.0)
            grouped[(mode, chamber, epoch)].append((position, start))
        for items in grouped.values():
            starts = [start for _, start in sorted(items)]
            gaps = [right - left for left, right in zip(starts, starts[1:])]
            cadence_gaps.extend(gaps)
            cadence_deviations.extend(
                abs(right - left) for left, right in zip(gaps, gaps[1:])
            )
    cadence_mean = statistics.fmean(cadence_gaps) if cadence_gaps else 0.0
    cadence_std = statistics.pstdev(cadence_gaps) if cadence_gaps else 0.0

    atr_stage_names = {
        "atr_lp_al", "atr_hold_before_al", "atr_al_exchange",
        "atr_hold_after_al", "atr_al_llupper", "atr_lllower_lp",
    }
    atr_intervals = []
    vtr_intervals = []
    al_intervals = []
    llupper_intervals = []
    lllower_intervals = []
    for (wafer, stage), edges in product_stages.items():
        start, end = edges.get("start", 0.0), edges.get("end", 0.0)
        if stage in atr_stage_names:
            atr_intervals.append((start, end))
        elif stage in {"vtr_load", "vtr_unload"}:
            vtr_intervals.append((start, end))
        elif stage == "al":
            al_intervals.append((start, end))
        elif stage == "llupper":
            occupied_end = product_stages.get((wafer, "vtr_load"), {}).get("start", end)
            llupper_intervals.append((start, occupied_end))
        elif stage == "lllower":
            occupied_end = product_stages.get((wafer, "atr_lllower_lp"), {}).get("start", end)
            lllower_intervals.append((start, occupied_end))

    pec_edges = defaultdict(dict)
    for name, value in values.items():
        match = PEC_STAGE_RE.match(name)
        if match:
            edge, job, stage = match.groups()
            pec_edges[(job, stage)][edge] = value
    pec_residence = defaultdict(dict)
    for (job, stage), edges in pec_edges.items():
        start, end = edges.get("start", 0.0), edges.get("end", 0.0)
        if stage in {"vtr_load", "vtr_unload"}:
            vtr_intervals.append((start, end))
        pec_residence[job][f"{stage}_start"] = start
        pec_residence[job][f"{stage}_end"] = end

    chamber_edges = defaultdict(dict)
    clean_count = 0
    for name, value in values.items():
        match = CH_RE.match(name)
        if match:
            kind, edge, chamber, slot = match.groups()
            chamber_edges[(int(chamber), kind, int(slot))][edge] = value
        if name.startswith("clean_active_") and value >= 0.5:
            clean_count += 1
    chamber_busy = defaultdict(list)
    chamber_clean = defaultdict(list)
    for (chamber, kind, _), edges in chamber_edges.items():
        interval = (edges.get("start", 0.0), edges.get("end", 0.0))
        chamber_busy[chamber].append(interval)
        if kind == "clean":
            chamber_clean[chamber].append(interval)

    pec_intervals = [
        (edges.get("vtr_load_start", 0.0), edges.get("vtr_unload_end", 0.0))
        for edges in pec_residence.values()
    ]
    denom = cmax if cmax > 1e-9 else math.nan
    ch_utils = {
        f"ch{chamber}_utilization": _union_length(intervals) / denom
        for chamber, intervals in chamber_busy.items()
    }
    clean_time = sum(_union_length(items) for items in chamber_clean.values())
    mean_cycle = statistics.fmean(cycle_times) if cycle_times else None
    p95_cycle = None
    if cycle_times:
        ordered = sorted(cycle_times)
        p95_cycle = ordered[min(len(ordered) - 1, math.ceil(0.95 * len(ordered)) - 1)]
    return {
        "total_wafers": len(completions),
        "cmax": cmax,
        "throughput_wph": None if not completions or cmax <= 0 else 3600.0 * len(completions) / cmax,
        "mean_cycle_time": mean_cycle,
        "p95_cycle_time": p95_cycle,
        "atr_utilization": _union_length(atr_intervals) / denom,
        "vtr_utilization": _union_length(vtr_intervals) / denom,
        "al_utilization": _union_length(al_intervals) / denom,
        "llupper_capacity_utilization": sum(max(0.0, b - a) for a, b in llupper_intervals) / (2.0 * denom),
        "lllower_capacity_utilization": sum(max(0.0, b - a) for a, b in lllower_intervals) / (2.0 * denom),
        "pec_peak_in_tool": _peak_overlap(pec_intervals),
        "clean_count": clean_count,
        "clean_time_share": clean_time / (2.0 * denom),
        "physical_route_total_wait": sum(route_waits),
        "physical_route_max_wait": max(route_waits, default=0.0),
        "physical_cadence_cv": (
            0.0 if cadence_mean <= 1e-12 else cadence_std / cadence_mean
        ),
        "physical_cadence_deviation_sum": sum(cadence_deviations),
        **ch_utils,
    }


def _parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input_dir", required=True, help="Directory containing benchmark JSON files.")
    parser.add_argument("--output_dir", required=True)
    parser.add_argument("--validate", action="store_true", help="Use SCIP checkSol on every saved solution.")
    parser.add_argument("--fail_on_invalid", action="store_true")
    return parser.parse_args()


def _is_benchmark_payload(payload):
    """Return whether payload is an original or combined benchmark artifact."""

    if not isinstance(payload, dict):
        return False
    meta = payload.get("meta")
    rows = payload.get("rows")
    if not isinstance(meta, dict) or not BENCHMARK_META_FIELDS.issubset(meta):
        return False
    if not isinstance(meta.get("methods"), list) or not isinstance(meta.get("seeds"), list):
        return False
    if not isinstance(rows, list) or not rows:
        return False
    return all(
        isinstance(row, dict) and BENCHMARK_ROW_FIELDS.issubset(row)
        for row in rows
    )


def _load_benchmark_rows(input_root):
    benchmark_files = []
    rows = []
    for path in sorted(input_root.rglob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not _is_benchmark_payload(payload):
            continue
        benchmark_files.append(str(path))
        rows.extend(payload["rows"])
    return benchmark_files, rows


def main():
    args = _parse_args()
    input_root = Path(args.input_dir).resolve()
    benchmark_files, rows = _load_benchmark_rows(input_root)
    if not rows:
        raise RuntimeError(f"No benchmark JSON with raw rows found under {input_root}")

    output_rows = []
    invalid = []
    seen = set()
    for row in rows:
        solution_text = row.get("solution_file")
        if not solution_text:
            continue
        solution_path = Path(solution_text)
        instance_path = Path(row["path"])
        key = (str(solution_path), str(instance_path))
        if key in seen:
            continue
        seen.add(key)
        values = _parse_solution(solution_path)
        feasible, reason = (True, "not_checked")
        if args.validate:
            feasible, reason = _validate(instance_path, solution_path)
        result = {
            "suite": row.get("suite"), "instance": row.get("instance"),
            "path": str(instance_path), "method": row.get("method"),
            "run_label": row.get("run_label"), "warm_start": row.get("warm_start"),
            "solver_seed": row.get("seed"), "training_seed": row.get("training_seed"),
            "status": row.get("status"), "solving_time": row.get("solving_time"),
            "gap": row.get("gap"), "pdi": row.get("primal_dual_integral"),
            "solution_file": str(solution_path), "physically_feasible": feasible,
            "validation_note": reason,
            **_metrics(row, values),
        }
        output_rows.append(result)
        if not feasible:
            invalid.append(result)

    if not output_rows:
        raise RuntimeError("Benchmark rows exist, but no saved solution_file entries were found.")
    output_root = Path(args.output_dir).resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    csv_path = output_root / "cie_manufacturing_metrics.csv"
    fields = sorted({key for row in output_rows for key in row})
    with csv_path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(output_rows)
    json_path = output_root / "cie_manufacturing_metrics.json"
    json_path.write_text(json.dumps({
        'scip_feasibility_tolerance': SCIP_FEASIBILITY_TOLERANCE,
        'solution_serialization_allowance': SOLUTION_SERIALIZATION_ALLOWANCE,
        'solution_feasibility_tolerance': SOLUTION_FEASIBILITY_TOLERANCE,
        "source_benchmarks": benchmark_files,
        "solution_count": len(output_rows), "invalid_count": len(invalid),
        "rows": output_rows,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    report_path = output_root / "cie_manufacturing_metrics.md"
    report_path.write_text(
        "# C&IE manufacturing metrics\n\n"
        f"- Saved solutions: `{len(output_rows)}`\n"
        f"- SCIP-invalid solutions: `{len(invalid)}`\n"
        f"- Raw table: `{csv_path}`\n",
        encoding="utf-8",
    )
    print(f"Metrics CSV: {csv_path}")
    print(f"Metrics JSON: {json_path}")
    print(f"Validation report: {report_path}")
    if invalid and args.fail_on_invalid:
        raise RuntimeError(f"{len(invalid)} solutions failed SCIP feasibility validation")


if __name__ == "__main__":
    main()

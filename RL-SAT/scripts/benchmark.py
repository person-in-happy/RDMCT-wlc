#!/usr/bin/env python3
"""Run reproducible RL-SAT ablations and merge legacy four-arm results."""

from __future__ import annotations

import argparse
import copy
import csv
import html
import json
import math
import statistics
import sys
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Sequence


RL_SAT_ROOT = Path(__file__).resolve().parents[1]
if str(RL_SAT_ROOT) not in sys.path:
    sys.path.insert(0, str(RL_SAT_ROOT))

from rl_sat.config import load_config  # noqa: E402
from rl_sat.hybrid_solver import HybridRLSATSolver  # noqa: E402
from rl_sat.initial_solution import InitialPlanGenerator  # noqa: E402
from rl_sat.petri_gantt import generate_gantt_charts_from_records  # noqa: E402
from rl_sat.result_io import result_to_dict  # noqa: E402


LEGACY_METHODS = ("solver_only", "a3c_only", "beam_only", "a3c_beam")
RL_SAT_METHODS = (
    "initial_cp_sat",
    "heuristic_beam_cp_sat",
    "a3c_beam_cp_sat",
)
METHOD_ORDER = LEGACY_METHODS + RL_SAT_METHODS
METHOD_LABELS = {
    "solver_only": "SCIP only",
    "a3c_only": "A3C only",
    "beam_only": "Structure/beam only",
    "a3c_beam": "A3C + structure/beam",
    "initial_cp_sat": "RL-SAT initial + CP-SAT",
    "heuristic_beam_cp_sat": "RL-SAT heuristic beam + CP-SAT",
    "a3c_beam_cp_sat": "RL-SAT A3C beam + CP-SAT",
}
METHOD_COLORS = {
    "solver_only": "#4C78A8",
    "a3c_only": "#F58518",
    "beam_only": "#54A24B",
    "a3c_beam": "#E45756",
    "initial_cp_sat": "#72B7B2",
    "heuristic_beam_cp_sat": "#B279A2",
    "a3c_beam_cp_sat": "#FF9DA6",
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Compare all RL-SAT ablations and optionally merge the legacy "
            "solver_only/a3c_only/beam_only/a3c_beam experiment without "
            "invoking SCIP from RL-SAT."
        )
    )
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--checkpoint", type=Path, default=None)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument(
        "--legacy-ablation-json",
        "--scip-baseline-json",
        dest="legacy_ablation_json",
        type=Path,
        default=None,
        help=(
            "Read-only JSON produced by ../run_ablation_experiments.py. "
            "The old --scip-baseline-json spelling remains accepted."
        ),
    )
    parser.add_argument(
        "--allow-partial-legacy",
        action="store_true",
        help="Allow a legacy JSON that does not contain all four old methods.",
    )
    parser.add_argument(
        "--instance-name",
        default=None,
        help="Comparison instance label (default: config.output.run_name).",
    )
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--no-gantt", action="store_true")
    return parser


def _flatten_old_records(payload: Any) -> List[Dict[str, Any]]:
    if isinstance(payload, list):
        return [dict(item) for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []
    if isinstance(payload.get("results"), list):
        return [dict(item) for item in payload["results"] if isinstance(item, dict)]
    if isinstance(payload.get("results"), dict):
        rows = []
        for method, items in payload["results"].items():
            if isinstance(items, list):
                rows.extend(
                    {**item, "method": item.get("method", method)}
                    for item in items
                    if isinstance(item, dict)
                )
        return rows
    return [dict(payload)] if "solution" in payload or "best_obj" in payload else []


def _load_legacy(path: Path | None, allow_partial: bool):
    if path is None:
        return None, []
    source = path.resolve()
    payload = json.loads(source.read_text(encoding="utf-8"))
    records = _flatten_old_records(payload)
    methods = {str(row.get("method", "")) for row in records}
    missing = [method for method in LEGACY_METHODS if method not in methods]
    if missing and not allow_partial:
        raise SystemExit(
            "Legacy ablation JSON is missing required methods: "
            + ", ".join(missing)
            + ". Re-run the old four-arm ablation or pass --allow-partial-legacy."
        )
    return {
        "source": str(source),
        "record_count": len(records),
        "methods_present": sorted(methods),
        "missing_methods": missing,
        "note": "Read-only import; RL-SAT never invokes SCIP.",
    }, records


def _number(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _row(method: str, repeat: int, instance: str, result, elapsed: float) -> Dict[str, Any]:
    return {
        "method": method,
        "family": "rl_sat_cp_sat",
        "instance": instance,
        "repeat": repeat,
        "status": result.status,
        "objective_cmax": result.objective_cmax,
        "best_bound": result.best_bound,
        "relative_gap": result.relative_gap,
        "primal_dual_integral": None,
        "schedule_stability": result.schedule_stability,
        "wall_time": elapsed,
        "solver_wall_time": result.wall_time,
        "certificate_scope": result.certificate_scope,
        "scip_used": result.scip_used,
        "candidate_count": result.metadata.get("hybrid_pipeline", {}).get(
            "candidate_count"
        ),
        "branches": result.metadata.get("branches"),
        "conflicts": result.metadata.get("conflicts"),
    }


def _legacy_row(record: Mapping[str, Any], ordinal: int) -> Dict[str, Any]:
    method = str(record.get("method", "legacy_unknown"))
    return {
        "method": method,
        "family": "legacy_mip_scip",
        "instance": str(record.get("instance", "unknown")),
        "repeat": record.get("repeat", ordinal),
        "status": record.get("status", "UNKNOWN"),
        "objective_cmax": _number(record.get("best_obj")),
        "best_bound": _number(record.get("best_bound")),
        "relative_gap": _number(record.get("primal_dual_gap")),
        "primal_dual_integral": _number(record.get("primaldualintegral")),
        "schedule_stability": record.get("schedule_stability"),
        "wall_time": _number(record.get("wall_time", record.get("solving_time"))),
        "solver_wall_time": _number(record.get("solving_time")),
        "certificate_scope": record.get("certificate_scope", "legacy_mip_scip"),
        "scip_used": True,
        "candidate_count": record.get("n_solutions"),
        "branches": record.get("ntotal_nodes"),
        "conflicts": None,
    }


def _write_csv(rows: Iterable[Dict[str, Any]], path: Path) -> None:
    rows = list(rows)
    fields = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _mean(values: Iterable[Any]) -> float | None:
    valid = [_number(value) for value in values]
    valid = [value for value in valid if value is not None]
    return statistics.fmean(valid) if valid else None


def _summarise(rows: Sequence[Mapping[str, Any]]) -> Dict[str, Dict[str, Any]]:
    summary: Dict[str, Dict[str, Any]] = {}
    for method in METHOD_ORDER:
        selected = [row for row in rows if row.get("method") == method]
        if not selected:
            continue
        feasible = [row for row in selected if _number(row.get("objective_cmax")) is not None]
        summary[method] = {
            "runs": len(selected),
            "feasible_runs": len(feasible),
            "mean_wall_time": _mean(row.get("wall_time") for row in selected),
            "mean_objective": _mean(row.get("objective_cmax") for row in feasible),
            "mean_gap": _mean(row.get("relative_gap") for row in feasible),
            "mean_primal_dual_integral": _mean(
                row.get("primal_dual_integral") for row in selected
            ),
        }
    return summary


def _fmt(value: Any) -> str:
    number = _number(value)
    if number is None:
        return "N/A"
    return f"{number:.4f}" if abs(number) < 1000 else f"{number:.2f}"


def _metric_chart(
    parts: List[str],
    x: float,
    y: float,
    width: float,
    title: str,
    key: str,
    summary: Mapping[str, Mapping[str, Any]],
) -> float:
    methods = [method for method in METHOD_ORDER if method in summary]
    values = [_number(summary[method].get(key)) for method in methods]
    maximum = max((value for value in values if value is not None), default=1.0)
    row_height = 34
    label_width = 230
    value_width = 145
    plot_x = x + label_width
    plot_width = max(width - label_width - value_width, 100)
    parts.append(
        f'<text x="{x:.1f}" y="{y:.1f}" font-size="18" font-weight="700" fill="#222">{html.escape(title)}</text>'
    )
    parts.append(
        f'<text x="{x:.1f}" y="{y + 21:.1f}" font-size="11" fill="#666">Lower is better; N/A is not converted to zero.</text>'
    )
    for index, method in enumerate(methods):
        row_y = y + 40 + index * row_height
        value = values[index]
        fill = 0.0 if value is None else plot_width * value / max(maximum, 1e-12)
        label = html.escape(METHOD_LABELS.get(method, method))
        parts.append(
            f'<text x="{x:.1f}" y="{row_y + 13:.1f}" font-size="12" font-weight="600" fill="#333">{label}</text>'
        )
        parts.append(
            f'<rect x="{plot_x:.1f}" y="{row_y:.1f}" width="{plot_width:.1f}" height="17" rx="8" fill="#E9EDF2"/>'
        )
        if fill > 0:
            parts.append(
                f'<rect x="{plot_x:.1f}" y="{row_y:.1f}" width="{fill:.1f}" height="17" rx="8" fill="{METHOD_COLORS[method]}"/>'
            )
        counts = summary[method]
        parts.append(
            f'<text x="{plot_x + plot_width + 8:.1f}" y="{row_y + 13:.1f}" font-size="11" fill="#444">{_fmt(value)} ({counts["feasible_runs"]}/{counts["runs"]})</text>'
        )
    return 54 + len(methods) * row_height


def _write_comparison_svg(
    path: Path,
    summary: Mapping[str, Mapping[str, Any]],
    instance_label: str,
) -> None:
    width = 1780
    panel_width = 828
    left_x = 42
    right_x = 910
    top = 118
    methods = [method for method in METHOD_ORDER if method in summary]
    chart_height = 54 + len(methods) * 34
    panel_height = 92 + chart_height * 2 + 34
    height = int(top + panel_height + 60)
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        f'<rect width="{width}" height="{height}" fill="#FFFFFF"/>',
        '<text x="42" y="40" font-size="28" font-weight="700" fill="#202020">Legacy + RL-SAT Ablation Comparison</text>',
        f'<text x="42" y="70" font-size="14" fill="#565656">Instance: {html.escape(instance_label)} | Legacy four arms retained; RL-SAT three arms appended.</text>',
        '<text x="42" y="94" font-size="12" fill="#8A4B08">Certificate scopes differ: legacy MIP/SCIP and canonical RL-SAT CP-SAT bounds must not be merged.</text>',
        f'<rect x="{left_x}" y="{top}" width="{panel_width}" height="{panel_height}" rx="18" fill="#F8FBFF" stroke="#D6E3F3"/>',
        f'<rect x="{right_x}" y="{top}" width="{panel_width}" height="{panel_height}" rx="18" fill="#FFF9F4" stroke="#F1DFC9"/>',
        f'<text x="{left_x + 28}" y="{top + 42}" font-size="22" font-weight="700" fill="#1F3B63">Algorithm Efficiency</text>',
        f'<text x="{right_x + 28}" y="{top + 42}" font-size="22" font-weight="700" fill="#7B4A12">Solution Quality</text>',
    ]
    left_y = top + 78
    left_y += _metric_chart(parts, left_x + 28, left_y, panel_width - 56, "Mean Wall Time", "mean_wall_time", summary) + 20
    _metric_chart(parts, left_x + 28, left_y, panel_width - 56, "Mean Primal-Dual Integral", "mean_primal_dual_integral", summary)
    right_y = top + 78
    right_y += _metric_chart(parts, right_x + 28, right_y, panel_width - 56, "Mean Makespan", "mean_objective", summary) + 20
    _metric_chart(parts, right_x + 28, right_y, panel_width - 56, "Mean Relative Gap", "mean_gap", summary)
    parts.append("</svg>")
    path.write_text("\n".join(parts) + "\n", encoding="utf-8")


def _write_markdown(
    path: Path,
    summary: Mapping[str, Mapping[str, Any]],
    artifacts: Mapping[str, Any],
) -> None:
    lines = [
        "# RL-SAT 与旧算法联合消融结果",
        "",
        "旧四组算法原样保留，RL-SAT 三组作为新增对照。不同模型的 bound/gap 证书范围不得混写。",
        "",
        "| 算法 | 有效/总次数 | 平均时间 | 平均 Cmax | 平均 gap | 平均 PDI |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for method in METHOD_ORDER:
        item = summary.get(method)
        if item is None:
            continue
        lines.append(
            f'| {METHOD_LABELS[method]} | {item["feasible_runs"]}/{item["runs"]} | '
            f'{_fmt(item["mean_wall_time"])} | {_fmt(item["mean_objective"])} | '
            f'{_fmt(item["mean_gap"])} | {_fmt(item["mean_primal_dual_integral"])} |'
        )
    lines.extend(
        [
            "",
            "## 产物",
            "",
            f'- 联合对比图：`{artifacts.get("comparison_svg", "")}`',
            f'- 交互甘特图：`{artifacts.get("gantt_index", "")}`',
            f'- 可重绘记录：`{artifacts.get("gantt_records_json", "")}`',
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    args = build_parser().parse_args()
    if args.repeats <= 0:
        raise SystemExit("--repeats must be positive")
    base_config = load_config(args.config)
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    instance_name = args.instance_name or base_config.output.run_name

    legacy_reference, legacy_records = _load_legacy(
        args.legacy_ablation_json,
        args.allow_partial_legacy,
    )
    rows: List[Dict[str, Any]] = [
        _legacy_row(record, ordinal)
        for ordinal, record in enumerate(legacy_records, start=1)
    ]
    gantt_records: List[Dict[str, Any]] = [
        dict(record) for record in legacy_records if record.get("solution")
    ]

    methods = list(RL_SAT_METHODS[:2])
    if args.checkpoint is not None:
        methods.append("a3c_beam_cp_sat")
    for repeat in range(1, args.repeats + 1):
        for method in methods:
            config = copy.deepcopy(base_config)
            config.rl.seed += repeat - 1
            config.cpsat.random_seed += repeat - 1
            checkpoint = args.checkpoint if method == "a3c_beam_cp_sat" else None
            solver = HybridRLSATSolver(config, checkpoint=checkpoint, device=args.device)
            candidates = None
            if method == "initial_cp_sat":
                candidates = [InitialPlanGenerator(solver.problem).generate()]
            started = time.perf_counter()
            result = solver.solve(candidates=candidates)
            elapsed = time.perf_counter() - started
            rows.append(_row(method, repeat, instance_name, result, elapsed))
            record = result_to_dict(result)
            record["method"] = method
            record["instance"] = instance_name
            record.setdefault("metadata", {})["benchmark_repeat"] = repeat
            gantt_records.append(record)

    best_by_instance: Dict[str, float] = {}
    for row in rows:
        objective = _number(row.get("objective_cmax"))
        if objective is None:
            continue
        instance = str(row.get("instance", "unknown"))
        best_by_instance[instance] = min(best_by_instance.get(instance, objective), objective)
    for row in rows:
        objective = _number(row.get("objective_cmax"))
        best = best_by_instance.get(str(row.get("instance", "unknown")))
        row["gap_to_instance_best"] = (
            None
            if objective is None or best is None
            else (objective - best) / max(1.0, abs(best))
        )

    summary = _summarise(rows)
    comparison_svg = output_dir / "comparison.svg"
    _write_comparison_svg(comparison_svg, summary, instance_name)
    records_json = output_dir / "gantt_records.json"
    records_json.write_text(
        json.dumps({"results": gantt_records}, ensure_ascii=False, indent=2, allow_nan=False)
        + "\n",
        encoding="utf-8",
    )
    gantt_outputs: List[str] = []
    if not args.no_gantt:
        gantt_outputs = generate_gantt_charts_from_records(
            gantt_records,
            str(output_dir / "gantt"),
            view="all",
            comparison_svg=str(comparison_svg),
        )

    artifacts = {
        "comparison_svg": str(comparison_svg),
        "gantt_records_json": str(records_json),
        "gantt_outputs": gantt_outputs,
        "gantt_index": str(output_dir / "gantt" / "index.html") if gantt_outputs else "",
    }
    payload = {
        "schema": "rl_sat_benchmark_v2",
        "config": str(args.config.resolve()),
        "checkpoint": str(args.checkpoint.resolve()) if args.checkpoint else None,
        "instance_name": instance_name,
        "repeats": args.repeats,
        "method_order": list(METHOD_ORDER),
        "legacy_reference": legacy_reference,
        "best_by_instance": best_by_instance,
        "summary": summary,
        "rows": rows,
        "artifacts": artifacts,
        "interpretation": {
            "quality": "Compare makespan only for matching physical instances and parameters.",
            "efficiency": "Compare end-to-end wall time only under the same hardware and budget.",
            "bound_scope": (
                "Legacy SCIP/MIP and canonical RL-SAT CP-SAT bounds have different "
                "certificate scopes and are intentionally kept in separate rows."
            ),
            "pec": (
                "RL-SAT uses exact cumulative PEC capacity/dwell windows but symmetry-"
                "aggregates PEC identity; it does not fabricate per-token PEC paths."
            ),
        },
    }
    json_path = output_dir / "benchmark.json"
    csv_path = output_dir / "benchmark.csv"
    markdown_path = output_dir / "README.md"
    json_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    _write_csv(rows, csv_path)
    _write_markdown(markdown_path, summary, artifacts)
    print(
        json.dumps(
            {
                "status": "COMPLETED",
                "benchmark_json": str(json_path),
                "benchmark_csv": str(csv_path),
                "comparison_svg": str(comparison_svg),
                "gantt_index": artifacts["gantt_index"],
                "rows": len(rows),
                "methods": [method for method in METHOD_ORDER if method in summary],
                "scip_invoked_by_rl_sat": False,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
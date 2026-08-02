"""Submission-grade instance-level and DOE analysis for C&IE experiments.

The statistical unit is a manufacturing instance. Solver and policy-training
repetitions are aggregated within an instance before confidence intervals or
paired tests are computed. Inputs may be runner raw CSV files or combined JSON
files containing a rows list.
"""

from __future__ import annotations

import argparse
import csv
import itertools
import json
import math
import re
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Iterable, Sequence

import numpy as np
from scipy.stats import rankdata, t as student_t, wilcoxon


STAGES = ("validation", "main", "stability", "doe", "spbs", "sensitivity", "ood")
RATE_METRICS = ("failure_rate", "optimal_rate", "incumbent_rate")
VALUE_METRICS = ("primal_dual_integral", "gap", "solving_time")
ALL_METRICS = RATE_METRICS + VALUE_METRICS
METRIC_DIRECTIONS = {
    "failure_rate": "lower",
    "optimal_rate": "higher",
    "incumbent_rate": "higher",
    "primal_dual_integral": "lower",
    "gap": "lower",
    "solving_time": "lower",
}
DOE_FACTORS = ("wafer_count", "recipe_mix", "process_scale")
DOE_INTERACTIONS = (
    ("wafer_count", "recipe_mix"),
    ("wafer_count", "process_scale"),
    ("recipe_mix", "process_scale"),
)
DOE_PATTERN = re.compile(
    r"^cie_core_n(?P<total>\d+)_f(?P<full>\d+)_m(?P<mix>\d+)_"
    r"proc(?P<process>\d+)\.lp$",
    re.IGNORECASE,
)
REQUIRED_FIELDS = {
    "suite",
    "path",
    "method",
    "seed",
    "training_seed",
    "run_label",
    "warm_start",
    "status",
    "solving_time",
    "gap",
    "primal_dual_integral",
    "has_incumbent",
    "error",
    "solution_write_error",
}


class AnalysisError(RuntimeError):
    """Input evidence is incomplete or internally inconsistent."""


def _context(path: Path, index: int) -> str:
    return f"{path} row {index}"


def _text(value) -> str:
    return "" if value is None else str(value).strip()


def _required_text(value, field: str, context: str) -> str:
    result = _text(value)
    if not result:
        raise AnalysisError(f"{context}: required field {field!r} is empty")
    return result


def _integer(value, field: str, context: str) -> int:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise AnalysisError(
            f"{context}: field {field!r} must be an integer, got {value!r}"
        ) from exc
    if not math.isfinite(number) or int(number) != number:
        raise AnalysisError(
            f"{context}: field {field!r} must be an integer, got {value!r}"
        )
    return int(number)


def _boolean(value, field: str, context: str) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and value in (0, 1):
        return bool(value)
    normalized = _text(value).lower()
    if normalized in {"true", "1"}:
        return True
    if normalized in {"false", "0"}:
        return False
    raise AnalysisError(
        f"{context}: field {field!r} must be a boolean, got {value!r}"
    )


def _number(value, field: str, context: str):
    if value is None or _text(value) == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise AnalysisError(
            f"{context}: field {field!r} must be numeric or empty, got {value!r}"
        ) from exc
    if not math.isfinite(number):
        raise AnalysisError(
            f"{context}: field {field!r} must be finite, got {value!r}"
        )
    return number


def _variant(row: dict, stage: str, context: str) -> str:
    method = row["method"]
    if stage == "stability":
        profile = _required_text(
            row.get("stability_profile"), "stability_profile", context
        )
        return f"{method}[{profile}]"
    if stage == "spbs":
        label = row["run_label"]
        if not label.startswith("spbs_"):
            raise AnalysisError(
                f"{context}: SPBS run_label must begin with 'spbs_', got {label!r}"
            )
        return f"{method}[{label}]"
    if stage == "doe":
        label = row["run_label"]
        if label != "manufacturing_doe":
            raise AnalysisError(
                f"{context}: DOE run_label must be 'manufacturing_doe', got {label!r}"
            )
        return f"{method}[{label}]"
    return method


def _normalize_row(raw: dict, stage: str, context: str) -> dict:
    if not isinstance(raw, dict):
        raise AnalysisError(f"{context}: benchmark row must be an object")
    missing = sorted(REQUIRED_FIELDS - set(raw))
    if missing:
        raise AnalysisError(f"{context}: missing required fields: {', '.join(missing)}")

    error = _text(raw["error"])
    solution_error = _text(raw["solution_write_error"])
    failure = bool(error or solution_error)
    status = _text(raw["status"]).lower()
    if not status and not failure:
        raise AnalysisError(
            f"{context}: status is empty but no runner/write error is recorded"
        )

    row = {
        "suite": _required_text(raw["suite"], "suite", context),
        "path": _required_text(raw["path"], "path", context),
        "instance": _text(raw.get("instance")),
        "method": _required_text(raw["method"], "method", context),
        "seed": _integer(raw["seed"], "seed", context),
        "training_seed": _integer(raw["training_seed"], "training_seed", context),
        "run_label": _text(raw["run_label"]),
        "warm_start": _text(raw["warm_start"]),
        "stability_profile": (
            _text(raw.get("stability_profile")) if stage == "stability" else ""
        ),
        "status": status,
        "solving_time": _number(raw["solving_time"], "solving_time", context),
        "gap": _number(raw["gap"], "gap", context),
        "primal_dual_integral": _number(
            raw["primal_dual_integral"], "primal_dual_integral", context
        ),
        "has_incumbent": _boolean(
            raw["has_incumbent"], "has_incumbent", context
        ),
        "error": error,
        "solution_write_error": solution_error,
        "failure": failure,
    }
    row["variant"] = _variant(row, stage, context)
    if not failure:
        for field in ("solving_time", "primal_dual_integral"):
            if row[field] is None:
                raise AnalysisError(
                    f"{context}: non-failed row has no finite {field!r}"
                )
        if row["has_incumbent"] and row["gap"] is None:
            raise AnalysisError(f"{context}: incumbent row has no finite 'gap'")
    return row


def _dedup_key(row: dict) -> tuple:
    return (
        row["suite"],
        row["path"],
        row["method"],
        row["seed"],
        row["training_seed"],
        row["run_label"],
        row["warm_start"],
        row["stability_profile"],
    )


def load_rows(input_dir: str | Path, stage: str) -> tuple[list[dict], list[str]]:
    """Load, validate, and deduplicate raw observations."""

    if stage not in STAGES:
        raise AnalysisError(f"unsupported stage {stage!r}; choose from {STAGES}")
    root = Path(input_dir).resolve()
    if not root.is_dir():
        raise AnalysisError(f"input directory does not exist: {root}")

    records: list[tuple[dict, str]] = []
    sources: list[str] = []
    for path in sorted(root.rglob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            continue
        if (
            not isinstance(payload, dict)
            or not isinstance(payload.get("rows"), list)
            or not isinstance(payload.get("meta"), dict)
        ):
            continue
        sources.append(str(path))
        records.extend(
            (row, _context(path, index))
            for index, row in enumerate(payload["rows"], start=1)
        )
    for path in sorted(root.rglob("*_raw.csv")):
        try:
            with path.open("r", encoding="utf-8-sig", newline="") as stream:
                reader = csv.DictReader(stream)
                if reader.fieldnames is None:
                    raise AnalysisError(f"{path}: CSV has no header")
                sources.append(str(path))
                records.extend(
                    (row, _context(path, index))
                    for index, row in enumerate(reader, start=2)
                )
        except UnicodeError as exc:
            raise AnalysisError(f"{path}: raw CSV is not valid UTF-8") from exc
    if not records:
        raise AnalysisError(
            f"no combined JSON rows or *_raw.csv observations found under {root}"
        )

    unique: dict[tuple, dict] = {}
    first_context: dict[tuple, str] = {}
    for raw, context in records:
        row = _normalize_row(raw, stage, context)
        key = _dedup_key(row)
        previous = unique.get(key)
        if previous is None:
            unique[key] = row
            first_context[key] = context
        elif previous != row:
            raise AnalysisError(
                f"conflicting duplicate observation for key {key!r}: "
                f"{first_context[key]} versus {context}"
            )
    return list(unique.values()), sorted(set(sources))


def _mean(values: Iterable[float]):
    values = list(values)
    return statistics.fmean(values) if values else None


def aggregate_instances(rows: Sequence[dict]) -> list[dict]:
    """Collapse solver and training repetitions to manufacturing instances."""

    grouped: dict[tuple, list[dict]] = defaultdict(list)
    for row in rows:
        grouped[(row["suite"], row["path"], row["variant"])].append(row)

    results = []
    for (suite, path, method), repeats in sorted(grouped.items()):
        successful = [row for row in repeats if not row["failure"]]
        pdi = [
            row["primal_dual_integral"]
            for row in successful
            if row["primal_dual_integral"] is not None
        ]
        gaps = [
            row["gap"]
            for row in successful
            if row["has_incumbent"] and row["gap"] is not None
        ]
        times = [
            row["solving_time"]
            for row in successful
            if row["solving_time"] is not None
        ]
        instance_name = next(
            (row["instance"] for row in repeats if row["instance"]),
            re.split(r"[\\/]", path)[-1],
        )
        results.append(
            {
                "suite": suite,
                "path": path,
                "instance": instance_name,
                "method": method,
                "repeat_count": len(repeats),
                "failure_rate": _mean(row["failure"] for row in repeats),
                "optimal_rate": _mean(
                    row["status"] == "optimal" and not row["failure"]
                    for row in repeats
                ),
                "incumbent_rate": _mean(
                    row["has_incumbent"] and not row["failure"] for row in repeats
                ),
                "primal_dual_integral": _mean(pdi),
                "n_primal_dual_integral": len(pdi),
                "gap": _mean(gaps),
                "n_gap": len(gaps),
                "solving_time": _mean(times),
                "n_solving_time": len(times),
            }
        )
    return results


def _finite(value) -> bool:
    return isinstance(value, (int, float)) and math.isfinite(float(value))


def _bootstrap_mean_ci(
    values: Sequence[float], samples: int, seed: int
) -> tuple[float | None, float | None]:
    values = np.asarray(values, dtype=np.float64)
    if values.size == 0:
        return None, None
    if values.size == 1:
        value = float(values[0])
        return value, value
    if samples < 1:
        raise AnalysisError("bootstrap_samples must be at least 1")
    rng = np.random.default_rng(seed)
    indices = rng.integers(0, len(values), size=(samples, len(values)))
    means = values[indices].mean(axis=1)
    low, high = np.quantile(means, (0.025, 0.975))
    return float(low), float(high)


def summarize_methods(
    instance_rows: Sequence[dict], bootstrap_samples: int, bootstrap_seed: int
) -> list[dict]:
    by_method: dict[str, list[dict]] = defaultdict(list)
    for row in instance_rows:
        by_method[row["method"]].append(row)
    summaries = []
    seed_offset = 0
    for method, method_rows in sorted(by_method.items()):
        result = {
            "method": method,
            "n_instances": len(method_rows),
            "raw_runs": sum(row["repeat_count"] for row in method_rows),
        }
        for metric in ALL_METRICS:
            values = [float(row[metric]) for row in method_rows if _finite(row[metric])]
            low, high = _bootstrap_mean_ci(
                values, bootstrap_samples, bootstrap_seed + seed_offset
            )
            seed_offset += 1
            result[metric] = _mean(values)
            result[f"{metric}_ci_low"] = low
            result[f"{metric}_ci_high"] = high
            result[f"n_{metric}"] = len(values)
        summaries.append(result)
    return summaries


def _cohens_dz(differences: Sequence[float]):
    if len(differences) < 2:
        return None
    sd = statistics.stdev(differences)
    if sd <= 1e-15:
        return 0.0 if abs(statistics.fmean(differences)) <= 1e-15 else None
    return statistics.fmean(differences) / sd


def _rank_biserial(differences: Sequence[float]) -> float:
    nonzero = np.asarray(
        [value for value in differences if abs(value) > 1e-15],
        dtype=np.float64,
    )
    if nonzero.size == 0:
        return 0.0
    ranks = rankdata(np.abs(nonzero), method="average")
    positive = float(ranks[nonzero > 0].sum())
    negative = float(ranks[nonzero < 0].sum())
    return (positive - negative) / float(ranks.sum())


def _holm(records: list[dict]) -> None:
    ordered = sorted(enumerate(records), key=lambda item: float(item[1]["p_value"]))
    running = 0.0
    total = len(ordered)
    for rank, (index, record) in enumerate(ordered):
        adjusted = min(1.0, (total - rank) * float(record["p_value"]))
        running = max(running, adjusted)
        records[index]["p_holm"] = running


def compare_methods(
    instance_rows: Sequence[dict],
    reference: str,
    bootstrap_samples: int,
    bootstrap_seed: int,
) -> list[dict]:
    by_method: dict[str, dict[tuple, dict]] = defaultdict(dict)
    for row in instance_rows:
        key = (row["suite"], row["path"])
        if key in by_method[row["method"]]:
            raise AnalysisError(
                f"duplicate instance-method aggregate for {row['method']!r}, {key!r}"
            )
        by_method[row["method"]][key] = row
    if reference not in by_method:
        raise AnalysisError(
            f"reference method {reference!r} is absent; available: {sorted(by_method)}"
        )
    if len(by_method) < 2:
        return []

    tests = []
    seed_offset = 1000
    for comparison, candidate in sorted(by_method.items()):
        if comparison == reference:
            continue
        common = sorted(set(by_method[reference]) & set(candidate))
        if not common:
            raise AnalysisError(
                f"{reference!r} and {comparison!r} have no common instances"
            )
        for metric in ALL_METRICS:
            pairs = [
                (
                    float(by_method[reference][key][metric]),
                    float(candidate[key][metric]),
                )
                for key in common
                if _finite(by_method[reference][key][metric])
                and _finite(candidate[key][metric])
            ]
            if not pairs:
                raise AnalysisError(
                    f"no finite pairs for {reference!r} versus {comparison!r}, "
                    f"metric {metric!r}"
                )
            differences = [right - left for left, right in pairs]
            low, high = _bootstrap_mean_ci(
                differences, bootstrap_samples, bootstrap_seed + seed_offset
            )
            seed_offset += 1
            if all(abs(value) <= 1e-15 for value in differences):
                statistic, p_value = 0.0, 1.0
            else:
                result = wilcoxon(
                    differences,
                    alternative="two-sided",
                    zero_method="wilcox",
                    method="auto",
                )
                statistic, p_value = float(result.statistic), float(result.pvalue)
            tests.append(
                {
                    "reference": reference,
                    "comparison": comparison,
                    "metric": metric,
                    "direction": METRIC_DIRECTIONS[metric],
                    "n_instances": len(pairs),
                    "reference_mean": _mean(left for left, _ in pairs),
                    "comparison_mean": _mean(right for _, right in pairs),
                    "mean_difference_comparison_minus_reference": _mean(differences),
                    "difference_ci_low": low,
                    "difference_ci_high": high,
                    "median_difference_comparison_minus_reference": float(
                        np.median(differences)
                    ),
                    "paired_cohens_dz": _cohens_dz(differences),
                    "matched_pairs_rank_biserial": _rank_biserial(differences),
                    "wilcoxon_statistic": statistic,
                    "p_value": p_value,
                    "p_holm": None,
                }
            )
    _holm(tests)
    return tests


def _doe_factors(row: dict) -> dict:
    name = re.split(r"[\\/]", row["path"])[-1]
    match = DOE_PATTERN.match(name)
    if match is None:
        raise AnalysisError(
            "DOE factors require a generated name of the form "
            f"cie_core_nNNN_fNNN_mNNN_procNNN.lp; got {name!r}"
        )
    total = int(match.group("total"))
    full = int(match.group("full"))
    mix = int(match.group("mix"))
    if full + mix != total:
        raise AnalysisError(
            f"DOE filename {name!r} is inconsistent: full + mix != total"
        )
    if mix == 0:
        ratio = "pure41"
    elif full == 0:
        ratio = "pure22"
    else:
        divisor = math.gcd(full, mix)
        ratio = f"{full // divisor}to{mix // divisor}"
    return {
        "wafer_count": total,
        "recipe_mix": ratio,
        "process_scale": int(match.group("process")) / 100.0,
    }


def _recipe_fraction(value: str) -> float:
    if value == "pure41":
        return 1.0
    if value == "pure22":
        return 0.0
    left, right = (int(item) for item in value.split("to"))
    return left / (left + right)


def _factor_levels(rows: Sequence[dict]) -> dict[str, list]:
    levels = {
        "wafer_count": sorted({row["wafer_count"] for row in rows}),
        "recipe_mix": sorted(
            {row["recipe_mix"] for row in rows},
            key=lambda value: (-_recipe_fraction(value), value),
        ),
        "process_scale": sorted({row["process_scale"] for row in rows}),
    }
    for factor, values in levels.items():
        if len(values) < 2:
            raise AnalysisError(
                f"DOE factor {factor!r} has only {len(values)} level(s): {values}"
            )
    return levels


def _design_matrix(rows: Sequence[dict], levels: dict[str, list]):
    columns = [np.ones(len(rows), dtype=np.float64)]
    terms = [{"term": "Intercept", "effect_type": "intercept"}]
    factor_columns: dict[tuple, np.ndarray] = {}
    for factor in DOE_FACTORS:
        baseline = levels[factor][0]
        for level in levels[factor][1:]:
            column = np.asarray(
                [float(row[factor] == level) for row in rows], dtype=np.float64
            )
            factor_columns[(factor, level)] = column
            columns.append(column)
            terms.append(
                {
                    "term": f"{factor}[T.{level}]",
                    "effect_type": "main",
                    "factor": factor,
                    "level": level,
                    "baseline": baseline,
                }
            )
    for factor_a, factor_b in DOE_INTERACTIONS:
        for level_a in levels[factor_a][1:]:
            for level_b in levels[factor_b][1:]:
                columns.append(
                    factor_columns[(factor_a, level_a)]
                    * factor_columns[(factor_b, level_b)]
                )
                terms.append(
                    {
                        "term": (
                            f"{factor_a}[T.{level_a}]:"
                            f"{factor_b}[T.{level_b}]"
                        ),
                        "effect_type": "interaction",
                        "factor_a": factor_a,
                        "level_a": level_a,
                        "baseline_a": levels[factor_a][0],
                        "factor_b": factor_b,
                        "level_b": level_b,
                        "baseline_b": levels[factor_b][0],
                    }
                )
    return np.column_stack(columns), terms


def _doe_ols(rows: Sequence[dict], response: str, levels: dict[str, list]) -> dict:
    usable = [row for row in rows if _finite(row[response])]
    matrix, terms = _design_matrix(usable, levels)
    values = np.asarray([row[response] for row in usable], dtype=np.float64)
    rank = int(np.linalg.matrix_rank(matrix))
    parameter_count = matrix.shape[1]
    if len(usable) <= parameter_count or rank != parameter_count:
        raise AnalysisError(
            f"DOE response {response!r} is not estimable: n={len(usable)}, "
            f"parameters={parameter_count}, rank={rank}. Missing or censored cells "
            "must be resolved, or the prespecified model changed before analysis."
        )
    coefficients, _, _, _ = np.linalg.lstsq(matrix, values, rcond=None)
    fitted = matrix @ coefficients
    residuals = values - fitted
    degrees_freedom = len(values) - rank
    sse = float(residuals @ residuals)
    mse = sse / degrees_freedom
    inverse_crossproduct = np.linalg.pinv(matrix.T @ matrix)
    standard_errors = np.sqrt(
        np.maximum(np.diag(mse * inverse_crossproduct), 0.0)
    )
    return {
        "response": response,
        "rows": usable,
        "matrix": matrix,
        "terms": terms,
        "values": values,
        "coefficients": coefficients,
        "fitted": fitted,
        "residuals": residuals,
        "rank": rank,
        "parameter_count": parameter_count,
        "degrees_freedom": degrees_freedom,
        "sse": sse,
        "mse": mse,
        "inverse_crossproduct": inverse_crossproduct,
        "standard_errors": standard_errors,
    }


def _doe_effect_rows(fit: dict) -> list[dict]:
    critical = float(student_t.ppf(0.975, fit["degrees_freedom"]))
    effects = []
    for term, estimate, standard_error in zip(
        fit["terms"], fit["coefficients"], fit["standard_errors"]
    ):
        estimate = float(estimate)
        standard_error = float(standard_error)
        if standard_error <= 1e-15:
            t_statistic = 0.0 if abs(estimate) <= 1e-15 else None
            p_value = 1.0 if t_statistic == 0.0 else 0.0
        else:
            t_statistic = estimate / standard_error
            p_value = float(
                2.0 * student_t.sf(
                    abs(t_statistic), fit["degrees_freedom"]
                )
            )
        effects.append(
            {
                "response": fit["response"],
                **term,
                "estimate": estimate,
                "std_error": standard_error,
                "ci_low": estimate - critical * standard_error,
                "ci_high": estimate + critical * standard_error,
                "t_statistic": t_statistic,
                "p_value": p_value,
            }
        )
    return effects


def _doe_diagnostic_rows(fit: dict) -> list[dict]:
    matrix = fit["matrix"]
    residuals = fit["residuals"]
    hat = np.sum(
        matrix * (matrix @ fit["inverse_crossproduct"]), axis=1
    )
    if fit["mse"] <= 1e-30:
        standardized = np.zeros_like(residuals)
    else:
        standardized = residuals / np.sqrt(
            np.maximum(fit["mse"] * (1.0 - hat), 1e-30)
        )
    cooks = (
        standardized**2
        * hat
        / np.maximum(fit["parameter_count"] * (1.0 - hat), 1e-30)
    )
    results = []
    for row, observed, predicted, residual, leverage, std_residual, cook in zip(
        fit["rows"],
        fit["values"],
        fit["fitted"],
        residuals,
        hat,
        standardized,
        cooks,
    ):
        results.append(
            {
                "response": fit["response"],
                "suite": row["suite"],
                "path": row["path"],
                "instance": row["instance"],
                **{factor: row[factor] for factor in DOE_FACTORS},
                "observed": float(observed),
                "fitted": float(predicted),
                "residual": float(residual),
                "leverage": float(leverage),
                "standardized_residual": float(std_residual),
                "cooks_distance": float(cook),
            }
        )
    return results


def _doe_model_record(fit: dict) -> dict:
    centered = fit["values"] - fit["values"].mean()
    sst = float(centered @ centered)
    if sst <= 1e-30:
        r_squared = 1.0 if fit["sse"] <= 1e-30 else None
    else:
        r_squared = 1.0 - fit["sse"] / sst
    adjusted = (
        None
        if r_squared is None
        else 1.0
        - (1.0 - r_squared)
        * (len(fit["values"]) - 1)
        / fit["degrees_freedom"]
    )
    return {
        "response": fit["response"],
        "n_observations": len(fit["values"]),
        "n_parameters": fit["parameter_count"],
        "rank": fit["rank"],
        "residual_degrees_freedom": fit["degrees_freedom"],
        "rmse": math.sqrt(max(fit["mse"], 0.0)),
        "r_squared": r_squared,
        "adjusted_r_squared": adjusted,
        "condition_number": float(np.linalg.cond(fit["matrix"])),
        "coding": "treatment coding; first listed level is the baseline",
        "main_effect_interpretation": (
            "conditional level contrast at baseline levels of other factors"
        ),
    }


def _fit_doe_response(
    rows: Sequence[dict],
    response: str,
    levels: dict[str, list],
) -> tuple[dict, list[dict], list[dict]]:
    fit = _doe_ols(rows, response, levels)
    return (
        _doe_model_record(fit),
        _doe_effect_rows(fit),
        _doe_diagnostic_rows(fit),
    )


def analyze_doe(
    instance_rows: Sequence[dict], reference: str
) -> tuple[dict, list[dict], list[dict]]:
    selected = [
        dict(row, **_doe_factors(row))
        for row in instance_rows
        if row["method"] == reference
    ]
    if not selected:
        raise AnalysisError(
            f"DOE reference method {reference!r} has no instance-level rows"
        )
    levels = _factor_levels(selected)
    observed = {
        tuple(row[factor] for factor in DOE_FACTORS) for row in selected
    }
    expected = set(
        itertools.product(*(levels[factor] for factor in DOE_FACTORS))
    )
    missing = sorted(expected - observed, key=str)
    if missing:
        preview = ", ".join(map(str, missing[:5]))
        raise AnalysisError(
            f"DOE is not complete; {len(missing)} factorial cells are missing "
            f"(first: {preview})"
        )

    models = []
    effects = []
    diagnostics = []
    for response in ALL_METRICS:
        model, response_effects, response_diagnostics = _fit_doe_response(
            selected, response, levels
        )
        models.append(model)
        effects.extend(response_effects)
        diagnostics.extend(response_diagnostics)
    metadata = {
        "reference_method": reference,
        "factors": levels,
        "baselines": {factor: levels[factor][0] for factor in DOE_FACTORS},
        "prespecified_interactions": [
            f"{left}:{right}" for left, right in DOE_INTERACTIONS
        ],
        "complete_factorial_cells": len(expected),
        "observed_factorial_cells": len(observed),
        "models": models,
    }
    return metadata, effects, diagnostics


def _write_csv(path: Path, rows: Sequence[dict], fields: Sequence[str]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _create_doe_plots(
    output_dir: Path,
    effects: Sequence[dict],
    diagnostics: Sequence[dict],
) -> tuple[list[str], str | None]:
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError as exc:
        return [], f"matplotlib unavailable: {exc}"

    paths = []
    pdi_effects = [
        row
        for row in effects
        if row["response"] == "primal_dual_integral"
        and row["effect_type"] != "intercept"
    ]
    if pdi_effects:
        height = max(6.0, 0.28 * len(pdi_effects))
        figure, axis = plt.subplots(figsize=(11, height))
        positions = np.arange(len(pdi_effects))
        estimates = np.asarray([row["estimate"] for row in pdi_effects])
        lower = estimates - np.asarray([row["ci_low"] for row in pdi_effects])
        upper = np.asarray([row["ci_high"] for row in pdi_effects]) - estimates
        axis.errorbar(
            estimates,
            positions,
            xerr=np.vstack((lower, upper)),
            fmt="o",
            capsize=3,
        )
        axis.axvline(0.0, color="black", linewidth=0.8)
        axis.set_yticks(positions, [row["term"] for row in pdi_effects])
        axis.invert_yaxis()
        axis.set_xlabel("PDI coefficient with 95% confidence interval")
        axis.set_title("Prespecified DOE effects (non-AI generated)")
        figure.tight_layout()
        path = output_dir / "cie_submission_doe_pdi_effects.png"
        figure.savefig(path, dpi=200)
        plt.close(figure)
        paths.append(str(path))

    figure, axes = plt.subplots(3, 2, figsize=(12, 13))
    for axis, response in zip(axes.flat, ALL_METRICS):
        rows = [row for row in diagnostics if row["response"] == response]
        axis.scatter(
            [row["fitted"] for row in rows],
            [row["standardized_residual"] for row in rows],
            s=18,
            alpha=0.8,
        )
        axis.axhline(0.0, color="black", linewidth=0.8)
        axis.axhline(2.0, color="gray", linewidth=0.6, linestyle="--")
        axis.axhline(-2.0, color="gray", linewidth=0.6, linestyle="--")
        axis.set_title(response)
        axis.set_xlabel("Fitted")
        axis.set_ylabel("Standardized residual")
    figure.suptitle("DOE residual diagnostics (non-AI generated)")
    figure.tight_layout()
    path = output_dir / "cie_submission_doe_diagnostics.png"
    figure.savefig(path, dpi=200)
    plt.close(figure)
    paths.append(str(path))
    return paths, None


def analyze_submission(
    input_dir: str | Path,
    output_dir: str | Path,
    stage: str,
    reference: str,
    *,
    bootstrap_samples: int = 2000,
    bootstrap_seed: int = 2027,
    make_plots: bool = True,
) -> dict:
    """Run validated analysis and write machine-readable outputs."""

    if bootstrap_samples < 1:
        raise AnalysisError("bootstrap_samples must be at least 1")
    rows, sources = load_rows(input_dir, stage)
    instances = aggregate_instances(rows)
    summaries = summarize_methods(
        instances, bootstrap_samples, bootstrap_seed
    )
    comparisons = compare_methods(
        instances, reference, bootstrap_samples, bootstrap_seed
    )

    doe_metadata = None
    doe_effects: list[dict] = []
    doe_diagnostics: list[dict] = []
    if stage == "doe":
        doe_metadata, doe_effects, doe_diagnostics = analyze_doe(
            instances, reference
        )

    output = Path(output_dir).resolve()
    output.mkdir(parents=True, exist_ok=True)
    instance_path = output / "cie_submission_instance_metrics.csv"
    summary_path = output / "cie_submission_method_summary.csv"
    comparison_path = output / "cie_submission_pairwise_tests.csv"
    analysis_path = output / "cie_submission_analysis.json"

    instance_fields = [
        "suite",
        "instance",
        "path",
        "method",
        "repeat_count",
        *RATE_METRICS,
        *[
            field
            for metric in VALUE_METRICS
            for field in (metric, f"n_{metric}")
        ],
    ]
    summary_fields = ["method", "n_instances", "raw_runs"]
    for metric in ALL_METRICS:
        summary_fields.extend(
            (
                metric,
                f"{metric}_ci_low",
                f"{metric}_ci_high",
                f"n_{metric}",
            )
        )
    comparison_fields = [
        "reference",
        "comparison",
        "metric",
        "direction",
        "n_instances",
        "reference_mean",
        "comparison_mean",
        "mean_difference_comparison_minus_reference",
        "difference_ci_low",
        "difference_ci_high",
        "median_difference_comparison_minus_reference",
        "paired_cohens_dz",
        "matched_pairs_rank_biserial",
        "wilcoxon_statistic",
        "p_value",
        "p_holm",
    ]
    _write_csv(instance_path, instances, instance_fields)
    _write_csv(summary_path, summaries, summary_fields)
    _write_csv(comparison_path, comparisons, comparison_fields)
    outputs = {
        "instance_metrics": str(instance_path),
        "method_summary": str(summary_path),
        "pairwise_tests": str(comparison_path),
    }
    plot_warning = None
    if stage == "doe":
        effects_path = output / "cie_submission_doe_effects.csv"
        diagnostics_path = output / "cie_submission_doe_diagnostics.csv"
        models_path = output / "cie_submission_doe_models.json"
        effect_fields = [
            "response",
            "effect_type",
            "term",
            "factor",
            "level",
            "baseline",
            "factor_a",
            "level_a",
            "baseline_a",
            "factor_b",
            "level_b",
            "baseline_b",
            "estimate",
            "std_error",
            "ci_low",
            "ci_high",
            "t_statistic",
            "p_value",
        ]
        diagnostic_fields = [
            "response",
            "suite",
            "instance",
            "path",
            *DOE_FACTORS,
            "observed",
            "fitted",
            "residual",
            "leverage",
            "standardized_residual",
            "cooks_distance",
        ]
        _write_csv(effects_path, doe_effects, effect_fields)
        _write_csv(diagnostics_path, doe_diagnostics, diagnostic_fields)
        models_path.write_text(
            json.dumps(
                doe_metadata, ensure_ascii=False, indent=2, allow_nan=False
            ),
            encoding="utf-8",
        )
        outputs.update(
            {
                "doe_effects": str(effects_path),
                "doe_diagnostics": str(diagnostics_path),
                "doe_models": str(models_path),
            }
        )
        if make_plots:
            plots, plot_warning = _create_doe_plots(
                output, doe_effects, doe_diagnostics
            )
            outputs["doe_plots"] = plots

    payload = {
        "stage": stage,
        "reference_method": reference,
        "sources": sources,
        "unique_raw_runs": len(rows),
        "manufacturing_instance_method_rows": len(instances),
        "aggregation_unit": "manufacturing instance",
        "repeat_aggregation": (
            "solver and training repetitions are averaged within each "
            "manufacturing instance before inference"
        ),
        "failure_definition": (
            "non-empty runner error or solution_write_error; time and memory "
            "limits remain solver outcomes, not infrastructure failures"
        ),
        "metric_availability": {
            "primal_dual_integral": "all non-failed rows",
            "gap": "non-failed rows with an incumbent",
            "solving_time": "all non-failed rows, including limit outcomes",
        },
        "bootstrap": {
            "confidence_level": 0.95,
            "samples": bootstrap_samples,
            "seed": bootstrap_seed,
            "resampling_unit": "manufacturing instance",
        },
        "paired_tests": {
            "test": "two-sided Wilcoxon signed-rank",
            "difference": "comparison minus reference",
            "holm_scope": "all reference-vs-comparison metric tests",
            "metric_directions": METRIC_DIRECTIONS,
        },
        "method_summaries": summaries,
        "comparisons": comparisons,
        "doe": doe_metadata,
        "plot_warning": plot_warning,
        "outputs": outputs,
    }
    report_path = output / "cie_submission_analysis.md"
    outputs["analysis"] = str(analysis_path)
    outputs["report"] = str(report_path)
    analysis_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False),
        encoding="utf-8",
    )
    report_path.write_text(
        "# C&IE submission analysis\n\n"
        f"- Stage: {stage}\n"
        f"- Reference: {reference}\n"
        f"- Unique raw runs: {len(rows)}\n"
        f"- Instance-method rows: {len(instances)}\n"
        "- Statistical unit: manufacturing instance\n"
        "- Inference: bootstrap 95% CI and two-sided paired Wilcoxon with "
        "global Holm adjustment\n"
        f"- Machine-readable analysis: {analysis_path.name}\n",
        encoding="utf-8",
    )
    return payload


def _parse_args(argv: Sequence[str] | None = None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input_dir", required=True)
    parser.add_argument("--output_dir", required=True)
    parser.add_argument("--stage", required=True, choices=STAGES)
    parser.add_argument(
        "--reference",
        "--reference_method",
        dest="reference",
        required=True,
    )
    parser.add_argument("--bootstrap_samples", type=int, default=2000)
    parser.add_argument("--bootstrap_seed", type=int, default=2027)
    parser.add_argument("--no_plots", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        payload = analyze_submission(
            args.input_dir,
            args.output_dir,
            args.stage,
            args.reference,
            bootstrap_samples=args.bootstrap_samples,
            bootstrap_seed=args.bootstrap_seed,
            make_plots=not args.no_plots,
        )
    except AnalysisError as exc:
        raise SystemExit(f"C&IE submission analysis failed: {exc}") from exc
    print(f"Analysis: {payload['outputs']['analysis']}")
    print(f"Report: {payload['outputs']['report']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

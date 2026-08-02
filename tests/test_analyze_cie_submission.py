import csv
import importlib.util
import json
from pathlib import Path

import pytest


SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "cie"
    / "code"
    / "analyze_cie_submission.py"
)
SPEC = importlib.util.spec_from_file_location("analyze_cie_submission", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)

FIELDS = [
    "suite",
    "path",
    "instance",
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
]


def _write_rows(folder, rows):
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "campaign_raw.csv"
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    return path


def _row(path, method, seed, training_seed, pdi, gap, solve_time, **extra):
    row = {
        "suite": "cie_core",
        "path": str(path),
        "instance": Path(path).name,
        "method": method,
        "seed": seed,
        "training_seed": training_seed,
        "run_label": extra.pop("run_label", "main"),
        "warm_start": "none",
        "status": extra.pop("status", "optimal"),
        "solving_time": solve_time,
        "gap": gap,
        "primal_dual_integral": pdi,
        "has_incumbent": extra.pop("has_incumbent", True),
        "error": extra.pop("error", ""),
        "solution_write_error": extra.pop("solution_write_error", ""),
    }
    row.update(extra)
    return row


def test_instance_first_pairing_bootstrap_wilcoxon_and_holm(tmp_path):
    rows = []
    for instance_index in range(6):
        instance = tmp_path / f"case_{instance_index}.lp"
        for solver_seed in (1, 2):
            rows.append(
                _row(
                    instance,
                    "scip_default",
                    solver_seed,
                    -1,
                    20 + instance_index + solver_seed,
                    0.20,
                    10,
                )
            )
            for training_seed in (1, 2):
                rows.append(
                    _row(
                        instance,
                        "proposed",
                        solver_seed,
                        training_seed,
                        10 + instance_index + solver_seed + training_seed,
                        0.10,
                        8,
                    )
                )
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    _write_rows(input_dir, rows)
    payload = MODULE.analyze_submission(
        input_dir,
        output_dir,
        "main",
        "scip_default",
        bootstrap_samples=200,
        bootstrap_seed=19,
        make_plots=False,
    )

    assert payload["unique_raw_runs"] == 36
    assert payload["manufacturing_instance_method_rows"] == 12
    summary = {row["method"]: row for row in payload["method_summaries"]}
    assert summary["scip_default"]["raw_runs"] == 12
    assert summary["proposed"]["raw_runs"] == 24
    tests = payload["comparisons"]
    assert {row["metric"] for row in tests} == set(MODULE.ALL_METRICS)
    assert all(row["n_instances"] == 6 for row in tests)
    assert all(0 <= row["p_holm"] <= 1 for row in tests)
    pdi = next(row for row in tests if row["metric"] == "primal_dual_integral")
    assert pdi["mean_difference_comparison_minus_reference"] < 0
    assert pdi["matched_pairs_rank_biserial"] < 0
    saved = json.loads(
        (output_dir / "cie_submission_analysis.json").read_text(encoding="utf-8")
    )
    assert saved["paired_tests"]["test"] == "two-sided Wilcoxon signed-rank"


def test_missing_required_schema_field_fails_explicitly(tmp_path):
    input_dir = tmp_path / "input"
    row = _row(tmp_path / "case.lp", "scip_default", 1, -1, 10, 0, 1)
    del row["primal_dual_integral"]
    _write_rows(input_dir, [row])
    with pytest.raises(MODULE.AnalysisError, match="no finite.*primal"):
        MODULE.load_rows(input_dir, "main")


def test_doe_effects_interactions_ci_and_diagnostics(tmp_path):
    rows = []
    for total in (8, 16):
        for full, mix in ((total, 0), (total // 2, total // 2)):
            for process in (90, 110):
                name = (
                    f"cie_core_n{total:03d}_f{full:03d}_m{mix:03d}_"
                    f"proc{process:03d}.lp"
                )
                instance = tmp_path / name
                base = total + mix * 0.3 + process * 0.05
                rows.append(
                    _row(
                        instance,
                        "scip_default",
                        1,
                        -1,
                        base,
                        0.1 + 0.001 * mix,
                        base / 2,
                        run_label="manufacturing_doe",
                    )
                )
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    _write_rows(input_dir, rows)
    payload = MODULE.analyze_submission(
        input_dir,
        output_dir,
        "doe",
        "scip_default[manufacturing_doe]",
        bootstrap_samples=50,
        make_plots=False,
    )

    assert payload["doe"]["complete_factorial_cells"] == 8
    assert payload["doe"]["prespecified_interactions"] == [
        "wafer_count:recipe_mix",
        "wafer_count:process_scale",
        "recipe_mix:process_scale",
    ]
    with (output_dir / "cie_submission_doe_effects.csv").open(
        encoding="utf-8-sig"
    ) as stream:
        effects = list(csv.DictReader(stream))
    assert {row["effect_type"] for row in effects} >= {"main", "interaction"}
    assert all(row["ci_low"] != "" and row["ci_high"] != "" for row in effects)
    with (output_dir / "cie_submission_doe_diagnostics.csv").open(
        encoding="utf-8-sig"
    ) as stream:
        diagnostics = list(csv.DictReader(stream))
    assert len(diagnostics) == len(MODULE.ALL_METRICS) * 8
    assert {row["response"] for row in diagnostics} == set(MODULE.ALL_METRICS)

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from cie.code.audit_cie_submission import (
    PRIMARY_KEY_FIELDS,
    REQUIRED_ROW_FIELDS,
    PrimaryKey,
    _canonical_conflict_value,
    audit_campaign,
    build_expected_matrix,
    main,
)


def test_csv_jsonl_boolean_values_are_compared_semantically():
    assert _canonical_conflict_value("has_incumbent", "False") is False
    assert _canonical_conflict_value("has_incumbent", False) is False
    assert _canonical_conflict_value("has_incumbent", "true") is True
    assert _canonical_conflict_value("has_incumbent", True) is True
    assert _canonical_conflict_value("has_incumbent", "False") != (
        _canonical_conflict_value("has_incumbent", True)
    )


SUITES = {
    "validation": ("cie_validation", "validation"),
    "main": ("cie_core_nominal", "test"),
    "stability": ("cie_core_nominal", "test"),
    "doe": ("cie_core", "test"),
    "spbs": ("cie_core_spbs", "test"),
    "sensitivity": ("cie_sensitivity", "test"),
    "ood": ("cie_ood", "test"),
}


def _write_manifest(tmp_path: Path, stage: str, instance_count: int = 1) -> Path:
    config_dir = tmp_path / "configs"
    data_dir = tmp_path / "data"
    config_dir.mkdir(parents=True)
    data_dir.mkdir(parents=True)
    suite, split = SUITES[stage]
    for index in range(instance_count):
        (data_dir / f"instance_{index:02d}.lp").write_text(
            "Minimize\n obj: x\nSubject To\n c: x >= 0\nEnd\n",
            encoding="utf-8",
        )
    manifest = {
        "suites": [
            {
                "name": suite,
                "family": "test",
                "scale": "test",
                "split": split,
                "root": "../data",
                "glob": "*.lp",
            }
        ]
    }
    path = config_dir / "manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    return path


def _write_csv(path: Path, rows: list[dict], fields: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = fields or sorted({field for row in rows for field in row})
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _read_csv(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        return [dict(row) for row in csv.DictReader(stream)]


def _write_jsonl(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(record) + "\n" for record in records),
        encoding="utf-8",
    )


def _make_valid_campaign(
    tmp_path: Path,
    stage: str = "validation",
    solver_seeds: tuple[int, ...] = (1, 2),
    training_seeds: tuple[int, ...] = (1, 2),
):
    manifest = _write_manifest(tmp_path, stage)
    campaign = tmp_path / "campaign"
    raw_path = campaign / "shard" / "runs" / "formal_raw.csv"
    checkpoint_path = campaign / "shard" / "runs" / ".checkpoints" / "formal.jsonl"
    solution_dir = campaign / "shard" / "solutions"
    solution_dir.mkdir(parents=True)
    expected = build_expected_matrix(
        stage,
        manifest,
        solver_seeds=solver_seeds,
        training_seeds=training_seeds,
    )
    rows = []
    for index, expected_run in enumerate(expected.values(), start=1):
        key = expected_run.key
        solution = solution_dir / f"solution_{index:04d}.sol"
        solution.write_text("solution status: feasible\nx 0\n", encoding="utf-8")
        rows.append(
            {
                "suite": key.suite,
                "relative_path": key.relative_path,
                "path": str(expected_run.instance_path),
                "instance": expected_run.instance_name,
                "split": expected_run.split,
                "method": key.method,
                "seed": key.solver_seed,
                "training_seed": key.training_seed,
                "run_label": key.run_label,
                "warm_start": key.warm_start,
                "stability_profile": key.stability_profile,
                "status": "optimal",
                "error": "",
                "has_incumbent": True,
                "solution_file": str(solution),
                "solution_write_error": "",
            }
        )
    _write_csv(raw_path, rows)
    benchmark_json = raw_path.with_suffix(".json")
    benchmark_json.write_text(json.dumps({"rows": rows}), encoding="utf-8")
    checkpoint_records = [
        {"record_type": "meta", "signature": "test-signature"},
        *(
            {"record_type": "row", "key": str(index), "row": row}
            for index, row in enumerate(rows)
        ),
        {
            "record_type": "complete",
            "artifacts": [str(raw_path), str(benchmark_json)],
        },
    ]
    _write_jsonl(checkpoint_path, checkpoint_records)

    analysis = tmp_path / "analysis"
    analysis.mkdir()
    analysis_rows = [
        {
            "solution_file": row["solution_file"],
            "physically_feasible": True,
            "validation_note": "checked active primary model",
        }
        for row in rows
    ]
    metrics = {
        "source_benchmarks": [str(benchmark_json)],
        "solution_count": len(analysis_rows),
        "invalid_count": 0,
        "rows": analysis_rows,
    }
    (analysis / "cie_manufacturing_metrics.json").write_text(
        json.dumps(metrics), encoding="utf-8"
    )
    _write_csv(analysis / "cie_manufacturing_metrics.csv", analysis_rows)
    (analysis / "cie_manufacturing_metrics.md").write_text(
        "# metrics\n\n- SCIP-invalid solutions: `0`\n", encoding="utf-8"
    )
    return {
        "manifest": manifest,
        "campaign": campaign,
        "analysis": analysis,
        "raw": raw_path,
        "checkpoint": checkpoint_path,
        "rows": rows,
        "expected": expected,
        "solver_seeds": solver_seeds,
        "training_seeds": training_seeds,
    }


@pytest.mark.parametrize(
    ("stage", "expected_count"),
    [
        ("validation", 2),
        ("main", 24),
        ("stability", 12),
        ("doe", 2),
        ("spbs", 4),
        ("sensitivity", 2),
        ("ood", 24),
    ],
)
def test_stage_expected_matrices(stage, expected_count, tmp_path):
    manifest = _write_manifest(tmp_path, stage)
    expected = build_expected_matrix(
        stage,
        manifest,
        solver_seeds=(1, 2),
        training_seeds=(1, 2),
    )
    assert len(expected) == expected_count
    assert len(set(expected)) == expected_count


def test_primary_key_explicitly_contains_all_formal_dimensions():
    assert tuple(PrimaryKey.__dataclass_fields__) == (
        "stage",
        "suite",
        "relative_path",
        "method",
        "solver_seed",
        "training_seed",
        "run_label",
        "warm_start",
        "stability_profile",
    )
    for field in ("training_seed", "run_label", "warm_start", "stability_profile"):
        assert field in PRIMARY_KEY_FIELDS


def test_complete_campaign_passes_csv_jsonl_solution_and_analysis_audit(tmp_path):
    fixture = _make_valid_campaign(tmp_path)
    report = audit_campaign(
        stage="validation",
        input_dir=fixture["campaign"],
        analysis_dir=fixture["analysis"],
        manifest_path=fixture["manifest"],
        solver_seeds=fixture["solver_seeds"],
        training_seeds=fixture["training_seeds"],
    )
    assert report.ok, report.issues
    assert report.expected_rows == 2
    assert report.csv_rows == 2
    assert report.jsonl_rows == 2
    assert report.incumbent_rows == 2


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("missing_row", "exact expected count"),
        ("duplicate_row", "Duplicate raw CSV primary key"),
        ("row_error", "has benchmark error"),
        ("missing_solution", "incumbent solution does not exist"),
        ("duplicate_solution", "is reused by two primary keys"),
        ("missing_stability", "missing required columns"),
        ("incomplete_checkpoint", "is incomplete"),
        ("invalid_analysis", "invalid_count=1"),
        ("unchecked_analysis", "was not checked by SCIP"),
        ("missing_analysis_artifact", "artifact is missing"),
    ],
)
def test_incomplete_or_invalid_campaign_is_rejected(tmp_path, mutation, message):
    fixture = _make_valid_campaign(tmp_path)
    rows = _read_csv(fixture["raw"])
    if mutation == "missing_row":
        _write_csv(fixture["raw"], rows[:-1])
    elif mutation == "duplicate_row":
        _write_csv(fixture["raw"], rows + [rows[0]])
    elif mutation == "row_error":
        rows[0]["error"] = "MemoryError"
        _write_csv(fixture["raw"], rows)
    elif mutation == "missing_solution":
        Path(rows[0]["solution_file"]).unlink()
    elif mutation == "duplicate_solution":
        rows[1]["solution_file"] = rows[0]["solution_file"]
        _write_csv(fixture["raw"], rows)
    elif mutation == "missing_stability":
        fields = [field for field in rows[0] if field != "stability_profile"]
        trimmed = [{key: value for key, value in row.items() if key in fields} for row in rows]
        _write_csv(fixture["raw"], trimmed, fields)
    elif mutation == "incomplete_checkpoint":
        records = [
            json.loads(line)
            for line in fixture["checkpoint"].read_text(encoding="utf-8").splitlines()
        ]
        _write_jsonl(
            fixture["checkpoint"],
            [record for record in records if record.get("record_type") != "complete"],
        )
    elif mutation in {"invalid_analysis", "unchecked_analysis"}:
        metrics_path = fixture["analysis"] / "cie_manufacturing_metrics.json"
        metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
        if mutation == "invalid_analysis":
            metrics["invalid_count"] = 1
        else:
            metrics["rows"][0]["validation_note"] = "not_checked"
        metrics_path.write_text(json.dumps(metrics), encoding="utf-8")
    elif mutation == "missing_analysis_artifact":
        (fixture["analysis"] / "cie_manufacturing_metrics.md").unlink()

    report = audit_campaign(
        stage="validation",
        input_dir=fixture["campaign"],
        analysis_dir=fixture["analysis"],
        manifest_path=fixture["manifest"],
        solver_seeds=fixture["solver_seeds"],
        training_seeds=fixture["training_seeds"],
    )
    assert not report.ok
    assert any(message in issue for issue in report.issues), report.issues


def test_cli_returns_nonzero_and_requires_checked_analysis(tmp_path, capsys):
    fixture = _make_valid_campaign(tmp_path)
    metrics_path = fixture["analysis"] / "cie_manufacturing_metrics.json"
    metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
    metrics["invalid_count"] = 2
    metrics_path.write_text(json.dumps(metrics), encoding="utf-8")

    exit_code = main(
        [
            "--stage",
            "validation",
            "--input-dir",
            str(fixture["campaign"]),
            "--analysis-dir",
            str(fixture["analysis"]),
            "--manifest",
            str(fixture["manifest"]),
            "--solver-seeds",
            "1,2",
        ]
    )
    captured = capsys.readouterr()
    assert exit_code == 1
    assert "AUDIT FAIL" in captured.out
    assert "invalid_count=2" in captured.err


def test_required_row_schema_contains_solution_and_error_contract():
    for field in (
        "error",
        "has_incumbent",
        "solution_file",
        "solution_write_error",
        "stability_profile",
    ):
        assert field in REQUIRED_ROW_FIELDS

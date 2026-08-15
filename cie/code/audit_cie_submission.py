"""Fail-closed acceptance audit for formal C&IE experiment campaigns.

The benchmark runner persists expensive observations twice: completed batches are
written as ``*_raw.csv`` files, while crash-safe progress is appended to JSONL
checkpoint files.  This audit treats CSV rows as the final campaign artifacts and
uses JSONL rows to detect dangling, conflicting, or incomplete checkpoints.

SCIP feasibility checking is intentionally not repeated here.  Pass
``--analysis-dir`` pointing at output produced by::

    python cie/code/analyze_cie_solutions.py --input_dir <campaign> \
        --output_dir <analysis> --validate --fail_on_invalid

The audit verifies that those validation artifacts cover every incumbent exactly
once and report ``invalid_count == 0``.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable, Mapping, Sequence


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MANIFEST = PROJECT_ROOT / "cie" / "configs" / "cie_benchmark_suites.json"
INSTANCE_SUFFIXES = (".lp", ".mps", ".cip", ".lp.gz", ".mps.gz")
DEFAULT_SOLVER_SEEDS = tuple(range(1, 11))
DEFAULT_TRAINING_SEEDS = tuple(range(1, 6))
STAGES = (
    "validation",
    "main",
    "stability",
    "doe",
    "spbs",
    "sensitivity",
    "ood",
)

LEARNED_METHODS = (
    "hem",
    "rdmct_feature_only",
    "hem_beam",
    "hem_structure",
    "proposed",
)
TRAINING_SEED_ONE_METHODS = (
    "scip_default",
    "adaptive_cutsel",
    *LEARNED_METHODS,
)
STABILITY_PROFILES = ("full", "stage2_off", "linear_off")

PRIMARY_KEY_FIELDS = (
    "suite",
    "relative_path",
    "method",
    "seed",
    "training_seed",
    "run_label",
    "warm_start",
    "stability_profile",
)
REQUIRED_ROW_FIELDS = (
    *PRIMARY_KEY_FIELDS,
    "path",
    "instance",
    "split",
    "error",
    "has_incumbent",
    "solution_file",
    "solution_write_error",
)


class AuditConfigurationError(RuntimeError):
    """Raised when the requested audit cannot be constructed."""


@dataclass(frozen=True, order=True)
class PrimaryKey:
    """Unique experimental unit within one audited stage."""

    stage: str
    suite: str
    relative_path: str
    method: str
    solver_seed: int
    training_seed: int
    run_label: str
    warm_start: str
    stability_profile: str

    def display(self) -> str:
        return (
            f"{self.stage}/{self.suite}/{self.relative_path} | {self.method} | "
            f"solver={self.solver_seed} | train={self.training_seed} | "
            f"label={self.run_label!r} | warm={self.warm_start} | "
            f"stability={self.stability_profile}"
        )


@dataclass(frozen=True)
class ExpectedRun:
    key: PrimaryKey
    instance_path: Path
    instance_name: str
    split: str


@dataclass
class SourceRow:
    source: Path
    line_number: int
    kind: str
    row: dict

    def location(self) -> str:
        return f"{self.source}:{self.line_number}"


@dataclass
class CheckpointInfo:
    path: Path
    row_count: int = 0
    meta_records: list[dict] = field(default_factory=list)
    complete_records: list[dict] = field(default_factory=list)
    is_checkpoint: bool = False


@dataclass
class AuditReport:
    stage: str
    expected_rows: int
    csv_rows: int = 0
    jsonl_rows: int = 0
    incumbent_rows: int = 0
    csv_files: list[str] = field(default_factory=list)
    jsonl_files: list[str] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.issues

    def to_dict(self) -> dict:
        payload = asdict(self)
        payload["ok"] = self.ok
        return payload


@dataclass(frozen=True)
class SuiteInstance:
    suite: str
    split: str
    relative_path: str
    path: Path
    solver_seeds: tuple[int, ...]


STAGE_SUITES = {
    "validation": "cie_validation",
    "main": "cie_core_nominal",
    "stability": "cie_core_nominal",
    "doe": "cie_core",
    "spbs": "cie_core_spbs",
    "sensitivity": "cie_sensitivity",
    "ood": "cie_ood",
}


def _canonical_relative_path(value: object) -> str:
    text = str(value or "").strip().replace("\\", "/")
    while text.startswith("./"):
        text = text[2:]
    return text


def _path_identity(value: object, anchors: Sequence[Path] = ()) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    path = Path(text).expanduser()
    candidates = [path] if path.is_absolute() else [anchor / path for anchor in anchors]
    if not candidates:
        candidates = [path]
    selected = next((item for item in candidates if item.exists()), candidates[0])
    try:
        selected = selected.resolve(strict=False)
    except OSError:
        selected = selected.absolute()
    return os.path.normcase(str(selected))


def _parse_integer(value: object, name: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{name} must be an integer, not a boolean")
    text = str(value).strip()
    if not text:
        raise ValueError(f"{name} is empty")
    try:
        return int(text)
    except ValueError as exc:
        raise ValueError(f"{name}={value!r} is not an integer") from exc


def _parse_bool(value: object, name: str) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"true", "1", "yes"}:
        return True
    if text in {"false", "0", "no"}:
        return False
    raise ValueError(f"{name}={value!r} is not a boolean")


def _canonical_conflict_value(field_name: str, value: object) -> object:
    """Normalize CSV and JSONL values before cross-artifact comparison."""
    if field_name == "has_incumbent":
        return _parse_bool(value, field_name)
    return str(value or "").strip()


def parse_seed_list(value: str, name: str) -> tuple[int, ...]:
    try:
        values = tuple(
            _parse_integer(item, name)
            for item in str(value).split(",")
            if item.strip()
        )
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc
    if not values:
        raise argparse.ArgumentTypeError(f"{name} must contain at least one seed")
    if len(values) != len(set(values)):
        raise argparse.ArgumentTypeError(f"{name} contains duplicate seeds: {value}")
    return values


def _load_suite_instances(manifest_path: Path, suite_name: str) -> list[SuiteInstance]:
    manifest_path = manifest_path.resolve()
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise AuditConfigurationError(f"Cannot read manifest {manifest_path}: {exc}") from exc
    suites = [item for item in payload.get("suites", []) if item.get("name") == suite_name]
    if len(suites) != 1:
        raise AuditConfigurationError(
            f"Manifest must define suite {suite_name!r} exactly once; found {len(suites)}"
        )
    suite = suites[0]
    root = Path(str(suite.get("root", ""))).expanduser()
    if not root.is_absolute():
        root = (manifest_path.parent / root).resolve()
    pattern = str(suite.get("glob", "**/*"))
    if root.is_file():
        paths = [root]
    elif root.is_dir():
        paths = sorted(
            path
            for path in root.glob(pattern)
            if path.is_file()
            and any(str(path).lower().endswith(suffix) for suffix in INSTANCE_SUFFIXES)
        )
    else:
        paths = []
    if not paths:
        raise AuditConfigurationError(
            f"Suite {suite_name!r} has no instances under {root} matching {pattern!r}"
        )
    suite_seeds = tuple(_parse_integer(item, "manifest suite seed") for item in suite.get("seeds", []))
    split = str(suite.get("split", "test"))
    return [
        SuiteInstance(
            suite=suite_name,
            split=split,
            relative_path=_canonical_relative_path(
                path.relative_to(root) if root.is_dir() else path.name
            ),
            path=path.resolve(),
            solver_seeds=suite_seeds,
        )
        for path in paths
    ]


def _stage_dimensions(
    stage: str,
    training_seeds: Sequence[int],
    spbs_warm_starts: str,
) -> list[tuple[str, int, str, str, str]]:
    """Return method, training seed, run label, warm start, stability profile."""

    if stage == "validation":
        return [("scip_default", -1, "final_validation", "none", "full")]
    if stage in {"main", "ood"}:
        dimensions = []
        for training_seed in training_seeds:
            methods = (
                TRAINING_SEED_ONE_METHODS
                if training_seed == 1
                else LEARNED_METHODS
            )
            dimensions.extend(
                (method, training_seed, f"trainseed_{training_seed}", "auto", "full")
                for method in methods
            )
        return dimensions
    if stage == "stability":
        return [
            (
                "proposed",
                training_seed,
                f"stability_{profile}_trainseed_{training_seed}",
                "auto",
                profile,
            )
            for profile in STABILITY_PROFILES
            for training_seed in training_seeds
        ]
    if stage == "doe":
        return [("scip_default", -1, "manufacturing_doe", "auto", "full")]
    if stage == "spbs":
        warm_starts = ("none", "auto") if spbs_warm_starts == "both" else (spbs_warm_starts,)
        return [
            ("scip_default", -1, f"spbs_{warm_start}", warm_start, "full")
            for warm_start in warm_starts
        ]
    if stage == "sensitivity":
        return [("scip_default", -1, "", "auto", "full")]
    raise AuditConfigurationError(f"Unsupported stage: {stage!r}")


def build_expected_matrix(
    stage: str,
    manifest_path: Path | str = DEFAULT_MANIFEST,
    solver_seeds: Sequence[int] = DEFAULT_SOLVER_SEEDS,
    training_seeds: Sequence[int] = DEFAULT_TRAINING_SEEDS,
    spbs_warm_starts: str = "both",
) -> dict[PrimaryKey, ExpectedRun]:
    if stage not in STAGES:
        raise AuditConfigurationError(f"Unsupported stage: {stage!r}")
    if not solver_seeds:
        raise AuditConfigurationError("At least one solver seed is required")
    if stage in {"main", "stability", "ood"} and not training_seeds:
        raise AuditConfigurationError(f"Stage {stage} requires training seeds")
    if spbs_warm_starts not in {"both", "none", "auto"}:
        raise AuditConfigurationError(
            f"spbs_warm_starts must be both, none, or auto; got {spbs_warm_starts!r}"
        )
    instances = _load_suite_instances(Path(manifest_path), STAGE_SUITES[stage])
    dimensions = _stage_dimensions(stage, training_seeds, spbs_warm_starts)
    expected: dict[PrimaryKey, ExpectedRun] = {}
    for instance in instances:
        seeds = instance.solver_seeds or tuple(int(value) for value in solver_seeds)
        for solver_seed in seeds:
            for method, training_seed, run_label, warm_start, stability in dimensions:
                key = PrimaryKey(
                    stage=stage,
                    suite=instance.suite,
                    relative_path=instance.relative_path,
                    method=method,
                    solver_seed=int(solver_seed),
                    training_seed=int(training_seed),
                    run_label=run_label,
                    warm_start=warm_start,
                    stability_profile=stability,
                )
                if key in expected:
                    raise AuditConfigurationError(f"Expected matrix generated duplicate key: {key.display()}")
                expected[key] = ExpectedRun(
                    key=key,
                    instance_path=instance.path,
                    instance_name=instance.path.name,
                    split=instance.split,
                )
    return expected


def _iter_files(root: Path, suffix: str) -> Iterable[Path]:
    if root.is_file():
        if root.suffix.lower() == suffix:
            yield root
        return
    if not root.is_dir():
        return
    for path in sorted(root.rglob(f"*{suffix}")):
        try:
            relative_parts = path.relative_to(root).parts[:-1]
        except ValueError:
            relative_parts = path.parts[:-1]
        if any(part.lower() == "combined" for part in relative_parts):
            continue
        yield path


def _looks_like_raw_csv(path: Path) -> bool:
    if path.name.lower().endswith("_raw.csv"):
        return True
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as stream:
            fields = set(csv.DictReader(stream).fieldnames or [])
    except OSError:
        return False
    return {"suite", "method", "seed", "training_seed", "relative_path"}.issubset(fields)


def _read_csv_rows(root: Path, report: AuditReport) -> list[SourceRow]:
    rows: list[SourceRow] = []
    for path in _iter_files(root, ".csv"):
        if not _looks_like_raw_csv(path):
            continue
        report.csv_files.append(str(path))
        try:
            with path.open("r", encoding="utf-8-sig", newline="") as stream:
                reader = csv.DictReader(stream)
                fields = set(reader.fieldnames or [])
                missing = sorted(set(REQUIRED_ROW_FIELDS) - fields)
                if missing:
                    report.issues.append(
                        f"Raw CSV {path} is missing required columns: {', '.join(missing)}"
                    )
                for line_number, row in enumerate(reader, start=2):
                    rows.append(SourceRow(path, line_number, "csv", dict(row)))
        except (OSError, csv.Error) as exc:
            report.issues.append(f"Cannot read raw CSV {path}: {exc}")
    report.csv_rows = len(rows)
    if not report.csv_files:
        report.issues.append(f"No raw benchmark CSV was found recursively under {root}")
    return rows


def _read_jsonl_rows(
    root: Path, report: AuditReport
) -> tuple[list[SourceRow], list[CheckpointInfo]]:
    rows: list[SourceRow] = []
    checkpoints: list[CheckpointInfo] = []
    for path in _iter_files(root, ".jsonl"):
        report.jsonl_files.append(str(path))
        info = CheckpointInfo(path=path)
        try:
            with path.open("r", encoding="utf-8") as stream:
                for line_number, line in enumerate(stream, start=1):
                    if not line.strip():
                        continue
                    try:
                        record = json.loads(line)
                    except json.JSONDecodeError as exc:
                        report.issues.append(f"Malformed JSONL at {path}:{line_number}: {exc}")
                        continue
                    if not isinstance(record, dict):
                        report.issues.append(
                            f"JSONL record at {path}:{line_number} is not an object"
                        )
                        continue
                    record_type = record.get("record_type")
                    if record_type in {"meta", "row", "complete"}:
                        info.is_checkpoint = True
                    if record_type == "meta":
                        info.meta_records.append(record)
                    elif record_type == "complete":
                        info.complete_records.append(record)
                    elif record_type == "row":
                        row = record.get("row")
                        if not isinstance(row, dict):
                            report.issues.append(
                                f"Checkpoint row at {path}:{line_number} has no row object"
                            )
                            continue
                        info.row_count += 1
                        rows.append(SourceRow(path, line_number, "jsonl", dict(row)))
                    elif record_type is None and {"suite", "method", "seed"}.issubset(record):
                        rows.append(SourceRow(path, line_number, "jsonl", dict(record)))
        except OSError as exc:
            report.issues.append(f"Cannot read JSONL {path}: {exc}")
        checkpoints.append(info)
    report.jsonl_rows = len(rows)
    return rows, checkpoints


def _primary_key(source_row: SourceRow, stage: str, report: AuditReport) -> PrimaryKey | None:
    row = source_row.row
    missing = [field for field in PRIMARY_KEY_FIELDS if field not in row]
    if missing:
        report.issues.append(
            f"{source_row.location()} cannot form the formal primary key; "
            f"missing fields: {', '.join(missing)}"
        )
        return None
    try:
        solver_seed = _parse_integer(row["seed"], "seed")
        training_seed = _parse_integer(row["training_seed"], "training_seed")
    except ValueError as exc:
        report.issues.append(f"{source_row.location()} has invalid primary key: {exc}")
        return None
    return PrimaryKey(
        stage=stage,
        suite=str(row["suite"] or "").strip(),
        relative_path=_canonical_relative_path(row["relative_path"]),
        method=str(row["method"] or "").strip(),
        solver_seed=solver_seed,
        training_seed=training_seed,
        run_label=str(row["run_label"] or "").strip(),
        warm_start=str(row["warm_start"] or "").strip(),
        stability_profile=str(row["stability_profile"] or "").strip(),
    )


def _validate_common_row(source_row: SourceRow, report: AuditReport) -> None:
    row = source_row.row
    missing = [field for field in REQUIRED_ROW_FIELDS if field not in row]
    if missing:
        report.issues.append(
            f"{source_row.location()} is missing required fields: {', '.join(missing)}"
        )
        return
    if str(row.get("error") or "").strip():
        report.issues.append(
            f"{source_row.location()} has benchmark error: {row.get('error')}"
        )
    if str(row.get("solution_write_error") or "").strip():
        report.issues.append(
            f"{source_row.location()} has solution_write_error: "
            f"{row.get('solution_write_error')}"
        )
    try:
        has_incumbent = _parse_bool(row.get("has_incumbent"), "has_incumbent")
    except ValueError as exc:
        report.issues.append(f"{source_row.location()} {exc}")
        return
    solution_text = str(row.get("solution_file") or "").strip()
    if has_incumbent and not solution_text:
        report.issues.append(
            f"{source_row.location()} has_incumbent is true but solution_file is empty"
        )
    if not has_incumbent and solution_text:
        report.issues.append(
            f"{source_row.location()} has_incumbent is false but solution_file is populated"
        )


def _validate_expected_identity(
    source_row: SourceRow,
    expected: ExpectedRun,
    input_root: Path,
    report: AuditReport,
) -> None:
    row = source_row.row
    if str(row.get("instance") or "") != expected.instance_name:
        report.issues.append(
            f"{source_row.location()} instance={row.get('instance')!r}, "
            f"expected {expected.instance_name!r}"
        )
    if str(row.get("split") or "") != expected.split:
        report.issues.append(
            f"{source_row.location()} split={row.get('split')!r}, expected {expected.split!r}"
        )
    actual_path = _path_identity(row.get("path"), (input_root, PROJECT_ROOT))
    expected_path = _path_identity(expected.instance_path)
    if actual_path != expected_path:
        report.issues.append(
            f"{source_row.location()} path does not match manifest instance: "
            f"{row.get('path')!r} != {expected.instance_path}"
        )


def _format_examples(keys: Iterable[PrimaryKey], limit: int = 8) -> str:
    ordered = sorted(keys)
    shown = "; ".join(key.display() for key in ordered[:limit])
    if len(ordered) > limit:
        shown += f"; ... ({len(ordered) - limit} more)"
    return shown


def _resolve_artifact_path(value: object, input_root: Path) -> Path:
    path = Path(str(value)).expanduser()
    if path.is_absolute():
        return path
    candidates = (PROJECT_ROOT / path, input_root / path)
    return next((candidate for candidate in candidates if candidate.exists()), candidates[0])


def _validate_checkpoints(
    checkpoints: Sequence[CheckpointInfo], input_root: Path, report: AuditReport
) -> None:
    for checkpoint in checkpoints:
        if not checkpoint.is_checkpoint:
            continue
        if len(checkpoint.meta_records) != 1:
            report.issues.append(
                f"Checkpoint {checkpoint.path} has {len(checkpoint.meta_records)} meta records; expected 1"
            )
        elif not str(checkpoint.meta_records[0].get("signature") or "").strip():
            report.issues.append(f"Checkpoint {checkpoint.path} has no signature")
        if len(checkpoint.complete_records) != 1:
            report.issues.append(
                f"Checkpoint {checkpoint.path} is incomplete: "
                f"{checkpoint.row_count} row records and "
                f"{len(checkpoint.complete_records)} complete markers"
            )
            continue
        artifacts = checkpoint.complete_records[0].get("artifacts")
        if not isinstance(artifacts, list) or not artifacts:
            report.issues.append(
                f"Checkpoint {checkpoint.path} complete marker has no artifact list"
            )
            continue
        missing = [
            str(_resolve_artifact_path(item, input_root))
            for item in artifacts
            if not _resolve_artifact_path(item, input_root).is_file()
        ]
        if missing:
            report.issues.append(
                f"Checkpoint {checkpoint.path} references missing artifacts: {', '.join(missing)}"
            )


def _validate_solutions(
    csv_by_key: Mapping[PrimaryKey, SourceRow], input_root: Path, report: AuditReport
) -> set[str]:
    solution_to_key: dict[str, PrimaryKey] = {}
    incumbent_solutions: set[str] = set()
    for key, source_row in csv_by_key.items():
        row = source_row.row
        try:
            has_incumbent = _parse_bool(row.get("has_incumbent"), "has_incumbent")
        except ValueError:
            continue
        if not has_incumbent:
            continue
        solution_text = str(row.get("solution_file") or "").strip()
        if not solution_text:
            continue
        solution_path = Path(solution_text).expanduser()
        if not solution_path.is_absolute():
            candidates = (input_root / solution_path, source_row.source.parent / solution_path)
            solution_path = next(
                (candidate for candidate in candidates if candidate.exists()), candidates[0]
            )
        identity = _path_identity(solution_path)
        if solution_path.suffix.lower() != ".sol":
            report.issues.append(
                f"{source_row.location()} incumbent solution is not a .sol file: {solution_path}"
            )
        if not solution_path.is_file():
            report.issues.append(
                f"{source_row.location()} incumbent solution does not exist: {solution_path}"
            )
        previous = solution_to_key.get(identity)
        if previous is not None and previous != key:
            report.issues.append(
                f"Incumbent solution {solution_path} is reused by two primary keys: "
                f"{previous.display()} and {key.display()}"
            )
        solution_to_key[identity] = key
        incumbent_solutions.add(identity)
    report.incumbent_rows = len(incumbent_solutions)
    if not incumbent_solutions:
        report.issues.append("Campaign has no incumbent .sol files to validate")
    return incumbent_solutions


def _read_analysis_csv(path: Path, report: AuditReport) -> list[dict]:
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream)
            fields = set(reader.fieldnames or [])
            required = {"solution_file", "physically_feasible", "validation_note"}
            missing = sorted(required - fields)
            if missing:
                report.issues.append(
                    f"Analysis CSV {path} is missing columns: {', '.join(missing)}"
                )
            return [dict(row) for row in reader]
    except (OSError, csv.Error) as exc:
        report.issues.append(f"Cannot read analysis CSV {path}: {exc}")
        return []


def _validate_analysis(
    analysis_dir: Path,
    incumbent_solutions: set[str],
    report: AuditReport,
) -> None:
    analysis_dir = analysis_dir.resolve()
    json_path = analysis_dir / "cie_manufacturing_metrics.json"
    csv_path = analysis_dir / "cie_manufacturing_metrics.csv"
    markdown_path = analysis_dir / "cie_manufacturing_metrics.md"
    for path in (json_path, csv_path, markdown_path):
        if not path.is_file():
            report.issues.append(
                f"Required feasibility-analysis artifact is missing: {path}. "
                "Generate it with analyze_cie_solutions.py --validate --fail_on_invalid."
            )
    if not json_path.is_file() or not csv_path.is_file():
        return
    try:
        payload = json.loads(json_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        report.issues.append(f"Cannot read analysis JSON {json_path}: {exc}")
        return
    if not isinstance(payload, dict):
        report.issues.append(f"Analysis JSON {json_path} is not an object")
        return
    invalid_count = payload.get("invalid_count")
    solution_count = payload.get("solution_count")
    rows = payload.get("rows")
    if not isinstance(invalid_count, int) or isinstance(invalid_count, bool):
        report.issues.append(f"Analysis JSON {json_path} has non-integer invalid_count")
    elif invalid_count != 0:
        report.issues.append(f"Analysis reports invalid_count={invalid_count}; expected 0")
    if not isinstance(solution_count, int) or isinstance(solution_count, bool):
        report.issues.append(f"Analysis JSON {json_path} has non-integer solution_count")
        solution_count = -1
    if not isinstance(rows, list):
        report.issues.append(f"Analysis JSON {json_path} has no rows list")
        rows = []
    if solution_count != len(rows):
        report.issues.append(
            f"Analysis solution_count={solution_count}, but JSON contains {len(rows)} rows"
        )
    if solution_count != len(incumbent_solutions):
        report.issues.append(
            f"Analysis solution_count={solution_count}, but raw campaign has "
            f"{len(incumbent_solutions)} unique incumbents"
        )
    source_benchmarks = payload.get("source_benchmarks")
    if not isinstance(source_benchmarks, list) or not source_benchmarks:
        report.issues.append(f"Analysis JSON {json_path} has no source_benchmarks")
    else:
        missing_sources = [
            item
            for item in source_benchmarks
            if not _resolve_artifact_path(item, analysis_dir).is_file()
        ]
        if missing_sources:
            report.issues.append(
                "Analysis references missing source benchmark artifacts: "
                + ", ".join(str(item) for item in missing_sources)
            )

    json_solutions: list[str] = []
    for index, row in enumerate(rows, start=1):
        location = f"{json_path}:rows[{index}]"
        if not isinstance(row, dict):
            report.issues.append(f"{location} is not an object")
            continue
        solution_text = str(row.get("solution_file") or "").strip()
        if not solution_text:
            report.issues.append(f"{location} has no solution_file")
        else:
            json_solutions.append(_path_identity(solution_text, (analysis_dir, PROJECT_ROOT)))
        try:
            feasible = _parse_bool(row.get("physically_feasible"), "physically_feasible")
        except ValueError as exc:
            report.issues.append(f"{location} {exc}")
            feasible = False
        if not feasible:
            report.issues.append(f"{location} is not physically feasible")
        note = str(row.get("validation_note") or "").strip()
        if not note or note.lower() == "not_checked":
            report.issues.append(
                f"{location} was not checked by SCIP; run analysis with --validate"
            )
    if len(json_solutions) != len(set(json_solutions)):
        report.issues.append("Analysis JSON contains duplicate solution_file entries")
    if set(json_solutions) != incumbent_solutions:
        missing = incumbent_solutions - set(json_solutions)
        extra = set(json_solutions) - incumbent_solutions
        report.issues.append(
            f"Analysis JSON solution coverage differs from raw incumbents: "
            f"missing={len(missing)}, extra={len(extra)}"
        )

    csv_rows = _read_analysis_csv(csv_path, report)
    if len(csv_rows) != len(incumbent_solutions):
        report.issues.append(
            f"Analysis CSV has {len(csv_rows)} rows; expected {len(incumbent_solutions)}"
        )
    csv_solutions: list[str] = []
    for line_number, row in enumerate(csv_rows, start=2):
        location = f"{csv_path}:{line_number}"
        solution_text = str(row.get("solution_file") or "").strip()
        if solution_text:
            csv_solutions.append(_path_identity(solution_text, (analysis_dir, PROJECT_ROOT)))
        try:
            feasible = _parse_bool(row.get("physically_feasible"), "physically_feasible")
        except ValueError as exc:
            report.issues.append(f"{location} {exc}")
            feasible = False
        if not feasible:
            report.issues.append(f"{location} is not physically feasible")
        note = str(row.get("validation_note") or "").strip()
        if not note or note.lower() == "not_checked":
            report.issues.append(f"{location} was not checked by SCIP")
    if len(csv_solutions) != len(set(csv_solutions)):
        report.issues.append("Analysis CSV contains duplicate solution_file entries")
    if set(csv_solutions) != incumbent_solutions:
        report.issues.append("Analysis CSV solution coverage differs from raw incumbents")


def audit_campaign(
    *,
    stage: str,
    input_dir: Path | str,
    analysis_dir: Path | str,
    manifest_path: Path | str = DEFAULT_MANIFEST,
    solver_seeds: Sequence[int] = DEFAULT_SOLVER_SEEDS,
    training_seeds: Sequence[int] = DEFAULT_TRAINING_SEEDS,
    spbs_warm_starts: str = "both",
) -> AuditReport:
    input_root = Path(input_dir).resolve()
    if not input_root.exists():
        raise AuditConfigurationError(f"Input path does not exist: {input_root}")
    expected = build_expected_matrix(
        stage,
        manifest_path=manifest_path,
        solver_seeds=solver_seeds,
        training_seeds=training_seeds,
        spbs_warm_starts=spbs_warm_starts,
    )
    report = AuditReport(stage=stage, expected_rows=len(expected))
    csv_rows = _read_csv_rows(input_root, report)
    jsonl_rows, checkpoints = _read_jsonl_rows(input_root, report)
    _validate_checkpoints(checkpoints, input_root, report)

    csv_by_key: dict[PrimaryKey, SourceRow] = {}
    for source_row in csv_rows:
        _validate_common_row(source_row, report)
        key = _primary_key(source_row, stage, report)
        if key is None:
            continue
        previous = csv_by_key.get(key)
        if previous is not None:
            report.issues.append(
                f"Duplicate raw CSV primary key at {previous.location()} and "
                f"{source_row.location()}: {key.display()}"
            )
        else:
            csv_by_key[key] = source_row
        expected_run = expected.get(key)
        if expected_run is not None:
            _validate_expected_identity(source_row, expected_run, input_root, report)

    jsonl_by_key: dict[PrimaryKey, SourceRow] = {}
    for source_row in jsonl_rows:
        _validate_common_row(source_row, report)
        key = _primary_key(source_row, stage, report)
        if key is None:
            continue
        previous = jsonl_by_key.get(key)
        if previous is not None:
            report.issues.append(
                f"Duplicate JSONL primary key at {previous.location()} and "
                f"{source_row.location()}: {key.display()}"
            )
        else:
            jsonl_by_key[key] = source_row
        expected_run = expected.get(key)
        if expected_run is not None:
            _validate_expected_identity(source_row, expected_run, input_root, report)

    if report.csv_rows != len(expected):
        report.issues.append(
            f"Raw CSV row count is {report.csv_rows}; exact expected count is {len(expected)}"
        )
    missing = set(expected) - set(csv_by_key)
    unexpected = set(csv_by_key) - set(expected)
    if missing:
        report.issues.append(
            f"Raw CSV is missing {len(missing)} expected primary keys: {_format_examples(missing)}"
        )
    if unexpected:
        report.issues.append(
            f"Raw CSV contains {len(unexpected)} unexpected primary keys: "
            f"{_format_examples(unexpected)}"
        )

    checkpoint_only = set(jsonl_by_key) - set(csv_by_key)
    checkpoint_unexpected = set(jsonl_by_key) - set(expected)
    if checkpoint_only:
        report.issues.append(
            f"JSONL contains {len(checkpoint_only)} checkpoint-only rows with no final raw CSV: "
            f"{_format_examples(checkpoint_only)}"
        )
    if checkpoint_unexpected:
        report.issues.append(
            f"JSONL contains {len(checkpoint_unexpected)} rows outside the expected matrix: "
            f"{_format_examples(checkpoint_unexpected)}"
        )

    for key in set(csv_by_key) & set(jsonl_by_key):
        csv_row = csv_by_key[key].row
        jsonl_row = jsonl_by_key[key].row
        for field_name in (
            "error",
            "has_incumbent",
            "solution_file",
            "solution_write_error",
            "status",
        ):
            if _canonical_conflict_value(
                field_name, csv_row.get(field_name)
            ) != _canonical_conflict_value(field_name, jsonl_row.get(field_name)):
                report.issues.append(
                    f"CSV/JSONL conflict for {key.display()} field {field_name}: "
                    f"{csv_by_key[key].location()} != {jsonl_by_key[key].location()}"
                )

    incumbent_solutions = _validate_solutions(csv_by_key, input_root, report)
    _validate_analysis(Path(analysis_dir), incumbent_solutions, report)
    return report


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", required=True, choices=STAGES)
    parser.add_argument(
        "--input-dir",
        required=True,
        help="Campaign directory recursively containing final raw CSV and JSONL checkpoints.",
    )
    parser.add_argument(
        "--analysis-dir",
        required=True,
        help=(
            "Directory containing cie_manufacturing_metrics.json/csv/md generated "
            "by analyze_cie_solutions.py --validate --fail_on_invalid."
        ),
    )
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    parser.add_argument(
        "--solver-seeds",
        default=",".join(str(item) for item in DEFAULT_SOLVER_SEEDS),
        help="Exact comma-separated solver seed set expected in this campaign.",
    )
    parser.add_argument(
        "--training-seeds",
        default=",".join(str(item) for item in DEFAULT_TRAINING_SEEDS),
        help="Exact training seed set for main, stability, and OOD campaigns.",
    )
    parser.add_argument(
        "--spbs-warm-starts",
        choices=("both", "none", "auto"),
        default="both",
    )
    parser.add_argument(
        "--json-report",
        help="Optional path to write the machine-readable audit result.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        solver_seeds = parse_seed_list(args.solver_seeds, "solver seeds")
        training_seeds = parse_seed_list(args.training_seeds, "training seeds")
        report = audit_campaign(
            stage=args.stage,
            input_dir=args.input_dir,
            analysis_dir=args.analysis_dir,
            manifest_path=args.manifest,
            solver_seeds=solver_seeds,
            training_seeds=training_seeds,
            spbs_warm_starts=args.spbs_warm_starts,
        )
    except AuditConfigurationError as exc:
        print(f"AUDIT CONFIGURATION ERROR: {exc}", file=sys.stderr)
        return 2
    if args.json_report:
        report_path = Path(args.json_report).resolve()
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            json.dumps(report.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    status = "PASS" if report.ok else "FAIL"
    print(
        f"C&IE SUBMISSION AUDIT {status}: stage={report.stage}, "
        f"expected={report.expected_rows}, csv={report.csv_rows}, "
        f"jsonl={report.jsonl_rows}, incumbents={report.incumbent_rows}"
    )
    for issue in report.issues:
        print(f"ERROR: {issue}", file=sys.stderr)
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

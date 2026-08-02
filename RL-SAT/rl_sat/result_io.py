"""Result serialisation helpers for the RL-SAT solver.

This module intentionally has no dependency on SCIP, OR-Tools, matplotlib, or
the concrete dataclass implementation in :mod:`rl_sat.domain`.  Keeping the
output boundary structural makes it possible to inspect an interrupted run and
to render a schedule from a saved JSON file without importing the solver.
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import asdict, fields, is_dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Optional, Tuple


SCHEMA_NAME = "rl-sat-result"
SCHEMA_VERSION = 1

# Stable stage identifiers used by the original Petri-net Gantt tooling.
CANONICAL_PRODUCT_STAGES: Tuple[str, ...] = (
    "atr_lp_al",
    "al",
    "atr_al_exchange",
    "atr_al_llupper",
    "llupper",
    "vtr_load",
    "pm",
    "vtr_unload",
    "lllower",
    "atr_lllower_lp",
)


def _member(value: Any, *names: str, default: Any = None) -> Any:
    """Read the first present mapping key or object attribute."""

    if isinstance(value, Mapping):
        for name in names:
            if name in value:
                return value[name]
    else:
        for name in names:
            if hasattr(value, name):
                return getattr(value, name)
    return default


def _plain(value: Any) -> Any:
    """Convert common Python/scientific values into strict JSON values."""

    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, Enum):
        return _plain(value.value)
    if isinstance(value, Path):
        return str(value)
    if is_dataclass(value):
        return {field.name: _plain(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_plain(item) for item in value]

    # numpy scalars and similar scalar wrappers expose ``item``.  Importing
    # numpy here would unnecessarily make result inspection depend on it.
    item_method = getattr(value, "item", None)
    if callable(item_method):
        try:
            return _plain(item_method())
        except (TypeError, ValueError):
            pass
    if hasattr(value, "__dict__"):
        return {
            str(key): _plain(item)
            for key, item in vars(value).items()
            if not str(key).startswith("_")
        }
    return str(value)


def _number(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if math.isfinite(number) else default


def _identifier(value: Any, fallback: str) -> str:
    text = str(value if value is not None else fallback).strip()
    text = re.sub(r"[^0-9A-Za-z_]+", "_", text).strip("_")
    return text or fallback


def normalise_task(task: Any, ordinal: int = 0) -> Dict[str, Any]:
    """Return one task using the stable, renderer-facing task schema.

    The solver is free to use ``start_time``/``finish_time`` or
    ``machine``/``operation`` internally; these aliases are deliberately
    accepted at the persistence boundary.
    """

    start = _number(_member(task, "start", "start_time", "begin", default=0.0))
    raw_end = _member(task, "end", "end_time", "finish", "finish_time")
    duration = _number(_member(task, "duration", "processing_time", default=0.0))
    end = start + duration if raw_end is None else _number(raw_end, start + duration)
    if end < start:
        start, end = end, start

    stage = _member(task, "stage", "operation", "operation_type", "task_type", "name")
    resource = _member(
        task,
        "resource",
        "resource_id",
        "machine",
        "machine_id",
        default="unassigned",
    )
    wafer = _member(task, "wafer", "wafer_id", "product", "job", "job_id")
    task_id = _member(task, "id", "task_id", "uid", default=f"task_{ordinal:04d}")
    metadata = _plain(_member(task, "metadata", "meta", default={}))
    if not isinstance(metadata, Mapping):
        metadata = {"value": metadata}

    known_names = {
        "id",
        "task_id",
        "uid",
        "start",
        "start_time",
        "begin",
        "end",
        "end_time",
        "finish",
        "finish_time",
        "duration",
        "processing_time",
        "stage",
        "operation",
        "operation_type",
        "task_type",
        "name",
        "resource",
        "resource_id",
        "machine",
        "machine_id",
        "wafer",
        "wafer_id",
        "product",
        "job",
        "job_id",
        "metadata",
        "meta",
    }
    plain_task = _plain(task)
    if isinstance(plain_task, Mapping):
        extras = {key: value for key, value in plain_task.items() if key not in known_names}
        if extras:
            metadata = {**extras, **dict(metadata)}

    return {
        "id": str(task_id),
        "wafer": None if wafer is None else _plain(wafer),
        "stage": str(stage if stage is not None else "unspecified"),
        "resource": str(resource),
        "start": start,
        "end": end,
        "duration": end - start,
        "metadata": dict(metadata),
    }


def normalise_tasks(tasks: Optional[Iterable[Any]]) -> List[Dict[str, Any]]:
    result = [normalise_task(task, ordinal) for ordinal, task in enumerate(tasks or ())]
    return sorted(
        result,
        key=lambda task: (
            task["start"],
            task["end"],
            str(task["resource"]),
            str(task["wafer"]),
            task["stage"],
            task["id"],
        ),
    )


def build_petri_gantt_compat(
    tasks: Iterable[Any],
    cmax: Optional[float] = None,
    base_solution: Optional[Mapping[str, Any]] = None,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Build ``record`` and variable-value maps understood by Petri Gantts.

    ``solution`` always contains ``c_max`` and, for product stages,
    ``prod_stage_start_<wafer>_<stage>`` /
    ``prod_stage_end_<wafer>_<stage>``.  When multiple physical tasks represent
    the same logical product stage, their envelope is used.  This preserves the
    old variable-name contract while retaining every physical task in
    ``record["tasks"]``.
    """

    task_rows = normalise_tasks(tasks)
    observed_cmax = max((task["end"] for task in task_rows), default=0.0)
    final_cmax = max(observed_cmax, _number(cmax, observed_cmax))

    solution: Dict[str, Any] = {}
    if base_solution:
        solution.update({str(key): _plain(value) for key, value in base_solution.items()})
    solution["c_max"] = final_cmax

    product_rows: List[Dict[str, Any]] = []
    resource_rows: List[Dict[str, Any]] = []
    envelopes: Dict[Tuple[str, str], Tuple[float, float]] = {}

    for ordinal, task in enumerate(task_rows):
        stage_id = _identifier(task["stage"], "unspecified")
        resource_id = _identifier(task["resource"], "unassigned")
        task_id = _identifier(task["id"], f"task_{ordinal:04d}")

        start_var = f"resource_task_start_{task_id}"
        end_var = f"resource_task_end_{task_id}"
        solution[start_var] = task["start"]
        solution[end_var] = task["end"]
        resource_rows.append(
            {
                "task_id": task["id"],
                "resource": task["resource"],
                "wafer": task["wafer"],
                "stage": task["stage"],
                "start_var": start_var,
                "end_var": end_var,
            }
        )

        wafer_values: List[Any] = []
        if task["wafer"] is not None:
            wafer_values.append(task["wafer"])
        metadata_wafers = task.get("metadata", {}).get("wafer_ids", [])
        if isinstance(metadata_wafers, (list, tuple, set)):
            wafer_values.extend(metadata_wafers)
        for wafer_value in dict.fromkeys(wafer_values):
            wafer_id = _identifier(wafer_value, "na")
            key = (wafer_id, stage_id)
            previous = envelopes.get(key)
            if previous is None:
                envelopes[key] = (task["start"], task["end"])
            else:
                envelopes[key] = (
                    min(previous[0], task["start"]),
                    max(previous[1], task["end"]),
                )

    for (wafer_id, stage_id), (start, end) in sorted(envelopes.items()):
        start_var = f"prod_stage_start_{wafer_id}_{stage_id}"
        end_var = f"prod_stage_end_{wafer_id}_{stage_id}"
        solution[start_var] = start
        solution[end_var] = end
        product_rows.append(
            {
                "wafer": wafer_id,
                "stage": stage_id,
                "start_var": start_var,
                "end_var": end_var,
            }
        )

    record = {
        "format": "petri_gantt_variable_map_v1",
        "cmax_var": "c_max",
        "canonical_product_stages": list(CANONICAL_PRODUCT_STAGES),
        "product_stages": product_rows,
        "resource_tasks": resource_rows,
        "tasks": task_rows,
    }
    return record, solution


def result_to_dict(result: Any) -> Dict[str, Any]:
    """Convert a ``ScheduleResult``-like value to the stable JSON schema."""

    tasks = normalise_tasks(_member(result, "tasks", "schedule", "operations", default=[]))
    observed_cmax = max((task["end"] for task in tasks), default=0.0)
    primary_cmax = _number(
        _member(
            result,
            "primary_cmax",
            "objective_cmax",
            "cmax",
            "makespan",
            default=observed_cmax,
        ),
        observed_cmax,
    )
    primary_cmax = max(primary_cmax, observed_cmax)
    best_obj = _plain(
        _member(
            result,
            "best_obj",
            "objective_cmax",
            "objective",
            "objective_value",
            default=primary_cmax,
        )
    )
    metadata = _plain(_member(result, "metadata", "meta", "statistics", default={}))
    if not isinstance(metadata, Mapping):
        metadata = {"value": metadata}
    base_solution = _member(result, "solution", "values", default=None)
    if not isinstance(base_solution, Mapping):
        candidate = metadata.get("legacy_solution", {})
        base_solution = candidate if isinstance(candidate, Mapping) else {}
    record, solution = build_petri_gantt_compat(tasks, primary_cmax, base_solution)
    primary_status = _member(result, 'primary_status')
    if primary_status is None:
        primary_status = metadata.get(
            'primary_status',
            _member(result, 'status', 'solve_status', default='UNKNOWN'),
        )
    stability_status = _member(result, 'stability_status')
    if stability_status is None:
        stability_status = metadata.get('secondary_status')
    if stability_status is None:
        stability_status = 'not_run'
    nonzero_solution_vars = sum(
        abs(_number(value, 0.0)) > 1e-12 for value in solution.values()
    )

    instance = _member(result, "instance", "instance_name", "name")
    if instance is None:
        instance = metadata.get("instance", metadata.get("run_name", "unknown"))
    payload = {
        "schema": SCHEMA_NAME,
        "schema_version": SCHEMA_VERSION,
        "instance": str(instance),
        "method": str(_member(result, "method", default="RL-SAT")),
        "status": str(_member(result, "status", "solve_status", default="UNKNOWN")),
        "solving_time": _number(
            _member(
                result,
                "solving_time",
                "wall_time",
                "solve_time",
                "runtime",
                "elapsed",
                default=0.0,
            )
        ),
        "best_obj": best_obj,
        "primary_cmax": primary_cmax,
        "best_bound": _plain(_member(result, "best_bound")),
        "primal_dual_gap": _plain(
            _member(result, "relative_gap", "primal_dual_gap")
        ),
        "primaldualintegral": None,
        "ntotal_nodes": None,
        "schedule_stability": _plain(_member(result, "schedule_stability")),
        "solver": str(_member(result, "solver", default="OR-Tools CP-SAT")),
        "scip_used": bool(_member(result, "scip_used", default=False)),
        "certificate_scope": str(
            _member(result, "certificate_scope", default="canonical_project_model")
        ),
        "solution": solution,
        "tasks": tasks,
        "metadata": dict(metadata),
        "record": record,
    }
    payload.update(
        {
            'primary_status': str(primary_status),
            'stability_status': str(stability_status),
            'nonzero_solution_vars': nonzero_solution_vars,
        }
    )
    return _plain(payload)


def write_result_json(result: Any, path: Any, *, indent: int = 2) -> Path:
    """Atomically write a result JSON file and return its resolved path."""

    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + ".tmp")
    text = json.dumps(
        result_to_dict(result),
        ensure_ascii=False,
        indent=indent,
        sort_keys=False,
        allow_nan=False,
    )
    temporary.write_text(text + "\n", encoding="utf-8")
    temporary.replace(destination)
    return destination.resolve()


def read_result_json(path: Any) -> Dict[str, Any]:
    """Load and lightly validate a previously written result."""

    source = Path(path)
    payload = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(payload, MutableMapping):
        raise ValueError(f"Result root must be an object: {source}")
    required = {
        "instance",
        "status",
        "solving_time",
        "best_obj",
        "primary_cmax",
        "solution",
        "tasks",
        "metadata",
    }
    missing = sorted(required.difference(payload))
    if missing:
        raise ValueError(f"Result is missing required fields: {', '.join(missing)}")
    payload["tasks"] = normalise_tasks(payload.get("tasks", []))
    if "record" not in payload:
        record, solution = build_petri_gantt_compat(
            payload["tasks"],
            payload.get("primary_cmax"),
            payload.get("solution"),
        )
        payload["record"] = record
        payload["solution"] = solution
    return dict(payload)


# Short aliases used by CLI code and convenient for external experiment scripts.
save_result = write_result_json
load_result = read_result_json


__all__ = [
    "CANONICAL_PRODUCT_STAGES",
    "SCHEMA_NAME",
    "SCHEMA_VERSION",
    "build_petri_gantt_compat",
    "load_result",
    "normalise_task",
    "normalise_tasks",
    "read_result_json",
    "result_to_dict",
    "save_result",
    "write_result_json",
]

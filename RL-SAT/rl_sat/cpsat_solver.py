"""Detailed, SCIP-independent CP-SAT scheduler for the cluster tool.

The project canonical mapping fixes every scheduling unit to its physical
chamber and position.  A reinforcement-learning ``dispatch_order`` is used
only as a CP-SAT value/search hint, never as a precedence constraint.
Consequently that hint cannot add or remove a feasible schedule.

The model represents:

* the complete product route LP -> ATR -> AL -> LLupper -> VTR -> CH ->
  VTR -> LLlower -> ATR -> LP;
* the four-action 4x1 load/process/unload sequence and chamber rotation;
* the atomic 2x2 head/bridge/tail sequence in which ``k`` product pairs use
  ``k + 1`` exposures;
* cleaning epochs, chamber occupancy, both robots, AL, the two slots of each
  load lock, and chamber-bound PEC-token capacity.

No legacy optimizer-backed model module is imported here; this scheduler has
only the OR-Tools runtime path.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

try:
    import ortools
    from ortools.sat.python import cp_model
except ImportError as exc:  # pragma: no cover - exercised only without dependency
    ortools = None
    cp_model = None
    _ORTOOLS_IMPORT_ERROR: Optional[BaseException] = exc
else:
    _ORTOOLS_IMPORT_ERROR = None

from .config import CPSATConfig, FULL_MODE, MIX_MODE, estimate_horizon, to_ticks
from .domain import Plan, Problem, ScheduleResult, ScheduleTask, WaferPair


@dataclass
class _DisplayTask:
    task_id: str
    name: str
    resource: str
    start: Any
    end: Any
    stage: str
    mode: str = ""
    chamber: Optional[int] = None
    pair_id: Optional[str] = None
    wafer_ids: Tuple[int, ...] = ()
    task_type: str = "operation"
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class _IntervalTask:
    task_id: str
    start: Any
    end: Any
    interval: Any
    source: str = ""
    destination: str = ""


@dataclass
class _PairState:
    pair: WaferPair
    atr_service: _IntervalTask
    atr_return: _IntervalTask
    llupper_ready: Any
    vtr_load_start: Any
    vtr_load_end: Any
    pm_start: Any
    pm_end: Any
    vtr_unload_start: Any
    vtr_unload_end: Any
    completion: Any
    release_wait: Any
    llupper_wait: Any
    pre_process_wait: Any
    post_process_wait: Any
    lllower_wait: Any


@dataclass
class _SolveSnapshot:
    status: str
    values: Dict[Any, int]
    cmax: int
    stability: int
    primary_bound: float
    solver_wall_time: float
    response_stats: str
    conflicts: int
    branches: int


class _ModelBuilder:
    """Build one fixed-chamber-assignment scheduling model."""

    def __init__(self, problem: Problem, plan: Plan, config: CPSATConfig):
        if cp_model is None:
            raise RuntimeError(
                "OR-Tools is required by RL-SAT. Install the 'ortools' package."
            ) from _ORTOOLS_IMPORT_ERROR
        plan.validate(problem)
        self.problem = problem
        self.input_plan = plan.clone()
        self.config = config
        self.tool = problem.tool
        self.scale = config.time_scale
        self.horizon = self._safe_horizon()
        self.model = cp_model.CpModel()
        self.display_tasks: List[_DisplayTask] = []
        self.resources: Dict[str, List[Any]] = {
            "ATR": [],
            "AL": [],
            "VTR": [],
            "CH2": [],
            "CH3": [],
            "LLupper-1": [],
            "LLupper-2": [],
            "LLlower-1": [],
            "LLlower-2": [],
        }
        self.atr_tasks: List[_IntervalTask] = []
        self.vtr_tasks: List[_IntervalTask] = []
        self.pec_intervals: Dict[int, List[Any]] = {2: [], 3: []}
        self.pec_demands: Dict[int, List[int]] = {2: [], 3: []}
        self.all_vars: List[Any] = []
        self.assignment_vars: Dict[Tuple[int, str, str, int], Any] = {}
        self.legacy_bindings: Dict[str, Any] = {}
        self.mix_cycle_counts: Dict[int, int] = {2: 0, 3: 0}
        self.full_positions: Dict[int, List[Dict[str, Any]]] = {2: [], 3: []}
        self.mix_positions: Dict[int, List[Dict[str, Any]]] = {2: [], 3: []}
        self.pairs: Dict[str, _PairState] = {}
        self.wait_vars: List[Any] = []
        self.cmax: Any = None
        self.stability: Any = None
        self._build()

    def ticks(self, value: float) -> int:
        return to_ticks(
            value,
            self.scale,
            exact=self.config.require_exact_scaling,
        )

    def _safe_horizon(self) -> int:
        base = estimate_horizon(self.tool, self.scale)
        pair_count = len(self.problem.pairs)
        route = (
            self.tool.atr_lp_al_total_time
            + 2.0 * self.tool.aligner_time
            + self.tool.al_exchange_time
            + self.tool.atr_al_llupper_total_time
            + self.tool.llupper_time
            + 2.0 * self.tool.pair_transfer_time
            + 2.0
            * max(self.tool.full_process_time, self.tool.mix_process_time)
            + self.tool.lllower_time
            + self.tool.atr_lllower_lp_total_time
        )
        # A deliberately loose serial upper bound avoids making the configured
        # horizon an accidental feasibility restriction.
        serial_seconds = max(100.0, (pair_count + 2) * route * 4.0)
        return max(
            base,
            to_ticks(serial_seconds, self.scale, exact=False),
        )

    def _var(self, name: str, lower: int = 0, upper: Optional[int] = None):
        var = self.model.new_int_var(
            lower,
            self.horizon if upper is None else upper,
            name,
        )
        self.all_vars.append(var)
        return var

    def _bool(self, name: str):
        var = self.model.new_bool_var(name)
        self.all_vars.append(var)
        return var

    def _fixed_interval(
        self,
        task_id: str,
        duration: float | int,
        resource: Optional[str],
        *,
        duration_is_ticks: bool = False,
        source: str = "",
        destination: str = "",
    ) -> _IntervalTask:
        ticks = int(duration) if duration_is_ticks else self.ticks(float(duration))
        start = self._var(f"{task_id}_start")
        end = self._var(f"{task_id}_end")
        interval = self.model.new_interval_var(start, ticks, end, task_id)
        task = _IntervalTask(task_id, start, end, interval, source, destination)
        if resource:
            self.resources.setdefault(resource, []).append(interval)
        return task

    def _span_interval(
        self,
        task_id: str,
        start: Any,
        end: Any,
        resource: Optional[str],
    ) -> _IntervalTask:
        size = self._var(f"{task_id}_size")
        self.model.add(size == end - start)
        interval = self.model.new_interval_var(start, size, end, task_id)
        task = _IntervalTask(task_id, start, end, interval)
        if resource:
            self.resources.setdefault(resource, []).append(interval)
        return task

    def _optional_span(
        self,
        task_id: str,
        start: Any,
        end: Any,
        presence: Any,
    ):
        size = self._var(f"{task_id}_size")
        self.model.add(size == end - start).only_enforce_if(presence)
        self.model.add(size == 0).only_enforce_if(presence.Not())
        return self.model.new_optional_interval_var(
            start, size, end, presence, task_id
        )

    def _display(
        self,
        task_id: str,
        name: str,
        resource: str,
        start: Any,
        end: Any,
        stage: str,
        *,
        mode: str = "",
        chamber: Optional[int] = None,
        pair_id: Optional[str] = None,
        wafer_ids: Sequence[int] = (),
        task_type: str = "operation",
        metadata: Optional[Mapping[str, Any]] = None,
    ) -> None:
        self.display_tasks.append(
            _DisplayTask(
                task_id=task_id,
                name=name,
                resource=resource,
                start=start,
                end=end,
                stage=stage,
                mode=mode,
                chamber=chamber,
                pair_id=pair_id,
                wafer_ids=tuple(wafer_ids),
                task_type=task_type,
                metadata=dict(metadata or {}),
            )
        )

    def _bind_legacy_interval(
        self, prefix: str, task: _IntervalTask
    ) -> None:
        parts = prefix.split("_")
        split_at = len(parts)
        while split_at and parts[split_at - 1].isdigit():
            split_at -= 1
        stem = "_".join(parts[:split_at])
        indices = "_".join(parts[split_at:])
        separator = "_" if indices else ""
        self.legacy_bindings[
            f"{stem}_start{separator}{indices}"
        ] = task.start
        self.legacy_bindings[
            f"{stem}_end{separator}{indices}"
        ] = task.end

    def _bind_legacy_active(self, name: str) -> None:
        active = self._bool(name)
        self.model.add(active == 1)
        self.legacy_bindings[name] = active

    def _derived_fixed_task(
        self,
        task_id: str,
        duration: float,
        start_equals: Any,
        *,
        resource: Optional[str] = None,
    ) -> _IntervalTask:
        task = self._fixed_interval(task_id, duration, resource)
        self.model.add(task.start == start_equals)
        return task

    def _build_pair_front_routes(self) -> None:
        tool = self.tool
        for pair_id in sorted(
            self.problem.pairs,
            key=lambda key: (
                self.problem.pairs[key].mode,
                self.problem.pairs[key].mode_index,
            ),
        ):
            pair = self.problem.pairs[pair_id]
            in_ticks = self.ticks(tool.atr_lp_al_total_time)
            out_ticks = self.ticks(tool.atr_al_llupper_total_time)
            align_ticks = self.ticks(tool.aligner_time)
            exchange_ticks = self.ticks(tool.al_exchange_time)
            service_ticks = (
                in_ticks
                + pair.product_load * align_ticks
                + (exchange_ticks if pair.product_load == 2 else 0)
                + out_ticks
            )
            service = self._fixed_interval(
                f"pair_{pair_id}_atr_front_service",
                service_ticks,
                "ATR",
                duration_is_ticks=True,
                source="LP",
                destination="LLupper",
            )
            self.atr_tasks.append(service)

            atr_in = self._derived_fixed_task(
                f"pair_{pair_id}_atr_lp_al",
                tool.atr_lp_al_total_time,
                service.start,
            )
            self._display(
                atr_in.task_id,
                f"{pair_id} LP→AL",
                "ATR",
                atr_in.start,
                atr_in.end,
                "atr_lp_al",
                mode=pair.mode,
                pair_id=pair_id,
                wafer_ids=pair.wafer_ids,
                task_type="product_stage",
            )

            cursor = atr_in.end
            for member_index, wafer_id in enumerate(pair.wafer_ids):
                if member_index:
                    exchange = self._derived_fixed_task(
                        f"pair_{pair_id}_atr_al_exchange",
                        tool.al_exchange_time,
                        cursor,
                    )
                    self._display(
                        exchange.task_id,
                        f"{pair_id} AL exchange",
                        "ATR",
                        exchange.start,
                        exchange.end,
                        "atr_al_exchange",
                        mode=pair.mode,
                        pair_id=pair_id,
                        wafer_ids=pair.wafer_ids,
                        task_type="product_stage",
                    )
                    cursor = exchange.end
                alignment = self._derived_fixed_task(
                    f"wafer_{wafer_id}_al",
                    tool.aligner_time,
                    cursor,
                    resource="AL",
                )
                self._display(
                    alignment.task_id,
                    f"W{wafer_id} align",
                    "AL",
                    alignment.start,
                    alignment.end,
                    "al",
                    mode=pair.mode,
                    pair_id=pair_id,
                    wafer_ids=(wafer_id,),
                    task_type="product_stage",
                )
                cursor = alignment.end

            atr_to_ll = self._derived_fixed_task(
                f"pair_{pair_id}_atr_al_llupper",
                tool.atr_al_llupper_total_time,
                cursor,
            )
            self.model.add(atr_to_ll.end == service.end)
            self._display(
                atr_to_ll.task_id,
                f"{pair_id} AL→LLupper",
                "ATR",
                atr_to_ll.start,
                atr_to_ll.end,
                "atr_al_llupper",
                mode=pair.mode,
                pair_id=pair_id,
                wafer_ids=pair.wafer_ids,
                task_type="product_stage",
            )

            llupper_ready = self._var(f"pair_{pair_id}_llupper_ready")
            self.model.add(
                llupper_ready == service.end + self.ticks(tool.llupper_time)
            )
            self._display(
                f"pair_{pair_id}_llupper",
                f"{pair_id} LLupper pump",
                "LLupper",
                service.end,
                llupper_ready,
                "llupper",
                mode=pair.mode,
                pair_id=pair_id,
                wafer_ids=pair.wafer_ids,
                task_type="product_stage",
            )

            load_start = self._var(f"pair_{pair_id}_vtr_load_start")
            load_end = self._var(f"pair_{pair_id}_vtr_load_end")
            self.model.add(
                load_end == load_start + self.ticks(tool.pair_transfer_time)
            )
            pm_start = self._var(f"pair_{pair_id}_pm_start")
            pm_end = self._var(f"pair_{pair_id}_pm_end")
            unload_start = self._var(f"pair_{pair_id}_vtr_unload_start")
            unload_end = self._var(f"pair_{pair_id}_vtr_unload_end")
            self.model.add(
                unload_end == unload_start + self.ticks(tool.pair_transfer_time)
            )

            atr_return = self._fixed_interval(
                f"pair_{pair_id}_atr_lllower_lp",
                tool.atr_lllower_lp_total_time,
                "ATR",
                source="LLlower",
                destination="LP",
            )
            self.atr_tasks.append(atr_return)
            completion = atr_return.end

            release_wait = self._var(f"pair_{pair_id}_release_wait")
            llupper_wait = self._var(f"pair_{pair_id}_llupper_wait")
            pre_process_wait = self._var(f"pair_{pair_id}_pre_process_wait")
            post_wait = self._var(f"pair_{pair_id}_post_process_wait")
            lllower_wait = self._var(f"pair_{pair_id}_lllower_wait")
            self.model.add(release_wait == service.start)
            self.model.add(llupper_wait == load_start - llupper_ready)
            self.model.add(pre_process_wait == pm_start - load_end)
            self.model.add(post_wait == unload_start - pm_end)
            lllower_ready_expr = unload_end + self.ticks(tool.lllower_time)
            self.model.add(lllower_wait == atr_return.start - lllower_ready_expr)
            self.model.add(load_start >= llupper_ready)
            self.model.add(pm_start >= load_end)
            self.model.add(unload_start >= pm_end)
            self.model.add(atr_return.start >= lllower_ready_expr)

            max_module = self.ticks(tool.max_module_residency_time)
            self.model.add(unload_end - load_start <= max_module)
            self.model.add(load_start - service.end <= max_module)
            self.model.add(atr_return.start - unload_end <= max_module)
            if tool.max_schedule_wait_time > 0:
                max_wait = self.ticks(tool.max_schedule_wait_time)
                self.model.add(llupper_wait <= max_wait)
                self.model.add(pre_process_wait <= max_wait)
                self.model.add(post_wait <= max_wait)
                self.model.add(lllower_wait <= max_wait)
            self.wait_vars.extend(
                [
                    release_wait,
                    llupper_wait,
                    pre_process_wait,
                    post_wait,
                    lllower_wait,
                ]
            )

            self._display(
                f"pair_{pair_id}_vtr_load",
                f"{pair_id} VTR load",
                "VTR",
                load_start,
                load_end,
                "vtr_load",
                mode=pair.mode,
                pair_id=pair_id,
                wafer_ids=pair.wafer_ids,
                task_type="product_stage",
            )
            self._display(
                f"pair_{pair_id}_pm",
                f"{pair_id} process",
                "CH",
                pm_start,
                pm_end,
                "pm",
                mode=pair.mode,
                pair_id=pair_id,
                wafer_ids=pair.wafer_ids,
                task_type="product_stage",
            )
            self._display(
                f"pair_{pair_id}_vtr_unload",
                f"{pair_id} VTR unload",
                "VTR",
                unload_start,
                unload_end,
                "vtr_unload",
                mode=pair.mode,
                pair_id=pair_id,
                wafer_ids=pair.wafer_ids,
                task_type="product_stage",
            )
            lllower_end = self._var(f"pair_{pair_id}_lllower_end")
            self.model.add(
                lllower_end == unload_end + self.ticks(tool.lllower_time)
            )
            self._display(
                f"pair_{pair_id}_lllower",
                f"{pair_id} LLlower vent",
                "LLlower",
                unload_end,
                lllower_end,
                "lllower",
                mode=pair.mode,
                pair_id=pair_id,
                wafer_ids=pair.wafer_ids,
                task_type="product_stage",
            )
            self._display(
                atr_return.task_id,
                f"{pair_id} LLlower→LP",
                "ATR",
                atr_return.start,
                atr_return.end,
                "atr_lllower_lp",
                mode=pair.mode,
                pair_id=pair_id,
                wafer_ids=pair.wafer_ids,
                task_type="product_stage",
            )

            self.pairs[pair_id] = _PairState(
                pair=pair,
                atr_service=service,
                atr_return=atr_return,
                llupper_ready=llupper_ready,
                vtr_load_start=load_start,
                vtr_load_end=load_end,
                pm_start=pm_start,
                pm_end=pm_end,
                vtr_unload_start=unload_start,
                vtr_unload_end=unload_end,
                completion=completion,
                release_wait=release_wait,
                llupper_wait=llupper_wait,
                pre_process_wait=pre_process_wait,
                post_process_wait=post_wait,
                lllower_wait=lllower_wait,
            )

    def _add_pec_use(
        self,
        chamber: int,
        task_id: str,
        start: Any,
        end: Any,
        demand: int,
        presence: Optional[Any] = None,
    ) -> None:
        if demand <= 0:
            return
        if presence is None:
            interval = self._span_interval(task_id, start, end, None).interval
        else:
            interval = self._optional_span(task_id, start, end, presence)
        self.pec_intervals[chamber].append(interval)
        self.pec_demands[chamber].append(int(demand))

    def _map_pair_to_actions(
        self,
        pair_id: str,
        load: _IntervalTask,
        pm_start: Any,
        pm_end: Any,
        unload: _IntervalTask,
        selector: Any,
    ) -> None:
        pair = self.pairs[pair_id]
        for left, right in (
            (pair.vtr_load_start, load.start),
            (pair.vtr_load_end, load.end),
            (pair.pm_start, pm_start),
            (pair.pm_end, pm_end),
            (pair.vtr_unload_start, unload.start),
            (pair.vtr_unload_end, unload.end),
        ):
            self.model.add(left == right).only_enforce_if(selector)

    def _equipment_task(
        self,
        task_id: str,
        duration: float,
        resource: str,
        stage: str,
        chamber: int,
        *,
        name: Optional[str] = None,
        mode: str = "",
        source: str = "",
        destination: str = "",
        metadata: Optional[Mapping[str, Any]] = None,
    ) -> _IntervalTask:
        # The enclosing CH window is the sole chamber occupancy interval.
        # Internal rotations/exposures are timing markers; adding both them
        # and their containing window to NoOverlap would create self-conflict.
        interval_resource = None if resource.startswith("CH") else resource
        task = self._fixed_interval(
            task_id,
            duration,
            interval_resource,
            source=source,
            destination=destination,
        )
        if interval_resource == "VTR":
            self.vtr_tasks.append(task)
        enriched_metadata = {
            "operation_kind": stage,
            "chamber": chamber,
            "source": source,
            "destination": destination,
            **dict(metadata or {}),
        }
        self._display(
            task_id,
            name or task_id,
            resource,
            task.start,
            task.end,
            stage,
            mode=mode,
            chamber=chamber,
            task_type="equipment_action",
            metadata=enriched_metadata,
        )
        return task

    def _build_cleaning(
        self,
        chamber: int,
        clean_index: int,
        previous_end: Optional[Any],
    ) -> Tuple[Any, Any]:
        prefix = f"ch{chamber}_clean_{clean_index}"
        front_load = self._equipment_task(
            f"{prefix}_front_load",
            self.tool.pair_transfer_time,
            "VTR",
            "clean_vtr_load",
            chamber,
            name=f"CH{chamber} clean front load",
            source="PEC_storage",
            destination=f"CH{chamber}",
        )
        rotate_in = self._equipment_task(
            f"{prefix}_rotate_in",
            self.tool.pm_rotation_time_180,
            f"CH{chamber}",
            "clean_rotation",
            chamber,
            name=f"CH{chamber} clean rotate",
        )
        back_load = self._equipment_task(
            f"{prefix}_back_load",
            self.tool.pair_transfer_time,
            "VTR",
            "clean_vtr_load",
            chamber,
            name=f"CH{chamber} clean back load",
            source="PEC_storage",
            destination=f"CH{chamber}",
        )
        process = self._equipment_task(
            f"{prefix}_process",
            self.tool.effective_cleaning_process_time,
            f"CH{chamber}",
            "cleaning",
            chamber,
            name=f"CH{chamber} clean",
        )
        back_unload = self._equipment_task(
            f"{prefix}_back_unload",
            self.tool.pair_transfer_time,
            "VTR",
            "clean_vtr_unload",
            chamber,
            name=f"CH{chamber} clean back unload",
            source=f"CH{chamber}",
            destination="PEC_storage",
        )
        rotate_out = self._equipment_task(
            f"{prefix}_rotate_out",
            self.tool.pm_rotation_time_180,
            f"CH{chamber}",
            "clean_rotation",
            chamber,
            name=f"CH{chamber} clean rotate",
        )
        front_unload = self._equipment_task(
            f"{prefix}_front_unload",
            self.tool.pair_transfer_time,
            "VTR",
            "clean_vtr_unload",
            chamber,
            name=f"CH{chamber} clean front unload",
            source=f"CH{chamber}",
            destination="PEC_storage",
        )
        if previous_end is not None:
            self.model.add(front_load.start >= previous_end)
        self.model.add(rotate_in.start == front_load.end)
        self.model.add(back_load.start >= rotate_in.end)
        self.model.add(process.start == back_load.end)
        self.model.add(back_unload.start >= process.end)
        self.model.add(rotate_out.start == back_unload.end)
        self.model.add(front_unload.start >= rotate_out.end)
        window = self._span_interval(
            f"{prefix}_window",
            front_load.start,
            front_unload.end,
            f"CH{chamber}",
        )
        self._bind_legacy_active(f"clean_active_{chamber}_{clean_index}")
        self._bind_legacy_interval(
            f"clean_front_load_{chamber}_{clean_index}", front_load
        )
        self._bind_legacy_interval(
            f"clean_back_load_{chamber}_{clean_index}", back_load
        )
        self._bind_legacy_interval(
            f"clean_{chamber}_{clean_index}", process
        )
        self._bind_legacy_interval(
            f"clean_back_unload_{chamber}_{clean_index}", back_unload
        )
        self._bind_legacy_interval(
            f"clean_front_unload_{chamber}_{clean_index}", front_unload
        )
        self._add_pec_use(
            chamber,
            f"{prefix}_pec",
            window.start,
            window.end,
            4,
        )
        return window.start, window.end

    def _build_full_position(
        self,
        chamber: int,
        position: int,
        previous_end: Optional[Any],
        full_units: Sequence[str],
    ) -> Dict[str, Any]:
        prefix = f"ch{chamber}_full_pos_{position + 1}"
        canonical_unit = self.problem.units[full_units[position]]
        back_is_product = len(canonical_unit.pair_ids) > 1
        front_load = self._equipment_task(
            f"{prefix}_front_load",
            self.tool.pair_transfer_time,
            "VTR",
            "full_vtr_load",
            chamber,
            name=f"CH{chamber} 4x1 front load",
            mode=FULL_MODE,
            source="LLupper",
            destination=f"CH{chamber}",
            metadata={"position": position + 1},
        )
        rotate_in = self._equipment_task(
            f"{prefix}_rotate_in",
            self.tool.pm_rotation_time_180,
            f"CH{chamber}",
            "full_rotation",
            chamber,
            name=f"CH{chamber} 4x1 rotate",
            mode=FULL_MODE,
        )
        back_load = self._equipment_task(
            f"{prefix}_back_load",
            self.tool.pair_transfer_time,
            "VTR",
            "full_vtr_load",
            chamber,
            name=f"CH{chamber} 4x1 back load",
            mode=FULL_MODE,
            source="LLupper" if back_is_product else "PEC_storage",
            destination=f"CH{chamber}",
        )
        process = self._equipment_task(
            f"{prefix}_process",
            self.tool.full_process_time,
            f"CH{chamber}",
            "full_process",
            chamber,
            name=f"CH{chamber} 4x1 process",
            mode=FULL_MODE,
        )
        back_unload = self._equipment_task(
            f"{prefix}_back_unload",
            self.tool.pair_transfer_time,
            "VTR",
            "full_vtr_unload",
            chamber,
            name=f"CH{chamber} 4x1 back unload",
            mode=FULL_MODE,
            source=f"CH{chamber}",
            destination="LLlower" if back_is_product else "PEC_storage",
        )
        rotate_out = self._equipment_task(
            f"{prefix}_rotate_out",
            self.tool.pm_rotation_time_180,
            f"CH{chamber}",
            "full_rotation",
            chamber,
            name=f"CH{chamber} 4x1 rotate",
            mode=FULL_MODE,
        )
        front_unload = self._equipment_task(
            f"{prefix}_front_unload",
            self.tool.pair_transfer_time,
            "VTR",
            "full_vtr_unload",
            chamber,
            name=f"CH{chamber} 4x1 front unload",
            mode=FULL_MODE,
            source=f"CH{chamber}",
            destination="LLlower",
        )
        if previous_end is not None:
            self.model.add(front_load.start >= previous_end)
        self.model.add(rotate_in.start == front_load.end)
        self.model.add(back_load.start >= rotate_in.end)
        self.model.add(process.start == back_load.end)
        self.model.add(back_unload.start >= process.end)
        self.model.add(rotate_out.start == back_unload.end)
        self.model.add(front_unload.start >= rotate_out.end)
        window = self._span_interval(
            f"{prefix}_window",
            front_load.start,
            front_unload.end,
            f"CH{chamber}",
        )
        batch = position + 1
        self._bind_legacy_active(f"full_batch_used_{chamber}_{batch}")
        self._bind_legacy_interval(
            f"full_front_load_{chamber}_{batch}", front_load
        )
        self._bind_legacy_interval(
            f"full_back_load_{chamber}_{batch}", back_load
        )
        self._bind_legacy_interval(f"full_{chamber}_{batch}", process)
        self._bind_legacy_interval(
            f"full_back_unload_{chamber}_{batch}", back_unload
        )
        self._bind_legacy_interval(
            f"full_front_unload_{chamber}_{batch}", front_unload
        )

        selectors: Dict[str, Any] = {}
        for unit_id in full_units:
            selector = self._bool(
                f"assign_ch{chamber}_{unit_id}_full_pos_{position + 1}"
            )
            self.assignment_vars[(chamber, FULL_MODE, unit_id, position)] = selector
            selectors[unit_id] = selector
            unit = self.problem.units[unit_id]
            first_pair = unit.pair_ids[0]
            self._map_pair_to_actions(
                first_pair,
                front_load,
                process.start,
                process.end,
                front_unload,
                selector,
            )
            if len(unit.pair_ids) > 1:
                self._map_pair_to_actions(
                    unit.pair_ids[1],
                    back_load,
                    process.start,
                    process.end,
                    back_unload,
                    selector,
                )
            self._add_pec_use(
                chamber,
                f"{prefix}_{unit_id}_pec",
                window.start,
                window.end,
                unit.pec_fill,
                selector,
            )
        self.model.add_exactly_one(list(selectors.values()))
        return {
            "position": position,
            "selectors": selectors,
            "start": window.start,
            "end": window.end,
        }

    def _build_mix_segment(
        self,
        chamber: int,
        segment_index: int,
        global_offset: int,
        pair_count: int,
        previous_end: Optional[Any],
        mix_units: Sequence[str],
    ) -> Tuple[Any, List[Dict[str, Any]]]:
        prefix = f"ch{chamber}_mix_seg_{segment_index}"
        head = self._equipment_task(
            f"{prefix}_head",
            self.tool.pair_transfer_time,
            "VTR",
            "mix_head",
            chamber,
            name=f"CH{chamber} 2x2 PEC/PW head",
            mode=MIX_MODE,
            source="LLupper",
            destination=f"CH{chamber}",
            metadata={"segment": segment_index},
        )
        if previous_end is not None:
            self.model.add(head.start >= previous_end)
        cycles: List[_IntervalTask] = []
        bridges: List[_IntervalTask] = []
        for cycle_index in range(pair_count + 1):
            cycle = self._equipment_task(
                f"{prefix}_cycle_{cycle_index + 1}",
                self.tool.mix_process_time,
                f"CH{chamber}",
                "mix_exposure",
                chamber,
                name=f"CH{chamber} 2x2 exposure",
                mode=MIX_MODE,
                metadata={
                    "segment": segment_index,
                    "cycle": cycle_index + 1,
                },
            )
            cycles.append(cycle)
            if cycle_index == 0:
                self.model.add(cycle.start == head.end)
            else:
                bridge = self._equipment_task(
                    f"{prefix}_bridge_{cycle_index}",
                    self.tool.pair_transfer_time,
                    "VTR",
                    "mix_bridge",
                    chamber,
                    name=f"CH{chamber} 2x2 atomic bridge",
                    mode=MIX_MODE,
                    source="LLupper",
                    destination="LLlower",
                    metadata={
                        "segment": segment_index,
                        "bridge": cycle_index,
                    },
                )
                bridges.append(bridge)
                self.model.add(bridge.start >= cycles[cycle_index - 1].end)
                self.model.add(cycle.start == bridge.end)
        tail = self._equipment_task(
            f"{prefix}_tail",
            self.tool.pair_transfer_time,
            "VTR",
            "mix_tail",
            chamber,
            name=f"CH{chamber} 2x2 PW/PEC tail",
            mode=MIX_MODE,
            source=f"CH{chamber}",
            destination="LLlower",
            metadata={"segment": segment_index},
        )
        self.model.add(tail.start >= cycles[-1].end)
        window = self._span_interval(
            f"{prefix}_window",
            head.start,
            tail.end,
            f"CH{chamber}",
        )
        cycle_offset = self.mix_cycle_counts[chamber]
        if segment_index == 1:
            self._bind_legacy_active(f"mix_active_{chamber}")
            self._bind_legacy_interval(f"mix_head_{chamber}", head)
        self._bind_legacy_interval(
            f"mix_head_{chamber}_{segment_index}", head
        )
        self._bind_legacy_interval(
            f"mix_tail_{chamber}_{segment_index}", tail
        )
        # Unsuffixed tail aliases intentionally point at the last segment.
        self._bind_legacy_interval(f"mix_tail_{chamber}", tail)
        for local_cycle, cycle in enumerate(cycles, start=1):
            global_cycle = cycle_offset + local_cycle
            self._bind_legacy_active(
                f"mix_cycle_used_{chamber}_{global_cycle}"
            )
            self._bind_legacy_interval(
                f"mix_cycle_{chamber}_{global_cycle}", cycle
            )
        for local_bridge, bridge in enumerate(bridges, start=2):
            global_cycle = cycle_offset + local_bridge
            self._bind_legacy_interval(
                f"mix_bridge_{chamber}_{global_cycle}", bridge
            )
        self._bind_legacy_interval(
            f"mix_last_cycle_{chamber}_{segment_index}", cycles[-1]
        )
        if bridges:
            self._bind_legacy_interval(
                f"mix_tail_load_{chamber}_{segment_index}", bridges[-1]
            )
            self._bind_legacy_interval(
                f"mix_tail_load_{chamber}", bridges[-1]
            )
        self.mix_cycle_counts[chamber] += len(cycles)
        # Two boundary PEC wafers remain in the chamber throughout a complete
        # PEC-headed/PEC-tailed segment.
        self._add_pec_use(
            chamber,
            f"{prefix}_boundary_pec",
            window.start,
            window.end,
            2,
        )

        positions: List[Dict[str, Any]] = []
        for local_position in range(pair_count):
            global_position = global_offset + local_position
            load = head if local_position == 0 else bridges[local_position - 1]
            unload = (
                tail
                if local_position == pair_count - 1
                else bridges[local_position + 1]
            )
            selectors: Dict[str, Any] = {}
            for unit_id in mix_units:
                selector = self._bool(
                    f"assign_ch{chamber}_{unit_id}_mix_pos_{global_position + 1}"
                )
                self.assignment_vars[
                    (chamber, MIX_MODE, unit_id, global_position)
                ] = selector
                selectors[unit_id] = selector
                pair_id = self.problem.units[unit_id].pair_ids[0]
                self._map_pair_to_actions(
                    pair_id,
                    load,
                    cycles[local_position].start,
                    cycles[local_position + 1].end,
                    unload,
                    selector,
                )
                embedded = self.problem.pairs[pair_id].embedded_pec
                self._add_pec_use(
                    chamber,
                    f"{prefix}_{unit_id}_embedded_pec_{global_position + 1}",
                    load.start,
                    unload.end,
                    embedded,
                    selector,
                )
            self.model.add_exactly_one(list(selectors.values()))
            positions.append(
                {
                    "position": global_position,
                    "selectors": selectors,
                    "start": load.start,
                    "end": unload.end,
                    "segment": segment_index,
                    "segment_position": local_position,
                }
            )
        return window.end, positions

    def _add_assignment_permutations_and_hints(
        self,
        chamber: int,
        kind: str,
        units: Sequence[str],
        positions: Sequence[Dict[str, Any]],
    ) -> None:
        for unit_id in units:
            row = [
                self.assignment_vars[(chamber, kind, unit_id, position)]
                for position in range(len(positions))
            ]
            self.model.add_exactly_one(row)

        hinted_order = [
            unit_id
            for unit_id in self.input_plan.chamber_units[chamber]
            if self.problem.units[unit_id].kind == kind
        ]
        for position, unit_id in enumerate(hinted_order):
            for other in units:
                selector = self.assignment_vars[
                    (chamber, kind, other, position)
                ]
                self.model.add(selector == int(other == unit_id))

    @staticmethod
    def _dispatch_unit_id(item: Any, known: Mapping[str, Any]) -> Optional[str]:
        if isinstance(item, str):
            return item if item in known else None
        if isinstance(item, Mapping):
            for key in ("unit_id", "unit", "id"):
                value = item.get(key)
                if isinstance(value, str) and value in known:
                    return value
            return None
        if isinstance(item, (list, tuple)):
            for value in item:
                if isinstance(value, str) and value in known:
                    return value
        return None

    def _apply_dispatch_order_hints(self) -> None:
        raw_order = self.input_plan.metadata.get("dispatch_order", ())
        if not isinstance(raw_order, (list, tuple)):
            return
        seen = set()
        stride = max(1, self.ticks(self.tool.pair_transfer_time))
        for rank, item in enumerate(raw_order):
            unit_id = self._dispatch_unit_id(item, self.problem.units)
            if unit_id is None or unit_id in seen:
                continue
            seen.add(unit_id)
            pair_id = self.problem.units[unit_id].pair_ids[0]
            self.model.add_hint(
                self.pairs[pair_id].atr_service.start,
                min(self.horizon, rank * stride),
            )

    def _build_chambers(self) -> None:
        interval = self.tool.cleaning_interval
        for chamber in self.problem.chambers:
            units = list(self.input_plan.chamber_units[chamber])
            canonical_queue = getattr(self.problem, "canonical_queue", None)
            if (
                not self.tool.allow_dynamic_chamber_assignment
                and callable(canonical_queue)
            ):
                expected = list(canonical_queue(chamber))
                if units != expected:
                    raise ValueError(
                        f"Plan CH{chamber} must equal the fixed canonical queue "
                        f"{expected}; got {units}."
                    )
            elif not self.tool.allow_dynamic_chamber_assignment:
                for unit_id in units:
                    unit = self.problem.units[unit_id]
                    canonical_chamber = getattr(unit, "canonical_chamber", None)
                    if canonical_chamber is None and unit.pair_ids:
                        canonical_chamber = getattr(
                            self.problem.pairs[unit.pair_ids[0]],
                            "canonical_chamber",
                            None,
                        )
                    if canonical_chamber is not None and int(canonical_chamber) != chamber:
                        raise ValueError(
                            f"{unit_id} belongs to canonical CH{canonical_chamber}, "
                            f"not CH{chamber}."
                        )
            full_units = [
                unit_id
                for unit_id in units
                if self.problem.units[unit_id].kind == FULL_MODE
            ]
            mix_units = [
                unit_id
                for unit_id in units
                if self.problem.units[unit_id].kind == MIX_MODE
            ]
            previous_end: Optional[Any] = None
            used_cycles = 0
            clean_index = 0

            for position in range(len(full_units)):
                if interval > 0 and used_cycles == interval:
                    clean_index += 1
                    _, previous_end = self._build_cleaning(
                        chamber, clean_index, previous_end
                    )
                    used_cycles = 0
                pos = self._build_full_position(
                    chamber,
                    position,
                    previous_end,
                    full_units,
                )
                self.full_positions[chamber].append(pos)
                previous_end = pos["end"]
                used_cycles += 1

            self._add_assignment_permutations_and_hints(
                chamber,
                FULL_MODE,
                full_units,
                self.full_positions[chamber],
            )

            remaining = len(mix_units)
            offset = 0
            segment_index = 0
            while remaining:
                if interval <= 0:
                    take = remaining
                else:
                    room = interval - used_cycles
                    if room < 2:
                        clean_index += 1
                        _, previous_end = self._build_cleaning(
                            chamber, clean_index, previous_end
                        )
                        used_cycles = 0
                        room = interval
                    take = min(remaining, room - 1)
                segment_index += 1
                previous_end, positions = self._build_mix_segment(
                    chamber,
                    segment_index,
                    offset,
                    take,
                    previous_end,
                    mix_units,
                )
                self.mix_positions[chamber].extend(positions)
                offset += take
                remaining -= take
                used_cycles += take + 1

            self._add_assignment_permutations_and_hints(
                chamber,
                MIX_MODE,
                mix_units,
                self.mix_positions[chamber],
            )

    def _build_load_locks(self) -> None:
        tool = self.tool
        placement_lead = self.ticks(tool.pair_transfer_time)
        llupper_tail = self.ticks(tool.llupper_time)
        for pair_id, pair_state in self.pairs.items():
            pair = pair_state.pair
            upper_start = self._var(f"pair_{pair_id}_llupper_occupancy_start")
            upper_end = self._var(f"pair_{pair_id}_llupper_occupancy_end")
            self.model.add(
                upper_start == pair_state.atr_service.end - placement_lead
            )
            self.model.add(
                upper_end == pair_state.vtr_load_end + llupper_tail
            )
            lower_start = self._var(f"pair_{pair_id}_lllower_occupancy_start")
            lower_end = self._var(f"pair_{pair_id}_lllower_occupancy_end")
            self.model.add(lower_start == pair_state.vtr_unload_start)
            self.model.add(
                lower_end
                == pair_state.atr_return.start
                + self.ticks(tool.atr_load_unload_time)
                + self.ticks(tool.lllower_time)
            )

            for wafer_id in pair.wafer_ids:
                upper_choices = []
                lower_choices = []
                for slot in (1, 2):
                    upper_presence = self._bool(
                        f"wafer_{wafer_id}_llupper_slot_{slot}"
                    )
                    self.legacy_bindings[
                        f"llupper_slot_assign_{wafer_id}_{slot}"
                    ] = upper_presence
                    upper_interval = self._optional_span(
                        f"wafer_{wafer_id}_llupper_slot_{slot}_occupancy",
                        upper_start,
                        upper_end,
                        upper_presence,
                    )
                    self.resources[f"LLupper-{slot}"].append(upper_interval)
                    upper_choices.append(upper_presence)

                    lower_presence = self._bool(
                        f"wafer_{wafer_id}_lllower_slot_{slot}"
                    )
                    self.legacy_bindings[
                        f"lllower_slot_assign_{wafer_id}_{slot}"
                    ] = lower_presence
                    lower_interval = self._optional_span(
                        f"wafer_{wafer_id}_lllower_slot_{slot}_occupancy",
                        lower_start,
                        lower_end,
                        lower_presence,
                    )
                    self.resources[f"LLlower-{slot}"].append(lower_interval)
                    lower_choices.append(lower_presence)
                self.model.add_exactly_one(upper_choices)
                self.model.add_exactly_one(lower_choices)

    @staticmethod
    def _atr_location(location: str) -> str:
        if location.startswith("LL"):
            return "LL"
        return location

    def _atr_setup_ticks(self, left: _IntervalTask, right: _IntervalTask) -> int:
        source = self._atr_location(right.source)
        destination = self._atr_location(left.destination)
        if source == destination:
            return 0
        if {source, destination} == {"LP", "LL"}:
            return self.ticks(self.tool.atr_empty_ll_to_lp_time)
        return self.ticks(self.tool.atr_transfer_time)

    def _add_atr_circuit(self) -> None:
        tasks = self.atr_tasks
        if not tasks:
            return
        arcs = []
        depot_out: Dict[int, Any] = {}
        depot_in: Dict[int, Any] = {}
        for index in range(1, len(tasks) + 1):
            depot_out[index] = self._bool(f"atr_arc_0_{index}")
            depot_in[index] = self._bool(f"atr_arc_{index}_0")
            arcs.append((0, index, depot_out[index]))
            arcs.append((index, 0, depot_in[index]))
        for left_index, left in enumerate(tasks, start=1):
            for right_index, right in enumerate(tasks, start=1):
                if left_index == right_index:
                    continue
                arc = self._bool(f"atr_arc_{left_index}_{right_index}")
                arcs.append((left_index, right_index, arc))
                self.model.add(
                    right.start
                    >= left.end + self._atr_setup_ticks(left, right)
                ).only_enforce_if(arc)
        self.model.add_circuit(arcs)

    def _add_vtr_circuit(self) -> None:
        """Sequence mandatory VTR actions with endpoint-aware empty travel."""

        tasks = self.vtr_tasks
        if not tasks:
            return
        missing = [
            task.task_id
            for task in tasks
            if not task.source or not task.destination
        ]
        if missing:
            raise ValueError(f"VTR actions missing endpoints: {missing}")
        arcs = []
        for index in range(1, len(tasks) + 1):
            arcs.append((0, index, self._bool(f"vtr_arc_0_{index}")))
            arcs.append((index, 0, self._bool(f"vtr_arc_{index}_0")))
        setup = self.ticks(self.tool.pair_transfer_time)
        for left_index, left in enumerate(tasks, start=1):
            for right_index, right in enumerate(tasks, start=1):
                if left_index == right_index:
                    continue
                arc = self._bool(f"vtr_arc_{left_index}_{right_index}")
                arcs.append((left_index, right_index, arc))
                reposition = 0 if left.destination == right.source else setup
                self.model.add(
                    right.start >= left.end + reposition
                ).only_enforce_if(arc)
        self.model.add_circuit(arcs)

    def _add_resource_constraints(self) -> None:
        self._add_atr_circuit()
        self._add_vtr_circuit()
        for resource, intervals in self.resources.items():
            if intervals:
                self.model.add_no_overlap(intervals)
        capacity = self.tool.pec_pool_size // len(self.problem.chambers)
        for chamber in self.problem.chambers:
            if self.pec_intervals[chamber]:
                self.model.add_cumulative(
                    self.pec_intervals[chamber],
                    self.pec_demands[chamber],
                    capacity,
                )

    def _build_objective(self) -> None:
        completions = [pair.completion for pair in self.pairs.values()]
        self.cmax = self._var("c_max")
        self.model.add_max_equality(self.cmax, completions)

        square_upper = self.horizon * self.horizon
        stability_terms: List[Any] = []
        self.wait_square_vars = []
        for index, wait in enumerate(self.wait_vars, start=1):
            square = self._var(
                f"schedule_wait_square_{index}",
                upper=square_upper,
            )
            self.model.add_multiplication_equality(square, [wait, wait])
            self.wait_square_vars.append(square)
            stability_terms.append(square)

        self.chamber_idle_vars = {}
        self.chamber_idle_square_vars = {}
        for chamber in self.problem.chambers:
            busy_terms = [
                task.end - task.start
                for task in self.display_tasks
                if task.resource == f"CH{chamber}"
                and task.task_type == "equipment_action"
            ]
            idle = self._var(f"chamber_{chamber}_idle_total")
            self.model.add(idle == self.cmax - sum(busy_terms))
            idle_square = self._var(
                f"chamber_{chamber}_idle_square",
                upper=square_upper,
            )
            self.model.add_multiplication_equality(
                idle_square, [idle, idle]
            )
            self.chamber_idle_vars[chamber] = idle
            self.chamber_idle_square_vars[chamber] = idle_square
            stability_terms.append(idle_square)

        stability_upper = square_upper * max(1, len(stability_terms))
        if stability_upper >= 2**62:
            raise ValueError(
                "Squared stability objective exceeds the safe CP-SAT integer "
                "range; reduce the time horizon or time_scale."
            )
        self.stability = self._var(
            "schedule_stability_ticks_squared",
            upper=stability_upper,
        )
        self.model.add(self.stability == sum(stability_terms))
        self.model.minimize(self.cmax)

    def _build(self) -> None:
        self._build_pair_front_routes()
        self._build_chambers()
        self._apply_dispatch_order_hints()
        self._build_load_locks()
        self._add_resource_constraints()
        self._build_objective()

    def add_incumbent_hints(self, values: Mapping[Any, int]) -> None:
        self.model.clear_hints()
        for var in self.all_vars:
            if var in values:
                self.model.add_hint(var, int(values[var]))

    def solved_plan(self, values: Mapping[Any, int]) -> Plan:
        chamber_units: Dict[int, List[str]] = {2: [], 3: []}
        for chamber in self.problem.chambers:
            for kind, positions in (
                (FULL_MODE, self.full_positions[chamber]),
                (MIX_MODE, self.mix_positions[chamber]),
            ):
                for position in range(len(positions)):
                    selected = [
                        unit_id
                        for unit_id in self.input_plan.chamber_units[chamber]
                        if self.problem.units[unit_id].kind == kind
                        and values.get(
                            self.assignment_vars[
                                (chamber, kind, unit_id, position)
                            ],
                            0,
                        )
                        > 0
                    ]
                    if len(selected) != 1:
                        raise RuntimeError(
                            f"Could not decode CH{chamber} {kind} position "
                            f"{position + 1}."
                        )
                    chamber_units[chamber].append(selected[0])
        solved = Plan(
            chamber_units=chamber_units,
            source=f"{self.input_plan.source}+cpsat_timing",
            score=self.input_plan.score,
            metadata=dict(self.input_plan.metadata),
        )
        solved.metadata.update(
            {
                "input_dispatch_order": self.input_plan.metadata.get("dispatch_order", []),
                "dispatch_order_role": "cp_sat_hint_only",
                "chamber_assignment_role": (
                    "rl_beam_candidate"
                    if self.tool.allow_dynamic_chamber_assignment
                    else "fixed_canonical_model_structure"
                ),
            }
        )
        solved.validate(self.problem)
        return solved

    def decoded_tasks(self, values: Mapping[Any, int]) -> List[ScheduleTask]:
        result = []
        for spec in self.display_tasks:
            start = values[spec.start] / self.scale
            end = values[spec.end] / self.scale
            if end < start:
                raise RuntimeError(f"Decoded negative task duration: {spec.task_id}")
            resource = spec.resource
            if resource == "CH" and spec.pair_id:
                unit_id = next(
                    unit_id
                    for unit_id, unit in self.problem.units.items()
                    if spec.pair_id in unit.pair_ids
                )
                resource = (
                    f"CH{self.input_plan.unit_to_chamber()[unit_id]}"
                )
            result.append(
                ScheduleTask(
                    task_id=spec.task_id,
                    name=spec.name,
                    resource=resource,
                    start=start,
                    end=end,
                    stage=spec.stage,
                    mode=spec.mode,
                    chamber=spec.chamber
                    if spec.chamber is not None
                    else (
                        int(resource[2:])
                        if resource.startswith("CH") and resource[2:].isdigit()
                        else None
                    ),
                    pair_id=spec.pair_id,
                    wafer_ids=spec.wafer_ids,
                    task_type=spec.task_type,
                    metadata=dict(spec.metadata),
                )
            )
        result.sort(key=lambda item: (item.start, item.end, item.task_id))
        return result

    def legacy_solution(
        self,
        values: Mapping[Any, int],
        solved_plan: Plan,
        tasks: Sequence[ScheduleTask],
        cmax: float,
        stability: float,
    ) -> Dict[str, float]:
        """Build the legacy variable-name view used by Petri Gantt tooling."""

        solution: Dict[str, float] = {
            "c_max": float(cmax),
            "schedule_stability": float(stability),
        }
        for name, var in self.legacy_bindings.items():
            value = float(values[var])
            # Interval bindings are CP-SAT ticks; all persisted Gantt times use
            # seconds. Boolean/assignment bindings stay unchanged.
            if "_start" in name or "_end" in name:
                value /= self.scale
            solution[name] = value
        for pair_id, pair in self.problem.pairs.items():
            completion = values[self.pairs[pair_id].completion] / self.scale
            for wafer_id in pair.wafer_ids:
                solution[f"wafer_completion_{wafer_id}"] = completion

        product_stages = {
            "atr_lp_al", "al", "atr_al_exchange", "atr_al_llupper",
            "llupper", "vtr_load", "pm", "vtr_unload", "lllower",
            "atr_lllower_lp",
        }
        for task in tasks:
            if task.stage not in product_stages:
                continue
            for wafer_id in task.wafer_ids:
                start_name = f"prod_stage_start_{wafer_id}_{task.stage}"
                end_name = f"prod_stage_end_{wafer_id}_{task.stage}"
                solution[start_name] = min(
                    solution.get(start_name, task.start), task.start
                )
                solution[end_name] = max(
                    solution.get(end_name, task.end), task.end
                )

        for chamber in self.problem.chambers:
            full_units = [
                unit_id for unit_id in solved_plan.chamber_units[chamber]
                if self.problem.units[unit_id].kind == FULL_MODE
            ]
            for batch, unit_id in enumerate(full_units, start=1):
                solution[f"full_batch_used_{chamber}_{batch}"] = 1.0
                for side, pair_id in enumerate(
                    self.problem.units[unit_id].pair_ids, start=1
                ):
                    pair = self.problem.pairs[pair_id]
                    solution[
                        f"assign_full_{pair.mode_index}_{chamber}_{batch}_{side}"
                    ] = 1.0
                    for wafer_id in pair.wafer_ids:
                        solution[
                            f"wafer_to_full_pair_{wafer_id}_{pair.mode_index}"
                        ] = 1.0
            mix_units = [
                unit_id for unit_id in solved_plan.chamber_units[chamber]
                if self.problem.units[unit_id].kind == MIX_MODE
            ]
            solution[f"mix_active_{chamber}"] = float(bool(mix_units))
            for position, unit_id in enumerate(mix_units, start=1):
                pair = self.problem.pairs[
                    self.problem.units[unit_id].pair_ids[0]
                ]
                solution[
                    f"assign_mix_{pair.mode_index}_{chamber}_{position}"
                ] = 1.0
                for wafer_id in pair.wafer_ids:
                    solution[
                        f"wafer_to_mix_pair_{wafer_id}_{pair.mode_index}"
                    ] = 1.0
        return solution


class CPSATScheduler:
    """Solve detailed timing for one selected chamber-assignment candidate.

    Dynamic candidates carry CH2/CH3 assignments and compatibility candidates
    carry fixed canonical queues. Bounds certify only this selected CP-SAT
    abstraction, never the legacy MIP or every possible chamber assignment.
    """

    def __init__(self, problem: Problem, config: CPSATConfig):
        if cp_model is None:
            raise RuntimeError(
                "OR-Tools is required by RL-SAT. Install the 'ortools' package."
            ) from _ORTOOLS_IMPORT_ERROR
        self.problem = problem
        self.config = config
        self.config.validate(problem.tool)

    def _new_solver(self, time_limit: float):
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = max(0.01, float(time_limit))
        solver.parameters.num_search_workers = self.config.num_workers
        solver.parameters.random_seed = self.config.random_seed
        solver.parameters.log_search_progress = self.config.log_search_progress
        return solver

    @staticmethod
    def _status_name(solver: Any, status: Any) -> str:
        try:
            return str(solver.status_name(status)).upper()
        except TypeError:  # compatibility with OR-Tools versions exposing a property
            return str(solver.status_name()).upper()

    @staticmethod
    def _capture(
        builder: _ModelBuilder,
        solver: Any,
        status: Any,
        *,
        primary_bound: Optional[float] = None,
    ) -> _SolveSnapshot:
        values = {var: int(solver.value(var)) for var in builder.all_vars}
        return _SolveSnapshot(
            status=CPSATScheduler._status_name(solver, status),
            values=values,
            cmax=int(solver.value(builder.cmax)),
            stability=int(solver.value(builder.stability)),
            primary_bound=float(
                solver.best_objective_bound
                if primary_bound is None
                else primary_bound
            ),
            solver_wall_time=float(solver.wall_time),
            response_stats=str(solver.response_stats()),
            conflicts=int(solver.num_conflicts),
            branches=int(solver.num_branches),
        )

    def solve(
        self,
        plan: Plan,
        *,
        time_limit_seconds: Optional[float] = None,
        lexicographic_stability: Optional[bool] = None,
        incumbent_result: Optional[ScheduleResult] = None,
    ) -> ScheduleResult:
        started = time.perf_counter()
        plan.validate(self.problem)
        builder = _ModelBuilder(self.problem, plan, self.config)
        incumbent_hint_count = 0
        if incumbent_result is not None and incumbent_result.feasible:
            incumbent_tasks = {
                task.task_id: task for task in incumbent_result.tasks
            }
            hinted_vars = set()
            for spec in builder.display_tasks:
                task = incumbent_tasks.get(spec.task_id)
                if task is None:
                    continue
                for var, seconds in (
                    (spec.start, task.start),
                    (spec.end, task.end),
                ):
                    if var in hinted_vars:
                        continue
                    builder.model.add_hint(
                        var, to_ticks(seconds, builder.scale, exact=False)
                    )
                    hinted_vars.add(var)
                    incumbent_hint_count += 1
            if incumbent_result.objective_cmax is not None:
                builder.model.add_hint(
                    builder.cmax,
                    to_ticks(
                        incumbent_result.objective_cmax,
                        builder.scale,
                        exact=False,
                    ),
                )
                incumbent_hint_count += 1
        total_limit = float(
            self.config.time_limit_seconds
            if time_limit_seconds is None
            else time_limit_seconds
        )
        use_secondary = (
            self.config.lexicographic_stability
            if lexicographic_stability is None
            else bool(lexicographic_stability)
        )
        primary_limit = total_limit * (0.7 if use_secondary else 1.0)
        primary_solver = self._new_solver(primary_limit)
        primary_status_code = primary_solver.solve(builder.model)
        primary_status = self._status_name(primary_solver, primary_status_code)
        feasible_statuses = {"FEASIBLE", "OPTIMAL"}

        if primary_status not in feasible_statuses:
            return ScheduleResult(
                status=primary_status,
                objective_cmax=None,
                best_bound=(
                    float(primary_solver.best_objective_bound) / builder.scale
                    if math.isfinite(float(primary_solver.best_objective_bound))
                    else None
                ),
                relative_gap=None,
                wall_time=time.perf_counter() - started,
                plan=plan.clone(),
                tasks=[],
                wafer_completion={},
                pair_completion={},
                certificate_scope=(
                "dynamic_chamber_assignment_cp_sat_abstraction"
                if self.problem.tool.allow_dynamic_chamber_assignment
                else "canonical_assignment_cp_sat_abstraction"
            ),
                message=(
                    "CP-SAT did not find a feasible schedule within this "
                    "candidate's time limit."
                ),
                metadata={
                    "ortools_version": getattr(ortools, "__version__", "unknown"),
                    "time_scale": builder.scale,
                    "horizon_ticks": builder.horizon,
                    "primary_status": primary_status,
                    "incumbent_hint_count": incumbent_hint_count,
                    "response_stats": primary_solver.response_stats(),
                    "model_scope": (
                        "dynamic candidate chamber assignment; dispatch order hint only"
                        if self.problem.tool.allow_dynamic_chamber_assignment
                        else "canonical chamber assignment; dispatch order hint only"
                    ),
                },
            )

        primary = self._capture(builder, primary_solver, primary_status_code)
        chosen = primary
        secondary_status: Optional[str] = None
        secondary_proven = False
        if use_secondary and total_limit - primary_limit > 0.01:
            builder.model.add(builder.cmax <= primary.cmax)
            builder.model.minimize(builder.stability)
            builder.add_incumbent_hints(primary.values)
            secondary_solver = self._new_solver(total_limit - primary_limit)
            secondary_status_code = secondary_solver.solve(builder.model)
            secondary_status = self._status_name(
                secondary_solver, secondary_status_code
            )
            if secondary_status in feasible_statuses:
                chosen = self._capture(
                    builder,
                    secondary_solver,
                    secondary_status_code,
                    primary_bound=primary.primary_bound,
                )
                secondary_proven = secondary_status == "OPTIMAL"

        solved_plan = builder.solved_plan(chosen.values)
        tasks = builder.decoded_tasks(chosen.values)
        pair_completion = {
            pair_id: chosen.values[state.completion] / builder.scale
            for pair_id, state in builder.pairs.items()
        }
        wafer_completion = {
            wafer_id: pair_completion[pair_id]
            for pair_id, pair in self.problem.pairs.items()
            for wafer_id in pair.wafer_ids
        }
        objective = chosen.cmax / builder.scale
        bound = primary.primary_bound / builder.scale
        gap = max(0.0, objective - bound) / max(1.0, abs(objective))
        primary_optimal = primary.status == "OPTIMAL"
        status = "OPTIMAL" if primary_optimal else "FEASIBLE"
        stability_value = chosen.stability / (builder.scale * builder.scale)
        legacy_solution = builder.legacy_solution(
            chosen.values, solved_plan, tasks, objective, stability_value
        )

        return ScheduleResult(
            status=status,
            objective_cmax=objective,
            best_bound=bound,
            relative_gap=gap,
            wall_time=time.perf_counter() - started,
            plan=solved_plan,
            tasks=tasks,
            wafer_completion=wafer_completion,
            pair_completion=pair_completion,
            certificate_scope=(
                "dynamic_chamber_assignment_cp_sat_abstraction"
                if self.problem.tool.allow_dynamic_chamber_assignment
                else "canonical_assignment_cp_sat_abstraction"
            ),
            schedule_stability=stability_value,
            message=(
                "Primary makespan proven optimal for the selected CP-SAT assignment abstraction."
                if primary_optimal
                else "Feasible incumbent for the selected CP-SAT assignment abstraction."
            ),
            metadata={
                "legacy_solution": legacy_solution,
                "ortools_version": getattr(ortools, "__version__", "unknown"),
                "time_scale": builder.scale,
                "legacy_time_unit": "seconds",
                "horizon_ticks": builder.horizon,
                "primary_status": primary.status,
                "incumbent_hint_count": incumbent_hint_count,
                "secondary_status": secondary_status,
                "secondary_stability_proven": secondary_proven,
                "actual_wph": (
                    len(self.problem.product_wafer_ids) * 3600.0 / objective
                    if objective > 0
                    else None
                ),
                "stability_objective": {
                    "unit": "seconds_squared",
                    "definition": (
                        "sum of squared release, LLupper, pre-process chamber, "
                        "post-process and LLlower waits plus squared CH2/CH3 "
                        "aggregate idle"
                    ),
                    "wait_term_count": len(builder.wait_vars),
                    "chamber_idle_seconds": {
                        str(chamber): (
                            chosen.values[builder.chamber_idle_vars[chamber]]
                            / builder.scale
                        )
                        for chamber in self.problem.chambers
                    },
                },
                "primary_solver_wall_time": primary.solver_wall_time,
                "selected_solver_wall_time": chosen.solver_wall_time,
                "conflicts": chosen.conflicts,
                "branches": chosen.branches,
                "response_stats": chosen.response_stats,
                "model_scope": {
                    "chamber_assignment": (
                        "RL/Beam candidate assignment"
                        if self.problem.tool.allow_dynamic_chamber_assignment
                        else "fixed canonical project mapping"
                    ),
                    "dispatch_order": "RL value/search hint only",
                    "full_before_mix": "per-chamber project process rule",
                    "certificate": (
                        "conditional on the selected CP-SAT assignment abstraction; "
                        "not a legacy SCIP-MIP global certificate"
                    ),
                },
                "physical_model": {
                    "product_route": (
                        "LP-ATR-AL-LLupper-VTR-CH-VTR-LLlower-ATR-LP"
                    ),
                    "mix_bridge": (
                        "atomic exchange; k pairs use k+1 exposures"
                    ),
                    "cleaning": "per-candidate chamber process-cycle epochs",
                    "vtr_empty_reposition": (
                        "endpoint-aware circuit; zero for matching endpoints, "
                        "pair_transfer_time otherwise"
                    ),
                    "resources": [
                        "CH2",
                        "CH3",
                        "ATR",
                        "AL",
                        "VTR",
                        "LLupper slots",
                        "LLlower slots",
                        "chamber-bound PEC tokens",
                    ],
                },
                "declared_abstractions": [
                    (
                        "A bundled two-wafer ATR front service holds the ATR "
                        "through the serial one-slot AL calibrations."
                    ),
                    (
                        "VTR loaded exchanges use pair_transfer_time. Its "
                        "empty reposition circuit uses coarsened physical "
                        "endpoints and pair_transfer_time on endpoint changes."
                    ),
                    (
                        "PEC identity is symmetry-aggregated as cumulative "
                        "chamber-bound token capacity; token count and dwell "
                        "windows are exact for this abstraction."
                    ),
                ],
            },
        )


def solve_fixed_plan(
    problem: Problem,
    plan: Plan,
    config: CPSATConfig,
    *,
    time_limit_seconds: Optional[float] = None,
) -> ScheduleResult:
    """Convenience wrapper used by scripts and tests."""

    return CPSATScheduler(problem, config).solve(
        plan,
        time_limit_seconds=time_limit_seconds,
    )


__all__ = ["CPSATScheduler", "solve_fixed_plan"]

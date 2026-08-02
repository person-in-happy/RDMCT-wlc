from __future__ import annotations

import copy
import math
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from .config import FULL_MODE, MIX_MODE, ToolConfig


@dataclass(frozen=True)
class WaferPair:
    pair_id: str
    mode: str
    mode_index: int
    wafer_ids: Tuple[int, ...]
    product_load: int
    embedded_pec: int
    canonical_chamber: int
    canonical_position: int
    canonical_batch: Optional[int] = None
    canonical_side: Optional[int] = None
    exposure_count: int = 1

    @property
    def is_tail_pair(self) -> bool:
        return self.product_load == 1


@dataclass(frozen=True)
class SchedulingUnit:
    unit_id: str
    kind: str
    pair_ids: Tuple[str, ...]
    product_wafers: int
    pec_fill: int
    process_cycles: int
    estimated_duration: float
    canonical_chamber: int
    canonical_position: int


@dataclass
class Problem:
    tool: ToolConfig
    wafer_modes: Dict[int, str]
    pairs: Dict[str, WaferPair]
    units: Dict[str, SchedulingUnit]
    unit_order: List[str]

    @property
    def chambers(self) -> Tuple[int, int]:
        return (2, 3)

    @property
    def full_units(self) -> List[str]:
        return [unit_id for unit_id in self.unit_order if self.units[unit_id].kind == FULL_MODE]

    @property
    def mix_units(self) -> List[str]:
        return [unit_id for unit_id in self.unit_order if self.units[unit_id].kind == MIX_MODE]

    @property
    def product_wafer_ids(self) -> List[int]:
        return sorted(self.wafer_modes)

    def canonical_queue(self, chamber: int) -> List[str]:
        if chamber not in self.chambers:
            raise ValueError(f'Unknown process chamber: CH{chamber}')
        return [
            unit_id
            for unit_id in self.unit_order
            if self.units[unit_id].canonical_chamber == chamber
        ]

    @property
    def canonical_queues(self) -> Dict[int, List[str]]:
        return {
            chamber: self.canonical_queue(chamber)
            for chamber in self.chambers
        }


@dataclass
class Plan:
    chamber_units: Dict[int, List[str]] = field(
        default_factory=lambda: {2: [], 3: []}
    )
    source: str = "unknown"
    score: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def clone(self) -> "Plan":
        return copy.deepcopy(self)

    def unit_to_chamber(self) -> Dict[str, int]:
        return {
            unit_id: chamber
            for chamber, unit_ids in self.chamber_units.items()
            for unit_id in unit_ids
        }

    def assignments(self) -> List[Tuple[str, int, int]]:
        return [
            (unit_id, chamber, position)
            for chamber in sorted(self.chamber_units)
            for position, unit_id in enumerate(self.chamber_units[chamber], start=1)
        ]

    def dispatch_order(self) -> List[str]:
        '''Return the cross-chamber release priority stored by RL/Beam.'''

        raw = self.metadata.get('dispatch_order')
        if raw is None:
            return [
                unit_id
                for chamber in sorted(self.chamber_units)
                for unit_id in self.chamber_units[chamber]
            ]
        if not isinstance(raw, (list, tuple)):
            raise ValueError('plan metadata dispatch_order must be a list.')
        return [str(unit_id) for unit_id in raw]

    def validate(self, problem: Problem, complete: bool = True) -> None:
        if set(self.chamber_units) != set(problem.chambers):
            raise ValueError('Plan must contain exactly CH2 and CH3.')
        flat = [unit for units in self.chamber_units.values() for unit in units]
        if len(flat) != len(set(flat)):
            raise ValueError("A scheduling unit appears more than once.")
        unknown = sorted(set(flat) - set(problem.units))
        if unknown:
            raise ValueError(f"Plan contains unknown units: {unknown}")
        if complete and set(flat) != set(problem.units):
            missing = sorted(set(problem.units) - set(flat))
            raise ValueError(f"Plan is incomplete; missing units: {missing}")
        for chamber in problem.chambers:
            actual = self.chamber_units[chamber]
            if problem.tool.allow_dynamic_chamber_assignment:
                kinds = [problem.units[unit_id].kind for unit_id in actual]
                first_mix = next(
                    (index for index, kind in enumerate(kinds) if kind == MIX_MODE),
                    len(kinds),
                )
                if any(kind == FULL_MODE for kind in kinds[first_mix:]):
                    raise ValueError(
                        f'CH{chamber} must schedule all 4x1 units before 2x2 units.'
                    )
            else:
                canonical = problem.canonical_queue(chamber)
                expected = canonical if complete else canonical[: len(actual)]
                if actual != expected:
                    raise ValueError(
                        f'CH{chamber} must follow its fixed canonical queue. '
                        f'Expected {expected}, got {actual}.'
                    )
                wrong_chamber = [
                    unit_id
                    for unit_id in actual
                    if problem.units[unit_id].canonical_chamber != chamber
                ]
                if wrong_chamber:
                    raise ValueError(
                        f'Units assigned outside canonical CH{chamber}: {wrong_chamber}'
                    )

        if 'dispatch_order' in self.metadata:
            dispatch = self.dispatch_order()
            if len(dispatch) != len(set(dispatch)):
                raise ValueError('dispatch_order contains a duplicate scheduling unit.')
            if set(dispatch) != set(flat):
                missing = sorted(set(flat) - set(dispatch))
                extra = sorted(set(dispatch) - set(flat))
                raise ValueError(
                    'dispatch_order must contain exactly the scheduled units; '
                    f'missing={missing}, extra={extra}.'
                )
            positions = {unit_id: index for index, unit_id in enumerate(dispatch)}
            for chamber in problem.chambers:
                projection = sorted(
                    self.chamber_units[chamber],
                    key=positions.__getitem__,
                )
                if projection != self.chamber_units[chamber]:
                    raise ValueError(
                        f'dispatch_order reverses canonical CH{chamber} queue.'
                    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "chamber_units": {str(key): list(value) for key, value in self.chamber_units.items()},
            "source": self.source,
            "score": self.score,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "Plan":
        return cls(
            chamber_units={int(key): list(value) for key, value in raw["chamber_units"].items()},
            source=str(raw.get("source", "loaded")),
            score=raw.get("score"),
            metadata=dict(raw.get("metadata", {})),
        )


@dataclass
class ScheduleTask:
    task_id: str
    name: str
    resource: str
    start: float
    end: float
    stage: str
    mode: str = ""
    chamber: Optional[int] = None
    pair_id: Optional[str] = None
    wafer_ids: Tuple[int, ...] = ()
    task_type: str = "operation"
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def duration(self) -> float:
        return self.end - self.start

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["wafer_ids"] = list(self.wafer_ids)
        data["duration"] = self.duration
        return data


@dataclass
class ScheduleResult:
    status: str
    objective_cmax: Optional[float]
    best_bound: Optional[float]
    relative_gap: Optional[float]
    wall_time: float
    plan: Plan
    tasks: List[ScheduleTask]
    wafer_completion: Dict[int, float]
    pair_completion: Dict[str, float]
    solver: str = "OR-Tools CP-SAT"
    scip_used: bool = False
    certificate_scope: str = "fixed_rl_plan"
    schedule_stability: Optional[float] = None
    message: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def feasible(self) -> bool:
        return self.status.upper() in {"FEASIBLE", "OPTIMAL"}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": "rl_sat_result_v1",
            "status": self.status,
            "solver": self.solver,
            "scip_used": self.scip_used,
            "certificate_scope": self.certificate_scope,
            "objective_cmax": self.objective_cmax,
            "best_bound": self.best_bound,
            "relative_gap": self.relative_gap,
            "schedule_stability": self.schedule_stability,
            "wall_time": self.wall_time,
            "plan": self.plan.to_dict(),
            "tasks": [task.to_dict() for task in self.tasks],
            "wafer_completion": {str(key): value for key, value in self.wafer_completion.items()},
            "pair_completion": dict(self.pair_completion),
            "message": self.message,
            "metadata": self.metadata,
        }


def _canonical_pair_slot(
    mode: str,
    mode_index: int,
) -> Tuple[int, int, Optional[int], Optional[int]]:
    if mode == FULL_MODE:
        # Exact order in petri_mip_generator.py: batch, CH2/CH3, side 1/2.
        zero_based = mode_index - 1
        batch = zero_based // 4 + 1
        chamber = 2 + ((zero_based % 4) // 2)
        side = zero_based % 2 + 1
        return chamber, batch, batch, side
    # P1->CH2-pos1, P2->CH3-pos1, P3->CH2-pos2, ...
    chamber = 2 if mode_index % 2 else 3
    position = (mode_index + 1) // 2
    return chamber, position, None, None


def _pair_mode_wafers(wafer_ids: Sequence[int], mode: str) -> List[WaferPair]:
    result: List[WaferPair] = []
    for index in range(0, len(wafer_ids), 2):
        members = tuple(wafer_ids[index : index + 2])
        mode_index = index // 2 + 1
        prefix = "F" if mode == FULL_MODE else "M"
        chamber, position, batch, side = _canonical_pair_slot(mode, mode_index)
        result.append(
            WaferPair(
                pair_id=f"{prefix}{mode_index}",
                mode=mode,
                mode_index=mode_index,
                wafer_ids=members,
                product_load=len(members),
                embedded_pec=2 - len(members),
                canonical_chamber=chamber,
                canonical_position=position,
                canonical_batch=batch,
                canonical_side=side,
                exposure_count=1 if mode == FULL_MODE else 2,
            )
        )
    return result


def build_problem(tool: ToolConfig) -> Problem:
    tool.validate()
    modes = tool.resolved_modes()
    wafer_modes = {wafer_id: mode for wafer_id, mode in enumerate(modes, start=1)}
    full_wafers = [wafer_id for wafer_id, mode in wafer_modes.items() if mode == FULL_MODE]
    mix_wafers = [wafer_id for wafer_id, mode in wafer_modes.items() if mode == MIX_MODE]
    pair_list = _pair_mode_wafers(full_wafers, FULL_MODE) + _pair_mode_wafers(
        mix_wafers, MIX_MODE
    )
    pairs = {pair.pair_id: pair for pair in pair_list}
    units: Dict[str, SchedulingUnit] = {}
    order: List[str] = []

    full_pairs = [pair for pair in pair_list if pair.mode == FULL_MODE]
    for index in range(0, len(full_pairs), 2):
        members = full_pairs[index : index + 2]
        unit_id = f"FB{index // 2 + 1}"
        canonical_chamber = members[0].canonical_chamber
        canonical_position = members[0].canonical_position
        if any(
            pair.canonical_chamber != canonical_chamber
            or pair.canonical_position != canonical_position
            for pair in members
        ):
            raise AssertionError('Canonical 4x1 batch crosses a CH/batch slot.')
        product_count = sum(pair.product_load for pair in members)
        pec_fill = 4 - product_count
        units[unit_id] = SchedulingUnit(
            unit_id=unit_id,
            kind=FULL_MODE,
            pair_ids=tuple(pair.pair_id for pair in members),
            product_wafers=product_count,
            pec_fill=pec_fill,
            process_cycles=1,
            estimated_duration=(
                4 * tool.pair_transfer_time
                + 2 * tool.pm_rotation_time_180
                + tool.full_process_time
            ),
            canonical_chamber=canonical_chamber,
            canonical_position=canonical_position,
        )
        order.append(unit_id)

    mix_pairs = [pair for pair in pair_list if pair.mode == MIX_MODE]
    for pair in mix_pairs:
        unit_id = f"MU{pair.mode_index}"
        units[unit_id] = SchedulingUnit(
            unit_id=unit_id,
            kind=MIX_MODE,
            pair_ids=(pair.pair_id,),
            product_wafers=pair.product_load,
            pec_fill=pair.embedded_pec,
            # Every 2x2 product pair participates in two adjacent exposures.
            process_cycles=pair.exposure_count,
            estimated_duration=(
                2 * tool.mix_process_time + 2 * tool.pair_transfer_time
            ),
            canonical_chamber=pair.canonical_chamber,
            canonical_position=pair.canonical_position,
        )
        order.append(unit_id)

    return Problem(
        tool=tool,
        wafer_modes=wafer_modes,
        pairs=pairs,
        units=units,
        unit_order=order,
    )


def flatten_pair_ids(problem: Problem, unit_ids: Iterable[str]) -> List[str]:
    return [
        pair_id
        for unit_id in unit_ids
        for pair_id in problem.units[unit_id].pair_ids
    ]

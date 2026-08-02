from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

from .config import FULL_MODE, MIX_MODE
from .domain import Plan, Problem


FULL_ASSIGN_RE = re.compile(r"^assign_full_(\d+)_(\d+)_(\d+)_(\d+)\s+([-+0-9.eE]+)")
MIX_ASSIGN_RE = re.compile(r"^assign_mix_(\d+)_(\d+)_(\d+)\s+([-+0-9.eE]+)")


@dataclass
class PlanEstimate:
    makespan_lower_bound: float
    chamber_loads: Dict[int, float]
    robot_load: float
    aligner_load: float
    imbalance: float
    cleaning_count: int

    def to_dict(self):
        return {
            "makespan_lower_bound": self.makespan_lower_bound,
            "chamber_loads": {str(k): v for k, v in self.chamber_loads.items()},
            "robot_load": self.robot_load,
            "aligner_load": self.aligner_load,
            "imbalance": self.imbalance,
            "cleaning_count": self.cleaning_count,
        }


def _chamber_process_load(problem: Problem, units: Iterable[str]) -> Tuple[float, int]:
    tool = problem.tool
    full_units = [unit for unit in units if problem.units[unit].kind == FULL_MODE]
    mix_units = [unit for unit in units if problem.units[unit].kind == MIX_MODE]
    process_time = 0.0
    cleaning_count = 0
    cycles_since_clean = 0
    cleaning_duration = (
        4 * tool.pair_transfer_time
        + 2 * tool.pm_rotation_time_180
        + tool.effective_cleaning_process_time
    )

    for unit in full_units:
        if (
            tool.cleaning_interval
            and cycles_since_clean == tool.cleaning_interval
        ):
            cleaning_count += 1
            process_time += cleaning_duration
            cycles_since_clean = 0
        process_time += problem.units[unit].estimated_duration
        cycles_since_clean += 1

    remaining = len(mix_units)
    while remaining:
        if tool.cleaning_interval:
            room = tool.cleaning_interval - cycles_since_clean
            if room < 2:
                cleaning_count += 1
                process_time += cleaning_duration
                cycles_since_clean = 0
                room = tool.cleaning_interval
            take = min(remaining, max(1, room - 1))
        else:
            take = remaining
        process_time += (
            (take + 2) * tool.pair_transfer_time
            + (take + 1) * tool.mix_process_time
        )
        cycles_since_clean += take + 1
        remaining -= take
        if remaining and tool.cleaning_interval and cycles_since_clean >= tool.cleaning_interval:
            cleaning_count += 1
            process_time += cleaning_duration
            cycles_since_clean = 0
    return process_time, cleaning_count


def estimate_plan(problem: Problem, plan: Plan) -> PlanEstimate:
    plan.validate(problem, complete=False)
    chamber_loads: Dict[int, float] = {}
    cleaning_count = 0
    for chamber in problem.chambers:
        load, cleans = _chamber_process_load(problem, plan.chamber_units[chamber])
        chamber_loads[chamber] = load
        cleaning_count += cleans

    pairs = [
        problem.pairs[pair_id]
        for unit_ids in plan.chamber_units.values()
        for unit_id in unit_ids
        for pair_id in problem.units[unit_id].pair_ids
    ]
    tool = problem.tool
    robot_load = sum(
        tool.atr_lp_al_total_time
        + tool.atr_al_llupper_total_time
        + tool.atr_lllower_lp_total_time
        for _ in pairs
    )
    robot_load += sum(
        2 * tool.pair_transfer_time
        + (tool.pair_transfer_time if pair.mode == MIX_MODE else 0.0)
        for pair in pairs
    )
    aligner_load = sum(
        pair.product_load * tool.aligner_time
        + (tool.al_exchange_time if pair.product_load == 2 else 0.0)
        for pair in pairs
    )
    chamber_peak = max(chamber_loads.values(), default=0.0)
    lower_bound = max(chamber_peak, robot_load / 2.0, aligner_load)
    imbalance = abs(chamber_loads.get(2, 0.0) - chamber_loads.get(3, 0.0))
    return PlanEstimate(
        makespan_lower_bound=lower_bound,
        chamber_loads=chamber_loads,
        robot_load=robot_load,
        aligner_load=aligner_load,
        imbalance=imbalance,
        cleaning_count=cleaning_count,
    )


class InitialPlanGenerator:
    """Generate a deterministic structure-aware incumbent without SCIP."""

    def __init__(self, problem: Problem):
        self.problem = problem

    def generate(self) -> Plan:
        if not self.problem.tool.allow_dynamic_chamber_assignment:
            queues = self.problem.canonical_queues
            plan = Plan(
                chamber_units={
                    chamber: list(queue) for chamber, queue in queues.items()
                },
                source="structure_aware_initial",
            )
            loads = {chamber: 0.0 for chamber in self.problem.chambers}
            next_index = {chamber: 0 for chamber in self.problem.chambers}
            dispatch_order: List[str] = []
            while len(dispatch_order) < len(self.problem.units):
                available = [
                    chamber
                    for chamber in self.problem.chambers
                    if next_index[chamber] < len(queues[chamber])
                ]
                chamber = min(available, key=lambda ch: (loads[ch], ch))
                unit_id = queues[chamber][next_index[chamber]]
                next_index[chamber] += 1
                dispatch_order.append(unit_id)
                loads[chamber] += self.problem.units[unit_id].estimated_duration
        else:
            plan = Plan(
                chamber_units={chamber: [] for chamber in self.problem.chambers},
                source="balanced_dynamic_initial",
            )
            dispatch_order = []
            for unit_id in self.problem.unit_order:
                choices = []
                for chamber in self.problem.chambers:
                    trial_units = {
                        key: list(value) for key, value in plan.chamber_units.items()
                    }
                    trial_units[chamber].append(unit_id)
                    loads = {}
                    clean_count = 0
                    for key in self.problem.chambers:
                        load, cleans = _chamber_process_load(
                            self.problem, trial_units[key]
                        )
                        loads[key] = load
                        clean_count += cleans
                    choices.append(
                        (
                            max(loads.values()),
                            abs(loads[2] - loads[3]),
                            clean_count,
                            chamber,
                            loads,
                        )
                    )
                _, _, _, chamber, loads = min(choices)
                plan.chamber_units[chamber].append(unit_id)
                dispatch_order.append(unit_id)

        plan.metadata["dispatch_order"] = dispatch_order
        plan.metadata["assignment_mode"] = (
            "dynamic_balanced"
            if self.problem.tool.allow_dynamic_chamber_assignment
            else "fixed_canonical"
        )
        plan.metadata["dispatch_seed_loads"] = {
            str(chamber): load for chamber, load in loads.items()
        }
        plan.validate(self.problem)
        estimate = estimate_plan(self.problem, plan)
        plan.score = estimate.makespan_lower_bound
        plan.metadata["estimate"] = estimate.to_dict()
        return plan

    def from_legacy_sol(self, path: str | Path) -> Plan:
        """Check legacy structural variables without importing or using SCIP.

        The legacy MIP records canonical assignments. They are checked for
        compatibility only; dynamic mode then builds a fresh balanced Plan,
        while canonical mode recreates the fixed queues.
        """

        solution_path = Path(path)
        full_records: List[Tuple[int, int, int, int]] = []
        mix_records: List[Tuple[int, int, int]] = []
        with solution_path.open("r", encoding="utf-8", errors="ignore") as handle:
            for raw_line in handle:
                line = raw_line.strip()
                full_match = FULL_ASSIGN_RE.match(line)
                if full_match and float(full_match.group(5)) > 0.5:
                    full_records.append((
                        int(full_match.group(1)),
                        int(full_match.group(2)),
                        int(full_match.group(3)),
                        int(full_match.group(4)),
                    ))
                    continue
                mix_match = MIX_ASSIGN_RE.match(line)
                if mix_match and float(mix_match.group(4)) > 0.5:
                    mix_records.append((
                        int(mix_match.group(1)),
                        int(mix_match.group(2)),
                        int(mix_match.group(3)),
                    ))

        checked = 0
        for pair_index, chamber, batch, side in full_records:
            pair = self.problem.pairs.get(f'F{pair_index}')
            if pair is None or pair.mode != FULL_MODE:
                raise ValueError(
                    f'Legacy solution has unknown positive full pair F{pair_index}.'
                )
            expected = (
                pair.canonical_chamber,
                pair.canonical_batch,
                pair.canonical_side,
            )
            actual = (chamber, batch, side)
            if actual != expected:
                raise ValueError(
                    f'Legacy F{pair_index} assignment {actual} conflicts with '
                    f'canonical {expected}.'
                )
            checked += 1

        for pair_index, chamber, position in mix_records:
            pair = self.problem.pairs.get(f'M{pair_index}')
            if pair is None or pair.mode != MIX_MODE:
                raise ValueError(
                    f'Legacy solution has unknown positive mix pair M{pair_index}.'
                )
            expected = (pair.canonical_chamber, pair.canonical_position)
            actual = (chamber, position)
            if actual != expected:
                raise ValueError(
                    f'Legacy M{pair_index} assignment {actual} conflicts with '
                    f'canonical {expected}.'
                )
            checked += 1

        if not checked:
            raise ValueError(
                f'No positive assign_full/assign_mix records found in {solution_path}.'
            )
        plan = self.generate()
        plan.source = f'structure_aware_initial+legacy_check:{solution_path.name}'
        plan.metadata.update(
            {
                'legacy_structural_assignments_checked': checked,
                'legacy_solution': str(solution_path),
                'legacy_solution_role': 'consistency_check_only',
            }
        )
        return plan

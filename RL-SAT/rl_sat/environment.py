from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import numpy as np

from .config import FULL_MODE, MIX_MODE
from .domain import Plan, Problem
from .initial_solution import estimate_plan


UNIT_FEATURE_DIM = 10
CHAMBER_FEATURE_DIM = 7
GLOBAL_FEATURE_DIM = 5


@dataclass
class Observation:
    unit_features: np.ndarray
    chamber_features: np.ndarray
    global_features: np.ndarray
    action_mask: np.ndarray
    unit_ids: List[str]

    def as_torch(self, device=None):
        import torch

        return {
            "unit_features": torch.as_tensor(
                self.unit_features, dtype=torch.float32, device=device
            ),
            "chamber_features": torch.as_tensor(
                self.chamber_features, dtype=torch.float32, device=device
            ),
            "global_features": torch.as_tensor(
                self.global_features, dtype=torch.float32, device=device
            ),
            "action_mask": torch.as_tensor(
                self.action_mask, dtype=torch.bool, device=device
            ),
        }


class StructureAwareSchedulingEnv:
    """Finite structural MDP used by A3C and Beam search.

    Pair membership remains symmetry-broken. In dynamic mode an action assigns
    the next scheduling unit to CH2 or CH3; in compatibility mode it releases
    the head of a fixed canonical queue. Detailed timing, cleaning and physical
    feasibility are handled later by CP-SAT.
    """

    def __init__(self, problem: Problem, seed: int = 1):
        self.problem = problem
        self.rng = np.random.default_rng(seed)
        self.unit_ids = list(problem.unit_order)
        self.unit_index = {unit_id: index for index, unit_id in enumerate(self.unit_ids)}
        self.normalizer = max(
            1.0,
            sum(unit.estimated_duration for unit in self.problem.units.values()) / 2.0,
        )
        self.plan = Plan(source='a3c', metadata={'dispatch_order': []})
        self.scheduled: Dict[str, int] = {}
        self.done = False
        self._last_potential = 0.0

    def clone(self) -> "StructureAwareSchedulingEnv":
        return copy.deepcopy(self)

    def reset(self, prefix: Optional[Plan] = None) -> Observation:
        self.plan = Plan(source='a3c', metadata={'dispatch_order': []})
        self.scheduled = {}
        self.done = False
        if prefix is not None:
            prefix.validate(self.problem, complete=False)
            self.plan = prefix.clone()
            if 'dispatch_order' not in self.plan.metadata:
                self.plan.metadata['dispatch_order'] = self.plan.dispatch_order()
            for chamber, units in self.plan.chamber_units.items():
                for unit_id in units:
                    self.scheduled[unit_id] = chamber
            self.done = len(self.scheduled) == len(self.unit_ids)
        self._last_potential = self._potential()
        return self.observation()

    @property
    def remaining(self) -> List[str]:
        return [unit for unit in self.unit_ids if unit not in self.scheduled]

    def _mix_started(self, chamber: int) -> bool:
        return any(
            self.problem.units[unit_id].kind == MIX_MODE
            for unit_id in self.plan.chamber_units[chamber]
        )

    def action_mask(self) -> np.ndarray:
        mask = np.zeros((len(self.unit_ids), 2), dtype=bool)
        if self.problem.tool.allow_dynamic_chamber_assignment:
            remaining = self.remaining
            if remaining:
                # Unit identities stay symmetry-broken in their original order;
                # the learned action chooses CH2 versus CH3. All 4x1 units
                # precede 2x2 units globally, matching chamber construction.
                unit_id = remaining[0]
                unit_idx = self.unit_index[unit_id]
                for chamber_idx, chamber in enumerate(self.problem.chambers):
                    if (
                        self.problem.units[unit_id].kind == FULL_MODE
                        and self._mix_started(chamber)
                    ):
                        continue
                    mask[unit_idx, chamber_idx] = True
        else:
            for chamber_idx, chamber in enumerate(self.problem.chambers):
                queue = self.problem.canonical_queue(chamber)
                next_position = len(self.plan.chamber_units[chamber])
                if next_position >= len(queue):
                    continue
                unit_id = queue[next_position]
                mask[self.unit_index[unit_id], chamber_idx] = True
        if self.remaining and not mask.any():
            raise RuntimeError('Structural action mask reached a dead end.')
        return mask

    def _loads(self) -> Dict[int, float]:
        estimate = estimate_plan(self.problem, self.plan)
        return estimate.chamber_loads

    def observation(self) -> Observation:
        tool = self.problem.tool
        total_units = max(1, len(self.unit_ids))
        max_unit_duration = max(
            1.0, *(unit.estimated_duration for unit in self.problem.units.values())
        )
        max_canonical_position = max(
            1, *(unit.canonical_position for unit in self.problem.units.values())
        )
        unit_features = np.zeros((len(self.unit_ids), UNIT_FEATURE_DIM), dtype=np.float32)
        for index, unit_id in enumerate(self.unit_ids):
            unit = self.problem.units[unit_id]
            unit_features[index] = np.asarray(
                [
                    float(unit.kind == FULL_MODE),
                    float(unit.kind == MIX_MODE),
                    unit.product_wafers / 4.0,
                    unit.pec_fill / 4.0,
                    unit.process_cycles / max(tool.cleaning_interval, 1),
                    unit.estimated_duration / max_unit_duration,
                    len(unit.pair_ids) / 2.0,
                    float(unit.canonical_chamber == 3),
                    float(unit_id in self.scheduled),
                    unit.canonical_position / max_canonical_position,
                ],
                dtype=np.float32,
            )

        loads = self._loads()
        load_scale = max(self.normalizer, max(loads.values(), default=1.0))
        chamber_features = np.zeros((2, CHAMBER_FEATURE_DIM), dtype=np.float32)
        for chamber_idx, chamber in enumerate(self.problem.chambers):
            units = self.plan.chamber_units[chamber]
            full_count = sum(self.problem.units[unit].kind == FULL_MODE for unit in units)
            mix_count = sum(self.problem.units[unit].kind == MIX_MODE for unit in units)
            process_cycles = sum(
                self.problem.units[unit].process_cycles for unit in units
            )
            chamber_features[chamber_idx] = np.asarray(
                [
                    loads.get(chamber, 0.0) / load_scale,
                    full_count / total_units,
                    mix_count / total_units,
                    process_cycles / max(tool.cleaning_interval, 1),
                    float(self._mix_started(chamber)),
                    len(units) / total_units,
                    (tool.pec_pool_size / 2.0) / 4.0,
                ],
                dtype=np.float32,
            )

        remaining = len(self.remaining)
        full_remaining = sum(
            self.problem.units[unit].kind == FULL_MODE for unit in self.remaining
        )
        mix_remaining = remaining - full_remaining
        global_features = np.asarray(
            [
                remaining / total_units,
                full_remaining / total_units,
                mix_remaining / total_units,
                abs(loads.get(2, 0.0) - loads.get(3, 0.0)) / load_scale,
                len(self.scheduled) / total_units,
            ],
            dtype=np.float32,
        )
        return Observation(
            unit_features=unit_features,
            chamber_features=chamber_features,
            global_features=global_features,
            action_mask=self.action_mask() if not self.done else np.zeros((len(self.unit_ids), 2), dtype=bool),
            unit_ids=list(self.unit_ids),
        )

    def _potential(self) -> float:
        estimate = estimate_plan(self.problem, self.plan)
        return (
            estimate.makespan_lower_bound
            + 0.10 * estimate.imbalance
            + 0.02 * estimate.cleaning_count * self.problem.tool.effective_cleaning_process_time
        )

    def step(self, action: int) -> Tuple[Observation, float, bool, Dict[str, float]]:
        if self.done:
            raise RuntimeError("Cannot step a completed environment.")
        unit_idx, chamber_idx = divmod(int(action), 2)
        if unit_idx < 0 or unit_idx >= len(self.unit_ids) or chamber_idx not in (0, 1):
            raise ValueError(f"Invalid action index: {action}")
        mask = self.action_mask()
        if not mask[unit_idx, chamber_idx]:
            raise ValueError(f"Masked structural action selected: {action}")
        unit_id = self.unit_ids[unit_idx]
        chamber = self.problem.chambers[chamber_idx]
        self.plan.chamber_units[chamber].append(unit_id)
        self.scheduled[unit_id] = chamber
        dispatch_order = self.plan.metadata.setdefault('dispatch_order', [])
        if not isinstance(dispatch_order, list):
            dispatch_order = list(dispatch_order)
            self.plan.metadata['dispatch_order'] = dispatch_order
        dispatch_order.append(unit_id)
        new_potential = self._potential()
        reward = -(new_potential - self._last_potential) / self.normalizer
        self._last_potential = new_potential
        self.done = len(self.scheduled) == len(self.unit_ids)
        if self.done:
            self.plan.validate(self.problem)
            estimate = estimate_plan(self.problem, self.plan)
            self.plan.score = estimate.makespan_lower_bound
            self.plan.metadata["estimate"] = estimate.to_dict()
            reward -= 0.05 * estimate.imbalance / self.normalizer
        info = {
            "potential": new_potential,
            "scheduled": float(len(self.scheduled)),
            "remaining": float(len(self.remaining)),
        }
        return self.observation(), float(reward), self.done, info

    def signature(self) -> Tuple[str, ...]:
        if not self.problem.tool.allow_dynamic_chamber_assignment:
            return tuple(self.plan.dispatch_order())
        assignments = self.plan.unit_to_chamber()
        return tuple(
            f"{unit_id}@CH{assignments[unit_id]}"
            for unit_id in self.plan.dispatch_order()
        )

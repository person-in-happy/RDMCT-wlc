from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

import numpy as np
import torch

from .config import BeamConfig
from .domain import Plan, Problem
from .environment import StructureAwareSchedulingEnv
from .initial_solution import estimate_plan
from .model import StructureAwareActorCritic


@dataclass
class BeamNode:
    env: StructureAwareSchedulingEnv
    log_probability: float
    rank_score: float


def _assignment_signature(plan: Plan) -> Tuple[str, ...]:
    assignments = plan.unit_to_chamber()
    return tuple(
        f"{unit_id}@CH{assignments[unit_id]}"
        for unit_id in plan.dispatch_order()
    )

def _diversity_distance(first: Plan, second: Plan) -> float:
    first_order = _assignment_signature(first)
    second_order = _assignment_signature(second)
    first_set = set(first_order)
    second_set = set(second_order)
    union = first_set | second_set
    if not union:
        return 0.0
    membership_distance = len(first_set ^ second_set) / len(union)
    shared = sorted(first_set & second_set)
    first_pos = {unit: index for index, unit in enumerate(first_order)}
    second_pos = {unit: index for index, unit in enumerate(second_order)}
    discordant = 0
    comparisons = 0
    for left_index, left in enumerate(shared):
        for right in shared[left_index + 1 :]:
            comparisons += 1
            first_before = first_pos[left] < first_pos[right]
            second_before = second_pos[left] < second_pos[right]
            discordant += first_before != second_before
    order_distance = discordant / max(1, comparisons)
    return 0.5 * membership_distance + 0.5 * order_distance


class StructureAwareBeamSearch:
    def __init__(
        self,
        problem: Problem,
        config: BeamConfig,
        model: Optional[StructureAwareActorCritic] = None,
        *,
        device: str | torch.device = "cpu",
        seed: int = 1,
    ):
        self.problem = problem
        self.config = config
        self.model = model
        self.device = torch.device(device)
        self.seed = seed

    def _heuristic_log_probs(self, env: StructureAwareSchedulingEnv) -> np.ndarray:
        observation = env.observation()
        scores = np.full(observation.action_mask.size, -np.inf, dtype=np.float64)
        for action in np.flatnonzero(observation.action_mask.reshape(-1)):
            trial = env.clone()
            _, _, _, _ = trial.step(int(action))
            estimate = estimate_plan(self.problem, trial.plan)
            scores[action] = -(
                estimate.makespan_lower_bound + 0.15 * estimate.imbalance
            )
        finite = np.isfinite(scores)
        if not finite.any():
            return scores
        max_score = scores[finite].max()
        exp_scores = np.exp(scores[finite] - max_score)
        log_normalizer = max_score + math.log(exp_scores.sum())
        scores[finite] -= log_normalizer
        return scores

    def _log_probs(self, env: StructureAwareSchedulingEnv) -> np.ndarray:
        if self.model is None:
            return self._heuristic_log_probs(env)
        self.model.eval()
        observation = env.observation()
        with torch.no_grad():
            values = self.model.action_log_probs(observation, device=self.device)
        result = values.numpy().astype(np.float64)
        # ``masked_fill(finfo.min)`` remains finite, so an explicit -inf is
        # required before ``np.isfinite`` selects Beam expansions.
        result[~observation.action_mask.reshape(-1)] = -np.inf
        return result

    def _node_score(self, env: StructureAwareSchedulingEnv, log_probability: float) -> float:
        estimate = estimate_plan(self.problem, env.plan)
        return (
            self.config.policy_weight * log_probability
            - self.config.lower_bound_weight * estimate.makespan_lower_bound
            - self.config.imbalance_weight * estimate.imbalance
        )

    def search(self) -> List[Plan]:
        root_env = StructureAwareSchedulingEnv(self.problem, seed=self.seed)
        root_env.reset()
        beam = [BeamNode(root_env, 0.0, 0.0)]
        completed: List[BeamNode] = []
        while beam:
            expanded: List[BeamNode] = []
            for node in beam:
                if node.env.done:
                    completed.append(node)
                    continue
                log_probs = self._log_probs(node.env)
                valid = np.flatnonzero(np.isfinite(log_probs))
                if not len(valid):
                    continue
                top_actions = valid[
                    np.argsort(log_probs[valid])[-self.config.expand_per_node :][::-1]
                ]
                for action in top_actions:
                    child = node.env.clone()
                    child.step(int(action))
                    cumulative = node.log_probability + float(log_probs[action])
                    expanded.append(
                        BeamNode(
                            env=child,
                            log_probability=cumulative,
                            rank_score=self._node_score(child, cumulative),
                        )
                    )
            if not expanded:
                break
            unique = {}
            for node in sorted(expanded, key=lambda item: item.rank_score, reverse=True):
                unique.setdefault(node.env.signature(), node)
            chosen: List[BeamNode] = []
            for node in unique.values():
                diversity = 0.0
                if chosen:
                    diversity = min(
                        _diversity_distance(node.env.plan, other.env.plan)
                        for other in chosen
                    )
                node.rank_score += self.config.diversity_weight * diversity
                chosen.append(node)
                chosen.sort(key=lambda item: item.rank_score, reverse=True)
                chosen = chosen[: self.config.width]
            beam = chosen
            if all(node.env.done for node in beam):
                completed.extend(beam)
                break
        plans: List[Plan] = []
        seen = set()
        for node in sorted(completed, key=lambda item: item.rank_score, reverse=True):
            signature = node.env.signature()
            if signature in seen:
                continue
            seen.add(signature)
            plan = node.env.plan.clone()
            plan.source = "a3c_beam" if self.model is not None else "heuristic_beam"
            plan.metadata.update(
                {
                    "beam_log_probability": node.log_probability,
                    "beam_rank_score": node.rank_score,
                }
            )
            plans.append(plan)
            if len(plans) >= self.config.candidates_for_cpsat:
                break
        return plans


def merge_plan_candidates(
    initial_plan: Plan,
    beam_plans: Sequence[Plan],
    maximum: int,
) -> List[Plan]:
    candidates = [initial_plan.clone(), *(plan.clone() for plan in beam_plans)]
    result: List[Plan] = []
    signatures = set()
    for plan in candidates:
        signature = _assignment_signature(plan)
        if signature in signatures:
            continue
        signatures.add(signature)
        result.append(plan)
        if len(result) >= maximum:
            break
    return result

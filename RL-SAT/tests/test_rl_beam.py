from __future__ import annotations

import torch

from rl_sat.beam_search import StructureAwareBeamSearch
from rl_sat.config import BeamConfig, ToolConfig
from rl_sat.domain import build_problem
from rl_sat.environment import StructureAwareSchedulingEnv
from rl_sat.model import StructureAwareActorCritic


def _problem():
    return build_problem(
        ToolConfig(
            process_mode="mixed",
            mode_4x1_wafers=8,
            mode_2x2_wafers=8,
            cleaning_interval=5,
        )
    )


def test_actor_masks_every_noncanonical_action():
    problem = _problem()
    env = StructureAwareSchedulingEnv(problem)
    observation = env.reset()
    model = StructureAwareActorCritic(hidden_dim=16)
    tensors = observation.as_torch()
    logits, value = model(**tensors)
    assert logits.shape == (len(problem.units) * 2,)
    assert value.ndim == 0
    valid = torch.as_tensor(observation.action_mask.reshape(-1))
    assert torch.isfinite(logits[valid]).all()
    assert (logits[~valid] < -1e20).all()


def test_beam_changes_dispatch_hints_not_assignments():
    problem = _problem()
    beam = StructureAwareBeamSearch(
        problem,
        BeamConfig(
            width=4,
            expand_per_node=2,
            candidates_for_cpsat=4,
        ),
        model=None,
        seed=3,
    )
    plans = beam.search()
    assert plans
    reference = plans[0].chamber_units
    signatures = set()
    for plan in plans:
        plan.validate(problem)
        assert plan.chamber_units == reference
        signature = tuple(plan.metadata["dispatch_order"])
        assert set(signature) == set(problem.units)
        signatures.add(signature)
    assert len(signatures) == len(plans)


def test_dynamic_beam_preserves_distinct_chamber_assignments():
    problem = build_problem(
        ToolConfig(
            process_mode="mixed",
            mode_4x1_wafers=5,
            mode_2x2_wafers=3,
            cleaning_interval=2,
            allow_dynamic_chamber_assignment=True,
        )
    )
    beam = StructureAwareBeamSearch(
        problem,
        BeamConfig(
            width=8,
            expand_per_node=2,
            candidates_for_cpsat=8,
        ),
        model=None,
        seed=3,
    )
    plans = beam.search()

    assert len(plans) > 1
    assignments = set()
    for plan in plans:
        plan.validate(problem)
        assignments.add(tuple(sorted(plan.unit_to_chamber().items())))
    assert len(assignments) > 1
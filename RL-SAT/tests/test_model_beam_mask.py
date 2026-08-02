from __future__ import annotations

from rl_sat.beam_search import StructureAwareBeamSearch
from rl_sat.config import BeamConfig, ToolConfig
from rl_sat.domain import build_problem
from rl_sat.model import StructureAwareActorCritic


def test_neural_beam_never_expands_masked_noncanonical_action():
    problem = build_problem(
        ToolConfig(
            process_mode="mixed",
            mode_4x1_wafers=8,
            mode_2x2_wafers=8,
        )
    )
    plans = StructureAwareBeamSearch(
        problem,
        BeamConfig(width=4, expand_per_node=2, candidates_for_cpsat=4),
        StructureAwareActorCritic(hidden_dim=16),
        seed=5,
    ).search()
    assert plans
    for plan in plans:
        plan.validate(problem)

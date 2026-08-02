from __future__ import annotations

import numpy as np
import pytest

from rl_sat.config import MIX_MODE, ToolConfig, to_ticks
from rl_sat.domain import Plan, build_problem
from rl_sat.environment import StructureAwareSchedulingEnv
from rl_sat.initial_solution import InitialPlanGenerator, estimate_plan


def _problem():
    tool = ToolConfig(
        process_mode="mixed",
        mode_4x1_wafers=8,
        mode_2x2_wafers=6,
        cleaning_interval=5,
    )
    return build_problem(tool)


def test_pair_and_chamber_layout_matches_project_canonical_order():
    problem = _problem()
    assert problem.units["FB1"].pair_ids == ("F1", "F2")
    assert problem.units["FB1"].canonical_chamber == 2
    assert problem.units["FB1"].canonical_position == 1
    assert problem.units["FB2"].pair_ids == ("F3", "F4")
    assert problem.units["FB2"].canonical_chamber == 3
    assert problem.units["MU1"].canonical_chamber == 2
    assert problem.units["MU1"].canonical_position == 1
    assert problem.units["MU2"].canonical_chamber == 3
    assert problem.units["MU3"].canonical_chamber == 2
    assert problem.units["MU3"].process_cycles == 2


def test_initial_solution_and_rl_only_interleave_fixed_queues():
    problem = _problem()
    initial = InitialPlanGenerator(problem).generate()
    initial.validate(problem)
    assert initial.chamber_units == {
        2: ["FB1", "MU1", "MU3"],
        3: ["FB2", "MU2"],
    }
    assert set(initial.metadata["dispatch_order"]) == set(problem.units)

    env = StructureAwareSchedulingEnv(problem, seed=7)
    observation = env.reset()
    while not env.done:
        valid = np.flatnonzero(observation.action_mask.reshape(-1))
        assert 1 <= len(valid) <= 2
        observation, _, _, _ = env.step(int(valid[-1]))
    env.plan.validate(problem)
    assert env.plan.chamber_units == initial.chamber_units
    assert env.plan.metadata["dispatch_order"] == list(env.signature())


def test_plan_rejects_noncanonical_chamber():
    problem = _problem()
    invalid = Plan(
        chamber_units={2: ["FB2"], 3: ["FB1"]},
        source="negative-test",
    )
    with pytest.raises(ValueError, match="canonical"):
        invalid.validate(problem, complete=False)


def test_dynamic_initial_solution_balances_chambers_and_avoids_cleaning():
    tool = ToolConfig(
        process_mode="mixed",
        mode_4x1_wafers=10,
        mode_2x2_wafers=10,
        cleaning_interval=5,
        cleaning_process_time=500.0,
        allow_dynamic_chamber_assignment=True,
    )
    problem = build_problem(tool)
    plan = InitialPlanGenerator(problem).generate()
    plan.validate(problem)
    estimate = estimate_plan(problem, plan)

    assert set(plan.unit_to_chamber()) == set(problem.units)
    assert estimate.cleaning_count == 0
    assert estimate.chamber_loads == {2: 956.0, 3: 940.0}
    assert estimate.imbalance == 16.0


def test_dynamic_environment_actions_choose_chambers():
    tool = ToolConfig(
        process_mode="mixed",
        mode_4x1_wafers=8,
        mode_2x2_wafers=6,
        cleaning_interval=5,
        allow_dynamic_chamber_assignment=True,
    )
    problem = build_problem(tool)
    left = StructureAwareSchedulingEnv(problem, seed=7)
    right = StructureAwareSchedulingEnv(problem, seed=7)
    left_obs = left.reset()
    right_obs = right.reset()

    left_actions = np.flatnonzero(left_obs.action_mask.reshape(-1))
    right_actions = np.flatnonzero(right_obs.action_mask.reshape(-1))
    assert len(left_actions) == len(right_actions) == 2
    left.step(int(left_actions[0]))
    right.step(int(right_actions[1]))
    assert left.signature() != right.signature()


def test_dynamic_plan_rejects_full_unit_after_mix():
    tool = ToolConfig(
        process_mode="mixed",
        mode_4x1_wafers=8,
        mode_2x2_wafers=2,
        allow_dynamic_chamber_assignment=True,
    )
    problem = build_problem(tool)
    invalid = Plan(
        chamber_units={2: ["MU1", "FB1"], 3: ["FB2"]},
        source="negative-test",
    )
    with pytest.raises(ValueError, match="4x1 units before 2x2"):
        invalid.validate(problem)

@pytest.mark.parametrize(
    ("full_wafers", "mix_wafers", "cleaning_interval"),
    [
        (1, 0, 0),
        (5, 0, 2),
        (20, 0, 2),
        (0, 1, 0),
        (0, 3, 3),
        (0, 10, 3),
        (1, 1, 0),
        (2, 2, 2),
        (3, 3, 5),
        (5, 7, 4),
        (10, 10, 5),
    ],
)
def test_dynamic_initial_plan_supports_all_mode_combinations(
    full_wafers, mix_wafers, cleaning_interval
):
    tool = ToolConfig(
        process_mode="mixed",
        mode_4x1_wafers=full_wafers,
        mode_2x2_wafers=mix_wafers,
        cleaning_interval=cleaning_interval,
        cleaning_process_time=37.0,
        allow_dynamic_chamber_assignment=True,
    )
    problem = build_problem(tool)
    plan = InitialPlanGenerator(problem).generate()
    plan.validate(problem)
    estimate = estimate_plan(problem, plan)

    assert set(plan.unit_to_chamber()) == set(problem.units)
    assert all(load >= 0 for load in estimate.chamber_loads.values())
    for chamber in problem.chambers:
        kinds = [problem.units[unit].kind for unit in plan.chamber_units[chamber]]
        assert kinds == sorted(kinds, key=lambda kind: kind == MIX_MODE)

def test_time_scaling_is_never_silent():
    assert to_ticks(2.5, 10, exact=True) == 25
    with pytest.raises(ValueError, match="not exactly representable"):
        to_ticks(1.25, 2, exact=True)


def test_initial_estimate_counts_full_cleaning_at_interval_boundary():
    tool = ToolConfig(
        process_mode='4x1',
        mode_4x1_wafers=20,
        mode_2x2_wafers=0,
        cleaning_interval=2,
    )
    problem = build_problem(tool)
    plan = InitialPlanGenerator(problem).generate()
    estimate = estimate_plan(problem, plan)

    full_duration = (
        4 * tool.pair_transfer_time
        + 2 * tool.pm_rotation_time_180
        + tool.full_process_time
    )
    clean_duration = (
        4 * tool.pair_transfer_time
        + 2 * tool.pm_rotation_time_180
        + tool.effective_cleaning_process_time
    )
    assert estimate.cleaning_count == 1
    assert estimate.chamber_loads[2] == 3 * full_duration + clean_duration
    assert estimate.chamber_loads[3] == 2 * full_duration

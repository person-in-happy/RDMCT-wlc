from __future__ import annotations

from collections import defaultdict

import pytest

from rl_sat.config import CPSATConfig, ToolConfig
from rl_sat.cpsat_solver import CPSATScheduler
from rl_sat.domain import build_problem
from rl_sat.initial_solution import InitialPlanGenerator
from rl_sat.petri_gantt import generate_gantt_charts_from_records
from rl_sat.result_io import result_to_dict


def _solve(full_wafers: int, mix_wafers: int, cleaning_interval: int = 5):
    tool = ToolConfig(
        process_mode="mixed",
        mode_4x1_wafers=full_wafers,
        mode_2x2_wafers=mix_wafers,
        cleaning_interval=cleaning_interval,
    )
    problem = build_problem(tool)
    plan = InitialPlanGenerator(problem).generate()
    config = CPSATConfig(
        time_scale=10,
        time_limit_seconds=5.0,
        candidate_time_limit_seconds=2.0,
        final_polish_seconds=0.0,
        num_workers=2,
        random_seed=3,
        lexicographic_stability=False,
    )
    result = CPSATScheduler(problem, config).solve(
        plan,
        time_limit_seconds=5.0,
        lexicographic_stability=False,
    )
    return problem, result


def _solve_dynamic(
    full_wafers: int,
    mix_wafers: int,
    cleaning_interval: int = 5,
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
    config = CPSATConfig(
        time_scale=10,
        time_limit_seconds=10.0,
        candidate_time_limit_seconds=5.0,
        final_polish_seconds=0.0,
        num_workers=2,
        random_seed=3,
        lexicographic_stability=False,
    )
    result = CPSATScheduler(problem, config).solve(
        plan,
        time_limit_seconds=10.0,
        lexicographic_stability=False,
    )
    return problem, plan, result

def _assert_no_overlap(tasks, resource, *, equipment_only=False):
    selected = [
        task
        for task in tasks
        if task.resource == resource
        and (not equipment_only or task.task_type == "equipment_action")
    ]
    selected.sort(key=lambda task: (task.start, task.end, task.task_id))
    for left, right in zip(selected, selected[1:]):
        assert left.end <= right.start + 1e-9, (
            resource,
            left.task_id,
            right.task_id,
        )


@pytest.mark.parametrize(
    ("full_wafers", "mix_wafers"),
    [
        (2, 0),
        (5, 0),
        (0, 2),
        (0, 3),
        (3, 3),
    ],
)
def test_small_mode_and_odd_tail_matrix(full_wafers, mix_wafers):
    problem, result = _solve(full_wafers, mix_wafers)
    assert result.feasible, result.message
    assert result.scip_used is False
    assert result.objective_cmax == max(result.wafer_completion.values())
    assert set(result.wafer_completion) == set(problem.product_wafer_ids)
    assert result.best_bound <= result.objective_cmax + 1e-9

    stages = defaultdict(set)
    for task in result.tasks:
        assert 0 <= task.start <= task.end <= result.objective_cmax + 1e-9
        for wafer_id in task.wafer_ids:
            stages[wafer_id].add(task.stage)
    required = {
        "atr_lp_al",
        "al",
        "atr_al_llupper",
        "llupper",
        "vtr_load",
        "pm",
        "vtr_unload",
        "lllower",
        "atr_lllower_lp",
    }
    for wafer_id in problem.product_wafer_ids:
        assert required <= stages[wafer_id]

    _assert_no_overlap(result.tasks, "ATR")
    _assert_no_overlap(result.tasks, "AL")
    _assert_no_overlap(result.tasks, "VTR", equipment_only=True)
    _assert_no_overlap(result.tasks, "CH2", equipment_only=True)
    _assert_no_overlap(result.tasks, "CH3", equipment_only=True)


def test_cleaning_splits_long_2x2_chain_at_exposure_boundary():
    problem, result = _solve(0, 10, cleaning_interval=3)
    assert result.feasible, result.message
    clean_tasks = [
        task
        for task in result.tasks
        if task.stage == "cleaning" and task.task_type == "equipment_action"
    ]
    assert clean_tasks
    for chamber in problem.chambers:
        pair_count = len(
            [
                unit
                for unit in problem.canonical_queue(chamber)
                if problem.units[unit].kind == "2x2"
            ]
        )
        segments = 1 if pair_count <= 2 else 2
        exposures = [
            task
            for task in result.tasks
            if task.chamber == chamber and task.stage == "mix_exposure"
        ]
        assert len(exposures) == pair_count + segments


def test_dynamic_chamber_assignment_improves_mixed_cleaning_instance():
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
    config = CPSATConfig(
        time_scale=10,
        time_limit_seconds=10.0,
        candidate_time_limit_seconds=10.0,
        final_polish_seconds=0.0,
        num_workers=2,
        random_seed=3,
        lexicographic_stability=False,
    )
    result = CPSATScheduler(problem, config).solve(
        plan,
        time_limit_seconds=10.0,
        lexicographic_stability=False,
    )

    assert result.feasible, result.message
    assert result.objective_cmax < 2130.0
    assert result.metadata["actual_wph"] == pytest.approx(
        len(problem.product_wafer_ids) * 3600.0 / result.objective_cmax
    )
    assert result.metadata["actual_wph"] > 20 * 3600.0 / 2130.0
    assert result.metadata["stability_objective"]["unit"] == "seconds_squared"
    assert result.metadata["stability_objective"]["chamber_idle_seconds"].keys() == {
        "2",
        "3",
    }


@pytest.mark.parametrize(
    ("full_wafers", "mix_wafers", "cleaning_interval"),
    [
        (1, 0, 0),
        (5, 0, 2),
        (9, 0, 1),
        (0, 1, 0),
        (0, 3, 3),
        (0, 10, 3),
        (1, 1, 0),
        (2, 2, 2),
        (3, 3, 5),
    ],
)
def test_dynamic_solver_supports_general_input_matrix(
    full_wafers,
    mix_wafers,
    cleaning_interval,
):
    problem, plan, result = _solve_dynamic(
        full_wafers,
        mix_wafers,
        cleaning_interval,
    )

    plan.validate(problem)
    assert result.feasible, result.message
    assert result.scip_used is False
    assert set(plan.unit_to_chamber()) == set(problem.units)
    assert set(result.wafer_completion) == set(problem.product_wafer_ids)
    assert result.objective_cmax == max(result.wafer_completion.values())
    assert result.certificate_scope == (
        "dynamic_chamber_assignment_cp_sat_abstraction"
    )

    for task in result.tasks:
        assert 0 <= task.start <= task.end <= result.objective_cmax + 1e-9
    _assert_no_overlap(result.tasks, "ATR")
    _assert_no_overlap(result.tasks, "AL")
    _assert_no_overlap(result.tasks, "VTR", equipment_only=True)
    _assert_no_overlap(result.tasks, "CH2", equipment_only=True)
    _assert_no_overlap(result.tasks, "CH3", equipment_only=True)


@pytest.mark.parametrize(
    ("full_wafers", "mix_wafers", "cleaning_interval"),
    [
        (1, 0, 0),
        (0, 1, 0),
        (1, 1, 0),
    ],
)
def test_dynamic_tail_combinations_render_continuous_compatible_gantt(
    full_wafers,
    mix_wafers,
    cleaning_interval,
    tmp_path,
):
    _, _, result = _solve_dynamic(
        full_wafers,
        mix_wafers,
        cleaning_interval,
    )
    assert result.feasible, result.message

    outputs = generate_gantt_charts_from_records(
        [result_to_dict(result)],
        str(tmp_path / f"gantt-{full_wafers}-{mix_wafers}"),
        view="all",
    )
    names = {path.replace("\\", "/").rsplit("/", 1)[-1] for path in outputs}
    assert "index.html" in names
    assert "manifest.json" in names
    assert any(name.endswith("_gantt.svg") for name in names)


def test_legacy_assignment_map_is_canonical():
    problem, result = _solve(4, 4)
    assert result.feasible, result.message
    legacy = result.metadata["legacy_solution"]
    for pair in problem.pairs.values():
        if pair.mode == "4x1":
            key = (
                f"assign_full_{pair.mode_index}_{pair.canonical_chamber}_"
                f"{pair.canonical_batch}_{pair.canonical_side}"
            )
        else:
            key = (
                f"assign_mix_{pair.mode_index}_{pair.canonical_chamber}_"
                f"{pair.canonical_position}"
            )
        assert legacy[key] == 1.0

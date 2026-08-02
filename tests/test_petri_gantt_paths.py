import json

import pytest

import petri_gantt


def _assert_lane_is_continuous(schedule, lane_prefix):
    lane = next(name for name in schedule["lanes"] if name.startswith(lane_prefix))
    tasks = sorted(
        (task for task in schedule["tasks"] if task["lane"] == lane),
        key=lambda task: (task["start"], task["end"]),
    )
    assert tasks
    for previous, current in zip(tasks, tasks[1:]):
        assert current["start"] == previous["end"]
    return lane, tasks


def _base_product_solution():
    solution = {
        "c_max": 100.0,
        "wafer_to_full_pair_1_1": 1.0,
        "wafer_to_full_pair_2_1": 1.0,
        "assign_full_1_2_1_1": 1.0,
    }
    stages = {
        1: {
            "atr_lp_al": (0.0, 10.0),
            "al": (10.0, 20.0),
            "atr_hold_after_al": (24.0, 34.0),
            "atr_al_llupper": (34.0, 44.0),
            "llupper": (44.0, 54.0),
            "vtr_load": (54.0, 58.0),
            "pm": (58.0, 78.0),
            "vtr_unload": (78.0, 82.0),
            "lllower": (82.0, 90.0),
            "atr_lllower_lp": (90.0, 100.0),
        },
        2: {
            "atr_lp_al": (0.0, 10.0),
            "atr_hold_before_al": (10.0, 20.0),
            "atr_al_exchange": (20.0, 24.0),
            "al": (24.0, 34.0),
            "atr_al_llupper": (34.0, 44.0),
            "llupper": (44.0, 54.0),
            "vtr_load": (54.0, 58.0),
            "pm": (58.0, 78.0),
            "vtr_unload": (78.0, 82.0),
            "lllower": (82.0, 90.0),
            "atr_lllower_lp": (90.0, 100.0),
        },
    }
    for wafer_id, wafer_stages in stages.items():
        for stage_name, (start, end) in wafer_stages.items():
            solution[f"prod_stage_start_{wafer_id}_{stage_name}"] = start
            solution[f"prod_stage_end_{wafer_id}_{stage_name}"] = end
    return solution


def test_shared_al_exchange_is_projected_to_both_product_wafers():
    schedule = petri_gantt._collect_path_schedule(_base_product_solution())

    _, first_tasks = _assert_lane_is_continuous(schedule, "Product W1 ")
    _assert_lane_is_continuous(schedule, "Product W2 ")

    projected = [
        task
        for task in first_tasks
        if task["label"].startswith("ATR holding calibrated wafer during AL exchange")
    ]
    assert [(task["start"], task["end"]) for task in projected] == [(20.0, 24.0)]


def test_reused_pec_token_has_one_continuous_physical_lane():
    solution = _base_product_solution()
    for job_id, times in {
        5: ((5.0, 9.0), (9.0, 19.0), (19.0, 23.0)),
        25: ((40.0, 44.0), (44.0, 54.0), (54.0, 58.0)),
    }.items():
        solution[f"pec_token_assign_{job_id}_1"] = 1.0
        for stage_name, (start, end) in zip(("vtr_load", "pm", "vtr_unload"), times):
            solution[f"pec_stage_start_{job_id}_{stage_name}"] = start
            solution[f"pec_stage_end_{job_id}_{stage_name}"] = end

    schedule = petri_gantt._collect_path_schedule(solution)
    pec_lanes = [lane for lane in schedule["lanes"] if lane.startswith("PEC ")]

    assert pec_lanes == ["PEC P1 | jobs E5,E25"]
    _, tasks = _assert_lane_is_continuous(schedule, "PEC P1 ")
    storage_waits = [task for task in tasks if task["label"].startswith("PEC storage wait")]
    assert [(task["start"], task["end"]) for task in storage_waits] == [(23.0, 40.0)]


def test_anonymous_pec_tokens_use_round_robin_and_wrap_after_pool_size():
    solution = _base_product_solution()
    solution["_gantt_pec_pool_size"] = 8
    for job_id in range(1, 10):
        start = float(job_id * 10)
        # Deliberately give every job the same legacy token assignment; the
        # display allocator must ignore identity and use PEC1..PEC8, then PEC1.
        solution[f"pec_token_assign_{job_id}_1"] = 1.0
        stages = {
            "vtr_load": (start, start + 2.0),
            "pm": (start + 1.9995, start + 6.0),
            "vtr_unload": (start + 6.0, start + 8.0),
        }
        for stage_name, (stage_start, stage_end) in stages.items():
            solution[f"pec_stage_start_{job_id}_{stage_name}"] = stage_start
            solution[f"pec_stage_end_{job_id}_{stage_name}"] = stage_end

    schedule = petri_gantt._collect_path_schedule(solution)
    pec_lanes = [lane for lane in schedule["lanes"] if lane.startswith("PEC ")]

    assert [lane.split(" |", 1)[0] for lane in pec_lanes] == [
        f"PEC P{token_id}" for token_id in range(1, 9)
    ]
    assert pec_lanes[0] == "PEC P1 | jobs E1,E9"
    _assert_lane_is_continuous(schedule, "PEC P1 ")


def test_mix_product_cycles_are_selected_by_pm_window_across_epoch_reset():
    solution = _base_product_solution()
    for key in (
        "wafer_to_full_pair_1_1",
        "wafer_to_full_pair_2_1",
        "assign_full_1_2_1_1",
    ):
        solution.pop(key)
    solution.update(
        {
            "wafer_to_mix_pair_1_5": 1.0,
            "wafer_to_mix_pair_2_5": 1.0,
            "assign_mix_5_2_3": 1.0,
            # Position 3 belongs to a later cleaning epoch. Its physical
            # process window is cycles 4/5, not position 3 plus cycle 4.
            "mix_cycle_start_2_3": 30.0,
            "mix_cycle_end_2_3": 40.0,
            "mix_cycle_start_2_4": 58.0,
            "mix_cycle_end_2_4": 68.0,
            "mix_cycle_start_2_5": 70.0,
            "mix_cycle_end_2_5": 78.0,
        }
    )

    schedule = petri_gantt._collect_path_schedule(solution)
    lane = next(name for name in schedule["lanes"] if name.startswith("Product W1 "))
    pm_tasks = sorted(
        (
            task
            for task in schedule["tasks"]
            if task["lane"] == lane
            and (
                task["label"].startswith("2x2 PM process")
                or task["label"].startswith("2x2 in-chamber")
            )
        ),
        key=lambda task: task["start"],
    )

    assert [(task["start"], task["end"]) for task in pm_tasks] == [
        (58.0, 68.0),
        (68.0, 70.0),
        (70.0, 78.0),
    ]
    _assert_lane_is_continuous(schedule, "Product W1 ")

def test_lane_validator_rejects_source_overlap():
    tasks = [
        {"lane": "PEC P1", "start": 0.0, "end": 5.0, "label": "first"},
        {"lane": "PEC P1", "start": 4.0, "end": 8.0, "label": "second"},
    ]

    with pytest.raises(ValueError, match="overlapping interval"):
        petri_gantt._validate_continuous_entity_lanes(["PEC P1"], tasks)


def test_interactive_frontend_lists_every_ablation_metric(tmp_path):
    comparison = tmp_path / "comparison.svg"
    gap = tmp_path / "case_gap.svg"
    pdi = tmp_path / "case_pdi.svg"
    for path in (comparison, gap, pdi):
        path.write_text("<svg xmlns=\"http://www.w3.org/2000/svg\"/>", encoding="utf-8")

    output_dir = tmp_path / "gantt"
    generated = petri_gantt.generate_gantt_charts_from_records(
        [],
        str(output_dir),
        comparison_svg=str(comparison),
        metric_svgs=[str(gap), str(pdi)],
    )

    manifest = json.loads(
        (output_dir / "manifest.json").read_text(encoding="utf-8")
    )
    html = (output_dir / "index.html").read_text(encoding="utf-8")
    assert len(generated) == 2
    assert [entry["name"] for entry in manifest["metric_svgs"]] == ["gap", "pdi"]
    assert "Ablation Metrics" in html
    assert "case_gap.svg" in html
    assert "case_pdi.svg" in html

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


def test_reused_pec_token_hides_storage_and_chamber_waits():
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
    tasks = sorted(
        (task for task in schedule["tasks"] if task["lane"] == pec_lanes[0]),
        key=lambda task: (task["start"], task["end"]),
    )
    assert not any("wait" in task["label"].lower() for task in tasks)
    assert [(task["start"], task["end"]) for task in tasks] == [
        (5.0, 9.0),
        (9.0, 19.0),
        (19.0, 23.0),
        (40.0, 44.0),
        (44.0, 54.0),
        (54.0, 58.0),
    ]


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
    assert not any(
        "wait" in task["label"].lower()
        for task in schedule["tasks"]
        if task["lane"].startswith("PEC ")
    )


def test_sparse_split_bridge_solution_renders_early_unload_and_later_load():
    solution = {
        "c_max": 238.0,
        "mix_active_2": 1.0,
        "mix_pos_used_2_1": 1.0,
        "mix_last_pos_2_1": 1.0,
        "assign_mix_1_2_1": 1.0,
        "wafer_to_mix_pair_1_1": 1.0,
        "wafer_to_mix_pair_2_1": 1.0,
        "mix_head_start_2": 10.0,
        "mix_head_end_2": 14.0,
        "mix_cycle_used_2_1": 1.0,
        "mix_cycle_start_2_1": 14.0,
        "mix_cycle_end_2_1": 104.0,
        "mix_cycle_used_2_2": 1.0,
        "mix_bridge_start_2_2": 104.0,
        "mix_bridge_unload_end_2_2": 108.0,
        # SCIP sparse .sol output omits mix_bridge_combined_2_2=0.
        "mix_bridge_load_start_2_2": 140.0,
        "mix_bridge_end_2_2": 144.0,
        "mix_cycle_start_2_2": 144.0,
        "mix_cycle_end_2_2": 234.0,
        "mix_tail_start_2": 234.0,
        "mix_tail_end_2": 238.0,
    }

    schedule = petri_gantt._collect_chamber_schedule(solution)
    tasks = [task for task in schedule["tasks"] if task["lane"].startswith("CH2 ")]

    assert any(
        task["label"].startswith("2x2 early unload")
        and (task["start"], task["end"]) == (104.0, 108.0)
        for task in tasks
    )
    assert any(
        task["label"].startswith("2x2 chamber vacant")
        and (task["start"], task["end"]) == (108.0, 140.0)
        for task in tasks
    )
    assert any(
        task["label"].startswith("2x2 later load")
        and (task["start"], task["end"]) == (140.0, 144.0)
        for task in tasks
    )

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


def test_resource_chamber_wait_merges_contiguous_occupancy_changes():
    solution = {'c_max': 102.0}
    for wafer_id, pair_id in ((1, 1), (2, 1), (3, 2), (4, 2)):
        solution[f'wafer_to_full_pair_{wafer_id}_{pair_id}'] = 1.0
        for stage_name, (start, end) in {
            'vtr_load': (54.0, 58.0),
            'pm': (58.0, 78.0),
            'vtr_unload': (88.0, 92.0) if pair_id == 1 else (98.0, 102.0),
        }.items():
            solution[f'prod_stage_start_{wafer_id}_{stage_name}'] = start
            solution[f'prod_stage_end_{wafer_id}_{stage_name}'] = end
    solution['assign_full_1_2_1_1'] = 1.0
    solution['assign_full_2_2_1_2'] = 1.0

    schedule = petri_gantt._collect_resource_schedule(solution)
    waits = [
        task
        for task in schedule['tasks']
        if task['lane'] == 'CH2 PM'
        and task['label'].startswith('CH wait for VTR unload')
    ]

    assert [(task['start'], task['end']) for task in waits] == [(78.0, 98.0)]
    assert '78.000-88.000: W1, W2, W3, W4' in waits[0]['label']
    assert '88.000-98.000: W3, W4' in waits[0]['label']

def test_cleaning_hides_waits_and_uses_teal_in_path_view():
    solution = _base_product_solution()
    solution.update(
        {
            "clean_active_3_1": 1.0,
            "clean_front_load_start_3_1": 40.0,
            "clean_start_3_1": 44.0,
            "clean_end_3_1": 54.0,
            "clean_front_unload_end_3_1": 58.0,
            "pec_token_assign_25_1": 1.0,
            "pec_stage_start_25_vtr_load": 40.0,
            "pec_stage_end_25_vtr_load": 44.0,
            "pec_stage_start_25_pm": 44.0,
            "pec_stage_end_25_pm": 54.0,
            "pec_stage_start_25_vtr_unload": 54.0,
            "pec_stage_end_25_vtr_unload": 58.0,
        }
    )

    schedule = petri_gantt._collect_path_schedule(solution)
    cleaning = [
        task for task in schedule["tasks"]
        if task["label"].startswith("CH cleaning")
    ]

    assert [(task["start"], task["end"], task["color"]) for task in cleaning] == [
        (44.0, 54.0, petri_gantt.CLEAN_COLOR)
    ]
    assert petri_gantt.CLEAN_COLOR != "#E45756"
    assert not any(
        "wait" in task["label"].lower()
        and task["start"] < 58.0
        and task["end"] > 40.0
        for task in schedule["tasks"]
    )
    assert not any(
        "wait" in task["label"].lower()
        for task in schedule["tasks"]
        if task["lane"].startswith("PEC ")
    )


def test_resource_cleaning_clips_other_module_waits_and_has_no_red_pec_overlay():
    solution = _base_product_solution()
    for wafer_id in (1, 2):
        solution[f"prod_stage_start_{wafer_id}_vtr_unload"] = 98.0
        solution[f"prod_stage_end_{wafer_id}_vtr_unload"] = 102.0
    solution.update(
        {
            "clean_front_load_start_3_1": 80.0,
            "clean_start_3_1": 82.0,
            "clean_end_3_1": 86.0,
            "clean_front_unload_end_3_1": 88.0,
            "pec_job_chamber_90_3": 1.0,
            "pec_token_assign_90_1": 1.0,
            "pec_stage_start_90_vtr_load": 80.0,
            "pec_stage_end_90_vtr_load": 82.0,
            "pec_stage_start_90_pm": 82.0,
            "pec_stage_end_90_pm": 86.0,
            "pec_stage_start_90_vtr_unload": 86.0,
            "pec_stage_end_90_vtr_unload": 88.0,
        }
    )

    schedule = petri_gantt._collect_resource_schedule(solution)
    cleaning = [
        task for task in schedule["tasks"]
        if task["label"].startswith("CH cleaning 1")
    ]
    waits = [
        task for task in schedule["tasks"]
        if "wait" in task["label"].lower()
    ]

    assert [(task["lane"], task["start"], task["end"], task["color"]) for task in cleaning] == [
        ("CH3 PM", 80.0, 88.0, petri_gantt.CLEAN_COLOR)
    ]
    assert not any(task["start"] < 88.0 and task["end"] > 80.0 for task in waits)
    assert not any(
        task["label"].startswith("PEC chamber support")
        and task["start"] < 88.0
        and task["end"] > 80.0
        for task in schedule["tasks"]
    )
    assert not any(
        "wait" in task["label"].lower()
        and ("PEC" in task["label"] or "\nE" in task["label"])
        for task in schedule["tasks"]
    )


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


@pytest.mark.parametrize("combined,start,unload_end,load_start,end,expected_wait", [
    (1, 159, 163, 159, 163, 59),
    (0, 100, 104, 159, 163, 55),
])
def test_exchange_projection_does_not_color_idle_as_exchange(
    combined, start, unload_end, load_start, end, expected_wait
):
    solution = {
        "mix_bridge_combined_2_2": combined,
        "mix_bridge_start_2_2": start,
        "mix_bridge_unload_end_2_2": unload_end,
        "mix_bridge_load_start_2_2": load_start,
        "mix_bridge_end_2_2": end,
    }
    segments = list(petri_gantt._mix_exchange_segments(solution, 2, 2, 100, 163))
    assert segments[0][0] == 100 and segments[-1][1] == 163
    assert all(a[1] == b[0] for a, b in zip(segments, segments[1:]))
    exchanges = [b-a for a, b, _, color in segments if color == "#BAB0AC"]
    assert exchanges and all(duration == 4 for duration in exchanges)
    assert sum(b-a for a, b, _, color in segments if color == "#F2A09A") == expected_wait


def test_resource_cycles_follow_wafer_windows_across_cleaning():
    """A second chain starts at cycle 4 although its first PW is position 3."""
    solution = _base_product_solution()
    for k in list(solution):
        if k.startswith(('wafer_to_full_pair_', 'assign_full_')):
            del solution[k]
    solution.update({
        'wafer_to_mix_pair_1_5': 1, 'wafer_to_mix_pair_2_5': 1,
        'assign_mix_5_2_3': 1,
        'mix_cycle_start_2_3': 292, 'mix_cycle_end_2_3': 382,
        'mix_cycle_start_2_4': 922, 'mix_cycle_end_2_4': 1012,
        'mix_cycle_start_2_5': 1016, 'mix_cycle_end_2_5': 1106,
        'mix_bridge_start_2_5': 1012, 'mix_bridge_end_2_5': 1016,
        'mix_bridge_combined_2_5': 1, 'c_max': 1200,
    })
    for wafer in (1, 2):
        solution[f'prod_stage_end_{wafer}_vtr_load'] = 922
        solution[f'prod_stage_start_{wafer}_pm'] = 922
        solution[f'prod_stage_end_{wafer}_pm'] = 1106
        solution[f'prod_stage_start_{wafer}_vtr_unload'] = 1106
        solution[f'prod_stage_end_{wafer}_vtr_unload'] = 1110
    schedule = petri_gantt._collect_schedule(solution, 'resources')
    process = [t for t in schedule['tasks'] if t['lane'] == 'CH2 PM' and '2x2 PM process' in t['label']]
    assert [(t['start'],t['end']) for t in process] == [(922,1012),(1016,1106)]
    assert not any(t['lane']=='CH2 PM' and 'wait' in t['label'].lower()
                   and t['start'] < 1106 and t['end'] > 1016 for t in schedule['tasks'])

from __future__ import annotations

import json

from rl_sat.petri_gantt import (
    _adapt_rl_sat_solution,
    generate_gantt_charts_from_records,
)


def _stage(solution, wafer, stage, start, end):
    solution[f"prod_stage_start_{wafer}_{stage}"] = start
    solution[f"prod_stage_end_{wafer}_{stage}"] = end


def _record():
    solution = {
        "c_max": 190.0,
        "full_batch_used_2_1": 1.0,
        "assign_full_1_2_1_1": 1.0,
        "wafer_to_full_pair_1_1": 1.0,
        "wafer_to_full_pair_2_1": 1.0,
        "mix_cycle_start_2_1": 1040.0,
        "mix_cycle_end_2_1": 1500.0,
        "full_start_2_1": 1040.0,
        "full_end_2_1": 1500.0,
    }
    common = {
        "atr_lp_al": (0.0, 11.0),
        "atr_al_exchange": (31.0, 39.0),
        "atr_al_llupper": (59.0, 70.0),
        "llupper": (70.0, 100.0),
        "vtr_load": (100.0, 104.0),
        "pm": (104.0, 150.0),
        "vtr_unload": (150.0, 154.0),
        "lllower": (154.0, 179.0),
        "atr_lllower_lp": (179.0, 190.0),
    }
    for wafer in (1, 2):
        for stage, (start, end) in common.items():
            _stage(solution, wafer, stage, start, end)
    _stage(solution, 1, "al", 11.0, 31.0)
    _stage(solution, 2, "al", 39.0, 59.0)
    legacy = {
        "mix_cycle_start_2_1": 1040.0,
        "mix_cycle_end_2_1": 1500.0,
        "full_start_2_1": 1040.0,
        "full_end_2_1": 1500.0,
    }
    return {
        "schema": "rl-sat-result",
        "instance": "compat-smoke",
        "method": "initial_cp_sat",
        "status": "OPTIMAL",
        "best_obj": 190.0,
        "solution": solution,
        "tasks": [
            {
                "id": "pair_F1_atr_lp_al",
                "stage": "atr_lp_al",
                "resource": "ATR",
                "start": 0.0,
                "end": 11.0,
                "metadata": {"pair_id": "F1", "wafer_ids": [1, 2]},
            }
        ],
        "metadata": {
            "time_scale": 10,
            "legacy_solution": legacy,
            "declared_abstractions": [
                "PEC identity is symmetry-aggregated as cumulative capacity."
            ],
        },
    }


def test_rl_sat_adapter_converts_old_ticks_and_builds_pair_holds():
    record = _record()
    adapted = _adapt_rl_sat_solution(record, record["solution"])
    assert adapted["mix_cycle_start_2_1"] == 104.0
    assert adapted["mix_cycle_end_2_1"] == 150.0
    assert adapted["prod_stage_start_2_atr_hold_before_al"] == 11.0
    assert adapted["prod_stage_end_2_atr_hold_before_al"] == 31.0
    assert adapted["prod_stage_start_1_atr_hold_after_al"] == 39.0
    assert adapted["prod_stage_end_1_atr_hold_after_al"] == 59.0


def test_compatible_renderer_creates_original_three_views_and_frontend(tmp_path):
    outputs = generate_gantt_charts_from_records(
        [_record()],
        str(tmp_path / "gantt"),
        view="all",
    )
    output_names = {path.rsplit("\\", 1)[-1].rsplit("/", 1)[-1] for path in outputs}
    assert "index.html" in output_names
    assert "manifest.json" in output_names
    assert any(name.endswith("_gantt.svg") for name in output_names)
    assert any(name.endswith("_chambers_gantt.svg") for name in output_names)
    assert any(name.endswith("_resources_gantt.svg") for name in output_names)
    manifest = json.loads((tmp_path / "gantt" / "manifest.json").read_text("utf-8"))
    assert len(manifest["charts"]) == 3
    index = (tmp_path / "gantt" / "index.html").read_text("utf-8")
    assert "wheel" in index
    assert "pointerdown" in index
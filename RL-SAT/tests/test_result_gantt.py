from __future__ import annotations

import json

from rl_sat.domain import Plan, ScheduleResult, ScheduleTask
from rl_sat.gantt import render_gantt_bundle
from rl_sat.result_io import result_to_dict, write_result_json


def _result():
    tasks = [
        ScheduleTask(
            task_id="pair_in",
            name="pair input",
            resource="ATR",
            start=0.0,
            end=11.0,
            stage="atr_lp_al",
            pair_id="F1",
            wafer_ids=(1, 2),
        ),
        ScheduleTask(
            task_id="w1_al",
            name="align wafer 1",
            resource="AL",
            start=11.0,
            end=31.0,
            stage="al",
            pair_id="F1",
            wafer_ids=(1,),
        ),
        ScheduleTask(
            task_id="w2_al",
            name="align wafer 2",
            resource="AL",
            start=39.0,
            end=59.0,
            stage="al",
            pair_id="F1",
            wafer_ids=(2,),
        ),
    ]
    return ScheduleResult(
        status="OPTIMAL",
        objective_cmax=59.0,
        best_bound=59.0,
        relative_gap=0.0,
        wall_time=0.01,
        plan=Plan(chamber_units={2: [], 3: []}),
        tasks=tasks,
        wafer_completion={1: 59.0, 2: 59.0},
        pair_completion={"F1": 59.0},
        metadata={"instance": "gantt_smoke"},
    )


def test_result_keeps_old_variable_contract(tmp_path):
    payload = result_to_dict(_result())
    assert payload['primary_status'] == 'OPTIMAL'
    assert payload['stability_status'] == 'not_run'
    assert payload['nonzero_solution_vars'] == sum(
        abs(float(value)) > 1e-12 for value in payload['solution'].values()
    )
    assert payload["instance"] == "gantt_smoke"
    assert payload["solution"]["c_max"] == 59.0
    assert payload["solution"]["prod_stage_start_1_atr_lp_al"] == 0.0
    assert payload["solution"]["prod_stage_end_2_atr_lp_al"] == 11.0
    destination = write_result_json(_result(), tmp_path / "result.json")
    loaded = json.loads(destination.read_text(encoding="utf-8"))
    assert loaded["scip_used"] is False


def test_three_gantt_views_and_manifest_are_created(tmp_path):
    outputs = render_gantt_bundle(_result(), tmp_path / "gantt")
    for name in ("overview", "resource", "product"):
        assert (tmp_path / "gantt" / f"{name}.svg").is_file()
        assert "<svg" in (tmp_path / "gantt" / f"{name}.svg").read_text(
            encoding="utf-8"
        )
    assert (tmp_path / "gantt" / "manifest.json").is_file()
    assert (tmp_path / "gantt" / "index.html").is_file()
    assert outputs["charts"]["product"].endswith("product.svg")

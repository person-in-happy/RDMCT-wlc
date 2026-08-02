from types import SimpleNamespace

import numpy as np
import pytest

import cutsel_agent_parallel as cutsel
import run_ablation_experiments as ablation
from petri_mip_generator import get_petri_model_description_path


def _fair_args(**overrides):
    values = {
        "enforce_fair_ablation": "True",
        "a3c_max_candidates": 128,
        "a3c_max_selected_cuts": 30,
        "heuristic_max_candidates": 128,
        "heuristic_max_selected_cuts": 30,
        "proposed_max_candidates": 128,
        "proposed_max_selected_cuts": 30,
        "a3c_decode_type": "greedy",
        "a3c_beam_decode_type": "greedy",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_fair_ablation_rejects_budget_and_decode_confounds():
    ablation._validate_ablation_protocol(_fair_args())

    with pytest.raises(ValueError, match="Unfair cut budgets"):
        ablation._validate_ablation_protocol(
            _fair_args(heuristic_max_selected_cuts=256)
        )

    with pytest.raises(ValueError, match="different learned decode"):
        ablation._validate_ablation_protocol(
            _fair_args(a3c_beam_decode_type="beam_search")
        )


def test_project_mode_labels_are_checked():
    assert ablation._label_expected_mode("wafer17_41_20260711.lp") == "4x1"
    assert ablation._label_expected_mode("wafer17_22_20260711.lp") == "2x2"
    assert ablation._label_expected_mode("wafer17_mix_20260711.lp") is None
    assert ablation._label_expected_mode("1.1_wafer47_41") == "4x1"

    ablation._validate_mode_label("wafer17_41.lp", 17, 0, "test")
    with pytest.raises(ValueError, match="label means pure 4x1"):
        ablation._validate_mode_label("wafer17_41.lp", 0, 17, "test")


def test_duplicate_instance_content_is_not_independent_evidence(tmp_path):
    for name in ("wafer17_22_a.lp", "wafer17_22_b.lp"):
        (tmp_path / name).write_text("Minimize\n obj: x\nEnd\n", encoding="utf-8")
        description = get_petri_model_description_path(str(tmp_path), name)
        with open(description, "w", encoding="utf-8") as stream:
            stream.write("- `4x1` wafers: `0`\n- `2x2` wafers: `17`\n")

    args = SimpleNamespace(
        instance_dir=str(tmp_path),
        validate_instance_label="True",
        allow_duplicate_instances="False",
    )
    with pytest.raises(ValueError, match="Duplicate instance content"):
        ablation._build_instance_manifest(
            args,
            ["wafer17_22_a.lp", "wafer17_22_b.lp"],
        )


def test_ablation_output_label_must_match_selected_file(tmp_path):
    instance_name = "wafer47_22.lp"
    (tmp_path / instance_name).write_text("Minimize\n obj: x\nEnd\n", encoding="utf-8")
    description = get_petri_model_description_path(str(tmp_path), instance_name)
    with open(description, "w", encoding="utf-8") as stream:
        stream.write("- `4x1` wafers: `0`\n- `2x2` wafers: `47`\n")

    args = SimpleNamespace(
        instance_dir=str(tmp_path),
        instance_type="1.1_wafer47_41",
        validate_instance_label="True",
        allow_duplicate_instances="False",
    )
    with pytest.raises(ValueError, match="Ablation label/file mismatch"):
        ablation._build_instance_manifest(args, [instance_name])


def test_single_instance_warm_start_uses_selected_instance(monkeypatch, tmp_path):
    selected_solution = tmp_path / "selected_warmstart.sol"
    selected_solution.write_text("solution status: feasible\n", encoding="utf-8")
    requested_names = []

    def fake_find(output_dir, instance_name):
        requested_names.append((output_dir, instance_name))
        return str(selected_solution) if instance_name == "selected.lp" else None

    monkeypatch.setattr(ablation, "find_compatible_mixed_warm_start", fake_find)
    args = SimpleNamespace(
        warm_start_solution_file="",
        instance_dir=str(tmp_path),
        instance_name="default.lp",
        generate_petri_instance="False",
        warm_start_time_limit=180.0,
    )
    petri_cfg = SimpleNamespace(mix_wafer_ids=[])

    result = ablation._prepare_shared_warm_start(args, petri_cfg, "selected.lp")

    assert result == str(selected_solution.resolve())
    assert requested_names == [(str(tmp_path), "selected.lp")]


def test_heuristic_beam_prefilters_before_full_feature_extraction(monkeypatch):
    cuts = [object() for _ in range(4)]
    efficacy = {
        id(cuts[0]): 0.1,
        id(cuts[1]): 0.9,
        id(cuts[2]): 0.2,
        id(cuts[3]): 0.8,
    }

    class FakeModel:
        def getCutEfficacy(self, cut):
            return efficacy[id(cut)]

    extracted = []

    def fake_feature_generator(model, selected_cuts):
        extracted.append(list(selected_cuts))
        features = np.zeros((len(selected_cuts), 23), dtype=np.float32)
        features[:, 1] = [
            model.getCutEfficacy(cut)
            for cut in selected_cuts
        ]
        return features

    monkeypatch.setattr(
        cutsel,
        "advanced_cut_feature_generator",
        fake_feature_generator,
    )
    selector = cutsel.HeuristicBeamCutSelectAgent(
        FakeModel(),
        sel_cuts_percent=0.5,
        beam_size=1,
        max_candidates=2,
        max_selected_cuts=1,
    )
    result = selector._cutselselect_impl(
        cuts,
        forcedcuts=[],
        root=True,
        maxnselectedcuts=4,
    )

    assert extracted == [[cuts[1], cuts[3]]]
    assert selector.data["candidate_indices"] == [1, 3]
    assert len(selector.data["state"]) == 2
    assert sorted(map(id, result["cuts"])) == sorted(map(id, cuts))


def test_two_phase_objective_overrides_apply_to_every_method_environment():
    cfg = {"env": {"scip_time_limit": 800.0, "presolving": True}}
    args = SimpleNamespace(
        time_limit=3000.0,
        evaluation_node_limit=-1,
        evaluation_stall_node_limit=-1,
        lexicographic_schedule_stability="True",
        lexicographic_stability_time_limit=120.0,
        schedule_chamber_idle_square_penalty=1.0,
        schedule_pm_wait_square_penalty=1.0,
        schedule_module_wait_square_penalty=1.0,
        schedule_robot_wait_square_penalty=1.0,
    )

    env_kwargs = ablation._build_env_kwargs(cfg, args)

    assert env_kwargs["scip_time_limit"] == 3000.0
    assert env_kwargs["scip_node_limit"] == -1
    assert env_kwargs["scip_stall_node_limit"] == -1
    assert env_kwargs["lexicographic_schedule_stability"] is True
    assert env_kwargs["schedule_stability_mode"] == "linear"
    assert env_kwargs["lexicographic_stability_time_limit"] == 120.0


@pytest.mark.parametrize(
    ("profile", "stage_two", "mode"),
    (
        ("full", True, "linear"),
        ("stage2_off", False, "linear"),
        ("linear_off", True, "quadratic"),
    ),
)
def test_schedule_stability_profiles_change_one_factor_at_a_time(
    profile, stage_two, mode
):
    cfg = {
        "env": {
            "scip_time_limit": 600.0,
            "presolving": True,
            "lexicographic_schedule_stability": True,
            "schedule_stability_mode": "linear",
            "lexicographic_stability_time_limit": 60.0,
        }
    }
    args = SimpleNamespace(
        time_limit=-1.0,
        evaluation_node_limit=-1,
        evaluation_stall_node_limit=-1,
        stability_ablation_profile=profile,
        lexicographic_schedule_stability="",
        lexicographic_stability_time_limit=-1.0,
        schedule_chamber_idle_square_penalty=1e-5,
        schedule_pm_wait_square_penalty=1e-3,
        schedule_module_wait_square_penalty=1e-5,
        schedule_robot_wait_square_penalty=1e-5,
    )

    env_kwargs = ablation._build_env_kwargs(cfg, args)

    assert env_kwargs["lexicographic_schedule_stability"] is stage_two
    assert env_kwargs["schedule_stability_mode"] == mode
    assert env_kwargs["lexicographic_stability_time_limit"] == 60.0


def test_progress_console_mode_redirects_details_to_log(
    monkeypatch,
    tmp_path,
    capsys,
):
    args = SimpleNamespace(
        output_dir=str(tmp_path),
        instance_type="quiet-test",
        detailed_log_file="",
        console_mode="progress",
    )
    monkeypatch.setattr(ablation, "_parse_args", lambda: args)
    monkeypatch.setattr(ablation, "_resolve_runtime_args", lambda value: value)

    def fake_execute(runtime_args, run_timestamp, progress_file):
        print("noisy stdout detail")
        import sys

        print("noisy stderr detail", file=sys.stderr)
        ablation.logger.log("structured logger detail")
        progress_file.write("PROGRESS 1/1\n")
        progress_file.flush()

    monkeypatch.setattr(ablation, "_execute_ablation", fake_execute)

    ablation.main()

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "PROGRESS 1/1\n"
    log_files = list(tmp_path.glob("ablation_quiet-test_*.log"))
    assert len(log_files) == 1
    detail = log_files[0].read_text(encoding="utf-8")
    assert "noisy stdout detail" in detail
    assert "noisy stderr detail" in detail
    assert "structured logger detail" in detail

def test_empty_powershell_checkpoint_gets_actionable_error(monkeypatch, capsys):
    monkeypatch.setattr(
        ablation.sys,
        "argv",
        [
            "run_ablation_experiments.py",
            "--test_model_path",
            "--device",
            "cuda:0",
        ],
    )

    with pytest.raises(SystemExit, match="2"):
        ablation._parse_args()

    error = capsys.readouterr().err
    assert "$LegacyCheckpoint is probably empty or undefined" in error
    assert "Test-Path -LiteralPath $LegacyCheckpoint" in error

def test_separate_metric_svgs_cover_all_ablation_views(tmp_path):
    summary = {
        method: {
            "num_instances": 1,
            "num_completed": 1,
            "num_with_solution": int(method != "solver_only"),
            "incumbent_rate_percent": 0.0 if method == "solver_only" else 100.0,
            "mean_best_obj": None if method == "solver_only" else 100.0,
            "mean_primal_dual_gap": None if method == "solver_only" else 0.1,
            "mean_primaldualintegral": None if method == "solver_only" else 2.0,
            "mean_solving_time": 10.0,
            "mean_primary_solving_time": 8.0,
            "mean_stability_solving_time": 2.0,
            "mean_wall_time": 12.0,
            "mean_callback_time": 0.25,
            "mean_ntotal_nodes": 4.0,
            "num_valid_solving_time": 1,
            "num_valid_primary_solving_time": 1,
            "num_valid_stability_solving_time": 1,
            "num_valid_wall_time": 1,
            "num_valid_callback_time": 1,
            "num_valid_best_obj": int(method != "solver_only"),
            "num_valid_primal_dual_gap": int(method != "solver_only"),
            "num_valid_primaldualintegral": int(method != "solver_only"),
            "num_valid_ntotal_nodes": 1,
        }
        for method in ablation.METHOD_ORDER
    }

    outputs = ablation._write_metric_svgs(tmp_path, "ablation_case", summary)

    expected_suffixes = {
        "feasibility",
        "objective",
        "gap",
        "pdi",
        "time",
        "two_stage_time",
        "wall_time",
        "callback",
        "nodes",
    }
    actual_suffixes = {
        str(path)
        .replace("\\", "/")
        .rsplit("/", 1)[-1]
        .removeprefix("ablation_case_")
        .removesuffix(".svg")
        for path in outputs
    }
    assert len(outputs) == len(expected_suffixes)
    assert actual_suffixes == expected_suffixes
    for output in outputs:
        text = open(output, encoding="utf-8").read()
        assert text.startswith("<svg")
        assert "SCIP Default" in text
        assert "A3C + Structure Rerank" in text


def test_zero_metrics_are_visible_and_equal_values_are_labeled_as_ties(tmp_path):
    summary = {
        method: {
            "num_instances": 1,
            "num_completed": 1,
            "num_with_solution": 1,
            "incumbent_rate_percent": 100.0,
            "mean_best_obj": 483.0,
            "mean_primal_dual_gap": 0.0,
            "mean_primaldualintegral": 0.0,
            "mean_solving_time": 0.3,
            "mean_primary_solving_time": 0.2,
            "mean_stability_solving_time": 0.1,
            "mean_wall_time": 0.4,
            "mean_callback_time": 0.0,
            "mean_ntotal_nodes": 1.0,
            "num_valid_solving_time": 1,
            "num_valid_primary_solving_time": 1,
            "num_valid_stability_solving_time": 1,
            "num_valid_wall_time": 1,
            "num_valid_callback_time": 1,
            "num_valid_best_obj": 1,
            "num_valid_primal_dual_gap": 1,
            "num_valid_primaldualintegral": 1,
            "num_valid_ntotal_nodes": 1,
        }
        for method in ablation.METHOD_ORDER
    }

    outputs = ablation._write_metric_svgs(tmp_path, "ablation_tie", summary)
    gap_path = next(path for path in outputs if str(path).endswith("_gap.svg"))
    objective_path = next(
        path for path in outputs if str(path).endswith("_objective.svg")
    )
    gap_svg = open(gap_path, encoding="utf-8").read()
    objective_svg = open(objective_path, encoding="utf-8").read()

    assert "TIE: all valid values equal" in gap_svg
    assert "0.0000" in gap_svg
    assert "tie vs SCIP" in gap_svg
    assert ">n/a (" not in gap_svg
    assert "TIE: all valid values equal" in objective_svg

from types import SimpleNamespace

import pytest

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

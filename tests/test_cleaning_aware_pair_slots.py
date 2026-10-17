from petri_mip_generator import (
    PetriMIPConfig,
    _canonical_cleaning_layout,
    _canonical_mix_slot_by_pair,
    build_petri_mip_model,
)
from petri_warm_start import _canonical_pairs_by_pm


def _pure_2x2_config(*, wafers, cleaning_interval):
    return PetriMIPConfig(
        num_batches=15,
        total_wafers=wafers,
        full_mode_wafers=0,
        mix_mode_wafers=wafers,
        cleaning_interval=cleaning_interval,
    )


def _pure_4x1_config(*, wafers, cleaning_interval):
    return PetriMIPConfig(
        num_batches=15,
        total_wafers=wafers,
        full_mode_wafers=wafers,
        mix_mode_wafers=0,
        cleaning_interval=cleaning_interval,
    )


def test_terminal_interval_cycle_triggers_cleaning():
    cfg = _pure_4x1_config(wafers=20, cleaning_interval=3)
    layout = _canonical_cleaning_layout(cfg)

    assert layout[2]["last_epoch"] == 1
    assert layout[2]["clean_count"] == 1
    assert layout[3]["clean_count"] == 0
    assert cfg.num_clean_slots_per_pm == 1


def test_no_terminal_clean_before_interval_is_completed():
    cfg = _pure_4x1_config(wafers=16, cleaning_interval=3)
    layout = _canonical_cleaning_layout(cfg)

    assert layout[2]["clean_count"] == 0
    assert layout[3]["clean_count"] == 0
    assert cfg.num_clean_slots_per_pm == 0


def test_production_model_excludes_terminal_clean_from_product_makespan():
    cfg = _pure_4x1_config(wafers=20, cleaning_interval=3)
    model = build_petri_mip_model(cfg)
    try:
        constraints = {constraint.name: constraint for constraint in model.getConss()}
        triggered = constraints["clean_active_from_trigger_2_1"]
        inactive = constraints["clean_active_from_trigger_3_1"]

        assert model.getLhs(triggered) == 1.0
        assert model.getRhs(triggered) == 1.0
        assert model.getLhs(inactive) == 0.0
        assert model.getRhs(inactive) == 0.0
        assert "makespan_lb_1" in constraints
        assert not any(name.startswith("makespan_clean_lb_") for name in constraints)
    finally:
        model.freeProb()


def test_partial_pair_moves_out_of_single_pair_cleaning_segment():
    cfg = _pure_2x2_config(wafers=17, cleaning_interval=3)
    layout = _canonical_cleaning_layout(cfg)
    slots = _canonical_mix_slot_by_pair(cfg, layout)

    assert slots[9] == (2, 4)
    assert slots[7] == (2, 5)
    partial_segment = next(
        segment
        for segment in layout[2]["segments"]
        if slots[9][1] in segment["positions"]
    )
    replacement_segment = next(
        segment
        for segment in layout[2]["segments"]
        if slots[7][1] in segment["positions"]
    )
    assert len(partial_segment["positions"]) == 2
    assert len(replacement_segment["positions"]) == 1
    assert _canonical_pairs_by_pm(cfg)[2] == [1, 3, 5, 9, 7]


def test_partial_pair_keeps_normal_slot_when_segment_has_multiple_pairs():
    cfg = _pure_2x2_config(wafers=17, cleaning_interval=10)

    assert _canonical_mix_slot_by_pair(cfg)[9] == (2, 5)
    assert _canonical_pairs_by_pm(cfg)[2] == [1, 3, 5, 7, 9]


def test_production_model_uses_cleaning_aware_partial_pair_slot():
    cfg = _pure_2x2_config(wafers=17, cleaning_interval=3)
    model = build_petri_mip_model(cfg)
    try:
        constraints = {constraint.name: constraint for constraint in model.getConss()}
        selected = constraints["mix_pair_slot_fixed_9_2_4"]
        rejected = constraints["mix_pair_slot_fixed_9_2_5"]

        assert model.getLhs(selected) == 1.0
        assert model.getRhs(selected) == 1.0
        assert model.getLhs(rejected) == 0.0
        assert model.getRhs(rejected) == 0.0
    finally:
        model.freeProb()

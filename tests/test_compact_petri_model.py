import json

import pytest

pytest.importorskip("pyscipopt")

from petri_mip_generator import PetriMIPConfig, build_petri_mip_model
from petri_warm_start import (
    _warm_start_profiles,
    _sha256_file,
    find_compatible_mixed_warm_start,
    write_mixed_warm_start,
)
def _config(mode, secondary="compact_resource_idle"):
    common = {
        "num_batches": 1,
        "total_wafers": 4,
        "full_mode_wafers": 0,
        "mix_mode_wafers": 0,
        "cleaning_interval": 5,
        "schedule_stability_objective": secondary,
    }
    if mode == "4x1":
        common["process_mode"] = "4x1"
    elif mode == "2x2":
        common["process_mode"] = "2x2"
    elif mode == "mixed":
        common.update(
            process_mode="mixed",
            full_mode_wafers=2,
            mix_mode_wafers=2,
        )
    else:
        raise ValueError(mode)
    return PetriMIPConfig(**common)


def _solve_primary(config):
    model = build_petri_mip_model(config)
    model.setParam("display/verblevel", 0)
    model.setParam("limits/time", 60.0)
    model.optimize()
    assert str(model.getStatus()).lower() == "optimal"
    return model, float(model.getObjVal())


def test_large_ood_warm_start_reserves_unrestricted_fallback():
    config = PetriMIPConfig(
        num_batches=14,
        total_wafers=48,
        full_mode_wafers=24,
        mix_mode_wafers=24,
        process_mode='mixed',
    )
    assert _warm_start_profiles(config) == (
        ('spbs_fixed_slots', 0.50),
        ('spbs_structure_only', 0.25),
        ('spbs_unrestricted', None),
    )


def test_programmatic_defaults_cover_complete_2x2_residence():
    config = _config("2x2")
    assert config.max_module_residency_time == 10000.0
    assert config.max_robot_residency_time == 10000.0
    _, objective = _solve_primary(config)
    assert objective > 0


def test_compact_secondary_has_constant_quadratic_auxiliary_count():
    compact = build_petri_mip_model(_config("mixed", "compact_resource_idle"))
    compact_names = [variable.name for variable in compact.getVars()]
    legacy = build_petri_mip_model(_config("mixed", "legacy_wait_square"))
    legacy_names = [variable.name for variable in legacy.getVars()]

    assert sum(name.startswith("resource_idle_square_") for name in compact_names) == 5
    assert not any(name.startswith("schedule_wait_square_") for name in compact_names)
    assert not any(name.startswith("resource_idle_square_") for name in legacy_names)
    assert any(name.startswith("schedule_wait_square_") for name in legacy_names)
    assert len(compact_names) < len(legacy_names)


@pytest.mark.parametrize("mode", ["4x1", "2x2", "mixed"])
def test_compact_and_legacy_preserve_primary_cmax(mode):
    _, compact_objective = _solve_primary(
        _config(mode, "compact_resource_idle")
    )
    _, legacy_objective = _solve_primary(
        _config(mode, "legacy_wait_square")
    )
    assert compact_objective == pytest.approx(
        legacy_objective,
        abs=1e-6,
        rel=1e-9,
    )


def test_exact_alias_relaxations_remain_integral_at_optimum():
    model, _ = _solve_primary(_config("mixed"))
    prefixes = (
        "wafer_to_full_pair_",
        "wafer_to_mix_pair_",
        "assign_full_",
        "assign_mix_",
        "pec_job_chamber_",
    )
    aliases = [
        variable
        for variable in model.getVars()
        if variable.name.startswith(prefixes)
        and not variable.name.startswith("pec_job_chamber_link_")
    ]
    assert aliases
    assert all(variable.vtype() == "CONTINUOUS" for variable in aliases)
    for variable in aliases:
        value = float(model.getVal(variable))
        assert min(abs(value), abs(value - 1.0)) <= 1e-7


def test_spbs_warm_start_is_feasible_in_full_quadratic_model(tmp_path):
    config = _config("mixed", "compact_resource_idle")
    solution_path = write_mixed_warm_start(
        tmp_path,
        "warmstart_smoke.lp",
        config,
        time_limit=60.0,
        memory_limit_mb=1024,
        random_seed=1,
    )

    assert solution_path is not None
    model = build_petri_mip_model(config)
    try:
        solution = model.readSolFile(solution_path)
        assert model.checkSol(
            solution,
            printreason=False,
            completely=True,
            original=True,
        )
        assert model.addSol(solution, free=True)
    finally:
        model.freeProb()


def test_cached_warm_start_requires_full_quadratic_scope(tmp_path):
    instance_path = tmp_path / "cache.lp"
    solution_path = tmp_path / "cache_warmstart.sol"
    metadata_path = tmp_path / "cache_warmstart.meta.json"
    instance_path.write_text("test instance", encoding="utf-8")
    solution_path.write_text("objective value: 0\n", encoding="utf-8")
    metadata = {
        "instance_sha256": _sha256_file(instance_path),
        "warm_start_strategy": "SPBS",
    }
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")

    assert find_compatible_mixed_warm_start(tmp_path, "cache.lp") is None

    metadata["solution_scope"] = "full_quadratic_model"
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
    assert find_compatible_mixed_warm_start(tmp_path, "cache.lp") == str(solution_path)

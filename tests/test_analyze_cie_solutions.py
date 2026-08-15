import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace


SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "cie"
    / "code"
    / "analyze_cie_solutions.py"
)
SPEC = importlib.util.spec_from_file_location("analyze_cie_solutions", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def _benchmark_row(instance_path, solution_path):
    return {
        "suite": "cie_validation",
        "path": str(instance_path),
        "instance": instance_path.name,
        "method": "scip_default",
        "seed": 1,
        "training_seed": -1,
        "run_label": "final_validation",
        "warm_start": "none",
        "status": "optimal",
        "solving_time": 1.0,
        "gap": 0.0,
        "primal_dual_integral": 1.0,
        "solution_file": str(solution_path),
    }


def _original_meta():
    return {
        "manifest": "manifest.json",
        "methods": ["scip_default"],
        "seeds": [1],
        "training_seed": -1,
        "run_label": "final_validation",
        "stability_profile": "full",
        "time_limit": 600,
        "node_limit": -1,
        "memory_limit_mb": 2048,
        "instance_count": 1,
        "empty_suites": [],
    }


def _combined_meta():
    return {
        "methods": ["scip_default"],
        "seeds": [1],
        "training_seeds": [-1],
        "stability_profiles": ["full"],
        "stability_profile": "full",
        "time_limit": 600,
        "instance_count": 1,
        "empty_suites": [],
        "source_runs": [],
    }


def test_original_and_combined_payloads_are_accepted_but_analysis_is_not(tmp_path):
    row = _benchmark_row(tmp_path / "case.lp", tmp_path / "case.sol")

    assert MODULE._is_benchmark_payload({"meta": _original_meta(), "rows": [row]})
    assert MODULE._is_benchmark_payload({"meta": _combined_meta(), "rows": [row]})
    assert not MODULE._is_benchmark_payload({
        "source_benchmarks": ["run.json"],
        "solution_count": 1,
        "invalid_count": 0,
        "rows": [{
            "suite": "cie_validation",
            "path": str(tmp_path / "case.lp"),
            "method": "scip_default",
            "solver_seed": 1,
            "solution_file": str(tmp_path / "case.sol"),
        }],
    })


def test_repeated_analysis_does_not_consume_its_own_output(tmp_path, monkeypatch):
    input_root = tmp_path / "campaign"
    output_root = input_root / "analysis"
    input_root.mkdir()
    solution_path = input_root / "case.sol"
    solution_path.write_text(
        "solution status: optimal solution found\n"
        "objective value: 10\n"
        "c_max 10\n"
        "wafer_completion_0 10\n",
        encoding="utf-8",
    )
    benchmark_path = input_root / "cie_benchmark_test.json"
    benchmark_path.write_text(
        json.dumps({
            "meta": _original_meta(),
            "rows": [_benchmark_row(input_root / "case.lp", solution_path)],
        }),
        encoding="utf-8",
    )
    args = SimpleNamespace(
        input_dir=str(input_root),
        output_dir=str(output_root),
        validate=False,
        fail_on_invalid=False,
    )
    monkeypatch.setattr(MODULE, "_parse_args", lambda: args)

    MODULE.main()
    first = json.loads(
        (output_root / "cie_manufacturing_metrics.json").read_text(encoding="utf-8")
    )
    MODULE.main()
    second = json.loads(
        (output_root / "cie_manufacturing_metrics.json").read_text(encoding="utf-8")
    )

    assert first == second
    assert second["source_benchmarks"] == [str(benchmark_path)]
    assert second["solution_count"] == 1
    assert second["rows"][0]["solver_seed"] == 1


def test_serialized_solution_allowance_is_tiny_and_explicit():
    assert MODULE.SCIP_FEASIBILITY_TOLERANCE == 1.0e-6
    assert MODULE.SOLUTION_SERIALIZATION_ALLOWANCE == 1.0e-12
    assert MODULE.SOLUTION_FEASIBILITY_TOLERANCE == 1.000001e-6


def test_physical_stability_metrics_ignore_floating_auxiliary_slacks(tmp_path):
    values = {
        "c_max": 50.0,
        "wafer_completion_1": 50.0,
        "prod_stage_end_1_atr_lp_al": 2.0,
        "prod_stage_start_1_al": 5.0,
        "prod_stage_end_1_al": 8.0,
        "prod_stage_start_1_atr_al_llupper": 10.0,
        "prod_stage_end_1_llupper": 14.0,
        "prod_stage_start_1_vtr_load": 15.0,
        "prod_stage_end_1_vtr_load": 17.0,
        "prod_stage_start_1_pm": 19.0,
        "prod_stage_end_1_pm": 25.0,
        "prod_stage_start_1_vtr_unload": 29.0,
        "prod_stage_end_1_lllower": 35.0,
        "prod_stage_start_1_atr_lllower_lp": 40.0,
        "full_batch_used_2_1": 1.0,
        "full_batch_used_2_2": 1.0,
        "full_batch_used_2_3": 1.0,
        "full_start_2_1": 0.0,
        "full_start_2_2": 10.0,
        "full_start_2_3": 25.0,
        "full_batch_idle_2_1_2": 10000.0,
        "schedule_wait_unconstrained": 10000.0,
    }

    metrics = MODULE._metrics(
        {"best_objective": 50.0}, values
    )

    assert metrics["physical_route_total_wait"] == 17.0
    assert metrics["physical_route_max_wait"] == 5.0
    assert metrics["physical_cadence_cv"] == 0.2
    assert metrics["physical_cadence_deviation_sum"] == 5.0

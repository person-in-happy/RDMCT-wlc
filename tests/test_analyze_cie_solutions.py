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

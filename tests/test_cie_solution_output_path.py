from pathlib import Path
from types import SimpleNamespace

from cie.code.run_cie_benchmarks import (
    _benchmark_artifact_prefix,
    _checkpoint_path,
    _solution_output_path,
)


def _build(root, label, max_path_chars=240):
    return _solution_output_path(
        root,
        suite="wafer20_pure22_clean3",
        instance_stem="wafer20_22_clean3_20260826",
        method="proposed",
        seed=1,
        training_seed=1,
        run_label=label,
        max_path_chars=max_path_chars,
    )


def test_solution_path_preserves_readable_name_when_within_budget(tmp_path):
    path = _build(tmp_path, "short_run")

    assert path.parent == tmp_path
    assert path.name.endswith("__short_run.sol")


def test_solution_path_uses_deterministic_digest_when_over_budget(tmp_path):
    label = "long_publication_run_" * 20
    first = _build(tmp_path, label, max_path_chars=180)
    second = _build(tmp_path, label, max_path_chars=180)

    assert first == second
    assert len(str(first)) < 180
    assert first.suffix == ".sol"
    assert first.name.startswith(("wafer20_pure22_clean3", "solution_"))
    assert label not in first.name


def test_benchmark_artifact_prefix_hashes_long_run_label(tmp_path):
    label = "long_publication_run_" * 20
    first = _benchmark_artifact_prefix(
        tmp_path, label, "20260827_210130", max_path_chars=180
    )
    second = _benchmark_artifact_prefix(
        tmp_path, label, "20260827_210130", max_path_chars=180
    )

    assert first == second
    assert len(f"{first}_summary.csv") < 180
    assert label not in first.name


def test_checkpoint_path_hashes_long_run_label(tmp_path):
    args = SimpleNamespace(
        output_dir=str(tmp_path),
        run_label="long_publication_run_" * 20,
        training_seed=1,
    )
    path = _checkpoint_path(args, "a" * 64)

    assert path.parent.name == ".checkpoints"
    assert len(str(path)) < 240
    assert path.name.startswith("checkpoint_")
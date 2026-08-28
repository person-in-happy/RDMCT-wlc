import json
from types import SimpleNamespace

import pytest

import petri_mip_generator as generator
import petri_warm_start


class _FakeModel:
    def __init__(self, *, feasible):
        self.feasible = feasible
        self.checked_solution = None
        self.check_kwargs = None

    def writeProblem(self, path):
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("fake lp")

    def readSolFile(self, path):
        self.solution_path = path
        return "loaded solution"

    def checkSol(self, solution, **kwargs):
        self.checked_solution = solution
        self.check_kwargs = kwargs
        return self.feasible


def _install_warm_start_fakes(monkeypatch, tmp_path, *, feasible):
    model = _FakeModel(feasible=feasible)
    solution_path = tmp_path / "case_warmstart.sol"
    solution_path.write_text("fake solution", encoding="utf-8")
    metadata_path = tmp_path / "case_warmstart.meta.json"
    metadata_path.write_text(
        json.dumps({"solution_scope": "full_quadratic_model"}),
        encoding="utf-8",
    )

    monkeypatch.setattr(generator, "build_petri_mip_model", lambda cfg: model)
    monkeypatch.setattr(generator, "_write_model_description", lambda *args: None)
    monkeypatch.setattr(
        petri_warm_start,
        "find_compatible_mixed_warm_start",
        lambda *args: str(solution_path),
    )
    monkeypatch.setattr(
        petri_warm_start,
        "write_mixed_warm_start",
        lambda *args, **kwargs: pytest.fail("cache should have been reused"),
    )

    def fail_polishing(*args, **kwargs):
        raise RuntimeError("polished completion is infeasible")

    monkeypatch.setattr(
        petri_warm_start,
        "polish_mixed_warm_start",
        fail_polishing,
    )
    return model, metadata_path


def test_polishing_failure_retains_independently_verified_warm_start(
    monkeypatch, tmp_path, capsys
):
    model, metadata_path = _install_warm_start_fakes(
        monkeypatch,
        tmp_path,
        feasible=True,
    )

    result = generator.generate_petri_mip_instance(
        tmp_path,
        "case.lp",
        SimpleNamespace(mix_wafer_ids=(1,)),
        warm_start_time_limit=60.0,
        require_warm_start=True,
        append_date=False,
    )

    assert result == str(tmp_path / "case.lp")
    assert model.checked_solution == "loaded solution"
    assert model.check_kwargs == {
        "printreason": False,
        "completely": True,
        "original": True,
    }
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    assert metadata["polishing_fallback"]["status"] == (
        "retained_verified_full_model_warm_start"
    )
    assert "polished completion is infeasible" in metadata["polishing_fallback"][
        "reason"
    ]
    assert "independently verified full-model warm start" in capsys.readouterr().out


def test_polishing_failure_rejects_invalid_retained_warm_start(monkeypatch, tmp_path):
    model, _ = _install_warm_start_fakes(
        monkeypatch,
        tmp_path,
        feasible=False,
    )

    with pytest.raises(
        RuntimeError,
        match="did not pass full-model feasibility validation",
    ):
        generator.generate_petri_mip_instance(
            tmp_path,
            "case.lp",
            SimpleNamespace(mix_wafer_ids=(1,)),
            warm_start_time_limit=60.0,
            require_warm_start=True,
            append_date=False,
        )

    assert model.check_kwargs["completely"] is True
    assert model.check_kwargs["original"] is True
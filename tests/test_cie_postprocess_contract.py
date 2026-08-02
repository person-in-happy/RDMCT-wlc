from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "cie" / "run_cie_postprocess.ps1"


def test_postprocess_is_fail_closed_and_runs_all_submission_steps():
    text = SCRIPT.read_text(encoding="utf-8")
    for command in (
        "combine_cie_runs.py",
        "analyze_cie_solutions.py",
        "--validate",
        "--fail_on_invalid",
        "audit_cie_submission.py",
        "analyze_cie_submission.py",
        "--bootstrap_samples",
    ):
        assert command in text
    assert "$ErrorActionPreference = 'Stop'" in text
    assert "if ($LASTEXITCODE -ne 0)" in text


def test_formal_stage_defaults_match_the_frozen_protocol():
    text = SCRIPT.read_text(encoding="utf-8")
    for stage in (
        "validation",
        "main",
        "stability",
        "doe",
        "spbs",
        "sensitivity",
        "ood",
    ):
        assert f"{stage} =" in text
    assert "ood = '1,2,3'" in text
    assert "spbs = '1,2,3,4,5,6,7,8,9,10'" in text
    assert "doe = 'scip_default[manufacturing_doe]'" in text
    assert "spbs = 'scip_default[spbs_auto]'" in text


def test_formal_doe_requires_programmatic_figures():
    text = SCRIPT.read_text(encoding="utf-8")
    assert "cie_submission_doe_pdi_effects.png" in text
    assert "cie_submission_doe_diagnostics.png" in text
    assert "Install requirements.txt before the formal freeze." in text

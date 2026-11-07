import importlib.util
from pathlib import Path


SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "JMS"
    / "analyze_mode_cleaning_crossover.py"
)
SPEC = importlib.util.spec_from_file_location("mode_cleaning_crossover", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def test_parse_int_spec_accepts_ranges_and_rejects_clean1():
    assert MODULE._parse_int_spec("2-4,6") == [2, 3, 4, 6]
    try:
        MODULE._parse_int_spec("1-3", minimum=2)
    except ValueError:
        pass
    else:
        raise AssertionError("cleaning interval 1 must be rejected")


def test_bridge_audit_accepts_one_4s_combined_exchange_and_one_split(tmp_path):
    solution = tmp_path / "case.sol"
    solution.write_text(
        "mix_bridge_combined_2_2 1\n"
        "mix_bridge_start_2_2 10\n"
        "mix_bridge_unload_end_2_2 14\n"
        "mix_bridge_load_start_2_2 10\n"
        "mix_bridge_end_2_2 14\n"
        "mix_bridge_start_2_3 20\n"
        "mix_bridge_unload_end_2_3 24\n"
        "mix_bridge_load_start_2_3 30\n"
        "mix_bridge_end_2_3 34\n",
        encoding="utf-8",
    )

    counts = MODULE._audit_bridge_solution(solution)

    assert counts == {"active": 2, "combined": 1, "split": 1}


def test_bridge_audit_rejects_8s_combined_exchange(tmp_path):
    solution = tmp_path / "case.sol"
    solution.write_text(
        "mix_bridge_combined_2_2 1\n"
        "mix_bridge_start_2_2 10\n"
        "mix_bridge_unload_end_2_2 14\n"
        "mix_bridge_load_start_2_2 10\n"
        "mix_bridge_end_2_2 18\n",
        encoding="utf-8",
    )

    try:
        MODULE._audit_bridge_solution(solution)
    except ValueError as exc:
        assert "load duration" in str(exc) or "one 4.0s" in str(exc)
    else:
        raise AssertionError("An 8 s combined exchange must fail the audit")


def test_winner_uses_lower_cmax_and_has_explicit_tie_tolerance():
    assert MODULE._winner(610.0, 578.0) == "2x2"
    assert MODULE._winner(610.0, 1070.0) == "4x1"
    assert MODULE._winner(610.0, 610.0005) == "tie"


def test_suite_names_cover_all_three_modes():
    for mode in ("pure41", "pure22", "mixed11"):
        match = MODULE.SUITE_RE.match(f"mode_n017_clean03_{mode}")
        assert match is not None
        assert match.group("mode") == mode


def test_failed_bridge_audit_excludes_cell_from_exact_csv(tmp_path, monkeypatch):
    import json, csv, sys
    sol=tmp_path/'bad.sol'
    sol.write_text('mix_bridge_start_2_2 10\nmix_bridge_end_2_2 18\nmix_bridge_unload_end_2_2 14\nmix_bridge_load_start_2_2 10\nmix_bridge_combined_2_2 1\n')
    metrics=tmp_path/'metrics.json'
    metrics.write_text(json.dumps({'rows':[{'suite':'mode_n024_clean05_mixed11','solver_seed':1,'training_seed':1,'status':'optimal','gap':0,'physically_feasible':True,'cmax_matches_last_product_return':True,'solution_file':str(sol),'cmax':1796}]}))
    out=tmp_path/'out'
    monkeypatch.setattr(sys,'argv',['audit','--metrics',str(metrics),'--output_dir',str(out),'--wafer_counts','24','--cleaning_intervals','5'])
    MODULE.main()
    assert list(csv.DictReader((out/'mode_cleaning_cells.csv').open(encoding='utf-8-sig'))) == []

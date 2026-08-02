from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CIE_CODE = PROJECT_ROOT / "cie" / "code"
if str(CIE_CODE) not in sys.path:
    sys.path.insert(0, str(CIE_CODE))

from combine_cie_runs import _deduplicate_rows, _write_csv


def _baseline_row(*, warm_start, run_label, training_seed=1, marker="original"):
    return {
        "method": "scip_default",
        "path": "instance.lp",
        "seed": 1,
        "training_seed": training_seed,
        "stability_profile": "full",
        "warm_start": warm_start,
        "run_label": run_label,
        "marker": marker,
    }


def test_spbs_none_and_auto_are_distinct_conditions():
    rows = [
        _baseline_row(warm_start="none", run_label="spbs_none"),
        _baseline_row(warm_start="auto", run_label="spbs_auto"),
    ]

    merged = _deduplicate_rows(rows)

    assert len(merged) == 2
    assert {(row["warm_start"], row["run_label"]) for row in merged} == {
        ("none", "spbs_none"),
        ("auto", "spbs_auto"),
    }


def test_duplicate_rows_from_the_same_condition_are_collapsed():
    rows = [
        _baseline_row(
            warm_start="auto", run_label="spbs_auto", marker="first"
        ),
        _baseline_row(
            warm_start="auto", run_label="spbs_auto", marker="rerun"
        ),
    ]

    merged = _deduplicate_rows(rows)

    assert len(merged) == 1
    assert merged[0]["marker"] == "first"


def test_main_baselines_repeated_for_training_seeds_remain_deduplicated():
    rows = [
        _baseline_row(
            warm_start="auto", run_label="trainseed_1", training_seed=1
        ),
        _baseline_row(
            warm_start="auto", run_label="trainseed_2", training_seed=2
        ),
    ]

    merged = _deduplicate_rows(rows)

    assert len(merged) == 1


def test_csv_writer_preserves_union_of_fields_across_resumed_schemas(tmp_path):
    output = tmp_path / "mixed.csv"
    old_schema = {f"field_{index}": index for index in range(45)}
    new_schema = dict(old_schema)
    new_schema.update(
        {
            "schedule_stability_mode": "lexicographic",
            "stability_status": "timelimit",
            "lexicographic_stability_time_limit": 60.0,
            "lexicographic_schedule_stability": {"status": "timelimit"},
            "primary_status": "timelimit",
            "stability_profile": "full",
        }
    )

    _write_csv(output, [old_schema, new_schema])

    with open(output, encoding="utf-8-sig", newline="") as stream:
        parsed = list(__import__("csv").DictReader(stream))
    assert len(parsed[0]) == 51
    assert parsed[0]["stability_profile"] == ""
    assert parsed[1]["primary_status"] == "timelimit"
    assert parsed[1]["lexicographic_schedule_stability"] == (
        '{"status": "timelimit"}'
    )

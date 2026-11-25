"""Verify the ordered mixed eight-wafer handoffs and independently score the nine schedules."""
import csv
import hashlib
import json
import math
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
JMS = HERE.parents[1]
OUT = JMS / "results/table3_mixed8_20261125/archived_stream"
sys.path.insert(0, str(HERE.parent / "huber_residence_20261125"))
from verify_manuscript import independent

GAPS = {"10pct": 0.10, "1pct": 0.01, "0p01pct": 0.0001}
LOG = JMS / "results/table4_one_percent_20261124/runs/D_n8_H10_mixed_dual__s1/A/attempt_001/solver.log"
BOUND = JMS / "results/residence_objective_20261125/primary_relaxation_tight/result.json"


def read(path):
    return json.loads(path.read_bytes())


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def close(actual, expected):
    assert math.isclose(float(actual), float(expected), rel_tol=0, abs_tol=2e-6), (actual, expected)


def verify():
    search = read(OUT / "primary_search.json")
    assert search["identity"]["log_sha256"] == digest(LOG)
    assert search["identity"]["cap_certificate"] == digest(BOUND)
    proof = read(BOUND)
    assert proof["status"] == "INFEASIBLE" and proof["cap"] == 552 and proof["lower"] == 553
    events = search["events"]
    trace = re.findall(r"^#\d+\s+[\d.]+s best:([\d.]+)\s+next:", LOG.read_text(errors="replace"), re.M)
    assert [float(v) for v in trace] == [event["upper"] for event in events[2:]]
    assert all(x["upper"] > y["upper"] for x, y in zip(events, events[1:]))
    assert len(events) == 9
    for seq, event in enumerate(events):
        path = OUT / event["path"]
        assert digest(path / "primary.json") == event["record_sha256"]
        native = read(path / "primary.json")
        assert native["rows"] == 281012 and native["replay"]["valid"]
        assert native["record"]["replay_order"] == seq
        assert native["schedule_sha256"] == digest(path / "schedule.json")
        assert native["assignment_sha256"] == digest(path / "assignment.json.gz")
        source = JMS / native["record"]["source"]
        assert native["record"]["source_sha256"] == digest(source / "primary.json")
        configuration = read(path / "schedule.json")["config"]
        assert configuration["load_ports"] == {f"LP{n}": {"4x1": 1, "2x2": 1} for n in range(1, 5)}
        assert (configuration["cleaning_interval"], configuration["dummy_count"], configuration["horizon"]) == (10, 8, 100000)
        assert configuration["module_residency"] == configuration["robot_residency"] == 100
        close(independent(read(path / "schedule.json"))["cmax"], event["upper"])
        close((event["upper"] - proof["lower"]) / proof["lower"], event["gap"])
    for key, requested in GAPS.items():
        assert next(e for e in events if e["gap"] <= requested) == search["gates"][key]
    csv_path = OUT / "threshold_cells.csv"
    with csv_path.open(encoding="utf8", newline="") as f:
        cells = list(csv.DictReader(f))
    assert len(cells) == 9 and {(r["gA"], r["gB"]) for r in cells} == {(a, b) for a in GAPS for b in GAPS}
    for r in cells:
        base = JMS / r["source"]
        result = read(base / "result.json")
        assert result["original_rows"] == result["replayed_rows"] == 281012 and result["replay"]["valid"]
        assert result["files"]["schedule.json"] == r["schedule_sha256"] == digest(base / "schedule.json")
        assert result["files"]["assignment.json.gz"] == r["assignment_sha256"] == digest(base / "assignment.json.gz")
        assert search["gates"][r["gA"]]["record_sha256"] == r["A_sha256"]
        expected = independent(read(base / "schedule.json"))
        for column, metric in (("f_A", "cmax"), ("f_B", "secondary"), ("mean", "mean_residence"),
                               ("spread", "residence_range"), ("E", "clean_deficit")):
            close(r[column], expected[metric])
        close(expected["secondary"], r["B_upper"])
        lower = float(r["B_lower"])
        assert lower > 0
        assert (float(r["B_upper"]) - lower) / lower <= GAPS[r["gB"]] + 1e-8
        assert float(r["f_A"]) <= float(r["A_upper"]) + 2e-6
    return dict(status="passed", cells=len(cells), primary_candidates=len(events),
                trace_incumbents=len(trace), native_rows_per_candidate_or_endpoint=281012,
                reused_fixed_secondary=sum(r["reused"] == "True" for r in cells),
                new_fixed_secondary=sum(r["reused"] == "False" for r in cells),
                table_sha256=digest(csv_path), primary_log_sha256=digest(LOG), lower_certificate_sha256=digest(BOUND),
                handoff_upper_s={k: search["gates"][k]["upper"] for k in GAPS})


if __name__ == "__main__":
    report = verify()
    destination = OUT / "validation.json"
    text = json.dumps(report, indent=2)
    if not destination.exists() or destination.read_text(encoding="utf8") != text:
        tmp = destination.with_suffix(".tmp")
        tmp.write_text(text, encoding="utf8")
        tmp.replace(destination)
    print(text)

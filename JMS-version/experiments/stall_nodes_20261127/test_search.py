"""Short functional tests for the two-stage stopping conditions."""
import gzip
import hashlib
from itertools import combinations
import json
from pathlib import Path
import subprocess
import sys

import pytest


@pytest.mark.parametrize(
    ("patience", "gap", "expected_status"),
    [(1, 0.0, "stallnodelimit"), (100, 1.0, "gaplimit"), (-1, 0.0, "optimal")],
)
def test_native_stopping_conditions(patience, gap, expected_status):
    scip = pytest.importorskip("pyscipopt")
    model = scip.Model()
    model.hideOutput()
    model.setPresolve(scip.SCIP_PARAMSETTING.OFF)
    model.setSeparating(scip.SCIP_PARAMSETTING.OFF)
    model.setHeuristics(scip.SCIP_PARAMSETTING.OFF)
    model.setParam("misc/usesymmetry", 0)
    model.setParam("parallel/maxnthreads", 1)
    model.setParam("limits/gap", gap)
    model.setParam("limits/stallnodes", patience)

    # Each triangle's continuous relaxation costs 1.5. Its integer cover costs 2.
    vertices = [model.addVar(vtype="B") for _ in range(24)]
    for start in range(0, len(vertices), 3):
        for left, right in combinations(vertices[start:start + 3], 2):
            model.addCons(left + right >= 1)
    model.setObjective(scip.quicksum(vertices), "minimize")
    initial = model.createSol()
    for vertex in vertices:
        model.setSolVal(initial, vertex, 1)
    assert model.addSol(initial)
    model.optimize()

    assert str(model.getStatus()) == expected_status
    assert model.checkSol(model.getBestSol(), original=True, completely=True)
    assert model.getDualbound() <= 16 <= model.getObjVal()
    if expected_status == "stallnodelimit":
        assert model.getGap() > gap
    else:
        assert model.getGap() <= gap


def test_cli_stalled_handoff_and_resume(tmp_path):
    pytest.importorskip("pyscipopt")
    case = tmp_path / "case.json"
    config = {
        "load_ports": {f"LP{i}": {"4x1": 0, "2x2": int(i <= 2)} for i in range(1, 5)},
        "max_pairs": 4,
        "max_cycles": 2,
        "dummy_count": 6,
        "module_residency": 1000,
        "robot_residency": 1000,
    }
    case.write_text(json.dumps(config), encoding="utf-8")
    out = tmp_path / "solve"
    command = [
        sys.executable, str(Path(__file__).with_name("run.py")), str(case), str(out),
        "--use-input-candidate-limits", "--spbs-seconds", "0", "--seed", "1",
        "--gap-a", "0", "--gap-b", ".01", "--stall-nodes-a", "1", "--stall-nodes-b", "-1",
        "--seconds-a", "60", "--seconds-b", "15",
    ]
    subprocess.run(command, check=True, timeout=120)
    result = json.loads((out / "result.json").read_bytes())
    primary, secondary = (result["stages"][stage] for stage in ("A", "B"))
    assert primary["native_status"] == "stallnodelimit"
    assert primary["stop_reason"] == "stagnation"
    assert not primary["gap_met"] and primary["upper"] > primary["lower"]
    assert primary["restricted_candidate_bounds"]
    assert secondary["stop_reason"] == "gap" and secondary["gap_met"]
    assert secondary["cmax_cap"] == pytest.approx(primary["upper"], abs=1e-6)
    assert secondary["initial_metrics"] == pytest.approx(primary["metrics"], abs=1e-6)
    assert result["metrics"]["cmax"] <= primary["upper"] + 1.01e-6
    assert result["metrics"]["secondary"] <= primary["metrics"]["secondary"] + 1e-6
    assignments = []
    for stage in ("A", "B"):
        record = result["stages"][stage]
        assert record["validation"]["valid"] and record["original_rows_checked"] > 0
        with gzip.open(out / stage / "assignment.json.gz", "rt", encoding="utf-8") as stream:
            values = json.load(stream)["nonzero"]
        assignments.append({name: round(value) for name, value in values.items()
                            if name.startswith(("order_", "product_first_")) and value > .5})
    assert assignments[0] and assignments[0] == assignments[1]

    # With only the A endpoint committed, a retry must reuse that same handoff.
    stage_a_file = out / "A" / "record.json"
    mtime = stage_a_file.stat().st_mtime_ns
    handoff = hashlib.sha256(stage_a_file.read_bytes()).hexdigest()
    (out / "B" / "record.json").unlink()
    (out / "result.json").unlink()
    subprocess.run(command, check=True, timeout=120)
    resumed = json.loads((out / "result.json").read_bytes())["stages"]
    assert stage_a_file.stat().st_mtime_ns == mtime
    assert resumed["A"] == primary
    assert resumed["B"]["parent_sha256"] == handoff
    assert resumed["B"]["validation"]["valid"]

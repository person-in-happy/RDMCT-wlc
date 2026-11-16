"""Protocol/API tests; no manuscript benchmark results are generated here."""
from pathlib import Path
import importlib.util
import json
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import finite_budget as f


def test_protocol_is_complete_and_budget_matched():
    cells = f.make_cells(f.source_records())
    assert len(cells) == 162
    assert len({c["id"] for c in cells}) == 162
    assert sum(c["suite"] == "objectives" for c in cells) == 60
    assert sum(c["suite"] == "components" for c in cells) == 96
    assert sum(c["suite"] == "preparation" for c in cells) == 6
    for cell in cells:
        assert sum(f.budgets(cell)) == cell["budget"]
        if cell["suite"] == "components":
            assert cell["budget"] + 60 == 300
            prep = next(c for c in cells if c["id"] == cell["preparation"])
            assert (prep["case"], prep["seed"]) == (cell["case"], cell["seed"])


def test_physical_rhythm_does_not_count_cleaning_boundaries():
    cfg = dict(chambers=[2], vtr_travel=2, atr_travel=3, alignment=20, pump=30, vent=25)
    d = dict(config=cfg, jobs=[dict(name="p", product=True, origin="VS", load_start=4,
                 unload_end=10, loan_end=30)],
             events=[dict(job="p", kind="source_pick", end=2),
                     dict(job="p", kind="destination_put", start=12)],
             cycles=[dict(chamber=2,index=i,mode="2x2",pairs=[i,i+1],start=t)
                     for i,t in enumerate([0,10,25])])
    measured = f.physical_metrics(d)
    assert measured["rhythm_centers"] == 1 and measured["rhythm"] == 5
    d["cycles"][1]["mode"] = "clean"
    assert f.physical_metrics(d)["rhythm_centers"] == 0


def test_normalized_joint_has_distinct_bound_scope():
    sys.path.insert(0, str(f.ROOT))
    from scip_imports import scip
    from types import SimpleNamespace
    m = scip.Model()
    m.hideOutput()
    c, w = m.addVar(lb=1, ub=2), m.addVar(lb=0, ub=10)
    m.addCons(w >= 20 - 10*c)
    x = SimpleNamespace(model=m,cmax=c,secondary_objective=w,primary_objective=c)
    assert f.configure_objective(x, "joint_1", {"cmax":1.,"secondary":1.}) == "normalized_weighted_objective"
    m.optimize()
    assert abs(m.getVal(c)-2) < 1e-6
    m.freeTransform()
    assert f.configure_objective(x, "primary", {"cmax":1.,"secondary":1.}) == "product_return_cmax"
    m.optimize()
    assert abs(m.getVal(c)-1) < 1e-6
    m.freeProb()


def test_shared_input_metrics_match_saved_certificates():
    for c in f.source_records():
        d = f.read(c["source"])
        measured = f.physical_metrics(d)
        assert abs(measured["cmax"] - d["cmax"]) < 2e-4
        if c["backend"] == "E":
            assert measured["rhythm_centers"] > 0
        assert Path(c["values"]).is_file()

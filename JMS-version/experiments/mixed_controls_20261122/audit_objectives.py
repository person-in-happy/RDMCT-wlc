"""Trace the common start and incumbent for each eligible run in Table 4."""
import csv
from pathlib import Path
import subprocess
import sys

from controls import OUT, ROOT, cell, matched, product, read, save, sha
from objective16 import register

DEST = OUT / "objective_audit"
TOL = 2e-4


def stages(row, path, run):
    if "stages" in run:
        records = [record for record, _ in run["stages"]]
        if row["arm"] == "AB":
            endpoint = path.parent / "secondary/runs/endpoint"
        else:
            endpoint = None
        return records, endpoint
    if row["arm"] == "B":
        return [run["record"]], None
    stage = ROOT / run["job"]["assignment"]
    log = stage.with_name("stage.json")
    if not log.is_file():
        log = stage.with_name("primary.json")
    first = read(log)["record"]
    return ([first, run["record"]], path.parent) if row["arm"] == "AB" else ([first], None)


def same_events(left, right):
    def events(data):
        return {e["name"]: (e["kind"], e.get("location"), e.get("robot"), e["start"], e["end"])
                for e in data["events"]}
    a, b = events(left), events(right)
    return a.keys() == b.keys() and all(
        a[k][:3] == b[k][:3] and abs(a[k][3]-b[k][3]) <= TOL and abs(a[k][4]-b[k][4]) <= TOL
        for k in a)


def audit_case(case):
    register()
    spec = matched.CASES[case]
    sys.path.insert(0, str(cell.BACKENDS[spec["backend"]]))
    import model

    src = ROOT / spec["source"]
    assert sha(src) == spec["source_sha256"]
    initial = read(src)
    start = product.product_metrics(initial)
    with (OUT / "objective_runs.csv").open(encoding="utf-8-sig", newline="") as f:
        rows = [r for r in csv.DictReader(f) if r["case"] == case and r["eligible"] == "True"]
    assert len(rows) == len({(r["seed"], r["arm"]) for r in rows}) == 12
    traced = []
    for r in rows:
        path = ROOT / r["record"]
        run = read(path)
        records, endpoint = stages(r, path, run)
        arm = r["arm"]
        assert r["start"] == spec["assignment_sha256"]
        a, b = float(r["cmax"]), float(r["secondary"])
        score = a / start["cmax"] + .1 * b / start["secondary"]
        expected = {"A": a, "B": b, "J": score, "AB": b}[arm]
        assert abs(expected - records[-1]["upper"]) < TOL
        info = dict(seed=int(r["seed"]), arm=arm, source=r["record"], start_A=start["cmax"],
                    start_B=start["secondary"], end_A=a, end_B=b, end_J=score, stages=records)
        if "job" in run:
            output = path.with_name("schedule.json")
            if not output.is_file():
                output = ROOT / run["job"]["schedule"]
        elif arm == "A":
            output = path.parent / "primary/schedule.json"
        else:
            output = path.parent / "secondary/runs/endpoint/schedule.json"
        info["same_initial_events"] = same_events(initial, read(output))
        if arm == "AB":
            # Insert the returned vector into the unrestricted B/J model, supplying
            # the epigraph variables that do not occur in fixed-structure solves.
            data = read(endpoint / "schedule.json")
            vals = cell.values(endpoint / "assignment.json.gz")
            x = model.Integrated(model.Config(**data["config"]))
            for chamber in x.cfg.chambers:
                for q in range(2, x.Q):
                    active = all(vals.get(x.keep[chamber, i].name, 0) > .5 for i in (q, q - 1))
                    t, u, v = [vals.get(x.cy.start[chamber, i].name, 0.) for i in (q, q - 1, q - 2)]
                    vals[f"rhythm_{chamber}_{q}"] = max(0., abs(t - 2 * u + v) - (0. if active else x.M))
            f_b, maximum, extra = product.objective_terms(x, vals, False, 25)
            vector = vals | extra | {maximum.name: float(r["wait_max"]), x.cmax.name: a}
            joint = x.cmax / start["cmax"] + .1 * f_b / start["secondary"]
            for expr, expected in ((f_b, b), (joint, score)):
                x.model.setObjective(expr, "minimize")
                s = cell.attach(x, vector)
                actual = x.model.getSolObjVal(s)
                assert abs(actual - expected) < TOL, (case, r["seed"], actual, expected)
                x.model.freeSol(s)
            info["checked_full_model_rows"] = x.model.getNConss()
            x.model.freeProb()
        traced.append(info)
    save(DEST / (case + ".json"), traced)


if __name__ == "__main__":
    if len(sys.argv) == 2:
        audit_case(sys.argv[1])
    else:
        cases = read(OUT / "summary.json")["objectives"]
        for case in cases:
            subprocess.run([sys.executable, "-B", "-X", "utf8", __file__, case], check=True)
        print(f"Verified {len(cases)} cases, 60 matched runs", flush=True)

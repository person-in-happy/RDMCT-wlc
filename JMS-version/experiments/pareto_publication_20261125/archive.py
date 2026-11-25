"""Find matching native schedule/assignment pairs in earlier campaigns by full instance identity."""
import csv
import hashlib
import json
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
JMS = HERE.parents[1]
RESULTS = JMS / "results"
OUT = RESULTS / HERE.name
sys.path.insert(0, str(HERE.parent / "square_residence_20261125"))
from score import metrics

REFERENCES = {
    "pure4": RESULTS / "mixed_controls_20261122/grid_2x2/n4__1pct/A/schedule.json",
    "mixed16": RESULTS / "pareto_scales_20261125/continuous16/endpoint810/schedule.json",
}


def read(path):
    return json.loads(path.read_bytes())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def records(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def save_rows(path, rows):
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def key(row):
    return round(float(row["fA"]), 5), round(float(row["fB"]), 5)


def nondominated(rows):
    # A 1e-5 s tolerance separates the new 3.05e-5 endpoint improvement from SCIP replay noise.
    tol = 1e-5
    numeric = [(float(r["fA"]), float(r["fB"]), r) for r in rows]
    retained = []
    for a, b, row in sorted(numeric, key=lambda item: (item[0], item[1], item[2]["schedule"])):
        if any(x <= a+tol and y <= b+tol and (x < a-tol or y < b-tol) for x,y,_ in numeric):
            continue
        if not any(abs(float(r["fA"])-a) <= tol and abs(float(r["fB"])-b) <= tol for r in retained):
            retained.append(row)
    return retained


def main():
    configs = {label: read(p)["config"] for label, p in REFERENCES.items()}
    archived = []
    paths = subprocess.check_output(["rg", "--files", "--no-ignore", "-g", "schedule.json", "results"],
                                    cwd=JMS, encoding="utf-8").splitlines()
    for raw in sorted(paths):
        relative = Path(raw)
        if relative.parts[1] in (HERE.name, "square_reverse16_20261125", "pareto_enriched_20261125",
                                 "pareto_four_enriched_20261125"):
            continue
        path = JMS / relative
        if not path.with_name("assignment.json.gz").is_file():
            continue
        doc = read(path)
        for group, cfg in configs.items():
            if doc.get("config") == cfg:
                score = metrics(doc)
                archived.append(dict(group=group, schedule=relative.as_posix(), sha256=sha(path),
                                     fA=score["cmax"], fB=score["secondary"]))
    OUT.mkdir(exist_ok=True, parents=True)
    save_rows(OUT / "earlier_schedules.csv", archived)
    for group in configs:
        group_rows = [row for row in archived if row["group"] == group]
        print(group, len(group_rows), [key(r) for r in nondominated(group_rows)], flush=True)


if __name__ == "__main__":
    main()

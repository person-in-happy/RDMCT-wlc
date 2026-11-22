"""Replay archived Pareto assignment vectors and rescore historic sample tables."""
import csv
import sys
from pathlib import Path

import numpy as np

from objective import HERE, JMS, ROOT, physical_metrics, product_metrics

sys.path.insert(0, str(HERE.parent / "pareto_front_20261118"))
from slices import BACKEND, Config, Integrated, digest, inventory, read, validate


OUT = JMS / "results/product_wait_20261122/audit"
ARCHIVE = JMS / "results/pareto_front_20261118_r1"
REVIEW = JMS / "review/pareto_objectives_20261118"


def relative(path):
    return path.relative_to(ROOT).as_posix()


def csv_rows(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def write(name, rows):
    with (OUT / name).open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def measure(schedule):
    result = product_metrics(schedule)
    return dict(cmax=result["cmax"], product_secondary=result["secondary"],
                product_wait_sum=result["wait_sum"], product_wait_max=result["wait_max"],
                rhythm=result["rhythm"], all_secondary=physical_metrics(schedule)["secondary"])


def replay_vectors():
    rows = []
    for case in ("n2", "n4"):
        meta = read(ARCHIVE / case / "slices.json")
        assert all(digest(BACKEND / name) == h for name, h in meta["backend_hashes"].items())
        native = Integrated(Config(**meta["config"]))
        model = native.model
        variables = model.getVars(transformed=False)
        assert [v.name for v in variables] == meta["variables"]
        discrete, continuous = meta["discrete_indices"], meta["continuous_indices"]
        files = sorted((ARCHIVE / case).rglob("*.npz"))
        if case == "n4":
            files += sorted((HERE.parent / "pareto_rl_dmct_20261119/runs").rglob("*.npz"))
        for path in files:
            signature = digest(path)
            with np.load(path, allow_pickle=False) as src:
                if set(src.files) == {"v"}:
                    vectors = np.atleast_2d(src["v"])
                else:
                    dkey = "d" if "d" in src else "discrete"
                    vkey = next(k for k in src if k != dkey)
                    floats = np.atleast_2d(src[vkey])
                    vectors = np.empty((len(floats), len(variables)))
                    vectors[:, discrete] = src[dkey]
                    vectors[:, continuous] = floats
            for index, values in enumerate(vectors):
                assert len(values) == len(variables)
                sol = model.createSol()
                try:
                    for v, value in zip(variables, values):
                        model.setSolVal(sol, v, float(value))
                    if not model.checkSol(sol, printreason=False, completely=True, original=True):
                        raise ValueError(f"Invalid assignment {path} vertex {index}")
                    schedule = native.result(solution=sol)
                    check = validate(schedule)
                    if not check["valid"]:
                        raise ValueError((path, index, check["errors"]))
                    rows.append(dict(source=relative(path), vertex=index, sha256=signature,
                                     physical_checks=check["checks"], **measure(schedule)))
                finally:
                    model.freeSol(sol)
        model.freeProb()
    write("assignment_vector_scores.csv", rows)
    return {(r["source"], r["vertex"]): r for r in rows}


def main():
    vectors = replay_vectors()
    groups = {}
    for case in ("n2", "n4"):
        groups["observed_runs_" + case] = [
            (relative(folder / "result.json"), None) for folder in inventory(case)]
    groups["previous_s1_vertices"] = [(r["witness_path"], float(r["B_weighted_s"]))
                                      for r in csv_rows(REVIEW / "certified_s1_frontier.csv")]
    groups["mixed_feasible_points"] = [(r["source"], float(r["B_weighted_s"]))
                                      for r in csv_rows(REVIEW / "mixed_feasible_points.csv")]
    rows = []
    for group, entries in groups.items():
        local = []
        for name, old_b in entries:
            if "#vertex=" in name:
                source, index = name.split("#vertex=")
                score = vectors[(source, int(index))]
            else:
                path = ROOT / name
                if path.name == "evidence.json":
                    path = path.with_name("result.json")
                schedule = read(path)
                if not validate(schedule)["valid"]:
                    raise ValueError(name)
                score = measure(schedule)
                name = relative(path)
            if old_b is not None and abs(score["all_secondary"] - old_b) > 0.0002:
                raise ValueError((name, score["all_secondary"], old_b))
            local.append(dict(group=group, source=name,
                         **{k: score[k] for k in ("cmax","product_secondary","product_wait_sum",
                                                  "product_wait_max","rhythm","all_secondary")}))
        for row in local:
            a,b = (round(row[k], 4) for k in ("cmax", "product_secondary"))
            other_points = [(round(p["cmax"], 4), round(p["product_secondary"], 4)) for p in local]
            row["nondominated_within_listed_samples"] = not any(
                x <= a and y <= b and (x < a or y < b) for x,y in other_points)
        rows.extend(local)
    write("pareto_sample_scores.csv", rows)
    print(f"{len(vectors)} vector vertices and {len(rows)} referenced samples checked", flush=True)


if __name__ == "__main__":
    main()

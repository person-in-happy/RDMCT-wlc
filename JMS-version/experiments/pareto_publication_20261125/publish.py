"""Rebuild the displayed nondominated sets from the verified union, without pooling instances."""
from collections import Counter
import json
from pathlib import Path
import sys

from archive import HERE, JMS, OUT, RESULTS, REFERENCES, key, nondominated, read, records, save_rows, sha
from figure import FIG, draw

sys.path.insert(0, str(JMS / "tools"))
from verify_square_experiments_20261125 import physical

SOURCES = (
    (OUT/"earlier_schedules.csv", None),
    (RESULTS/"pareto_square_20261125/all_observations.csv", "mixed16"),
    (RESULTS/"pareto_four_enriched_20261125/pure4_observations.csv", "pure4"),
    (RESULTS/"pareto_enriched_20261125/observations_union.csv", "mixed16"),
    (RESULTS/"square_reverse16_20261125/candidates.csv", "mixed16"),
)


def get(row, *fields):
    return next(row[k] for k in fields if k in row and row[k] != "")


def merge_sources():
    inventories = {group:read(path)["config"] for group, path in REFERENCES.items()}
    paths = {}
    for source, label in SOURCES:
        for r in records(source):
            group = label or r["group"]
            p = JMS / get(r, "schedule", "schedule_path")
            entry = (group, get(r, "sha256", "schedule_sha256"),
                     float(get(r, "fA", "fa", "cmax")), float(get(r, "fB", "fb", "secondary")))
            if p in paths:
                old = paths[p]
                assert old[:2] == entry[:2] and max(abs(a-b) for a,b in zip(old[2:], entry[2:])) < 3e-5, p
            paths[p] = entry
    for cap in sorted((OUT/"sixteen_inside").glob("cap_*/result.json")):
        r = read(cap)
        assert r["status"] == "optimal" and r["original_rows"] == 1109436
        paths[cap.with_name("schedule.json")] = ("mixed16", r["files"]["schedule.json"],
                                                r["metrics"]["cmax"], r["metrics"]["secondary"])
    assert read(OUT/"sixteen_inside/progress.json")["completed"] == 11
    out = []
    for p, (group, fingerprint, a, b) in sorted(paths.items()):
        assert sha(p) == fingerprint and read(p)["config"] == inventories[group], p
        c, mean, spread, unused, score = physical(p)
        assert max(abs(c-a), abs(score-b)) < 3e-5, (p, c, score, a, b)
        out.append(dict(group=group, fA=c, fB=score, mean_residence=mean, residence_range=spread,
                        unused_cycles=unused, schedule=p.relative_to(JMS).as_posix(), sha256=fingerprint))
    return out


def native_replay(group, points):
    sys.path.insert(0, str(HERE.parent/"pareto_square_20261125"))
    from fixed import sweep
    cfg = sweep.Config(**read(REFERENCES[group])["config"])
    model = sweep.Integrated(cfg)
    solver = model.model
    native_rows = solver.getNConss()
    replayed = []
    for row in points:
        source = JMS/row["schedule"]
        assignment = source.with_name("assignment.json.gz")
        values = sweep.cell.values(assignment)
        sol = sweep.cell.solution(model, values)
        assert solver.checkSol(sol, original=True, completely=True), source
        doc = model.result(solution=sol)
        solver.freeSol(sol)
        replay = sweep.validate(doc)
        metric = sweep.metrics(doc)
        assert replay["valid"] and abs(metric["secondary"]-row["fB"]) < 3e-5
        assert abs(metric["cmax"]-row["fA"]) < 2e-5
        replayed.append(dict(row, assignment_sha256=sha(assignment), model_rows=native_rows,
                             physical_checks=replay["checks"]))
    solver.freeProb()
    return replayed


def main():
    data = merge_sources()
    fronts = {}
    summary = {}
    for group in REFERENCES:
        observed = [r for r in data if r["group"] == group]
        front = nondominated(observed)
        coords = set(map(key, observed))
        assert all(u["fA"]+1e-5 < v["fA"] and u["fB"] > v["fB"]+1e-5 for u,v in zip(front, front[1:]))
        front = native_replay(group, front)
        save_rows(OUT / f"{group}_front.csv", front)
        fronts[group] = front
        summary[group] = dict(raw_observations=len(observed), unique_vectors=len(coords), nondominated=len(front),
                              first=[front[0]["fA"], front[0]["fB"]], last=[front[-1]["fA"], front[-1]["fB"]],
                              source_runs=dict(Counter(Path(r["schedule"]).parts[1] for r in observed)))
    assert all(abs(r["fB"]-(457.625-30.125*(r["fA"]-810)+.5*(r["fA"]-810)**2)) < 3e-5
               for r in fronts["mixed16"] if r["fA"] <= 811.00001)
    assert abs(fronts["pure4"][-1]["fB"]-6.71875) < 3e-5
    assert abs(fronts["mixed16"][-1]["fB"]-3.404296875) < 3e-5
    summary["mixed16"]["above_811"] = sum(r["fA"] > 811.00001 for r in fronts["mixed16"])
    summary["pure4"]["above_417"] = sum(r["fA"] > 417.00001 for r in fronts["pure4"])
    baseline = [(float(r["cmax"]), float(r["secondary"])) for r in records(RESULTS/"pareto_square_20261125/sixteen_pareto.csv")]
    summary["mixed16"]["new_past_811"] = sum(r["fA"] > 811.00001 and
        not any(abs(a-r["fA"])<=1e-5 and abs(b-r["fB"])<=1e-5 for a,b in baseline) for r in fronts["mixed16"])
    save_rows(OUT/"sample_union.csv", data)
    draw(fronts["pure4"], fronts["mixed16"])
    summary.update(figure=FIG.relative_to(JMS).as_posix(), figure_sha256=sha(FIG),
                   dominance_tolerance=1e-5, certificate_sha256=sha(RESULTS/"pareto_square_20261125/certificate.json"),
                   pure4_certificate_sha256=sha(RESULTS/"pareto_four_enriched_20261125/pure4_certificate.json"),
                   source_hashes={p.relative_to(JMS).as_posix():sha(p) for p, group in SOURCES},
                   outputs={n:sha(OUT/n) for n in ("mixed16_front.csv", "pure4_front.csv", "sample_union.csv","displayed_curves.json")})
    (OUT/"validation.json").write_text(json.dumps(summary, indent=2), encoding="utf8")
    print(json.dumps({g:summary[g] for g in REFERENCES}, indent=2))


if __name__ == "__main__":
    main()

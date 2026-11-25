"""Rebuild the nine-instance threshold grid and check the current Chinese manuscript."""
import csv
import json
import sys
from itertools import product
from pathlib import Path
from statistics import mean

HERE = Path(__file__).resolve().parent
JMS = HERE.parents[1]
sys.path.insert(0, str(HERE.parent / "huber_residence_20261125"))
from verify_manuscript import audit, digest, independent, verify_front_and_figures

RESULTS = JMS / "results"
OLD = RESULTS / "huber_residence_20261125/supplement"
OUT = RESULTS / "table3_grid8_20261125"
LEVELS = {"10pct": .1, "1pct": .01, "0p01pct": .0001}
NEW_CASES = ("D_n8_pure_4x1", "D_n8_pure_2x2", "D_n8_H10_mixed_dual")
OLD_CASES = ("D_n2_4x1_scenario1", "D_n2_pure_2x2", "D_n2_mixed_scenario3", "pure", "D_n4_pure_2x2", "mixed")


def get_grid():
    manifest = audit.read(OLD / "manifest.json")
    inputs = [OLD / "threshold_cells.csv"]
    inputs += [RESULTS / "table3_pure8_20261125/certified" / recipe / "threshold_cells.csv"
               for recipe in ("4x1", "2x2")]
    inputs.append(RESULTS / "table3_mixed8_20261125/archived_stream/threshold_cells.csv")
    grid = {}
    for path in inputs:
        for row in audit.csv_rows(path):
            key = (row["case"], row["gA"], row["gB"])
            assert key not in grid
            if path == inputs[0]:
                ref = manifest[row["name"]]
                a = ref["primary"]
                assert a["gate"] and ref["settings"]["seed"] == 1
                a_hash = ref["settings"]["schedule"]
                assert digest(JMS.parent / ref["source"] / ref["schedule"]) == a_hash
                folder = OLD / row["source"]
            else:
                a_path = JMS / row["A_proof"] if "A_proof" in row else JMS / row["A_source"] / "primary.json"
                raw_a = audit.read(a_path)
                a = raw_a.get("record", raw_a)
                assert raw_a["replay"]["valid"] and a["seed"] == 1
                a_hash = raw_a["schedule_sha256"]
                assert digest(a_path.parent / "schedule.json") == a_hash
                if "A_sha256" in row:
                    assert digest(a_path) == row["A_sha256"]
                folder = JMS / row["source"]
            p = folder / "schedule.json"
            physical_schedule = audit.read(p)
            physical = independent(physical_schedule)
            b = audit.read(folder / "result.json")
            assert b["eligible"] and b["replay"]["valid"] and b["seed"] == 1
            assert b["replayed_rows"] == b["original_rows"] > 0
            for filename, expected in b["files"].items():
                assert digest(folder / filename) == expected
            assert b["parents"][0]["schedule_sha256"] == a_hash
            assert b["files"]["schedule.json"] == row.get("schedule_sha256", b["files"]["schedule.json"])
            audit.check_fields(physical, row, {"cmax":"f_A", "secondary":"f_B", "mean_residence":"mean",
                                              "residence_range":"spread", "clean_deficit":"E" if "E" in row else "clean_deficit"})
            if key[0] in NEW_CASES:
                cfg = physical_schedule["config"]
                assert cfg["cleaning_interval"] == 10 and cfg["dummy_count"] == 8 and cfg["horizon"] == 100000
                assert len(cfg["load_ports"]) == 4 and all(sum(s.values()) == 2 for s in cfg["load_ports"].values())
            r = b["record"]
            for stage, bounds, target in (("A",a,LEVELS[key[1]]),("B",r,LEVELS[key[2]])):
                lb, ub = bounds["lower"], bounds["upper"]
                assert lb <= ub+2e-5 and ub-lb <= target*abs(lb)+2e-5, (key, stage, lb, ub)
                assert bounds["gap"] <= target+1e-7
            assert abs(physical["cmax"]-a["upper"]) < 2e-4 and abs(physical["secondary"]-r["upper"]) < 2e-4
            grid[key] = dict(case=key[0], gA=key[1], gB=key[2], seed=b["seed"], f_A=physical["cmax"],
                             f_B=physical["secondary"], mean=physical["mean_residence"], spread=physical["residence_range"],
                             clean_deficit=physical["clean_deficit"], huber=physical["huber_penalty"],
                             A_lower=a["lower"], A_upper=a["upper"], A_gap=a["gap"],
                             B_lower=r["lower"], B_upper=r["upper"], B_gap=r["gap"],
                             schedule_path=p.relative_to(JMS).as_posix(), schedule_sha256=b["files"]["schedule.json"],
                             primary_schedule_sha256=a_hash, source_csv=path.relative_to(JMS).as_posix())
    assert set(grid) == set(product(OLD_CASES+NEW_CASES, LEVELS, LEVELS))
    for c, a in product(OLD_CASES+NEW_CASES, LEVELS):
        assert len({grid[c,a,b]["primary_schedule_sha256"] for b in LEVELS}) == 1
    return grid


def summarize(grid, cases=OLD_CASES + NEW_CASES):
    ranking = []
    for a,b in product(LEVELS,repeat=2):
        means = {}
        for obj in ("f_A","f_B"):
            ratios = []
            for c in cases:
                best = min(grid[c,i,j][obj] for i,j in product(LEVELS,repeat=2))
                ratios.append(grid[c,a,b][obj] / max(1,best))
            means[obj] = round(mean(ratios), 6)
        ranking.append(dict(gA=a, gB=b, **means))
    choice = min(ranking, key=lambda r:(r["f_A"],r["f_B"],-LEVELS[r["gA"]],-LEVELS[r["gB"]]))
    cases_with_tradeoff = []
    for c in cases:
        for a,a2 in zip(LEVELS,list(LEVELS)[1:]):
            if any(grid[c,a,b]["f_A"] > grid[c,a2,b]["f_A"]+2e-4 and
                   grid[c,a2,b]["f_B"] > grid[c,a,b]["f_B"]+2e-4 for b in LEVELS):
                cases_with_tradeoff.append(c)
                break
    return ranking, choice, cases_with_tradeoff


def write_csv(path, rows):
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main():
    grid = get_grid()
    ranking, choice, shown = summarize(grid)
    assert shown == ["D_n4_pure_2x2", *NEW_CASES[:2]]
    assert (choice["gA"], choice["gB"]) == ("0p01pct", "1pct")
    order = list(product(OLD_CASES+NEW_CASES, LEVELS, LEVELS))
    write_csv(OUT/"threshold_cells.csv", [grid[k] for k in order])
    write_csv(OUT/"normalized_means.csv", ranking)
    audit.independent = independent
    summary = OUT/"manuscript_validation.json"
    audit.main(False, True, extra_grid=[grid[k] for k in order if k[0] in NEW_CASES], extra_cases=NEW_CASES,
               display_cases=shown, with_hit_column=False, validation_path=summary)
    findings = audit.read(summary) | verify_front_and_figures()
    findings.update(selected_thresholds=choice, displayed_cases=shown,
                    full_grid_sha256=digest(OUT/"threshold_cells.csv"), pdf_sha256=digest(JMS/"JMS_Review_CN.pdf"))
    summary.write_text(json.dumps(findings,indent=2)+"\n",encoding="utf8")
    print(json.dumps(findings,indent=2))


if __name__ == "__main__":
    main()

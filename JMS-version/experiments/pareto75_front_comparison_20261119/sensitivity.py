"""Descriptive sensitivity on frozen checkpoints. The confirmatory tests stay at 160 evaluations."""
from statistics import median

from analysis_fronts import REPORT, csvrows, hv, nd, table
from case_setup import CASES, OUT, read
from mechanism import ARMS, MOUT, MSEEDS
from trial import exported


def area(points, limits, reference):
    normal = [((a-limits[0][0])/(limits[0][1]-limits[0][0]),
               (b-limits[1][0])/(limits[1][1]-limits[1][0])) for a, b in nd(points)]
    assert all(x < 1 and y < 1 for x, y in normal)
    next_b = reference
    score = 0
    for x, y in normal:
        score += (reference-x)*(next_b-y)
        next_b = y
    if reference == 1.1:
        assert abs(score-hv(points, limits)) < 1e-10
    return score


def main():
    held = {(r["case"],r["method"],int(r["seed"])): float(r["HV"])
            for r in csvrows(REPORT / "ablation_runs.csv")}
    results = []
    for case in CASES:
        bounds = read(OUT / "shared" / (case+".json"))["bounds"]
        runs = {(method, seed): read(MOUT / case / f"{method}_{seed}" / "run.json")
                for method in ARMS for seed in MSEEDS}
        for evaluations, reference in [(12,1.1),(40,1.1),(80,1.1),(160,1.1),(160,1.0),(160,1.2)]:
            scores = {}
            for (method,seed), run in runs.items():
                points = list(map(tuple, run["checkpoints"][str(evaluations)]))
                assert points == nd(points)
                scores[method,seed] = area(exported(points), bounds, reference)
                if (evaluations,reference)==(160,1.1):
                    assert abs(scores[method,seed]-held[case,method,seed])<1e-10
            for opponent in ("no_blocks","random_init"):
                diffs = [scores["full",s]-scores[opponent,s] for s in MSEEDS]
                results.append(dict(case=case,opponent=opponent,evaluations=evaluations,reference=reference,
                    median_delta=median(diffs),wins=sum(v>1e-10 for v in diffs),
                    ties=sum(abs(v)<=1e-10 for v in diffs),losses=sum(v< -1e-10 for v in diffs)))
    table(REPORT/"sensitivity.csv",results)
    for r in results:
        if r["opponent"]=="no_blocks":
            print(r["case"],r["evaluations"],r["reference"],r["wins"],r["ties"],r["losses"],round(r["median_delta"],5))


if __name__ == "__main__":
    main()

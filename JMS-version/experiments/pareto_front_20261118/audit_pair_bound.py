"""Replay the nominal dual-source pair bound and the supported-point HV on saved schedules."""
import argparse
import csv
import hashlib
import json
import sys
from collections import Counter, defaultdict
from fractions import Fraction
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
JMS = ROOT / "JMS-version"
REVIEW = JMS / "review/pareto_objectives_20261118"
FRONT = JMS / "results/pareto_front_20261118_r1"
sys.path.insert(0, str(JMS / "experiments/finite_budget_20261116"))
from finite_budget import physical_metrics

TOL = 2e-5


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def wait_bounds(pp, pd):
    """Necessary lower bounds in the nominal dual-source model."""
    total = 28 * pp + 6 * pd
    longest = max(28 / 3 if pp else 0, 3 if pd else 0)
    return total, longest, total + 10 * longest


def admissible_pp_counts(products, cap):
    return [p for p in range(products // 2 + 1)
            if wait_bounds(p, products - 2 * p)[2] <= cap + TOL]


def check_schedule(path, expected_hash=None):
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    data = json.loads(raw.decode("utf-8-sig"))
    cfg = data["config"]
    if expected_hash is not None and digest != expected_hash:
        raise ValueError(f"{path}: certificate witness hash changed")
    if not data["validation"]["valid"] or cfg["source"] != "dual":
        raise ValueError(f"{path}: requires a validated dual-source schedule")
    if (cfg["atr_handling"], cfg["alignment"], cfg["handling"], cfg["vtr_travel"]) != (4, 20, 1, 2):
        raise ValueError(f"{path}: timings differ from the nominal proposition")
    by_pair = defaultdict(list)
    by_job = defaultdict(dict)
    for job in data["jobs"]:
        by_pair[job["pair"]].append(job)
    for event in data["events"]:
        if "job" in event:
            by_job[event["job"]][event["kind"]] = event

    def at_least(value, bound, label):
        if value + TOL < bound:
            raise ValueError(f"{path}: {label} = {value} < {bound}")

    pp = pd = 0
    for pair, jobs in by_pair.items():
        if len(jobs) != 2:
            raise ValueError(f"{path}: expected two wafer routes in pair {pair}")
        if any(abs(jobs[0][t] - jobs[1][t]) > TOL for t in ("load_start", "unload_end")):
            raise ValueError(f"{path}: pair {pair} does not share its load/unload time")
        products = [j for j in jobs if j["product"]]
        if len(products) == 2:
            pp += 1
            early, late = sorted(products, key=lambda j: by_job[j["name"]]["al_pick"]["end"])
            e = by_job[early["name"]]
            at_least(by_job[late["name"]]["al_pick"]["end"] - e["al_pick"]["end"], 28, "AL gap")
            waits = (e["upper_put"]["start"] - e["al_pick"]["end"] - cfg["atr_travel"],
                     e["source_pick"]["start"] - e["upper_put"]["end"] - cfg["pump"],
                     early["load_start"] - e["source_pick"]["end"] - cfg["vtr_travel"])
            at_least(sum(waits), 28, "PP wait sum")
            at_least(max(waits), 28 / 3, "PP wait maximum")
        elif len(products) == 1:
            pd += 1
            events = [by_job[j["name"]] for j in jobs]
            if ({e["source_pick"]["location"] for e in events} != {"U", "VS"}
                    or {e["destination_put"]["location"] for e in events} != {"L", "VS"}):
                raise ValueError(f"{path}: pair {pair} does not use the specified routes")
            inbound = [j["load_start"] - e["source_pick"]["end"] - cfg["vtr_travel"]
                       for j, e in zip(jobs, events)]
            outbound = [e["destination_put"]["start"] - j["unload_end"] - cfg["vtr_travel"]
                        for j, e in zip(jobs, events)]
            at_least(max(inbound), 3, "PD inbound wait")
            at_least(max(outbound), 3, "PD outbound wait")
    metrics = physical_metrics(data)
    sum_bound, max_bound, bound = wait_bounds(pp, pd)
    at_least(metrics["wait_sum"], sum_bound, "total wait")
    at_least(metrics["wait_max"], max_bound, "maximum wait")
    at_least(metrics["secondary"], bound, "B")
    return {"path": path.relative_to(ROOT).as_posix(), "sha256": digest, "products": 2 * pp + pd,
            "PP": pp, "PD": pd, "B_lower_bound": bound, **metrics}


def supported(points, point):
    """A positive ratio w_A / w_B must meet every comparison simultaneously."""
    a, b = point
    lower, upper = Fraction(0), None
    for x, y in points:
        if x > a:
            lower = max(lower, (b - y) / (x - a))
        if x < a:
            cap = (y - b) / (a - x)
            upper = cap if upper is None else min(upper, cap)
    return upper is None or (upper > 0 and lower <= upper)


def front_summary(rows):
    points = sorted((Fraction(r["Cmax_s"]), Fraction(r["B_fraction"])) for r in rows)
    subset = [point for point in points if supported(points, point)]
    min_a, max_b = points[0]
    max_a, min_b = points[-1]
    ref = Fraction(11, 10)

    def hv(front):
        total, previous_y = Fraction(), ref
        for a, b in front:
            x = (a - min_a) / (max_a - min_a)
            y = (b - min_b) / (max_b - min_b)
            total += (ref - x) * (previous_y - y)
            previous_y = y
        return total

    all_hv, supported_hv = hv(points), hv(subset)
    return {"points": len(points), "supported": [[str(a), str(b)] for a, b in subset],
            "unsupported": [[str(a), str(b)] for a, b in points if (a, b) not in subset],
            "normalization_A": [str(min_a), str(max_a)], "normalization_B": [str(min_b), str(max_b)],
            "normalized_reference": [1.1, 1.1], "HV_all": float(all_hv),
            "HV_supported": float(supported_hv), "ratio": float(supported_hv / all_hv),
            "lexicographic_A_B_at_B_cap_100": [str(v) for v in min(p for p in points if p[1] <= 100)]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="Save the JSON report (default: write to stdout)")
    args = parser.parse_args()
    with (REVIEW / "certified_s1_frontier.csv").open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    schedules = [(r["witness_path"], "S1_certificate", r["witness_sha256"]) for r in rows]
    endpoints = FRONT / "n4/endpoint_search/results.json"
    for entry in read_json(endpoints):
        if entry["name"] in ("chain_orders", "global_makespan_at_54"):
            schedules.extend((endpoints.parent / v["schedule"], "n4_slice_vertices", None)
                             for v in entry["vertices"])
    runs = JMS / "results/finite_budget_20261116_r1/runs"
    schedules.extend((p, p.parent.name.split("__")[0], None) for p in sorted(runs.glob("D_*/result.json")))
    results = []
    for path, group, digest in schedules:
        results.append({"group": group, **check_schedule(ROOT / path, digest)})
    for row, witness in zip(rows, results):
        if (abs(witness["cmax"] - float(row["Cmax_s"])) > TOL
                or abs(witness["secondary"] - float(Fraction(row["B_fraction"]))) > TOL):
            raise ValueError(f"{witness['path']}: objectives differ from certificate")
    groups = Counter(r["group"] for r in results)
    pairings = Counter((r["products"], r["PP"], r["PD"]) for r in results)
    report = {"tolerance": TOL, "schedule_files": len(results), "by_group": dict(sorted(groups.items())),
              "by_pair_count": [{"N": n, "PP": p, "PD": d, "files": count}
                                for (n, p, d), count in sorted(pairings.items())],
              "minimum_B_slack": min(r["secondary"] - r["B_lower_bound"] for r in results),
              "attains_bound_files": sum(abs(r["secondary"] - r["B_lower_bound"]) <= TOL for r in results),
              "positive_rhythm_files": sum(r["rhythm"] > TOL for r in results),
              "screen_examples": [{"N": n, "B_cap": cap, "surviving_PP_counts": admissible_pp_counts(n, cap)}
                                  for n, cap in ((2, 100), (4, 100), (4, 140))],
              "S1_front": front_summary(rows), "records": results}
    content = json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False)
    if args.output:
        args.output.write_text(content + "\n", encoding="utf-8")
        print(json.dumps({k: v for k, v in report.items() if k != "records"}, ensure_ascii=False))
    else:
        print(content)


if __name__ == "__main__":
    main()

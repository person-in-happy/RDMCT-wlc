"""Create instance-level C&IE tables and paired significance tests."""

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
from collections import defaultdict
from pathlib import Path

from scipy.stats import wilcoxon


METRICS = ("primal_dual_integral", "gap", "solving_time")


def _finite(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _variant(row):
    method = str(row.get("method", "unknown"))
    label = str(row.get("run_label") or "")
    if label.startswith("stability_"):
        return f"{method}[{row.get('stability_profile', 'full')}]"
    if label.startswith("spbs_") or label == "manufacturing_doe":
        return f"{method}[{label}]"
    return method


def _holm(records):
    indexed = sorted(
        ((index, record["p_value"]) for index, record in enumerate(records)
         if record["p_value"] is not None),
        key=lambda item: item[1],
    )
    running = 0.0
    count = len(indexed)
    for rank, (index, p_value) in enumerate(indexed):
        adjusted = min(1.0, (count - rank) * p_value)
        running = max(running, adjusted)
        records[index]["p_holm"] = running


def _args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input_dir", required=True)
    parser.add_argument("--output_dir", required=True)
    parser.add_argument("--reference_method", default="proposed")
    return parser.parse_args()


def main():
    args = _args()
    raw = []
    sources = []
    for path in sorted(Path(args.input_dir).resolve().rglob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(payload, dict) and isinstance(payload.get("rows"), list):
            sources.append(str(path))
            raw.extend(payload["rows"])
    if not raw:
        raise RuntimeError("No benchmark JSON containing raw rows was found")

    # Combined and per-run JSON files may contain the same observation.
    unique = {}
    for row in raw:
        key = (
            row.get("suite"), row.get("path"), row.get("method"), row.get("seed"),
            row.get("training_seed"), row.get("run_label"), row.get("warm_start"),
        )
        unique[key] = row

    grouped = defaultdict(lambda: defaultdict(list))
    for row in unique.values():
        instance_key = (str(row.get("suite")), str(row.get("path")))
        for metric in METRICS:
            value = _finite(row.get(metric))
            if value is not None:
                grouped[(instance_key, _variant(row))][metric].append(value)

    instance_rows = []
    for ((suite, path), method), metric_values in sorted(grouped.items()):
        result = {"suite": suite, "path": path, "instance": Path(path).name, "method": method}
        for metric in METRICS:
            values = metric_values.get(metric, [])
            result[metric] = statistics.fmean(values) if values else None
            result[f"n_{metric}"] = len(values)
        instance_rows.append(result)

    by_method = defaultdict(dict)
    for row in instance_rows:
        key = (row["suite"], row["path"])
        by_method[row["method"]][key] = row
    reference = by_method.get(args.reference_method, {})
    tests = []
    if reference:
        for method, candidates in sorted(by_method.items()):
            if method == args.reference_method:
                continue
            for metric in METRICS:
                pairs = []
                for key in sorted(set(reference) & set(candidates)):
                    left = _finite(reference[key].get(metric))
                    right = _finite(candidates[key].get(metric))
                    if left is not None and right is not None:
                        pairs.append((left, right))
                p_value = None
                if len(pairs) >= 5 and any(abs(a - b) > 1e-12 for a, b in pairs):
                    p_value = float(wilcoxon(
                        [a for a, _ in pairs], [b for _, b in pairs],
                        alternative="two-sided", zero_method="wilcox",
                    ).pvalue)
                tests.append({
                    "reference": args.reference_method, "comparison": method,
                    "metric": metric, "n_instances": len(pairs),
                    "reference_mean": statistics.fmean(a for a, _ in pairs) if pairs else None,
                    "comparison_mean": statistics.fmean(b for _, b in pairs) if pairs else None,
                    "p_value": p_value, "p_holm": None,
                })
        _holm(tests)

    output = Path(args.output_dir).resolve()
    output.mkdir(parents=True, exist_ok=True)
    table_path = output / "cie_instance_level_metrics.csv"
    fields = ["suite", "instance", "path", "method"] + [
        field for metric in METRICS for field in (metric, f"n_{metric}")
    ]
    with table_path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(instance_rows)
    tests_path = output / "cie_instance_level_significance.json"
    tests_path.write_text(json.dumps({
        "sources": sources, "raw_unique_runs": len(unique),
        "aggregation_unit": "manufacturing instance",
        "reference_method": args.reference_method, "tests": tests,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    report = output / "cie_instance_level_report.md"
    report.write_text(
        "# C&IE instance-level analysis\n\n"
        f"- Unique solver runs: `{len(unique)}`\n"
        f"- Instance-method rows: `{len(instance_rows)}`\n"
        "- Repetitions are averaged within each manufacturing instance before paired tests.\n"
        "- Paired Wilcoxon tests use Holm correction across reported comparisons.\n"
        f"- Table: `{table_path}`\n- Significance: `{tests_path}`\n",
        encoding="utf-8",
    )
    print(f"Instance table: {table_path}")
    print(f"Significance: {tests_path}")
    print(f"Report: {report}")


if __name__ == "__main__":
    main()

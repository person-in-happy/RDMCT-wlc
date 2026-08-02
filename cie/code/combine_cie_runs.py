"""Combine per-training-seed CIE benchmark JSON files into one report."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime
from pathlib import Path

CIE_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = CIE_ROOT.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from run_cie_benchmarks import (
    _aggregate,
    _paired_significance,
    _write_report,
)


def _write_csv(path, rows):
    """Write rows whose schemas may differ across resumed campaign versions."""

    if not rows:
        return
    fieldnames = []
    seen = set()
    for row in rows:
        for key in row:
            if key not in seen:
                seen.add(key)
                fieldnames.append(key)
    with open(path, "w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            serializable = {
                key: json.dumps(value, ensure_ascii=False)
                if isinstance(value, (dict, list))
                else value
                for key, value in row.items()
            }
            writer.writerow(serializable)


def _normalized_run_label(row):
    """Return the experimental-condition label used for deduplication.

    Learned campaigns historically repeated fixed SCIP/ACS baselines once per
    training seed and labelled those copies "trainseed_N". Those labels do not
    describe different baseline conditions and must remain deduplicated. Other
    labels, notably "spbs_none" and "spbs_auto", identify distinct experimental
    conditions and therefore must be retained.
    """

    label = str(row.get("run_label") or "")
    prefix = "trainseed_"
    if label.startswith(prefix) and label[len(prefix):].isdigit():
        return ""
    return label


def _deduplicate_rows(rows):
    """Deduplicate reruns without collapsing distinct experiment conditions."""

    deduplicated = []
    seen = set()
    for row in rows:
        condition = (
            row.get("stability_profile", "full"),
            row.get("warm_start", ""),
            _normalized_run_label(row),
        )
        if row["method"] in {"scip_default", "adaptive_cutsel"}:
            key = (
                row["method"],
                row["path"],
                row["seed"],
                *condition,
            )
        else:
            key = (
                row["method"],
                row["path"],
                row["seed"],
                row.get("training_seed", -1),
                *condition,
            )
        if key in seen:
            continue
        seen.add(key)
        deduplicated.append(row)
    return deduplicated


def _parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input_dir", default=str(CIE_ROOT / "results" / "main" / "runs"))
    parser.add_argument("--output_dir", default=str(CIE_ROOT / "results" / "main" / "combined"))
    parser.add_argument(
        "--recursive",
        action="store_true",
        help="Find benchmark JSON files recursively under input_dir (for parallel shards).",
    )
    return parser.parse_args()


def main():
    args = _parse_args()
    input_dir = Path(args.input_dir).resolve()
    finder = input_dir.rglob if args.recursive else input_dir.glob
    files = sorted(set(finder("cie_benchmark*.json")))
    if not files:
        raise RuntimeError(f"No benchmark JSON files found in {input_dir}")

    rows = []
    source_meta = []
    for path in files:
        with open(path, "r", encoding="utf-8") as stream:
            payload = json.load(stream)
        if "rows" not in payload or "meta" not in payload:
            continue
        rows.extend(payload["rows"])
        source_meta.append({"file": str(path), "meta": payload["meta"]})

    # SCIP and ACS do not depend on a learned-policy training seed, but their
    # warm-start and labelled experimental conditions still matter. In
    # particular, SPBS none/auto rows must both survive the merge.
    deduplicated = _deduplicate_rows(rows)

    summary = _aggregate(deduplicated)
    significance = _paired_significance(deduplicated)
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    prefix = output_dir / f"cie_combined_{timestamp}"
    methods = sorted({row["method"] for row in deduplicated})
    solver_seeds = sorted({int(row["seed"]) for row in deduplicated})
    training_seeds = sorted(
        {
            int(row.get("training_seed", -1))
            for row in deduplicated
            if row["method"] in {
                "hem",
                "hem_beam",
                "hem_structure",
                "a3c",
                "beam_search",
                "proposed",
                "rdmct_feature_only",
                "rdmct_a3c",
            }
        }
    )
    meta = {
        "methods": methods,
        "seeds": solver_seeds,
        "training_seeds": training_seeds,
        "stability_profiles": sorted(
            {row.get("stability_profile", "full") for row in deduplicated}
        ),
        "stability_profile": (
            next(iter({row.get("stability_profile", "full") for row in deduplicated}))
            if len({row.get("stability_profile", "full") for row in deduplicated}) == 1
            else "mixed"
        ),
        "time_limit": source_meta[0]["meta"].get("time_limit"),
        "instance_count": len({row["path"] for row in deduplicated}),
        "empty_suites": [],
        "source_runs": source_meta,
    }
    with open(f"{prefix}.json", "w", encoding="utf-8") as stream:
        json.dump(
            {
                "meta": meta,
                "summary": summary,
                "paired_significance": significance,
                "rows": deduplicated,
            },
            stream,
            ensure_ascii=False,
            indent=2,
        )
    _write_csv(f"{prefix}_raw.csv", deduplicated)
    _write_csv(f"{prefix}_summary.csv", summary)
    _write_report(f"{prefix}.md", meta, summary, significance)
    print(f"Combined JSON: {prefix}.json")
    print(f"Combined raw CSV: {prefix}_raw.csv")
    print(f"Combined summary CSV: {prefix}_summary.csv")
    print(f"Combined report: {prefix}.md")


if __name__ == "__main__":
    main()

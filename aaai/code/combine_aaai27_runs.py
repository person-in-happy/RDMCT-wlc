"""Combine per-training-seed AAAI benchmark JSON files into one report."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

AAAI_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = AAAI_ROOT.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from run_aaai27_benchmarks import (
    _aggregate,
    _paired_significance,
    _write_csv,
    _write_report,
)


def _parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input_dir", default=str(AAAI_ROOT / "results" / "final_benchmark" / "runs"))
    parser.add_argument("--output_dir", default=str(AAAI_ROOT / "results" / "final_benchmark" / "combined"))
    return parser.parse_args()


def main():
    args = _parse_args()
    input_dir = Path(args.input_dir).resolve()
    files = sorted(input_dir.glob("aaai27_benchmark*.json"))
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

    # SCIP and ACS do not depend on a learned-policy training seed. Keep one
    # record per instance/SCIP-seed instead of counting the repeated baseline
    # runs once for every checkpoint pair.
    deduplicated = []
    seen = set()
    for row in rows:
        if row["method"] in {"scip_default", "adaptive_cutsel"}:
            key = (row["method"], row["path"], row["seed"])
        else:
            key = (
                row["method"],
                row["path"],
                row["seed"],
                row.get("training_seed", -1),
            )
        if key in seen:
            continue
        seen.add(key)
        deduplicated.append(row)

    summary = _aggregate(deduplicated)
    significance = _paired_significance(deduplicated)
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    prefix = output_dir / f"aaai27_combined_{timestamp}"
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

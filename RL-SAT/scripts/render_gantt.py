#!/usr/bin/env python3
"""Render the original-project-compatible interactive Gantt from result JSON."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


RL_SAT_ROOT = Path(__file__).resolve().parents[1]
if str(RL_SAT_ROOT) not in sys.path:
    sys.path.insert(0, str(RL_SAT_ROOT))

from rl_sat.gantt import render_gantt_bundle  # noqa: E402
from rl_sat.petri_gantt import generate_gantt_charts_from_solution_file  # noqa: E402
from rl_sat.result_io import read_result_json  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Generate the same full-flow, chamber, and resource views and "
            "interactive index as the original project."
        )
    )
    parser.add_argument("result", type=Path, help="Path to result/ablation JSON")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Destination directory (default: <input stem>_gantt)",
    )
    parser.add_argument(
        "--view",
        choices=["full", "chambers", "resources", "all"],
        default="all",
    )
    parser.add_argument(
        "--comparison-svg",
        type=Path,
        default=None,
        help="Optional comparison SVG embedded in index.html.",
    )
    parser.add_argument(
        "--simple",
        action="store_true",
        help="Render the earlier RL-SAT overview/resource/product bundle instead.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    source = args.result.resolve()
    if not source.is_file():
        raise SystemExit(f"Result file does not exist: {source}")
    destination = (
        args.output_dir.resolve()
        if args.output_dir is not None
        else source.with_name(source.stem + "_gantt")
    )
    if args.simple:
        outputs = render_gantt_bundle(read_result_json(source), destination)
    else:
        outputs = {
            "renderer": "rl_sat.petri_gantt",
            "generated": generate_gantt_charts_from_solution_file(
                str(source),
                str(destination),
                view=args.view,
                comparison_svg=(
                    str(args.comparison_svg.resolve())
                    if args.comparison_svg is not None
                    else ""
                ),
            ),
            "output_dir": str(destination),
        }
    print(json.dumps(outputs, ensure_ascii=False, indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())

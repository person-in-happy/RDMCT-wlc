#!/usr/bin/env python3
"""Solve one wafer-cluster-tool instance with A3C/beam + CP-SAT."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


RL_SAT_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = RL_SAT_ROOT.parent
if str(RL_SAT_ROOT) not in sys.path:
    sys.path.insert(0, str(RL_SAT_ROOT))

from rl_sat.config import load_config  # noqa: E402
from rl_sat.gantt import render_gantt_bundle  # noqa: E402
from rl_sat.hybrid_solver import HybridRLSATSolver  # noqa: E402
from rl_sat.petri_gantt import generate_gantt_charts_from_solution_file  # noqa: E402
from rl_sat.result_io import result_to_dict, write_result_json  # noqa: E402


def _default_output_dir(config) -> Path:
    configured = Path(config.output.output_dir)
    if configured.is_absolute():
        return configured
    if configured.parts and configured.parts[0].lower() == "rl-sat":
        return PROJECT_ROOT / configured
    return RL_SAT_ROOT / configured


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run the SCIP-free initial+A3C+beam+CP-SAT scheduling pipeline."
        )
    )
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--checkpoint", type=Path, default=None)
    parser.add_argument(
        "--warm-start-sol",
        type=Path,
        default=None,
        help="Optional legacy .sol used only to verify canonical assignments.",
    )
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--no-gantt", action="store_true")
    parser.add_argument(
        "--no-original-gantt",
        action="store_true",
        help=("Skip the vendored Petri Gantt compatible with the original project. " "The flag name is retained for command compatibility."),
    )
    return parser


def _render_compatible_gantt(result_json: Path, output_dir: Path):
    generated = generate_gantt_charts_from_solution_file(
        str(result_json),
        str(output_dir),
        view="all",
    )
    return {
        "status": "COMPLETED" if generated else "EMPTY",
        "renderer": "rl_sat.petri_gantt",
        "generated": generated,
        "output_dir": str(output_dir),
    }
def main() -> int:
    args = build_parser().parse_args()
    config = load_config(args.config)
    output_dir = (
        args.output_dir.resolve()
        if args.output_dir is not None
        else _default_output_dir(config).resolve()
    )
    output_dir.mkdir(parents=True, exist_ok=True)

    solver = HybridRLSATSolver(
        config,
        checkpoint=args.checkpoint,
        legacy_solution=args.warm_start_sol,
        device=args.device,
    )
    result = solver.solve()
    result.metadata.setdefault("instance", config.output.run_name)
    result.metadata.setdefault("run_name", config.output.run_name)
    result.metadata.setdefault("config", config.to_dict())
    result_json = write_result_json(result, output_dir / "result.json")
    payload = result_to_dict(result)

    artifacts = {"result_json": str(result_json)}
    if config.output.write_legacy_solution_json:
        legacy_path = output_dir / "legacy_solution.json"
        legacy_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
            encoding="utf-8",
        )
        artifacts["legacy_solution_json"] = str(legacy_path)

    if config.output.render_gantt and not args.no_gantt and result.feasible:
        artifacts["gantt"] = render_gantt_bundle(result, output_dir / "gantt")
        if not args.no_original_gantt:
            artifacts["original_petri_gantt"] = _render_compatible_gantt(
                result_json,
                output_dir / "petri_gantt",
            )

    summary = {
        "status": result.status,
        "objective_cmax": result.objective_cmax,
        "best_bound": result.best_bound,
        "relative_gap": result.relative_gap,
        "wall_time": result.wall_time,
        "certificate_scope": result.certificate_scope,
        "scip_used": result.scip_used,
        "artifacts": artifacts,
    }
    (output_dir / "run_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False))
    return 0 if result.feasible else 2


if __name__ == "__main__":
    raise SystemExit(main())

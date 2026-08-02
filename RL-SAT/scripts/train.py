#!/usr/bin/env python3
"""Train the SCIP-free structure-aware A3C dispatch-priority policy."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


RL_SAT_ROOT = Path(__file__).resolve().parents[1]
if str(RL_SAT_ROOT) not in sys.path:
    sys.path.insert(0, str(RL_SAT_ROOT))

from rl_sat.a3c import A3CTrainer  # noqa: E402
from rl_sat.config import load_config  # noqa: E402
from rl_sat.domain import build_problem  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Train A3C to prioritize the two fixed canonical CH queues."
    )
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--device", default="cpu")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    config = load_config(args.config)
    problem = build_problem(config.tool)
    output_dir = (
        args.output_dir
        if args.output_dir is not None
        else RL_SAT_ROOT / "results" / config.output.run_name / "training"
    ).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    checkpoint = output_dir / "a3c_dispatch.pt"
    metrics_path = output_dir / "metrics.jsonl"
    trainer = A3CTrainer(problem, config, device=args.device)
    metrics = trainer.train(
        checkpoint_path=checkpoint,
        metrics_path=metrics_path,
    )
    summary = {
        "status": "COMPLETED",
        "episodes": len(metrics),
        "checkpoint": str(checkpoint),
        "metrics": str(metrics_path),
        "device": args.device,
        "canonical_assignments": True,
        "scip_used": False,
    }
    summary_path = output_dir / "training_summary.json"
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Fail if the RL-SAT runtime imports SCIP or legacy SCIP model builders."""

from __future__ import annotations

import argparse
import ast
import importlib
import importlib.abc
import json
import sys
from pathlib import Path
from typing import Iterable


RL_SAT_ROOT = Path(__file__).resolve().parents[1]
if str(RL_SAT_ROOT) not in sys.path:
    sys.path.insert(0, str(RL_SAT_ROOT))


FORBIDDEN_ROOTS = {
    "pyscipopt",
    "scip_imports",
    "petri_mip_generator",
    "petri_warm_start",
    "parallel_reinforce_algorithm",
    "run_ablation_experiments",
}


class _ForbiddenImportFinder(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split(".", 1)[0] in FORBIDDEN_ROOTS:
            raise ImportError(f"Forbidden SCIP-side import attempted: {fullname}")
        return None


def _imports(path: Path) -> Iterable[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name
        elif isinstance(node, ast.ImportFrom) and node.module:
            yield node.module


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Statically and dynamically verify the RL-SAT/SCIP isolation boundary."
    )
    parser.add_argument("--config", type=Path, default=None)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    violations = []
    checked_files = []
    for path in sorted(RL_SAT_ROOT.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        checked_files.append(str(path.relative_to(RL_SAT_ROOT)))
        for module in _imports(path):
            if module.split(".", 1)[0] in FORBIDDEN_ROOTS:
                violations.append(
                    {
                        "file": str(path.relative_to(RL_SAT_ROOT)),
                        "module": module,
                    }
                )
    if violations:
        print(json.dumps({"status": "FAILED", "violations": violations}, indent=2))
        return 1

    finder = _ForbiddenImportFinder()
    sys.meta_path.insert(0, finder)
    imported = []
    try:
        modules = (
            "rl_sat.config",
            "rl_sat.domain",
            "rl_sat.initial_solution",
            "rl_sat.environment",
            "rl_sat.model",
            "rl_sat.a3c",
            "rl_sat.beam_search",
            "rl_sat.cpsat_solver",
            "rl_sat.hybrid_solver",
            "rl_sat.result_io",
            "rl_sat.gantt",
            "rl_sat.gantt_paths",
            "rl_sat.petri_gantt",
        )
        for module in modules:
            importlib.import_module(module)
            imported.append(module)
        if args.config is not None:
            from rl_sat.config import load_config
            from rl_sat.domain import build_problem
            from rl_sat.environment import StructureAwareSchedulingEnv

            problem = build_problem(load_config(args.config).tool)
            env = StructureAwareSchedulingEnv(problem)
            observation = env.reset()
            while not env.done:
                action = int(observation.action_mask.reshape(-1).nonzero()[0][0])
                observation, _, _, _ = env.step(action)
    finally:
        sys.meta_path.remove(finder)

    payload = {
        "status": "PASSED",
        "checked_python_files": len(checked_files),
        "dynamically_imported": imported,
        "config_smoke_tested": args.config is not None,
        "scip_used": False,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

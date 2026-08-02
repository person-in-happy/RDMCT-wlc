from __future__ import annotations

import ast
import importlib
from pathlib import Path


FORBIDDEN = {
    "pyscipopt",
    "scip_imports",
    "petri_mip_generator",
    "petri_warm_start",
    "parallel_reinforce_algorithm",
    "run_ablation_experiments",
}


def test_runtime_python_tree_has_no_scip_side_imports():
    root = Path(__file__).resolve().parents[1]
    violations = []
    for path in sorted((root / "rl_sat").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            modules = []
            if isinstance(node, ast.Import):
                modules = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                modules = [node.module]
            for module in modules:
                if module.split(".", 1)[0] in FORBIDDEN:
                    violations.append((path.name, module))
    assert violations == []


def test_core_import_does_not_load_pyscipopt():
    importlib.import_module("rl_sat")
    import sys

    assert "pyscipopt" not in sys.modules

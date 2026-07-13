"""Generate reproducible multi-family MILP benchmarks for AAAI-27 experiments.

The generated instances are intentionally independent of the semiconductor
formulation. They provide four standard MILP families for transfer tests:
set cover, multidimensional knapsack, capacitated facility location, and
maximum-weight independent set.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

AAAI_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = AAAI_ROOT.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from path_utils import resolve_path
from scip_imports import scip


def _parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output_dir", default=str(AAAI_ROOT / "data" / "milp"))
    parser.add_argument("--train_instances", type=int, default=20)
    parser.add_argument("--validation_instances", type=int, default=5)
    parser.add_argument("--test_instances", type=int, default=10)
    parser.add_argument("--seed", type=int, default=2027)
    parser.add_argument(
        "--scales",
        default="small,medium,large",
        help="Comma-separated subset of small, medium, large.",
    )
    return parser.parse_args()


def _quiet_model(name):
    model = scip.Model(name)
    model.hideOutput()
    return model


def _write(model, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    model.writeProblem(str(path))
    model.freeProb()


def _setcover(path, rng, scale):
    sizes = {
        "small": (80, 160, 0.08),
        "medium": (160, 400, 0.05),
        "large": (300, 800, 0.035),
    }
    rows, cols, density = sizes[scale]
    model = _quiet_model(path.stem)
    variables = [
        model.addVar(vtype="B", name=f"x_{j}", obj=float(rng.integers(1, 101)))
        for j in range(cols)
    ]
    incidence = rng.random((rows, cols)) < density
    for i in range(rows):
        if not incidence[i].any():
            incidence[i, int(rng.integers(cols))] = True
        model.addCons(
            scip.quicksum(variables[j] for j in np.flatnonzero(incidence[i])) >= 1,
            name=f"cover_{i}",
        )
    model.setMinimize()
    _write(model, path)


def _knapsack(path, rng, scale):
    sizes = {"small": (150, 3), "medium": (400, 5), "large": (900, 8)}
    items, dimensions = sizes[scale]
    model = _quiet_model(path.stem)
    profits = rng.integers(10, 250, size=items)
    weights = rng.integers(1, 100, size=(dimensions, items))
    variables = [
        model.addVar(vtype="B", name=f"x_{j}", obj=float(profits[j]))
        for j in range(items)
    ]
    for dim in range(dimensions):
        capacity = int(0.35 * np.sum(weights[dim]))
        model.addCons(
            scip.quicksum(
                int(weights[dim, j]) * variables[j] for j in range(items)
            )
            <= capacity,
            name=f"capacity_{dim}",
        )
    model.setMaximize()
    _write(model, path)


def _facility_location(path, rng, scale):
    sizes = {"small": (20, 60), "medium": (40, 150), "large": (75, 300)}
    facilities, customers = sizes[scale]
    model = _quiet_model(path.stem)
    demand = rng.integers(5, 25, size=customers)
    capacity = rng.integers(
        max(30, int(np.sum(demand) / facilities)),
        max(60, int(2.2 * np.sum(demand) / facilities)),
        size=facilities,
    )
    fixed = rng.integers(100, 1000, size=facilities)
    transport = rng.integers(1, 100, size=(facilities, customers))
    open_vars = [
        model.addVar(vtype="B", name=f"open_{i}", obj=float(fixed[i]))
        for i in range(facilities)
    ]
    assign = {
        (i, j): model.addVar(
            vtype="B",
            name=f"assign_{i}_{j}",
            obj=float(transport[i, j]),
        )
        for i in range(facilities)
        for j in range(customers)
    }
    for j in range(customers):
        model.addCons(
            scip.quicksum(assign[i, j] for i in range(facilities)) == 1,
            name=f"serve_{j}",
        )
    for i in range(facilities):
        model.addCons(
            scip.quicksum(
                int(demand[j]) * assign[i, j] for j in range(customers)
            )
            <= int(capacity[i]) * open_vars[i],
            name=f"facility_capacity_{i}",
        )
    model.setMinimize()
    _write(model, path)


def _independent_set(path, rng, scale):
    sizes = {"small": (180, 0.035), "medium": (450, 0.018), "large": (900, 0.01)}
    vertices, edge_probability = sizes[scale]
    model = _quiet_model(path.stem)
    weights = rng.integers(1, 100, size=vertices)
    variables = [
        model.addVar(vtype="B", name=f"x_{i}", obj=float(weights[i]))
        for i in range(vertices)
    ]
    upper = rng.random((vertices, vertices))
    edges = np.argwhere(np.triu(upper < edge_probability, k=1))
    for edge_id, (u, v) in enumerate(edges):
        model.addCons(
            variables[int(u)] + variables[int(v)] <= 1,
            name=f"edge_{edge_id}",
        )
    model.setMaximize()
    _write(model, path)


GENERATORS = {
    "setcover": _setcover,
    "knapsack": _knapsack,
    "facility_location": _facility_location,
    "independent_set": _independent_set,
}


def main():
    args = _parse_args()
    output_dir = Path(resolve_path(args.output_dir))
    scales = [item.strip() for item in args.scales.split(",") if item.strip()]
    unknown = sorted(set(scales) - {"small", "medium", "large"})
    if unknown:
        raise ValueError(f"Unknown scales: {unknown}")
    split_counts = {
        "train": args.train_instances,
        "validation": args.validation_instances,
        "test": args.test_instances,
    }
    generated = 0
    seed_sequence = np.random.SeedSequence(args.seed)
    total = len(GENERATORS) * len(scales) * sum(split_counts.values())
    child_seeds = iter(seed_sequence.spawn(total))
    for family, generator in GENERATORS.items():
        for scale in scales:
            for split, count in split_counts.items():
                for index in range(count):
                    rng = np.random.default_rng(next(child_seeds))
                    path = (
                        output_dir
                        / family
                        / scale
                        / split
                        / f"{family}_{scale}_{split}_{index:03d}.mps"
                    )
                    generator(path, rng, scale)
                    generated += 1
                    print(f"[{generated}/{total}] {path}", flush=True)
    print(f"Generated {generated} instances under {output_dir}")


if __name__ == "__main__":
    main()

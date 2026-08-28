"""Validate one SCIP solution against the active primary C&IE model."""

from __future__ import annotations

import argparse
from pathlib import Path

from analyze_cie_solutions import _validate


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--instance", required=True)
    parser.add_argument("--solution", required=True)
    args = parser.parse_args()

    instance = Path(args.instance).resolve()
    solution = Path(args.solution).resolve()
    if not instance.is_file():
        raise FileNotFoundError(f"Instance does not exist: {instance}")
    if not solution.is_file():
        raise FileNotFoundError(f"Solution does not exist: {solution}")

    feasible, note = _validate(instance, solution)
    print(f"active-primary checkSol: feasible={feasible}; {note}")
    if not feasible:
        raise RuntimeError(
            f"Solution is incompatible with the active primary model: {solution}"
        )


if __name__ == "__main__":
    main()
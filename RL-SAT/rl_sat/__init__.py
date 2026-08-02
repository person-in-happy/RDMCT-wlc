"""SCIP-free reinforcement-learning and CP-SAT scheduler.

The package is intentionally self-contained under ``RL-SAT``.  Importing it
must not import PySCIPOpt or any module from the legacy SCIP execution path.
"""

from .config import ExperimentConfig, load_config
from .domain import Plan, Problem, ScheduleResult, build_problem


def __getattr__(name: str):
    # Keep lightweight imports (domain/config/visualization) independent from
    # optional OR-Tools and Torch native libraries while exposing public APIs.
    if name == 'CPSATScheduler':
        from .cpsat_solver import CPSATScheduler

        return CPSATScheduler
    if name == 'HybridRLSATSolver':
        from .hybrid_solver import HybridRLSATSolver

        return HybridRLSATSolver
    raise AttributeError(name)

__all__ = [
    "ExperimentConfig",
    "CPSATScheduler",
    "HybridRLSATSolver",
    "Plan",
    "Problem",
    "ScheduleResult",
    "build_problem",
    "load_config",
]

__version__ = "0.1.0"

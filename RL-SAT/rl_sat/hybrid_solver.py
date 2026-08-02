"""A3C/beam candidate orchestration followed by detailed CP-SAT scheduling."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

from .beam_search import StructureAwareBeamSearch, merge_plan_candidates
from .config import ExperimentConfig
from .cpsat_solver import CPSATScheduler
from .domain import Plan, Problem, ScheduleResult, build_problem
from .initial_solution import InitialPlanGenerator
from .model import StructureAwareActorCritic, load_checkpoint


class HybridRLSATSolver:
    """Run initial construction + structure-aware beam + CP-SAT.

    Pair and 4x1-batch membership remain symmetry-broken. In dynamic mode,
    A3C/beam proposes chamber assignments; in compatibility mode it proposes
    fixed-queue release hints. CP-SAT rebuilds cleaning for each candidate and
    optimizes detailed physical timing.
    """

    def __init__(
        self,
        config: ExperimentConfig,
        checkpoint_path: Optional[str | Path] = None,
        warm_start_sol: Optional[str | Path] = None,
        device: str = "cpu",
        *,
        checkpoint: Optional[str | Path] = None,
        legacy_solution: Optional[str | Path] = None,
    ):
        config.validate()
        if checkpoint is not None and checkpoint_path is not None:
            if Path(checkpoint) != Path(checkpoint_path):
                raise ValueError('checkpoint and checkpoint_path disagree.')
        if legacy_solution is not None and warm_start_sol is not None:
            if Path(legacy_solution) != Path(warm_start_sol):
                raise ValueError('legacy_solution and warm_start_sol disagree.')
        checkpoint = checkpoint if checkpoint is not None else checkpoint_path
        legacy_solution = (
            legacy_solution if legacy_solution is not None else warm_start_sol
        )
        self.config = config
        self.problem: Problem = build_problem(config.tool)
        self.checkpoint = Path(checkpoint) if checkpoint else None
        self.legacy_solution = Path(legacy_solution) if legacy_solution else None
        self.device = device
        self.model: Optional[StructureAwareActorCritic] = None
        self.checkpoint_metadata: Dict[str, Any] = {}
        if self.checkpoint is not None:
            self.model, self.checkpoint_metadata = load_checkpoint(
                self.checkpoint,
                device=device,
            )

    def candidate_plans(self) -> List[Plan]:
        generator = InitialPlanGenerator(self.problem)
        if self.legacy_solution is None:
            initial = generator.generate()
        else:
            initial = generator.from_legacy_sol(self.legacy_solution)
        beam = StructureAwareBeamSearch(
            self.problem,
            self.config.beam,
            self.model,
            device=self.device,
            seed=self.config.rl.seed,
        )
        beam_plans = beam.search()
        return merge_plan_candidates(
            initial,
            beam_plans,
            self.config.beam.candidates_for_cpsat,
        )

    @staticmethod
    def _rank(result: ScheduleResult):
        return (
            float("inf") if result.objective_cmax is None else result.objective_cmax,
            float("inf")
            if result.schedule_stability is None
            else result.schedule_stability,
            result.wall_time,
        )

    @staticmethod
    def _candidate_summary(index: int, plan: Plan, result: ScheduleResult):
        return {
            "candidate_index": index,
            "source": plan.source,
            "input_plan": plan.to_dict(),
            "status": result.status,
            "objective_cmax": result.objective_cmax,
            "best_bound": result.best_bound,
            "relative_gap": result.relative_gap,
            "schedule_stability": result.schedule_stability,
            "wall_time": result.wall_time,
            "dispatch_priority_hint": plan.dispatch_order(),
            "solved_plan": result.plan.to_dict() if result.feasible else None,
        }

    def solve(
        self,
        *,
        candidates: Optional[Sequence[Plan]] = None,
    ) -> ScheduleResult:
        pipeline_started = time.perf_counter()
        plans = [plan.clone() for plan in (candidates or self.candidate_plans())]
        if not plans:
            raise ValueError("Hybrid RL-SAT requires at least one candidate plan.")
        for plan in plans:
            plan.validate(self.problem)

        scheduler = CPSATScheduler(self.problem, self.config.cpsat)
        candidate_results: List[ScheduleResult] = []
        summaries: List[Dict[str, Any]] = []
        cpsat_started = time.perf_counter()
        total_budget = float(self.config.cpsat.time_limit_seconds)
        polish_reserve = min(
            float(self.config.cpsat.final_polish_seconds), total_budget
        )
        screening_allocations: List[float] = []
        for index, plan in enumerate(plans, start=1):
            remaining = total_budget - (time.perf_counter() - cpsat_started)
            screening_available = remaining - polish_reserve
            if screening_available <= 0.01:
                if candidate_results:
                    break
                screening_available = remaining
            allocated = min(
                float(self.config.cpsat.candidate_time_limit_seconds),
                max(0.01, screening_available),
            )
            result = scheduler.solve(
                plan,
                time_limit_seconds=allocated,
                # Candidate screening spends all of its budget on makespan.
                lexicographic_stability=False,
            )
            screening_allocations.append(allocated)
            candidate_results.append(result)
            summary = self._candidate_summary(index, plan, result)
            summary["allocated_time_limit_seconds"] = allocated
            summaries.append(summary)
        screening_elapsed = time.perf_counter() - cpsat_started

        feasible = [result for result in candidate_results if result.feasible]
        polish_budget = 0.0
        polish_elapsed = 0.0
        if feasible:
            selected = min(feasible, key=self._rank)
            selected_index = candidate_results.index(selected) + 1
            remaining = total_budget - (time.perf_counter() - cpsat_started)
            polish_budget = min(
                float(self.config.cpsat.final_polish_seconds),
                max(0.0, remaining),
            )
            if polish_budget > 0.01:
                polish_started = time.perf_counter()
                polished = scheduler.solve(
                    selected.plan,
                    time_limit_seconds=polish_budget,
                    lexicographic_stability=self.config.cpsat.lexicographic_stability,
                    incumbent_result=selected,
                )
                polish_elapsed = time.perf_counter() - polish_started
                if polished.feasible and self._rank(polished) <= self._rank(selected):
                    selected = polished
                    polish_selected = True
                else:
                    polish_selected = False
            else:
                polish_selected = False
        else:
            # Preserve the most informative solver status and diagnostics.
            selected = candidate_results[0]
            selected_index = 1
            polish_selected = False

        pipeline_wall_time = time.perf_counter() - pipeline_started
        full_wafers = sum(
            mode == "4x1" for mode in self.problem.wafer_modes.values()
        )
        mix_wafers = len(self.problem.wafer_modes) - full_wafers
        instance = (
            f"{len(self.problem.wafer_modes)}w_"
            f"{full_wafers}full_{mix_wafers}mix"
        )
        selected.wall_time = pipeline_wall_time
        selected.metadata = {
            **selected.metadata,
            "instance": instance,
            "run_name": self.config.output.run_name,
            "branches": selected.metadata.get("branches"),
            "conflicts": selected.metadata.get("conflicts"),
            "hybrid_pipeline": {
                "algorithm": (
                    "balanced initial solution + A3C chamber assignment + "
                    "structure-aware beam search + CP-SAT"
                ),
                "candidate_count": len(summaries),
                "proposed_candidate_count": len(plans),
                "selected_candidate_index": selected_index,
                "final_polish_selected": polish_selected,
                "pipeline_wall_time": pipeline_wall_time,
                "cpsat_budget": {
                    "configured_total_seconds": total_budget,
                    "screening_allocations_seconds": screening_allocations,
                    "screening_elapsed_seconds": screening_elapsed,
                    "polish_reserved_seconds": polish_reserve,
                    "polish_allocated_seconds": polish_budget,
                    "polish_elapsed_seconds": polish_elapsed,
                    "total_elapsed_seconds": time.perf_counter() - cpsat_started,
                },
                "checkpoint": str(self.checkpoint) if self.checkpoint else None,
                "checkpoint_metadata": self.checkpoint_metadata,
                "legacy_structural_solution": (
                    str(self.legacy_solution) if self.legacy_solution else None
                ),
                "candidate_results": summaries,
                "important_scope_note": (
                    "Pair membership remains symmetry-broken. When dynamic "
                    "assignment is enabled, A3C/Beam chooses each 4x1 batch or "
                    "2x2 unit's chamber and CP-SAT rebuilds cleaning epochs for "
                    "that candidate; otherwise the legacy canonical queues are "
                    "used. Bounds certify only the selected CP-SAT abstraction, "
                    "not global equivalence to the legacy SCIP Petri MIP."
                ),
            },
        }
        return selected


def solve_hybrid(
    config: ExperimentConfig,
    *,
    checkpoint: Optional[str | Path] = None,
    legacy_solution: Optional[str | Path] = None,
    checkpoint_path: Optional[str | Path] = None,
    warm_start_sol: Optional[str | Path] = None,
    device: str = "cpu",
    candidates: Optional[Sequence[Plan]] = None,
) -> ScheduleResult:
    """Convenience entry point for CLI scripts."""

    return HybridRLSATSolver(
        config,
        checkpoint=checkpoint,
        legacy_solution=legacy_solution,
        checkpoint_path=checkpoint_path,
        warm_start_sol=warm_start_sol,
        device=device,
    ).solve(candidates=candidates)


__all__ = ["HybridRLSATSolver", "solve_hybrid"]

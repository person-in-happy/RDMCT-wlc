import os
import re
import threading
import time
from pathlib import Path
import numpy as np
from scip_imports import scip

from logger import logger
from path_utils import resolve_path
from petri_warm_start import find_compatible_mixed_warm_start

class SCIPCutSelEnv():
    def __init__(
        self,
        instance_file_path,
        scip_seed,
        seed,
        scip_time_limit=3600,
        single_instance_file=None,
        scip_verbosity=0,
        scip_memory_limit_mb=0.0,
        scip_node_limit=-1,
        scip_stall_node_limit=-1,
        scip_solution_limit=-1,
        scip_relative_gap_limit=0.0,
        scip_absolute_gap_limit=0.0,
        scip_emphasis="default",
        scip_heuristics_profile="default",
        scip_disable_expensive_heuristics=False,
        cutsel_max_candidates=128,
        cutsel_max_selected_cuts=16,
        cutsel_use_structure_rerank=None,
        scip_rare_clock_check=True,
        scip_lp_iteration_limit=100000,
        scip_root_lp_iteration_limit=500000,
        scip_interrupt_grace_seconds=30.0,
        warm_start_solution_file=None,
        lexicographic_schedule_stability=True,
        schedule_stability_mode="linear",
        lexicographic_fix_discrete_decisions=True,
        lexicographic_free_double_decisions=True,
        lexicographic_cmax_tolerance=1e-6,
        lexicographic_stability_time_limit=10.0,
        lexicographic_stability_node_limit=5000,
        schedule_linear_wait_weight=1.0,
        schedule_linear_max_wait_weight=10.0,
        schedule_cadence_deviation_weight=25.0,
        schedule_max_wait_time=0.0,
        schedule_wait_cap_mode="hard",
        schedule_wait_cap_excess_weight=1000.0,
        schedule_chamber_idle_square_penalty=1e-5,
        schedule_pm_wait_square_penalty=1e-3,
        schedule_module_wait_square_penalty=1e-5,
        schedule_robot_wait_square_penalty=1e-5,
        schedule_atr_transfer_time=3.0,
        schedule_vtr_transfer_time=4.0,
        schedule_atr_return_time=3.0,
        **init_scip_kwargs
    ):
        self.instance_file_path = str(resolve_path(instance_file_path))
        if not os.path.isdir(self.instance_file_path):
            raise FileNotFoundError(f"instance_file_path does not exist: {self.instance_file_path}")
        self.instances = sorted(
            f_name
            for f_name in os.listdir(self.instance_file_path)
            if f_name.endswith((".lp", ".mps", ".cip"))
        )
        self.single_instance_file = single_instance_file
        self.scip_seed = scip_seed
        self.seed = seed
        self.scip_time_limit = scip_time_limit
        self.scip_verbosity = scip_verbosity
        self.scip_memory_limit_mb = scip_memory_limit_mb
        self.scip_node_limit = scip_node_limit
        self.scip_stall_node_limit = scip_stall_node_limit
        self.scip_solution_limit = scip_solution_limit
        self.scip_relative_gap_limit = scip_relative_gap_limit
        self.scip_absolute_gap_limit = scip_absolute_gap_limit
        self.scip_emphasis = scip_emphasis
        self.scip_heuristics_profile = scip_heuristics_profile
        self.scip_disable_expensive_heuristics = scip_disable_expensive_heuristics
        self.cutsel_max_candidates = cutsel_max_candidates
        self.cutsel_max_selected_cuts = cutsel_max_selected_cuts
        self.cutsel_use_structure_rerank = cutsel_use_structure_rerank
        self.scip_rare_clock_check = scip_rare_clock_check
        self.scip_lp_iteration_limit = scip_lp_iteration_limit
        self.scip_root_lp_iteration_limit = scip_root_lp_iteration_limit
        self.scip_interrupt_grace_seconds = scip_interrupt_grace_seconds
        self.warm_start_solution_file = warm_start_solution_file
        self.lexicographic_schedule_stability = lexicographic_schedule_stability
        self.schedule_stability_mode = str(schedule_stability_mode or "linear").strip().lower()
        self.lexicographic_fix_discrete_decisions = lexicographic_fix_discrete_decisions
        self.lexicographic_free_double_decisions = lexicographic_free_double_decisions
        self.lexicographic_cmax_tolerance = lexicographic_cmax_tolerance
        self.lexicographic_stability_time_limit = lexicographic_stability_time_limit
        self.lexicographic_stability_node_limit = lexicographic_stability_node_limit
        self.schedule_linear_wait_weight = schedule_linear_wait_weight
        self.schedule_linear_max_wait_weight = schedule_linear_max_wait_weight
        self.schedule_cadence_deviation_weight = schedule_cadence_deviation_weight
        self.schedule_max_wait_time = schedule_max_wait_time
        self.schedule_wait_cap_mode = str(schedule_wait_cap_mode or "hard").strip().lower()
        self.schedule_wait_cap_excess_weight = schedule_wait_cap_excess_weight
        self.schedule_chamber_idle_square_penalty = schedule_chamber_idle_square_penalty
        self.schedule_pm_wait_square_penalty = schedule_pm_wait_square_penalty
        self.schedule_module_wait_square_penalty = schedule_module_wait_square_penalty
        self.schedule_robot_wait_square_penalty = schedule_robot_wait_square_penalty
        self.schedule_atr_transfer_time = schedule_atr_transfer_time
        self.schedule_vtr_transfer_time = schedule_vtr_transfer_time
        self.schedule_atr_return_time = schedule_atr_return_time
        self.init_scip_kwargs = init_scip_kwargs
        self._lexicographic_info = {}

        # self.reset()
        self.set_seed()

    def _resolve_instance_file(self, instance_file):
        instance_text = str(instance_file)
        candidate = Path(instance_text).expanduser()

        if candidate.is_absolute() or len(candidate.parts) > 1:
            resolved_candidate = resolve_path(candidate)
            if resolved_candidate.is_file():
                return str(resolved_candidate)

        configured_candidate = Path(self.instance_file_path) / instance_text
        if configured_candidate.is_file():
            return str(configured_candidate.resolve())

        generated_root = resolve_path("generated_instances")
        if generated_root.is_dir():
            matches = sorted(
                path.resolve()
                for path in generated_root.rglob(Path(instance_text).name)
                if path.is_file()
            )
            if len(matches) == 1:
                logger.log(
                    "warning: instance file not found in "
                    f"{self.instance_file_path}; using {matches[0]}"
                )
                return str(matches[0])
            if len(matches) > 1:
                shown_matches = "\n".join(f"  - {path}" for path in matches[:10])
                extra = "" if len(matches) <= 10 else f"\n  ... and {len(matches) - 10} more"
                raise FileNotFoundError(
                    f"Instance file `{instance_text}` was not found in {self.instance_file_path}, "
                    "and the same filename exists in multiple generated instance directories:\n"
                    f"{shown_matches}{extra}\n"
                    "Pass an absolute path or update env.instance_file_path."
                )

        available = ", ".join(self.instances[:10])
        if len(self.instances) > 10:
            available += f", ... and {len(self.instances) - 10} more"
        available_text = available or "none"
        raise FileNotFoundError(
            f"Instance file does not exist: {configured_candidate.resolve()}. "
            f"Available instances in {self.instance_file_path}: {available_text}"
        )

    def _set_scip_separator_params(self, max_rounds_root=-1, max_rounds=-1, max_cuts_root=10000, max_cuts=10000,
                                frequency=10):
        """
        Function for setting the separator params in SCIP. It goes through all separators, enables them at all points
        in the solving process,
        Args:
            scip: The SCIP Model object
            max_rounds_root: The max number of separation rounds that can be performed at the root node
            max_rounds: The max number of separation rounds that can be performed at any non-root node
            max_cuts_root: The max number of cuts that can be added per round in the root node
            max_cuts: The max number of cuts that can be added per node at any non-root node
            frequency: The separators will be called each time the tree hits a new multiple of this depth
        Returns:
            The SCIP Model with all the appropriate parameters now set
        """

        assert type(max_cuts) == int and type(max_rounds) == int
        assert type(max_cuts_root) == int and type(max_rounds_root) == int

        model = self.m

        # First for the aggregation heuristic separator
        model.setParam('separating/aggregation/freq', frequency)
        model.setParam('separating/aggregation/maxrounds', max_rounds)
        model.setParam('separating/aggregation/maxroundsroot', max_rounds_root)
        model.setParam('separating/aggregation/maxsepacuts', max_cuts)
        model.setParam('separating/aggregation/maxsepacutsroot', max_cuts_root)

        # Now the Chvatal-Gomory w/ MIP separator
        # model.setParam('separating/cgmip/freq', frequency)
        # model.setParam('separating/cgmip/maxrounds', max_rounds)
        # model.setParam('separating/cgmip/maxroundsroot', max_rounds_root)

        # The clique separator
        model.setParam('separating/clique/freq', frequency)
        model.setParam('separating/clique/maxsepacuts', max_cuts)

        # The close-cuts separator
        model.setParam('separating/closecuts/freq', frequency)

        # The CMIR separator
        model.setParam('separating/cmir/freq', frequency)

        # The Convex Projection separator
        model.setParam('separating/convexproj/freq', frequency)
        model.setParam('separating/convexproj/maxdepth', -1)

        # The disjunctive cut separator
        model.setParam('separating/disjunctive/freq', frequency)
        model.setParam('separating/disjunctive/maxrounds', max_rounds)
        model.setParam('separating/disjunctive/maxroundsroot', max_rounds_root)
        model.setParam('separating/disjunctive/maxinvcuts', max_cuts)
        model.setParam('separating/disjunctive/maxinvcutsroot', max_cuts_root)
        model.setParam('separating/disjunctive/maxdepth', -1)

        # The separator for edge-concave function
        model.setParam('separating/eccuts/freq', frequency)
        model.setParam('separating/eccuts/maxrounds', max_rounds)
        model.setParam('separating/eccuts/maxroundsroot', max_rounds_root)
        model.setParam('separating/eccuts/maxsepacuts', max_cuts)
        model.setParam('separating/eccuts/maxsepacutsroot', max_cuts_root)
        model.setParam('separating/eccuts/maxdepth', -1)

        # The flow cover cut separator
        model.setParam('separating/flowcover/freq', frequency)

        # The gauge separator
        model.setParam('separating/gauge/freq', frequency)

        # Gomory MIR cuts
        model.setParam('separating/gomory/freq', frequency)
        model.setParam('separating/gomory/maxrounds', max_rounds)
        model.setParam('separating/gomory/maxroundsroot', max_rounds_root)
        model.setParam('separating/gomory/maxsepacuts', max_cuts)
        model.setParam('separating/gomory/maxsepacutsroot', max_cuts_root)

        # The implied bounds separator
        model.setParam('separating/impliedbounds/freq', frequency)

        # The integer objective value separator
        model.setParam('separating/intobj/freq', frequency)

        # The knapsack cover separator
        model.setParam('separating/knapsackcover/freq', frequency)

        # The multi-commodity-flow network cut separator
        model.setParam('separating/mcf/freq', frequency)
        model.setParam('separating/mcf/maxsepacuts', max_cuts)
        model.setParam('separating/mcf/maxsepacutsroot', max_cuts_root)

        # The odd cycle separator
        model.setParam('separating/oddcycle/freq', frequency)
        model.setParam('separating/oddcycle/maxrounds', max_rounds)
        model.setParam('separating/oddcycle/maxroundsroot', max_rounds_root)
        model.setParam('separating/oddcycle/maxsepacuts', max_cuts)
        model.setParam('separating/oddcycle/maxsepacutsroot', max_cuts_root)

        # The rapid learning separator
        model.setParam('separating/rapidlearning/freq', frequency)

        # The strong CG separator
        # model.setParam('separating/strongcg/freq', frequency)
        # model.setParam('separating/strongcg/maxrounds', max_rounds)
        # model.setParam('separating/strongcg/maxroundsroot', max_rounds_root)
        # model.setParam('separating/strongcg/maxsepacuts', max_cuts)
        # model.setParam('separating/strongcg/maxsepacutsroot', max_cuts_root)

        # The zero-half separator
        model.setParam('separating/zerohalf/freq', frequency)
        model.setParam('separating/zerohalf/maxcutcands', max(max_cuts, max_cuts_root))
        model.setParam('separating/zerohalf/maxrounds', max_rounds)
        model.setParam('separating/zerohalf/maxroundsroot', max_rounds_root)
        model.setParam('separating/zerohalf/maxsepacuts', max_cuts)
        model.setParam('separating/zerohalf/maxsepacutsroot', max_cuts_root)

        # Now the general cut and round parameters
        model.setParam("separating/maxroundsroot", max_rounds_root)
        model.setParam("separating/maxstallroundsroot", max_rounds_root)
        model.setParam("separating/maxcutsroot", max_cuts_root)

        model.setParam("separating/maxrounds", max_rounds)
        model.setParam("separating/maxstallrounds", 1)
        model.setParam("separating/maxcuts", max_cuts)

    def _init_scip_params(self, **init_scip_kwargs):
        seed = self.scip_seed % 2147483648  # SCIP seed range

        # set up randomization
        self.m.setBoolParam('randomization/permutevars', True)
        self.m.setIntParam('randomization/permutationseed', seed)
        self.m.setIntParam('randomization/randomseedshift', seed)

        # separators
        self._set_scip_separator_params(init_scip_kwargs['max_rounds_root'], 1, 10000, 1000, 10)

        # separation only at root node
        self.m.setIntParam('separating/maxrounds', 0)

        # no restart
        self.m.setIntParam('presolving/maxrestarts', 0)


        # if asked, disable presolving
        if not init_scip_kwargs['presolving']:
            self.m.setIntParam('presolving/maxrounds', 0)
            self.m.setIntParam('presolving/maxrestarts', 0)

        # if asked, disable separating (cuts)
        if not init_scip_kwargs['separating']:
            self.m.setIntParam('separating/maxroundsroot', 0)

        # if asked, disable conflict analysis (more cuts)
        if not init_scip_kwargs['conflict']:
            self.m.setBoolParam('conflict/enable', False)

        # if asked, disable primal heuristics
        if not init_scip_kwargs['heuristics']:
            self.m.setHeuristics(scip.SCIP_PARAMSETTING.OFF)

    def set_seed(self, seed=None):
        if seed is not None:
            self.seed = seed
            self.rng = np.random.RandomState(seed)
        else:
            self.rng = np.random.RandomState(self.seed)

    def _strip_inactive_schedule_stability_constraints(self):
        """Remove secondary-only auxiliaries when phase two is disabled."""
        if (
            self.lexicographic_schedule_stability
            and self.schedule_stability_mode != "linear"
        ):
            return
        secondary_prefixes = [
            "schedule_wait_square_def_",
            "chamber_nonprocess_wait_",
            "resource_idle_",
        ]
        if (
            float(self.schedule_max_wait_time or 0.0) <= 0
            or self.schedule_wait_cap_mode != "hard"
        ):
            secondary_prefixes.append("schedule_wait_def_")
        secondary_prefixes = tuple(secondary_prefixes)
        removable = [
            constraint
            for constraint in self.m.getConss()
            if constraint.name == "schedule_stability_def"
            or constraint.name.startswith(secondary_prefixes)
        ]
        for constraint in removable:
            self.m.delCons(constraint)
        if removable:
            logger.log(
                "removed inactive schedule-stability constraints before primary solve: "
                f"{len(removable)}"
            )

    def _apply_schedule_wait_cap(self):
        """Apply the per-interval cap to generated and legacy Petri LPs."""
        cap = float(self.schedule_max_wait_time or 0.0)
        if cap <= 0:
            return
        if self.schedule_wait_cap_mode != "hard":
            logger.log(
                f"effective soft schedule wait target: {cap:.1f}s "
                f"(excess_weight={float(self.schedule_wait_cap_excess_weight):g})"
            )
            return
        exact_prefixes = (
            "llupper_wait_",
            "lllower_wait_",
            "full_pair_post_process_wait_",
            "mix_pair_post_process_wait_",
            "full_batch_idle_",
            "full_to_mix_idle_",
            "mix_cycle_to_bridge_idle_",
            "mix_tail_idle_",
        )
        existing = {constraint.name for constraint in self.m.getConss()}
        capped = 0
        for variable in self.m.getVars():
            is_chamber_wait = (
                variable.name.startswith("chamber_nonprocess_wait_")
                and not variable.name.startswith("chamber_nonprocess_wait_square_")
            )
            is_generic_wait = (
                variable.name.startswith("schedule_wait_")
                and not variable.name.startswith("schedule_wait_square_")
            )
            if (
                not variable.name.startswith(exact_prefixes)
                and not is_chamber_wait
                and not is_generic_wait
            ):
                continue
            constraint_name = f"schedule_wait_cap_{variable.name}"
            if constraint_name in existing:
                continue
            self.m.addCons(variable <= cap, name=constraint_name)
            capped += 1
        logger.log(f"effective hard schedule wait cap: {cap:.1f}s ({capped} runtime constraints added)")

    def _configure_linear_stability_objective(self, discrete_values):
        variables = {variable.name: variable for variable in self.m.getVars()}
        stability_var = variables.get("schedule_stability")
        if stability_var is None:
            return None

        wait_prefixes = (
            "llupper_wait_",
            "lllower_wait_",
            "full_pair_post_process_wait_",
            "mix_pair_post_process_wait_",
            "full_batch_idle_",
            "full_to_mix_idle_",
            "mix_cycle_to_bridge_idle_",
            "mix_tail_idle_",
            "chamber_idle_total_",
        )
        wait_variables = [
            variable
            for variable in self.m.getVars()
            if variable.name.startswith(wait_prefixes)
            or (
                self.schedule_wait_cap_mode == "hard"
                and variable.name.startswith("schedule_wait_")
                and not variable.name.startswith("schedule_wait_square_")
            )
        ]
        individual_wait_variables = [
            variable
            for variable in wait_variables
            if not variable.name.startswith("chamber_idle_total_")
        ]
        max_wait = self.m.addVar(vtype="C", lb=0.0, name="schedule_linear_max_wait")
        for index, variable in enumerate(individual_wait_variables):
            self.m.addCons(
                max_wait >= variable,
                name=f"schedule_linear_max_wait_lb_{index}",
            )

        cap_excesses = []
        wait_target = float(self.schedule_max_wait_time or 0.0)
        if self.schedule_wait_cap_mode == "soft" and wait_target > 0:
            for index, variable in enumerate(individual_wait_variables):
                excess = self.m.addVar(
                    vtype="C",
                    lb=0.0,
                    name=f"schedule_wait_cap_excess_{index}",
                )
                self.m.addCons(
                    excess >= variable - wait_target,
                    name=f"schedule_wait_cap_excess_lb_{index}",
                )
                cap_excesses.append(excess)

        grouped_starts = {}
        for mode, start_pattern, used_template, epoch_prefix in (
            ("full", re.compile(r"^full_start_(\d+)_(\d+)$"), "full_batch_used", "full_batch_epoch"),
            ("mix", re.compile(r"^mix_cycle_start_(\d+)_(\d+)$"), "mix_cycle_used", "mix_cycle_epoch"),
        ):
            for variable in self.m.getVars():
                match = start_pattern.match(variable.name)
                if not match:
                    continue
                chamber, position = (int(item) for item in match.groups())
                used_name = f"{used_template}_{chamber}_{position}"
                if discrete_values.get(used_name, 0) < 0.5:
                    continue
                epoch = 0
                epoch_marker = f"{epoch_prefix}_{chamber}_{position}_"
                for name, value in discrete_values.items():
                    if value >= 0.5 and name.startswith(epoch_marker):
                        epoch = int(name.rsplit("_", 1)[-1])
                        break
                grouped_starts.setdefault((mode, chamber, epoch), []).append(
                    (position, variable)
                )

        cadence_deviations = []
        for (mode, chamber, epoch), items in sorted(grouped_starts.items()):
            ordered = [variable for _, variable in sorted(items)]
            for index in range(2, len(ordered)):
                previous_gap = ordered[index - 1] - ordered[index - 2]
                current_gap = ordered[index] - ordered[index - 1]
                deviation = self.m.addVar(
                    vtype="C",
                    lb=0.0,
                    name=f"schedule_cadence_deviation_{mode}_{chamber}_{epoch}_{index}",
                )
                self.m.addCons(
                    deviation >= current_gap - previous_gap,
                    name=f"schedule_cadence_deviation_pos_{mode}_{chamber}_{epoch}_{index}",
                )
                self.m.addCons(
                    deviation >= previous_gap - current_gap,
                    name=f"schedule_cadence_deviation_neg_{mode}_{chamber}_{epoch}_{index}",
                )
                cadence_deviations.append(deviation)

        stability_expr = (
            float(self.schedule_linear_wait_weight) * scip.quicksum(wait_variables)
            + float(self.schedule_linear_max_wait_weight) * max_wait
            + float(self.schedule_cadence_deviation_weight)
            * scip.quicksum(cadence_deviations)
            + float(self.schedule_wait_cap_excess_weight)
            * scip.quicksum(cap_excesses)
        )
        self.m.addCons(
            stability_var == stability_expr,
            name="schedule_linear_stability_def",
        )
        logger.log(
            "configured linear schedule stability: "
            f"wait_vars={len(wait_variables)}, cadence_terms={len(cadence_deviations)}, "
            f"cap_excess_terms={len(cap_excesses)}"
        )
        return stability_var
        
    def reset(self):
        # create scip model
        self.m = scip.Model()
        self._lexicographic_info = {}
        if self.single_instance_file == 'all':
            if not self.instances:
                raise ValueError(f"No instance files found in {self.instance_file_path}")
            instance_file = self.rng.choice(self.instances)
        else:
            instance_file = self.single_instance_file
        # instance_file = 'instance_9575.lp'
        logger.log(f"instance_file: {instance_file}")
        selected_instance_name = Path(str(instance_file)).name
        instance_file = self._resolve_instance_file(instance_file)
        logger.log(f"resolved_instance_file: {instance_file}")
        self.m.setIntParam('display/verblevel', self.scip_verbosity)
        self.m.readProblem(instance_file)
        self._strip_inactive_schedule_stability_constraints()
        self._apply_schedule_wait_cap()
        warm_start_file = self.warm_start_solution_file
        if str(warm_start_file).strip().lower() == "auto":
            warm_start_file = find_compatible_mixed_warm_start(
                self.instance_file_path,
                selected_instance_name,
            )
        if warm_start_file:
            warm_start_path = resolve_path(warm_start_file)
            if warm_start_path.is_file():
                try:
                    warm_start = self.m.readSolFile(str(warm_start_path))
                    fully_feasible = bool(
                        self.m.checkSol(
                            warm_start,
                            printreason=False,
                            completely=True,
                            original=True,
                        )
                    )
                    if fully_feasible:
                        stored = self.m.addSol(warm_start, free=True)
                        logger.log(
                            f"loaded feasible Petri warm start: {warm_start_path} (stored={stored})"
                        )
                    else:
                        self.m.freeSol(warm_start)
                        logger.log(
                            f"warning: rejected incomplete or infeasible Petri warm start: {warm_start_path}"
                        )
                except Exception as exc:
                    logger.log(f"warning: failed to load Petri warm start {warm_start_path}: {exc}")
            else:
                logger.log(f"warning: Petri warm start not found: {warm_start_path}")
        self.m.setRealParam('limits/time', self.scip_time_limit)
        # SCIP's default memory limit is effectively unlimited.  Dense 2x2
        # Petri instances can then grow the branch-and-bound tree until
        # Windows denies an allocation, which appears as a fatal SCIP_ERROR
        # instead of a normal solve status.  A positive cap lets SCIP stop
        # cleanly with status `memlimit` and keeps any incumbent (including
        # the constructive warm start) available for reporting.
        if self.scip_memory_limit_mb is not None and float(self.scip_memory_limit_mb) > 0:
            self.m.setRealParam('limits/memory', float(self.scip_memory_limit_mb))
        if self.scip_node_limit is not None and int(self.scip_node_limit) >= 0:
            self.m.setLongintParam('limits/nodes', int(self.scip_node_limit))
        if self.scip_stall_node_limit is not None and int(self.scip_stall_node_limit) >= 0:
            self.m.setLongintParam('limits/stallnodes', int(self.scip_stall_node_limit))
        if self.scip_solution_limit is not None and int(self.scip_solution_limit) > 0:
            self.m.setIntParam('limits/solutions', int(self.scip_solution_limit))
        self.m.setRealParam('limits/gap', max(0.0, float(self.scip_relative_gap_limit)))
        self.m.setRealParam('limits/absgap', max(0.0, float(self.scip_absolute_gap_limit)))
        self.m.setIntParam('timing/clocktype', 2)
        # Apply the broad preset first.  The explicit separator and heuristic
        # controls below must win; otherwise FEASIBILITY silently re-enables
        # expensive sub-SCIP heuristics and non-root separation.
        self._apply_scip_emphasis()
        self._init_scip_params(**self.init_scip_kwargs)
        self._apply_scip_heuristics_profile(
            enabled=bool(self.init_scip_kwargs.get('heuristics', True))
        )
        # SCIP emphasis presets may update many parameters. Reapply explicit
        # resource caps so a quality-oriented preset cannot remove them.
        self.m.setRealParam('limits/time', self.scip_time_limit)
        if self.scip_memory_limit_mb is not None and float(self.scip_memory_limit_mb) > 0:
            self.m.setRealParam('limits/memory', float(self.scip_memory_limit_mb))
        if self.scip_node_limit is not None and int(self.scip_node_limit) >= 0:
            self.m.setLongintParam('limits/nodes', int(self.scip_node_limit))
        if self.scip_stall_node_limit is not None and int(self.scip_stall_node_limit) >= 0:
            self.m.setLongintParam('limits/stallnodes', int(self.scip_stall_node_limit))
        if self.scip_solution_limit is not None and int(self.scip_solution_limit) > 0:
            self.m.setIntParam('limits/solutions', int(self.scip_solution_limit))
        self.m.setRealParam('limits/gap', max(0.0, float(self.scip_relative_gap_limit)))
        self.m.setRealParam('limits/absgap', max(0.0, float(self.scip_absolute_gap_limit)))
        self.m.setBoolParam('timing/rareclockcheck', bool(self.scip_rare_clock_check))
        if self.scip_lp_iteration_limit is not None and int(self.scip_lp_iteration_limit) >= 0:
            self.m.setLongintParam('lp/iterlim', int(self.scip_lp_iteration_limit))
        if self.scip_root_lp_iteration_limit is not None and int(self.scip_root_lp_iteration_limit) >= 0:
            self.m.setLongintParam('lp/rootiterlim', int(self.scip_root_lp_iteration_limit))
        logger.log(
            "effective SCIP limits: "
            f"time={self.scip_time_limit}s, "
            f"memory={self.scip_memory_limit_mb}MB, "
            f"nodes={self.scip_node_limit}, "
            f"stall_nodes={self.scip_stall_node_limit}, "
            f"solutions={self.scip_solution_limit}, emphasis={self.scip_emphasis}, "
            f"gap={self.scip_relative_gap_limit}, absgap={self.scip_absolute_gap_limit}, "
            f"heuristics_profile={self.scip_heuristics_profile}, "
            f"rare_clock_check={self.scip_rare_clock_check}, "
            f"lp_iter={self.scip_lp_iteration_limit}, "
            f"root_lp_iter={self.scip_root_lp_iteration_limit}, "
            f"interrupt_grace={self.scip_interrupt_grace_seconds}s, "
            f"stability_time={self.lexicographic_stability_time_limit}s, "
            f"stability_nodes={self.lexicographic_stability_node_limit}"
        )

        return instance_file

    def _apply_scip_emphasis(self):
        """Apply a named SCIP search preset after local parameter setup."""
        emphasis_name = str(self.scip_emphasis or "default").strip().lower()
        if emphasis_name in {"", "default", "none"}:
            return
        emphasis_map = {
            "optimality": scip.SCIP_PARAMEMPHASIS.OPTIMALITY,
            "feasibility": scip.SCIP_PARAMEMPHASIS.FEASIBILITY,
        }
        try:
            emphasis = emphasis_map[emphasis_name]
        except KeyError as exc:
            supported = ", ".join(sorted(emphasis_map))
            raise ValueError(
                f"Unsupported scip_emphasis `{self.scip_emphasis}`. "
                f"Use default, {supported}."
            ) from exc
        self.m.setEmphasis(emphasis, quiet=True)
        logger.log(f"applied SCIP emphasis: {emphasis_name}")

    def _apply_scip_heuristics_profile(self, enabled=True):
        if not enabled:
            self.m.setHeuristics(scip.SCIP_PARAMSETTING.OFF)
            logger.log("applied SCIP heuristics profile: off")
            return
        profile_name = str(self.scip_heuristics_profile or "default").strip().lower()
        profile_map = {
            "default": scip.SCIP_PARAMSETTING.DEFAULT,
            "fast": scip.SCIP_PARAMSETTING.FAST,
            "aggressive": scip.SCIP_PARAMSETTING.AGGRESSIVE,
            "off": scip.SCIP_PARAMSETTING.OFF,
        }
        try:
            profile = profile_map[profile_name]
        except KeyError as exc:
            supported = ", ".join(sorted(profile_map))
            raise ValueError(
                f"Unsupported scip_heuristics_profile `{self.scip_heuristics_profile}`. "
                f"Use {supported}."
            ) from exc
        if profile_name != "default":
            self.m.setHeuristics(profile)
        if self.scip_disable_expensive_heuristics:
            disabled = []
            available_params = self.m.getParams()
            for heuristic in ("alns", "rins", "subnlp", "multistart", "mpec"):
                param = f"heuristics/{heuristic}/freq"
                if param in available_params:
                    self.m.setIntParam(param, -1)
                    disabled.append(heuristic)
            logger.log(
                "disabled memory-intensive SCIP heuristics: "
                + ", ".join(disabled)
            )
        logger.log(f"applied SCIP heuristics profile: {profile_name}")

    def step(self, CutSel, solution_file=None):
        if CutSel is not None:
            # Keep this safeguard in the environment configuration so test,
            # evaluation, and training use the same bounded callback path.
            # Method-level settings may be stricter; never silently replace
            # them because that makes the reported ablation budget false.
            if hasattr(CutSel, "max_candidates"):
                env_cap = int(self.cutsel_max_candidates)
                agent_cap = CutSel.max_candidates
                if env_cap > 0:
                    CutSel.max_candidates = (
                        env_cap
                        if agent_cap is None or int(agent_cap) <= 0
                        else min(int(agent_cap), env_cap)
                    )
            if hasattr(CutSel, "max_selected_cuts"):
                env_cap = int(self.cutsel_max_selected_cuts)
                agent_cap = CutSel.max_selected_cuts
                if env_cap > 0:
                    CutSel.max_selected_cuts = (
                        env_cap
                        if agent_cap is None or int(agent_cap) <= 0
                        else min(int(agent_cap), env_cap)
                    )
            structure_rerank = getattr(
                self, "cutsel_use_structure_rerank", None
            )
            if (
                hasattr(CutSel, "use_structure_rerank")
                and structure_rerank is not None
            ):
                CutSel.use_structure_rerank = bool(structure_rerank)
            self.m.includeCutsel(
                cutsel=CutSel,
                name="RL trained cutsel",
                desc="",
                priority=666666
            )

        try:
            self._optimize_with_lexicographic_stability()
            stats = self._collect_stats()
            if solution_file and int(stats.get("n_solutions", 0) or 0) > 0:
                try:
                    self.m.writeSol(self.m.getBestSol(), str(solution_file))
                    stats["solution_file"] = str(solution_file)
                    stats["solution_write_error"] = None
                except Exception as exc:
                    stats["solution_file"] = None
                    stats["solution_write_error"] = f"{type(exc).__name__}: {exc}"
            if CutSel is not None:
                stats["cutsel_effective_max_candidates"] = getattr(
                    CutSel, "max_candidates", None
                )
                stats["cutsel_effective_max_selected_cuts"] = getattr(
                    CutSel, "max_selected_cuts", None
                )
                get_telemetry = getattr(CutSel, "get_telemetry", None)
                stats["cutsel_telemetry"] = (
                    get_telemetry() if callable(get_telemetry) else {}
                )
            return stats
        finally:
            self.m.freeProb()

    def solve_default(self, solution_file=None):
        try:
            self._optimize_with_lexicographic_stability()
            stats = self._collect_stats()
            if solution_file and int(stats.get("n_solutions", 0) or 0) > 0:
                try:
                    self.m.writeSol(self.m.getBestSol(), str(solution_file))
                    stats["solution_file"] = str(solution_file)
                    stats["solution_write_error"] = None
                except Exception as exc:
                    stats["solution_file"] = None
                    stats["solution_write_error"] = f"{type(exc).__name__}: {exc}"
            return stats
        finally:
            self.m.freeProb()

    def _var_by_name(self, name):
        for var in self.m.getVars():
            if var.name == name:
                return var
        return None

    def _optimize_with_lexicographic_stability(self):
        """Maximize WPH first, then stabilize only an equally fast schedule."""
        stability_time_limit = float(self.lexicographic_stability_time_limit)
        cmax_var = self._var_by_name("c_max")
        stability_var = self._var_by_name("schedule_stability")
        supports_schedule_stability = (
            cmax_var is not None and stability_var is not None
        )
        if (
            self.lexicographic_schedule_stability
            and stability_time_limit > 0
            and supports_schedule_stability
        ):
            primary_time_limit = max(
                1.0,
                float(self.scip_time_limit) - stability_time_limit,
            )
            self.m.setRealParam("limits/time", primary_time_limit)
            logger.log(
                "reserved lexicographic stability budget: "
                f"primary={primary_time_limit:.1f}s, stability={stability_time_limit:.1f}s"
            )
        primary_timer_start = time.perf_counter()
        self._optimize_with_watchdog("primary")
        primary_elapsed_time = time.perf_counter() - primary_timer_start
        primary_status = str(self.m.getStatus())
        primary_solution = self.m.getBestSol()
        primary_cmax = None
        if primary_solution is not None and cmax_var is not None:
            primary_cmax = float(self.m.getSolVal(primary_solution, cmax_var))

        self._lexicographic_info = {
            "primary_status": primary_status,
            "primary_cmax": primary_cmax,
            "primary_solving_time": float(primary_elapsed_time),
            "primary_scip_solving_time": float(self.m.getSolvingTime()),
            "primary_ntotal_nodes": float(self.m.getNTotalNodes()),
            "primary_primal_dual_gap": float(self.m.getGap()),
            "primary_primaldualintegral": self._safe_get_primal_dual_integral(),
            "stability_status": "not_run",
            "stability_solving_time": 0.0,
            "stability_scip_solving_time": 0.0,
            "stability_ntotal_nodes": 0.0,
        }
        logger.log(
            "lexicographic phase 1 (WPH): "
            f"status={primary_status}, c_max={primary_cmax}"
        )
        if not self.lexicographic_schedule_stability:
            return
        if primary_solution is None or primary_cmax is None:
            self._lexicographic_info["stability_status"] = "skipped_no_primary_solution"
            return
        if cmax_var is None or stability_var is None:
            self._lexicographic_info["stability_status"] = "skipped_non_petri_model"
            return

        fixed_discrete_values = {}
        if self.lexicographic_fix_discrete_decisions:
            for var in self.m.getVars():
                if var.vtype() in {"BINARY", "INTEGER", "IMPLINT"}:
                    # Robot batching is part of schedule-quality optimization,
                    # not a routing identity. Keep these choices free so phase
                    # 2 can select double-gripper operation when it reduces
                    # the global squared-wait objective.
                    if self.lexicographic_free_double_decisions and "_double_" in var.name:
                        continue
                    fixed_discrete_values[var.name] = round(
                        float(self.m.getSolVal(primary_solution, var))
                    )

        primary_solving_time = float(primary_elapsed_time)
        remaining_time = max(0.0, float(self.scip_time_limit) - primary_solving_time)
        if remaining_time <= 1e-6:
            self._lexicographic_info["stability_status"] = "skipped_no_time_budget"
            return
        if stability_time_limit <= 1e-6:
            self._lexicographic_info["stability_status"] = "skipped_stability_time_disabled"
            return
        phase2_time_limit = min(remaining_time, stability_time_limit)

        self.m.freeTransform()
        cmax_var = self._var_by_name("c_max")
        stability_var = self._var_by_name("schedule_stability")
        if fixed_discrete_values:
            fixed_count = 0
            for var in self.m.getVars():
                value = fixed_discrete_values.get(var.name)
                if value is None:
                    continue
                self.m.chgVarLb(var, value)
                self.m.chgVarUb(var, value)
                fixed_count += 1
            logger.log(
                "lexicographic phase 2: fixed "
                f"{fixed_count} discrete routing/order decisions from the primary incumbent"
            )
        if self.schedule_stability_mode == "linear":
            stability_var = self._configure_linear_stability_objective(
                fixed_discrete_values
            )
            if stability_var is None:
                self._lexicographic_info["stability_status"] = "skipped_non_petri_model"
                return
        self.m.addCons(
            cmax_var <= primary_cmax + float(self.lexicographic_cmax_tolerance),
            name="lexicographic_primary_cmax_fix",
        )
        self.m.setObjective(stability_var, "minimize")
        self.m.setRealParam("limits/time", phase2_time_limit)
        # Primary smoke-test/stagnation limits must not immediately terminate
        # the continuous schedule-compaction phase.  Users can disable phase 2
        # explicitly with lexicographic_stability_time_limit=0.
        self.m.setIntParam("limits/solutions", -1)
        self.m.setLongintParam("limits/stallnodes", -1)
        stability_node_limit = int(self.lexicographic_stability_node_limit)
        if stability_node_limit >= 0:
            self.m.setLongintParam("limits/nodes", stability_node_limit)

        stability_timer_start = time.perf_counter()
        self._optimize_with_watchdog("stability")
        stability_elapsed_time = time.perf_counter() - stability_timer_start
        stability_status = str(self.m.getStatus())
        self._lexicographic_info.update(
            {
                "stability_solving_time": float(stability_elapsed_time),
                "stability_scip_solving_time": float(self.m.getSolvingTime()),
                "stability_ntotal_nodes": float(self.m.getNTotalNodes()),
                "stability_primal_dual_gap": float(self.m.getGap()),
                "stability_primaldualintegral": (
                    self._safe_get_primal_dual_integral()
                ),
            }
        )
        if primary_status != "optimal":
            stability_status = f"incumbent_{primary_status}_{stability_status}"
        self._lexicographic_info["stability_status"] = stability_status
        logger.log(
            "lexicographic phase 2 (stability): "
            f"status={self._lexicographic_info['stability_status']}"
        )

    def _optimize_with_watchdog(self, phase):
        """Ask SCIP to return cleanly if a native LP call overruns its time limit."""
        try:
            solve_limit = float(self.m.getParam("limits/time"))
        except Exception:
            solve_limit = float(self.scip_time_limit)
        grace = max(0.0, float(self.scip_interrupt_grace_seconds))
        watchdog = None
        if 0.0 < solve_limit < 1e19:
            delay = solve_limit + grace

            def interrupt_solve():
                try:
                    logger.log(
                        f"SCIP {phase} watchdog fired after {delay:.1f}s; "
                        "requesting a clean solver interruption"
                    )
                    self.m.interruptSolve()
                except Exception as exc:
                    try:
                        logger.log(f"warning: SCIP watchdog interrupt failed: {exc}")
                    except Exception:
                        pass

            watchdog = threading.Timer(delay, interrupt_solve)
            watchdog.daemon = True
            watchdog.start()
        try:
            self.m.optimize()
        finally:
            if watchdog is not None:
                watchdog.cancel()

    def _collect_stats(self):
        stats = {}
        best_sol = self.m.getBestSol()
        cmax_var = self._var_by_name("c_max")
        stability_var = self._var_by_name("schedule_stability")
        final_cmax = None
        final_stability = None
        if best_sol is not None:
            if cmax_var is not None:
                final_cmax = float(self.m.getSolVal(best_sol, cmax_var))
            if stability_var is not None:
                final_stability = float(self.m.getSolVal(best_sol, stability_var))
        current_solving_time = float(self.m.getSolvingTime())
        current_nodes = float(self.m.getNTotalNodes())
        current_gap = float(self.m.getGap())
        current_pdi = self._safe_get_primal_dual_integral()
        primary_time = self._lexicographic_info.get("primary_solving_time")
        stability_time = float(
            self._lexicographic_info.get("stability_solving_time", 0.0) or 0.0
        )
        primary_nodes = self._lexicographic_info.get("primary_ntotal_nodes")
        stability_nodes = float(
            self._lexicographic_info.get("stability_ntotal_nodes", 0.0) or 0.0
        )
        primary_gap = self._lexicographic_info.get("primary_primal_dual_gap")
        primary_pdi = self._lexicographic_info.get("primary_primaldualintegral")

        # SCIP resets several counters when freeTransform() starts the
        # lexicographic schedule-compaction phase. Ablation metrics must use
        # phase-one gap/PDI (the Cmax objective being compared) and cumulative
        # two-stage time; otherwise a fast phase two appears as a blank 0 s.
        stats['primary_solving_time'] = (
            current_solving_time if primary_time is None else float(primary_time)
        )
        stats['primary_scip_solving_time'] = self._lexicographic_info.get(
            "primary_scip_solving_time", current_solving_time
        )
        stats['stability_solving_time'] = stability_time
        stats['stability_scip_solving_time'] = self._lexicographic_info.get(
            "stability_scip_solving_time", 0.0
        )
        stats['solving_time'] = stats['primary_solving_time'] + stability_time
        stats['scip_solving_time_raw'] = current_solving_time
        stats['primary_ntotal_nodes'] = (
            current_nodes if primary_nodes is None else float(primary_nodes)
        )
        stats['stability_ntotal_nodes'] = stability_nodes
        stats['ntotal_nodes'] = stats['primary_ntotal_nodes']
        stats['total_ntotal_nodes'] = stats['primary_ntotal_nodes'] + stability_nodes
        stats['primal_dual_gap'] = (
            current_gap if primary_gap is None else float(primary_gap)
        )
        stats['primaldualintegral'] = (
            current_pdi if primary_pdi is None else primary_pdi
        )
        stats['primary_primal_dual_gap'] = stats['primal_dual_gap']
        stats['primary_primaldualintegral'] = stats['primaldualintegral']
        stats['stability_primal_dual_gap'] = self._lexicographic_info.get(
            "stability_primal_dual_gap"
        )
        stats['stability_primaldualintegral'] = self._lexicographic_info.get(
            "stability_primaldualintegral"
        )
        primary_status = self._lexicographic_info.get("primary_status")
        stats['status'] = primary_status or str(self.m.getStatus())
        stats['primary_status'] = primary_status
        stats['stability_status'] = self._lexicographic_info.get("stability_status")
        stats['primary_cmax'] = self._lexicographic_info.get("primary_cmax", final_cmax)
        stats['schedule_stability'] = final_stability
        stats['n_solutions'] = self.m.getNSols()
        # Keep existing reporting and ablation tables WPH-oriented even after
        # phase two changes SCIP's active objective to schedule_stability.
        stats['best_obj'] = final_cmax if final_cmax is not None else self._safe_get_best_obj()
        stats['solution'] = self._extract_best_solution()
        stats.update(self._calculate_schedule_wait_metrics())
        return stats

    def _calculate_schedule_wait_metrics(self):
        best_sol = self.m.getBestSol()
        empty_metrics = {
            'schedule_pm_wait_square': 0.0,
            'schedule_module_wait_square': 0.0,
            'schedule_robot_wait_square': 0.0,
            'schedule_chamber_idle_square': 0.0,
            'schedule_wait_penalty': 0.0,
            'schedule_total_wait': 0.0,
            'schedule_max_wait': 0.0,
            'schedule_cadence_gap_mean': 0.0,
            'schedule_cadence_gap_std': 0.0,
            'schedule_cadence_cv': 0.0,
            'schedule_cadence_deviation_sum': 0.0,
        }
        if best_sol is None:
            return empty_metrics

        stage_values = {}
        chamber_idle_totals = []
        named_values = {}
        stage_pattern = re.compile(r'^prod_stage_(start|end)_(\d+)_(.+)$')
        for var in self.m.getVars():
            try:
                value = float(self.m.getSolVal(best_sol, var))
            except Exception:
                continue
            named_values[var.name] = value
            match = stage_pattern.match(var.name)
            if match:
                edge, wafer_id, stage = match.groups()
                stage_values[(int(wafer_id), edge, stage)] = value
            elif var.name.startswith('chamber_idle_total_'):
                chamber_idle_totals.append(value)

        def stage_value(wafer_id, edge, stage):
            return stage_values.get((wafer_id, edge, stage))

        def positive_gap(later, earlier, offset=0.0):
            if later is None or earlier is None:
                return 0.0
            return max(0.0, later - earlier - offset)

        pm_wait_square = 0.0
        module_wait_square = 0.0
        robot_wait_square = 0.0
        atr_loaded_transfer_time = 2.0 * self.schedule_vtr_transfer_time + self.schedule_atr_transfer_time
        atr_loaded_return_time = 2.0 * self.schedule_vtr_transfer_time + self.schedule_atr_return_time
        wafer_ids = sorted({wafer_id for wafer_id, _, _ in stage_values})
        for wafer_id in wafer_ids:
            pm_waits = (
                positive_gap(stage_value(wafer_id, 'start', 'pm'), stage_value(wafer_id, 'end', 'vtr_load')),
                positive_gap(stage_value(wafer_id, 'start', 'vtr_unload'), stage_value(wafer_id, 'end', 'pm')),
            )
            module_waits = (
                positive_gap(stage_value(wafer_id, 'start', 'al'), stage_value(wafer_id, 'end', 'atr_lp_al')),
                positive_gap(stage_value(wafer_id, 'start', 'atr_al_llupper'), stage_value(wafer_id, 'end', 'al')),
                positive_gap(stage_value(wafer_id, 'start', 'llupper'), stage_value(wafer_id, 'end', 'atr_al_llupper')),
                positive_gap(stage_value(wafer_id, 'start', 'vtr_load'), stage_value(wafer_id, 'end', 'llupper')),
                positive_gap(stage_value(wafer_id, 'start', 'lllower'), stage_value(wafer_id, 'end', 'vtr_unload')),
                positive_gap(stage_value(wafer_id, 'start', 'atr_lllower_lp'), stage_value(wafer_id, 'end', 'lllower')),
            )
            robot_waits = (
                positive_gap(stage_value(wafer_id, 'end', 'atr_lp_al'), stage_value(wafer_id, 'start', 'atr_lp_al'), atr_loaded_transfer_time),
                positive_gap(stage_value(wafer_id, 'end', 'atr_al_llupper'), stage_value(wafer_id, 'start', 'atr_al_llupper'), atr_loaded_transfer_time),
                positive_gap(stage_value(wafer_id, 'end', 'vtr_load'), stage_value(wafer_id, 'start', 'vtr_load'), self.schedule_vtr_transfer_time),
                positive_gap(stage_value(wafer_id, 'end', 'vtr_unload'), stage_value(wafer_id, 'start', 'vtr_unload'), self.schedule_vtr_transfer_time),
                positive_gap(stage_value(wafer_id, 'end', 'atr_lllower_lp'), stage_value(wafer_id, 'start', 'atr_lllower_lp'), atr_loaded_return_time),
            )
            pm_wait_square += sum(wait * wait for wait in pm_waits)
            module_wait_square += sum(wait * wait for wait in module_waits)
            robot_wait_square += sum(wait * wait for wait in robot_waits)

        chamber_idle_square = sum(max(0.0, idle) ** 2 for idle in chamber_idle_totals)
        wait_penalty = (
            self.schedule_pm_wait_square_penalty * pm_wait_square
            + self.schedule_module_wait_square_penalty * module_wait_square
            + self.schedule_robot_wait_square_penalty * robot_wait_square
            + self.schedule_chamber_idle_square_penalty * chamber_idle_square
        )
        linear_wait_prefixes = (
            'llupper_wait_',
            'lllower_wait_',
            'full_pair_post_process_wait_',
            'mix_pair_post_process_wait_',
            'full_batch_idle_',
            'full_to_mix_idle_',
            'mix_cycle_to_bridge_idle_',
            'mix_tail_idle_',
            'chamber_idle_total_',
        )
        linear_waits = [
            max(0.0, value)
            for name, value in named_values.items()
            if name.startswith(linear_wait_prefixes)
            or (
                name.startswith('schedule_wait_')
                and not name.startswith('schedule_wait_square_')
            )
        ]
        individual_waits = [
            max(0.0, value)
            for name, value in named_values.items()
            if (
                name.startswith(linear_wait_prefixes)
                or (
                    name.startswith('schedule_wait_')
                    and not name.startswith('schedule_wait_square_')
                )
            )
            and not name.startswith('chamber_idle_total_')
        ]

        cadence_gaps = []
        cadence_deviations = []
        for mode, start_pattern, used_template, epoch_prefix in (
            ('full', re.compile(r'^full_start_(\d+)_(\d+)$'), 'full_batch_used', 'full_batch_epoch'),
            ('mix', re.compile(r'^mix_cycle_start_(\d+)_(\d+)$'), 'mix_cycle_used', 'mix_cycle_epoch'),
        ):
            grouped = {}
            for name, value in named_values.items():
                match = start_pattern.match(name)
                if not match:
                    continue
                chamber, position = (int(item) for item in match.groups())
                if named_values.get(f'{used_template}_{chamber}_{position}', 0.0) < 0.5:
                    continue
                epoch = 0
                marker = f'{epoch_prefix}_{chamber}_{position}_'
                for candidate, candidate_value in named_values.items():
                    if candidate_value >= 0.5 and candidate.startswith(marker):
                        epoch = int(candidate.rsplit('_', 1)[-1])
                        break
                grouped.setdefault((mode, chamber, epoch), []).append((position, value))
            for items in grouped.values():
                starts = [value for _, value in sorted(items)]
                gaps = [right - left for left, right in zip(starts, starts[1:])]
                cadence_gaps.extend(gaps)
                cadence_deviations.extend(
                    abs(right - left) for left, right in zip(gaps, gaps[1:])
                )
        cadence_mean = float(np.mean(cadence_gaps)) if cadence_gaps else 0.0
        cadence_std = float(np.std(cadence_gaps)) if cadence_gaps else 0.0
        return {
            'schedule_pm_wait_square': pm_wait_square,
            'schedule_module_wait_square': module_wait_square,
            'schedule_robot_wait_square': robot_wait_square,
            'schedule_chamber_idle_square': chamber_idle_square,
            'schedule_wait_penalty': wait_penalty,
            'schedule_total_wait': float(sum(linear_waits)),
            'schedule_max_wait': float(max(individual_waits, default=0.0)),
            'schedule_cadence_gap_mean': cadence_mean,
            'schedule_cadence_gap_std': cadence_std,
            'schedule_cadence_cv': 0.0 if cadence_mean <= 1e-12 else cadence_std / cadence_mean,
            'schedule_cadence_deviation_sum': float(sum(cadence_deviations)),
        }

    def _safe_get_best_obj(self):
        if self.m.getNSols() <= 0 or self.m.getBestSol() is None:
            return None
        try:
            return float(self.m.getObjVal())
        except Exception:
            return None

    def _safe_get_primal_dual_integral(self):
        if hasattr(self.m, "getPrimalDualIntegral"):
            try:
                return float(self.m.getPrimalDualIntegral())
            except Exception:
                pass
        # Missing API support is not a perfect score. Keep it unavailable so
        # the ablation report can render n/a instead of a misleading zero.
        return None

    def _extract_best_solution(self):
        best_sol = self.m.getBestSol()
        if best_sol is None:
            return {}

        result = {}
        for var in self.m.getVars():
            try:
                value = float(self.m.getSolVal(best_sol, var))
            except Exception:
                continue
            if abs(value) > 1e-12:
                result[var.name] = value
        return result

    def set_random_seed(self, seed):
        self.rng = np.random.RandomState(seed)
# test
if __name__ == '__main__':
    # test SCIPCutSelEnv
    instance_file_path = "../dataset/data/instances/setcover/train_500r_1000c_0.05d"
    seed = 0
    init_scip_kwargs = {
        'presolving': True,
        'separating': True,
        'conflict': True,
        'heuristics': True
    }
    env = SCIPCutSelEnv(
        instance_file_path,
        seed,
        scip_time_limit=3600,
        **init_scip_kwargs   
    )

    instance_file = env.reset()
    print(f"instance_file: {instance_file}")

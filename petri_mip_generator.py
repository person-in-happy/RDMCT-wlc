import argparse
import math
import os
import re
from dataclasses import dataclass
from typing import Dict, List

from path_utils import append_date_to_filename, resolve_path
from scip_imports import scip


MODE_MIX = "2x2"
MODE_FULL = "4x1"
PROCESS_MODE_AUTO = "auto"
PROCESS_MODE_MIXED = "mixed"
PROCESS_MODE_CUSTOM = "custom"
_MODE_TOKEN_RE = re.compile(r"[,\s;|]+")


def _normalize_mode_token(token: str) -> str:
    cleaned = (
        token.strip()
        .lower()
        .replace("脳", "x")
        .replace("×", "x")
        .replace("＊", "x")
        .replace("_", "")
        .replace("-", "")
    )
    aliases = {
        "2x2": MODE_MIX,
        "2": MODE_MIX,
        "mix": MODE_MIX,
        "mixed": MODE_MIX,
        "pipeline": MODE_MIX,
        "4x1": MODE_FULL,
        "4": MODE_FULL,
        "full": MODE_FULL,
        "batch": MODE_FULL,
    }
    if cleaned not in aliases:
        raise ValueError(
            f"Unsupported mode token `{token}`. Use only `2x2` / `4x1` or their simple aliases."
        )
    return aliases[cleaned]


def _normalize_process_mode(token: str) -> str:
    cleaned = (
        (token or PROCESS_MODE_AUTO)
        .strip()
        .lower()
        .replace("脳", "x")
        .replace("×", "x")
        .replace("＊", "x")
        .replace("_", "")
        .replace("-", "")
    )
    aliases = {
        "": PROCESS_MODE_AUTO,
        "auto": PROCESS_MODE_AUTO,
        "default": PROCESS_MODE_AUTO,
        "count": PROCESS_MODE_AUTO,
        "counts": PROCESS_MODE_AUTO,
        "both": PROCESS_MODE_MIXED,
        "mixed": PROCESS_MODE_MIXED,
        "mixrun": PROCESS_MODE_MIXED,
        "hybrid": PROCESS_MODE_MIXED,
        "custom": PROCESS_MODE_CUSTOM,
        "sequence": PROCESS_MODE_CUSTOM,
        "wafer": PROCESS_MODE_CUSTOM,
        "waferlevel": PROCESS_MODE_CUSTOM,
        "perwafer": PROCESS_MODE_CUSTOM,
        "4x1": MODE_FULL,
        "4": MODE_FULL,
        "full": MODE_FULL,
        "fullonly": MODE_FULL,
        "only4x1": MODE_FULL,
        "2x2": MODE_MIX,
        "2": MODE_MIX,
        "mix": MODE_MIX,
        "pipeline": MODE_MIX,
        "mixonly": MODE_MIX,
        "only2x2": MODE_MIX,
    }
    if cleaned not in aliases:
        raise ValueError(
            f"Unsupported process_mode `{token}`. Use auto, mixed, custom, 4x1, or 2x2."
        )
    return aliases[cleaned]


def _parse_mode_sequence(total_wafers: int, mode_sequence: str) -> List[str]:
    raw_tokens = [token for token in _MODE_TOKEN_RE.split(mode_sequence.strip()) if token]
    if not raw_tokens:
        return []

    modes = [_normalize_mode_token(token) for token in raw_tokens]
    if total_wafers > 0 and total_wafers % 2 == 0 and len(modes) == total_wafers // 2:
        expanded: List[str] = []
        for mode in modes:
            expanded.extend([mode, mode])
        return expanded
    if total_wafers > 0 and len(modes) != total_wafers:
        raise ValueError(
            "mode_sequence length must equal either the number of product wafers "
            f"({total_wafers}) or the legacy even pair count ({total_wafers // 2})."
        )
    return modes


def _parse_wafer_mode_map(wafer_mode_map: str) -> Dict[int, str]:
    assignments: Dict[int, str] = {}
    raw_tokens = [token for token in _MODE_TOKEN_RE.split(wafer_mode_map.strip()) if token]
    for raw_token in raw_tokens:
        if "=" in raw_token:
            wafer_token, mode_token = raw_token.split("=", 1)
        elif ":" in raw_token:
            wafer_token, mode_token = raw_token.split(":", 1)
        else:
            raise ValueError(
                f"Invalid wafer mode assignment `{raw_token}`. Use forms like W3:2x2 or 3=4x1."
            )

        wafer_token = wafer_token.strip().lower()
        if wafer_token.startswith("wafer"):
            wafer_token = wafer_token[5:]
        if wafer_token.startswith("w"):
            wafer_token = wafer_token[1:]
        if not wafer_token.isdigit():
            raise ValueError(
                f"Invalid wafer id in assignment `{raw_token}`. Use a 1-based product wafer id."
            )
        wafer_id = int(wafer_token)
        if wafer_id <= 0:
            raise ValueError(f"Wafer ids are 1-based, got `{wafer_id}` in `{raw_token}`.")
        if wafer_id in assignments:
            raise ValueError(f"Duplicate wafer mode assignment for W{wafer_id}.")
        assignments[wafer_id] = _normalize_mode_token(mode_token)
    return assignments


def _pair_loads(num_mode_wafers: int) -> Dict[int, int]:
    num_pairs = math.ceil(num_mode_wafers / 2.0)
    if num_pairs <= 0:
        return {}
    loads = {pair_id: 2 for pair_id in range(1, num_pairs + 1)}
    if num_mode_wafers % 2 == 1:
        loads[num_pairs] = 1
    return loads


def _format_wafer_ids(wafer_ids: List[int], max_items: int = 12) -> str:
    if not wafer_ids:
        return "none"
    labels = [f"W{wafer_id}" for wafer_id in wafer_ids]
    if len(labels) <= max_items:
        return ", ".join(labels)
    return ", ".join(labels[:max_items]) + ", ..."


def _format_wafer_mode_summary(modes: List[str], max_items: int = 24) -> str:
    labels = [f"W{idx}:{mode}" for idx, mode in enumerate(modes, start=1)]
    if len(labels) <= max_items:
        return ", ".join(labels)
    return ", ".join(labels[:max_items]) + ", ..."


@dataclass
class PetriMIPConfig:
    num_batches: int = 10
    num_pm: int = 2
    num_steps: int = 13
    total_wafers: int = 0
    pec_pool_size: int = 8
    batch_size: int = 4
    big_m: float = 10000.0
    pm_transfer_gap: float = 1.0
    pm_rotation_time_180: float = 2.0
    pair_transfer_time: float = 4.0
    atr_transfer_time: float = 3.0
    atr_return_time: float = 3.0
    atr_capacity: int = 2
    vtr_capacity: int = 4
    aligner_time: float = 20.0
    llupper_time: float = 30.0
    lllower_time: float = 25.0
    full_process_time: float = 180.0
    # A 2x2 product PW pair is exposed twice in adjacent cycles. Both
    # exposures use the same physical recipe duration.
    mix_boundary_process_time: float = 130.0
    mix_internal_process_time: float = 130.0
    cleaning_interval: int = 10
    cleaning_process_time: float = 500.0
    max_module_residency_time: float = 10000.0
    max_robot_residency_time: float = 10000.0
    # Per-interval cap for avoidable schedule waits; zero disables the cap.
    max_schedule_wait_time: float = 0.0
    pm_balance_penalty: float = 0.01
    chamber_idle_penalty: float = 1e-4
    post_process_wait_penalty: float = 0.05
    ll_wait_penalty: float = 1e-4
    # High-priority penalty for wafers residing in a rotary chamber while no
    # chamber process recipe is running. It is applied per non-process chamber
    # window, so one long 2x2 bridge/tail wait is penalized directly instead
    # of being diluted into a per-CH total.
    chamber_nonprocess_wait_square_penalty: float = 1e-2
    # A VTR has enough fingers to carry both product wafers of a PW pair in
    # one same-route action.  This is the physical default for 4x1 work.
    force_full_vtr_double: bool = True
    # ATR also has two grippers. Complete 4x1 product pairs use bundled
    # LP->AL, AL->LLupper, and LLlower->LP transfers.
    force_full_atr_double: bool = True
    # The original pure-4x1 ATR chain forced every LLlower->LP return into a
    # fixed AL-service gap. That hand-crafted cycle becomes infeasible for
    # larger pure 4x1 workloads, so use the validated generic ATR resource
    # model by default. Keep the legacy chain opt-in only for reproduction of
    # older experiments.
    use_legacy_pure_full_atr_chain: bool = False
    # 2x2 product PW pairs should use the same two-product robot behavior as
    # 4x1 pairs before and after chamber processing. A tail product+PEC pair
    # still has only one product wafer and is fixed to single-product action.
    force_mix_atr_double: bool = True
    force_mix_vtr_double: bool = True
    process_mode: str = PROCESS_MODE_AUTO
    mode_sequence: str = ""
    wafer_mode_map: str = ""
    default_wafer_mode: str = ""
    full_mode_wafers: int = 10
    mix_mode_wafers: int = 10
    load_ports: int = 4
    load_port_slots: int = 25
    pec_storage_slots: int = 10

    @property
    def pm_ids(self) -> List[int]:
        if self.num_pm == 2:
            return [2, 3]
        return list(range(1, self.num_pm + 1))

    @property
    def product_wafer_modes(self) -> List[str]:
        modes = self._base_product_wafer_modes()
        wafer_overrides = _parse_wafer_mode_map(self.wafer_mode_map) if self.wafer_mode_map.strip() else {}
        if not wafer_overrides:
            return modes

        target_total = self.total_wafers or len(modes) or max(wafer_overrides)
        if modes and target_total != len(modes):
            raise ValueError(
                "wafer_mode_map target count disagrees with the resolved wafer list. "
                f"Resolved {len(modes)} wafers but total_wafers is {target_total}."
            )
        if not modes:
            default_mode = _normalize_mode_token(self.default_wafer_mode) if self.default_wafer_mode.strip() else ""
            if default_mode:
                modes = [default_mode] * target_total
            else:
                missing_ids = [w for w in range(1, target_total + 1) if w not in wafer_overrides]
                if missing_ids:
                    raise ValueError(
                        "wafer_mode_map does not cover every product wafer. "
                        "Provide --default_wafer_mode or assign all wafer ids. "
                        f"First missing wafer: W{missing_ids[0]}."
                    )
                modes = [wafer_overrides[w] for w in range(1, target_total + 1)]

        for wafer_id, mode in wafer_overrides.items():
            if wafer_id > len(modes):
                raise ValueError(
                    f"wafer_mode_map references W{wafer_id}, but only {len(modes)} product wafers are configured."
                )
            modes[wafer_id - 1] = mode
        return modes

    def _base_product_wafer_modes(self) -> List[str]:
        process_mode = _normalize_process_mode(self.process_mode)
        explicit_count = self.full_mode_wafers + self.mix_mode_wafers
        if self.mode_sequence and self.mode_sequence.strip():
            return _parse_mode_sequence(self.total_wafers, self.mode_sequence)
        if self.wafer_mode_map.strip() and process_mode == PROCESS_MODE_AUTO:
            if self.default_wafer_mode.strip() or (
                self.total_wafers > 0 and self.total_wafers != explicit_count
            ):
                return []
        if process_mode == PROCESS_MODE_CUSTOM:
            return []
        if process_mode == MODE_FULL:
            count = self.total_wafers if self.total_wafers > 0 else self.full_mode_wafers
            if count <= 0:
                raise ValueError("process_mode=4x1 requires --total_wafers or --mode_4x1_wafers > 0.")
            return [MODE_FULL] * count
        if process_mode == MODE_MIX:
            count = self.total_wafers if self.total_wafers > 0 else self.mix_mode_wafers
            if count <= 0:
                raise ValueError("process_mode=2x2 requires --total_wafers or --mode_2x2_wafers > 0.")
            return [MODE_MIX] * count
        if explicit_count <= 0:
            if self.total_wafers > 0:
                raise ValueError(
                    "Provide explicit per-mode counts, set --process_mode to 4x1/2x2, "
                    "or provide wafer-level mode_sequence/wafer_mode_map."
                )
            raise ValueError("At least one product wafer is required.")
        if self.total_wafers not in (0, explicit_count):
            raise ValueError(
                "total_wafers is inconsistent with the explicit per-mode counts. "
                f"Expected 0 or {explicit_count}, got {self.total_wafers}."
            )
        return [MODE_FULL] * self.full_mode_wafers + [MODE_MIX] * self.mix_mode_wafers

    @property
    def total_product_wafers(self) -> int:
        return len(self.product_wafer_modes)

    @property
    def product_wafer_ids(self) -> List[int]:
        return list(range(1, self.total_product_wafers + 1))

    @property
    def full_wafer_ids(self) -> List[int]:
        return [
            wafer_id
            for wafer_id, mode in enumerate(self.product_wafer_modes, start=1)
            if mode == MODE_FULL
        ]

    @property
    def mix_wafer_ids(self) -> List[int]:
        return [
            wafer_id
            for wafer_id, mode in enumerate(self.product_wafer_modes, start=1)
            if mode == MODE_MIX
        ]

    @property
    def num_full_pairs(self) -> int:
        return math.ceil(len(self.full_wafer_ids) / 2.0)

    @property
    def num_mix_pairs(self) -> int:
        return math.ceil(len(self.mix_wafer_ids) / 2.0)

    @property
    def full_pair_ids(self) -> List[int]:
        return list(range(1, self.num_full_pairs + 1))

    @property
    def mix_pair_ids(self) -> List[int]:
        return list(range(1, self.num_mix_pairs + 1))

    @property
    def full_pair_product_loads(self) -> Dict[int, int]:
        return _pair_loads(len(self.full_wafer_ids))

    @property
    def mix_pair_product_loads(self) -> Dict[int, int]:
        return _pair_loads(len(self.mix_wafer_ids))

    @property
    def num_full_batches_per_pm(self) -> int:
        # One 4x1 batch contains exactly two PW pairs, so this is the tightest
        # safe per-chamber upper bound even if all 4x1 work is sent to one PM.
        return max(1, math.ceil(self.num_full_pairs / 2.0))

    @property
    def num_full_slots_per_pm(self) -> int:
        return self.num_full_batches_per_pm

    @property
    def num_mix_positions_per_pm(self) -> int:
        return max(1, self.num_mix_pairs)

    @property
    def num_mix_cycles_per_pm(self) -> int:
        layouts = _canonical_cleaning_layout(self)
        return max(1, *(layout["mix_cycle_count"] for layout in layouts.values()))

    @property
    def max_chamber_processes_per_pm(self) -> int:
        return self.num_full_slots_per_pm + self.num_mix_cycles_per_pm

    @property
    def num_clean_slots_per_pm(self) -> int:
        if self.cleaning_interval <= 0:
            return 0
        layouts = _canonical_cleaning_layout(self)
        return max(0, *(max(0, layout["last_epoch"] - 1) for layout in layouts.values()))

    @property
    def effective_cleaning_process_time(self) -> float:
        if self.cleaning_process_time > 0:
            return self.cleaning_process_time
        return 2.0 * self.full_process_time

    @property
    def atr_load_unload_time(self) -> float:
        """ATR load or unload duration; it matches one VTR transfer action."""
        return self.pair_transfer_time

    @property
    def atr_lp_al_total_time(self) -> float:
        return 2.0 * self.atr_load_unload_time + self.atr_transfer_time

    @property
    def atr_al_llupper_total_time(self) -> float:
        return 2.0 * self.atr_load_unload_time + self.atr_transfer_time

    @property
    def atr_lllower_lp_total_time(self) -> float:
        return 2.0 * self.atr_load_unload_time + self.atr_return_time

    @property
    def atr_empty_ll_to_lp_time(self) -> float:
        """Empty return from LL to LP through AL: LL->AL plus AL->LP."""
        return 2.0 * self.atr_transfer_time

    @property
    def al_exchange_time(self) -> float:
        """Pick the calibrated wafer from AL, then place its companion into AL."""
        return 2.0 * self.atr_load_unload_time

    @property
    def al_companion_place_time(self) -> float:
        """Place a held companion into AL after the first wafer was sent to LL."""
        return self.atr_load_unload_time

    @property
    def max_product_capacity(self) -> int:
        return self.load_ports * self.load_port_slots

    @property
    def mix_process_time(self) -> float:
        return self.mix_boundary_process_time

    def validate(self) -> None:
        _normalize_process_mode(self.process_mode)
        if self.default_wafer_mode.strip():
            _normalize_mode_token(self.default_wafer_mode)
        if self.num_pm != 2:
            raise ValueError("This device contains only CH2 and CH3, so num_pm must be 2.")
        if self.num_batches <= 0:
            raise ValueError("num_batches must be positive.")
        if self.batch_size != 4:
            raise ValueError("batch_size is fixed to 4 for the four-pocket rotary chamber.")
        if self.total_wafers < 0 or self.full_mode_wafers < 0 or self.mix_mode_wafers < 0:
            raise ValueError("Wafer counts must be non-negative.")
        if self.total_product_wafers <= 0:
            raise ValueError("At least one product wafer is required.")
        if self.total_product_wafers > self.max_product_capacity:
            raise ValueError(
                "Product wafer count exceeds LP capacity. "
                f"Capacity is {self.max_product_capacity}, got {self.total_product_wafers}."
            )
        if self.pec_pool_size < 0 or self.pec_pool_size > self.pec_storage_slots:
            raise ValueError(
                "pec_pool_size must stay within PEC storage capacity. "
                f"Storage slots: {self.pec_storage_slots}, got {self.pec_pool_size}."
            )
        if self.pec_pool_size < 4 * self.num_pm or self.pec_pool_size % self.num_pm != 0:
            raise ValueError(
                "The technical disclosure binds four PEC wafers to each rotary chamber. "
                f"Need a multiple of num_pm and at least {4 * self.num_pm}, got {self.pec_pool_size}."
            )
        if self.cleaning_interval < 0:
            raise ValueError("cleaning_interval must be non-negative; use 0 only to disable cleaning constraints.")
        if self.mix_wafer_ids and self.cleaning_interval == 1:
            raise ValueError(
                "cleaning_interval=1 cannot complete a 2x2 product pair: each pair needs two "
                "consecutive process exposures. Use cleaning_interval=0 to disable cleaning or "
                "set it to at least 2."
            )
        if self.cleaning_process_time < 0:
            raise ValueError("cleaning_process_time must be non-negative.")
        if (
            self.max_module_residency_time < 0
            or self.max_robot_residency_time < 0
            or self.max_schedule_wait_time < 0
        ):
            raise ValueError("Residency-time limits must be non-negative.")
        if self.atr_capacity <= 0:
            raise ValueError("atr_capacity must be positive.")
        if self.vtr_capacity < 2:
            raise ValueError("vtr_capacity must be at least 2 because VTR transfer tasks carry wafer pairs.")
        if abs(self.mix_boundary_process_time - self.mix_internal_process_time) > 1e-9:
            raise ValueError(
                "2x2 first and second processing exposures must use the same duration; "
                "set mix_boundary_process_time and mix_internal_process_time to the same value."
            )
        if min(
            self.big_m,
            self.pm_transfer_gap,
            self.pm_rotation_time_180,
            self.pair_transfer_time,
            self.atr_transfer_time,
            self.atr_return_time,
            self.aligner_time,
            self.llupper_time,
            self.lllower_time,
            self.full_process_time,
            self.mix_boundary_process_time,
            self.mix_internal_process_time,
            self.effective_cleaning_process_time,
            self.max_module_residency_time,
            self.max_robot_residency_time,
            self.max_schedule_wait_time,
            self.pm_balance_penalty,
            self.chamber_idle_penalty,
            self.post_process_wait_penalty,
            self.ll_wait_penalty,
            self.chamber_nonprocess_wait_square_penalty,
        ) < 0:
            raise ValueError("All duration parameters must be non-negative.")
        full_capacity = 2 * self.num_pm * self.num_full_slots_per_pm
        if self.num_full_pairs > full_capacity:
            raise ValueError(
                "num_batches is too small for the requested number of 4x1 product pairs. "
                f"Need capacity {self.num_full_pairs} but current upper bound is {full_capacity}."
            )


def _maybe_one(value):
    return 1 if value is None else value


def _add_duration_cons(model, start_var, end_var, duration: float, name_prefix: str, active_var=None) -> None:
    if active_var is None:
        model.addCons(end_var == start_var + duration, name=f"{name_prefix}_duration")
        return
    model.addCons(start_var <= 1000000.0 * active_var, name=f"{name_prefix}_start_cap")
    model.addCons(end_var <= 1000000.0 * active_var, name=f"{name_prefix}_end_cap")
    model.addCons(end_var == start_var + duration * active_var, name=f"{name_prefix}_duration")


def _add_min_duration_cons(model, start_var, end_var, duration: float, name_prefix: str, active_var=None) -> None:
    if active_var is None:
        model.addCons(end_var >= start_var + duration, name=f"{name_prefix}_min_duration")
        return
    model.addCons(start_var <= 1000000.0 * active_var, name=f"{name_prefix}_start_cap")
    model.addCons(end_var <= 1000000.0 * active_var, name=f"{name_prefix}_end_cap")
    model.addCons(end_var >= start_var + duration * active_var, name=f"{name_prefix}_min_duration")


def _add_residency_upper_bound(model, start_var, end_var, max_duration: float, name: str, active_var=None) -> None:
    if active_var is None:
        model.addCons(end_var <= start_var + max_duration, name=name)
        return
    model.addCons(end_var <= start_var + max_duration * active_var, name=name)


def _add_optional_gap_slack(model, slack_terms, later_start, earlier_end, active_var, big_m: float, name: str):
    slack = model.addVar(vtype="C", lb=0.0, name=name)
    model.addCons(
        slack >= later_start - earlier_end - big_m * (1 - active_var),
        name=f"{name}_lb",
    )
    model.addCons(slack <= big_m * active_var, name=f"{name}_cap")
    slack_terms.append(slack)
    return slack


def _link_optional_stage(model, start_var, end_var, ref_start, ref_end, active_var, big_m: float, name_prefix: str) -> None:
    model.addCons(start_var <= big_m * active_var, name=f"{name_prefix}_start_cap")
    model.addCons(end_var <= big_m * active_var, name=f"{name_prefix}_end_cap")
    model.addCons(start_var >= ref_start - big_m * (1 - active_var), name=f"{name_prefix}_start_lb")
    model.addCons(start_var <= ref_start + big_m * (1 - active_var), name=f"{name_prefix}_start_ub")
    model.addCons(end_var >= ref_end - big_m * (1 - active_var), name=f"{name_prefix}_end_lb")
    model.addCons(end_var <= ref_end + big_m * (1 - active_var), name=f"{name_prefix}_end_ub")


def _link_stage_by_binary(model, start_var, end_var, ref_start, ref_end, selector_var, big_m: float, name_prefix: str) -> None:
    model.addCons(start_var >= ref_start - big_m * (1 - selector_var), name=f"{name_prefix}_start_lb")
    model.addCons(start_var <= ref_start + big_m * (1 - selector_var), name=f"{name_prefix}_start_ub")
    model.addCons(end_var >= ref_end - big_m * (1 - selector_var), name=f"{name_prefix}_end_lb")
    model.addCons(end_var <= ref_end + big_m * (1 - selector_var), name=f"{name_prefix}_end_ub")


def _synchronize_stages_when(
    model,
    first_start,
    first_end,
    second_start,
    second_end,
    enabled_var,
    big_m: float,
    name_prefix: str,
) -> None:
    """Make two physical transfers simultaneous only when a double action is selected."""
    model.addCons(first_start >= second_start - big_m * (1 - enabled_var), name=f"{name_prefix}_start_lb")
    model.addCons(first_start <= second_start + big_m * (1 - enabled_var), name=f"{name_prefix}_start_ub")
    model.addCons(first_end >= second_end - big_m * (1 - enabled_var), name=f"{name_prefix}_end_lb")
    model.addCons(first_end <= second_end + big_m * (1 - enabled_var), name=f"{name_prefix}_end_ub")


def _contain_stage_by_binary(model, start_var, end_var, window_start, window_end, selector_var, big_m: float, name_prefix: str) -> None:
    """Keep an individual wafer transfer inside its assigned pair-transfer window."""
    model.addCons(start_var >= window_start - big_m * (1 - selector_var), name=f"{name_prefix}_start_lb")
    model.addCons(end_var <= window_end + big_m * (1 - selector_var), name=f"{name_prefix}_end_ub")


def _add_precedence_lower_bound(
    model,
    next_start,
    prev_end,
    big_m: float,
    name: str,
    active_var=None,
    offset: float = 0.0,
) -> None:
    if active_var is None:
        model.addCons(next_start >= prev_end + offset, name=name)
        return
    model.addCons(
        next_start >= prev_end + offset - big_m * (1 - active_var),
        name=name,
    )


def _add_unary_resource_no_overlap(model, task_specs, big_m: float, prefix: str, transition_time=None) -> None:
    for left_idx in range(len(task_specs)):
        left_name, left_start, left_end, left_active = task_specs[left_idx]
        for right_idx in range(left_idx + 1, len(task_specs)):
            right_name, right_start, right_end, right_active = task_specs[right_idx]
            before = model.addVar(vtype="B", name=f"{prefix}_{left_name}_{right_name}")
            inactive_penalty = (1 - _maybe_one(left_active)) + (1 - _maybe_one(right_active))
            left_to_right = transition_time(left_name, right_name) if transition_time else 0.0
            right_to_left = transition_time(right_name, left_name) if transition_time else 0.0
            model.addCons(
                right_start >= left_end + left_to_right - big_m * (1 - before + inactive_penalty),
                name=f"{prefix}_lb_{left_name}_{right_name}",
            )
            model.addCons(
                left_start >= right_end + right_to_left - big_m * (before + inactive_penalty),
                name=f"{prefix}_ub_{left_name}_{right_name}",
            )


def _add_parallel_slot_resource(model, task_specs, slot_count: int, big_m: float, slot_prefix: str, order_prefix: str):
    """Assign tasks to physical slots; overlap is forbidden only within one slot."""
    slot_assign = {}
    normalized_specs = []
    for spec in task_specs:
        if len(spec) == 4:
            task_name, task_start, task_end, active_var = spec
            allowed_slots = list(range(1, slot_count + 1))
            demand = 1
        elif len(spec) == 5:
            task_name, task_start, task_end, active_var, allowed_slots = spec
            allowed_slots = list(allowed_slots)
            demand = 1
        elif len(spec) == 6:
            task_name, task_start, task_end, active_var, allowed_slots, demand = spec
            allowed_slots = list(allowed_slots)
        else:
            raise ValueError("task_specs entries must have 4, 5, or 6 items.")
        if not allowed_slots:
            raise ValueError(f"Task `{task_name}` has no allowed slots.")
        if demand <= 0 or demand > len(allowed_slots):
            raise ValueError(
                f"Task `{task_name}` has invalid slot demand {demand}; "
                f"allowed slot count is {len(allowed_slots)}."
            )
        normalized_specs.append((task_name, task_start, task_end, active_var, allowed_slots, demand))

    for task_name, _, _, active_var, allowed_slots, demand in normalized_specs:
        for slot_id in allowed_slots:
            slot_assign[(task_name, slot_id)] = model.addVar(
                vtype="B",
                name=f"{slot_prefix}_{task_name}_{slot_id}",
            )
        rhs = _maybe_one(active_var)
        model.addCons(
            scip.quicksum(slot_assign[(task_name, slot_id)] for slot_id in allowed_slots) == demand * rhs,
            name=f"{slot_prefix}_select_{task_name}",
        )

    for slot_id in range(1, slot_count + 1):
        for left_idx in range(len(normalized_specs)):
            left_name, left_start, left_end, _, _, _ = normalized_specs[left_idx]
            if (left_name, slot_id) not in slot_assign:
                continue
            for right_idx in range(left_idx + 1, len(normalized_specs)):
                right_name, right_start, right_end, _, _, _ = normalized_specs[right_idx]
                if (right_name, slot_id) not in slot_assign:
                    continue
                before = model.addVar(
                    vtype="B",
                    name=f"{order_prefix}_{left_name}_{right_name}_{slot_id}",
                )
                model.addCons(
                    right_start
                    >= left_end
                    - big_m * (1 - before)
                    - big_m * (1 - slot_assign[(left_name, slot_id)])
                    - big_m * (1 - slot_assign[(right_name, slot_id)]),
                    name=f"{order_prefix}_lb_{left_name}_{right_name}_{slot_id}",
                )
                model.addCons(
                    left_start
                    >= right_end
                    - big_m * before
                    - big_m * (1 - slot_assign[(left_name, slot_id)])
                    - big_m * (1 - slot_assign[(right_name, slot_id)]),
                    name=f"{order_prefix}_ub_{left_name}_{right_name}_{slot_id}",
                )
    return slot_assign


def _canonical_cleaning_layout(cfg: PetriMIPConfig):
    """Build the symmetry-broken CH epoch and 2x2 segment layout.

    A 2x2 segment with ``k`` product pairs needs ``k + 1`` process
    cycles: PEC+P1 at its head, adjacent product pairs internally, and Pk+PEC
    at its tail. An epoch boundary therefore closes the current segment with
    PEC and starts a fresh PEC-headed segment after cleaning.
    """
    full_slots = [
        (m, b, side)
        for b in range(1, cfg.num_full_batches_per_pm + 1)
        for m in cfg.pm_ids
        for side in (1, 2)
    ]
    active_full_batches = {m: set() for m in cfg.pm_ids}
    for _, (m, b, _) in zip(cfg.full_pair_ids, full_slots):
        active_full_batches[m].add(b)

    mix_counts = {m: 0 for m in cfg.pm_ids}
    for pair_index, _ in enumerate(cfg.mix_pair_ids):
        mix_counts[cfg.pm_ids[pair_index % len(cfg.pm_ids)]] += 1

    layouts = {}
    for m in cfg.pm_ids:
        epoch = 1
        used = 0
        full_epoch = {}
        batches = sorted(active_full_batches[m])
        for batch in batches:
            if cfg.cleaning_interval > 0 and used == cfg.cleaning_interval:
                epoch += 1
                used = 0
            full_epoch[batch] = epoch
            used += 1

        segments = []
        next_position = 1
        next_cycle = 1
        remaining = mix_counts[m]
        while remaining > 0:
            if cfg.cleaning_interval <= 0:
                segment_pairs = remaining
            else:
                room = cfg.cleaning_interval - used
                # A nonempty segment needs both a PEC head and a PEC tail
                # cycle. With fewer than two slots left, clean before 2x2.
                if room < 2:
                    epoch += 1
                    used = 0
                    room = cfg.cleaning_interval
                segment_pairs = min(remaining, room - 1)

            positions = list(range(next_position, next_position + segment_pairs))
            cycles = list(range(next_cycle, next_cycle + segment_pairs + 1))
            segments.append(
                {
                    "id": len(segments) + 1,
                    "epoch": epoch,
                    "positions": positions,
                    "cycles": cycles,
                }
            )
            next_position += segment_pairs
            next_cycle += segment_pairs + 1
            remaining -= segment_pairs
            used += segment_pairs + 1
            if remaining > 0:
                epoch += 1
                used = 0

        layouts[m] = {
            "full_epoch": full_epoch,
            "segments": segments,
            "mix_count": mix_counts[m],
            "mix_cycle_count": next_cycle - 1,
            "last_epoch": epoch if (batches or segments) else 0,
        }
    return layouts


def build_petri_mip_model(cfg: PetriMIPConfig):
    cfg.validate()
    model = scip.Model("dual_source_rotary_cluster_full_flow")
    big_m = cfg.big_m

    pm_ids = cfg.pm_ids
    cleaning_layout = _canonical_cleaning_layout(cfg)
    full_batches = list(range(1, cfg.num_full_batches_per_pm + 1))
    full_sides = [1, 2]
    mix_positions = list(range(1, cfg.num_mix_positions_per_pm + 1))
    max_mix_cycles = max(1, *(layout["mix_cycle_count"] for layout in cleaning_layout.values()))
    mix_cycles = list(range(1, max_mix_cycles + 1))
    max_clean_slots = max(
        0,
        *(max(0, layout["last_epoch"] - 1) for layout in cleaning_layout.values()),
    )
    clean_slots = list(range(1, max_clean_slots + 1))
    chamber_epochs = list(range(1, len(clean_slots) + 2)) if clean_slots else []
    mix_segments = {
        (m, segment["id"]): segment
        for m in pm_ids
        for segment in cleaning_layout[m]["segments"]
    }
    mix_position_segment = {
        (m, position): segment["id"]
        for (m, _), segment in mix_segments.items()
        for position in segment["positions"]
    }
    mix_position_first_cycle = {
        (m, position): segment["cycles"][0] + local_index
        for (m, _), segment in mix_segments.items()
        for local_index, position in enumerate(segment["positions"])
    }
    mix_cycle_segment = {
        (m, cycle): segment["id"]
        for (m, _), segment in mix_segments.items()
        for cycle in segment["cycles"]
    }
    mix_segment_first_position = {
        (m, segment_id): segment["positions"][0]
        for (m, segment_id), segment in mix_segments.items()
    }
    mix_segment_last_position = {
        (m, segment_id): segment["positions"][-1]
        for (m, segment_id), segment in mix_segments.items()
    }
    mix_segment_first_cycle = {
        (m, segment_id): segment["cycles"][0]
        for (m, segment_id), segment in mix_segments.items()
    }
    mix_segment_last_cycle = {
        (m, segment_id): segment["cycles"][-1]
        for (m, segment_id), segment in mix_segments.items()
    }
    mix_bridge_active = {
        (m, cycle): int(
            (m, cycle) in mix_cycle_segment
            and cycle != mix_segment_first_cycle[(m, mix_cycle_segment[(m, cycle)])]
        )
        for m in pm_ids
        for cycle in mix_cycles[1:]
    }
    pec_tokens_per_pm = cfg.pec_pool_size // len(pm_ids)
    pec_slots_by_pm = {
        pm_id: list(range(idx * pec_tokens_per_pm + 1, (idx + 1) * pec_tokens_per_pm + 1))
        for idx, pm_id in enumerate(pm_ids)
    }

    product_wafers = cfg.product_wafer_ids
    full_wafers = cfg.full_wafer_ids
    mix_wafers = cfg.mix_wafer_ids
    full_pair_ids = cfg.full_pair_ids
    mix_pair_ids = cfg.mix_pair_ids
    full_pair_loads = cfg.full_pair_product_loads
    mix_pair_loads = cfg.mix_pair_product_loads
    pure_full_mode = bool(product_wafers) and set(cfg.product_wafer_modes) == {MODE_FULL}
    chamber_idle_slacks = []

    wafer_to_full_pair = {
        (w, p): model.addVar(vtype="B", name=f"wafer_to_full_pair_{w}_{p}")
        for w in full_wafers
        for p in full_pair_ids
    }
    wafer_to_mix_pair = {
        (w, p): model.addVar(vtype="B", name=f"wafer_to_mix_pair_{w}_{p}")
        for w in mix_wafers
        for p in mix_pair_ids
    }

    assign_full = {
        (p, m, b, s): model.addVar(vtype="B", name=f"assign_full_{p}_{m}_{b}_{s}")
        for p in full_pair_ids
        for m in pm_ids
        for b in full_batches
        for s in full_sides
    }
    assign_mix = {
        (p, m, r): model.addVar(vtype="B", name=f"assign_mix_{p}_{m}_{r}")
        for p in mix_pair_ids
        for m in pm_ids
        for r in mix_positions
    }

    # A two-product full-mode PW pair may use one double-gripper action or
    # two single-gripper actions at each robot route. Tail pairs containing
    # only one product wafer are fixed to single-gripper operation below.
    full_atr_lp_al_double = {
        p: model.addVar(vtype="B", name=f"full_atr_lp_al_double_{p}")
        for p in full_pair_ids
    }
    full_atr_al_llupper_double = {
        p: model.addVar(vtype="B", name=f"full_atr_al_llupper_double_{p}")
        for p in full_pair_ids
    }
    full_atr_return_double = {
        p: model.addVar(vtype="B", name=f"full_atr_return_double_{p}")
        for p in full_pair_ids
    }
    full_vtr_load_double = {
        p: model.addVar(vtype="B", name=f"full_vtr_load_double_{p}")
        for p in full_pair_ids
    }
    full_vtr_unload_double = {
        p: model.addVar(vtype="B", name=f"full_vtr_unload_double_{p}")
        for p in full_pair_ids
    }
    mix_atr_lp_al_double = {
        p: model.addVar(vtype="B", name=f"mix_atr_lp_al_double_{p}")
        for p in mix_pair_ids
    }
    mix_atr_al_llupper_double = {
        p: model.addVar(vtype="B", name=f"mix_atr_al_llupper_double_{p}")
        for p in mix_pair_ids
    }
    mix_atr_return_double = {
        p: model.addVar(vtype="B", name=f"mix_atr_return_double_{p}")
        for p in mix_pair_ids
    }
    mix_vtr_load_double = {
        p: model.addVar(vtype="B", name=f"mix_vtr_load_double_{p}")
        for p in mix_pair_ids
    }
    mix_vtr_unload_double = {
        p: model.addVar(vtype="B", name=f"mix_vtr_unload_double_{p}")
        for p in mix_pair_ids
    }

    full_batch_used = {
        (m, b): model.addVar(vtype="B", name=f"full_batch_used_{m}_{b}")
        for m in pm_ids
        for b in full_batches
    }
    full_filler_side = {
        (m, b, s): model.addVar(vtype="B", name=f"full_filler_side_{m}_{b}_{s}")
        for m in pm_ids
        for b in full_batches
        for s in full_sides
    }
    full_batch_tail = {
        (m, b): model.addVar(vtype="B", name=f"full_batch_tail_{m}_{b}")
        for m in pm_ids
        for b in full_batches
    }

    mix_pos_used = {
        (m, r): model.addVar(vtype="B", name=f"mix_pos_used_{m}_{r}")
        for m in pm_ids
        for r in mix_positions
    }
    mix_cycle_used = {
        (m, c): model.addVar(vtype="B", name=f"mix_cycle_used_{m}_{c}")
        for m in pm_ids
        for c in mix_cycles
    }
    mix_active = {
        m: model.addVar(vtype="B", name=f"mix_active_{m}")
        for m in pm_ids
    }
    mix_last_cycle = {
        (m, c): model.addVar(vtype="B", name=f"mix_last_cycle_{m}_{c}")
        for m in pm_ids
        for c in mix_cycles
    }
    mix_last_pos = {
        (m, r): model.addVar(vtype="B", name=f"mix_last_pos_{m}_{r}")
        for m in pm_ids
        for r in mix_positions
    }

    full_front_load_start = {
        (m, b): model.addVar(vtype="C", lb=0.0, name=f"full_front_load_start_{m}_{b}")
        for m in pm_ids
        for b in full_batches
    }
    full_front_load_end = {
        (m, b): model.addVar(vtype="C", lb=0.0, name=f"full_front_load_end_{m}_{b}")
        for m in pm_ids
        for b in full_batches
    }
    full_back_load_start = {
        (m, b): model.addVar(vtype="C", lb=0.0, name=f"full_back_load_start_{m}_{b}")
        for m in pm_ids
        for b in full_batches
    }
    full_back_load_end = {
        (m, b): model.addVar(vtype="C", lb=0.0, name=f"full_back_load_end_{m}_{b}")
        for m in pm_ids
        for b in full_batches
    }
    full_start = {
        (m, b): model.addVar(vtype="C", lb=0.0, name=f"full_start_{m}_{b}")
        for m in pm_ids
        for b in full_batches
    }
    full_end = {
        (m, b): model.addVar(vtype="C", lb=0.0, name=f"full_end_{m}_{b}")
        for m in pm_ids
        for b in full_batches
    }
    full_back_unload_start = {
        (m, b): model.addVar(vtype="C", lb=0.0, name=f"full_back_unload_start_{m}_{b}")
        for m in pm_ids
        for b in full_batches
    }
    full_back_unload_end = {
        (m, b): model.addVar(vtype="C", lb=0.0, name=f"full_back_unload_end_{m}_{b}")
        for m in pm_ids
        for b in full_batches
    }
    full_front_unload_start = {
        (m, b): model.addVar(vtype="C", lb=0.0, name=f"full_front_unload_start_{m}_{b}")
        for m in pm_ids
        for b in full_batches
    }
    full_front_unload_end = {
        (m, b): model.addVar(vtype="C", lb=0.0, name=f"full_front_unload_end_{m}_{b}")
        for m in pm_ids
        for b in full_batches
    }
    full_side_load_start = {
        (m, b, 1): full_front_load_start[(m, b)]
        for m in pm_ids
        for b in full_batches
    }
    full_side_load_start.update(
        {
            (m, b, 2): full_back_load_start[(m, b)]
            for m in pm_ids
            for b in full_batches
        }
    )
    full_side_load_end = {
        (m, b, 1): full_front_load_end[(m, b)]
        for m in pm_ids
        for b in full_batches
    }
    full_side_load_end.update(
        {
            (m, b, 2): full_back_load_end[(m, b)]
            for m in pm_ids
            for b in full_batches
        }
    )
    full_side_unload_start = {
        (m, b, 1): full_front_unload_start[(m, b)]
        for m in pm_ids
        for b in full_batches
    }
    full_side_unload_start.update(
        {
            (m, b, 2): full_back_unload_start[(m, b)]
            for m in pm_ids
            for b in full_batches
        }
    )
    full_side_unload_end = {
        (m, b, 1): full_front_unload_end[(m, b)]
        for m in pm_ids
        for b in full_batches
    }
    full_side_unload_end.update(
        {
            (m, b, 2): full_back_unload_end[(m, b)]
            for m in pm_ids
            for b in full_batches
        }
    )

    mix_head_start = {
        (m, segment_id): model.addVar(vtype="C", lb=0.0, name=f"mix_head_start_{m}_{segment_id}")
        for m, segment_id in mix_segments
    }
    mix_head_end = {
        (m, segment_id): model.addVar(vtype="C", lb=0.0, name=f"mix_head_end_{m}_{segment_id}")
        for m, segment_id in mix_segments
    }
    mix_cycle_start = {
        (m, c): model.addVar(vtype="C", lb=0.0, name=f"mix_cycle_start_{m}_{c}")
        for m in pm_ids
        for c in mix_cycles
    }
    mix_cycle_end = {
        (m, c): model.addVar(vtype="C", lb=0.0, name=f"mix_cycle_end_{m}_{c}")
        for m in pm_ids
        for c in mix_cycles
    }
    mix_bridge_start = {
        (m, c): model.addVar(vtype="C", lb=0.0, name=f"mix_bridge_start_{m}_{c}")
        for m in pm_ids
        for c in mix_cycles[1:]
    }
    mix_bridge_end = {
        (m, c): model.addVar(vtype="C", lb=0.0, name=f"mix_bridge_end_{m}_{c}")
        for m in pm_ids
        for c in mix_cycles[1:]
    }
    mix_tail_load_start = {
        (m, segment_id): model.addVar(vtype="C", lb=0.0, name=f"mix_tail_load_start_{m}_{segment_id}")
        for m, segment_id in mix_segments
    }
    mix_tail_load_end = {
        (m, segment_id): model.addVar(vtype="C", lb=0.0, name=f"mix_tail_load_end_{m}_{segment_id}")
        for m, segment_id in mix_segments
    }
    mix_last_cycle_start = {
        (m, segment_id): model.addVar(vtype="C", lb=0.0, name=f"mix_last_cycle_start_{m}_{segment_id}")
        for m, segment_id in mix_segments
    }
    mix_last_cycle_end = {
        (m, segment_id): model.addVar(vtype="C", lb=0.0, name=f"mix_last_cycle_end_{m}_{segment_id}")
        for m, segment_id in mix_segments
    }
    mix_tail_start = {
        (m, segment_id): model.addVar(vtype="C", lb=0.0, name=f"mix_tail_start_{m}_{segment_id}")
        for m, segment_id in mix_segments
    }
    mix_tail_end = {
        (m, segment_id): model.addVar(vtype="C", lb=0.0, name=f"mix_tail_end_{m}_{segment_id}")
        for m, segment_id in mix_segments
    }

    clean_active = {
        (m, j): model.addVar(vtype="B", name=f"clean_active_{m}_{j}")
        for m in pm_ids
        for j in clean_slots
    }
    clean_front_load_start = {
        (m, j): model.addVar(vtype="C", lb=0.0, name=f"clean_front_load_start_{m}_{j}")
        for m in pm_ids
        for j in clean_slots
    }
    clean_front_load_end = {
        (m, j): model.addVar(vtype="C", lb=0.0, name=f"clean_front_load_end_{m}_{j}")
        for m in pm_ids
        for j in clean_slots
    }
    clean_back_load_start = {
        (m, j): model.addVar(vtype="C", lb=0.0, name=f"clean_back_load_start_{m}_{j}")
        for m in pm_ids
        for j in clean_slots
    }
    clean_back_load_end = {
        (m, j): model.addVar(vtype="C", lb=0.0, name=f"clean_back_load_end_{m}_{j}")
        for m in pm_ids
        for j in clean_slots
    }
    clean_start = {
        (m, j): model.addVar(vtype="C", lb=0.0, name=f"clean_start_{m}_{j}")
        for m in pm_ids
        for j in clean_slots
    }
    clean_end = {
        (m, j): model.addVar(vtype="C", lb=0.0, name=f"clean_end_{m}_{j}")
        for m in pm_ids
        for j in clean_slots
    }
    clean_back_unload_start = {
        (m, j): model.addVar(vtype="C", lb=0.0, name=f"clean_back_unload_start_{m}_{j}")
        for m in pm_ids
        for j in clean_slots
    }
    clean_back_unload_end = {
        (m, j): model.addVar(vtype="C", lb=0.0, name=f"clean_back_unload_end_{m}_{j}")
        for m in pm_ids
        for j in clean_slots
    }
    clean_front_unload_start = {
        (m, j): model.addVar(vtype="C", lb=0.0, name=f"clean_front_unload_start_{m}_{j}")
        for m in pm_ids
        for j in clean_slots
    }
    clean_front_unload_end = {
        (m, j): model.addVar(vtype="C", lb=0.0, name=f"clean_front_unload_end_{m}_{j}")
        for m in pm_ids
        for j in clean_slots
    }

    full_pair_vtr_load_start = {
        p: model.addVar(vtype="C", lb=0.0, name=f"full_pair_vtr_load_start_{p}")
        for p in full_pair_ids
    }
    full_pair_vtr_load_end = {
        p: model.addVar(vtype="C", lb=0.0, name=f"full_pair_vtr_load_end_{p}")
        for p in full_pair_ids
    }
    full_pair_pm_start = {
        p: model.addVar(vtype="C", lb=0.0, name=f"full_pair_pm_start_{p}")
        for p in full_pair_ids
    }
    full_pair_pm_end = {
        p: model.addVar(vtype="C", lb=0.0, name=f"full_pair_pm_end_{p}")
        for p in full_pair_ids
    }
    full_pair_vtr_unload_start = {
        p: model.addVar(vtype="C", lb=0.0, name=f"full_pair_vtr_unload_start_{p}")
        for p in full_pair_ids
    }
    full_pair_vtr_unload_end = {
        p: model.addVar(vtype="C", lb=0.0, name=f"full_pair_vtr_unload_end_{p}")
        for p in full_pair_ids
    }

    mix_pair_vtr_load_start = {
        p: model.addVar(vtype="C", lb=0.0, name=f"mix_pair_vtr_load_start_{p}")
        for p in mix_pair_ids
    }
    mix_pair_vtr_load_end = {
        p: model.addVar(vtype="C", lb=0.0, name=f"mix_pair_vtr_load_end_{p}")
        for p in mix_pair_ids
    }
    mix_pair_pm_start = {
        p: model.addVar(vtype="C", lb=0.0, name=f"mix_pair_pm_start_{p}")
        for p in mix_pair_ids
    }
    mix_pair_pm_end = {
        p: model.addVar(vtype="C", lb=0.0, name=f"mix_pair_pm_end_{p}")
        for p in mix_pair_ids
    }
    mix_pair_vtr_unload_start = {
        p: model.addVar(vtype="C", lb=0.0, name=f"mix_pair_vtr_unload_start_{p}")
        for p in mix_pair_ids
    }
    mix_pair_vtr_unload_end = {
        p: model.addVar(vtype="C", lb=0.0, name=f"mix_pair_vtr_unload_end_{p}")
        for p in mix_pair_ids
    }

    full_pair_completion = {
        p: model.addVar(vtype="C", lb=0.0, name=f"full_pair_completion_{p}")
        for p in full_pair_ids
    }
    full_pair_post_process_wait = {
        p: model.addVar(vtype="C", lb=0.0, name=f"full_pair_post_process_wait_{p}")
        for p in full_pair_ids
    }
    # These are release-time envelopes, not synchronization variables. They
    # record when the two LL slots occupied by one side of a 4x1 batch have
    # both been released; member wafers may use the LLs and robots at distinct
    # times, while only their PM processing remains synchronized.
    full_side_llupper_release = {
        (m, b, side): model.addVar(
            vtype="C",
            lb=0.0,
            name=f"full_side_llupper_release_{m}_{b}_{side}",
        )
        for m in pm_ids
        for b in full_batches
        for side in (1, 2)
    }
    full_side_lllower_release = {
        (m, b, side): model.addVar(
            vtype="C",
            lb=0.0,
            name=f"full_side_lllower_release_{m}_{b}_{side}",
        )
        for m in pm_ids
        for b in full_batches
        for side in (1, 2)
    }
    mix_pair_completion = {
        p: model.addVar(vtype="C", lb=0.0, name=f"mix_pair_completion_{p}")
        for p in mix_pair_ids
    }
    mix_pair_post_process_wait = {
        p: model.addVar(vtype="C", lb=0.0, name=f"mix_pair_post_process_wait_{p}")
        for p in mix_pair_ids
    }
    chamber_idle_total = {
        m: model.addVar(vtype="C", lb=0.0, name=f"chamber_idle_total_{m}")
        for m in pm_ids
    }
    chamber_nonprocess_wait_square = {
        m: model.addVar(vtype="C", lb=0.0, name=f"chamber_nonprocess_wait_square_{m}")
        for m in pm_ids
    }
    chamber_nonprocess_wait_square_terms = {m: [] for m in pm_ids}
    chamber_nonprocess_wait_terms = []

    def add_chamber_nonprocess_square_term(m, wait_expr, active_var, name: str) -> None:
        wait = model.addVar(vtype="C", lb=0.0, name=f"chamber_nonprocess_wait_{name}")
        square = model.addVar(vtype="C", lb=0.0, name=f"chamber_nonprocess_wait_square_{name}")
        model.addCons(
            wait >= wait_expr - big_m * (1 - active_var),
            name=f"chamber_nonprocess_wait_lb_{name}",
        )
        model.addCons(
            wait <= wait_expr + big_m * (1 - active_var),
            name=f"chamber_nonprocess_wait_ub_{name}",
        )
        model.addCons(
            wait <= big_m * active_var,
            name=f"chamber_nonprocess_wait_active_{name}",
        )
        model.addCons(
            square >= wait * wait,
            name=f"chamber_nonprocess_wait_square_def_{name}",
        )
        chamber_nonprocess_wait_terms.append(wait)
        chamber_nonprocess_wait_square_terms[m].append(square)

    # Wafers of the same process mode have identical model data. Pairing them
    # in wafer-id order removes label symmetry without changing any physical
    # schedule; the final pair receives the lone tail wafer when needed.
    full_pair_members = {}
    member_offset = 0
    for p in full_pair_ids:
        load = full_pair_loads[p]
        full_pair_members[p] = set(full_wafers[member_offset : member_offset + load])
        member_offset += load
    for p in full_pair_ids:
        for w in full_wafers:
            model.addCons(
                wafer_to_full_pair[(w, p)] == int(w in full_pair_members[p]),
                name=f"full_pair_membership_fixed_{w}_{p}",
            )
        double_allowed = int(full_pair_loads[p] == 2)
        for route_name, double_var in (
            ("atr_lp_al", full_atr_lp_al_double[p]),
            ("atr_al_llupper", full_atr_al_llupper_double[p]),
            ("atr_return", full_atr_return_double[p]),
            ("vtr_load", full_vtr_load_double[p]),
            ("vtr_unload", full_vtr_unload_double[p]),
        ):
            model.addCons(
                double_var <= double_allowed,
                name=f"full_{route_name}_double_allowed_{p}",
            )
        if cfg.force_full_vtr_double and double_allowed:
            # A VTR transfer of a two-product PW pair is one physical
            # pickup/place action, not two serial single-wafer transfers.
            model.addCons(
                full_vtr_load_double[p] == 1,
                name=f"full_vtr_load_double_required_{p}",
            )
            model.addCons(
                full_vtr_unload_double[p] == 1,
                name=f"full_vtr_unload_double_required_{p}",
            )
        if cfg.force_full_atr_double and double_allowed:
            model.addCons(
                full_atr_lp_al_double[p] == 1,
                name=f"full_atr_lp_al_double_required_{p}",
            )
            model.addCons(
                full_atr_al_llupper_double[p] == 1,
                name=f"full_atr_al_llupper_double_required_{p}",
            )
            model.addCons(
                full_atr_return_double[p] == 1,
                name=f"full_atr_return_double_required_{p}",
            )
        # AL is single-slot, but ATR's two-gripper capability is available in
        # both pure 4x1 and mixed 4x1+2x2 schedules. A complete two-wafer pair
        # uses a shared LP->AL pickup and shared AL->LLupper placement;
        # a shared output move requires the shared input move. No process-mode
        # condition is allowed to force these two decision variables to zero.
        model.addCons(
            full_atr_al_llupper_double[p] <= full_atr_lp_al_double[p],
            name=f"full_atr_al_bundle_double_precondition_{p}",
        )

    full_pair_by_wafer = {
        w: p
        for p, members in full_pair_members.items()
        for w in members
    }
    full_pair_first_member = {
        p: min(members)
        for p, members in full_pair_members.items()
    }
    full_pair_second_member = {
        p: max(members)
        for p, members in full_pair_members.items()
        if len(members) == 2
    }
    full_pair_first_by_wafer = {
        w: p for p, w in full_pair_first_member.items()
    }
    full_pair_second_by_wafer = {
        w: p for p, w in full_pair_second_member.items()
    }

    mix_pair_members = {}
    member_offset = 0
    for p in mix_pair_ids:
        load = mix_pair_loads[p]
        mix_pair_members[p] = set(mix_wafers[member_offset : member_offset + load])
        member_offset += load
    for p in mix_pair_ids:
        for w in mix_wafers:
            model.addCons(
                wafer_to_mix_pair[(w, p)] == int(w in mix_pair_members[p]),
                name=f"mix_pair_membership_fixed_{w}_{p}",
            )
        double_allowed = int(mix_pair_loads[p] == 2)
        for route_name, double_var in (
            ("atr_lp_al", mix_atr_lp_al_double[p]),
            ("atr_al_llupper", mix_atr_al_llupper_double[p]),
            ("atr_return", mix_atr_return_double[p]),
            ("vtr_load", mix_vtr_load_double[p]),
            ("vtr_unload", mix_vtr_unload_double[p]),
        ):
            model.addCons(
                double_var <= double_allowed,
                name=f"mix_{route_name}_double_allowed_{p}",
            )
        model.addCons(
            mix_atr_al_llupper_double[p] <= mix_atr_lp_al_double[p],
            name=f"mix_atr_al_bundle_double_precondition_{p}",
        )
        if double_allowed and cfg.force_mix_atr_double:
            model.addCons(
                mix_atr_lp_al_double[p] == 1,
                name=f"mix_atr_lp_al_double_required_{p}",
            )
            model.addCons(
                mix_atr_al_llupper_double[p] == 1,
                name=f"mix_atr_al_llupper_double_required_{p}",
            )
            model.addCons(
                mix_atr_return_double[p] == 1,
                name=f"mix_atr_return_double_required_{p}",
            )
        if double_allowed and cfg.force_mix_vtr_double:
            model.addCons(
                mix_vtr_load_double[p] == 1,
                name=f"mix_vtr_load_double_required_{p}",
            )
            model.addCons(
                mix_vtr_unload_double[p] == 1,
                name=f"mix_vtr_unload_double_required_{p}",
            )

    product_pair_members = {}
    product_pair_atr_lp_al_double = {}
    product_pair_atr_al_llupper_double = {}
    product_pair_atr_return_double = {}
    product_pair_vtr_load_double = {}
    product_pair_vtr_unload_double = {}
    for p in full_pair_ids:
        key = (MODE_FULL, p)
        product_pair_members[key] = full_pair_members[p]
        product_pair_atr_lp_al_double[key] = full_atr_lp_al_double[p]
        product_pair_atr_al_llupper_double[key] = full_atr_al_llupper_double[p]
        product_pair_atr_return_double[key] = full_atr_return_double[p]
        product_pair_vtr_load_double[key] = full_vtr_load_double[p]
        product_pair_vtr_unload_double[key] = full_vtr_unload_double[p]
    for p in mix_pair_ids:
        key = (MODE_MIX, p)
        product_pair_members[key] = mix_pair_members[p]
        product_pair_atr_lp_al_double[key] = mix_atr_lp_al_double[p]
        product_pair_atr_al_llupper_double[key] = mix_atr_al_llupper_double[p]
        product_pair_atr_return_double[key] = mix_atr_return_double[p]
        product_pair_vtr_load_double[key] = mix_vtr_load_double[p]
        product_pair_vtr_unload_double[key] = mix_vtr_unload_double[p]
    product_pair_first_member = {
        key: min(members)
        for key, members in product_pair_members.items()
    }
    product_pair_second_member = {
        key: max(members)
        for key, members in product_pair_members.items()
        if len(members) == 2
    }
    product_pair_first_by_wafer = {
        w: key for key, w in product_pair_first_member.items()
    }
    product_pair_second_by_wafer = {
        w: key for key, w in product_pair_second_member.items()
    }

    # Full-mode PW pairs are also interchangeable. Fix a canonical ordering
    # over the otherwise identical chamber/batch/side slots so SCIP does not
    # enumerate factorially many relabelings of the same 4x1 schedule.
    canonical_full_slots = [
        (m, b, s)
        for b in full_batches
        for m in pm_ids
        for s in full_sides
    ]
    canonical_full_slot_by_pair = {
        p: canonical_full_slots[p_index]
        for p_index, p in enumerate(full_pair_ids)
    }
    for p_index, p in enumerate(full_pair_ids):
        canonical_slot = canonical_full_slot_by_pair[p]
        for m in pm_ids:
            for b in full_batches:
                for s in full_sides:
                    model.addCons(
                        assign_full[(p, m, b, s)] == int((m, b, s) == canonical_slot),
                        name=f"full_pair_slot_fixed_{p}_{m}_{b}_{s}",
                    )
    for p in mix_pair_ids:
        model.addCons(
            scip.quicksum(assign_mix[(p, m, r)] for m in pm_ids for r in mix_positions) == 1,
            name=f"mix_pair_schedule_once_{p}",
        )

    # 2x2 PW pairs have the same recipe and timing within one input instance;
    # their pair IDs are labels rather than decisions.  Leaving every pair
    # free to occupy every chain position creates a factorial number of
    # identical solutions, and the generic resource model then fails to find
    # even a first incumbent at the root node.  Assign the interchangeable
    # pairs to a canonical interleaved CH/position order.  This keeps both CHs
    # balanced (P1->CH2-pos1, P2->CH3-pos1, P3->CH2-pos2, ...) while retaining
    # all physically meaningful timing decisions.  The odd product+PEC pair,
    # if present, naturally becomes the final product position.
    canonical_mix_slots = [
        (m, r)
        for r in mix_positions
        for m in pm_ids
    ]
    canonical_mix_slot_by_pair = {
        p: canonical_mix_slots[p_index]
        for p_index, p in enumerate(mix_pair_ids)
    }
    for p in mix_pair_ids:
        canonical_pm, canonical_pos = canonical_mix_slot_by_pair[p]
        for m in pm_ids:
            for r in mix_positions:
                model.addCons(
                    assign_mix[(p, m, r)] == int((m, r) == (canonical_pm, canonical_pos)),
                    name=f"mix_pair_slot_fixed_{p}_{m}_{r}",
                )

    full_pm_imbalance = None
    mix_pm_imbalance = None
    if len(pm_ids) == 2:
        left_pm, right_pm = pm_ids
        full_product_load_by_pm = {
            m: scip.quicksum(
                full_pair_loads[p] * assign_full[(p, m, b, s)]
                for p in full_pair_ids
                for b in full_batches
                for s in full_sides
            )
            for m in pm_ids
        }
        mix_product_load_by_pm = {
            m: scip.quicksum(
                mix_pair_loads[p] * assign_mix[(p, m, r)]
                for p in mix_pair_ids
                for r in mix_positions
            )
            for m in pm_ids
        }
        full_pm_imbalance = model.addVar(vtype="C", lb=0.0, name="full_pm_imbalance")
        mix_pm_imbalance = model.addVar(vtype="C", lb=0.0, name="mix_pm_imbalance")
        model.addCons(
            full_pm_imbalance >= full_product_load_by_pm[left_pm] - full_product_load_by_pm[right_pm],
            name="full_pm_share_abs_lb",
        )
        model.addCons(
            full_pm_imbalance >= full_product_load_by_pm[right_pm] - full_product_load_by_pm[left_pm],
            name="full_pm_share_abs_ub",
        )
        model.addCons(
            mix_pm_imbalance >= mix_product_load_by_pm[left_pm] - mix_product_load_by_pm[right_pm],
            name="mix_pm_share_abs_lb",
        )
        model.addCons(
            mix_pm_imbalance >= mix_product_load_by_pm[right_pm] - mix_product_load_by_pm[left_pm],
            name="mix_pm_share_abs_ub",
        )

    for m in pm_ids:
        for b in full_batches:
            assigned_pairs = scip.quicksum(assign_full[(p, m, b, s)] for p in full_pair_ids for s in full_sides)
            model.addCons(
                assigned_pairs >= full_batch_used[(m, b)],
                name=f"full_batch_has_product_{m}_{b}",
            )
            model.addCons(
                scip.quicksum(full_filler_side[(m, b, s)] for s in full_sides)
                == 2 * full_batch_used[(m, b)] - assigned_pairs,
                name=f"full_filler_count_{m}_{b}",
            )
            for s in full_sides:
                side_load = scip.quicksum(assign_full[(p, m, b, s)] for p in full_pair_ids)
                model.addCons(
                    side_load + full_filler_side[(m, b, s)] == full_batch_used[(m, b)],
                    name=f"full_side_capacity_{m}_{b}_{s}",
                )
            if full_pair_ids:
                model.addCons(
                    scip.quicksum(p * assign_full[(p, m, b, 1)] for p in full_pair_ids)
                    <= scip.quicksum(p * assign_full[(p, m, b, 2)] for p in full_pair_ids)
                    + full_pair_ids[-1] * full_filler_side[(m, b, 2)],
                    name=f"full_side_order_{m}_{b}",
                )
            if b != full_batches[-1]:
                model.addCons(
                    assigned_pairs >= 2 * full_batch_used[(m, b + 1)],
                    name=f"full_filler_tail_only_{m}_{b}",
                )
        for b in full_batches[:-1]:
            model.addCons(
                full_batch_used[(m, b)] >= full_batch_used[(m, b + 1)],
                name=f"full_batch_prefix_{m}_{b}",
            )
            model.addCons(
                full_batch_tail[(m, b)] <= full_batch_used[(m, b)],
                name=f"full_batch_tail_used_ub_{m}_{b}",
            )
            model.addCons(
                full_batch_tail[(m, b)] <= 1 - full_batch_used[(m, b + 1)],
                name=f"full_batch_tail_next_ub_{m}_{b}",
            )
            model.addCons(
                full_batch_tail[(m, b)] >= full_batch_used[(m, b)] - full_batch_used[(m, b + 1)],
                name=f"full_batch_tail_exact_{m}_{b}",
            )
        model.addCons(
            full_batch_tail[(m, full_batches[-1])] == full_batch_used[(m, full_batches[-1])],
            name=f"full_batch_tail_last_{m}",
        )

        for r in mix_positions:
            assigned_mix = scip.quicksum(assign_mix[(p, m, r)] for p in mix_pair_ids)
            model.addCons(
                mix_pos_used[(m, r)] == assigned_mix,
                name=f"mix_pos_capacity_{m}_{r}",
            )
        for r in mix_positions[:-1]:
            model.addCons(
                mix_pos_used[(m, r)] >= mix_pos_used[(m, r + 1)],
                name=f"mix_pos_prefix_{m}_{r}",
            )
        model.addCons(
            mix_active[m] == mix_pos_used[(m, 1)],
            name=f"mix_active_first_pos_{m}",
        )

        last_position = mix_positions[-1]
        active_cycle_count = cleaning_layout[m]["mix_cycle_count"]
        for c in mix_cycles:
            model.addCons(
                mix_cycle_used[(m, c)] == (mix_active[m] if c <= active_cycle_count else 0),
                name=f"mix_cycle_layout_{m}_{c}",
            )
            model.addCons(
                mix_last_cycle[(m, c)]
                == (mix_active[m] if c == active_cycle_count and active_cycle_count else 0),
                name=f"mix_last_cycle_layout_{m}_{c}",
            )

        model.addCons(
            mix_active[m] == scip.quicksum(mix_last_pos[(m, r)] for r in mix_positions),
            name=f"mix_last_pos_unique_{m}",
        )
        for r in mix_positions[:-1]:
            model.addCons(
                mix_last_pos[(m, r)] <= mix_pos_used[(m, r)],
                name=f"mix_last_pos_active_{m}_{r}",
            )
            model.addCons(
                mix_last_pos[(m, r)] + mix_pos_used[(m, r + 1)] <= 1,
                name=f"mix_last_pos_tail_only_{m}_{r}",
            )
            model.addCons(
                mix_last_pos[(m, r)] >= mix_pos_used[(m, r)] - mix_pos_used[(m, r + 1)],
                name=f"mix_last_pos_exact_{m}_{r}",
            )
        model.addCons(
            mix_last_pos[(m, last_position)] == mix_pos_used[(m, last_position)],
            name=f"mix_last_pos_terminal_{m}",
        )

    full_batch_epoch = {}
    mix_block_epoch = {}
    mix_cycle_epoch = {}
    process_epoch_used = {}
    if clean_slots:
        for m in pm_ids:
            layout = cleaning_layout[m]
            epochs_with_mix = {segment["epoch"] for segment in layout["segments"]}
            for epoch in chamber_epochs:
                process_epoch_used[(m, epoch)] = model.addVar(
                    vtype="B",
                    name=f"process_epoch_used_{m}_{epoch}",
                )
                model.addCons(
                    process_epoch_used[(m, epoch)] == int(0 < epoch <= layout["last_epoch"]),
                    name=f"process_epoch_layout_{m}_{epoch}",
                )

            for b in full_batches:
                for epoch in chamber_epochs:
                    full_batch_epoch[(m, b, epoch)] = model.addVar(
                        vtype="B",
                        name=f"full_batch_epoch_{m}_{b}_{epoch}",
                    )
                    target_epoch = layout["full_epoch"].get(b)
                    model.addCons(
                        full_batch_epoch[(m, b, epoch)]
                        == (full_batch_used[(m, b)] if epoch == target_epoch else 0),
                        name=f"full_batch_epoch_layout_{m}_{b}_{epoch}",
                    )

            for epoch in chamber_epochs:
                mix_block_epoch[(m, epoch)] = model.addVar(
                    vtype="B",
                    name=f"mix_block_epoch_{m}_{epoch}",
                )
                model.addCons(
                    mix_block_epoch[(m, epoch)]
                    == (mix_active[m] if epoch in epochs_with_mix else 0),
                    name=f"mix_block_epoch_layout_{m}_{epoch}",
                )

            for c in mix_cycles:
                for epoch in chamber_epochs:
                    mix_cycle_epoch[(m, c, epoch)] = model.addVar(
                        vtype="B",
                        name=f"mix_cycle_epoch_{m}_{c}_{epoch}",
                    )
                    cycle_segment_id = mix_cycle_segment.get((m, c))
                    cycle_epoch = (
                        mix_segments[(m, cycle_segment_id)]["epoch"]
                        if cycle_segment_id is not None
                        else None
                    )
                    model.addCons(
                        mix_cycle_epoch[(m, c, epoch)]
                        == (mix_cycle_used[(m, c)] if epoch == cycle_epoch else 0),
                        name=f"mix_cycle_epoch_layout_{m}_{c}_{epoch}",
                    )

            for epoch in chamber_epochs:
                epoch_process_count = scip.quicksum(
                    full_batch_epoch[(m, b, epoch)] for b in full_batches
                ) + scip.quicksum(mix_cycle_epoch[(m, c, epoch)] for c in mix_cycles)
                model.addCons(
                    epoch_process_count <= cfg.cleaning_interval * process_epoch_used[(m, epoch)],
                    name=f"process_epoch_capacity_{m}_{epoch}",
                )
                model.addCons(
                    epoch_process_count >= process_epoch_used[(m, epoch)],
                    name=f"process_epoch_nonempty_{m}_{epoch}",
                )

            for clean_slot in clean_slots:
                model.addCons(
                    clean_active[(m, clean_slot)] == process_epoch_used[(m, clean_slot + 1)],
                    name=f"clean_active_from_next_epoch_{m}_{clean_slot}",
                )

    for m in pm_ids:
        for b in full_batches[:-1]:
            if clean_slots:
                for epoch in chamber_epochs:
                    same_epoch = model.addVar(
                        vtype="B",
                        name=f"full_adjacent_same_epoch_{m}_{b}_{epoch}",
                    )
                    model.addCons(
                        same_epoch <= full_batch_epoch[(m, b, epoch)],
                        name=f"full_adjacent_same_epoch_left_ub_{m}_{b}_{epoch}",
                    )
                    model.addCons(
                        same_epoch <= full_batch_epoch[(m, b + 1, epoch)],
                        name=f"full_adjacent_same_epoch_right_ub_{m}_{b}_{epoch}",
                    )
                    model.addCons(
                        same_epoch
                        >= full_batch_epoch[(m, b, epoch)] + full_batch_epoch[(m, b + 1, epoch)] - 1,
                        name=f"full_adjacent_same_epoch_exact_{m}_{b}_{epoch}",
                    )
                    _add_optional_gap_slack(
                        model,
                        chamber_idle_slacks,
                        full_front_load_start[(m, b + 1)],
                        full_front_unload_end[(m, b)],
                        same_epoch,
                        big_m,
                        f"full_batch_idle_{m}_{b}_{b + 1}_{epoch}",
                    )
            else:
                _add_optional_gap_slack(
                    model,
                    chamber_idle_slacks,
                    full_front_load_start[(m, b + 1)],
                    full_front_unload_end[(m, b)],
                    full_batch_used[(m, b + 1)],
                    big_m,
                    f"full_batch_idle_{m}_{b}_{b + 1}",
                )

        for b in full_batches:
            if not cleaning_layout[m]["segments"]:
                continue
            first_segment_id = cleaning_layout[m]["segments"][0]["id"]
            if clean_slots:
                for epoch in chamber_epochs:
                    same_epoch = model.addVar(
                        vtype="B",
                        name=f"full_tail_mix_same_epoch_{m}_{b}_{epoch}",
                    )
                    model.addCons(
                        same_epoch <= full_batch_tail[(m, b)],
                        name=f"full_tail_mix_same_epoch_tail_ub_{m}_{b}_{epoch}",
                    )
                    model.addCons(
                        same_epoch <= full_batch_epoch[(m, b, epoch)],
                        name=f"full_tail_mix_same_epoch_full_ub_{m}_{b}_{epoch}",
                    )
                    model.addCons(
                        same_epoch <= mix_block_epoch[(m, epoch)],
                        name=f"full_tail_mix_same_epoch_mix_ub_{m}_{b}_{epoch}",
                    )
                    model.addCons(
                        same_epoch
                        >= full_batch_tail[(m, b)]
                        + full_batch_epoch[(m, b, epoch)]
                        + mix_block_epoch[(m, epoch)]
                        - 2,
                        name=f"full_tail_mix_same_epoch_exact_{m}_{b}_{epoch}",
                    )
                    _add_optional_gap_slack(
                        model,
                        chamber_idle_slacks,
                        mix_head_start[(m, first_segment_id)],
                        full_front_unload_end[(m, b)],
                        same_epoch,
                        big_m,
                        f"full_to_mix_idle_{m}_{b}_{epoch}",
                    )
            else:
                tail_to_mix = model.addVar(vtype="B", name=f"full_tail_to_mix_active_{m}_{b}")
                model.addCons(
                    tail_to_mix <= full_batch_tail[(m, b)],
                    name=f"full_tail_to_mix_tail_ub_{m}_{b}",
                )
                model.addCons(
                    tail_to_mix <= mix_active[m],
                    name=f"full_tail_to_mix_mix_ub_{m}_{b}",
                )
                model.addCons(
                    tail_to_mix >= full_batch_tail[(m, b)] + mix_active[m] - 1,
                    name=f"full_tail_to_mix_exact_{m}_{b}",
                )
                _add_optional_gap_slack(
                    model,
                    chamber_idle_slacks,
                    mix_head_start[(m, first_segment_id)],
                    full_front_unload_end[(m, b)],
                    tail_to_mix,
                    big_m,
                    f"full_to_mix_idle_{m}_{b}",
                )

    for m in pm_ids:
        for b in full_batches:
            used = full_batch_used[(m, b)]
            _add_duration_cons(
                model,
                full_front_load_start[(m, b)],
                full_front_load_end[(m, b)],
                cfg.pair_transfer_time,
                f"full_front_load_{m}_{b}",
                used,
            )
            _add_residency_upper_bound(
                model,
                full_front_load_start[(m, b)],
                full_front_load_end[(m, b)],
                cfg.max_robot_residency_time,
                f"full_front_load_robot_residency_{m}_{b}",
                used,
            )
            _add_duration_cons(
                model,
                full_start[(m, b)],
                full_end[(m, b)],
                cfg.full_process_time,
                f"full_proc_{m}_{b}",
                used,
            )
            _add_duration_cons(
                model,
                full_back_load_start[(m, b)],
                full_back_load_end[(m, b)],
                cfg.pair_transfer_time,
                f"full_back_load_{m}_{b}",
                used,
            )
            _add_residency_upper_bound(
                model,
                full_back_load_start[(m, b)],
                full_back_load_end[(m, b)],
                cfg.max_robot_residency_time,
                f"full_back_load_robot_residency_{m}_{b}",
                used,
            )
            _add_duration_cons(
                model,
                full_back_unload_start[(m, b)],
                full_back_unload_end[(m, b)],
                cfg.pair_transfer_time,
                f"full_back_unload_{m}_{b}",
                used,
            )
            _add_residency_upper_bound(
                model,
                full_back_unload_start[(m, b)],
                full_back_unload_end[(m, b)],
                cfg.max_robot_residency_time,
                f"full_back_unload_robot_residency_{m}_{b}",
                used,
            )
            _add_duration_cons(
                model,
                full_front_unload_start[(m, b)],
                full_front_unload_end[(m, b)],
                cfg.pair_transfer_time,
                f"full_front_unload_{m}_{b}",
                used,
            )
            _add_residency_upper_bound(
                model,
                full_front_unload_start[(m, b)],
                full_front_unload_end[(m, b)],
                cfg.max_robot_residency_time,
                f"full_front_unload_robot_residency_{m}_{b}",
                used,
            )
            _add_precedence_lower_bound(
                model,
                full_back_load_start[(m, b)],
                full_front_load_end[(m, b)],
                big_m,
                f"full_front_to_back_load_lb_{m}_{b}",
                used,
                cfg.pm_rotation_time_180,
            )
            model.addCons(
                full_start[(m, b)] == full_back_load_end[(m, b)],
                name=f"full_load_to_proc_sync_{m}_{b}",
            )
            _add_precedence_lower_bound(
                model,
                full_back_unload_start[(m, b)],
                full_end[(m, b)],
                big_m,
                f"full_proc_to_back_unload_lb_{m}_{b}",
                used,
            )
            _add_precedence_lower_bound(
                model,
                full_front_unload_start[(m, b)],
                full_back_unload_end[(m, b)],
                big_m,
                f"full_back_to_front_unload_lb_{m}_{b}",
                used,
                cfg.pm_rotation_time_180,
            )

        for clean_slot in clean_slots:
            used = clean_active[(m, clean_slot)]
            _add_duration_cons(
                model,
                clean_front_load_start[(m, clean_slot)],
                clean_front_load_end[(m, clean_slot)],
                cfg.pair_transfer_time,
                f"clean_front_load_{m}_{clean_slot}",
                used,
            )
            _add_residency_upper_bound(
                model,
                clean_front_load_start[(m, clean_slot)],
                clean_front_load_end[(m, clean_slot)],
                cfg.max_robot_residency_time,
                f"clean_front_load_robot_residency_{m}_{clean_slot}",
                used,
            )
            _add_duration_cons(
                model,
                clean_back_load_start[(m, clean_slot)],
                clean_back_load_end[(m, clean_slot)],
                cfg.pair_transfer_time,
                f"clean_back_load_{m}_{clean_slot}",
                used,
            )
            _add_residency_upper_bound(
                model,
                clean_back_load_start[(m, clean_slot)],
                clean_back_load_end[(m, clean_slot)],
                cfg.max_robot_residency_time,
                f"clean_back_load_robot_residency_{m}_{clean_slot}",
                used,
            )
            _add_duration_cons(
                model,
                clean_start[(m, clean_slot)],
                clean_end[(m, clean_slot)],
                cfg.effective_cleaning_process_time,
                f"clean_proc_{m}_{clean_slot}",
                used,
            )
            _add_duration_cons(
                model,
                clean_back_unload_start[(m, clean_slot)],
                clean_back_unload_end[(m, clean_slot)],
                cfg.pair_transfer_time,
                f"clean_back_unload_{m}_{clean_slot}",
                used,
            )
            _add_residency_upper_bound(
                model,
                clean_back_unload_start[(m, clean_slot)],
                clean_back_unload_end[(m, clean_slot)],
                cfg.max_robot_residency_time,
                f"clean_back_unload_robot_residency_{m}_{clean_slot}",
                used,
            )
            _add_duration_cons(
                model,
                clean_front_unload_start[(m, clean_slot)],
                clean_front_unload_end[(m, clean_slot)],
                cfg.pair_transfer_time,
                f"clean_front_unload_{m}_{clean_slot}",
                used,
            )
            _add_residency_upper_bound(
                model,
                clean_front_unload_start[(m, clean_slot)],
                clean_front_unload_end[(m, clean_slot)],
                cfg.max_robot_residency_time,
                f"clean_front_unload_robot_residency_{m}_{clean_slot}",
                used,
            )
            _add_precedence_lower_bound(
                model,
                clean_back_load_start[(m, clean_slot)],
                clean_front_load_end[(m, clean_slot)],
                big_m,
                f"clean_front_to_back_load_lb_{m}_{clean_slot}",
                used,
                cfg.pm_rotation_time_180,
            )
            _add_precedence_lower_bound(
                model,
                clean_start[(m, clean_slot)],
                clean_back_load_end[(m, clean_slot)],
                big_m,
                f"clean_load_to_proc_lb_{m}_{clean_slot}",
                used,
            )
            _add_precedence_lower_bound(
                model,
                clean_back_unload_start[(m, clean_slot)],
                clean_end[(m, clean_slot)],
                big_m,
                f"clean_proc_to_back_unload_lb_{m}_{clean_slot}",
                used,
            )
            _add_precedence_lower_bound(
                model,
                clean_front_unload_start[(m, clean_slot)],
                clean_back_unload_end[(m, clean_slot)],
                big_m,
                f"clean_back_to_front_unload_lb_{m}_{clean_slot}",
                used,
                cfg.pm_rotation_time_180,
            )
            if clean_slot > 1:
                _add_precedence_lower_bound(
                    model,
                    clean_front_load_start[(m, clean_slot)],
                    clean_front_unload_end[(m, clean_slot - 1)],
                    big_m,
                    f"clean_sequence_lb_{m}_{clean_slot}",
                    used,
                )

        for b in full_batches[:-1]:
            _add_precedence_lower_bound(
                model,
                full_front_load_start[(m, b + 1)],
                full_front_unload_end[(m, b)],
                big_m,
                f"full_batch_serial_order_{m}_{b}_{b + 1}",
                full_batch_used[(m, b + 1)],
            )

        # Chamber occupancy follows the technical disclosure: a chamber has one
        # serial 4x1 block followed by PEC-bounded 2x2 segments, with cleaning
        # windows between process epochs when the interval is reached.
        full_batch_tasks = [
            (
                f"full_batch_window_{m}_{b}",
                full_front_load_start[(m, b)],
                full_front_unload_end[(m, b)],
                full_batch_used[(m, b)],
            )
            for b in full_batches
        ]
        full_batch_tasks.extend(
            (
                f"clean_window_{m}_{clean_slot}",
                clean_front_load_start[(m, clean_slot)],
                clean_front_unload_end[(m, clean_slot)],
                clean_active[(m, clean_slot)],
            )
            for clean_slot in clean_slots
        )
        _add_unary_resource_no_overlap(model, full_batch_tasks, big_m, f"seq_full_batch_{m}")

    for m in pm_ids:
        for c in mix_cycles:
            used = mix_cycle_used[(m, c)]
            model.addCons(
                mix_cycle_start[(m, c)] <= big_m * used,
                name=f"mix_cycle_start_cap_{m}_{c}",
            )
            model.addCons(
                mix_cycle_end[(m, c)] <= big_m * used,
                name=f"mix_cycle_end_cap_{m}_{c}",
            )
            model.addCons(
                mix_cycle_end[(m, c)] == mix_cycle_start[(m, c)] + cfg.mix_process_time * used,
                name=f"mix_cycle_duration_{m}_{c}",
            )

        for c in mix_cycles[1:]:
            used = mix_active[m] if mix_bridge_active[(m, c)] else 0
            _add_duration_cons(
                model,
                mix_bridge_start[(m, c)],
                mix_bridge_end[(m, c)],
                cfg.pair_transfer_time,
                f"mix_bridge_{m}_{c}",
                used,
            )
            _add_residency_upper_bound(
                model,
                mix_bridge_start[(m, c)],
                mix_bridge_end[(m, c)],
                cfg.max_robot_residency_time,
                f"mix_bridge_robot_residency_{m}_{c}",
                used,
            )
            if mix_bridge_active[(m, c)]:
                _add_precedence_lower_bound(
                    model,
                    mix_bridge_start[(m, c)],
                    mix_cycle_end[(m, c - 1)],
                    big_m,
                    f"mix_cycle_to_bridge_lb_{m}_{c}",
                    used,
                )
                _add_optional_gap_slack(
                    model,
                    chamber_idle_slacks,
                    mix_bridge_start[(m, c)],
                    mix_cycle_end[(m, c - 1)],
                    used,
                    big_m,
                    f"mix_cycle_to_bridge_idle_{m}_{c}",
                )
                model.addCons(
                    mix_cycle_start[(m, c)] == mix_bridge_end[(m, c)],
                    name=f"mix_bridge_to_cycle_tight_{m}_{c}",
                )

        for segment in cleaning_layout[m]["segments"]:
            segment_id = segment["id"]
            first_cycle = segment["cycles"][0]
            last_cycle = segment["cycles"][-1]
            key = (m, segment_id)
            _add_duration_cons(
                model,
                mix_head_start[key],
                mix_head_end[key],
                cfg.pair_transfer_time,
                f"mix_head_{m}_{segment_id}",
                mix_active[m],
            )
            _add_residency_upper_bound(
                model,
                mix_head_start[key],
                mix_head_end[key],
                cfg.max_robot_residency_time,
                f"mix_head_robot_residency_{m}_{segment_id}",
                mix_active[m],
            )
            model.addCons(
                mix_cycle_start[(m, first_cycle)] == mix_head_end[key],
                name=f"mix_head_to_cycle_tight_{m}_{segment_id}",
            )
            _add_duration_cons(
                model,
                mix_tail_start[key],
                mix_tail_end[key],
                cfg.pair_transfer_time,
                f"mix_tail_{m}_{segment_id}",
                mix_active[m],
            )
            _add_residency_upper_bound(
                model,
                mix_tail_start[key],
                mix_tail_end[key],
                cfg.max_robot_residency_time,
                f"mix_tail_robot_residency_{m}_{segment_id}",
                mix_active[m],
            )
            _link_optional_stage(
                model,
                mix_last_cycle_start[key],
                mix_last_cycle_end[key],
                mix_cycle_start[(m, last_cycle)],
                mix_cycle_end[(m, last_cycle)],
                mix_active[m],
                big_m,
                f"mix_last_cycle_link_{m}_{segment_id}",
            )
            _link_optional_stage(
                model,
                mix_tail_load_start[key],
                mix_tail_load_end[key],
                mix_bridge_start[(m, last_cycle)],
                mix_bridge_end[(m, last_cycle)],
                mix_active[m],
                big_m,
                f"mix_tail_load_link_{m}_{segment_id}",
            )
            _add_precedence_lower_bound(
                model,
                mix_tail_start[key],
                mix_last_cycle_end[key],
                big_m,
                f"mix_last_cycle_to_tail_lb_{m}_{segment_id}",
                mix_active[m],
            )
            _add_optional_gap_slack(
                model,
                chamber_idle_slacks,
                mix_tail_start[key],
                mix_last_cycle_end[key],
                mix_active[m],
                big_m,
                f"mix_tail_idle_{m}_{segment_id}",
            )

        if cleaning_layout[m]["segments"]:
            first_segment_id = cleaning_layout[m]["segments"][0]["id"]
            for b in full_batches:
                model.addCons(
                    full_front_unload_end[(m, b)]
                    <= mix_head_start[(m, first_segment_id)]
                    + big_m * (1 - full_batch_used[(m, b)])
                    + big_m * (1 - mix_active[m]),
                    name=f"full_before_mix_{m}_{b}",
                )

    if clean_slots:
        for m in pm_ids:
            for b in full_batches:
                for epoch in chamber_epochs:
                    selector = full_batch_epoch[(m, b, epoch)]
                    if epoch > 1:
                        model.addCons(
                            full_front_load_start[(m, b)]
                            >= clean_front_unload_end[(m, epoch - 1)] - big_m * (1 - selector),
                            name=f"full_epoch_after_clean_{m}_{b}_{epoch}",
                        )
                    if epoch <= len(clean_slots):
                        model.addCons(
                            full_front_unload_end[(m, b)]
                            <= clean_front_load_start[(m, epoch)]
                            + big_m * (1 - selector)
                            + big_m * (1 - clean_active[(m, epoch)]),
                            name=f"full_epoch_before_clean_{m}_{b}_{epoch}",
                        )

            for segment in cleaning_layout[m]["segments"]:
                segment_id = segment["id"]
                epoch = segment["epoch"]
                key = (m, segment_id)
                if epoch > 1:
                    model.addCons(
                        mix_head_start[key]
                        >= clean_front_unload_end[(m, epoch - 1)] - big_m * (1 - mix_active[m]),
                        name=f"mix_segment_after_clean_{m}_{segment_id}",
                    )
                if epoch <= len(clean_slots):
                    model.addCons(
                        mix_tail_end[key]
                        <= clean_front_load_start[(m, epoch)]
                        + big_m * (1 - mix_active[m])
                        + big_m * (1 - clean_active[(m, epoch)]),
                        name=f"mix_segment_before_clean_{m}_{segment_id}",
                    )

    for p in full_pair_ids:
        for m in pm_ids:
            for b in full_batches:
                for s in full_sides:
                    selector = assign_full[(p, m, b, s)]
                    _link_stage_by_binary(
                        model,
                        full_pair_vtr_load_start[p],
                        full_pair_vtr_load_end[p],
                        full_side_load_start[(m, b, s)],
                        full_side_load_end[(m, b, s)],
                        selector,
                        big_m,
                        f"full_pair_load_link_{p}_{m}_{b}_{s}",
                    )
                    _link_stage_by_binary(
                        model,
                        full_pair_pm_start[p],
                        full_pair_pm_end[p],
                        full_start[(m, b)],
                        full_end[(m, b)],
                        selector,
                        big_m,
                        f"full_pair_pm_link_{p}_{m}_{b}_{s}",
                    )
                    _link_stage_by_binary(
                        model,
                        full_pair_vtr_unload_start[p],
                        full_pair_vtr_unload_end[p],
                        full_side_unload_start[(m, b, s)],
                        full_side_unload_end[(m, b, s)],
                        selector,
                        big_m,
                        f"full_pair_unload_link_{p}_{m}_{b}_{s}",
                    )
        model.addCons(
            full_pair_completion[p] == full_pair_vtr_unload_end[p],
            name=f"full_pair_completion_def_{p}",
        )
        model.addCons(
            full_pair_post_process_wait[p] == full_pair_vtr_unload_start[p] - full_pair_pm_end[p],
            name=f"full_pair_post_process_wait_def_{p}",
        )

    for p in mix_pair_ids:
        for m in pm_ids:
            for r in mix_positions:
                selector = assign_mix[(p, m, r)]
                segment_id = mix_position_segment.get((m, r))
                if segment_id is None:
                    continue
                first_cycle = mix_position_first_cycle[(m, r)]
                segment_key = (m, segment_id)
                if r == mix_segment_first_position[segment_key]:
                    _link_stage_by_binary(
                        model,
                        mix_pair_vtr_load_start[p],
                        mix_pair_vtr_load_end[p],
                        mix_head_start[segment_key],
                        mix_head_end[segment_key],
                        selector,
                        big_m,
                        f"mix_pair_load_head_link_{p}_{m}_{r}_{segment_id}",
                    )
                else:
                    _link_stage_by_binary(
                        model,
                        mix_pair_vtr_load_start[p],
                        mix_pair_vtr_load_end[p],
                        mix_bridge_start[(m, first_cycle)],
                        mix_bridge_end[(m, first_cycle)],
                        selector,
                        big_m,
                        f"mix_pair_load_bridge_link_{p}_{m}_{r}",
                    )
                _link_stage_by_binary(
                    model,
                    mix_pair_pm_start[p],
                    mix_pair_pm_end[p],
                    mix_cycle_start[(m, first_cycle)],
                    mix_cycle_end[(m, first_cycle + 1)],
                    selector,
                    big_m,
                    f"mix_pair_pm_link_{p}_{m}_{r}",
                )
                if r == mix_segment_last_position[segment_key]:
                    _link_stage_by_binary(
                        model,
                        mix_pair_vtr_unload_start[p],
                        mix_pair_vtr_unload_end[p],
                        mix_tail_start[segment_key],
                        mix_tail_end[segment_key],
                        selector,
                        big_m,
                        f"mix_pair_tail_unload_link_{p}_{m}_{r}_{segment_id}",
                    )
                else:
                    _link_stage_by_binary(
                        model,
                        mix_pair_vtr_unload_start[p],
                        mix_pair_vtr_unload_end[p],
                        mix_bridge_start[(m, first_cycle + 2)],
                        mix_bridge_end[(m, first_cycle + 2)],
                        selector,
                        big_m,
                        f"mix_pair_mid_unload_link_{p}_{m}_{r}",
                    )
        model.addCons(
            mix_pair_completion[p] == mix_pair_vtr_unload_end[p],
            name=f"mix_pair_completion_def_{p}",
        )
        model.addCons(
            mix_pair_post_process_wait[p] == mix_pair_vtr_unload_start[p] - mix_pair_pm_end[p],
            name=f"mix_pair_post_process_wait_def_{p}",
        )

    product_stage_order = [
        "atr_lp_al",
        "atr_hold_before_al",
        "atr_al_exchange",
        "al",
        "atr_hold_after_al",
        "atr_al_llupper",
        "llupper",
        "vtr_load",
        "pm",
        "vtr_unload",
        "lllower",
        "atr_lllower_lp",
    ]
    prod_stage_start = {
        (w, stage): model.addVar(vtype="C", lb=0.0, name=f"prod_stage_start_{w}_{stage}")
        for w in product_wafers
        for stage in product_stage_order
    }
    prod_stage_end = {
        (w, stage): model.addVar(vtype="C", lb=0.0, name=f"prod_stage_end_{w}_{stage}")
        for w in product_wafers
        for stage in product_stage_order
    }
    wafer_completion = {
        w: model.addVar(vtype="C", lb=0.0, name=f"wafer_completion_{w}")
        for w in product_wafers
    }
    # Excess residence after the required LL dwell.  These variables are
    # directly minimized as a secondary objective, so non-critical wafers are
    # no longer left in an LL simply because their delay does not affect c_max.
    llupper_wait = {
        w: model.addVar(vtype="C", lb=0.0, name=f"llupper_wait_{w}")
        for w in product_wafers
    }
    lllower_wait = {
        w: model.addVar(vtype="C", lb=0.0, name=f"lllower_wait_{w}")
        for w in product_wafers
    }
    for w in product_wafers:
        _add_duration_cons(
            model,
            prod_stage_start[(w, "atr_lp_al")],
            prod_stage_end[(w, "atr_lp_al")],
            cfg.atr_lp_al_total_time,
            f"prod_atr_lp_al_{w}",
        )
        pair_as_second = product_pair_second_by_wafer.get(w)
        pair_as_first = product_pair_first_by_wafer.get(w)
        if pair_as_second is None:
            model.addCons(
                prod_stage_start[(w, "al")] == prod_stage_end[(w, "atr_lp_al")],
                name=f"prod_al_start_immediately_{w}",
            )
            model.addCons(
                prod_stage_start[(w, "atr_hold_before_al")] == 0.0,
                name=f"prod_atr_hold_before_al_start_zero_{w}",
            )
            model.addCons(
                prod_stage_end[(w, "atr_hold_before_al")] == 0.0,
                name=f"prod_atr_hold_before_al_end_zero_{w}",
            )
            model.addCons(
                prod_stage_start[(w, "atr_al_exchange")] == 0.0,
                name=f"prod_atr_al_exchange_start_zero_{w}",
            )
            model.addCons(
                prod_stage_end[(w, "atr_al_exchange")] == 0.0,
                name=f"prod_atr_al_exchange_end_zero_{w}",
            )
        else:
            input_double = product_pair_atr_lp_al_double[pair_as_second]
            output_double = product_pair_atr_al_llupper_double[pair_as_second]
            first = product_pair_first_member[pair_as_second]
            model.addCons(
                prod_stage_start[(w, "al")]
                >= prod_stage_end[(w, "atr_lp_al")] - big_m * input_double,
                name=f"prod_al_start_single_lb_{w}",
            )
            model.addCons(
                prod_stage_start[(w, "al")]
                <= prod_stage_end[(w, "atr_lp_al")] + big_m * input_double,
                name=f"prod_al_start_single_ub_{w}",
            )
            # With a double LP pickup but single LL placement, ATR first
            # places wafer 1 into LLupper, then carries wafer 2 back to AL.
            # The exchange starts after that physical detour. With a shared
            # LL placement, the exchange instead picks wafer 1 from AL and
            # places wafer 2 into the one-slot AL before its calibration.
            model.addCons(
                prod_stage_start[(w, "atr_al_exchange")]
                >= prod_stage_end[(first, "al")]
                - big_m * (1 - output_double),
                name=f"prod_al_exchange_double_output_lb_{w}",
            )
            model.addCons(
                prod_stage_start[(w, "atr_al_exchange")]
                <= prod_stage_end[(first, "al")]
                + big_m * (1 - output_double),
                name=f"prod_al_exchange_double_output_ub_{w}",
            )
            model.addCons(
                prod_stage_start[(w, "atr_al_exchange")]
                >= prod_stage_end[(first, "atr_al_llupper")]
                + cfg.atr_transfer_time
                - big_m * (1 - input_double + output_double),
                name=f"prod_al_exchange_double_input_single_output_lb_{w}",
            )
            model.addCons(
                prod_stage_start[(w, "atr_al_exchange")]
                <= prod_stage_end[(first, "atr_al_llupper")]
                + cfg.atr_transfer_time
                + big_m * (1 - input_double + output_double),
                name=f"prod_al_exchange_double_input_single_output_ub_{w}",
            )
            model.addCons(
                prod_stage_start[(w, "atr_al_exchange")] <= big_m * input_double,
                name=f"prod_al_exchange_start_active_{w}",
            )
            model.addCons(
                prod_stage_end[(w, "atr_al_exchange")]
                == prod_stage_start[(w, "atr_al_exchange")]
                + cfg.al_exchange_time * output_double
                + cfg.al_companion_place_time * (input_double - output_double),
                name=f"prod_al_exchange_duration_{w}",
            )
            model.addCons(
                prod_stage_start[(w, "al")]
                >= prod_stage_end[(w, "atr_al_exchange")] - big_m * (1 - input_double),
                name=f"prod_al_start_after_exchange_lb_{w}",
            )
            model.addCons(
                prod_stage_start[(w, "al")]
                <= prod_stage_end[(w, "atr_al_exchange")] + big_m * (1 - input_double),
                name=f"prod_al_start_after_exchange_ub_{w}",
            )
            _link_optional_stage(
                model,
                prod_stage_start[(w, "atr_hold_before_al")],
                prod_stage_end[(w, "atr_hold_before_al")],
                prod_stage_end[(w, "atr_lp_al")],
                prod_stage_start[(w, "atr_al_exchange")],
                input_double,
                big_m,
                f"prod_atr_hold_before_al_{w}",
            )
        model.addCons(
            prod_stage_end[(w, "al")] == prod_stage_start[(w, "al")] + cfg.aligner_time,
            name=f"prod_al_duration_{w}",
        )
        if pair_as_first is None or pair_as_first not in product_pair_second_member:
            model.addCons(
                prod_stage_start[(w, "atr_al_llupper")] == prod_stage_end[(w, "al")],
                name=f"prod_al_pickup_immediately_{w}",
            )
            model.addCons(
                prod_stage_start[(w, "atr_hold_after_al")] == 0.0,
                name=f"prod_atr_hold_after_al_start_zero_{w}",
            )
            model.addCons(
                prod_stage_end[(w, "atr_hold_after_al")] == 0.0,
                name=f"prod_atr_hold_after_al_end_zero_{w}",
            )
        elif pair_as_second is not None:
            model.addCons(
                prod_stage_start[(w, "atr_al_llupper")] == prod_stage_end[(w, "al")],
                name=f"prod_al_pickup_immediately_{w}",
            )
            model.addCons(
                prod_stage_start[(w, "atr_hold_after_al")] == 0.0,
                name=f"prod_atr_hold_after_al_start_zero_{w}",
            )
            model.addCons(
                prod_stage_end[(w, "atr_hold_after_al")] == 0.0,
                name=f"prod_atr_hold_after_al_end_zero_{w}",
            )
        else:
            double_var = product_pair_atr_al_llupper_double[pair_as_first]
            second = product_pair_second_member[pair_as_first]
            model.addCons(
                prod_stage_start[(w, "atr_al_llupper")]
                >= prod_stage_end[(w, "al")] - big_m * double_var,
                name=f"prod_al_pickup_single_lb_{w}",
            )
            model.addCons(
                prod_stage_start[(w, "atr_al_llupper")]
                <= prod_stage_end[(w, "al")] + big_m * double_var,
                name=f"prod_al_pickup_single_ub_{w}",
            )
            model.addCons(
                prod_stage_start[(w, "atr_al_llupper")]
                >= prod_stage_end[(second, "al")] - big_m * (1 - double_var),
                name=f"prod_al_pickup_double_lb_{w}",
            )
            model.addCons(
                prod_stage_start[(w, "atr_al_llupper")]
                <= prod_stage_end[(second, "al")] + big_m * (1 - double_var),
                name=f"prod_al_pickup_double_ub_{w}",
            )
            _link_optional_stage(
                model,
                prod_stage_start[(w, "atr_hold_after_al")],
                prod_stage_end[(w, "atr_hold_after_al")],
                prod_stage_end[(second, "atr_al_exchange")],
                prod_stage_start[(w, "atr_al_llupper")],
                double_var,
                big_m,
                f"prod_atr_hold_after_al_{w}",
            )
        _add_duration_cons(
            model,
            prod_stage_start[(w, "atr_al_llupper")],
            prod_stage_end[(w, "atr_al_llupper")],
            cfg.atr_al_llupper_total_time,
            f"prod_atr_al_llupper_{w}",
        )
        # Each LL slot has its own pressure state.  LLupper starts in atmosphere
        # after ATR placement and pumps down before VTR may access this slot.
        model.addCons(
            prod_stage_start[(w, "llupper")] == prod_stage_end[(w, "atr_al_llupper")],
            name=f"prod_llupper_start_{w}",
        )
        model.addCons(
            prod_stage_end[(w, "llupper")] == prod_stage_start[(w, "llupper")] + cfg.llupper_time,
            name=f"prod_llupper_duration_{w}",
        )
        model.addCons(
            prod_stage_end[(w, "llupper")]
            <= prod_stage_start[(w, "llupper")] + cfg.max_module_residency_time,
            name=f"prod_llupper_max_residency_{w}",
        )
        model.addCons(
            prod_stage_start[(w, "vtr_load")] >= prod_stage_end[(w, "llupper")],
            name=f"prod_llupper_to_vtr_{w}",
        )
        model.addCons(
            llupper_wait[w]
            == prod_stage_start[(w, "vtr_load")] - prod_stage_end[(w, "llupper")],
            name=f"llupper_wait_def_{w}",
        )
        model.addCons(
            prod_stage_start[(w, "vtr_load")]
            <= prod_stage_end[(w, "atr_al_llupper")] + cfg.max_module_residency_time,
            name=f"prod_llupper_physical_max_residency_{w}",
        )
        _add_duration_cons(
            model,
            prod_stage_start[(w, "vtr_load")],
            prod_stage_end[(w, "vtr_load")],
            cfg.pair_transfer_time,
            f"prod_vtr_load_{w}",
        )
        model.addCons(
            prod_stage_start[(w, "pm")] >= prod_stage_end[(w, "vtr_load")],
            name=f"prod_vtr_load_to_pm_{w}",
        )
        model.addCons(
            prod_stage_end[(w, "pm")] <= prod_stage_start[(w, "pm")] + cfg.max_module_residency_time,
            name=f"prod_pm_max_residency_{w}",
        )
        model.addCons(
            prod_stage_start[(w, "vtr_unload")] >= prod_stage_end[(w, "pm")],
            name=f"prod_pm_to_vtr_unload_{w}",
        )
        _add_duration_cons(
            model,
            prod_stage_start[(w, "vtr_unload")],
            prod_stage_end[(w, "vtr_unload")],
            cfg.pair_transfer_time,
            f"prod_vtr_unload_{w}",
        )
        # LLlower is initially in vacuum for VTR placement.  It then vents to
        # atmosphere before ATR may access this slot.
        model.addCons(
            prod_stage_start[(w, "lllower")] == prod_stage_end[(w, "vtr_unload")],
            name=f"prod_lllower_start_{w}",
        )
        model.addCons(
            prod_stage_end[(w, "lllower")] == prod_stage_start[(w, "lllower")] + cfg.lllower_time,
            name=f"prod_lllower_duration_{w}",
        )
        model.addCons(
            prod_stage_end[(w, "lllower")]
            <= prod_stage_start[(w, "lllower")] + cfg.max_module_residency_time,
            name=f"prod_lllower_max_residency_{w}",
        )
        model.addCons(
            prod_stage_start[(w, "atr_lllower_lp")] >= prod_stage_end[(w, "lllower")],
            name=f"prod_atr_lllower_lp_start_{w}",
        )
        model.addCons(
            lllower_wait[w]
            == prod_stage_start[(w, "atr_lllower_lp")] - prod_stage_end[(w, "lllower")],
            name=f"lllower_wait_def_{w}",
        )
        model.addCons(
            prod_stage_start[(w, "atr_lllower_lp")]
            <= prod_stage_end[(w, "vtr_unload")] + cfg.max_module_residency_time,
            name=f"prod_lllower_physical_max_residency_{w}",
        )
        _add_duration_cons(
            model,
            prod_stage_start[(w, "atr_lllower_lp")],
            prod_stage_end[(w, "atr_lllower_lp")],
            cfg.atr_lllower_lp_total_time,
            f"prod_atr_lllower_lp_{w}",
        )
        model.addCons(
            wafer_completion[w] == prod_stage_end[(w, "atr_lllower_lp")],
            name=f"wafer_completion_def_{w}",
        )
        for stage in ("atr_lp_al", "atr_al_llupper", "vtr_load", "vtr_unload", "atr_lllower_lp"):
            model.addCons(
                prod_stage_end[(w, stage)] <= prod_stage_start[(w, stage)] + cfg.max_robot_residency_time,
                name=f"prod_{stage}_max_robot_residency_{w}",
            )

    for w in full_wafers:
        for p in full_pair_ids:
            selector = wafer_to_full_pair[(w, p)]
            # The pair transfer window can contain either one double-gripper
            # VTR action or two single-gripper actions. Synchronization is
            # selected separately by full_vtr_*_double below.
            _contain_stage_by_binary(
                model,
                prod_stage_start[(w, "vtr_load")],
                prod_stage_end[(w, "vtr_load")],
                full_pair_vtr_load_start[p],
                full_pair_vtr_load_end[p],
                selector,
                big_m,
                f"prod_full_vtr_load_window_{w}_{p}",
            )
            _link_stage_by_binary(
                model,
                prod_stage_start[(w, "pm")],
                prod_stage_end[(w, "pm")],
                full_pair_pm_start[p],
                full_pair_pm_end[p],
                selector,
                big_m,
                f"prod_full_pm_link_{w}_{p}",
            )
            _contain_stage_by_binary(
                model,
                prod_stage_start[(w, "vtr_unload")],
                prod_stage_end[(w, "vtr_unload")],
                full_pair_vtr_unload_start[p],
                full_pair_vtr_unload_end[p],
                selector,
                big_m,
                f"prod_full_vtr_unload_window_{w}_{p}",
            )

    for w in mix_wafers:
        for p in mix_pair_ids:
            selector = wafer_to_mix_pair[(w, p)]
            # The same atomic-transfer rule applies to a 2x2 PW pair.
            _link_stage_by_binary(
                model,
                prod_stage_start[(w, "vtr_load")],
                prod_stage_end[(w, "vtr_load")],
                mix_pair_vtr_load_start[p],
                mix_pair_vtr_load_end[p],
                selector,
                big_m,
                f"prod_mix_vtr_load_sync_{w}_{p}",
            )
            _link_stage_by_binary(
                model,
                prod_stage_start[(w, "pm")],
                prod_stage_end[(w, "pm")],
                mix_pair_pm_start[p],
                mix_pair_pm_end[p],
                selector,
                big_m,
                f"prod_mix_pm_link_{w}_{p}",
            )
            _link_stage_by_binary(
                model,
                prod_stage_start[(w, "vtr_unload")],
                prod_stage_end[(w, "vtr_unload")],
                mix_pair_vtr_unload_start[p],
                mix_pair_vtr_unload_end[p],
                selector,
                big_m,
                f"prod_mix_vtr_unload_sync_{w}_{p}",
            )

    # A double-gripper decision synchronizes only that robot route. Without
    # the decision, the two LL slots and their associated robot stages remain
    # fully independent.
    for p in full_pair_ids:
        members = sorted(full_pair_members[p])
        if len(members) != 2:
            continue
        first, second = members
        for route_name, first_stage, second_stage, double_var in (
            ("atr_lp_al", "atr_lp_al", "atr_lp_al", full_atr_lp_al_double[p]),
            ("atr_al_llupper", "atr_al_llupper", "atr_al_llupper", full_atr_al_llupper_double[p]),
            ("atr_return", "atr_lllower_lp", "atr_lllower_lp", full_atr_return_double[p]),
            ("vtr_load", "vtr_load", "vtr_load", full_vtr_load_double[p]),
            ("vtr_unload", "vtr_unload", "vtr_unload", full_vtr_unload_double[p]),
        ):
            _synchronize_stages_when(
                model,
                prod_stage_start[(first, first_stage)],
                prod_stage_end[(first, first_stage)],
                prod_stage_start[(second, second_stage)],
                prod_stage_end[(second, second_stage)],
                double_var,
                big_m,
                f"full_{route_name}_double_sync_{p}",
            )
    for p in mix_pair_ids:
        members = sorted(mix_pair_members[p])
        if len(members) != 2:
            continue
        first, second = members
        for route_name, first_stage, second_stage, double_var in (
            ("atr_lp_al", "atr_lp_al", "atr_lp_al", mix_atr_lp_al_double[p]),
            ("atr_al_llupper", "atr_al_llupper", "atr_al_llupper", mix_atr_al_llupper_double[p]),
            ("atr_return", "atr_lllower_lp", "atr_lllower_lp", mix_atr_return_double[p]),
            ("vtr_load", "vtr_load", "vtr_load", mix_vtr_load_double[p]),
            ("vtr_unload", "vtr_unload", "vtr_unload", mix_vtr_unload_double[p]),
        ):
            _synchronize_stages_when(
                model,
                prod_stage_start[(first, first_stage)],
                prod_stage_end[(first, first_stage)],
                prod_stage_start[(second, second_stage)],
                prod_stage_end[(second, second_stage)],
                double_var,
                big_m,
                f"mix_{route_name}_double_sync_{p}",
            )

    # A 4x1 batch uses both physical LL slots.  Its front side must therefore
    # clear LLupper before the back side enters, and its back side must clear
    # LLlower before the front side returns.  The release variables are max
    # envelopes over their members, so these constraints order physical slot
    # use without equating any two product-wafer schedules outside the PM.
    for m in pm_ids:
        for b in full_batches:
            for side in (1, 2):
                for p in full_pair_ids:
                    pair_side = assign_full[(p, m, b, side)]
                    for w in full_wafers:
                        member = wafer_to_full_pair[(w, p)]
                        inactive = 2 - pair_side - member
                        model.addCons(
                            full_side_llupper_release[(m, b, side)]
                            >= prod_stage_end[(w, "vtr_load")] - big_m * inactive,
                            name=f"full_llupper_release_{m}_{b}_{side}_{p}_{w}",
                        )
                        model.addCons(
                            full_side_lllower_release[(m, b, side)]
                            >= prod_stage_end[(w, "atr_lllower_lp")] - big_m * inactive,
                            name=f"full_lllower_release_{m}_{b}_{side}_{p}_{w}",
                        )

            for p in full_pair_ids:
                for w in full_wafers:
                    member = wafer_to_full_pair[(w, p)]
                    model.addCons(
                        prod_stage_start[(w, "atr_al_llupper")]
                        >= full_side_llupper_release[(m, b, 1)]
                        - big_m * (2 - assign_full[(p, m, b, 2)] - member),
                        name=f"full_llupper_side_handoff_{m}_{b}_{p}_{w}",
                    )
                    model.addCons(
                        prod_stage_start[(w, "lllower")]
                        >= full_side_lllower_release[(m, b, 2)]
                        - big_m * (2 - assign_full[(p, m, b, 1)] - member),
                        name=f"full_lllower_side_handoff_{m}_{b}_{p}_{w}",
                    )

    pec_job_specs = {}
    pec_job_counter = 0

    def add_pec_job(label, chamber_id, active_var, load_ref, pm_ref, unload_ref):
        nonlocal pec_job_counter
        pec_job_counter += 1
        pec_job_specs[pec_job_counter] = {
            "label": label,
            "chamber_id": chamber_id,
            "allowed_slots": pec_slots_by_pm[chamber_id],
            "active": active_var,
            "load_ref": load_ref,
            "pm_ref": pm_ref,
            "unload_ref": unload_ref,
        }

    for p, load in full_pair_loads.items():
        if load == 1:
            product_wafer = next(iter(full_pair_members[p]))
            for m in pm_ids:
                for b in full_batches:
                    for lane in full_sides:
                        add_pec_job(
                            f"embedded_full_{p}_{m}_{b}_{lane}",
                            m,
                            assign_full[(p, m, b, lane)],
                            (prod_stage_start[(product_wafer, "vtr_load")], prod_stage_end[(product_wafer, "vtr_load")]),
                            (prod_stage_start[(product_wafer, "pm")], prod_stage_end[(product_wafer, "pm")]),
                            (prod_stage_start[(product_wafer, "vtr_unload")], prod_stage_end[(product_wafer, "vtr_unload")]),
                        )
    for p, load in mix_pair_loads.items():
        if load == 1:
            product_wafer = next(iter(mix_pair_members[p]))
            for m in pm_ids:
                for r in mix_positions:
                    add_pec_job(
                        f"embedded_mix_{p}_{m}_{r}",
                        m,
                        assign_mix[(p, m, r)],
                        (prod_stage_start[(product_wafer, "vtr_load")], prod_stage_end[(product_wafer, "vtr_load")]),
                        (prod_stage_start[(product_wafer, "pm")], prod_stage_end[(product_wafer, "pm")]),
                        (prod_stage_start[(product_wafer, "vtr_unload")], prod_stage_end[(product_wafer, "vtr_unload")]),
                    )
    for m in pm_ids:
        for b in full_batches:
            for lane in full_sides:
                for filler_idx in range(1, 3):
                    add_pec_job(
                        f"full_fill_{m}_{b}_{lane}_{filler_idx}",
                        m,
                        full_filler_side[(m, b, lane)],
                        (full_side_load_start[(m, b, lane)], full_side_load_end[(m, b, lane)]),
                        (full_start[(m, b)], full_end[(m, b)]),
                        (full_side_unload_start[(m, b, lane)], full_side_unload_end[(m, b, lane)]),
                    )
        for segment in cleaning_layout[m]["segments"]:
            segment_id = segment["id"]
            key = (m, segment_id)
            first_cycle = segment["cycles"][0]
            for lane in range(1, 3):
                add_pec_job(
                    f"mix_head_{m}_{segment_id}_{lane}",
                    m,
                    mix_active[m],
                    (mix_head_start[key], mix_head_end[key]),
                    (mix_cycle_start[(m, first_cycle)], mix_cycle_end[(m, first_cycle)]),
                    (mix_bridge_start[(m, first_cycle + 1)], mix_bridge_end[(m, first_cycle + 1)]),
                )
                add_pec_job(
                    f"mix_tail_{m}_{segment_id}_{lane}",
                    m,
                    mix_active[m],
                    (mix_tail_load_start[key], mix_tail_load_end[key]),
                    (mix_last_cycle_start[key], mix_last_cycle_end[key]),
                    (mix_tail_start[key], mix_tail_end[key]),
                )
        for clean_slot in clean_slots:
            for lane in range(1, 3):
                add_pec_job(
                    f"clean_front_{m}_{clean_slot}_{lane}",
                    m,
                    clean_active[(m, clean_slot)],
                    (clean_front_load_start[(m, clean_slot)], clean_front_load_end[(m, clean_slot)]),
                    (clean_start[(m, clean_slot)], clean_end[(m, clean_slot)]),
                    (clean_front_unload_start[(m, clean_slot)], clean_front_unload_end[(m, clean_slot)]),
                )
                add_pec_job(
                    f"clean_back_{m}_{clean_slot}_{lane}",
                    m,
                    clean_active[(m, clean_slot)],
                    (clean_back_load_start[(m, clean_slot)], clean_back_load_end[(m, clean_slot)]),
                    (clean_start[(m, clean_slot)], clean_end[(m, clean_slot)]),
                    (clean_back_unload_start[(m, clean_slot)], clean_back_unload_end[(m, clean_slot)]),
                )

    pec_stage_order = ["vtr_load", "pm", "vtr_unload"]
    pec_job_ids = list(pec_job_specs.keys())
    pec_stage_start = {
        (job_id, stage): model.addVar(vtype="C", lb=0.0, name=f"pec_stage_start_{job_id}_{stage}")
        for job_id in pec_job_ids
        for stage in pec_stage_order
    }
    pec_stage_end = {
        (job_id, stage): model.addVar(vtype="C", lb=0.0, name=f"pec_stage_end_{job_id}_{stage}")
        for job_id in pec_job_ids
        for stage in pec_stage_order
    }
    pec_job_chamber = {
        job_id: model.addVar(
            vtype="B",
            name=f"pec_job_chamber_{job_id}_{pec_job_specs[job_id]['chamber_id']}",
        )
        for job_id in pec_job_ids
    }

    for job_id, spec in pec_job_specs.items():
        active = spec["active"]
        model.addCons(
            pec_job_chamber[job_id] == active,
            name=f"pec_job_chamber_link_{job_id}_{spec['chamber_id']}",
        )
        _link_optional_stage(
            model,
            pec_stage_start[(job_id, "vtr_load")],
            pec_stage_end[(job_id, "vtr_load")],
            spec["load_ref"][0],
            spec["load_ref"][1],
            active,
            big_m,
            f"pec_load_link_{job_id}",
        )
        _link_optional_stage(
            model,
            pec_stage_start[(job_id, "pm")],
            pec_stage_end[(job_id, "pm")],
            spec["pm_ref"][0],
            spec["pm_ref"][1],
            active,
            big_m,
            f"pec_pm_link_{job_id}",
        )
        _link_optional_stage(
            model,
            pec_stage_start[(job_id, "vtr_unload")],
            pec_stage_end[(job_id, "vtr_unload")],
            spec["unload_ref"][0],
            spec["unload_ref"][1],
            active,
            big_m,
            f"pec_unload_link_{job_id}",
        )
        for stage in ("vtr_load", "vtr_unload"):
            model.addCons(
                pec_stage_end[(job_id, stage)]
                <= pec_stage_start[(job_id, stage)] + cfg.max_robot_residency_time,
                name=f"pec_{stage}_max_robot_residency_{job_id}",
            )
        model.addCons(
            pec_stage_end[(job_id, "pm")]
            <= pec_stage_start[(job_id, "pm")] + cfg.max_module_residency_time,
            name=f"pec_pm_max_residency_{job_id}",
        )

    if pec_job_ids and cfg.pec_pool_size <= 0:
        raise ValueError("Active PEC jobs require pec_pool_size > 0.")

    if pec_job_ids:
        pec_task_specs = [
            (
                str(job_id),
                pec_stage_start[(job_id, "vtr_load")],
                pec_stage_end[(job_id, "vtr_unload")],
                pec_job_specs[job_id]["active"],
                pec_job_specs[job_id]["allowed_slots"],
            )
            for job_id in pec_job_ids
        ]
        _add_parallel_slot_resource(
            model,
            pec_task_specs,
            cfg.pec_pool_size,
            big_m,
            "pec_token_assign",
            "pec_token_order",
        )

    al_tasks = []
    llupper_tasks = []
    lllower_tasks = []
    for w in product_wafers:
        # AL is a single-slot calibrator. Its interval is exactly the
        # calibration process because arrival and pickup are both immediate.
        al_tasks.append(
            (str(w), prod_stage_start[(w, "al")], prod_stage_end[(w, "al")], None)
        )
        # Slot assignment covers the complete independent pressure cycle, not
        # only the wafer dwell.  This prevents the next robot from entering the
        # same slot before it has returned to its initial pressure state.
        llupper_tasks.append(
            (
                str(w),
                prod_stage_end[(w, "atr_al_llupper")] - cfg.atr_load_unload_time,
                prod_stage_end[(w, "vtr_load")] + cfg.llupper_time,
                None,
            )
        )
        lllower_tasks.append(
            (
                str(w),
                prod_stage_start[(w, "vtr_unload")],
                prod_stage_start[(w, "atr_lllower_lp")]
                + cfg.atr_load_unload_time
                + cfg.lllower_time,
                None,
            )
        )

    vtr_tasks = []
    vtr_task_locations = {}

    def append_vtr_task(task_name, task_start, task_end, task_active, source, destination):
        vtr_tasks.append((task_name, task_start, task_end, task_active))
        vtr_task_locations[task_name] = (source, destination)

    for m in pm_ids:
        for segment in cleaning_layout[m]["segments"]:
            segment_id = segment["id"]
            key = (m, segment_id)
            append_vtr_task(
                f"mix_head_{m}_{segment_id}",
                mix_head_start[key],
                mix_head_end[key],
                mix_active[m],
                "LLupper",
                f"CH{m}",
            )
            append_vtr_task(
                f"mix_tail_{m}_{segment_id}",
                mix_tail_start[key],
                mix_tail_end[key],
                mix_active[m],
                f"CH{m}",
                "LLlower",
            )
        for b in full_batches:
            append_vtr_task(
                f"full_front_load_{m}_{b}",
                full_front_load_start[(m, b)],
                full_front_load_end[(m, b)],
                full_batch_used[(m, b)],
                "LLupper",
                f"CH{m}",
            )
            append_vtr_task(
                f"full_back_load_{m}_{b}",
                full_back_load_start[(m, b)],
                full_back_load_end[(m, b)],
                full_batch_used[(m, b)],
                "LLupper",
                f"CH{m}",
            )
            append_vtr_task(
                f"full_back_unload_{m}_{b}",
                full_back_unload_start[(m, b)],
                full_back_unload_end[(m, b)],
                full_batch_used[(m, b)],
                f"CH{m}",
                "LLlower",
            )
            append_vtr_task(
                f"full_front_unload_{m}_{b}",
                full_front_unload_start[(m, b)],
                full_front_unload_end[(m, b)],
                full_batch_used[(m, b)],
                f"CH{m}",
                "LLlower",
            )
        for clean_slot in clean_slots:
            append_vtr_task(
                f"clean_front_load_{m}_{clean_slot}",
                clean_front_load_start[(m, clean_slot)],
                clean_front_load_end[(m, clean_slot)],
                clean_active[(m, clean_slot)],
                "PEC storage",
                f"CH{m}",
            )
            append_vtr_task(
                f"clean_back_load_{m}_{clean_slot}",
                clean_back_load_start[(m, clean_slot)],
                clean_back_load_end[(m, clean_slot)],
                clean_active[(m, clean_slot)],
                "PEC storage",
                f"CH{m}",
            )
            append_vtr_task(
                f"clean_back_unload_{m}_{clean_slot}",
                clean_back_unload_start[(m, clean_slot)],
                clean_back_unload_end[(m, clean_slot)],
                clean_active[(m, clean_slot)],
                f"CH{m}",
                "PEC storage",
            )
            append_vtr_task(
                f"clean_front_unload_{m}_{clean_slot}",
                clean_front_unload_start[(m, clean_slot)],
                clean_front_unload_end[(m, clean_slot)],
                clean_active[(m, clean_slot)],
                f"CH{m}",
                "PEC storage",
            )
        for c in mix_cycles[1:]:
            append_vtr_task(
                f"mix_bridge_{m}_{c}",
                mix_bridge_start[(m, c)],
                mix_bridge_end[(m, c)],
                mix_active[m] if mix_bridge_active[(m, c)] else 0,
                "LLupper",
                "LLlower",
            )

    def vtr_empty_transition(left_name, right_name):
        left_destination = vtr_task_locations[left_name][1]
        right_source = vtr_task_locations[right_name][0]
        return 0.0 if left_destination == right_source else cfg.pair_transfer_time

    atr_task_locations = {}
    for w in product_wafers:
        atr_task_locations[f"lp_al_{w}"] = ("LP", "AL")
        atr_task_locations[f"al_llupper_{w}"] = ("AL", "LL")
        atr_task_locations[f"lllower_lp_{w}"] = ("LL", "LP")

    def atr_empty_transition(left_name, right_name):
        left_destination = atr_task_locations[left_name][1]
        right_source = atr_task_locations[right_name][0]
        location_index = {"LP": 0, "AL": 1, "LL": 2}
        return abs(location_index[left_destination] - location_index[right_source]) * cfg.atr_transfer_time

    def pair_robot_actions(robot_name, pair_ids, pair_members, route_specs, route_windows=None, action_prefix="pair"):
        """Create one non-preemptive robot action for each PW pair and route.

        A selected double action uses one shared transfer window.  Otherwise the
        canonical first and second wafers execute two consecutive single
        transfers, so no unrelated robot action can be inserted between them.
        """
        actions = {}
        route_windows = route_windows or {}
        for route_name, stage_name, double_by_pair in route_specs:
            for p in pair_ids:
                members = sorted(pair_members[p])
                first = members[0]
                action_start = model.addVar(
                    vtype="C",
                    lb=0.0,
                    name=f"{robot_name}_{action_prefix}_action_start_{route_name}_{p}",
                )
                action_end = model.addVar(
                    vtype="C",
                    lb=0.0,
                    name=f"{robot_name}_{action_prefix}_action_end_{route_name}_{p}",
                )
                first_start = prod_stage_start[(first, stage_name)]
                first_end = prod_stage_end[(first, stage_name)]
                model.addCons(
                    action_start == first_start,
                    name=f"{robot_name}_{action_prefix}_action_start_link_{route_name}_{p}",
                )

                if len(members) == 1:
                    model.addCons(
                        action_end == first_end,
                        name=f"{robot_name}_{action_prefix}_action_end_single_{route_name}_{p}",
                    )
                else:
                    second = members[1]
                    second_start = prod_stage_start[(second, stage_name)]
                    second_end = prod_stage_end[(second, stage_name)]
                    double_var = double_by_pair[p]
                    # With two single moves, keep the same-route operations
                    # consecutive.  With a double move, synchronization above
                    # makes them one shared physical action.
                    model.addCons(
                        second_start >= first_end - big_m * double_var,
                        name=f"{robot_name}_{action_prefix}_single_order_lb_{route_name}_{p}",
                    )
                    model.addCons(
                        second_start <= first_end + big_m * double_var,
                        name=f"{robot_name}_{action_prefix}_single_order_ub_{route_name}_{p}",
                    )
                    model.addCons(
                        action_end >= first_end - big_m * (1 - double_var),
                        name=f"{robot_name}_{action_prefix}_action_end_double_lb_{route_name}_{p}",
                    )
                    model.addCons(
                        action_end <= first_end + big_m * (1 - double_var),
                        name=f"{robot_name}_{action_prefix}_action_end_double_ub_{route_name}_{p}",
                    )
                    model.addCons(
                        action_end >= second_end - big_m * double_var,
                        name=f"{robot_name}_{action_prefix}_action_end_single_lb_{route_name}_{p}",
                    )
                    model.addCons(
                        action_end <= second_end + big_m * double_var,
                        name=f"{robot_name}_{action_prefix}_action_end_single_ub_{route_name}_{p}",
                    )
                if route_name in route_windows:
                    window_start, window_end = route_windows[route_name][p]
                    model.addCons(
                        action_start == window_start,
                        name=f"{robot_name}_{action_prefix}_action_window_start_{route_name}_{p}",
                    )
                    model.addCons(
                        action_end == window_end,
                        name=f"{robot_name}_{action_prefix}_action_window_end_{route_name}_{p}",
                    )
                actions[(route_name, p)] = (f"{action_prefix}_{route_name}_{p}", action_start, action_end)
        return actions

    def full_pair_robot_actions(robot_name, route_specs, route_windows=None):
        return pair_robot_actions(
            robot_name,
            full_pair_ids,
            full_pair_members,
            route_specs,
            route_windows=route_windows,
            action_prefix="pair",
        )

    def mix_pair_robot_actions(robot_name, route_specs, route_windows=None):
        return pair_robot_actions(
            robot_name,
            mix_pair_ids,
            mix_pair_members,
            route_specs,
            route_windows=route_windows,
            action_prefix="mix_pair",
        )

    def add_robot_action_chain(robot_name, actions, transition_time=0.0):
        """Apply a known physical action order, including required empty repositioning."""
        for order_index, (left, right) in enumerate(zip(actions, actions[1:]), start=1):
            _left_name, _left_start, left_end = left
            _right_name, right_start, _right_end = right
            reposition_time = transition_time(left, right) if callable(transition_time) else transition_time
            model.addCons(
                right_start >= left_end + reposition_time,
                name=f"{robot_name}_physical_action_order_{order_index}",
            )

    full_pair_by_slot = {
        slot: p for p, slot in canonical_full_slot_by_pair.items()
    }

    def pair_at_slot(m, b, side):
        return full_pair_by_slot.get((m, b, side))

    # ATR has two grippers but only one physical motion path at a time. With a
    # selected bundled double action, it carries a PW pair from LP to AL,
    # serially calibrates the two wafers in the one-slot AL while retaining the
    # companion wafer, then carries the pair from AL to LLupper. Otherwise it
    # uses the original one-wafer-at-a-time action sequence.
    if pure_full_mode and cfg.use_legacy_pure_full_atr_chain:
        atr_return_actions = full_pair_robot_actions(
            "atr",
            (("lllower_lp", "atr_lllower_lp", full_atr_return_double),),
        )
        al_service_wafers = [
            w
            for p in full_pair_ids
            for w in sorted(full_pair_members[p])
        ]
        al_service_actions = []
        for p in full_pair_ids:
            members = sorted(full_pair_members[p])
            first = members[0]
            last = members[-1]
            al_service_actions.append(
                (
                    f"al_service_{p}",
                    prod_stage_start[(first, "atr_lp_al")],
                    prod_stage_end[(last, "atr_al_llupper")],
                )
            )
            if len(members) == 2:
                second = members[1]
                model.addCons(
                    prod_stage_start[(second, "atr_lp_al")]
                    >= prod_stage_end[(first, "atr_al_llupper")]
                    - big_m * full_atr_lp_al_double[p],
                    name=f"atr_al_service_single_pair_order_{p}",
                )
        add_robot_action_chain(
            "atr_al_service",
            al_service_actions,
            transition_time=cfg.atr_empty_ll_to_lp_time,
        )

        # Back-side unloading precedes front-side unloading in every PM batch,
        # so this is also the only physically valid global return order.
        atr_return_order = sorted(
            full_pair_ids,
            key=lambda p: (
                canonical_full_slot_by_pair[p][1],
                canonical_full_slot_by_pair[p][0],
                -canonical_full_slot_by_pair[p][2],
            ),
        )
        add_robot_action_chain(
            "atr_return",
            [atr_return_actions[("lllower_lp", p)] for p in atr_return_order],
            transition_time=cfg.atr_empty_ll_to_lp_time,
        )

        last_al_service_end = prod_stage_end[(al_service_wafers[-1], "atr_al_llupper")]
        for p in full_pair_ids:
            _return_name, return_start, return_end = atr_return_actions[("lllower_lp", p)]
            return_after_all_al = model.addVar(
                vtype="B",
                name=f"atr_return_after_all_al_{p}",
            )
            return_windows = []
            for w in al_service_wafers:
                selector = model.addVar(
                    vtype="B",
                    name=f"atr_return_during_al_{p}_{w}",
                )
                return_windows.append(selector)
                service_pair = full_pair_by_wafer[w]
                holding_selector = (
                    full_atr_lp_al_double[service_pair]
                    if w == full_pair_first_member[service_pair]
                    else full_atr_al_llupper_double[service_pair]
                )
                model.addCons(
                    selector <= 1 - holding_selector,
                    name=f"atr_return_not_while_holding_pair_{p}_{w}",
                )
                # ATR is at AL after the LP drop-off. To recover a wafer from
                # LLlower during this calibration window it must first move
                # empty AL->LL, perform the loaded LL->LP return, and then
                # move empty LP->AL before the calibrated wafer is picked up.
                model.addCons(
                    return_start
                    >= prod_stage_end[(w, "atr_lp_al")]
                    + cfg.atr_transfer_time
                    - big_m * (1 - selector),
                    name=f"atr_return_al_window_start_{p}_{w}",
                )
                model.addCons(
                    return_end
                    <= prod_stage_start[(w, "atr_al_llupper")]
                    - cfg.atr_transfer_time
                    + big_m * (1 - selector),
                    name=f"atr_return_al_window_end_{p}_{w}",
                )
            model.addCons(
                scip.quicksum(return_windows) + return_after_all_al == 1,
                name=f"atr_return_window_once_{p}",
            )
            model.addCons(
                return_start
                >= last_al_service_end - big_m * (1 - return_after_all_al),
                name=f"atr_return_after_all_al_lb_{p}",
            )
    else:
        # In mixed production, both 4x1 and 2x2 product pairs use the same
        # physical two-gripper ATR behavior. Represent a complete pair's
        # LP->AL, serial AL service, and AL->LL handoff as one non-preemptive
        # robot action so a synchronized double move is not mistaken for two
        # overlapping single-wafer tasks by the unary ATR resource.
        atr_resource_tasks = []

        def append_pair_al_services(mode_prefix, pair_ids, pair_members, input_double_by_pair):
            for p in pair_ids:
                members = sorted(pair_members[p])
                if not members:
                    continue
                first = members[0]
                last = members[-1]
                service_name = f"{mode_prefix}_al_service_{p}"
                atr_task_locations[service_name] = ("LP", "LL")
                atr_resource_tasks.append(
                    (
                        service_name,
                        prod_stage_start[(first, "atr_lp_al")],
                        prod_stage_end[(last, "atr_al_llupper")],
                        None,
                    )
                )
                if len(members) == 2:
                    second = members[1]
                    model.addCons(
                        prod_stage_start[(second, "atr_lp_al")]
                        >= prod_stage_end[(first, "atr_al_llupper")]
                        - big_m * input_double_by_pair[p],
                        name=f"{mode_prefix}_atr_al_service_single_pair_order_{p}",
                    )

        append_pair_al_services("full", full_pair_ids, full_pair_members, full_atr_lp_al_double)
        append_pair_al_services("mix", mix_pair_ids, mix_pair_members, mix_atr_lp_al_double)

        full_atr_return_actions = full_pair_robot_actions(
            "atr",
            (("lllower_lp", "atr_lllower_lp", full_atr_return_double),),
        )
        for p in full_pair_ids:
            action_name, action_start, action_end = full_atr_return_actions[("lllower_lp", p)]
            atr_task_locations[action_name] = ("LL", "LP")
            atr_resource_tasks.append((action_name, action_start, action_end, None))

        mix_atr_return_actions = mix_pair_robot_actions(
            "atr",
            (("lllower_lp", "atr_lllower_lp", mix_atr_return_double),),
        )
        for p in mix_pair_ids:
            action_name, action_start, action_end = mix_atr_return_actions[("lllower_lp", p)]
            atr_task_locations[action_name] = ("LL", "LP")
            atr_resource_tasks.append((action_name, action_start, action_end, None))
        _add_unary_resource_no_overlap(
            model,
            atr_resource_tasks,
            big_m,
            "seq_atr_action",
            transition_time=atr_empty_transition,
        )
    # AL is one physical calibration slot in every operating mode.
    if pure_full_mode:
        al_wafers = [
            w
            for p in full_pair_ids
            for w in sorted(full_pair_members[p])
        ]
        for left, right in zip(al_wafers, al_wafers[1:]):
            model.addCons(
                prod_stage_start[(right, "al")] >= prod_stage_end[(left, "al")],
                name=f"al_single_slot_{left}_{right}",
            )
    else:
        _add_parallel_slot_resource(model, al_tasks, 1, big_m, "al_slot_assign", "seq_al")
    # For a pure 4x1 workload, each PW pair uses the two LL slots in a known
    # front/back handoff pattern.  Make that physical pattern explicit as two
    # canonical slot chains instead of enumerating interchangeable LL-slot
    # colors and pairwise order binaries.
    if pure_full_mode:
        full_member_slot = {}
        for p in full_pair_ids:
            for slot_index, w in enumerate(sorted(full_pair_members[p])):
                full_member_slot[w] = slot_index

        upper_pair_order = list(full_pair_ids)
        lower_pair_order = sorted(
            full_pair_ids,
            key=lambda p: (
                canonical_full_slot_by_pair[p][1],
                canonical_full_slot_by_pair[p][0],
                -canonical_full_slot_by_pair[p][2],
            ),
        )
        for slot_index in range(2):
            upper_wafers = [
                w
                for p in upper_pair_order
                for w in sorted(full_pair_members[p])
                if full_member_slot[w] == slot_index
            ]
            lower_wafers = [
                w
                for p in lower_pair_order
                for w in sorted(full_pair_members[p])
                if full_member_slot[w] == slot_index
            ]
            for left, right in zip(upper_wafers, upper_wafers[1:]):
                model.addCons(
                    prod_stage_end[(right, "atr_al_llupper")] - cfg.atr_load_unload_time
                    >= prod_stage_end[(left, "vtr_load")] + cfg.llupper_time,
                    name=f"llupper_canonical_slot_{slot_index + 1}_{left}_{right}",
                )
            for left, right in zip(lower_wafers, lower_wafers[1:]):
                model.addCons(
                    prod_stage_start[(right, "vtr_unload")]
                    >= prod_stage_start[(left, "atr_lllower_lp")]
                    + cfg.atr_load_unload_time
                    + cfg.lllower_time,
                    name=f"lllower_canonical_slot_{slot_index + 1}_{left}_{right}",
                )
    else:
        _add_parallel_slot_resource(model, llupper_tasks, 2, big_m, "llupper_slot_assign", "seq_llupper")
        _add_parallel_slot_resource(model, lllower_tasks, 2, big_m, "lllower_slot_assign", "seq_lllower")
    # VTR follows the same steady cycle.  After both PMs receive their first
    # batch, each chamber releases its completed back/front pair and is loaded
    # with its own next batch before the robot proceeds to the other chamber.
    # This preserves one physical VTR path while keeping both PMs productive.
    if pure_full_mode and len(full_batches) <= cfg.cleaning_interval:
        vtr_actions = full_pair_robot_actions(
            "vtr",
            (
                ("load", "vtr_load", full_vtr_load_double),
                ("unload", "vtr_unload", full_vtr_unload_double),
            ),
            {
                "load": {
                    p: (full_pair_vtr_load_start[p], full_pair_vtr_load_end[p])
                    for p in full_pair_ids
                },
                "unload": {
                    p: (full_pair_vtr_unload_start[p], full_pair_vtr_unload_end[p])
                    for p in full_pair_ids
                },
            },
        )
        vtr_action_chain = []
        first_batch = full_batches[0]
        final_batch = full_batches[-1]

        def append_vtr_side(route_name, m, b, side):
            pair_id = pair_at_slot(m, b, side)
            if pair_id is not None:
                action = vtr_actions[(route_name, pair_id)]
                vtr_action_chain.append(action)
                vtr_task_locations[action[0]] = (
                    ("LLupper", f"CH{m}")
                    if route_name == "load"
                    else (f"CH{m}", "LLlower")
                )
                return
            if not any(pair_at_slot(m, b, s) is not None for s in full_sides):
                return
            side_name = "front" if side == 1 else "back"
            if route_name == "load":
                vtr_action_chain.append(
                    (
                        f"full_{side_name}_load_{m}_{b}",
                        full_front_load_start[(m, b)] if side == 1 else full_back_load_start[(m, b)],
                        full_front_load_end[(m, b)] if side == 1 else full_back_load_end[(m, b)],
                    )
                )
            else:
                vtr_action_chain.append(
                    (
                        f"full_{side_name}_unload_{m}_{b}",
                        full_front_unload_start[(m, b)] if side == 1 else full_back_unload_start[(m, b)],
                        full_front_unload_end[(m, b)] if side == 1 else full_back_unload_end[(m, b)],
                    )
                )

        for b in full_batches:
            for m in pm_ids:
                if b != first_batch:
                    append_vtr_side("unload", m, b - 1, 2)
                    append_vtr_side("unload", m, b - 1, 1)
                append_vtr_side("load", m, b, 1)
                append_vtr_side("load", m, b, 2)
        for m in pm_ids:
            append_vtr_side("unload", m, final_batch, 2)
            append_vtr_side("unload", m, final_batch, 1)
        add_robot_action_chain(
            "vtr",
            vtr_action_chain,
            transition_time=lambda left, right: vtr_empty_transition(left[0], right[0]),
        )
    else:
        _add_unary_resource_no_overlap(
            model,
            vtr_tasks,
            big_m,
            "seq_vtr_action",
            transition_time=vtr_empty_transition,
        )

    for m in pm_ids:
        full_idle_expr = scip.quicksum(
            full_front_unload_end[(m, b)]
            - full_front_load_start[(m, b)]
            - cfg.full_process_time * full_batch_used[(m, b)]
            for b in full_batches
        )
        mix_idle_expr = scip.quicksum(
            mix_tail_end[(m, segment["id"])]
            - mix_head_start[(m, segment["id"])]
            - scip.quicksum(
                mix_cycle_end[(m, c)] - mix_cycle_start[(m, c)]
                for c in segment["cycles"]
            )
            for segment in cleaning_layout[m]["segments"]
        )
        clean_idle_expr = scip.quicksum(
            clean_front_unload_end[(m, clean_slot)]
            - clean_front_load_start[(m, clean_slot)]
            - (clean_end[(m, clean_slot)] - clean_start[(m, clean_slot)])
            for clean_slot in clean_slots
        )
        model.addCons(
            chamber_idle_total[m] == full_idle_expr + mix_idle_expr + clean_idle_expr,
            name=f"chamber_idle_total_def_{m}",
        )
        for b in full_batches:
            add_chamber_nonprocess_square_term(
                m,
                full_front_unload_end[(m, b)]
                - full_front_load_start[(m, b)]
                - cfg.full_process_time * full_batch_used[(m, b)],
                full_batch_used[(m, b)],
                f"full_{m}_{b}",
            )
        for segment in cleaning_layout[m]["segments"]:
            segment_id = segment["id"]
            first_cycle = segment["cycles"][0]
            last_cycle = segment["cycles"][-1]
            add_chamber_nonprocess_square_term(
                m,
                mix_cycle_start[(m, first_cycle)] - mix_head_start[(m, segment_id)],
                mix_active[m],
                f"mix_head_{m}_{segment_id}",
            )
            add_chamber_nonprocess_square_term(
                m,
                mix_tail_end[(m, segment_id)] - mix_cycle_end[(m, last_cycle)],
                mix_active[m],
                f"mix_tail_{m}_{segment_id}",
            )
        for c in mix_cycles[1:]:
            if mix_bridge_active[(m, c)]:
                add_chamber_nonprocess_square_term(
                    m,
                    mix_cycle_start[(m, c)] - mix_cycle_end[(m, c - 1)],
                    mix_active[m],
                    f"mix_bridge_{m}_{c}",
                )
        for clean_slot in clean_slots:
            add_chamber_nonprocess_square_term(
                m,
                clean_front_unload_end[(m, clean_slot)]
                - clean_front_load_start[(m, clean_slot)]
                - (clean_end[(m, clean_slot)] - clean_start[(m, clean_slot)]),
                clean_active[(m, clean_slot)],
                f"clean_{m}_{clean_slot}",
            )
        model.addCons(
            chamber_nonprocess_wait_square[m] == scip.quicksum(chamber_nonprocess_wait_square_terms[m]),
            name=f"chamber_nonprocess_wait_square_def_{m}",
        )

    if cfg.max_schedule_wait_time > 0:
        wait_cap = float(cfg.max_schedule_wait_time)
        capped_waits = (
            list(llupper_wait.values())
            + list(lllower_wait.values())
            + list(full_pair_post_process_wait.values())
            + list(mix_pair_post_process_wait.values())
            + chamber_idle_slacks
            + chamber_nonprocess_wait_terms
        )
        for variable in capped_waits:
            model.addCons(
                variable <= wait_cap,
                name=f"schedule_wait_cap_{variable.name}",
            )

    c_max = model.addVar(vtype="C", lb=0.0, name="c_max")
    for w in product_wafers:
        model.addCons(c_max >= wafer_completion[w], name=f"makespan_lb_{w}")

    # The generated LP has a pure makespan objective: minimizing c_max is
    # exactly maximizing WPH for a fixed wafer count. The runner may then fix
    # c_max to either the proven optimum or the current incumbent and compact
    # that schedule in a bounded second phase. Keeping this score explicit in
    # the LP makes both objectives auditable in a saved solution.
    # Strict secondary objective: after phase 1 fixes Cmax, minimize the sum
    # of squared waiting intervals over every chamber and every product path.
    # This is lexicographic rather than a fragile weighted blend, so no amount
    # of wait reduction is allowed to worsen WPH/makespan.
    wait_square_terms = [
        square
        for m in pm_ids
        for square in chamber_nonprocess_wait_square_terms[m]
    ]

    def add_wait_square(wait_expr, name: str) -> None:
        wait = model.addVar(vtype="C", lb=0.0, name=f"schedule_wait_{name}")
        square = model.addVar(vtype="C", lb=0.0, name=f"schedule_wait_square_{name}")
        model.addCons(wait == wait_expr, name=f"schedule_wait_def_{name}")
        if cfg.max_schedule_wait_time > 0:
            model.addCons(
                wait <= float(cfg.max_schedule_wait_time),
                name=f"schedule_wait_cap_{wait.name}",
            )
        model.addCons(square >= wait * wait, name=f"schedule_wait_square_def_{name}")
        wait_square_terms.append(square)

    for w in product_wafers:
        # Chamber/module queueing before and after processing and LL service.
        add_wait_square(
            prod_stage_start[(w, "pm")] - prod_stage_end[(w, "vtr_load")],
            f"pm_before_{w}",
        )
        add_wait_square(
            prod_stage_start[(w, "vtr_unload")] - prod_stage_end[(w, "pm")],
            f"pm_after_{w}",
        )
        add_wait_square(
            prod_stage_start[(w, "al")] - prod_stage_end[(w, "atr_lp_al")],
            f"al_before_{w}",
        )
        add_wait_square(
            prod_stage_start[(w, "atr_al_llupper")] - prod_stage_end[(w, "al")],
            f"al_after_{w}",
        )
        add_wait_square(llupper_wait[w], f"llupper_{w}")
        add_wait_square(lllower_wait[w], f"lllower_{w}")

        # ATR holding and excess loaded-action duration; VTR uses the same
        # exact-duration check. These terms cover robot-side waiting without
        # introducing an artificial preference for early absolute timestamps.
        add_wait_square(
            prod_stage_end[(w, "atr_hold_before_al")]
            - prod_stage_start[(w, "atr_hold_before_al")],
            f"atr_hold_before_al_{w}",
        )
        add_wait_square(
            prod_stage_end[(w, "atr_hold_after_al")]
            - prod_stage_start[(w, "atr_hold_after_al")],
            f"atr_hold_after_al_{w}",
        )
        for stage, minimum_duration in (
            ("atr_lp_al", cfg.atr_lp_al_total_time),
            ("atr_al_llupper", cfg.atr_al_llupper_total_time),
            ("vtr_load", cfg.pair_transfer_time),
            ("vtr_unload", cfg.pair_transfer_time),
            ("atr_lllower_lp", cfg.atr_lllower_lp_total_time),
        ):
            add_wait_square(
                prod_stage_end[(w, stage)]
                - prod_stage_start[(w, stage)]
                - minimum_duration,
                f"{stage}_excess_{w}",
            )

    stability_expr = scip.quicksum(wait_square_terms)
    schedule_stability = model.addVar(vtype="C", lb=0.0, name="schedule_stability")
    model.addCons(
        schedule_stability == stability_expr,
        name="schedule_stability_def",
    )
    model.setObjective(c_max, "minimize")
    return model


def get_petri_model_description_path(output_dir: str, instance_name: str) -> str:
    stem, _ = os.path.splitext(instance_name)
    return os.path.join(output_dir, f"{stem}_model.md")


def _build_pair_slot_summary(mode_label: str, wafer_ids: List[int], pair_loads: Dict[int, int]) -> str:
    if not pair_loads:
        return f"- `{mode_label}` PW pairs: none"
    lines = [
        f"- `{mode_label}` product wafers: {len(wafer_ids)} ({_format_wafer_ids(wafer_ids)})",
        f"- `{mode_label}` PW pair slots: {len(pair_loads)}",
    ]
    for pair_id, load in pair_loads.items():
        if load == 2:
            lines.append(f"  - Pair {pair_id}: 2 product wafers")
        else:
            lines.append(f"  - Pair {pair_id}: 1 product wafer + 1 PEC wafer")
    return "\n".join(lines)


def _build_model_description(instance_name: str, cfg: PetriMIPConfig) -> str:
    chamber_labels = ", ".join(f"CH{pm_id}" for pm_id in cfg.pm_ids)
    product_modes = cfg.product_wafer_modes
    embedded_pec = sum(2 - load for load in cfg.full_pair_product_loads.values()) + sum(
        2 - load for load in cfg.mix_pair_product_loads.values()
    )
    return f"""# Dual-Source Mixed-Flow Full-Flow MIP

This file documents the exact full-flow MIP generated for `{instance_name}`.

## Device Scope

The model follows the dual-source rotary semiconductor cluster tool described in the supplied device brief:

- load ports: `LP1`-`LP{cfg.load_ports}`, capacity `{cfg.load_port_slots}` each
- atmospheric side: `ATR`, `AL`, `LLupper`
- vacuum side: `VTR`, `LLlower`, shared rotary chambers `{chamber_labels}`
- PEC side: `PEC storage`, capacity `{cfg.pec_storage_slots}` slots, `{cfg.pec_pool_size}` reusable PEC wafers, split into `{cfg.pec_pool_size // len(cfg.pm_ids)}` chamber-bound tokens per CH
- product flow: `LP -> ATR -> AL -> ATR -> LLupper -> VTR -> CH -> VTR -> LLlower -> ATR -> LP`
- PEC flow: `PEC storage -> VTR -> CH -> VTR -> PEC storage`

## What Is New In This Version

Compared with the previous chamber-level MIP, this version explicitly schedules:

1. when each product wafer is moved by `ATR`
2. when each product wafer occupies `AL`
3. when each product wafer occupies `LLupper` and `LLlower`
4. when each chamber transfer task uses `VTR`
5. when each PEC wafer leaves storage, enters a chamber, and returns to storage
6. when each CH performs mandatory pure-PEC cleaning after a configurable number of full-chamber process cycles
7. the final return time of every product wafer back to `LP`

The objective keeps the true end-to-end makespan and adds secondary penalties for balance,
chamber compactness, post-process unload waiting, and squared CH non-process residence.
Schedule-wait penalties are computed in the A3C reward after a feasible solution is obtained.

## Product Input Semantics

- process mode policy: `{_normalize_process_mode(cfg.process_mode)}`
- `4x1` wafers: `{len(cfg.full_wafer_ids)}`
- `2x2` wafers: `{len(cfg.mix_wafer_ids)}`
- total product wafers: `{cfg.total_product_wafers}`
- wafer-level modes: `{_format_wafer_mode_summary(product_modes)}`

Per-mode PW-pair formation:

{_build_pair_slot_summary(MODE_FULL, cfg.full_wafer_ids, cfg.full_pair_product_loads)}
{_build_pair_slot_summary(MODE_MIX, cfg.mix_wafer_ids, cfg.mix_pair_product_loads)}

Embedded PEC wafers forced by odd product counts: `{embedded_pec}`.

## Core Scheduling Semantics

- `4x1`: each chamber batch has two physical side slots. Side 1 is loaded first and unloaded last; side 2 is loaded second and unloaded first.
- an active `4x1` batch fills both side slots. If only one product-carrying PW pair is assigned, the other side is forced to a pure `PEC+PEC` filler pair.
- per chamber, `4x1` batches form one serial block by batch index; batch `b+1` can start only after batch `b` has fully unloaded.
- a pure `PEC+PEC` filler side is allowed only on the tail `4x1` batch of a chamber sequence. Earlier active `4x1` batches must carry two product PW pairs.
- `2x2`: product PW pairs form ordered PEC-bounded segments on a chamber. Within each segment, a product pair is processed in two adjacent cycles: first with the preceding product pair (or head PEC), then with the following product pair (or tail PEC).
- if the next `2x2` exposure reaches the cleaning interval, the preceding bridge loads tail PEC instead of the next product pair. After that exposure, the remaining product pair is removed/replaced by PEC, the chamber cleans, and the next segment restarts with head PEC plus the next product pair.
- per chamber, every active `4x1` batch must finish before that chamber's `2x2` block begins, matching the disclosure rule that `4x1` is completed before `2x2`.
- for every `4x1` batch, PM processing starts exactly when the second side finishes loading, so a full chamber cannot wait before processing (`full_start == full_back_load_end`).
- downstream stages may wait, but they cannot start before the required transfer or process has finished. Every complete two-product PW pair uses ATR double-gripper transfer in pure and mixed production alike, while the two AL calibrations remain serial because AL has one physical slot. Between them, ATR explicitly picks the calibrated wafer and places the held companion into AL; this exchange is not a zero-time or double-place operation. An odd one-product tail pair remains a single-gripper action.
- `ATR` and `VTR` each represent one physical robot. Their capacities describe how many wafers an atomic transfer can carry; they do not permit independent moves on different routes at the same time. Every ATR loaded transfer consists of load, route movement, and unload. Between consecutive ATR actions, the model inserts the empty movement required from the previous destination to the next source; in particular, `LL->LP` empty return takes two `LP->AL` route movements.
- ATR has a two-gripper payload, while AL has one physical slot. Every complete two-product PW pair in `4x1`, `2x2`, or mixed production uses one shared `LP->AL` move, a single-wafer AL placement, serial calibration with an explicit AL wafer exchange while ATR retains the companion, one shared `AL->LLupper` move, and a shared `LLlower->LP` return. All ATR routes remain globally non-overlapping.
- VTR `front/back load/unload` and `2x2` head/bridge/tail actions carry a two-product PW pair as one double-gripper action when both members are product wafers. Every loaded VTR action has exact duration `{cfg.pair_transfer_time:.1f}`. If one action's destination differs from the next action's source, an explicit `{cfg.pair_transfer_time:.1f}` empty reposition is required; for example, consecutive `LLupper->CH2` loads contain a `CH2->LLupper` return between them. Robot idle time carries no wafer and is not a VTR wait.
- For a pure `4x1` input, product wafers and PW pairs are indistinguishable apart from their identifiers. The model uses one canonical pairing and batch placement, then writes the implied ATR action chain, VTR action chain, and two LL slot chains directly. This removes label symmetry while retaining synchronized pair-transfer stages and serial AL calibration.
- chamber compactness slack measures avoidable gaps between adjacent `4x1` batches, between the tail `4x1` batch and the `2x2` block, and before `2x2` bridge/tail transfer actions. After a `2x2` head or bridge transfer has filled the chamber, the following exposure starts immediately by hard equality. In addition, every CH window that contains wafers but is not running a process recipe contributes a separate squared term to `chamber_nonprocess_wait_square_*`.
- product wafers inherit chamber transfer/process timing from the PW pair to which they belong.
- `AL` has one physical calibration slot. Calibration starts exactly after each wafer's physical AL placement. For a shared pair route, ATR single-places wafer 1, calibrates it, performs `pick wafer 1 + place wafer 2`, calibrates wafer 2, and single-picks wafer 2 before carrying the pair to LLupper. The companion and calibrated-wafer waits are ATR holding intervals rather than AL queueing.
- `LLupper` and `LLlower` are independent two-slot physical modules, and each slot has an independent pressure state.
  An `LLupper` slot executes ATR placement in atmosphere, pump-down, VTR pickup in vacuum, and vent-back to atmosphere.
  An `LLlower` slot executes VTR placement in vacuum, venting, ATR pickup in atmosphere, and pump-back to vacuum.
  Slot reuse is forbidden until that slot has completed its reset transition; the other slot and the other LL remain independent.
  Excess ready-state waiting before outbound pickup is included in the secondary objective. When a pair route selects its
  double-gripper variable, the two wafers enter or leave synchronously on two independent slots.
- PEC wafers are modeled as reusable, chamber-bound tokens. Each active PEC job occupies exactly one token from its assigned chamber's PEC subset, from `vtr_load` start until `vtr_unload` end.
- chamber cleaning is modeled as a pure `PEC+PEC` / `PEC+PEC` rotary batch. It uses the same VTR load/unload and chamber rotation semantics as `4x1`, occupies four PEC tokens, and adds a cleaning process interval.
- per chamber, process epochs are separated by cleaning batches so that each epoch contains at most `{cfg.cleaning_interval}` full-chamber process cycles. A long `2x2` workload is split at an exposure boundary with PEC tail/head pairs; it no longer has to fit in one cleaning epoch.

## Resource Constraints Added Explicitly

- `ATR`: one physical two-gripper robot for `LP->AL`, `AL->LLupper`, and `LLlower->LP`; each loaded action is `load ({cfg.atr_load_unload_time:.1f}) + move + unload ({cfg.atr_load_unload_time:.1f})`, and empty repositioning is explicitly sequenced
- `AL`: one physical calibration slot; pair service uses single-wafer placement/pickup and an explicit `{cfg.al_exchange_time:.1f}`-time wafer exchange between serial calibrations
- `LLupper`: 2 independent stateful slots; atmosphere ATR access -> pump-down -> vacuum VTR access -> vent reset
- `LLlower`: 2 independent stateful slots; vacuum VTR access -> vent -> atmosphere ATR access -> pump reset
- `VTR`: one physical four-gripper robot with payload capacity `{cfg.vtr_capacity}`; loaded actions include pickup, route movement, and placement, while endpoint-aware empty repositioning is sequenced separately
- `CH2`, `CH3`: chamber-internal sequence constraints for `4x1` slots, one contiguous `2x2` block, and pure-PEC cleaning windows

## Timing Parameters

- Big-M: `{cfg.big_m:.1f}`
- chamber transfer gap: `{cfg.pm_transfer_gap:.1f}`
- chamber `180°` rotation time: `{cfg.pm_rotation_time_180:.1f}`
- VTR load/unload time: `{cfg.pair_transfer_time:.1f}`
- VTR empty reposition time between different endpoints: `{cfg.pair_transfer_time:.1f}`
- ATR load/unload time: `{cfg.atr_load_unload_time:.1f}` (equal to VTR load/unload time)
- ATR LP->AL / AL->LLupper route movement time: `{cfg.atr_transfer_time:.1f}`
- ATR loaded LP->AL total time: `{cfg.atr_lp_al_total_time:.1f}`
- ATR loaded AL->LLupper total time: `{cfg.atr_al_llupper_total_time:.1f}`
- ATR loaded LLlower->LP movement time: `{cfg.atr_return_time:.1f}`; total time: `{cfg.atr_lllower_lp_total_time:.1f}`
- ATR empty LL->LP return time: `{cfg.atr_empty_ll_to_lp_time:.1f}`
- ATR AL pair exchange time: `{cfg.al_exchange_time:.1f}` (`pick calibrated + place companion`)
- ATR wafer capacity: `{cfg.atr_capacity}`
- VTR wafer capacity: `{cfg.vtr_capacity}`
- aligner minimum occupancy: `{cfg.aligner_time:.1f}`
- LLupper per-slot pump/reset transition: `{cfg.llupper_time:.1f}`
- LLlower per-slot vent/reset transition: `{cfg.lllower_time:.1f}`
- `4x1` process time: `{cfg.full_process_time:.1f}`
- `2x2` process time for each first/second exposure: `{cfg.mix_process_time:.1f}`
- cleaning interval: `{cfg.cleaning_interval}` full-chamber process cycles
- cleaning process time: `{cfg.effective_cleaning_process_time:.1f}`
- max module residency time: `{cfg.max_module_residency_time:.1f}`
- max robot residency time: `{cfg.max_robot_residency_time:.1f}`
- maximum individual avoidable schedule wait: `{cfg.max_schedule_wait_time:.1f}` (`0` disables the hard cap)
- secondary stability score: normalized weighted sum of PM imbalance, avoidable chamber gaps,
  squared CH non-process wafer residence, post-process wait, and excess LL wait
  (evaluated after fixing either the optimal or incumbent WPH)

## Main Variable Families

- `wafer_to_full_pair_*`, `wafer_to_mix_pair_*`: product wafer to PW-pair assignment
- `assign_full_*`, `assign_mix_*`: PW-pair to `4x1` batch-side / `2x2` chain-position assignment
- `full_batch_used_*`, `full_filler_side_*`, `full_batch_tail_*`
- `full_front_load_*`, `full_back_load_*`, `full_back_unload_*`, `full_front_unload_*`
- `mix_pos_used_*`, `mix_cycle_used_*`, `mix_active_*`, `mix_last_cycle_*`, `mix_last_pos_*`
- `clean_active_*`, `clean_front_load_*`, `clean_back_load_*`, `clean_*`, `clean_back_unload_*`, `clean_front_unload_*`
- `full_batch_idle_*`, `full_to_mix_idle_*`, `mix_*_idle_*`: soft compactness slacks for avoidable chamber gaps
- `full_pair_post_process_wait_*`, `mix_pair_post_process_wait_*`: product PW-pair wait from PM process end to unload start
- `llupper_wait_*`, `lllower_wait_*`: excess product-wafer waiting after the mandatory LL dwell and before outbound robot pickup
- `full_atr_*_double_*`, `full_vtr_*_double_*`, `mix_atr_*_double_*`, `mix_vtr_*_double_*`: per-PW-pair selection of single- or double-gripper action on the named robot route; `*_atr_al_llupper_double_*` can be `1` only when the corresponding `*_atr_lp_al_double_*` is `1`
- `chamber_idle_total_*`: total per-CH time that is neither processing nor cleaning
- `chamber_nonprocess_wait_*`, `chamber_nonprocess_wait_square_*`: per-window non-process CH residence and its squared sum, used as a high-priority stability penalty
- `process_epoch_used_*`, `full_batch_epoch_*`, `mix_block_epoch_*`, `mix_cycle_epoch_*`: the canonical cleaning-separated process epochs (`mix_block_epoch` marks every epoch containing a 2x2 segment)
- `prod_stage_start_*`, `prod_stage_end_*`: full product-wafer path stages, including `atr_hold_before_al`, `atr_al_exchange`, and `atr_hold_after_al` across serial single-slot AL calibration
- `full_side_llupper_release_*`, `full_side_lllower_release_*`: 4x1 front/back LL release-time envelopes, used only to
  enforce physical two-slot handoff order
- `pec_stage_start_*`, `pec_stage_end_*`: PEC circulation stages
- `pec_token_assign_*`: reusable PEC token assignment
- `atr_pair_action_start/end_*`, `atr_mix_pair_action_start/end_*`, `vtr_pair_action_start/end_*`: one PW pair's non-preemptive ATR/VTR action envelope; a double action has one shared transfer window, while two single actions are consecutive within this envelope
- `atr_al_service_physical_action_order_*`: pure-4x1 AL service order; a PW pair may share LP pickup, but its two wafers always enter the one-slot AL and calibrate one after the other
- `atr_return_during_al_*`, `atr_return_after_all_al_*`: legacy pure-4x1 ATR-return window selectors. They are emitted only when `use_legacy_pure_full_atr_chain=True`; the default uses `seq_atr_action_*` for pure 4x1 as well.
- `vtr_physical_action_order_*`: pure-4x1 continuous VTR cycle, which loads the next PM batch without waiting for an entire four-wafer batch to return to LP
- `seq_atr_action_*`, `seq_vtr_action_*`: generic mixed-mode ATR/VTR non-overlap ordering with endpoint-aware empty reposition times, used when the pure-4x1 continuous cycle is not applicable
- `llupper_slot_assign_*`, `lllower_slot_assign_*`: LL slot occupancy assignment
- `wafer_completion_*`: auxiliary terminal timestamp linking each product wafer's LP return to the makespan; it is
  not separately summed in the objective
- `c_max`: end-to-end makespan
- `schedule_wait_*`, `schedule_wait_square_*`: chamber/module/ATR/VTR/LL waiting intervals and their squared values;
- `schedule_stability`: sum of all chamber and robot waiting-time squares, minimized only after `c_max` is fixed;
  it is optimized only after the optimal `c_max` is fixed

## Objective

The primary LP objective is `min c_max`; for a fixed wafer count, this is exactly
`max WPH`. The runner then fixes `c_max` to the primary optimum when proven, or to
the current feasible incumbent when a resource limit interrupts phase one, and
minimizes `schedule_stability` only within the configured secondary time/node
budget. Thus a visually smoother Gantt chart can never be bought by reducing the
reported WPH. `wafer_completion_*` only defines lower bounds of `c_max`.

## Output Files

- LP model: `{instance_name}`
- Model description: `{os.path.basename(get_petri_model_description_path('', instance_name))}`
"""


def _write_model_description(output_dir: str, instance_name: str, cfg: PetriMIPConfig) -> str:
    description_path = get_petri_model_description_path(output_dir, instance_name)
    with open(description_path, "w", encoding="utf-8") as handle:
        handle.write(_build_model_description(instance_name, cfg))
    return description_path


def generate_petri_mip_instance(
    output_dir: str,
    instance_name: str,
    cfg: PetriMIPConfig,
    warm_start_time_limit: float = 180.0,
    require_warm_start: bool = True,
) -> str:
    """Generate an LP and, for mixed flows, its compatible primal warm start.

    The warm start is cached beside the LP and tagged with the LP SHA-256, so
    stale starts are never reused after an instance is regenerated.
    """
    output_dir = str(resolve_path(output_dir))
    os.makedirs(output_dir, exist_ok=True)
    dated_instance_name = append_date_to_filename(instance_name)
    lp_path = os.path.join(output_dir, dated_instance_name)
    model = build_petri_mip_model(cfg)
    model.writeProblem(lp_path)
    _write_model_description(output_dir, dated_instance_name, cfg)

    if cfg.mix_wafer_ids and float(warm_start_time_limit) > 0:
        try:
            # Import lazily: petri_warm_start imports this generator module.
            from petri_warm_start import (
                find_compatible_mixed_warm_start,
                polish_mixed_warm_start,
                write_mixed_warm_start,
            )

            warm_start = find_compatible_mixed_warm_start(
                output_dir,
                dated_instance_name,
            )
            if warm_start:
                print(f"reusing compatible Petri warm start: {warm_start}")
            else:
                warm_start = write_mixed_warm_start(
                    output_dir,
                    dated_instance_name,
                    cfg,
                    time_limit=float(warm_start_time_limit),
                )
                if warm_start:
                    print(f"generated Petri warm start: {warm_start}")
                else:
                    message = (
                        "LP was generated, but no compatible Petri warm start "
                        f"was found within {float(warm_start_time_limit):.0f}s"
                    )
                    if require_warm_start:
                        raise RuntimeError(message)
                    print(f"warning: {message}")
            if warm_start:
                polish_budget = min(
                    1800.0,
                    max(60.0, 0.20 * float(warm_start_time_limit)),
                )
                polished_start = polish_mixed_warm_start(
                    output_dir,
                    dated_instance_name,
                    cfg,
                    time_limit=polish_budget,
                )
                if not polished_start:
                    message = "compatible Petri warm start could not be schedule-polished"
                    if require_warm_start:
                        raise RuntimeError(message)
                    print(f"warning: {message}")
                else:
                    warm_start = polished_start
                    print(f"polished Petri warm start: {warm_start}")
        except Exception as exc:
            if require_warm_start:
                raise RuntimeError(
                    f"LP was generated, but required warm-start generation failed: {exc}"
                ) from exc
            print(f"warning: LP was generated, but warm-start generation failed: {exc}")
    return lp_path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate the dual-source mixed-flow semiconductor cluster full-flow MIP."
    )
    parser.add_argument("--output_dir", type=str, default="generated_instances/petri")
    parser.add_argument("--instance_name", type=str, default="petri_batch10_fullflow_v7.lp")
    parser.add_argument(
        "--warm_start_time_limit",
        type=float,
        default=180.0,
        help="Seconds used to build a compatible mixed-flow warm start; 0 disables it.",
    )
    parser.add_argument(
        "--allow_missing_warm_start",
        action="store_true",
        help="Allow mixed LP generation to succeed without a verified warm-start file.",
    )
    parser.add_argument("--num_batches", type=int, default=10)
    parser.add_argument("--num_pm", type=int, default=2)
    parser.add_argument("--num_steps", type=int, default=13)
    parser.add_argument("--total_wafers", type=int, default=0)
    parser.add_argument("--mode_4x1_wafers", "--full_mode_wafers", dest="mode_4x1_wafers", type=int, default=10)
    parser.add_argument("--mode_2x2_wafers", "--mix_mode_wafers", dest="mode_2x2_wafers", type=int, default=10)
    parser.add_argument("--pec_pool_size", type=int, default=8)
    parser.add_argument("--batch_size", type=int, default=4)
    parser.add_argument("--big_m", type=float, default=10000.0)
    parser.add_argument("--pm_transfer_gap", type=float, default=1.0)
    parser.add_argument("--pm_rotation_time_180", type=float, default=2.0)
    parser.add_argument("--pair_transfer_time", type=float, default=4.0)
    parser.add_argument("--atr_transfer_time", type=float, default=3.0)
    parser.add_argument("--atr_return_time", type=float, default=3.0)
    parser.add_argument("--atr_capacity", type=int, default=2)
    parser.add_argument("--vtr_capacity", type=int, default=4)
    parser.add_argument("--aligner_time", type=float, default=20.0)
    parser.add_argument("--llupper_time", type=float, default=30.0)
    parser.add_argument("--lllower_time", type=float, default=25.0)
    parser.add_argument("--full_process_time", type=float, default=80.0)
    parser.add_argument(
        "--mix_boundary_process_time",
        type=float,
        default=30.0,
        help="2x2 process duration; must equal --mix_internal_process_time.",
    )
    parser.add_argument(
        "--mix_internal_process_time",
        type=float,
        default=30.0,
        help="Legacy 2x2 duration alias; must equal --mix_boundary_process_time.",
    )
    parser.add_argument("--cleaning_interval", type=int, default=10)
    parser.add_argument("--cleaning_process_time", type=float, default=0.0)
    parser.add_argument("--max_module_residency_time", type=float, default=10000.0)
    parser.add_argument("--max_robot_residency_time", type=float, default=10000.0)
    parser.add_argument(
        "--max_schedule_wait_time",
        type=float,
        default=0.0,
        help="Hard cap for each avoidable LL, post-process, bridge, and chamber wait; 0 disables it.",
    )
    parser.add_argument("--pm_balance_penalty", type=float, default=0.01)
    parser.add_argument(
        "--chamber_idle_penalty",
        type=float,
        default=1e-4,
        help="Secondary objective weight that compacts avoidable gaps between chamber processing groups.",
    )
    parser.add_argument(
        "--post_process_wait_penalty",
        type=float,
        default=0.05,
        help="Secondary objective weight for product PW-pair waiting from PM process end to VTR unload start.",
    )
    parser.add_argument(
        "--ll_wait_penalty",
        type=float,
        default=1e-4,
        help="Small secondary objective weight for excess waiting after the mandatory LL dwell time.",
    )
    parser.add_argument(
        "--chamber_nonprocess_wait_square_penalty",
        type=float,
        default=1e-2,
        help="High-priority secondary objective weight for per-window squared non-process wafer residence in CH modules.",
    )
    parser.add_argument(
        "--process_mode",
        type=str,
        default=PROCESS_MODE_AUTO,
        help="Mode policy: auto/counts, mixed/both, 4x1, 2x2, or custom/wafer-level.",
    )
    parser.add_argument("--mode_sequence", type=str, default="")
    parser.add_argument(
        "--wafer_mode_map",
        "--wafer_modes",
        dest="wafer_mode_map",
        type=str,
        default="",
        help="Sparse wafer-level overrides, e.g. W1:4x1,W3=2x2.",
    )
    parser.add_argument(
        "--default_wafer_mode",
        type=str,
        default="",
        help="Default mode for wafer ids not listed in --wafer_mode_map.",
    )

    args = parser.parse_args()

    cfg = PetriMIPConfig(
        num_batches=args.num_batches,
        num_pm=args.num_pm,
        num_steps=args.num_steps,
        total_wafers=args.total_wafers,
        pec_pool_size=args.pec_pool_size,
        batch_size=args.batch_size,
        big_m=args.big_m,
        pm_transfer_gap=args.pm_transfer_gap,
        pm_rotation_time_180=args.pm_rotation_time_180,
        pair_transfer_time=args.pair_transfer_time,
        atr_transfer_time=args.atr_transfer_time,
        atr_return_time=args.atr_return_time,
        atr_capacity=args.atr_capacity,
        vtr_capacity=args.vtr_capacity,
        aligner_time=args.aligner_time,
        llupper_time=args.llupper_time,
        lllower_time=args.lllower_time,
        full_process_time=args.full_process_time,
        mix_boundary_process_time=args.mix_boundary_process_time,
        mix_internal_process_time=args.mix_internal_process_time,
        cleaning_interval=args.cleaning_interval,
        cleaning_process_time=args.cleaning_process_time,
        max_module_residency_time=args.max_module_residency_time,
        max_robot_residency_time=args.max_robot_residency_time,
        max_schedule_wait_time=args.max_schedule_wait_time,
        pm_balance_penalty=args.pm_balance_penalty,
        chamber_idle_penalty=args.chamber_idle_penalty,
        post_process_wait_penalty=args.post_process_wait_penalty,
        ll_wait_penalty=args.ll_wait_penalty,
        chamber_nonprocess_wait_square_penalty=args.chamber_nonprocess_wait_square_penalty,
        process_mode=args.process_mode,
        mode_sequence=args.mode_sequence,
        wafer_mode_map=args.wafer_mode_map,
        default_wafer_mode=args.default_wafer_mode,
        full_mode_wafers=args.mode_4x1_wafers,
        mix_mode_wafers=args.mode_2x2_wafers,
    )
    lp_path = generate_petri_mip_instance(
        args.output_dir,
        args.instance_name,
        cfg,
        warm_start_time_limit=args.warm_start_time_limit,
        require_warm_start=not args.allow_missing_warm_start,
    )
    generated_instance_name = os.path.basename(lp_path)
    print(f"generated MIP instance: {lp_path}")
    print(
        "generated model description: "
        f"{get_petri_model_description_path(str(resolve_path(args.output_dir)), generated_instance_name)}"
    )


if __name__ == "__main__":
    main()

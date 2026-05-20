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
    aligner_time: float = 20.0
    llupper_time: float = 30.0
    lllower_time: float = 25.0
    full_process_time: float = 80.0
    mix_boundary_process_time: float = 30.0
    mix_internal_process_time: float = 30.0
    cleaning_interval: int = 10
    cleaning_process_time: float = 0.0
    max_module_residency_time: float = 10000.0
    max_robot_residency_time: float = 10000.0
    pm_balance_penalty: float = 0.01
    mode_sequence: str = ""
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
        explicit_count = self.full_mode_wafers + self.mix_mode_wafers
        if self.mode_sequence and self.mode_sequence.strip():
            modes = _parse_mode_sequence(self.total_wafers, self.mode_sequence)
            if explicit_count > 0 and len(modes) != explicit_count:
                raise ValueError(
                    "Explicit mode counts and mode_sequence disagree. "
                    f"Counts imply {explicit_count} wafers but mode_sequence resolves to {len(modes)}."
                )
            return modes
        if explicit_count <= 0:
            if self.total_wafers > 0:
                raise ValueError(
                    "Provide either explicit --mode_4x1_wafers / --mode_2x2_wafers counts "
                    "or a wafer-level mode_sequence. total_wafers alone is no longer sufficient."
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
        return self.num_mix_positions_per_pm + 1

    @property
    def max_chamber_processes_per_pm(self) -> int:
        return self.num_full_slots_per_pm + self.num_mix_cycles_per_pm

    @property
    def num_clean_slots_per_pm(self) -> int:
        if self.cleaning_interval <= 0:
            return 0
        return max(0, math.ceil(self.max_chamber_processes_per_pm / self.cleaning_interval) - 1)

    @property
    def effective_cleaning_process_time(self) -> float:
        if self.cleaning_process_time > 0:
            return self.cleaning_process_time
        return 2.0 * self.full_process_time

    @property
    def max_product_capacity(self) -> int:
        return self.load_ports * self.load_port_slots

    def validate(self) -> None:
        if self.num_pm != 2:
            raise ValueError("This device contains only CH2 and CH3, so num_pm must be 2.")
        if self.num_batches <= 0:
            raise ValueError("num_batches must be positive.")
        if self.batch_size != 4:
            raise ValueError("batch_size is fixed to 4 for the four-pocket rotary chamber.")
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
        if self.cleaning_process_time < 0:
            raise ValueError("cleaning_process_time must be non-negative.")
        if self.max_module_residency_time < 0 or self.max_robot_residency_time < 0:
            raise ValueError("Residency-time limits must be non-negative.")
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
            self.pm_balance_penalty,
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


def _add_unary_resource_no_overlap(model, task_specs, big_m: float, prefix: str) -> None:
    for left_idx in range(len(task_specs)):
        left_name, left_start, left_end, left_active = task_specs[left_idx]
        for right_idx in range(left_idx + 1, len(task_specs)):
            right_name, right_start, right_end, right_active = task_specs[right_idx]
            before = model.addVar(vtype="B", name=f"{prefix}_{left_name}_{right_name}")
            inactive_penalty = (1 - _maybe_one(left_active)) + (1 - _maybe_one(right_active))
            model.addCons(
                right_start >= left_end - big_m * (1 - before + inactive_penalty),
                name=f"{prefix}_lb_{left_name}_{right_name}",
            )
            model.addCons(
                left_start >= right_end - big_m * (before + inactive_penalty),
                name=f"{prefix}_ub_{left_name}_{right_name}",
            )


def _add_parallel_slot_resource(model, task_specs, slot_count: int, big_m: float, slot_prefix: str, order_prefix: str):
    slot_assign = {}
    normalized_specs = []
    for spec in task_specs:
        if len(spec) == 4:
            task_name, task_start, task_end, active_var = spec
            allowed_slots = list(range(1, slot_count + 1))
        elif len(spec) == 5:
            task_name, task_start, task_end, active_var, allowed_slots = spec
            allowed_slots = list(allowed_slots)
        else:
            raise ValueError("task_specs entries must have 4 or 5 items.")
        if not allowed_slots:
            raise ValueError(f"Task `{task_name}` has no allowed slots.")
        normalized_specs.append((task_name, task_start, task_end, active_var, allowed_slots))

    for task_name, _, _, active_var, allowed_slots in normalized_specs:
        for slot_id in allowed_slots:
            slot_assign[(task_name, slot_id)] = model.addVar(
                vtype="B",
                name=f"{slot_prefix}_{task_name}_{slot_id}",
            )
        rhs = _maybe_one(active_var)
        model.addCons(
            scip.quicksum(slot_assign[(task_name, slot_id)] for slot_id in allowed_slots) == rhs,
            name=f"{slot_prefix}_select_{task_name}",
        )

    for slot_id in range(1, slot_count + 1):
        for left_idx in range(len(normalized_specs)):
            left_name, left_start, left_end, _, _ = normalized_specs[left_idx]
            if (left_name, slot_id) not in slot_assign:
                continue
            for right_idx in range(left_idx + 1, len(normalized_specs)):
                right_name, right_start, right_end, _, _ = normalized_specs[right_idx]
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


def build_petri_mip_model(cfg: PetriMIPConfig):
    cfg.validate()
    model = scip.Model("dual_source_rotary_cluster_full_flow")
    big_m = cfg.big_m

    pm_ids = cfg.pm_ids
    full_batches = list(range(1, cfg.num_full_batches_per_pm + 1))
    full_sides = [1, 2]
    mix_positions = list(range(1, cfg.num_mix_positions_per_pm + 1))
    mix_cycles = list(range(1, cfg.num_mix_cycles_per_pm + 1))
    clean_slots = list(range(1, cfg.num_clean_slots_per_pm + 1))
    chamber_epochs = list(range(1, len(clean_slots) + 2)) if clean_slots else []
    load_ports = list(range(1, cfg.load_ports + 1))
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

    product_lp_assign = {
        (w, lp): model.addVar(vtype="B", name=f"product_lp_assign_{w}_{lp}")
        for w in product_wafers
        for lp in load_ports
    }

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
        m: model.addVar(vtype="C", lb=0.0, name=f"mix_head_start_{m}")
        for m in pm_ids
    }
    mix_head_end = {
        m: model.addVar(vtype="C", lb=0.0, name=f"mix_head_end_{m}")
        for m in pm_ids
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
        m: model.addVar(vtype="C", lb=0.0, name=f"mix_tail_load_start_{m}")
        for m in pm_ids
    }
    mix_tail_load_end = {
        m: model.addVar(vtype="C", lb=0.0, name=f"mix_tail_load_end_{m}")
        for m in pm_ids
    }
    mix_last_cycle_start = {
        m: model.addVar(vtype="C", lb=0.0, name=f"mix_last_cycle_start_{m}")
        for m in pm_ids
    }
    mix_last_cycle_end = {
        m: model.addVar(vtype="C", lb=0.0, name=f"mix_last_cycle_end_{m}")
        for m in pm_ids
    }
    mix_tail_start = {
        m: model.addVar(vtype="C", lb=0.0, name=f"mix_tail_start_{m}")
        for m in pm_ids
    }
    mix_tail_end = {
        m: model.addVar(vtype="C", lb=0.0, name=f"mix_tail_end_{m}")
        for m in pm_ids
    }
    mix_block_end = {
        m: model.addVar(vtype="C", lb=0.0, name=f"mix_block_end_{m}")
        for m in pm_ids
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
    mix_pair_completion = {
        p: model.addVar(vtype="C", lb=0.0, name=f"mix_pair_completion_{p}")
        for p in mix_pair_ids
    }

    for w in product_wafers:
        model.addCons(
            scip.quicksum(product_lp_assign[(w, lp)] for lp in load_ports) == 1,
            name=f"product_lp_once_{w}",
        )
    for lp in load_ports:
        model.addCons(
            scip.quicksum(product_lp_assign[(w, lp)] for w in product_wafers) <= cfg.load_port_slots,
            name=f"product_lp_capacity_{lp}",
        )

    for w in full_wafers:
        model.addCons(
            scip.quicksum(wafer_to_full_pair[(w, p)] for p in full_pair_ids) == 1,
            name=f"full_wafer_assign_once_{w}",
        )
    for p, load in full_pair_loads.items():
        model.addCons(
            scip.quicksum(wafer_to_full_pair[(w, p)] for w in full_wafers) == load,
            name=f"full_pair_capacity_{p}",
        )
    for idx in range(len(full_wafers) - 1):
        left = full_wafers[idx]
        right = full_wafers[idx + 1]
        model.addCons(
            scip.quicksum(p * wafer_to_full_pair[(left, p)] for p in full_pair_ids)
            <= scip.quicksum(p * wafer_to_full_pair[(right, p)] for p in full_pair_ids),
            name=f"full_pairing_order_{left}_{right}",
        )

    for w in mix_wafers:
        model.addCons(
            scip.quicksum(wafer_to_mix_pair[(w, p)] for p in mix_pair_ids) == 1,
            name=f"mix_wafer_assign_once_{w}",
        )
    for p, load in mix_pair_loads.items():
        model.addCons(
            scip.quicksum(wafer_to_mix_pair[(w, p)] for w in mix_wafers) == load,
            name=f"mix_pair_capacity_{p}",
        )
    for idx in range(len(mix_wafers) - 1):
        left = mix_wafers[idx]
        right = mix_wafers[idx + 1]
        model.addCons(
            scip.quicksum(p * wafer_to_mix_pair[(left, p)] for p in mix_pair_ids)
            <= scip.quicksum(p * wafer_to_mix_pair[(right, p)] for p in mix_pair_ids),
            name=f"mix_pairing_order_{left}_{right}",
        )

    for p in full_pair_ids:
        model.addCons(
            scip.quicksum(assign_full[(p, m, b, s)] for m in pm_ids for b in full_batches for s in full_sides) == 1,
            name=f"full_pair_schedule_once_{p}",
        )
    for p in mix_pair_ids:
        model.addCons(
            scip.quicksum(assign_mix[(p, m, r)] for m in pm_ids for r in mix_positions) == 1,
            name=f"mix_pair_schedule_once_{p}",
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
        last_cycle = mix_cycles[-1]
        model.addCons(
            mix_cycle_used[(m, 1)] == mix_pos_used[(m, 1)],
            name=f"mix_cycle_lead_{m}",
        )
        for c in mix_cycles[1:-1]:
            prev_pos = mix_pos_used[(m, c - 1)]
            next_pos = mix_pos_used[(m, c)]
            model.addCons(
                mix_cycle_used[(m, c)] >= prev_pos,
                name=f"mix_cycle_prev_{m}_{c}",
            )
            model.addCons(
                mix_cycle_used[(m, c)] >= next_pos,
                name=f"mix_cycle_next_{m}_{c}",
            )
            model.addCons(
                mix_cycle_used[(m, c)] <= prev_pos + next_pos,
                name=f"mix_cycle_union_{m}_{c}",
            )
        model.addCons(
            mix_cycle_used[(m, last_cycle)] == mix_pos_used[(m, last_position)],
            name=f"mix_cycle_tail_{m}",
        )
        for c in mix_cycles[:-1]:
            model.addCons(
                mix_cycle_used[(m, c)] >= mix_cycle_used[(m, c + 1)],
                name=f"mix_cycle_prefix_{m}_{c}",
            )

        model.addCons(
            mix_active[m] == scip.quicksum(mix_last_cycle[(m, c)] for c in mix_cycles),
            name=f"mix_last_cycle_unique_{m}",
        )
        for c in mix_cycles[:-1]:
            model.addCons(
                mix_last_cycle[(m, c)] <= mix_cycle_used[(m, c)],
                name=f"mix_last_cycle_active_{m}_{c}",
            )
            model.addCons(
                mix_last_cycle[(m, c)] + mix_cycle_used[(m, c + 1)] <= 1,
                name=f"mix_last_cycle_tail_only_{m}_{c}",
            )
            model.addCons(
                mix_last_cycle[(m, c)] >= mix_cycle_used[(m, c)] - mix_cycle_used[(m, c + 1)],
                name=f"mix_last_cycle_exact_{m}_{c}",
            )
        model.addCons(
            mix_last_cycle[(m, last_cycle)] == mix_cycle_used[(m, last_cycle)],
            name=f"mix_last_cycle_terminal_{m}",
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
            for epoch in chamber_epochs:
                process_epoch_used[(m, epoch)] = model.addVar(
                    vtype="B",
                    name=f"process_epoch_used_{m}_{epoch}",
                )

            for b in full_batches:
                for epoch in chamber_epochs:
                    full_batch_epoch[(m, b, epoch)] = model.addVar(
                        vtype="B",
                        name=f"full_batch_epoch_{m}_{b}_{epoch}",
                    )
                model.addCons(
                    scip.quicksum(full_batch_epoch[(m, b, epoch)] for epoch in chamber_epochs)
                    == full_batch_used[(m, b)],
                    name=f"full_batch_epoch_once_{m}_{b}",
                )

            for epoch in chamber_epochs:
                mix_block_epoch[(m, epoch)] = model.addVar(
                    vtype="B",
                    name=f"mix_block_epoch_{m}_{epoch}",
                )
            model.addCons(
                scip.quicksum(mix_block_epoch[(m, epoch)] for epoch in chamber_epochs) == mix_active[m],
                name=f"mix_block_epoch_once_{m}",
            )

            for c in mix_cycles:
                for epoch in chamber_epochs:
                    mix_cycle_epoch[(m, c, epoch)] = model.addVar(
                        vtype="B",
                        name=f"mix_cycle_epoch_{m}_{c}_{epoch}",
                    )
                    model.addCons(
                        mix_cycle_epoch[(m, c, epoch)] <= mix_cycle_used[(m, c)],
                        name=f"mix_cycle_epoch_cycle_ub_{m}_{c}_{epoch}",
                    )
                    model.addCons(
                        mix_cycle_epoch[(m, c, epoch)] <= mix_block_epoch[(m, epoch)],
                        name=f"mix_cycle_epoch_block_ub_{m}_{c}_{epoch}",
                    )
                    model.addCons(
                        mix_cycle_epoch[(m, c, epoch)]
                        >= mix_cycle_used[(m, c)] + mix_block_epoch[(m, epoch)] - 1,
                        name=f"mix_cycle_epoch_exact_{m}_{c}_{epoch}",
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

            for epoch in chamber_epochs[:-1]:
                model.addCons(
                    process_epoch_used[(m, epoch)] >= process_epoch_used[(m, epoch + 1)],
                    name=f"process_epoch_prefix_{m}_{epoch}",
                )

            for clean_slot in clean_slots:
                model.addCons(
                    clean_active[(m, clean_slot)] == process_epoch_used[(m, clean_slot + 1)],
                    name=f"clean_active_from_next_epoch_{m}_{clean_slot}",
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
            _add_duration_cons(
                model,
                full_back_unload_start[(m, b)],
                full_back_unload_end[(m, b)],
                cfg.pair_transfer_time,
                f"full_back_unload_{m}_{b}",
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
            _add_precedence_lower_bound(
                model,
                full_back_load_start[(m, b)],
                full_front_load_end[(m, b)],
                big_m,
                f"full_front_to_back_load_lb_{m}_{b}",
                used,
                cfg.pm_rotation_time_180,
            )
            _add_precedence_lower_bound(
                model,
                full_start[(m, b)],
                full_back_load_end[(m, b)],
                big_m,
                f"full_load_to_proc_lb_{m}_{b}",
                used,
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
            _add_duration_cons(
                model,
                clean_back_load_start[(m, clean_slot)],
                clean_back_load_end[(m, clean_slot)],
                cfg.pair_transfer_time,
                f"clean_back_load_{m}_{clean_slot}",
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
            _add_duration_cons(
                model,
                clean_front_unload_start[(m, clean_slot)],
                clean_front_unload_end[(m, clean_slot)],
                cfg.pair_transfer_time,
                f"clean_front_unload_{m}_{clean_slot}",
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
        # serial 4x1 block, optional cleaning windows, and then at most one
        # contiguous 2x2 block.
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
        _add_duration_cons(
            model,
            mix_head_start[m],
            mix_head_end[m],
            cfg.pair_transfer_time,
            f"mix_head_{m}",
            mix_active[m],
        )
        _add_duration_cons(
            model,
            mix_tail_start[m],
            mix_tail_end[m],
            cfg.pair_transfer_time,
            f"mix_tail_{m}",
            mix_active[m],
        )
        model.addCons(
            mix_block_end[m] == mix_tail_end[m],
            name=f"mix_block_end_def_{m}",
        )
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
            if c == 1 or c == mix_cycles[-1]:
                model.addCons(
                    mix_cycle_end[(m, c)] == mix_cycle_start[(m, c)] + cfg.mix_boundary_process_time * used,
                    name=f"mix_cycle_duration_{m}_{c}",
                )
            else:
                extra_internal = cfg.mix_internal_process_time - cfg.mix_boundary_process_time
                model.addCons(
                    mix_cycle_end[(m, c)]
                    == mix_cycle_start[(m, c)]
                    + cfg.mix_boundary_process_time * used
                    + extra_internal * mix_pos_used[(m, c)],
                    name=f"mix_cycle_duration_{m}_{c}",
                )

        _add_precedence_lower_bound(
            model,
            mix_cycle_start[(m, 1)],
            mix_head_end[m],
            big_m,
            f"mix_head_to_cycle_lb_{m}",
            mix_active[m],
        )

        for c in mix_cycles[1:]:
            used = mix_cycle_used[(m, c)]
            _add_duration_cons(
                model,
                mix_bridge_start[(m, c)],
                mix_bridge_end[(m, c)],
                cfg.pair_transfer_time,
                f"mix_bridge_{m}_{c}",
                used,
            )
            _add_precedence_lower_bound(
                model,
                mix_bridge_start[(m, c)],
                mix_cycle_end[(m, c - 1)],
                big_m,
                f"mix_cycle_to_bridge_lb_{m}_{c}",
                used,
            )
            _add_precedence_lower_bound(
                model,
                mix_cycle_start[(m, c)],
                mix_bridge_end[(m, c)],
                big_m,
                f"mix_bridge_to_cycle_lb_{m}_{c}",
                used,
            )

        model.addCons(
            mix_tail_start[m] <= big_m * mix_active[m],
            name=f"mix_tail_start_cap_{m}",
        )
        model.addCons(
            mix_tail_end[m] <= big_m * mix_active[m],
            name=f"mix_tail_end_cap_{m}",
        )
        model.addCons(
            mix_tail_load_start[m] <= big_m * mix_active[m],
            name=f"mix_tail_load_start_cap_{m}",
        )
        model.addCons(
            mix_tail_load_end[m] <= big_m * mix_active[m],
            name=f"mix_tail_load_end_cap_{m}",
        )
        model.addCons(
            mix_last_cycle_start[m] <= big_m * mix_active[m],
            name=f"mix_last_cycle_start_cap_{m}",
        )
        model.addCons(
            mix_last_cycle_end[m] <= big_m * mix_active[m],
            name=f"mix_last_cycle_end_cap_{m}",
        )
        for c in mix_cycles:
            selector = mix_last_cycle[(m, c)]
            _link_stage_by_binary(
                model,
                mix_last_cycle_start[m],
                mix_last_cycle_end[m],
                mix_cycle_start[(m, c)],
                mix_cycle_end[(m, c)],
                selector,
                big_m,
                f"mix_last_cycle_link_{m}_{c}",
            )
            if c >= 2:
                _link_stage_by_binary(
                    model,
                    mix_tail_load_start[m],
                    mix_tail_load_end[m],
                    mix_bridge_start[(m, c)],
                    mix_bridge_end[(m, c)],
                    selector,
                    big_m,
                    f"mix_tail_load_link_{m}_{c}",
                )
        _add_precedence_lower_bound(
            model,
            mix_tail_start[m],
            mix_last_cycle_end[m],
            big_m,
            f"mix_last_cycle_to_tail_lb_{m}",
            mix_active[m],
        )

        for b in full_batches:
            model.addCons(
                full_front_unload_end[(m, b)]
                <= mix_head_start[m]
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

            for epoch in chamber_epochs:
                selector = mix_block_epoch[(m, epoch)]
                if epoch > 1:
                    model.addCons(
                        mix_head_start[m] >= clean_front_unload_end[(m, epoch - 1)] - big_m * (1 - selector),
                        name=f"mix_epoch_after_clean_{m}_{epoch}",
                    )
                if epoch <= len(clean_slots):
                    model.addCons(
                        mix_tail_end[m]
                        <= clean_front_load_start[(m, epoch)]
                        + big_m * (1 - selector)
                        + big_m * (1 - clean_active[(m, epoch)]),
                        name=f"mix_epoch_before_clean_{m}_{epoch}",
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

    mix_pair_mid_link = {}
    mix_pair_tail_link = {}
    for p in mix_pair_ids:
        for m in pm_ids:
            for r in mix_positions:
                selector = assign_mix[(p, m, r)]
                if r == 1:
                    _link_stage_by_binary(
                        model,
                        mix_pair_vtr_load_start[p],
                        mix_pair_vtr_load_end[p],
                        mix_head_start[m],
                        mix_head_end[m],
                        selector,
                        big_m,
                        f"mix_pair_load_head_link_{p}_{m}_{r}",
                    )
                else:
                    _link_stage_by_binary(
                        model,
                        mix_pair_vtr_load_start[p],
                        mix_pair_vtr_load_end[p],
                        mix_bridge_start[(m, r)],
                        mix_bridge_end[(m, r)],
                        selector,
                        big_m,
                        f"mix_pair_load_bridge_link_{p}_{m}_{r}",
                    )
                _link_stage_by_binary(
                    model,
                    mix_pair_pm_start[p],
                    mix_pair_pm_end[p],
                    mix_cycle_start[(m, r)],
                    mix_cycle_end[(m, r + 1)],
                    selector,
                    big_m,
                    f"mix_pair_pm_link_{p}_{m}_{r}",
                )
                tail_selector = model.addVar(vtype="B", name=f"mix_pair_tail_link_{p}_{m}_{r}")
                mix_pair_tail_link[(p, m, r)] = tail_selector
                model.addCons(
                    tail_selector <= selector,
                    name=f"mix_pair_tail_assign_ub_{p}_{m}_{r}",
                )
                model.addCons(
                    tail_selector <= mix_last_pos[(m, r)],
                    name=f"mix_pair_tail_pos_ub_{p}_{m}_{r}",
                )
                model.addCons(
                    tail_selector >= selector + mix_last_pos[(m, r)] - 1,
                    name=f"mix_pair_tail_exact_{p}_{m}_{r}",
                )
                _link_stage_by_binary(
                    model,
                    mix_pair_vtr_unload_start[p],
                    mix_pair_vtr_unload_end[p],
                    mix_tail_start[m],
                    mix_tail_end[m],
                    tail_selector,
                    big_m,
                    f"mix_pair_tail_unload_link_{p}_{m}_{r}",
                )
                if r < mix_positions[-1]:
                    mid_selector = model.addVar(vtype="B", name=f"mix_pair_mid_link_{p}_{m}_{r}")
                    mix_pair_mid_link[(p, m, r)] = mid_selector
                    model.addCons(
                        mid_selector <= selector,
                        name=f"mix_pair_mid_assign_ub_{p}_{m}_{r}",
                    )
                    model.addCons(
                        mid_selector <= mix_pos_used[(m, r + 1)],
                        name=f"mix_pair_mid_next_ub_{p}_{m}_{r}",
                    )
                    model.addCons(
                        mid_selector >= selector + mix_pos_used[(m, r + 1)] - 1,
                        name=f"mix_pair_mid_exact_{p}_{m}_{r}",
                    )
                    _link_stage_by_binary(
                        model,
                        mix_pair_vtr_unload_start[p],
                        mix_pair_vtr_unload_end[p],
                        mix_bridge_start[(m, r + 2)],
                        mix_bridge_end[(m, r + 2)],
                        mid_selector,
                        big_m,
                        f"mix_pair_mid_unload_link_{p}_{m}_{r}",
                    )
        model.addCons(
            scip.quicksum(mix_pair_tail_link[(p, m, r)] for m in pm_ids for r in mix_positions)
            + scip.quicksum(mix_pair_mid_link[(p, m, r)] for m in pm_ids for r in mix_positions[:-1])
            == 1,
            name=f"mix_pair_unload_once_{p}",
        )
        model.addCons(
            mix_pair_completion[p] == mix_pair_vtr_unload_end[p],
            name=f"mix_pair_completion_def_{p}",
        )

    product_stage_order = [
        "atr_lp_al",
        "al",
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

    for w in product_wafers:
        _add_duration_cons(
            model,
            prod_stage_start[(w, "atr_lp_al")],
            prod_stage_end[(w, "atr_lp_al")],
            cfg.atr_transfer_time,
            f"prod_atr_lp_al_{w}",
        )
        model.addCons(
            prod_stage_start[(w, "al")] >= prod_stage_end[(w, "atr_lp_al")],
            name=f"prod_al_start_{w}",
        )
        model.addCons(
            prod_stage_end[(w, "al")] >= prod_stage_start[(w, "al")] + cfg.aligner_time,
            name=f"prod_al_min_duration_{w}",
        )
        model.addCons(
            prod_stage_end[(w, "al")] <= prod_stage_start[(w, "al")] + cfg.max_module_residency_time,
            name=f"prod_al_max_residency_{w}",
        )
        model.addCons(
            prod_stage_start[(w, "atr_al_llupper")] >= prod_stage_end[(w, "al")],
            name=f"prod_atr_al_llupper_start_{w}",
        )
        _add_duration_cons(
            model,
            prod_stage_start[(w, "atr_al_llupper")],
            prod_stage_end[(w, "atr_al_llupper")],
            cfg.atr_transfer_time,
            f"prod_atr_al_llupper_{w}",
        )
        model.addCons(
            prod_stage_start[(w, "llupper")] >= prod_stage_end[(w, "atr_al_llupper")],
            name=f"prod_llupper_start_{w}",
        )
        model.addCons(
            prod_stage_end[(w, "llupper")] >= prod_stage_start[(w, "llupper")] + cfg.llupper_time,
            name=f"prod_llupper_min_duration_{w}",
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
            prod_stage_end[(w, "pm")] <= prod_stage_start[(w, "pm")] + cfg.max_module_residency_time,
            name=f"prod_pm_max_residency_{w}",
        )
        model.addCons(
            prod_stage_start[(w, "lllower")] >= prod_stage_end[(w, "vtr_unload")],
            name=f"prod_lllower_start_{w}",
        )
        model.addCons(
            prod_stage_end[(w, "lllower")] >= prod_stage_start[(w, "lllower")] + cfg.lllower_time,
            name=f"prod_lllower_min_duration_{w}",
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
        _add_duration_cons(
            model,
            prod_stage_start[(w, "atr_lllower_lp")],
            prod_stage_end[(w, "atr_lllower_lp")],
            cfg.atr_return_time,
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
            _link_stage_by_binary(
                model,
                prod_stage_start[(w, "vtr_load")],
                prod_stage_end[(w, "vtr_load")],
                full_pair_vtr_load_start[p],
                full_pair_vtr_load_end[p],
                selector,
                big_m,
                f"prod_full_vtr_load_link_{w}_{p}",
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
            _link_stage_by_binary(
                model,
                prod_stage_start[(w, "vtr_unload")],
                prod_stage_end[(w, "vtr_unload")],
                full_pair_vtr_unload_start[p],
                full_pair_vtr_unload_end[p],
                selector,
                big_m,
                f"prod_full_vtr_unload_link_{w}_{p}",
            )

    for w in mix_wafers:
        for p in mix_pair_ids:
            selector = wafer_to_mix_pair[(w, p)]
            _link_stage_by_binary(
                model,
                prod_stage_start[(w, "vtr_load")],
                prod_stage_end[(w, "vtr_load")],
                mix_pair_vtr_load_start[p],
                mix_pair_vtr_load_end[p],
                selector,
                big_m,
                f"prod_mix_vtr_load_link_{w}_{p}",
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
                f"prod_mix_vtr_unload_link_{w}_{p}",
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
            for m in pm_ids:
                for b in full_batches:
                    for lane in full_sides:
                        add_pec_job(
                            f"embedded_full_{p}_{m}_{b}_{lane}",
                            m,
                            assign_full[(p, m, b, lane)],
                            (full_pair_vtr_load_start[p], full_pair_vtr_load_end[p]),
                            (full_pair_pm_start[p], full_pair_pm_end[p]),
                            (full_pair_vtr_unload_start[p], full_pair_vtr_unload_end[p]),
                        )
    for p, load in mix_pair_loads.items():
        if load == 1:
            for m in pm_ids:
                for r in mix_positions:
                    add_pec_job(
                        f"embedded_mix_{p}_{m}_{r}",
                        m,
                        assign_mix[(p, m, r)],
                        (mix_pair_vtr_load_start[p], mix_pair_vtr_load_end[p]),
                        (mix_pair_pm_start[p], mix_pair_pm_end[p]),
                        (mix_pair_vtr_unload_start[p], mix_pair_vtr_unload_end[p]),
                    )
    for m in pm_ids:
        for b in full_batches:
            for lane in full_sides:
                add_pec_job(
                    f"full_fill_{m}_{b}_{lane}",
                    m,
                    full_filler_side[(m, b, lane)],
                    (full_side_load_start[(m, b, lane)], full_side_load_end[(m, b, lane)]),
                    (full_start[(m, b)], full_end[(m, b)]),
                    (full_side_unload_start[(m, b, lane)], full_side_unload_end[(m, b, lane)]),
                )
        for lane in range(1, 3):
            add_pec_job(
                f"mix_head_{m}_{lane}",
                m,
                mix_active[m],
                (mix_head_start[m], mix_head_end[m]),
                (mix_cycle_start[(m, 1)], mix_cycle_end[(m, 1)]),
                (mix_bridge_start[(m, 2)], mix_bridge_end[(m, 2)]),
            )
            add_pec_job(
                f"mix_tail_{m}_{lane}",
                m,
                mix_active[m],
                (mix_tail_load_start[m], mix_tail_load_end[m]),
                (mix_last_cycle_start[m], mix_last_cycle_end[m]),
                (mix_tail_start[m], mix_tail_end[m]),
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

    for job_id, spec in pec_job_specs.items():
        active = spec["active"]
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

    atr_tasks = []
    al_tasks = []
    llupper_tasks = []
    lllower_tasks = []
    for w in product_wafers:
        atr_tasks.append(
            (f"lp_al_{w}", prod_stage_start[(w, "atr_lp_al")], prod_stage_end[(w, "atr_lp_al")], None)
        )
        atr_tasks.append(
            (
                f"al_llupper_{w}",
                prod_stage_start[(w, "atr_al_llupper")],
                prod_stage_end[(w, "atr_al_llupper")],
                None,
            )
        )
        atr_tasks.append(
            (
                f"lllower_lp_{w}",
                prod_stage_start[(w, "atr_lllower_lp")],
                prod_stage_end[(w, "atr_lllower_lp")],
                None,
            )
        )
        al_tasks.append((str(w), prod_stage_start[(w, "al")], prod_stage_end[(w, "al")], None))
        llupper_tasks.append(
            (str(w), prod_stage_start[(w, "llupper")], prod_stage_end[(w, "llupper")], None)
        )
        lllower_tasks.append(
            (str(w), prod_stage_start[(w, "lllower")], prod_stage_end[(w, "lllower")], None)
        )

    vtr_tasks = []
    for m in pm_ids:
        vtr_tasks.append((f"mix_head_{m}", mix_head_start[m], mix_head_end[m], mix_active[m]))
        vtr_tasks.append((f"mix_tail_{m}", mix_tail_start[m], mix_tail_end[m], mix_active[m]))
        for b in full_batches:
            vtr_tasks.append(
                (
                    f"full_front_load_{m}_{b}",
                    full_front_load_start[(m, b)],
                    full_front_load_end[(m, b)],
                    full_batch_used[(m, b)],
                )
            )
            vtr_tasks.append(
                (
                    f"full_back_load_{m}_{b}",
                    full_back_load_start[(m, b)],
                    full_back_load_end[(m, b)],
                    full_batch_used[(m, b)],
                )
            )
            vtr_tasks.append(
                (
                    f"full_back_unload_{m}_{b}",
                    full_back_unload_start[(m, b)],
                    full_back_unload_end[(m, b)],
                    full_batch_used[(m, b)],
                )
            )
            vtr_tasks.append(
                (
                    f"full_front_unload_{m}_{b}",
                    full_front_unload_start[(m, b)],
                    full_front_unload_end[(m, b)],
                    full_batch_used[(m, b)],
                )
            )
        for clean_slot in clean_slots:
            vtr_tasks.append(
                (
                    f"clean_front_load_{m}_{clean_slot}",
                    clean_front_load_start[(m, clean_slot)],
                    clean_front_load_end[(m, clean_slot)],
                    clean_active[(m, clean_slot)],
                )
            )
            vtr_tasks.append(
                (
                    f"clean_back_load_{m}_{clean_slot}",
                    clean_back_load_start[(m, clean_slot)],
                    clean_back_load_end[(m, clean_slot)],
                    clean_active[(m, clean_slot)],
                )
            )
            vtr_tasks.append(
                (
                    f"clean_back_unload_{m}_{clean_slot}",
                    clean_back_unload_start[(m, clean_slot)],
                    clean_back_unload_end[(m, clean_slot)],
                    clean_active[(m, clean_slot)],
                )
            )
            vtr_tasks.append(
                (
                    f"clean_front_unload_{m}_{clean_slot}",
                    clean_front_unload_start[(m, clean_slot)],
                    clean_front_unload_end[(m, clean_slot)],
                    clean_active[(m, clean_slot)],
                )
            )
        for c in mix_cycles[1:]:
            vtr_tasks.append(
                (
                    f"mix_bridge_{m}_{c}",
                    mix_bridge_start[(m, c)],
                    mix_bridge_end[(m, c)],
                    mix_cycle_used[(m, c)],
                )
            )

    _add_unary_resource_no_overlap(model, atr_tasks, big_m, "seq_atr")
    _add_unary_resource_no_overlap(model, al_tasks, big_m, "seq_al")
    _add_parallel_slot_resource(model, llupper_tasks, 2, big_m, "llupper_slot_assign", "seq_llupper")
    _add_parallel_slot_resource(model, lllower_tasks, 2, big_m, "lllower_slot_assign", "seq_lllower")
    _add_unary_resource_no_overlap(model, vtr_tasks, big_m, "seq_vtr")

    c_max = model.addVar(vtype="C", lb=0.0, name="c_max")
    for w in product_wafers:
        model.addCons(c_max >= wafer_completion[w], name=f"makespan_lb_{w}")

    objective = c_max
    if (
        full_pm_imbalance is not None
        and mix_pm_imbalance is not None
        and cfg.pm_balance_penalty > 0
    ):
        objective = objective + cfg.pm_balance_penalty * (full_pm_imbalance + mix_pm_imbalance)

    model.setObjective(objective, "minimize")
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

The objective is therefore the true end-to-end makespan from the first LP pick to the last LP return.

## Product Input Semantics

- `4x1` wafers: `{len(cfg.full_wafer_ids)}`
- `2x2` wafers: `{len(cfg.mix_wafer_ids)}`
- total product wafers: `{cfg.total_product_wafers}`

Per-mode PW-pair formation:

{_build_pair_slot_summary(MODE_FULL, cfg.full_wafer_ids, cfg.full_pair_product_loads)}
{_build_pair_slot_summary(MODE_MIX, cfg.mix_wafer_ids, cfg.mix_pair_product_loads)}

Embedded PEC wafers forced by odd product counts: `{embedded_pec}`.

## Core Scheduling Semantics

- `4x1`: each chamber batch has two physical side slots. Side 1 is loaded first and unloaded last; side 2 is loaded second and unloaded first.
- an active `4x1` batch fills both side slots. If only one product-carrying PW pair is assigned, the other side is forced to a pure `PEC+PEC` filler pair.
- per chamber, `4x1` batches form one serial block by batch index; batch `b+1` can start only after batch `b` has fully unloaded.
- a pure `PEC+PEC` filler side is allowed only on the tail `4x1` batch of a chamber sequence. Earlier active `4x1` batches must carry two product PW pairs.
- `2x2`: product PW pairs form one contiguous prefix block on a chamber, with one pure PEC pair at the head and one pure PEC pair at the tail.
- per chamber, every active `4x1` batch must finish before that chamber's `2x2` block begins, matching the disclosure rule that `4x1` is completed before `2x2`.
- time continuity is relaxed to precedence: downstream stages may wait, but they cannot start before the required transfer or process has finished.
- product wafers inherit chamber transfer/process timing from the PW pair to which they belong.
- PEC wafers are modeled as reusable, chamber-bound tokens. Each active PEC job occupies exactly one token from its assigned chamber's PEC subset, from `vtr_load` start until `vtr_unload` end.
- chamber cleaning is modeled as a pure `PEC+PEC` / `PEC+PEC` rotary batch. It uses the same VTR load/unload and chamber rotation semantics as `4x1`, occupies four PEC tokens, and adds a cleaning process interval.
- per chamber, process epochs are separated by cleaning batches so that each epoch contains at most `{cfg.cleaning_interval}` full-chamber process cycles. `2x2` chains are kept inside one epoch, so the model will split such work across chambers or report infeasibility rather than silently violating the cleaning requirement.

## Resource Constraints Added Explicitly

- `ATR`: unary move resource for `LP->AL`, `AL->LLupper`, and `LLlower->LP`
- `AL`: unary occupancy resource
- `LLupper`: 2-slot occupancy resource
- `LLlower`: 2-slot occupancy resource
- `VTR`: unary transfer resource across `4x1` load/unload and `2x2` head/bridge/tail transfers
- `CH2`, `CH3`: chamber-internal sequence constraints for `4x1` slots, one contiguous `2x2` block, and pure-PEC cleaning windows

## Timing Parameters

- Big-M: `{cfg.big_m:.1f}`
- chamber transfer gap: `{cfg.pm_transfer_gap:.1f}`
- chamber `180°` rotation time: `{cfg.pm_rotation_time_180:.1f}`
- VTR transfer time: `{cfg.pair_transfer_time:.1f}`
- ATR transfer time: `{cfg.atr_transfer_time:.1f}`
- ATR return time: `{cfg.atr_return_time:.1f}`
- aligner minimum occupancy: `{cfg.aligner_time:.1f}`
- LLupper minimum occupancy: `{cfg.llupper_time:.1f}`
- LLlower minimum occupancy: `{cfg.lllower_time:.1f}`
- `4x1` process time: `{cfg.full_process_time:.1f}`
- `2x2` boundary process time: `{cfg.mix_boundary_process_time:.1f}`
- `2x2` internal process time: `{cfg.mix_internal_process_time:.1f}`
- cleaning interval: `{cfg.cleaning_interval}` full-chamber process cycles
- cleaning process time: `{cfg.effective_cleaning_process_time:.1f}`
- max module residency time: `{cfg.max_module_residency_time:.1f}`
- max robot residency time: `{cfg.max_robot_residency_time:.1f}`
- PM balance penalty: `{cfg.pm_balance_penalty:.4f}`

## Main Variable Families

- `product_lp_assign_*`: product wafer to LP assignment
- `wafer_to_full_pair_*`, `wafer_to_mix_pair_*`: product wafer to PW-pair assignment
- `assign_full_*`, `assign_mix_*`: PW-pair to `4x1` batch-side / `2x2` chain-position assignment
- `full_batch_used_*`, `full_filler_side_*`
- `full_front_load_*`, `full_back_load_*`, `full_back_unload_*`, `full_front_unload_*`
- `mix_pos_used_*`, `mix_cycle_used_*`, `mix_active_*`, `mix_last_cycle_*`, `mix_last_pos_*`
- `clean_active_*`, `clean_front_load_*`, `clean_back_load_*`, `clean_*`, `clean_back_unload_*`, `clean_front_unload_*`
- `process_epoch_used_*`, `full_batch_epoch_*`, `mix_block_epoch_*`, `mix_cycle_epoch_*`: cleaning-separated chamber process epochs
- `prod_stage_start_*`, `prod_stage_end_*`: full product-wafer path stages
- `pec_stage_start_*`, `pec_stage_end_*`: PEC circulation stages
- `pec_token_assign_*`: reusable PEC token assignment
- `llupper_slot_assign_*`, `lllower_slot_assign_*`: LL slot occupancy assignment
- `wafer_completion_*`, `c_max`

## Objective

`min c_max + lambda * (full_pm_imbalance + mix_pm_imbalance)`, where `c_max` is the latest product wafer return time to `LP`
and `lambda = {cfg.pm_balance_penalty:.4f}` softly encourages the `4x1` and `2x2` product work to be shared across both chambers.

## Output Files

- LP model: `{instance_name}`
- Model description: `{os.path.basename(get_petri_model_description_path('', instance_name))}`
"""


def _write_model_description(output_dir: str, instance_name: str, cfg: PetriMIPConfig) -> str:
    description_path = get_petri_model_description_path(output_dir, instance_name)
    with open(description_path, "w", encoding="utf-8") as handle:
        handle.write(_build_model_description(instance_name, cfg))
    return description_path


def generate_petri_mip_instance(output_dir: str, instance_name: str, cfg: PetriMIPConfig) -> str:
    output_dir = str(resolve_path(output_dir))
    os.makedirs(output_dir, exist_ok=True)
    dated_instance_name = append_date_to_filename(instance_name)
    lp_path = os.path.join(output_dir, dated_instance_name)
    model = build_petri_mip_model(cfg)
    model.writeProblem(lp_path)
    _write_model_description(output_dir, dated_instance_name, cfg)
    return lp_path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate the dual-source mixed-flow semiconductor cluster full-flow MIP."
    )
    parser.add_argument("--output_dir", type=str, default="generated_instances/petri")
    parser.add_argument("--instance_name", type=str, default="petri_batch10_fullflow_v7.lp")
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
    parser.add_argument("--aligner_time", type=float, default=20.0)
    parser.add_argument("--llupper_time", type=float, default=30.0)
    parser.add_argument("--lllower_time", type=float, default=25.0)
    parser.add_argument("--full_process_time", type=float, default=80.0)
    parser.add_argument("--mix_boundary_process_time", type=float, default=30.0)
    parser.add_argument("--mix_internal_process_time", type=float, default=30.0)
    parser.add_argument("--cleaning_interval", type=int, default=10)
    parser.add_argument("--cleaning_process_time", type=float, default=0.0)
    parser.add_argument("--max_module_residency_time", type=float, default=10000.0)
    parser.add_argument("--max_robot_residency_time", type=float, default=10000.0)
    parser.add_argument("--pm_balance_penalty", type=float, default=0.01)
    parser.add_argument("--mode_sequence", type=str, default="")

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
        pm_balance_penalty=args.pm_balance_penalty,
        mode_sequence=args.mode_sequence,
        full_mode_wafers=args.mode_4x1_wafers,
        mix_mode_wafers=args.mode_2x2_wafers,
    )
    lp_path = generate_petri_mip_instance(args.output_dir, args.instance_name, cfg)
    generated_instance_name = os.path.basename(lp_path)
    print(f"generated MIP instance: {lp_path}")
    print(
        "generated model description: "
        f"{get_petri_model_description_path(str(resolve_path(args.output_dir)), generated_instance_name)}"
    )


if __name__ == "__main__":
    main()

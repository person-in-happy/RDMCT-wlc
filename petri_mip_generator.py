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
    cleaned = token.strip().lower().replace("脳", "x").replace("_", "").replace("-", "")
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
    pec_pool_size: int = 12
    batch_size: int = 4
    big_m: float = 10000.0
    pm_transfer_gap: float = 6.0
    pair_transfer_time: float = 20.0
    full_process_time: float = 80.0
    mix_boundary_process_time: float = 30.0
    mix_internal_process_time: float = 30.0
    mode_sequence: str = ""
    full_mode_wafers: int = 10
    mix_mode_wafers: int = 10

    @property
    def pm_ids(self) -> List[int]:
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
    def full_internal_pec_wafers(self) -> int:
        return len(self.full_wafer_ids) % 2

    @property
    def mix_internal_pec_wafers(self) -> int:
        return len(self.mix_wafer_ids) % 2

    @property
    def total_internal_pec_wafers(self) -> int:
        return self.full_internal_pec_wafers + self.mix_internal_pec_wafers

    @property
    def num_full_slots_per_pm(self) -> int:
        return max(1, self.num_batches)

    @property
    def num_mix_positions_per_pm(self) -> int:
        return max(1, self.num_mix_pairs)

    @property
    def num_mix_cycles_per_pm(self) -> int:
        return self.num_mix_positions_per_pm + 1

    @property
    def full_slot_duration(self) -> float:
        return self.full_process_time + 2.0 * self.pair_transfer_time

    @property
    def mix_boundary_cycle_duration(self) -> float:
        return self.mix_boundary_process_time + 2.0 * self.pair_transfer_time

    @property
    def mix_internal_cycle_duration(self) -> float:
        return self.mix_internal_process_time + 2.0 * self.pair_transfer_time

    def validate(self) -> None:
        if self.num_pm != 2:
            raise ValueError("This semiconductor cluster tool contains CH2 and CH3 only, so num_pm must be 2.")
        if self.num_batches <= 0:
            raise ValueError("num_batches must be positive.")
        if self.batch_size != 4:
            raise ValueError("batch_size is fixed to 4 because each rotary chamber has four process positions.")
        if self.pec_pool_size < 0:
            raise ValueError("pec_pool_size must be non-negative.")
        if self.big_m <= 0:
            raise ValueError("big_m must be positive.")
        if self.pm_transfer_gap < 0 or self.pair_transfer_time < 0:
            raise ValueError("Transfer durations must be non-negative.")
        if self.full_process_time < 0 or self.mix_boundary_process_time < 0 or self.mix_internal_process_time < 0:
            raise ValueError("Process durations must be non-negative.")
        if self.full_mode_wafers < 0 or self.mix_mode_wafers < 0:
            raise ValueError("Explicit per-mode wafer counts must be non-negative.")
        if self.total_product_wafers <= 0:
            raise ValueError("At least one product wafer is required.")

        full_capacity = 2 * self.num_pm * self.num_full_slots_per_pm
        if self.num_full_pairs > full_capacity:
            raise ValueError(
                "num_batches is too small for the requested number of 4x1 PW pairs. "
                f"Need capacity {self.num_full_pairs} but current upper bound is {full_capacity}."
            )
        if self.pec_pool_size < self.total_internal_pec_wafers:
            raise ValueError(
                "pec_pool_size is too small even for pair formation. "
                f"Need at least {self.total_internal_pec_wafers} PEC wafers but got {self.pec_pool_size}."
            )


def build_petri_mip_model(cfg: PetriMIPConfig) -> scip.Model:
    cfg.validate()

    model = scip.Model("dual_source_rotary_cluster_shared_pm_pw_pairs")
    model.hideOutput()

    full_wafer_ids = cfg.full_wafer_ids
    mix_wafer_ids = cfg.mix_wafer_ids
    product_wafer_ids = cfg.product_wafer_ids
    full_pair_ids = cfg.full_pair_ids
    mix_pair_ids = cfg.mix_pair_ids
    pm_ids = cfg.pm_ids
    full_slots = list(range(1, cfg.num_full_slots_per_pm + 1))
    mix_positions = list(range(1, cfg.num_mix_positions_per_pm + 1))
    mix_cycles = list(range(1, cfg.num_mix_cycles_per_pm + 1))
    big_m = cfg.big_m

    wafer_to_full_pair = {
        (w, p): model.addVar(vtype="B", name=f"wafer_to_full_pair_{w}_{p}")
        for w in full_wafer_ids
        for p in full_pair_ids
    }
    wafer_to_mix_pair = {
        (w, p): model.addVar(vtype="B", name=f"wafer_to_mix_pair_{w}_{p}")
        for w in mix_wafer_ids
        for p in mix_pair_ids
    }

    assign_full = {
        (p, m, f): model.addVar(vtype="B", name=f"assign_full_{p}_{m}_{f}")
        for p in full_pair_ids
        for m in pm_ids
        for f in full_slots
    }
    full_slot_used = {
        (m, f): model.addVar(vtype="B", name=f"full_slot_used_{m}_{f}")
        for m in pm_ids
        for f in full_slots
    }
    full_pec_pairs = {
        (m, f): model.addVar(vtype="B", name=f"full_pec_pairs_{m}_{f}")
        for m in pm_ids
        for f in full_slots
    }
    full_after_mix = {
        (m, f): model.addVar(vtype="B", name=f"full_after_mix_{m}_{f}")
        for m in pm_ids
        for f in full_slots
    }

    assign_mix = {
        (p, m, r): model.addVar(vtype="B", name=f"assign_mix_{p}_{m}_{r}")
        for p in mix_pair_ids
        for m in pm_ids
        for r in mix_positions
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

    full_start = {
        (m, f): model.addVar(vtype="C", lb=0.0, name=f"full_start_{m}_{f}")
        for m in pm_ids
        for f in full_slots
    }
    full_end = {
        (m, f): model.addVar(vtype="C", lb=0.0, name=f"full_end_{m}_{f}")
        for m in pm_ids
        for f in full_slots
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
    mix_block_end = {
        m: model.addVar(vtype="C", lb=0.0, name=f"mix_block_end_{m}")
        for m in pm_ids
    }

    full_pair_completion = {
        p: model.addVar(vtype="C", lb=0.0, name=f"full_pair_completion_{p}")
        for p in full_pair_ids
    }
    mix_pair_completion = {
        p: model.addVar(vtype="C", lb=0.0, name=f"mix_pair_completion_{p}")
        for p in mix_pair_ids
    }
    wafer_completion = {
        w: model.addVar(vtype="C", lb=0.0, name=f"wafer_completion_{w}")
        for w in product_wafer_ids
    }
    c_max = model.addVar(vtype="C", lb=0.0, name="c_max")

    for w in full_wafer_ids:
        model.addCons(
            scip.quicksum(wafer_to_full_pair[(w, p)] for p in full_pair_ids) == 1,
            name=f"full_wafer_assign_once_{w}",
        )
    for p, load in cfg.full_pair_product_loads.items():
        model.addCons(
            scip.quicksum(wafer_to_full_pair[(w, p)] for w in full_wafer_ids) == load,
            name=f"full_pair_capacity_{p}",
        )
    for idx in range(len(full_wafer_ids) - 1):
        left = full_wafer_ids[idx]
        right = full_wafer_ids[idx + 1]
        model.addCons(
            scip.quicksum(p * wafer_to_full_pair[(left, p)] for p in full_pair_ids)
            <= scip.quicksum(p * wafer_to_full_pair[(right, p)] for p in full_pair_ids),
            name=f"full_pairing_order_{left}_{right}",
        )

    for w in mix_wafer_ids:
        model.addCons(
            scip.quicksum(wafer_to_mix_pair[(w, p)] for p in mix_pair_ids) == 1,
            name=f"mix_wafer_assign_once_{w}",
        )
    for p, load in cfg.mix_pair_product_loads.items():
        model.addCons(
            scip.quicksum(wafer_to_mix_pair[(w, p)] for w in mix_wafer_ids) == load,
            name=f"mix_pair_capacity_{p}",
        )
    for idx in range(len(mix_wafer_ids) - 1):
        left = mix_wafer_ids[idx]
        right = mix_wafer_ids[idx + 1]
        model.addCons(
            scip.quicksum(p * wafer_to_mix_pair[(left, p)] for p in mix_pair_ids)
            <= scip.quicksum(p * wafer_to_mix_pair[(right, p)] for p in mix_pair_ids),
            name=f"mix_pairing_order_{left}_{right}",
        )

    for p in full_pair_ids:
        model.addCons(
            scip.quicksum(assign_full[(p, m, f)] for m in pm_ids for f in full_slots) == 1,
            name=f"full_pair_schedule_once_{p}",
        )
    for p in mix_pair_ids:
        model.addCons(
            scip.quicksum(assign_mix[(p, m, r)] for m in pm_ids for r in mix_positions) == 1,
            name=f"mix_pair_schedule_once_{p}",
        )

    for m in pm_ids:
        for f in full_slots:
            full_pair_count = scip.quicksum(assign_full[(p, m, f)] for p in full_pair_ids)
            model.addCons(
                full_pair_count + full_pec_pairs[(m, f)] == 2 * full_slot_used[(m, f)],
                name=f"full_slot_capacity_{m}_{f}",
            )
            model.addCons(
                full_slot_used[(m, f)] <= full_pair_count,
                name=f"full_slot_has_product_pair_{m}_{f}",
            )
            if f < full_slots[-1]:
                model.addCons(
                    full_slot_used[(m, f)] >= full_slot_used[(m, f + 1)],
                    name=f"full_slot_prefix_{m}_{f}",
                )
                model.addCons(
                    full_after_mix[(m, f)] <= full_after_mix[(m, f + 1)],
                    name=f"full_after_mix_monotone_{m}_{f}",
                )

        for r in mix_positions:
            mix_assign_count = scip.quicksum(assign_mix[(p, m, r)] for p in mix_pair_ids)
            model.addCons(
                mix_pos_used[(m, r)] == mix_assign_count,
                name=f"mix_pos_capacity_{m}_{r}",
            )
            if r < mix_positions[-1]:
                model.addCons(
                    mix_pos_used[(m, r)] >= mix_pos_used[(m, r + 1)],
                    name=f"mix_pos_prefix_{m}_{r}",
                )
        model.addCons(
            mix_active[m] == mix_pos_used[(m, 1)],
            name=f"mix_active_def_{m}",
        )

    model.addCons(
        cfg.total_internal_pec_wafers
        + 2 * scip.quicksum(full_pec_pairs[(m, f)] for m in pm_ids for f in full_slots)
        + 4 * scip.quicksum(mix_active[m] for m in pm_ids)
        <= cfg.pec_pool_size,
        name="pec_wafer_budget",
    )

    for m in pm_ids:
        last_position = mix_positions[-1]
        last_cycle = mix_cycles[-1]
        model.addCons(
            mix_cycle_used[(m, 1)] == mix_pos_used[(m, 1)],
            name=f"mix_cycle_lead_exists_{m}",
        )
        for c in mix_cycles[1:-1]:
            prev_pos = mix_pos_used[(m, c - 1)]
            curr_pos = mix_pos_used[(m, c)]
            model.addCons(
                mix_cycle_used[(m, c)] >= prev_pos,
                name=f"mix_cycle_prev_{m}_{c}",
            )
            model.addCons(
                mix_cycle_used[(m, c)] >= curr_pos,
                name=f"mix_cycle_next_{m}_{c}",
            )
            model.addCons(
                mix_cycle_used[(m, c)] <= prev_pos + curr_pos,
                name=f"mix_cycle_union_{m}_{c}",
            )
        model.addCons(
            mix_cycle_used[(m, last_cycle)] == mix_pos_used[(m, last_position)],
            name=f"mix_cycle_tail_exists_{m}",
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

    for m in pm_ids:
        for f in full_slots:
            used = full_slot_used[(m, f)]
            model.addCons(
                full_start[(m, f)] <= big_m * used,
                name=f"full_start_cap_{m}_{f}",
            )
            model.addCons(
                full_end[(m, f)] <= big_m * used,
                name=f"full_end_cap_{m}_{f}",
            )
            model.addCons(
                full_end[(m, f)] == full_start[(m, f)] + cfg.full_slot_duration * used,
                name=f"full_duration_{m}_{f}",
            )
            if f < full_slots[-1]:
                next_used = full_slot_used[(m, f + 1)]
                model.addCons(
                    full_start[(m, f + 1)]
                    >= full_end[(m, f)] + cfg.pm_transfer_gap - big_m * (2 - used - next_used),
                    name=f"full_sequence_lb_{m}_{f}",
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
                    mix_cycle_end[(m, c)] == mix_cycle_start[(m, c)] + cfg.mix_boundary_cycle_duration * used,
                    name=f"mix_cycle_duration_{m}_{c}",
                )
            else:
                extra_internal = cfg.mix_internal_cycle_duration - cfg.mix_boundary_cycle_duration
                model.addCons(
                    mix_cycle_end[(m, c)]
                    == mix_cycle_start[(m, c)]
                    + cfg.mix_boundary_cycle_duration * used
                    + extra_internal * mix_pos_used[(m, c)],
                    name=f"mix_cycle_duration_{m}_{c}",
                )
            if c < mix_cycles[-1]:
                next_used = mix_cycle_used[(m, c + 1)]
                model.addCons(
                    mix_cycle_start[(m, c + 1)]
                    >= mix_cycle_end[(m, c)] + cfg.pm_transfer_gap - big_m * (1 - next_used),
                    name=f"mix_cycle_sequence_lb_{m}_{c}",
                )
                model.addCons(
                    mix_cycle_start[(m, c + 1)]
                    <= mix_cycle_end[(m, c)] + cfg.pm_transfer_gap + big_m * (2 - used - next_used),
                    name=f"mix_cycle_sequence_ub_{m}_{c}",
                )

        model.addCons(
            mix_block_end[m] <= big_m * mix_active[m],
            name=f"mix_block_end_cap_{m}",
        )
        for c in mix_cycles:
            model.addCons(
                mix_block_end[m] >= mix_cycle_end[(m, c)] - big_m * (1 - mix_last_cycle[(m, c)]),
                name=f"mix_block_end_lb_{m}_{c}",
            )
            model.addCons(
                mix_block_end[m] <= mix_cycle_end[(m, c)] + big_m * (1 - mix_last_cycle[(m, c)]),
                name=f"mix_block_end_ub_{m}_{c}",
            )

        for f in full_slots:
            model.addCons(
                full_end[(m, f)]
                <= mix_cycle_start[(m, 1)]
                - cfg.pm_transfer_gap
                + big_m * full_after_mix[(m, f)]
                + big_m * (1 - full_slot_used[(m, f)])
                + big_m * (1 - mix_active[m]),
                name=f"full_before_mix_{m}_{f}",
            )
            model.addCons(
                full_start[(m, f)]
                >= mix_block_end[m]
                + cfg.pm_transfer_gap
                - big_m * (1 - full_after_mix[(m, f)])
                - big_m * (1 - full_slot_used[(m, f)])
                - big_m * (1 - mix_active[m]),
                name=f"full_after_mix_{m}_{f}",
            )

    for p in full_pair_ids:
        for m in pm_ids:
            for f in full_slots:
                assign_var = assign_full[(p, m, f)]
                model.addCons(
                    full_pair_completion[p] >= full_end[(m, f)] - big_m * (1 - assign_var),
                    name=f"full_pair_completion_lb_{p}_{m}_{f}",
                )
                model.addCons(
                    full_pair_completion[p] <= full_end[(m, f)] + big_m * (1 - assign_var),
                    name=f"full_pair_completion_ub_{p}_{m}_{f}",
                )

    for p in mix_pair_ids:
        for m in pm_ids:
            for r in mix_positions:
                assign_var = assign_mix[(p, m, r)]
                second_pass_cycle = r + 1
                model.addCons(
                    mix_pair_completion[p] >= mix_cycle_end[(m, second_pass_cycle)] - big_m * (1 - assign_var),
                    name=f"mix_pair_completion_lb_{p}_{m}_{r}",
                )
                model.addCons(
                    mix_pair_completion[p] <= mix_cycle_end[(m, second_pass_cycle)] + big_m * (1 - assign_var),
                    name=f"mix_pair_completion_ub_{p}_{m}_{r}",
                )

    for w in full_wafer_ids:
        for p in full_pair_ids:
            member_var = wafer_to_full_pair[(w, p)]
            model.addCons(
                wafer_completion[w] >= full_pair_completion[p] - big_m * (1 - member_var),
                name=f"wafer_full_completion_lb_{w}_{p}",
            )
            model.addCons(
                wafer_completion[w] <= full_pair_completion[p] + big_m * (1 - member_var),
                name=f"wafer_full_completion_ub_{w}_{p}",
            )

    for w in mix_wafer_ids:
        for p in mix_pair_ids:
            member_var = wafer_to_mix_pair[(w, p)]
            model.addCons(
                wafer_completion[w] >= mix_pair_completion[p] - big_m * (1 - member_var),
                name=f"wafer_mix_completion_lb_{w}_{p}",
            )
            model.addCons(
                wafer_completion[w] <= mix_pair_completion[p] + big_m * (1 - member_var),
                name=f"wafer_mix_completion_ub_{w}_{p}",
            )

    for w in product_wafer_ids:
        model.addCons(
            c_max >= wafer_completion[w],
            name=f"cmax_ge_wafer_{w}",
        )

    for m in pm_ids:
        for f in full_slots[:-1]:
            model.addCons(
                scip.quicksum(p * assign_full[(p, m, f)] for p in full_pair_ids)
                - scip.quicksum(p * assign_full[(p, m, f + 1)] for p in full_pair_ids)
                + big_m * full_slot_used[(m, f)]
                + big_m * full_slot_used[(m, f + 1)]
                <= 2 * big_m,
                name=f"full_order_symmetry_{m}_{f}",
            )
        for r in mix_positions[:-1]:
            model.addCons(
                scip.quicksum(p * assign_mix[(p, m, r)] for p in mix_pair_ids)
                - scip.quicksum(p * assign_mix[(p, m, r + 1)] for p in mix_pair_ids)
                + big_m * mix_pos_used[(m, r)]
                + big_m * mix_pos_used[(m, r + 1)]
                <= 2 * big_m,
                name=f"mix_order_symmetry_{m}_{r}",
            )

    if len(pm_ids) == 2:
        model.addCons(
            scip.quicksum(full_slot_used[(pm_ids[0], f)] for f in full_slots)
            + scip.quicksum(mix_pos_used[(pm_ids[0], r)] for r in mix_positions)
            >= scip.quicksum(full_slot_used[(pm_ids[1], f)] for f in full_slots)
            + scip.quicksum(mix_pos_used[(pm_ids[1], r)] for r in mix_positions),
            name="pm_activity_symmetry",
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
    chamber_labels = ", ".join(f"CH{pm_id + 1}" for pm_id in cfg.pm_ids)
    return f"""# Dual-Source Mixed-Flow Semiconductor Cluster Scheduling MIP

This file documents the exact MIP generated for `{instance_name}`.

## Device Interpretation

The generated model follows the dual-source mixed-flow semiconductor cluster tool described in the supplied materials:

- shared rotary chambers: `CH2` and `CH3`
- product flow: `LP -> ATR -> AL -> ATR -> LLupper -> VTR -> CH -> VTR -> LLlower -> ATR -> LP`
- PEC flow: `PEC storage -> VTR -> CH -> VTR -> PEC storage`
- both `CH2` and `CH3` may execute `4x1` and `2x2`, but the two modes cannot overlap on the same chamber

## Corrected Input Semantics

This version no longer starts from pre-built product pairs. Instead, the input is an arbitrary number of product wafers for the two process modes:

- `4x1` mode wafers: `{len(cfg.full_wafer_ids)}`
- `2x2` mode wafers: `{len(cfg.mix_wafer_ids)}`
- total product wafers: `{cfg.total_product_wafers}`
- PEC wafers available: `{cfg.pec_pool_size}`

The MIP first assigns individual wafers to mode-consistent PW pairs:

1. `4x1` wafers can only be grouped with other `4x1` product wafers in the same PW pair.
2. `2x2` wafers can only be grouped with other `2x2` product wafers in the same PW pair.
3. If one mode has an odd number of product wafers, the last PW pair of that mode becomes `1 product wafer + 1 PEC wafer`.

PW-pair structure implied by the current instance:

{_build_pair_slot_summary(MODE_FULL, cfg.full_wafer_ids, cfg.full_pair_product_loads)}
{_build_pair_slot_summary(MODE_MIX, cfg.mix_wafer_ids, cfg.mix_pair_product_loads)}

## Scheduling Semantics

After PW-pair formation, the chamber scheduling layer is modeled exactly:

- `4x1`: each used chamber slot contains exactly 2 PW pairs. If only 1 product-carrying `4x1` PW pair is assigned to a slot, the remaining PW pair is a pure PEC pair.
- `2x2`: product-carrying `2x2` PW pairs form an ordered sequence. Each active sequence uses one pure PEC pair at the head and one pure PEC pair at the tail.
- every product wafer inherits the completion time of the PW pair to which it is assigned

## Size

- chambers: `{chamber_labels}`
- `4x1` PW pairs: `{cfg.num_full_pairs}`
- `2x2` PW pairs: `{cfg.num_mix_pairs}`
- `4x1` slot upper bound per chamber: `{cfg.num_full_slots_per_pm}`
- `2x2` position upper bound per chamber: `{cfg.num_mix_positions_per_pm}`
- `2x2` cycle upper bound per chamber: `{cfg.num_mix_cycles_per_pm}`
- internal PEC wafers forced by odd pair formation: `{cfg.total_internal_pec_wafers}`

## Timing Parameters

- Big-M: `{cfg.big_m:.1f}`
- chamber transfer gap `mu`: `{cfg.pm_transfer_gap:.1f}`
- aggregated PW-pair transfer time `beta`: `{cfg.pair_transfer_time:.1f}`
- `4x1` chamber process time: `{cfg.full_process_time:.1f}`
- `2x2` boundary process time: `{cfg.mix_boundary_process_time:.1f}`
- `2x2` internal process time: `{cfg.mix_internal_process_time:.1f}`

Derived durations used directly in the MIP:

- `T_full = full_process_time + 2 * beta = {cfg.full_slot_duration:.1f}`
- `T_mix_boundary = mix_boundary_process_time + 2 * beta = {cfg.mix_boundary_cycle_duration:.1f}`
- `T_mix_internal = mix_internal_process_time + 2 * beta = {cfg.mix_internal_cycle_duration:.1f}`

## Main Variables

### 1. Wafer-to-PW-pair formation

- `wafer_to_full_pair_w_p`: `4x1` wafer `w` is assigned to `4x1` PW pair `p`
- `wafer_to_mix_pair_w_p`: `2x2` wafer `w` is assigned to `2x2` PW pair `p`

### 2. Shared-chamber `4x1` allocation

- `assign_full_p_m_f`: `4x1` PW pair `p` assigned to chamber `m`, slot `f`
- `full_slot_used_m_f`: slot `f` on chamber `m` is used by `4x1`
- `full_pec_pairs_m_f`: slot `f` on chamber `m` uses one pure PEC PW pair
- `full_after_mix_m_f`: slot `f` is placed after the `2x2` block on the same chamber

### 3. Shared-chamber `2x2` allocation

- `assign_mix_p_m_r`: `2x2` PW pair `p` assigned to chamber `m`, position `r`
- `mix_pos_used_m_r`: position `r` is active
- `mix_cycle_used_m_c`: `2x2` cycle `c` exists
- `mix_active_m`: chamber `m` hosts a `2x2` sequence
- `mix_last_cycle_m_c`: cycle `c` is the final active cycle on chamber `m`

### 4. Time and completion variables

- `full_start_m_f`, `full_end_m_f`
- `mix_cycle_start_m_c`, `mix_cycle_end_m_c`
- `mix_block_end_m`
- `full_pair_completion_p`, `mix_pair_completion_p`
- `wafer_completion_w`
- `c_max`

## Core Constraints

1. Every product wafer is assigned to exactly one PW pair of the same required mode.
2. Every PW pair has fixed product capacity: 2 product wafers when possible, otherwise `1 product + 1 PEC`.
3. Every `4x1` PW pair is assigned to exactly one shared-chamber `4x1` slot.
4. Every `2x2` PW pair is assigned to exactly one shared-chamber `2x2` position.
5. Each used `4x1` slot satisfies `assigned product-carrying PW pairs + pure PEC pairs = 2`, and a pure-PEC-only slot is forbidden.
6. Each chamber `2x2` sequence is modeled as a prefix of positions with derived lead, internal, and tail cycles.
7. PEC availability is global and counted in wafers: odd pair formation consumes 1 PEC wafer per affected PW pair, each pure `4x1` PEC pair consumes 2 PEC wafers, and each active `2x2` sequence consumes 4 PEC wafers for the head and tail boundaries.
8. A chamber may contain both modes, but every `4x1` slot must lie entirely before or after the contiguous `2x2` block on that chamber.
9. A `4x1` PW pair completes at the end of its assigned slot; a `2x2` PW pair completes at the end of the next cycle because its second pass finishes there; every product wafer inherits its PW-pair completion time.
10. The objective is `min c_max`.

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
        description="Generate the dual-source mixed-flow semiconductor cluster scheduling MIP."
    )
    parser.add_argument("--output_dir", type=str, default="generated_instances/petri")
    parser.add_argument("--instance_name", type=str, default="petri_batch10_v2.lp")
    parser.add_argument("--num_batches", type=int, default=10)
    parser.add_argument("--num_pm", type=int, default=2)
    parser.add_argument("--num_steps", type=int, default=13)
    parser.add_argument("--total_wafers", type=int, default=0)
    parser.add_argument("--mode_4x1_wafers", "--full_mode_wafers", dest="mode_4x1_wafers", type=int, default=10)
    parser.add_argument("--mode_2x2_wafers", "--mix_mode_wafers", dest="mode_2x2_wafers", type=int, default=10)
    parser.add_argument("--pec_pool_size", type=int, default=12)
    parser.add_argument("--batch_size", type=int, default=4)
    parser.add_argument("--big_m", type=float, default=10000.0)
    parser.add_argument("--pm_transfer_gap", type=float, default=6.0)
    parser.add_argument("--pair_transfer_time", type=float, default=20.0)
    parser.add_argument("--full_process_time", type=float, default=80.0)
    parser.add_argument("--mix_boundary_process_time", type=float, default=30.0)
    parser.add_argument("--mix_internal_process_time", type=float, default=30.0)
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
        pair_transfer_time=args.pair_transfer_time,
        full_process_time=args.full_process_time,
        mix_boundary_process_time=args.mix_boundary_process_time,
        mix_internal_process_time=args.mix_internal_process_time,
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

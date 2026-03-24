import argparse
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
    cleaned = token.strip().lower().replace("×", "x").replace("_", "").replace("-", "")
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


def _parse_mode_sequence(num_product_pairs: int, total_wafers: int, mode_sequence: str) -> List[str]:
    if not mode_sequence or not mode_sequence.strip():
        return [MODE_MIX if pair_id % 2 == 1 else MODE_FULL for pair_id in range(1, num_product_pairs + 1)]

    raw_tokens = [token for token in _MODE_TOKEN_RE.split(mode_sequence.strip()) if token]
    if not raw_tokens:
        return [MODE_MIX if pair_id % 2 == 1 else MODE_FULL for pair_id in range(1, num_product_pairs + 1)]

    modes = [_normalize_mode_token(token) for token in raw_tokens]
    if len(modes) == num_product_pairs:
        return modes
    if len(modes) == total_wafers:
        pair_modes: List[str] = []
        for idx in range(0, total_wafers, 2):
            first = modes[idx]
            second = modes[idx + 1]
            if first != second:
                raise ValueError(
                    "Wafer-level mode_sequence must assign the same mode to both wafers of every product pair."
                )
            pair_modes.append(first)
        return pair_modes
    raise ValueError(
        "mode_sequence length must equal either the number of product pairs "
        f"({num_product_pairs}) or the number of product wafers ({total_wafers})."
    )


@dataclass
class PetriMIPConfig:
    num_batches: int = 10
    num_pm: int = 2
    num_steps: int = 13  # kept only for CLI compatibility
    total_wafers: int = 20
    pec_pool_size: int = 8
    batch_size: int = 4
    big_m: float = 10000.0
    pm_transfer_gap: float = 6.0
    pair_transfer_time: float = 20.0
    full_process_time: float = 80.0
    mix_boundary_process_time: float = 30.0
    mix_internal_process_time: float = 30.0
    mode_sequence: str = ""

    @property
    def pm_ids(self) -> List[int]:
        return list(range(1, self.num_pm + 1))

    @property
    def num_product_pairs(self) -> int:
        return self.total_wafers // 2

    @property
    def num_pec_pairs(self) -> int:
        return self.pec_pool_size // 2

    @property
    def pair_modes(self) -> List[str]:
        return _parse_mode_sequence(self.num_product_pairs, self.total_wafers, self.mode_sequence)

    @property
    def pair_mode_map(self) -> Dict[int, str]:
        return {pair_id: mode for pair_id, mode in enumerate(self.pair_modes, start=1)}

    @property
    def full_pairs(self) -> List[int]:
        return [pair_id for pair_id, mode in self.pair_mode_map.items() if mode == MODE_FULL]

    @property
    def mix_pairs(self) -> List[int]:
        return [pair_id for pair_id, mode in self.pair_mode_map.items() if mode == MODE_MIX]

    @property
    def num_full_slots_per_pm(self) -> int:
        return max(1, self.num_batches)

    @property
    def num_mix_positions_per_pm(self) -> int:
        return max(1, len(self.mix_pairs))

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
        if self.total_wafers <= 0 or self.total_wafers % 2 != 0:
            raise ValueError("total_wafers must be a positive even number because the model groups products into 2-wafer pairs.")
        if self.pec_pool_size < 0 or self.pec_pool_size % 2 != 0:
            raise ValueError("pec_pool_size must be a non-negative even number because PEC is modeled in 2-wafer pairs.")
        if self.batch_size != 4:
            raise ValueError("batch_size is fixed to 4 because each rotary chamber has four process positions.")
        if self.big_m <= 0:
            raise ValueError("big_m must be positive.")
        if self.pm_transfer_gap < 0 or self.pair_transfer_time < 0:
            raise ValueError("Transfer durations must be non-negative.")
        if self.full_process_time < 0 or self.mix_boundary_process_time < 0 or self.mix_internal_process_time < 0:
            raise ValueError("Process durations must be non-negative.")

        pair_modes = self.pair_modes
        if len(pair_modes) != self.num_product_pairs:
            raise ValueError("Failed to resolve a valid pair-level mode sequence.")

        full_pairs = sum(1 for mode in pair_modes if mode == MODE_FULL)
        full_capacity = 2 * self.num_pm * self.num_full_slots_per_pm
        if full_pairs > full_capacity:
            raise ValueError(
                "num_batches is too small for the requested number of 4x1 product pairs. "
                f"Need at most {full_capacity} but got {full_pairs}."
            )


def build_petri_mip_model(cfg: PetriMIPConfig) -> scip.Model:
    cfg.validate()

    model = scip.Model("dual_source_rotary_cluster_shared_pm")
    model.hideOutput()

    product_pairs = list(range(1, cfg.num_product_pairs + 1))
    full_pairs = cfg.full_pairs
    mix_pairs = cfg.mix_pairs
    pm_ids = cfg.pm_ids
    full_slots = list(range(1, cfg.num_full_slots_per_pm + 1))
    mix_positions = list(range(1, cfg.num_mix_positions_per_pm + 1))
    mix_cycles = list(range(1, cfg.num_mix_cycles_per_pm + 1))
    big_m = cfg.big_m

    assign_full = {
        (j, m, f): model.addVar(vtype="B", name=f"assign_full_{j}_{m}_{f}")
        for j in full_pairs
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
        (j, m, r): model.addVar(vtype="B", name=f"assign_mix_{j}_{m}_{r}")
        for j in mix_pairs
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
    pair_completion = {
        j: model.addVar(vtype="C", lb=0.0, name=f"pair_completion_{j}")
        for j in product_pairs
    }
    c_max = model.addVar(vtype="C", lb=0.0, name="c_max")

    for j in full_pairs:
        model.addCons(
            scip.quicksum(assign_full[(j, m, f)] for m in pm_ids for f in full_slots) == 1,
            name=f"full_pair_assign_once_{j}",
        )
    for j in mix_pairs:
        model.addCons(
            scip.quicksum(assign_mix[(j, m, r)] for m in pm_ids for r in mix_positions) == 1,
            name=f"mix_pair_assign_once_{j}",
        )

    for m in pm_ids:
        for f in full_slots:
            full_pair_count = scip.quicksum(assign_full[(j, m, f)] for j in full_pairs)
            model.addCons(
                full_pair_count + full_pec_pairs[(m, f)] == 2 * full_slot_used[(m, f)],
                name=f"full_slot_capacity_{m}_{f}",
            )
            model.addCons(
                full_slot_used[(m, f)] <= full_pair_count,
                name=f"full_slot_has_product_{m}_{f}",
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
            mix_assign_count = scip.quicksum(assign_mix[(j, m, r)] for j in mix_pairs)
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
        scip.quicksum(full_pec_pairs[(m, f)] for m in pm_ids for f in full_slots)
        + 2 * scip.quicksum(mix_active[m] for m in pm_ids)
        <= cfg.num_pec_pairs,
        name="pec_pair_budget",
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

    for j in full_pairs:
        for m in pm_ids:
            for f in full_slots:
                assign_var = assign_full[(j, m, f)]
                model.addCons(
                    pair_completion[j] >= full_end[(m, f)] - big_m * (1 - assign_var),
                    name=f"pair_full_lb_{j}_{m}_{f}",
                )
                model.addCons(
                    pair_completion[j] <= full_end[(m, f)] + big_m * (1 - assign_var),
                    name=f"pair_full_ub_{j}_{m}_{f}",
                )

    for j in mix_pairs:
        for m in pm_ids:
            for r in mix_positions:
                assign_var = assign_mix[(j, m, r)]
                second_pass_cycle = r + 1
                model.addCons(
                    pair_completion[j] >= mix_cycle_end[(m, second_pass_cycle)] - big_m * (1 - assign_var),
                    name=f"pair_mix_lb_{j}_{m}_{r}",
                )
                model.addCons(
                    pair_completion[j] <= mix_cycle_end[(m, second_pass_cycle)] + big_m * (1 - assign_var),
                    name=f"pair_mix_ub_{j}_{m}_{r}",
                )

    for j in product_pairs:
        model.addCons(
            c_max >= pair_completion[j],
            name=f"cmax_ge_pair_{j}",
        )

    for m in pm_ids:
        for f in full_slots[:-1]:
            model.addCons(
                scip.quicksum(j * assign_full[(j, m, f)] for j in full_pairs)
                - scip.quicksum(j * assign_full[(j, m, f + 1)] for j in full_pairs)
                + big_m * full_slot_used[(m, f)]
                + big_m * full_slot_used[(m, f + 1)]
                <= 2 * big_m,
                name=f"full_order_symmetry_{m}_{f}",
            )
        for r in mix_positions[:-1]:
            model.addCons(
                scip.quicksum(j * assign_mix[(j, m, r)] for j in mix_pairs)
                - scip.quicksum(j * assign_mix[(j, m, r + 1)] for j in mix_pairs)
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


def _build_mode_summary(cfg: PetriMIPConfig) -> str:
    pair_modes = cfg.pair_modes
    return "\n".join(f"- Pair {pair_id}: {mode}" for pair_id, mode in enumerate(pair_modes, start=1))


def _build_model_description(instance_name: str, cfg: PetriMIPConfig) -> str:
    chamber_labels = ", ".join(f"CH{pm_id + 1}" for pm_id in cfg.pm_ids)
    return f"""# Dual-Source Mixed-Flow Semiconductor Cluster Scheduling MIP

This file documents the exact MIP generated for `{instance_name}`.

## Device Interpretation

The generated model follows the problem statement given in the supplied materials:

- shared rotary chambers: `CH2` and `CH3`
- product flow: `LP -> ATR -> AL -> ATR -> LLupper -> VTR -> CH -> VTR -> LLlower -> ATR -> LP`
- PEC flow: `PEC storage -> VTR -> CH -> VTR -> PEC storage`
- each product pair has a fixed required chamber mode: `2x2` or `4x1`
- each chamber may execute both modes, but never overlap them in time

To keep the instance compact enough for MIP solving, the front-end robot and lock actions are aggregated into pair-level transfer durations. The key mixed-flow chamber semantics are modeled exactly:

- `4x1`: a chamber slot must be fully covered by two pair units, using product pairs and, if needed, one PEC pair
- `2x2`: product pairs form an ordered sequence with leading and trailing PEC boundaries, and every product pair completes after its second pass

## Size

- product wafers: `{cfg.total_wafers}`
- product pairs: `{cfg.num_product_pairs}`
- PEC wafers: `{cfg.pec_pool_size}`
- PEC pairs: `{cfg.num_pec_pairs}`
- chambers: `{chamber_labels}`
- 4x1 slot upper bound per chamber: `{cfg.num_full_slots_per_pm}`
- 2x2 position upper bound per chamber: `{cfg.num_mix_positions_per_pm}`
- 2x2 cycle upper bound per chamber: `{cfg.num_mix_cycles_per_pm}`

## Fixed Product Modes

{_build_mode_summary(cfg)}

Mode counts:

- `4x1` product pairs: `{len(cfg.full_pairs)}`
- `2x2` product pairs: `{len(cfg.mix_pairs)}`

## Timing Parameters

- Big-M: `{cfg.big_m:.1f}`
- chamber transfer gap `mu`: `{cfg.pm_transfer_gap:.1f}`
- aggregated pair transfer time `beta`: `{cfg.pair_transfer_time:.1f}`
- `4x1` chamber process time: `{cfg.full_process_time:.1f}`
- `2x2` boundary process time: `{cfg.mix_boundary_process_time:.1f}`
- `2x2` internal process time: `{cfg.mix_internal_process_time:.1f}`

Derived durations used directly in the MIP:

- `T_full = full_process_time + 2 * beta = {cfg.full_slot_duration:.1f}`
- `T_mix_boundary = mix_boundary_process_time + 2 * beta = {cfg.mix_boundary_cycle_duration:.1f}`
- `T_mix_internal = mix_internal_process_time + 2 * beta = {cfg.mix_internal_cycle_duration:.1f}`

## Main Variables

### 1. Shared-chamber 4x1 allocation

- `assign_full_j_m_f`: fixed-`4x1` product pair `j` assigned to chamber `m`, slot `f`
- `full_slot_used_m_f`: slot `f` on chamber `m` is used by `4x1`
- `full_pec_pairs_m_f`: slot `f` on chamber `m` consumes one PEC pair
- `full_after_mix_m_f`: slot `f` is placed after the `2x2` block on the same chamber

### 2. Shared-chamber 2x2 allocation

- `assign_mix_j_m_r`: fixed-`2x2` product pair `j` assigned to chamber `m`, position `r`
- `mix_pos_used_m_r`: position `r` is active
- `mix_cycle_used_m_c`: `2x2` cycle `c` exists
- `mix_active_m`: chamber `m` hosts a `2x2` sequence
- `mix_last_cycle_m_c`: cycle `c` is the final active cycle on chamber `m`

### 3. Time and completion variables

- `full_start_m_f`, `full_end_m_f`
- `mix_cycle_start_m_c`, `mix_cycle_end_m_c`
- `mix_block_end_m`
- `pair_completion_j`
- `c_max`

## Core Constraints

1. Every fixed-`4x1` product pair is assigned to exactly one shared-chamber `4x1` slot.
2. Every fixed-`2x2` product pair is assigned to exactly one shared-chamber `2x2` position.
3. Each used `4x1` slot satisfies `product pairs + PEC pairs = 2`, and PEC-only slots are forbidden.
4. Each chamber `2x2` sequence is modeled as a prefix of positions with derived lead, internal, and tail cycles.
5. PEC availability is global: every partial `4x1` slot consumes one PEC pair, and every active `2x2` sequence consumes two PEC pairs.
6. A chamber may contain both modes, but every `4x1` slot must lie entirely before or after the contiguous `2x2` block on that chamber.
7. A `4x1` pair completes at the end of its assigned slot; a `2x2` pair completes at the end of the next cycle because its second pass finishes there.
8. The objective is `min c_max`.

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
    parser.add_argument("--total_wafers", type=int, default=20)
    parser.add_argument("--pec_pool_size", type=int, default=8)
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

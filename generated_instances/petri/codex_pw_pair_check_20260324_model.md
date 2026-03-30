# Dual-Source Mixed-Flow Semiconductor Cluster Scheduling MIP

This file documents the exact MIP generated for `codex_pw_pair_check_20260324.lp`.

## Device Interpretation

The generated model follows the dual-source mixed-flow semiconductor cluster tool described in the supplied materials:

- shared rotary chambers: `CH2` and `CH3`
- product flow: `LP -> ATR -> AL -> ATR -> LLupper -> VTR -> CH -> VTR -> LLlower -> ATR -> LP`
- PEC flow: `PEC storage -> VTR -> CH -> VTR -> PEC storage`
- both `CH2` and `CH3` may execute `4x1` and `2x2`, but the two modes cannot overlap on the same chamber

## Corrected Input Semantics

This version no longer starts from pre-built product pairs. Instead, the input is an arbitrary number of product wafers for the two process modes:

- `4x1` mode wafers: `3`
- `2x2` mode wafers: `5`
- total product wafers: `8`
- PEC wafers available: `12`

The MIP first assigns individual wafers to mode-consistent PW pairs:

1. `4x1` wafers can only be grouped with other `4x1` product wafers in the same PW pair.
2. `2x2` wafers can only be grouped with other `2x2` product wafers in the same PW pair.
3. If one mode has an odd number of product wafers, the last PW pair of that mode becomes `1 product wafer + 1 PEC wafer`.

PW-pair structure implied by the current instance:

- `4x1` product wafers: 3 (W1, W2, W3)
- `4x1` PW pair slots: 2
  - Pair 1: 2 product wafers
  - Pair 2: 1 product wafer + 1 PEC wafer
- `2x2` product wafers: 5 (W4, W5, W6, W7, W8)
- `2x2` PW pair slots: 3
  - Pair 1: 2 product wafers
  - Pair 2: 2 product wafers
  - Pair 3: 1 product wafer + 1 PEC wafer

## Scheduling Semantics

After PW-pair formation, the chamber scheduling layer is modeled exactly:

- `4x1`: each used chamber slot contains exactly 2 PW pairs. If only 1 product-carrying `4x1` PW pair is assigned to a slot, the remaining PW pair is a pure PEC pair.
- `2x2`: product-carrying `2x2` PW pairs form an ordered sequence. Each active sequence uses one pure PEC pair at the head and one pure PEC pair at the tail.
- every product wafer inherits the completion time of the PW pair to which it is assigned

## Size

- chambers: `CH2, CH3`
- `4x1` PW pairs: `2`
- `2x2` PW pairs: `3`
- `4x1` slot upper bound per chamber: `3`
- `2x2` position upper bound per chamber: `3`
- `2x2` cycle upper bound per chamber: `4`
- internal PEC wafers forced by odd pair formation: `2`

## Timing Parameters

- Big-M: `10000.0`
- chamber transfer gap `mu`: `6.0`
- aggregated PW-pair transfer time `beta`: `20.0`
- `4x1` chamber process time: `80.0`
- `2x2` boundary process time: `30.0`
- `2x2` internal process time: `30.0`

Derived durations used directly in the MIP:

- `T_full = full_process_time + 2 * beta = 120.0`
- `T_mix_boundary = mix_boundary_process_time + 2 * beta = 70.0`
- `T_mix_internal = mix_internal_process_time + 2 * beta = 70.0`

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

- LP model: `codex_pw_pair_check_20260324.lp`
- Model description: `codex_pw_pair_check_20260324_model.md`

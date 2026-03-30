# Dual-Source Mixed-Flow Semiconductor Cluster Scheduling MIP

This file documents the exact MIP generated for `sanity_modes.lp`.

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

- product wafers: `8`
- product pairs: `4`
- PEC wafers: `8`
- PEC pairs: `4`
- chambers: `CH2, CH3`
- 4x1 slot upper bound per chamber: `2`
- 2x2 position upper bound per chamber: `2`
- 2x2 cycle upper bound per chamber: `3`

## Fixed Product Modes

- Pair 1: 2x2
- Pair 2: 4x1
- Pair 3: 2x2
- Pair 4: 4x1

Mode counts:

- `4x1` product pairs: `2`
- `2x2` product pairs: `2`

## Timing Parameters

- Big-M: `10000.0`
- chamber transfer gap `mu`: `6.0`
- aggregated pair transfer time `beta`: `20.0`
- `4x1` chamber process time: `80.0`
- `2x2` boundary process time: `30.0`
- `2x2` internal process time: `30.0`

Derived durations used directly in the MIP:

- `T_full = full_process_time + 2 * beta = 120.0`
- `T_mix_boundary = mix_boundary_process_time + 2 * beta = 70.0`
- `T_mix_internal = mix_internal_process_time + 2 * beta = 70.0`

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

- LP model: `sanity_modes.lp`
- Model description: `sanity_modes_model.md`

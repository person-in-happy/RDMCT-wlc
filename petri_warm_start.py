"""Structure-preserving binary-skeleton warm starts for Petri MIPs.

The unrestricted mixed-resource MIP has thousands of interchangeable binary
assignment, activation, epoch, slot, and resource-order decisions.  SCIP can
spend a long time before it reaches its first feasible schedule.  This module
builds a temporary copy, fixes a structure-aware subset of high-confidence
binary decisions, solves that reduced copy, and writes the resulting feasible
assignment as a SCIP solution file.  The original MIP remains unrestricted when
it consumes the incumbent, so the global optimum is unchanged.
"""

import hashlib
import json
import math
import time
from collections import OrderedDict
from pathlib import Path

from petri_mip_generator import PetriMIPConfig, _canonical_cleaning_layout, build_petri_mip_model
from scip_imports import scip

SPBS_ROLE_NAMES = (
    "assignment",
    "activation",
    "cleaning_epoch",
    "loadlock_slot",
    "low_risk_resource_order",
    "high_risk_resource_order",
    "timing_or_other",
)

SPBS_ROLE_CONFIDENCE = {
    "assignment": 1.00,
    "activation": 0.95,
    "cleaning_epoch": 0.95,
    "loadlock_slot": 0.80,
    "low_risk_resource_order": 0.70,
    "high_risk_resource_order": 0.35,
    "timing_or_other": 0.00,
}

SPBS_ROLE_FIX_POLICY = {
    "assignment": "fix",
    "activation": "fix",
    "cleaning_epoch": "fix",
    "loadlock_slot": "fix",
    "low_risk_resource_order": "fix",
    "high_risk_resource_order": "profile-dependent",
    "timing_or_other": "free",
}


def _sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _warm_start_paths(output_dir, instance_name):
    stem = Path(instance_name).stem
    output_path = Path(output_dir)
    return (
        output_path / f"{stem}_warmstart.sol",
        output_path / f"{stem}_warmstart.meta.json",
        output_path / instance_name,
    )


def find_compatible_mixed_warm_start(output_dir, instance_name):
    """Return a cached start only when it was built for the exact LP bytes."""
    solution_path, metadata_path, instance_path = _warm_start_paths(
        output_dir, instance_name
    )
    if not solution_path.is_file() or not metadata_path.is_file() or not instance_path.is_file():
        return None
    try:
        with metadata_path.open("r", encoding="utf-8") as handle:
            metadata = json.load(handle)
        if metadata.get("instance_sha256") != _sha256_file(instance_path):
            return None
    except (OSError, ValueError, TypeError):
        return None
    return str(solution_path)


def _fix_binary(model, variables, name, value):
    variable = variables.get(name)
    if variable is not None:
        model.chgVarLb(variable, float(value))
        model.chgVarUb(variable, float(value))


def _fix_unary_order(model, variables, prefix, model_order, desired_order):
    rank = {name: index for index, name in enumerate(desired_order)}
    for left_index, left_name in enumerate(model_order):
        for right_name in model_order[left_index + 1 :]:
            name = f"{prefix}_{left_name}_{right_name}"
            if name in variables:
                _fix_binary(model, variables, name, rank[left_name] < rank[right_name])


def _spbs_role_from_var_name(name):
    """Map a Petri binary variable to a structure role used by SPBS.

    The role matrix is intentionally coarser than the variable names: it only
    distinguishes assignment, activation, cleaning epochs, slot choices, and
    two levels of resource-order risk.  High-risk VTR order binaries are kept
    profile-dependent because fully fixing them can create artificial
    cross-resource precedence cycles in dense mixed instances.
    """
    if name.startswith(("wafer_to_", "assign_full_", "assign_mix_")):
        return "assignment"
    if name.startswith(
        (
            "full_batch_used_",
            "full_batch_tail_",
            "full_filler_side_",
            "mix_pos_used_",
            "mix_cycle_used_",
            "mix_active_",
            "mix_last_cycle_",
            "mix_last_pos_",
            "full_adjacent_same_epoch_",
            "full_tail_mix_same_epoch_",
        )
    ):
        return "activation"
    if name.startswith(
        (
            "clean_active_",
            "process_epoch_used_",
            "full_batch_epoch_",
            "mix_block_epoch_",
            "mix_cycle_epoch_",
        )
    ):
        return "cleaning_epoch"
    if name.startswith(("llupper_slot_assign_", "lllower_slot_assign_")):
        return "loadlock_slot"
    if name.startswith(("seq_atr_action_", "seq_al_", "seq_llupper_", "seq_lllower_")):
        return "low_risk_resource_order"
    if name.startswith("seq_vtr_action_"):
        return "high_risk_resource_order"
    return "timing_or_other"


def _is_binary_var(variable):
    try:
        label = str(variable.vtype()).upper()
    except Exception:
        try:
            label = str(variable.getType()).upper()
        except Exception:
            label = ""
    return "BINARY" in label


def _is_fixed_var(variable):
    try:
        return abs(float(variable.getLbGlobal()) - float(variable.getUbGlobal())) <= 1e-9
    except Exception:
        try:
            return abs(float(variable.getLbLocal()) - float(variable.getUbLocal())) <= 1e-9
        except Exception:
            return False


def _spbs_binary_structure_summary(variables, profile_name):
    """Summarize the implicit structure-feature matrix for binary variables.

    The full matrix is one row per binary variable with role one-hot columns,
    a role confidence score, and a policy indicator.  The temporary start
    solver only needs the role decisions, so we store an auditable summary in
    metadata instead of materializing a large dense matrix.
    """
    role_counts = OrderedDict((role, 0) for role in SPBS_ROLE_NAMES)
    fixed_counts = OrderedDict((role, 0) for role in SPBS_ROLE_NAMES)
    for name, variable in variables.items():
        if not _is_binary_var(variable):
            continue
        role = _spbs_role_from_var_name(name)
        role_counts[role] += 1
        if _is_fixed_var(variable):
            fixed_counts[role] += 1
    binary_count = int(sum(role_counts.values()))
    fixed_count = int(sum(fixed_counts.values()))
    return {
        "strategy": "SPBS",
        "profile": profile_name,
        "role_names": list(SPBS_ROLE_NAMES),
        "role_confidence": dict(SPBS_ROLE_CONFIDENCE),
        "role_fix_policy": dict(SPBS_ROLE_FIX_POLICY),
        "binary_variables": binary_count,
        "fixed_binary_variables": fixed_count,
        "free_binary_variables": binary_count - fixed_count,
        "role_counts": dict(role_counts),
        "fixed_role_counts": dict(fixed_counts),
    }


def _strip_secondary_stability_constraints(model):
    """Drop secondary-only quadratic auxiliaries from feasibility submodels."""
    prefixes = (
        "schedule_wait_def_",
        "schedule_wait_square_def_",
        "chamber_nonprocess_wait_",
    )
    removable = [
        constraint
        for constraint in model.getConss()
        if constraint.name == "schedule_stability_def"
        or constraint.name.startswith(prefixes)
    ]
    for constraint in removable:
        model.delCons(constraint)
    return len(removable)


def _pair_members(cfg, mode, pair_id):
    wafer_ids = cfg.full_wafer_ids if mode == "full" else cfg.mix_wafer_ids
    start = 2 * (pair_id - 1)
    return list(wafer_ids[start : start + 2])


def _canonical_pairs_by_pm(cfg):
    pairs_by_pm = {pm_id: [] for pm_id in cfg.pm_ids}
    for pair_id in cfg.mix_pair_ids:
        pm_id = cfg.pm_ids[(pair_id - 1) % len(cfg.pm_ids)]
        pairs_by_pm[pm_id].append(pair_id)
    return pairs_by_pm


def _canonical_full_pairs_by_batch(cfg):
    pairs_by_batch = {(pm_id, batch): [] for batch in range(1, cfg.num_full_batches_per_pm + 1) for pm_id in cfg.pm_ids}
    slots = [
        (pm_id, batch, side)
        for batch in range(1, cfg.num_full_batches_per_pm + 1)
        for pm_id in cfg.pm_ids
        for side in (1, 2)
    ]
    for pair_id, slot in zip(cfg.full_pair_ids, slots):
        pm_id, batch, side = slot
        pairs_by_batch[(pm_id, batch)].append((side, pair_id))
    return pairs_by_batch


def _mix_bridge_input_plan(cfg, mix_pairs_by_pm, last_full_batch):
    """Return an earliest-transition-first round-robin bridge-input order."""
    active_pm_ids = [pm_id for pm_id in cfg.pm_ids if mix_pairs_by_pm[pm_id]]
    transition_order = sorted(
        active_pm_ids,
        key=lambda pm_id: (last_full_batch.get(pm_id, 0), cfg.pm_ids.index(pm_id)),
    )
    plan = []
    scheduled = set()

    # Advance the chamber that entered 2x2 earlier first, then alternate by
    # chain position. This follows bridge readiness instead of starving one
    # chamber with a long burst on the other chamber.
    max_position = max((len(pair_ids) for pair_ids in mix_pairs_by_pm.values()), default=0)
    for position in range(2, max_position + 1):
        for pm_id in transition_order:
            item = (pm_id, position)
            if position <= len(mix_pairs_by_pm[pm_id]):
                plan.append(item)
                scheduled.add(item)
    return plan, transition_order


def _fix_cleaning_epochs(model, variables, cfg, full_pairs_by_batch, mix_pairs_by_pm):
    """Fix a valid full-before-mix epoch layout in the temporary start model."""
    canonical_layouts = _canonical_cleaning_layout(cfg)
    layouts = {}
    for pm_id in cfg.pm_ids:
        canonical = canonical_layouts[pm_id]
        segments = canonical["segments"]
        layouts[pm_id] = {
            "batch_epoch": canonical["full_epoch"],
            "mix_epoch": segments[0]["epoch"] if segments else 0,
            "segments": segments,
            "last_used_epoch": canonical["last_epoch"],
        }
    if cfg.cleaning_interval <= 0 or cfg.num_clean_slots_per_pm <= 0:
        return layouts

    epoch_count = cfg.num_clean_slots_per_pm + 1
    for pm_id in cfg.pm_ids:
        batch_epoch = layouts[pm_id]["batch_epoch"]
        segments = layouts[pm_id]["segments"]
        last_used_epoch = layouts[pm_id]["last_used_epoch"]
        mix_epochs = {segment["epoch"] for segment in segments}

        for epoch_id in range(1, epoch_count + 1):
            _fix_binary(
                model,
                variables,
                f"process_epoch_used_{pm_id}_{epoch_id}",
                epoch_id <= last_used_epoch,
            )
            _fix_binary(
                model,
                variables,
                f"mix_block_epoch_{pm_id}_{epoch_id}",
                epoch_id in mix_epochs,
            )
        for clean_slot in range(1, cfg.num_clean_slots_per_pm + 1):
            _fix_binary(
                model,
                variables,
                f"clean_active_{pm_id}_{clean_slot}",
                clean_slot < last_used_epoch,
            )
        for batch in range(1, cfg.num_full_batches_per_pm + 1):
            for epoch_id in range(1, epoch_count + 1):
                _fix_binary(
                    model,
                    variables,
                    f"full_batch_epoch_{pm_id}_{batch}_{epoch_id}",
                    batch_epoch.get(batch) == epoch_id,
                )
        cycle_epoch = {
            cycle: segment["epoch"]
            for segment in segments
            for cycle in segment["cycles"]
        }
        for cycle in range(1, cfg.num_mix_cycles_per_pm + 1):
            for epoch_id in range(1, epoch_count + 1):
                _fix_binary(
                    model,
                    variables,
                    f"mix_cycle_epoch_{pm_id}_{cycle}_{epoch_id}",
                    cycle_epoch.get(cycle) == epoch_id,
                )
    return layouts


def _fix_structural_assignment_and_activation(
    model,
    variables,
    cfg,
    full_pairs_by_batch,
    mix_pairs_by_pm,
    cleaning_layouts,
):
    """Tighten high-confidence SPBS assignment and activation roles.

    The production model already contains equality constraints that remove
    interchangeable pair labels.  Repeating those choices as variable bounds in
    the temporary start model gives presolve an explicit binary skeleton and
    makes the role-matrix metadata auditable.
    """
    full_pair_members = {}
    member_offset = 0
    for pair_id in cfg.full_pair_ids:
        load = cfg.full_pair_product_loads[pair_id]
        full_pair_members[pair_id] = set(
            cfg.full_wafer_ids[member_offset : member_offset + load]
        )
        member_offset += load
    for wafer_id in cfg.full_wafer_ids:
        for pair_id in cfg.full_pair_ids:
            _fix_binary(
                model,
                variables,
                f"wafer_to_full_pair_{wafer_id}_{pair_id}",
                wafer_id in full_pair_members[pair_id],
            )

    mix_pair_members = {}
    member_offset = 0
    for pair_id in cfg.mix_pair_ids:
        load = cfg.mix_pair_product_loads[pair_id]
        mix_pair_members[pair_id] = set(
            cfg.mix_wafer_ids[member_offset : member_offset + load]
        )
        member_offset += load
    for wafer_id in cfg.mix_wafer_ids:
        for pair_id in cfg.mix_pair_ids:
            _fix_binary(
                model,
                variables,
                f"wafer_to_mix_pair_{wafer_id}_{pair_id}",
                wafer_id in mix_pair_members[pair_id],
            )

    full_slot_by_pair = {
        pair_id: (pm_id, batch, side)
        for (pm_id, batch), side_pairs in full_pairs_by_batch.items()
        for side, pair_id in side_pairs
    }
    for pair_id in cfg.full_pair_ids:
        canonical_slot = full_slot_by_pair.get(pair_id)
        for pm_id in cfg.pm_ids:
            for batch in range(1, cfg.num_full_batches_per_pm + 1):
                for side in (1, 2):
                    _fix_binary(
                        model,
                        variables,
                        f"assign_full_{pair_id}_{pm_id}_{batch}_{side}",
                        canonical_slot == (pm_id, batch, side),
                    )

    mix_slot_by_pair = {
        pair_id: (pm_id, position)
        for pm_id, pair_ids in mix_pairs_by_pm.items()
        for position, pair_id in enumerate(pair_ids, start=1)
    }
    for pair_id in cfg.mix_pair_ids:
        canonical_slot = mix_slot_by_pair.get(pair_id)
        for pm_id in cfg.pm_ids:
            for position in range(1, cfg.num_mix_positions_per_pm + 1):
                _fix_binary(
                    model,
                    variables,
                    f"assign_mix_{pair_id}_{pm_id}_{position}",
                    canonical_slot == (pm_id, position),
                )

    for pm_id in cfg.pm_ids:
        active_full_batches = [
            batch
            for batch in range(1, cfg.num_full_batches_per_pm + 1)
            if full_pairs_by_batch[(pm_id, batch)]
        ]
        tail_batch = active_full_batches[-1] if active_full_batches else 0
        for batch in range(1, cfg.num_full_batches_per_pm + 1):
            active = batch in active_full_batches
            _fix_binary(model, variables, f"full_batch_used_{pm_id}_{batch}", active)
            _fix_binary(model, variables, f"full_batch_tail_{pm_id}_{batch}", batch == tail_batch)

        mix_count = len(mix_pairs_by_pm[pm_id])
        layout = cleaning_layouts.get(pm_id, {})
        active_mix_cycles = {
            cycle
            for segment in layout.get("segments", [])
            for cycle in segment["cycles"]
        }
        last_cycle = max(active_mix_cycles, default=0)
        for position in range(1, cfg.num_mix_positions_per_pm + 1):
            _fix_binary(
                model,
                variables,
                f"mix_pos_used_{pm_id}_{position}",
                position <= mix_count,
            )
            _fix_binary(
                model,
                variables,
                f"mix_last_pos_{pm_id}_{position}",
                bool(mix_count and position == mix_count),
            )
        for cycle in range(1, cfg.num_mix_cycles_per_pm + 1):
            _fix_binary(
                model,
                variables,
                f"mix_cycle_used_{pm_id}_{cycle}",
                cycle in active_mix_cycles,
            )
            _fix_binary(
                model,
                variables,
                f"mix_last_cycle_{pm_id}_{cycle}",
                bool(last_cycle and cycle == last_cycle),
            )
        _fix_binary(model, variables, f"mix_active_{pm_id}", mix_count > 0)


def _cap_noninitial_mix_bridge_waits(model, variables, cfg):
    """Cap avoidable 2x2 bridge waits only in the temporary start model.

    The first bridge is exempt because it includes the necessary mode-entry
    exchange identified in the Gantt chart. Later caps follow the physical
    two-chamber ATR/AL cadence rather than an arbitrary fixed constant.
    """
    pair_input_service = (
        cfg.atr_lp_al_total_time
        + 2.0 * cfg.aligner_time
        + cfg.al_exchange_time
        + cfg.atr_al_llupper_total_time
    )
    raw_cap = (
        2.0 * pair_input_service
        - cfg.mix_process_time
        - cfg.pair_transfer_time
        + cfg.atr_lllower_lp_total_time
    )
    quantum = max(cfg.pair_transfer_time, 1.0)
    wait_cap = math.ceil(raw_cap / quantum) * quantum

    for pm_id in cfg.pm_ids:
        for cycle in range(3, cfg.num_mix_cycles_per_pm + 1):
            bridge_start = variables.get(f"mix_bridge_start_{pm_id}_{cycle}")
            previous_cycle_end = variables.get(f"mix_cycle_end_{pm_id}_{cycle - 1}")
            if bridge_start is None or previous_cycle_end is None:
                continue
            model.addCons(
                bridge_start - previous_cycle_end <= wait_cap,
                name=f"warm_noninitial_bridge_wait_cap_{pm_id}_{cycle}",
            )


def _conservative_atr_pair_order(
    cfg,
    full_pairs_by_batch,
    mix_pairs_by_pm,
    cleaning_layouts=None,
):
    """Build a transition-aware ATR sequence.

    A chamber's first 2x2 pair is prepared while its final 4x1 batch is still
    finishing, then the chamber can enter its 2x2 head as soon as its own 4x1
    output has cleared. The two 2x2 chains are advanced by bridge readiness:
    prepare the pair required by one bridge and defer its released-pair return
    until after the following input preparation. This keeps ATR useful during
    2x2 and avoids both chamber starvation and a global full-return barrier.
    """
    actions = []
    al_order = []
    upper_order = []
    lower_order = []

    def add_input(mode, pair_id):
        action_prefix = "full" if mode == "full" else "mix"
        actions.append(f"{action_prefix}_al_service_{pair_id}")
        for wafer_id in _pair_members(cfg, mode, pair_id):
            al_order.append(str(wafer_id))
            upper_order.append((pair_id, wafer_id))

    def add_return(mode, pair_id):
        action_prefix = "pair" if mode == "full" else "mix_pair"
        actions.append(f"{action_prefix}_lllower_lp_{pair_id}")
        for wafer_id in _pair_members(cfg, mode, pair_id):
            lower_order.append((pair_id, wafer_id))

    active_full_batches = {
        pm_id: [
            batch
            for batch in range(1, cfg.num_full_batches_per_pm + 1)
            if full_pairs_by_batch[(pm_id, batch)]
        ]
        for pm_id in cfg.pm_ids
    }
    max_full_batch = max(
        (batches[-1] for batches in active_full_batches.values() if batches),
        default=0,
    )
    layouts = cleaning_layouts or _canonical_cleaning_layout(cfg)
    preloaded_mix_pairs = set()

    # Clear each full batch before inserting the next one. At a chamber's
    # full-to-mix boundary, stage its first 2x2 pair immediately after that
    # chamber's final full outputs return. Waiting for every chamber's full
    # returns creates an ATR/LL transition cycle on dense mixed workloads.
    for batch in range(1, max_full_batch + 1):
        for pm_id in cfg.pm_ids:
            side_pairs = dict(full_pairs_by_batch[(pm_id, batch)])
            for side in (1, 2):
                if side in side_pairs:
                    add_input("full", side_pairs[side])
        for pm_id in cfg.pm_ids:
            side_pairs = dict(full_pairs_by_batch[(pm_id, batch)])
            if (
                active_full_batches[pm_id]
                and batch == active_full_batches[pm_id][-1]
                and mix_pairs_by_pm[pm_id]
            ):
                first_segment = layouts.get(pm_id, {}).get("segments", [])[0]
                first_position = first_segment["positions"][0]
                first_mix_pair = mix_pairs_by_pm[pm_id][first_position - 1]
                add_input("mix", first_mix_pair)
                preloaded_mix_pairs.add(first_mix_pair)
            for side in (2, 1):
                if side in side_pairs:
                    add_return("full", side_pairs[side])
    max_mix_epoch = max(
        (
            segment["epoch"]
            for pm_id in cfg.pm_ids
            for segment in layouts.get(pm_id, {}).get("segments", [])
        ),
        default=0,
    )

    # A cleaning boundary splits a long 2x2 chain into independent PEC-bounded
    # segments.  The first pair of each segment is loaded by that segment's
    # head; internal pairs are loaded by bridge actions; the last bridge loads
    # tail PEC and releases the penultimate product pair; the segment tail
    # releases the final product pair.  Fix the ATR order to this same segmented
    # product flow so LLlower is not held hostage by the old single-tail chain.
    for epoch in range(1, max_mix_epoch + 1):
        for pm_id in cfg.pm_ids:
            pair_ids = mix_pairs_by_pm[pm_id]
            for segment in layouts.get(pm_id, {}).get("segments", []):
                if segment["epoch"] != epoch:
                    continue
                positions = segment["positions"]
                if not positions:
                    continue

                first_pair = pair_ids[positions[0] - 1]
                if first_pair not in preloaded_mix_pairs:
                    add_input("mix", first_pair)
                for bridge_index in range(1, len(positions) + 1):
                    if bridge_index < len(positions):
                        add_input("mix", pair_ids[positions[bridge_index] - 1])
                    unload_index = bridge_index - 2
                    if unload_index >= 0:
                        add_return("mix", pair_ids[positions[unload_index] - 1])
                add_return("mix", pair_ids[positions[-1] - 1])

    return actions, al_order, upper_order, lower_order


def _fix_conservative_mixed_resource_order(model, cfg, profile_name="spbs_full"):
    variables = {variable.name: variable for variable in model.getVars()}
    mix_pairs_by_pm = _canonical_pairs_by_pm(cfg)
    full_pairs_by_batch = _canonical_full_pairs_by_batch(cfg)
    fix_high_risk_vtr_order = profile_name == "spbs_full"
    fix_atr_al_order = profile_name in (
        "spbs_full",
        "spbs_relaxed_vtr",
        "spbs_relaxed_ll",
    )
    fix_loadlock_order = profile_name in ("spbs_full", "spbs_relaxed_vtr")
    fix_loadlock_slots = profile_name != "spbs_structure_only"
    cleaning_layouts = _fix_cleaning_epochs(
        model, variables, cfg, full_pairs_by_batch, mix_pairs_by_pm
    )
    _fix_structural_assignment_and_activation(
        model,
        variables,
        cfg,
        full_pairs_by_batch,
        mix_pairs_by_pm,
        cleaning_layouts,
    )
    if fix_loadlock_slots:
        for resource_name in ("llupper", "lllower"):
            for wafer_id in cfg.product_wafer_ids:
                chosen_slot = 1 if wafer_id % 2 else 2
                for slot_id in (1, 2):
                    _fix_binary(
                        model,
                        variables,
                        f"{resource_name}_slot_assign_{wafer_id}_{slot_id}",
                        slot_id == chosen_slot,
                    )
    if not fix_atr_al_order and not fix_loadlock_order:
        return _spbs_binary_structure_summary(variables, profile_name)

    # Do not impose an artificial upper bound on 2x2 bridge waiting here.
    # A complete LL slot pressure cycle now includes its post-pickup reset;
    # the former cadence-derived cap could cut off every schedule even though
    # the base MIP remained feasible.  Fixed physical resource orders already
    # provide enough reduction for this temporary feasibility solve.
    atr_order, al_order, upper_order, lower_order = _conservative_atr_pair_order(
        cfg,
        full_pairs_by_batch,
        mix_pairs_by_pm,
        cleaning_layouts,
    )

    atr_model_order = [f"full_al_service_{pair_id}" for pair_id in cfg.full_pair_ids]
    atr_model_order.extend(f"mix_al_service_{pair_id}" for pair_id in cfg.mix_pair_ids)
    atr_model_order.extend(f"pair_lllower_lp_{pair_id}" for pair_id in cfg.full_pair_ids)
    atr_model_order.extend(f"mix_pair_lllower_lp_{pair_id}" for pair_id in cfg.mix_pair_ids)
    if fix_atr_al_order:
        _fix_unary_order(model, variables, "seq_atr_action", atr_model_order, atr_order)
        _fix_unary_order(
            model,
            variables,
            "seq_al",
            [str(wafer_id) for wafer_id in cfg.product_wafer_ids],
            al_order,
        )

    if fix_loadlock_order:
        loadlock_orders = (("llupper", upper_order), ("lllower", lower_order))
    else:
        loadlock_orders = ()
    for resource_name, pair_order in loadlock_orders:
        labels = [str(wafer_id) for wafer_id in cfg.product_wafer_ids]
        order_by_slot = {1: [], 2: []}
        for _, wafer_id in pair_order:
            slot_id = 1 if wafer_id % 2 else 2
            order_by_slot[slot_id].append(str(wafer_id))

        for slot_id in (1, 2):
            rank = {label: index for index, label in enumerate(order_by_slot[slot_id])}
            for left_index, left_name in enumerate(labels):
                for right_name in labels[left_index + 1 :]:
                    name = f"seq_{resource_name}_{left_name}_{right_name}_{slot_id}"
                    if name in variables:
                        same_slot = left_name in rank and right_name in rank
                        _fix_binary(
                            model,
                            variables,
                            name,
                            same_slot and rank[left_name] < rank[right_name],
                        )

    if not fix_high_risk_vtr_order:
        return _spbs_binary_structure_summary(variables, profile_name)

    # Keep the temporary VTR order aligned with the conservative ATR order:
    # load a full-mode batch on all chambers, unload that batch on all chambers,
    # then load the next batch.  This avoids a cross-resource precedence cycle
    # where VTR starts PM2's next batch before PM3's previous output can return,
    # while ATR waits to insert that next batch until all previous outputs have
    # returned.
    vtr_model_order = []
    for pm_id in cfg.pm_ids:
        for segment in cleaning_layouts.get(pm_id, {}).get("segments", []):
            segment_id = segment["id"]
            vtr_model_order.extend(
                (
                    f"mix_head_{pm_id}_{segment_id}",
                    f"mix_tail_{pm_id}_{segment_id}",
                )
            )
        for batch in range(1, cfg.num_full_batches_per_pm + 1):
            vtr_model_order.extend(
                (
                    f"full_front_load_{pm_id}_{batch}",
                    f"full_back_load_{pm_id}_{batch}",
                    f"full_back_unload_{pm_id}_{batch}",
                    f"full_front_unload_{pm_id}_{batch}",
                )
            )
        vtr_model_order.extend(
            f"mix_bridge_{pm_id}_{cycle}"
            for cycle in range(2, cfg.num_mix_cycles_per_pm + 1)
        )
        for clean_slot in range(1, cfg.num_clean_slots_per_pm + 1):
            vtr_model_order.extend(
                (
                    f"clean_front_load_{pm_id}_{clean_slot}",
                    f"clean_back_load_{pm_id}_{clean_slot}",
                    f"clean_back_unload_{pm_id}_{clean_slot}",
                    f"clean_front_unload_{pm_id}_{clean_slot}",
                )
            )
    vtr_order = []
    active_full_batches = {
        pm_id: [
            batch
            for batch in range(1, cfg.num_full_batches_per_pm + 1)
            if full_pairs_by_batch[(pm_id, batch)]
        ]
        for pm_id in cfg.pm_ids
    }
    last_full_batch = {
        pm_id: (batches[-1] if batches else 0)
        for pm_id, batches in active_full_batches.items()
    }
    max_full_batch = max(last_full_batch.values(), default=0)
    cleaning_added = {pm_id: set() for pm_id in cfg.pm_ids}

    def add_cleaning(pm_id, clean_slot):
        if clean_slot in cleaning_added[pm_id]:
            return
        if clean_slot < 1 or clean_slot > cfg.num_clean_slots_per_pm:
            return
        vtr_order.extend(
            (
                f"clean_front_load_{pm_id}_{clean_slot}",
                f"clean_back_load_{pm_id}_{clean_slot}",
                f"clean_back_unload_{pm_id}_{clean_slot}",
                f"clean_front_unload_{pm_id}_{clean_slot}",
            )
        )
        cleaning_added[pm_id].add(clean_slot)

    def add_cleanings_before_epoch(pm_id, epoch):
        for clean_slot in range(1, max(1, int(epoch))):
            add_cleaning(pm_id, clean_slot)

    def add_mix_segment(pm_id, segment):
        segment_id = segment["id"]
        add_cleanings_before_epoch(pm_id, segment["epoch"])
        vtr_order.append(f"mix_head_{pm_id}_{segment_id}")
        for cycle in segment["cycles"][1:]:
            vtr_order.append(f"mix_bridge_{pm_id}_{cycle}")
        vtr_order.append(f"mix_tail_{pm_id}_{segment_id}")

    def add_mix_segments_for_epoch(epoch):
        for pm_id in cfg.pm_ids:
            for segment in cleaning_layouts.get(pm_id, {}).get("segments", []):
                if segment["epoch"] == epoch:
                    add_mix_segment(pm_id, segment)

    if not max_full_batch:
        max_mix_epoch = max(
            (
                segment["epoch"]
                for pm_id in cfg.pm_ids
                for segment in cleaning_layouts.get(pm_id, {}).get("segments", [])
            ),
            default=0,
        )
        for epoch in range(1, max_mix_epoch + 1):
            add_mix_segments_for_epoch(epoch)
    else:
        for pm_id in cfg.pm_ids:
            if full_pairs_by_batch[(pm_id, 1)]:
                first_epoch = cleaning_layouts.get(pm_id, {}).get("batch_epoch", {}).get(1, 1)
                add_cleanings_before_epoch(pm_id, first_epoch)
                vtr_order.extend(
                    (
                        f"full_front_load_{pm_id}_1",
                        f"full_back_load_{pm_id}_1",
                    )
                )

        for batch in range(2, max_full_batch + 1):
            for pm_id in cfg.pm_ids:
                if full_pairs_by_batch[(pm_id, batch - 1)]:
                    vtr_order.extend(
                        (
                            f"full_back_unload_{pm_id}_{batch - 1}",
                            f"full_front_unload_{pm_id}_{batch - 1}",
                        )
                    )
            for pm_id in cfg.pm_ids:
                if full_pairs_by_batch[(pm_id, batch)]:
                    current_epoch = cleaning_layouts.get(pm_id, {}).get("batch_epoch", {}).get(batch, 1)
                    add_cleanings_before_epoch(pm_id, current_epoch)
                    vtr_order.extend(
                        (
                            f"full_front_load_{pm_id}_{batch}",
                            f"full_back_load_{pm_id}_{batch}",
                        )
                    )

        for pm_id in cfg.pm_ids:
            if full_pairs_by_batch[(pm_id, max_full_batch)]:
                vtr_order.extend(
                    (
                        f"full_back_unload_{pm_id}_{max_full_batch}",
                        f"full_front_unload_{pm_id}_{max_full_batch}",
                    )
                )

        max_mix_epoch = max(
            (
                segment["epoch"]
                for pm_id in cfg.pm_ids
                for segment in cleaning_layouts.get(pm_id, {}).get("segments", [])
            ),
            default=0,
        )
        for epoch in range(1, max_mix_epoch + 1):
            add_mix_segments_for_epoch(epoch)
    vtr_order.extend(label for label in vtr_model_order if label not in set(vtr_order))
    _fix_unary_order(model, variables, "seq_vtr_action", vtr_model_order, vtr_order)
    return _spbs_binary_structure_summary(variables, profile_name)


def write_mixed_warm_start(output_dir, instance_name, cfg, time_limit=30.0):
    """Write a structure-preserving binary-skeleton primal start.

    SPBS first fixes assignment, activation, cleaning, slot, ATR/AL/LL order,
    and VTR order decisions. It progressively releases VTR and LL ordering,
    then all resource ordering and slot choices. Every profile solves only a
    temporary copy; the production MIP receives the result as an incumbent and
    remains free to prove or improve the optimum.
    """
    if not cfg.mix_wafer_ids:
        return None

    deadline = time.time() + float(time_limit)
    if cfg.total_product_wafers >= 32 and cfg.max_schedule_wait_time > 0:
        # A tight wait cap couples LL-slot choices and resource orders. The
        # legacy fixed-slot skeleton can be infeasible even when another
        # schedule satisfies the cap, so release it immediately and retain a
        # final unrestricted feasibility attempt.
        profiles = (
            ("spbs_structure_only", 0.60),
            ("spbs_unrestricted", None),
        )
    elif cfg.total_product_wafers >= 32:
        # Fixed global robot orders become brittle across several cleaning
        # epochs. Keep the high-confidence structural roles and LL-slot
        # symmetry breaking, while letting SCIP sequence the resources.
        profiles = (
            ("spbs_fixed_slots", 0.80),
            ("spbs_structure_only", None),
        )
    else:
        profiles = (
            ("spbs_full", 0.10),
            ("spbs_relaxed_vtr", 0.15),
            ("spbs_relaxed_ll", 0.45),
            ("spbs_fixed_slots", 0.15),
            ("spbs_structure_only", None),
        )
    total_time_limit = float(time_limit)
    profile_attempts = []
    for profile_name, budget_fraction in profiles:
        remaining = deadline - time.time()
        if remaining <= 1.0:
            break
        attempt_time_limit = remaining
        if budget_fraction is not None:
            attempt_time_limit = min(
                remaining,
                max(5.0, total_time_limit * budget_fraction),
            )
        model = build_petri_mip_model(cfg)
        structure_summary = None
        try:
            if profile_name == "spbs_unrestricted":
                variables = {variable.name: variable for variable in model.getVars()}
                structure_summary = _spbs_binary_structure_summary(
                    variables,
                    profile_name,
                )
            else:
                structure_summary = _fix_conservative_mixed_resource_order(
                    model,
                    cfg,
                    profile_name=profile_name,
                )
            stripped_stability_constraints = _strip_secondary_stability_constraints(model)
            structure_summary["stripped_stability_constraints"] = (
                stripped_stability_constraints
            )
            # A warm start needs one physically feasible schedule, not a good
            # makespan proof. The unrestricted production model keeps its
            # original min-c_max objective after this incumbent is imported.
            model.setObjective(0.0, "minimize")
            model.hideOutput(True)
            model.setEmphasis(scip.SCIP_PARAMEMPHASIS.FEASIBILITY)
            model.setHeuristics(scip.SCIP_PARAMSETTING.AGGRESSIVE)
            model.setRealParam("limits/time", float(attempt_time_limit))
            model.setIntParam("limits/solutions", 1)
            # The temporary model has its important discrete choices fixed above.
            # Deep exhaustive presolve and symmetry detection can otherwise consume
            # the entire warm-start budget before SCIP even attempts feasibility on
            # large cleaning instances.
            model.setPresolve(scip.SCIP_PARAMSETTING.FAST)
            model.setIntParam("presolving/maxrounds", 30)
            model.setIntParam("propagating/probing/maxprerounds", 0)
            model.setIntParam("misc/usesymmetry", 0)
            model.setIntParam("separating/maxroundsroot", 0)
            model.optimize()
            solution = model.getBestSol()
            attempt = {
                "profile": profile_name,
                "status": str(model.getStatus()),
                "solving_time": float(model.getSolvingTime()),
                "nodes": int(model.getNNodes()),
                "solutions": int(model.getNSols()),
                "structure_summary": structure_summary,
            }
            profile_attempts.append(attempt)
            if solution is None:
                print(
                    "warning: SPBS Petri warm-start profile ended without a solution: "
                    f"profile={profile_name}, status={model.getStatus()}, "
                    f"time={model.getSolvingTime():.3f}s, nodes={model.getNNodes()}"
                )
                continue

            output_path = Path(output_dir)
            output_path.mkdir(parents=True, exist_ok=True)
            warm_start_path, metadata_path, instance_path = _warm_start_paths(
                output_dir, instance_name
            )
            model.writeSol(solution, str(warm_start_path))
            if instance_path.is_file():
                with metadata_path.open("w", encoding="utf-8") as handle:
                    json.dump(
                        {
                            "instance_file": Path(instance_name).name,
                            "instance_sha256": _sha256_file(instance_path),
                            "warm_start_strategy": "SPBS",
                            "accepted_profile": profile_name,
                            "profile_attempts": profile_attempts,
                        },
                        handle,
                        ensure_ascii=False,
                        indent=2,
                    )
            return str(warm_start_path)
        finally:
            model.freeProb()

    return None


def polish_mixed_warm_start(output_dir, instance_name, cfg, time_limit=1800.0):
    """Compact a compatible SPBS start without changing its discrete structure."""
    warm_start_path = find_compatible_mixed_warm_start(output_dir, instance_name)
    if not warm_start_path:
        return None

    deadline = time.time() + float(time_limit)
    model = build_petri_mip_model(cfg)
    try:
        stripped_count = _strip_secondary_stability_constraints(model)
        initial_solution = model.readSolFile(str(warm_start_path))
        if not model.addSol(initial_solution, free=False):
            raise RuntimeError("the cached SPBS solution is not feasible in the generated model")

        discrete_values = {
            variable.name: round(float(model.getSolVal(initial_solution, variable)))
            for variable in model.getVars()
            if variable.vtype() in {"BINARY", "INTEGER", "IMPLINT"}
        }
        for variable in model.getVars():
            value = discrete_values.get(variable.name)
            if value is None:
                continue
            model.chgVarLb(variable, value)
            model.chgVarUb(variable, value)

        variables = {variable.name: variable for variable in model.getVars()}
        cmax_var = variables.get("c_max")
        if cmax_var is None:
            raise RuntimeError("generated Petri model has no c_max variable")
        initial_cmax = float(model.getSolVal(initial_solution, cmax_var))

        model.hideOutput(True)
        model.setPresolve(scip.SCIP_PARAMSETTING.FAST)
        model.setHeuristics(scip.SCIP_PARAMSETTING.OFF)
        model.setIntParam("misc/usesymmetry", 0)
        model.setIntParam("separating/maxroundsroot", 0)
        model.setIntParam("limits/solutions", -1)
        model.setObjective(cmax_var, "minimize")
        phase1_budget = max(1.0, 0.70 * max(1.0, deadline - time.time()))
        model.setRealParam("limits/time", phase1_budget)
        model.optimize()
        phase1_solution = model.getBestSol()
        if phase1_solution is None:
            raise RuntimeError(
                "fixed-structure makespan polishing returned no solution "
                f"(status={model.getStatus()}, time={model.getSolvingTime():.3f}s, "
                f"nodes={model.getNNodes()})"
            )
        polished_cmax = float(model.getSolVal(phase1_solution, cmax_var))
        phase1_status = str(model.getStatus())

        final_solution = phase1_solution
        linear_wait_value = None
        remaining = deadline - time.time()
        if remaining > 1.0:
            model.freeTransform()
            variables = {variable.name: variable for variable in model.getVars()}
            cmax_var = variables["c_max"]
            model.addCons(
                cmax_var <= polished_cmax + 1e-6,
                name="warmstart_polish_cmax_fix",
            )
            wait_prefixes = (
                "llupper_wait_",
                "lllower_wait_",
                "full_pair_post_process_wait_",
                "mix_pair_post_process_wait_",
                "chamber_idle_total_",
            )
            wait_variables = [
                variable
                for variable in model.getVars()
                if variable.name.startswith(wait_prefixes)
            ]
            linear_wait_expr = scip.quicksum(wait_variables)
            model.setObjective(linear_wait_expr, "minimize")
            model.setRealParam("limits/time", max(1.0, remaining))
            model.optimize()
            if model.getBestSol() is not None:
                final_solution = model.getBestSol()
                linear_wait_value = float(
                    sum(model.getSolVal(final_solution, variable) for variable in wait_variables)
                )

        model.writeSol(final_solution, str(warm_start_path))
        _, metadata_path, instance_path = _warm_start_paths(output_dir, instance_name)
        metadata = {}
        if metadata_path.is_file():
            with metadata_path.open("r", encoding="utf-8") as handle:
                metadata = json.load(handle)
        metadata.update(
            {
                "instance_file": Path(instance_name).name,
                "instance_sha256": _sha256_file(instance_path),
                "polishing": {
                    "fixed_discrete_variables": len(discrete_values),
                    "stripped_stability_constraints": stripped_count,
                    "initial_cmax": initial_cmax,
                    "polished_cmax": polished_cmax,
                    "phase1_status": phase1_status,
                    "linear_wait_value": linear_wait_value,
                },
            }
        )
        with metadata_path.open("w", encoding="utf-8") as handle:
            json.dump(metadata, handle, ensure_ascii=False, indent=2)
        return str(warm_start_path)
    finally:
        model.freeProb()


# Backward-compatible name used by early experiments.
write_pure_mix_warm_start = write_mixed_warm_start

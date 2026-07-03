"""Construct conservative primal starts for large pure-2x2 Petri MIPs.

The unrestricted mixed-resource MIP has thousands of interchangeable order
binaries.  SCIP can spend a long time before it reaches its first feasible
schedule.  This module fixes only a conservative physical order in a temporary
copy, solves that copy quickly, and writes the resulting feasible assignment as
a SCIP solution file.  The original MIP remains unrestricted when it consumes
the start.
"""

import hashlib
import json
import math
from pathlib import Path

from petri_mip_generator import PetriMIPConfig, build_petri_mip_model


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
    if cfg.cleaning_interval <= 0 or cfg.num_clean_slots_per_pm <= 0:
        return

    epoch_count = cfg.num_clean_slots_per_pm + 1
    for pm_id in cfg.pm_ids:
        batch_epoch = {}
        epoch = 1
        used_in_epoch = 0
        active_batches = [
            batch
            for batch in range(1, cfg.num_full_batches_per_pm + 1)
            if full_pairs_by_batch[(pm_id, batch)]
        ]
        for batch in active_batches:
            if used_in_epoch >= cfg.cleaning_interval:
                epoch += 1
                used_in_epoch = 0
            batch_epoch[batch] = epoch
            used_in_epoch += 1

        mix_cycle_count = len(mix_pairs_by_pm[pm_id]) + 1 if mix_pairs_by_pm[pm_id] else 0
        if mix_cycle_count > cfg.cleaning_interval:
            raise ValueError(
                f"CH{pm_id} 2x2 chain has {mix_cycle_count} cycles, exceeding "
                f"cleaning_interval={cfg.cleaning_interval}."
            )
        mix_epoch = 0
        if mix_cycle_count:
            if used_in_epoch + mix_cycle_count > cfg.cleaning_interval:
                epoch += 1
            mix_epoch = epoch

        last_used_epoch = max([0, *batch_epoch.values(), mix_epoch])
        if last_used_epoch > epoch_count:
            raise ValueError(
                f"Warm-start epoch layout for CH{pm_id} needs {last_used_epoch} epochs; "
                f"model provides {epoch_count}."
            )

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
                bool(mix_epoch and epoch_id == mix_epoch),
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
        for cycle in range(1, cfg.num_mix_cycles_per_pm + 1):
            cycle_active = 1 <= cycle <= mix_cycle_count
            for epoch_id in range(1, epoch_count + 1):
                _fix_binary(
                    model,
                    variables,
                    f"mix_cycle_epoch_{pm_id}_{cycle}_{epoch_id}",
                    bool(cycle_active and epoch_id == mix_epoch),
                )


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


def _conservative_atr_pair_order(cfg, full_pairs_by_batch, mix_pairs_by_pm):
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
    last_full_batch = {
        pm_id: (batches[-1] if batches else 0)
        for pm_id, batches in active_full_batches.items()
    }
    max_full_batch = max(last_full_batch.values(), default=0)
    mix_head_prepared = set()

    def prepare_mix_head(pm_id):
        pair_ids = mix_pairs_by_pm[pm_id]
        if pair_ids and pm_id not in mix_head_prepared:
            add_input("mix", pair_ids[0])
            mix_head_prepared.add(pm_id)

    # Prime the first 4x1 batch on every active chamber. For each later batch,
    # keep exactly one pair of lookahead. When a chamber has no next 4x1 batch,
    # prepare its 2x2 head before returning its final 4x1 output; LLupper and
    # LLlower are independent, so this overlaps mode transition without
    # creating the former "all 4x1 wafers must reach LP first" barrier.
    if max_full_batch:
        for pm_id in cfg.pm_ids:
            side_pairs = dict(full_pairs_by_batch[(pm_id, 1)])
            for side in (1, 2):
                if side in side_pairs:
                    add_input("full", side_pairs[side])
        for pm_id in cfg.pm_ids:
            if not active_full_batches[pm_id]:
                prepare_mix_head(pm_id)
    else:
        for pm_id in cfg.pm_ids:
            prepare_mix_head(pm_id)

    for batch in range(2, max_full_batch + 1):
        for pm_id in cfg.pm_ids:
            next_pairs = dict(full_pairs_by_batch[(pm_id, batch)])
            previous_pairs = dict(full_pairs_by_batch[(pm_id, batch - 1)])
            if 1 in next_pairs:
                add_input("full", next_pairs[1])
            elif previous_pairs and last_full_batch[pm_id] == batch - 1:
                prepare_mix_head(pm_id)
            if 2 in previous_pairs:
                add_return("full", previous_pairs[2])
            if 1 in previous_pairs:
                add_return("full", previous_pairs[1])
            if 2 in next_pairs:
                add_input("full", next_pairs[2])

    # Chambers whose final 4x1 batch is on the last global batch transition
    # here. The first 2x2 pair is deliberately placed before those final
    # outputs return to LP.
    if max_full_batch:
        for pm_id in cfg.pm_ids:
            if last_full_batch[pm_id] != max_full_batch:
                continue
            side_pairs = dict(full_pairs_by_batch[(pm_id, max_full_batch)])
            prepare_mix_head(pm_id)
            for side in (2, 1):
                if side in side_pairs:
                    add_return("full", side_pairs[side])

    # Round-robin bridge preparation. Bridge ``position`` loads that position's
    # pair and, from position 3 onward, releases the pair two positions behind.
    # Returning that released pair before preparing the other chamber's bridge
    # prevents LLlower blockage and gives ATR a nearly continuous useful chain.
    bridge_plan, transition_order = _mix_bridge_input_plan(
        cfg,
        mix_pairs_by_pm,
        last_full_batch,
    )
    pending_return = None
    for plan_index, (pm_id, position) in enumerate(bridge_plan):
        pair_ids = mix_pairs_by_pm[pm_id]
        add_input("mix", pair_ids[position - 1])
        if pending_return is not None:
            add_return("mix", pending_return)
            pending_return = None
        if position < 3:
            continue
        released_pair = pair_ids[position - 3]
        has_next_input = plan_index + 1 < len(bridge_plan)
        if has_next_input:
            # LLupper and LLlower are independent. During the fixed bridge
            # sequence, prepare the following bridge input first, then
            # clear the output released by this bridge. The pending LLlower
            # output is returned before the following VTR bridge, so it cannot
            # block that bridge, while one ATR return duration is hidden.
            pending_return = released_pair
        else:
            add_return("mix", released_pair)
    if pending_return is not None:
        add_return("mix", pending_return)

    # The bridge that introduces tail PEC releases the penultimate pair; the
    # tail action then releases the final pair. Match the same chamber rotation
    # used by the VTR order below.
    for pm_id in transition_order:
        pair_ids = mix_pairs_by_pm[pm_id]
        if len(pair_ids) >= 2:
            add_return("mix", pair_ids[-2])
    for pm_id in transition_order:
        pair_ids = mix_pairs_by_pm[pm_id]
        if pair_ids:
            add_return("mix", pair_ids[-1])

    return actions, al_order, upper_order, lower_order


def _fix_conservative_mixed_resource_order(model, cfg):
    variables = {variable.name: variable for variable in model.getVars()}
    mix_pairs_by_pm = _canonical_pairs_by_pm(cfg)
    full_pairs_by_batch = _canonical_full_pairs_by_batch(cfg)
    _fix_cleaning_epochs(model, variables, cfg, full_pairs_by_batch, mix_pairs_by_pm)
    # Do not impose an artificial upper bound on 2x2 bridge waiting here.
    # A complete LL slot pressure cycle now includes its post-pickup reset;
    # the former cadence-derived cap could cut off every schedule even though
    # the base MIP remained feasible.  Fixed physical resource orders already
    # provide enough reduction for this temporary feasibility solve.
    atr_order, al_order, upper_order, lower_order = _conservative_atr_pair_order(
        cfg,
        full_pairs_by_batch,
        mix_pairs_by_pm,
    )

    atr_model_order = [f"full_al_service_{pair_id}" for pair_id in cfg.full_pair_ids]
    atr_model_order.extend(f"mix_al_service_{pair_id}" for pair_id in cfg.mix_pair_ids)
    atr_model_order.extend(f"pair_lllower_lp_{pair_id}" for pair_id in cfg.full_pair_ids)
    atr_model_order.extend(f"mix_pair_lllower_lp_{pair_id}" for pair_id in cfg.mix_pair_ids)
    _fix_unary_order(model, variables, "seq_atr_action", atr_model_order, atr_order)
    _fix_unary_order(
        model,
        variables,
        "seq_al",
        [str(wafer_id) for wafer_id in cfg.product_wafer_ids],
        al_order,
    )

    for resource_name, pair_order in (("llupper", upper_order), ("lllower", lower_order)):
        labels = [str(wafer_id) for wafer_id in cfg.product_wafer_ids]
        order_by_slot = {1: [], 2: []}
        for _, wafer_id in pair_order:
            slot_id = 1 if wafer_id % 2 else 2
            order_by_slot[slot_id].append(str(wafer_id))

        for wafer_id in cfg.product_wafer_ids:
            chosen_slot = 1 if wafer_id % 2 else 2
            for slot_id in (1, 2):
                _fix_binary(
                    model,
                    variables,
                    f"{resource_name}_slot_assign_{wafer_id}_{slot_id}",
                    slot_id == chosen_slot,
                )

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

    # Pipeline 4x1 and transition each chamber independently. As soon as one
    # chamber finishes its own final 4x1 unload, execute its 2x2 head instead
    # of waiting for every 4x1 wafer from the other chamber to return to LP.
    vtr_model_order = []
    for pm_id in cfg.pm_ids:
        vtr_model_order.extend((f"mix_head_{pm_id}", f"mix_tail_{pm_id}"))
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
    mix_head_added = set()

    def add_mix_head(pm_id):
        if mix_pairs_by_pm[pm_id] and pm_id not in mix_head_added:
            vtr_order.append(f"mix_head_{pm_id}")
            mix_head_added.add(pm_id)

    if not max_full_batch:
        for pm_id in cfg.pm_ids:
            add_mix_head(pm_id)
    else:
        for pm_id in cfg.pm_ids:
            if full_pairs_by_batch[(pm_id, 1)]:
                vtr_order.extend(
                    (
                        f"full_front_load_{pm_id}_1",
                        f"full_back_load_{pm_id}_1",
                    )
                )
        for pm_id in cfg.pm_ids:
            if not active_full_batches[pm_id]:
                add_mix_head(pm_id)

    for batch in range(2, max_full_batch + 1):
        for pm_id in cfg.pm_ids:
            previous_active = bool(full_pairs_by_batch[(pm_id, batch - 1)])
            current_active = bool(full_pairs_by_batch[(pm_id, batch)])
            if previous_active:
                vtr_order.extend(
                    (
                        f"full_back_unload_{pm_id}_{batch - 1}",
                        f"full_front_unload_{pm_id}_{batch - 1}",
                    )
                )
            if current_active:
                vtr_order.extend(
                    (
                        f"full_front_load_{pm_id}_{batch}",
                        f"full_back_load_{pm_id}_{batch}",
                    )
                )
            elif previous_active and last_full_batch[pm_id] == batch - 1:
                add_mix_head(pm_id)

    if max_full_batch:
        for pm_id in cfg.pm_ids:
            if last_full_batch[pm_id] == max_full_batch:
                vtr_order.extend(
                    (
                        f"full_back_unload_{pm_id}_{max_full_batch}",
                        f"full_front_unload_{pm_id}_{max_full_batch}",
                    )
                )
                add_mix_head(pm_id)

    # Use the same readiness-oriented bridge plan as ATR: advance the chamber
    # that entered 2x2 earlier, then alternate the remaining chain positions.
    bridge_plan, transition_order = _mix_bridge_input_plan(
        cfg,
        mix_pairs_by_pm,
        last_full_batch,
    )
    for pm_id, cycle in bridge_plan:
        vtr_order.append(f"mix_bridge_{pm_id}_{cycle}")
    for pm_id in transition_order:
        terminal_cycle = len(mix_pairs_by_pm[pm_id]) + 1
        if terminal_cycle >= 2:
            vtr_order.append(f"mix_bridge_{pm_id}_{terminal_cycle}")
    for pm_id in transition_order:
        if mix_pairs_by_pm[pm_id]:
            vtr_order.append(f"mix_tail_{pm_id}")
    vtr_order.extend(label for label in vtr_model_order if label not in set(vtr_order))
    _fix_unary_order(model, variables, "seq_vtr_action", vtr_model_order, vtr_order)


def write_mixed_warm_start(output_dir, instance_name, cfg, time_limit=30.0):
    """Write a conservative primal start for any instance containing 2x2."""
    if not cfg.mix_wafer_ids:
        return None

    model = build_petri_mip_model(cfg)
    try:
        _fix_conservative_mixed_resource_order(model, cfg)
        model.hideOutput(True)
        model.setRealParam("limits/time", float(time_limit))
        model.optimize()
        solution = model.getBestSol()
        if solution is None:
            return None
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
                    },
                    handle,
                    ensure_ascii=False,
                    indent=2,
                )
        return str(warm_start_path)
    finally:
        model.freeProb()


# Backward-compatible name used by early experiments.
write_pure_mix_warm_start = write_mixed_warm_start

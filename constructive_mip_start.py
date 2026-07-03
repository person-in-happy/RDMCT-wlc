import argparse
import json
from pathlib import Path

from path_utils import resolve_path
from petri_gantt import generate_gantt_charts_from_solution_file
from petri_mip_generator import PetriMIPConfig, build_petri_mip_model
from scip_imports import scip


def _set(vals, name, value):
    vals[name] = float(value)


def _maybe(vals, names, name, value):
    if name in names:
        vals[name] = float(value)


def _set_unary_orders(vals, names, prefix, tasks):
    for left_idx, (left_name, _, left_end, _) in enumerate(tasks):
        for right_name, right_start, _, _ in tasks[left_idx + 1:]:
            var_name = f"{prefix}_{left_name}_{right_name}"
            if var_name in names:
                vals[var_name] = 1.0 if left_end <= right_start else 0.0


def _set_parallel_orders(vals, names, slot_prefix, order_prefix, tasks, slot_count, assignment_fn):
    def normalize_slots(chosen):
        if chosen is None:
            return []
        if isinstance(chosen, int):
            return [chosen]
        return list(chosen)

    for task_name, _, _, active in tasks:
        chosen_slots = normalize_slots(assignment_fn(task_name)) if active else []
        for slot in range(1, slot_count + 1):
            var_name = f"{slot_prefix}_{task_name}_{slot}"
            if var_name in names:
                vals[var_name] = 1.0 if active and slot in chosen_slots else 0.0

    for slot in range(1, slot_count + 1):
        for left_idx, (left_name, _, left_end, _) in enumerate(tasks):
            if f"{slot_prefix}_{left_name}_{slot}" not in names:
                continue
            for right_name, right_start, _, _ in tasks[left_idx + 1:]:
                var_name = f"{order_prefix}_{left_name}_{right_name}_{slot}"
                if var_name in names:
                    vals[var_name] = 1.0 if left_end <= right_start else 0.0


def _set_pair_orders(vals, names, pair_intervals):
    def pair_key(item):
        name = item[0]
        prefix = name[:1]
        try:
            number = int(name[1:])
        except ValueError:
            number = 0
        family_rank = 0 if prefix == "F" else 1
        return family_rank, number

    items = sorted(pair_intervals.items(), key=pair_key)
    for left_idx, (left_name, left) in enumerate(items):
        for right_name, right in items[left_idx + 1:]:
            upper_var = f"llupper_pair_order_{left_name}_{right_name}"
            if upper_var in names:
                vals[upper_var] = 1.0 if left["upper_end"] <= right["upper_entry"] else 0.0
            lower_var = f"lllower_pair_order_{left_name}_{right_name}"
            if lower_var in names:
                vals[lower_var] = 1.0 if left["lower_exit"] <= right["lower_entry"] else 0.0


def build_mip_clean_20260508_start(model):
    """Construct a conservative feasible start for the 25x4x1 + 15x2x2 case."""
    cfg = PetriMIPConfig(
        num_pm=2,
        pec_pool_size=8,
        full_mode_wafers=25,
        mix_mode_wafers=15,
        total_wafers=0,
        cleaning_interval=10,
        cleaning_process_time=60.0,
    )
    names = {var.name for var in model.getVars()}
    vals = {}

    for w in cfg.product_wafer_ids:
        target_lp = 1 if w <= cfg.load_port_slots else 2
        for lp in range(1, cfg.load_ports + 1):
            _set(vals, f"product_lp_assign_{w}_{lp}", 1 if lp == target_lp else 0)

    for idx, w in enumerate(cfg.full_wafer_ids):
        pair_id = idx // 2 + 1
        for candidate in cfg.full_pair_ids:
            _set(vals, f"wafer_to_full_pair_{w}_{candidate}", 1 if candidate == pair_id else 0)
    for idx, w in enumerate(cfg.mix_wafer_ids):
        pair_id = idx // 2 + 1
        for candidate in cfg.mix_pair_ids:
            _set(vals, f"wafer_to_mix_pair_{w}_{candidate}", 1 if candidate == pair_id else 0)

    full_map = {
        1: (2, 1, 1), 2: (2, 1, 2), 3: (2, 2, 1), 4: (2, 2, 2),
        5: (2, 3, 1), 6: (2, 3, 2), 7: (2, 4, 1),
        8: (3, 1, 1), 9: (3, 1, 2), 10: (3, 2, 1), 11: (3, 2, 2),
        12: (3, 3, 1), 13: (3, 3, 2),
    }
    mix_map = {
        8: (2, 1), 1: (2, 2), 2: (2, 3), 3: (2, 4),
        4: (3, 1), 5: (3, 2), 6: (3, 3), 7: (3, 4),
    }
    used_batches_by_pm = {2: {1, 2, 3, 4}, 3: {1, 2, 3}}
    active_mix_pos_by_pm = {2: {1, 2, 3, 4}, 3: {1, 2, 3, 4}}
    active_mix_cycles_by_pm = {2: {1, 2, 3, 4, 5}, 3: {1, 2, 3, 4, 5}}

    for p in cfg.full_pair_ids:
        for m in cfg.pm_ids:
            for b in range(1, cfg.num_full_batches_per_pm + 1):
                for side in (1, 2):
                    _set(vals, f"assign_full_{p}_{m}_{b}_{side}", 1 if full_map[p] == (m, b, side) else 0)
    for p in cfg.mix_pair_ids:
        for m in cfg.pm_ids:
            for pos in range(1, cfg.num_mix_positions_per_pm + 1):
                _set(vals, f"assign_mix_{p}_{m}_{pos}", 1 if mix_map[p] == (m, pos) else 0)

    for m in cfg.pm_ids:
        tail_batch = max(used_batches_by_pm[m])
        for b in range(1, cfg.num_full_batches_per_pm + 1):
            _set(vals, f"full_batch_used_{m}_{b}", 1 if b in used_batches_by_pm[m] else 0)
            _set(vals, f"full_batch_tail_{m}_{b}", 1 if b == tail_batch else 0)
            for side in (1, 2):
                _set(vals, f"full_filler_side_{m}_{b}_{side}", 1 if (m, b, side) == (2, 4, 2) else 0)
        _set(vals, f"mix_active_{m}", 1)
        for pos in range(1, cfg.num_mix_positions_per_pm + 1):
            _set(vals, f"mix_pos_used_{m}_{pos}", 1 if pos in active_mix_pos_by_pm[m] else 0)
            _set(vals, f"mix_last_pos_{m}_{pos}", 1 if pos == 4 else 0)
        for cycle in range(1, cfg.num_mix_cycles_per_pm + 1):
            _set(vals, f"mix_cycle_used_{m}_{cycle}", 1 if cycle in active_mix_cycles_by_pm[m] else 0)
            _set(vals, f"mix_last_cycle_{m}_{cycle}", 1 if cycle == 5 else 0)
        for epoch in (1, 2):
            _maybe(vals, names, f"process_epoch_used_{m}_{epoch}", 1 if epoch == 1 else 0)
            _maybe(vals, names, f"mix_block_epoch_{m}_{epoch}", 1 if epoch == 1 else 0)
        _maybe(vals, names, f"clean_active_{m}_1", 0)
        for b in range(1, cfg.num_full_batches_per_pm + 1):
            for epoch in (1, 2):
                _maybe(vals, names, f"full_batch_epoch_{m}_{b}_{epoch}", 1 if b in used_batches_by_pm[m] and epoch == 1 else 0)
        for b in range(1, cfg.num_full_batches_per_pm):
            for epoch in (1, 2):
                active = b in used_batches_by_pm[m] and (b + 1) in used_batches_by_pm[m] and epoch == 1
                _maybe(vals, names, f"full_adjacent_same_epoch_{m}_{b}_{epoch}", 1 if active else 0)
        for b in range(1, cfg.num_full_batches_per_pm + 1):
            for epoch in (1, 2):
                active = b == tail_batch and epoch == 1
                _maybe(vals, names, f"full_tail_mix_same_epoch_{m}_{b}_{epoch}", 1 if active else 0)
        for cycle in range(1, cfg.num_mix_cycles_per_pm + 1):
            for epoch in (1, 2):
                _maybe(vals, names, f"mix_cycle_epoch_{m}_{cycle}_{epoch}", 1 if cycle in active_mix_cycles_by_pm[m] and epoch == 1 else 0)

    full_window = {}
    chamber_vtr_offset = 63.0
    full_base_by_pm = {2: 500.0, 3: 500.0 + chamber_vtr_offset}
    full_batch_stride = 473.0
    full_unload_candidates = []
    for m in (2, 3):
        for idx, b in enumerate(sorted(used_batches_by_pm[m])):
            fls = full_base_by_pm[m] + idx * full_batch_stride
            fle = fls + 4.0
            bls, ble = fls + 126.0, fls + 130.0
            ps, pe = ble, ble + 80.0
            for name, value in (
                (f"full_front_load_start_{m}_{b}", fls), (f"full_front_load_end_{m}_{b}", fle),
                (f"full_back_load_start_{m}_{b}", bls), (f"full_back_load_end_{m}_{b}", ble),
                (f"full_start_{m}_{b}", ps), (f"full_end_{m}_{b}", pe),
            ):
                _set(vals, name, value)
            full_window[(m, b)] = {
                "front_load": (fls, fle),
                "back_load": (bls, ble),
                "pm": (ps, pe),
            }
            full_unload_candidates.append((pe, m, b))

    next_full_unload_start = 0.0
    for _, m, b in sorted(full_unload_candidates):
        fls = full_window[(m, b)]["front_load"][0]
        pe = full_window[(m, b)]["pm"][1]
        bus = max(pe, next_full_unload_start)
        bue = bus + 4.0
        next_full_unload_start = bus + 52.0
        fus = max(bue + 2.0, next_full_unload_start)
        fue = fus + 4.0
        next_full_unload_start = fus + 52.0
        for name, value in (
            (f"full_back_unload_start_{m}_{b}", bus), (f"full_back_unload_end_{m}_{b}", bue),
            (f"full_front_unload_start_{m}_{b}", fus), (f"full_front_unload_end_{m}_{b}", fue),
        ):
            _set(vals, name, value)
        full_window[(m, b)].update(
            {
                "back_unload": (bus, bue),
                "front_unload": (fus, fue),
                "window": (fls, fue),
            }
        )

    mix_window = {}
    last_full_end = {
        m: max(full_window[(m, b)]["window"][1] for b in used_batches_by_pm[m])
        for m in (2, 3)
    }
    mix_base_anchor = max(last_full_end.values()) + 300.0
    mix_base_by_pm = {2: mix_base_anchor, 3: mix_base_anchor + chamber_vtr_offset}
    for m in (2, 3):
        hs, he = mix_base_by_pm[m], mix_base_by_pm[m] + 4.0
        _set(vals, f"mix_head_start_{m}", hs)
        _set(vals, f"mix_head_end_{m}", he)
        cycles = {}
        bridges = {}
        cycle_start = he
        for cycle in range(1, 6):
            if cycle > 1:
                bs, be = cycles[cycle - 1][1] + 110.0, cycles[cycle - 1][1] + 114.0
                _set(vals, f"mix_bridge_start_{m}_{cycle}", bs)
                _set(vals, f"mix_bridge_end_{m}_{cycle}", be)
                bridges[cycle] = (bs, be)
                cycle_start = be
            cs, ce = cycle_start, cycle_start + 30.0
            _set(vals, f"mix_cycle_start_{m}_{cycle}", cs)
            _set(vals, f"mix_cycle_end_{m}_{cycle}", ce)
            cycles[cycle] = (cs, ce)
        _set(vals, f"mix_tail_load_start_{m}", bridges[5][0])
        _set(vals, f"mix_tail_load_end_{m}", bridges[5][1])
        _set(vals, f"mix_last_cycle_start_{m}", cycles[5][0])
        _set(vals, f"mix_last_cycle_end_{m}", cycles[5][1])
        ts, te = cycles[5][1] + 110.0, cycles[5][1] + 114.0
        _set(vals, f"mix_tail_start_{m}", ts)
        _set(vals, f"mix_tail_end_{m}", te)
        _set(vals, f"mix_block_end_{m}", te)
        mix_window[m] = {"head": (hs, he), "cycles": cycles, "bridges": bridges, "tail": (ts, te), "tail_load": bridges[5], "block": (hs, te)}

    for p, (m, b, side) in full_map.items():
        window = full_window[(m, b)]
        load = window["front_load"] if side == 1 else window["back_load"]
        unload = window["front_unload"] if side == 1 else window["back_unload"]
        _set(vals, f"full_pair_vtr_load_start_{p}", load[0])
        _set(vals, f"full_pair_vtr_load_end_{p}", load[1])
        _set(vals, f"full_pair_pm_start_{p}", window["pm"][0])
        _set(vals, f"full_pair_pm_end_{p}", window["pm"][1])
        _set(vals, f"full_pair_vtr_unload_start_{p}", unload[0])
        _set(vals, f"full_pair_vtr_unload_end_{p}", unload[1])
        _set(vals, f"full_pair_completion_{p}", unload[1])
        _maybe(vals, names, f"full_pair_post_process_wait_{p}", unload[0] - window["pm"][1])

    for p, (m, pos) in mix_map.items():
        window = mix_window[m]
        load = window["head"] if pos == 1 else window["bridges"][pos]
        pm = (window["cycles"][pos][0], window["cycles"][pos + 1][1])
        unload = window["tail"] if pos == 4 else window["bridges"][pos + 2]
        _set(vals, f"mix_pair_vtr_load_start_{p}", load[0])
        _set(vals, f"mix_pair_vtr_load_end_{p}", load[1])
        _set(vals, f"mix_pair_pm_start_{p}", pm[0])
        _set(vals, f"mix_pair_pm_end_{p}", pm[1])
        _set(vals, f"mix_pair_vtr_unload_start_{p}", unload[0])
        _set(vals, f"mix_pair_vtr_unload_end_{p}", unload[1])
        _set(vals, f"mix_pair_completion_{p}", unload[1])
        _maybe(vals, names, f"mix_pair_post_process_wait_{p}", unload[0] - pm[1])
        for other_m in cfg.pm_ids:
            for other_pos in range(1, cfg.num_mix_positions_per_pm + 1):
                _maybe(vals, names, f"mix_pair_tail_link_{p}_{other_m}_{other_pos}", 1 if (m, pos) == (other_m, other_pos) and pos == 4 else 0)
                if other_pos < cfg.num_mix_positions_per_pm:
                    _maybe(vals, names, f"mix_pair_mid_link_{p}_{other_m}_{other_pos}", 1 if (m, pos) == (other_m, other_pos) and pos < 4 else 0)

    wafer_full_pair = {w: idx // 2 + 1 for idx, w in enumerate(cfg.full_wafer_ids)}
    wafer_mix_pair = {w: idx // 2 + 1 for idx, w in enumerate(cfg.mix_wafer_ids)}
    full_pair_members = {p: [] for p in cfg.full_pair_ids}
    mix_pair_members = {p: [] for p in cfg.mix_pair_ids}
    for wafer, pair in wafer_full_pair.items():
        full_pair_members[pair].append(wafer)
    for wafer, pair in wafer_mix_pair.items():
        mix_pair_members[pair].append(wafer)

    product_pair_sync = {}
    for p in cfg.full_pair_ids:
        load_start = vals[f"full_pair_vtr_load_start_{p}"]
        unload_end = vals[f"full_pair_vtr_unload_end_{p}"]
        upper_start = load_start - cfg.llupper_time
        upper_end = load_start
        lower_start = unload_end
        lower_end = unload_end + cfg.lllower_time
        _set(vals, f"full_pair_llupper_start_{p}", upper_start)
        _set(vals, f"full_pair_llupper_end_{p}", upper_end)
        _set(vals, f"full_pair_lllower_start_{p}", lower_start)
        _set(vals, f"full_pair_lllower_end_{p}", lower_end)
        product_pair_sync[("full", p)] = {
            "upper_start": upper_start,
            "upper_end": upper_end,
            "lower_start": lower_start,
            "lower_end": lower_end,
        }
    for p in cfg.mix_pair_ids:
        load_start = vals[f"mix_pair_vtr_load_start_{p}"]
        unload_end = vals[f"mix_pair_vtr_unload_end_{p}"]
        upper_start = load_start - cfg.llupper_time
        upper_end = load_start
        lower_start = unload_end
        lower_end = unload_end + cfg.lllower_time
        _set(vals, f"mix_pair_llupper_start_{p}", upper_start)
        _set(vals, f"mix_pair_llupper_end_{p}", upper_end)
        _set(vals, f"mix_pair_lllower_start_{p}", lower_start)
        _set(vals, f"mix_pair_lllower_end_{p}", lower_end)
        product_pair_sync[("mix", p)] = {
            "upper_start": upper_start,
            "upper_end": upper_end,
            "lower_start": lower_start,
            "lower_end": lower_end,
        }

    def _pre_stages(pair_sync, member_idx, member_count):
        upper_start = pair_sync["upper_start"]
        first_member_start = upper_start - (
            member_count * (cfg.atr_lp_al_total_time + cfg.aligner_time + cfg.atr_al_llupper_total_time)
        )
        offset = member_idx * (cfg.atr_lp_al_total_time + cfg.aligner_time + cfg.atr_al_llupper_total_time)
        lp_al_start = first_member_start + offset
        lp_al_end = lp_al_start + cfg.atr_lp_al_total_time
        al_start = lp_al_end
        al_end = al_start + cfg.aligner_time
        al_ll_start = al_end
        al_ll_end = al_ll_start + cfg.atr_al_llupper_total_time
        return {
            "atr_lp_al": (lp_al_start, lp_al_end),
            "al": (al_start, al_end),
            "atr_al_llupper": (al_ll_start, al_ll_end),
            "llupper": (pair_sync["upper_start"], pair_sync["upper_end"]),
        }

    def _post_stages(pair_sync, member_idx):
        lower_end = pair_sync["lower_end"]
        return_start = lower_end + 12.0 + cfg.atr_lllower_lp_total_time * member_idx
        return {
            "lllower": (pair_sync["lower_start"], pair_sync["lower_end"]),
            "atr_lllower_lp": (return_start, return_start + cfg.atr_lllower_lp_total_time),
        }

    completion = {}
    pair_intervals = {}
    for w in cfg.product_wafer_ids:
        if w in wafer_full_pair:
            p = wafer_full_pair[w]
            member_idx = full_pair_members[p].index(w)
            member_count = len(full_pair_members[p])
            pair_sync = product_pair_sync[("full", p)]
            pair_label = f"F{p}"
            middle = {
                "vtr_load": (vals[f"full_pair_vtr_load_start_{p}"], vals[f"full_pair_vtr_load_end_{p}"]),
                "pm": (vals[f"full_pair_pm_start_{p}"], vals[f"full_pair_pm_end_{p}"]),
                "vtr_unload": (vals[f"full_pair_vtr_unload_start_{p}"], vals[f"full_pair_vtr_unload_end_{p}"]),
            }
        else:
            p = wafer_mix_pair[w]
            member_idx = mix_pair_members[p].index(w)
            member_count = len(mix_pair_members[p])
            pair_sync = product_pair_sync[("mix", p)]
            pair_label = f"M{p}"
            middle = {
                "vtr_load": (vals[f"mix_pair_vtr_load_start_{p}"], vals[f"mix_pair_vtr_load_end_{p}"]),
                "pm": (vals[f"mix_pair_pm_start_{p}"], vals[f"mix_pair_pm_end_{p}"]),
                "vtr_unload": (vals[f"mix_pair_vtr_unload_start_{p}"], vals[f"mix_pair_vtr_unload_end_{p}"]),
            }
        pre = _pre_stages(pair_sync, member_idx, member_count)
        post = _post_stages(pair_sync, member_idx)
        for stage, (start, end) in {**pre, **middle, **post}.items():
            _set(vals, f"prod_stage_start_{w}_{stage}", start)
            _set(vals, f"prod_stage_end_{w}_{stage}", end)
        completion[w] = post["atr_lllower_lp"][1]
        _set(vals, f"wafer_completion_{w}", completion[w])
        interval = pair_intervals.setdefault(
            pair_label,
            {
                "upper_entry": pre["atr_al_llupper"][0],
                "upper_end": middle["vtr_load"][1],
                "lower_entry": middle["vtr_unload"][0],
                "lower_exit": post["atr_lllower_lp"][1],
            },
        )
        interval["upper_entry"] = min(interval["upper_entry"], pre["atr_al_llupper"][0])
        interval["lower_exit"] = max(interval["lower_exit"], post["atr_lllower_lp"][1])

    _set(vals, "c_max", max(completion.values()))
    _set(vals, "full_pm_imbalance", 3)
    _set(vals, "mix_pm_imbalance", 1)

    for m in cfg.pm_ids:
        for j in range(1, cfg.num_clean_slots_per_pm + 1):
            for family in ("clean_front_load", "clean_back_load", "clean", "clean_back_unload", "clean_front_unload"):
                _maybe(vals, names, f"{family}_start_{m}_{j}", 0)
                _maybe(vals, names, f"{family}_end_{m}_{j}", 0)
        full_idle = sum(
            full_window[(m, b)]["window"][1] - full_window[(m, b)]["window"][0] - cfg.full_process_time
            for b in used_batches_by_pm[m]
        )
        mix_process = sum(end - start for start, end in mix_window[m]["cycles"].values())
        mix_idle = mix_window[m]["block"][1] - mix_window[m]["block"][0] - mix_process
        idle_total = full_idle + mix_idle
        _maybe(vals, names, f"chamber_idle_total_{m}", idle_total)
        _maybe(vals, names, f"chamber_idle_square_{m}", idle_total * idle_total)
        for b in range(1, cfg.num_full_batches_per_pm):
            if b in used_batches_by_pm[m] and (b + 1) in used_batches_by_pm[m]:
                slack = vals[f"full_front_load_start_{m}_{b + 1}"] - vals[f"full_front_unload_end_{m}_{b}"]
            else:
                slack = 0.0
            _maybe(vals, names, f"full_batch_idle_{m}_{b}_{b + 1}", slack)
            for epoch in (1, 2):
                _maybe(vals, names, f"full_batch_idle_{m}_{b}_{b + 1}_{epoch}", slack if epoch == 1 else 0.0)

        tail_batch = max(used_batches_by_pm[m])
        for b in range(1, cfg.num_full_batches_per_pm + 1):
            slack = vals[f"mix_head_start_{m}"] - vals[f"full_front_unload_end_{m}_{b}"] if b == tail_batch else 0.0
            _maybe(vals, names, f"full_to_mix_idle_{m}_{b}", slack)
            for epoch in (1, 2):
                _maybe(vals, names, f"full_to_mix_idle_{m}_{b}_{epoch}", slack if b == tail_batch and epoch == 1 else 0.0)

        _maybe(vals, names, f"mix_head_idle_{m}", vals[f"mix_cycle_start_{m}_1"] - vals[f"mix_head_end_{m}"])
        for cycle in range(2, cfg.num_mix_cycles_per_pm + 1):
            if cycle in active_mix_cycles_by_pm[m]:
                cycle_to_bridge = vals[f"mix_bridge_start_{m}_{cycle}"] - vals[f"mix_cycle_end_{m}_{cycle - 1}"]
                bridge_to_cycle = vals[f"mix_cycle_start_{m}_{cycle}"] - vals[f"mix_bridge_end_{m}_{cycle}"]
            else:
                cycle_to_bridge = 0.0
                bridge_to_cycle = 0.0
            _maybe(vals, names, f"mix_cycle_to_bridge_idle_{m}_{cycle}", cycle_to_bridge)
            _maybe(vals, names, f"mix_bridge_to_cycle_idle_{m}_{cycle}", bridge_to_cycle)
        _maybe(vals, names, f"mix_tail_idle_{m}", vals[f"mix_tail_start_{m}"] - vals[f"mix_last_cycle_end_{m}"])

    def _maybe_wait(name, later, earlier, offset=0.0):
        wait = max(0.0, later - earlier - offset)
        _maybe(vals, names, name, wait)
        _maybe(vals, names, f"{name}_square", wait * wait)

    for w in cfg.product_wafer_ids:
        _maybe_wait(
            f"prod_robot_wait_{w}_atr_lp_al",
            vals[f"prod_stage_end_{w}_atr_lp_al"],
            vals[f"prod_stage_start_{w}_atr_lp_al"],
            cfg.atr_lp_al_total_time,
        )
        _maybe_wait(
            f"prod_module_wait_{w}_al_pre",
            vals[f"prod_stage_start_{w}_al"],
            vals[f"prod_stage_end_{w}_atr_lp_al"],
        )
        _maybe_wait(
            f"prod_module_wait_{w}_al_post",
            vals[f"prod_stage_start_{w}_atr_al_llupper"],
            vals[f"prod_stage_end_{w}_al"],
        )
        _maybe_wait(
            f"prod_robot_wait_{w}_atr_al_llupper",
            vals[f"prod_stage_end_{w}_atr_al_llupper"],
            vals[f"prod_stage_start_{w}_atr_al_llupper"],
            cfg.atr_al_llupper_total_time,
        )
        _maybe_wait(
            f"prod_module_wait_{w}_llupper_pre",
            vals[f"prod_stage_start_{w}_llupper"],
            vals[f"prod_stage_end_{w}_atr_al_llupper"],
        )
        _maybe_wait(
            f"prod_module_wait_{w}_llupper_post",
            vals[f"prod_stage_start_{w}_vtr_load"],
            vals[f"prod_stage_end_{w}_llupper"],
        )
        _maybe_wait(
            f"prod_robot_wait_{w}_vtr_load",
            vals[f"prod_stage_end_{w}_vtr_load"],
            vals[f"prod_stage_start_{w}_vtr_load"],
            cfg.pair_transfer_time,
        )
        _maybe_wait(
            f"prod_pm_wait_{w}_pre",
            vals[f"prod_stage_start_{w}_pm"],
            vals[f"prod_stage_end_{w}_vtr_load"],
        )
        _maybe_wait(
            f"prod_pm_wait_{w}_post",
            vals[f"prod_stage_start_{w}_vtr_unload"],
            vals[f"prod_stage_end_{w}_pm"],
        )
        _maybe_wait(
            f"prod_robot_wait_{w}_vtr_unload",
            vals[f"prod_stage_end_{w}_vtr_unload"],
            vals[f"prod_stage_start_{w}_vtr_unload"],
            cfg.pair_transfer_time,
        )
        _maybe_wait(
            f"prod_module_wait_{w}_lllower_pre",
            vals[f"prod_stage_start_{w}_lllower"],
            vals[f"prod_stage_end_{w}_vtr_unload"],
        )
        _maybe_wait(
            f"prod_module_wait_{w}_lllower_post",
            vals[f"prod_stage_start_{w}_atr_lllower_lp"],
            vals[f"prod_stage_end_{w}_lllower"],
        )
        _maybe_wait(
            f"prod_robot_wait_{w}_atr_lllower_lp",
            vals[f"prod_stage_end_{w}_atr_lllower_lp"],
            vals[f"prod_stage_start_{w}_atr_lllower_lp"],
            cfg.atr_lllower_lp_total_time,
        )

    atr_tasks = []
    al_tasks = []
    llupper_tasks = []
    lllower_tasks = []
    for w in cfg.product_wafer_ids:
        atr_tasks.extend([
            (f"lp_al_{w}", vals[f"prod_stage_start_{w}_atr_lp_al"], vals[f"prod_stage_end_{w}_atr_lp_al"], True),
            (f"al_llupper_{w}", vals[f"prod_stage_start_{w}_atr_al_llupper"], vals[f"prod_stage_end_{w}_atr_al_llupper"], True),
            (f"lllower_lp_{w}", vals[f"prod_stage_start_{w}_atr_lllower_lp"], vals[f"prod_stage_end_{w}_atr_lllower_lp"], True),
        ])
        al_tasks.append((str(w), vals[f"prod_stage_start_{w}_al"], vals[f"prod_stage_end_{w}_al"], True))
        llupper_tasks.append(
            (
                str(w),
                vals[f"prod_stage_end_{w}_atr_al_llupper"] - cfg.atr_load_unload_time,
                vals[f"prod_stage_end_{w}_vtr_load"] + cfg.llupper_time,
                True,
            )
        )
        lllower_tasks.append(
            (
                str(w),
                vals[f"prod_stage_start_{w}_vtr_unload"],
                vals[f"prod_stage_start_{w}_atr_lllower_lp"]
                + cfg.atr_load_unload_time
                + cfg.lllower_time,
                True,
            )
        )
    _set_parallel_orders(vals, names, "atr_slot_assign", "seq_atr", atr_tasks, cfg.atr_capacity, lambda task: 1)
    _set_unary_orders(vals, names, "seq_al", al_tasks)
    _set_parallel_orders(vals, names, "llupper_slot_assign", "seq_llupper", llupper_tasks, 2, lambda task: 1 if int(task) % 2 else 2)
    _set_parallel_orders(vals, names, "lllower_slot_assign", "seq_lllower", lllower_tasks, 2, lambda task: 1 if int(task) % 2 else 2)
    _set_pair_orders(vals, names, pair_intervals)

    vtr_tasks = []
    for m in cfg.pm_ids:
        vtr_tasks.append((f"mix_head_{m}", vals[f"mix_head_start_{m}"], vals[f"mix_head_end_{m}"], True))
        vtr_tasks.append((f"mix_tail_{m}", vals[f"mix_tail_start_{m}"], vals[f"mix_tail_end_{m}"], True))
        for b in range(1, cfg.num_full_batches_per_pm + 1):
            active = b in used_batches_by_pm[m]
            vtr_tasks.extend([
                (f"full_front_load_{m}_{b}", vals.get(f"full_front_load_start_{m}_{b}", 0), vals.get(f"full_front_load_end_{m}_{b}", 0), active),
                (f"full_back_load_{m}_{b}", vals.get(f"full_back_load_start_{m}_{b}", 0), vals.get(f"full_back_load_end_{m}_{b}", 0), active),
                (f"full_back_unload_{m}_{b}", vals.get(f"full_back_unload_start_{m}_{b}", 0), vals.get(f"full_back_unload_end_{m}_{b}", 0), active),
                (f"full_front_unload_{m}_{b}", vals.get(f"full_front_unload_start_{m}_{b}", 0), vals.get(f"full_front_unload_end_{m}_{b}", 0), active),
            ])
        for j in range(1, cfg.num_clean_slots_per_pm + 1):
            for family in ("clean_front_load", "clean_back_load", "clean_back_unload", "clean_front_unload"):
                vtr_tasks.append((f"{family}_{m}_{j}", 0, 0, False))
        for cycle in range(2, cfg.num_mix_cycles_per_pm + 1):
            active = cycle in active_mix_cycles_by_pm[m]
            vtr_tasks.append((f"mix_bridge_{m}_{cycle}", vals.get(f"mix_bridge_start_{m}_{cycle}", 0), vals.get(f"mix_bridge_end_{m}_{cycle}", 0), active))
    _set_parallel_orders(vals, names, "vtr_slot_assign", "seq_vtr", vtr_tasks, cfg.vtr_capacity, lambda task: (1, 2))

    for m in cfg.pm_ids:
        tasks = []
        for b in range(1, cfg.num_full_batches_per_pm + 1):
            active = b in used_batches_by_pm[m]
            tasks.append((f"full_batch_window_{m}_{b}", vals.get(f"full_front_load_start_{m}_{b}", 0), vals.get(f"full_front_unload_end_{m}_{b}", 0), active))
        for j in range(1, cfg.num_clean_slots_per_pm + 1):
            tasks.append((f"clean_window_{m}_{j}", 0, 0, False))
        _set_unary_orders(vals, names, f"seq_full_batch_{m}", tasks)

    pec_jobs = []

    def add_pec(chamber, active, load, pm, unload):
        pec_jobs.append({"chamber": chamber, "active": active, "load": load, "pm": pm, "unload": unload})

    for p, load in cfg.full_pair_product_loads.items():
        if load == 1:
            for m in cfg.pm_ids:
                for b in range(1, cfg.num_full_batches_per_pm + 1):
                    for lane in (1, 2):
                        active = full_map[p] == (m, b, lane)
                        window = full_window.get((m, b), {"front_load": (0, 0), "back_load": (0, 0), "pm": (0, 0), "front_unload": (0, 0), "back_unload": (0, 0)})
                        add_pec(m, active, window["front_load"] if lane == 1 else window["back_load"], window["pm"], window["front_unload"] if lane == 1 else window["back_unload"])
    for p, load in cfg.mix_pair_product_loads.items():
        if load == 1:
            for m in cfg.pm_ids:
                for pos in range(1, cfg.num_mix_positions_per_pm + 1):
                    active = mix_map[p] == (m, pos)
                    window = mix_window[m]
                    load_iv = window["head"] if pos == 1 else window["bridges"].get(pos, (0, 0))
                    pm_iv = (window["cycles"].get(pos, (0, 0))[0], window["cycles"].get(pos + 1, (0, 0))[1]) if pos <= 4 else (0, 0)
                    unload_iv = window["tail"] if pos == 4 else window["bridges"].get(pos + 2, (0, 0))
                    add_pec(m, active, load_iv, pm_iv, unload_iv)
    for m in cfg.pm_ids:
        for b in range(1, cfg.num_full_batches_per_pm + 1):
            for lane in (1, 2):
                active = (m, b, lane) == (2, 4, 2)
                window = full_window.get((m, b), {"front_load": (0, 0), "back_load": (0, 0), "pm": (0, 0), "front_unload": (0, 0), "back_unload": (0, 0)})
                for _filler_idx in (1, 2):
                    add_pec(m, active, window["front_load"] if lane == 1 else window["back_load"], window["pm"], window["front_unload"] if lane == 1 else window["back_unload"])
        for _ in (1, 2):
            window = mix_window[m]
            add_pec(m, True, window["head"], window["cycles"][1], window["bridges"][2])
            add_pec(m, True, window["tail_load"], window["cycles"][5], window["tail"])
        for _ in range(1, cfg.num_clean_slots_per_pm + 1):
            for _lane in (1, 2):
                add_pec(m, False, (0, 0), (0, 0), (0, 0))
                add_pec(m, False, (0, 0), (0, 0), (0, 0))

    last_end = {slot: -1.0 for slot in range(1, cfg.pec_pool_size + 1)}
    pec_token = {}
    active_job_ids = sorted(
        [idx + 1 for idx, job in enumerate(pec_jobs) if job["active"]],
        key=lambda job_id: pec_jobs[job_id - 1]["load"][0],
    )
    for job_id in active_job_ids:
        job = pec_jobs[job_id - 1]
        allowed = range(1, 5) if job["chamber"] == 2 else range(5, 9)
        for slot in allowed:
            if last_end[slot] <= job["load"][0]:
                pec_token[job_id] = slot
                last_end[slot] = job["unload"][1]
                break
        else:
            raise RuntimeError(f"No PEC token is available for job {job_id}.")

    for job_id, job in enumerate(pec_jobs, start=1):
        for stage, interval in (("vtr_load", job["load"]), ("pm", job["pm"]), ("vtr_unload", job["unload"])):
            _set(vals, f"pec_stage_start_{job_id}_{stage}", interval[0] if job["active"] else 0)
            _set(vals, f"pec_stage_end_{job_id}_{stage}", interval[1] if job["active"] else 0)
        allowed = range(1, 5) if job["chamber"] == 2 else range(5, 9)
        for slot in allowed:
            _set(vals, f"pec_token_assign_{job_id}_{slot}", 1 if job["active"] and pec_token.get(job_id) == slot else 0)

    for slot in range(1, cfg.pec_pool_size + 1):
        for left_id, left_job in enumerate(pec_jobs, start=1):
            if f"pec_token_assign_{left_id}_{slot}" not in names:
                continue
            left_end = left_job["unload"][1] if left_job["active"] else 0
            for right_id, right_job in enumerate(pec_jobs[left_id:], start=left_id + 1):
                var_name = f"pec_token_order_{left_id}_{right_id}_{slot}"
                if var_name in names:
                    right_start = right_job["load"][0] if right_job["active"] else 0
                    vals[var_name] = 1.0 if left_end <= right_start else 0.0

    for var_name in names:
        vals.setdefault(var_name, 0.0)
    return cfg, vals


def _apply_solution(model, vals):
    vars_by_name = {var.name: var for var in model.getVars()}
    missing = sorted(set(vals) - set(vars_by_name))
    if missing:
        raise KeyError(f"{len(missing)} solution variables are missing from the model, first: {missing[:5]}")
    sol = model.createSol()
    for name, value in vals.items():
        model.setSolVal(sol, vars_by_name[name], value)
    return sol


def _extract_solution_from_values(vals):
    return {
        name: value
        for name, value in vals.items()
        if abs(value) > 1e-9
    }


def _extract_solution_from_scip(model):
    best_sol = model.getBestSol()
    if best_sol is None:
        return {}
    result = {}
    for var in model.getVars():
        value = float(model.getSolVal(best_sol, var))
        if abs(value) > 1e-9:
            result[var.name] = value
    return result


def _load_lp_model_with_solution(lp_path, vals):
    model = scip.Model()
    model.hideOutput(True)
    model.readProblem(str(lp_path))
    sol = _apply_solution(model, vals)
    if not model.checkSol(sol, printreason=True, completely=True):
        raise RuntimeError(f"Constructive start failed SCIP feasibility checking on {lp_path}.")
    return model, sol


def main():
    parser = argparse.ArgumentParser(description="Build a constructive physical-capacity feasible start.")
    parser.add_argument("--output_json", default="petri_transfer_constructive_physical_solution.json")
    parser.add_argument("--lp_path", default="generated_instances/MIP/mip_clean_20260508.lp")
    parser.add_argument("--skip_lp_check", action="store_true")
    parser.add_argument("--optimize_time_limit", type=float, default=0.0)
    parser.add_argument("--generate_gantt", action="store_true")
    args = parser.parse_args()

    model = build_petri_mip_model(
        PetriMIPConfig(
            num_pm=2,
            pec_pool_size=8,
            full_mode_wafers=25,
            mix_mode_wafers=15,
            total_wafers=0,
            cleaning_interval=10,
            cleaning_process_time=60.0,
        )
    )
    cfg, vals = build_mip_clean_20260508_start(model)
    sol = _apply_solution(model, vals)
    if not model.checkSol(sol, printreason=True, completely=True):
        raise RuntimeError("Constructive start failed SCIP feasibility checking.")

    solve_model = model
    solve_sol = sol
    verified_actual_lp = False
    source_lp = None
    if not args.skip_lp_check:
        lp_path = resolve_path(args.lp_path)
        if not lp_path.exists():
            raise FileNotFoundError(f"LP file not found: {lp_path}")
        solve_model, solve_sol = _load_lp_model_with_solution(lp_path, vals)
        verified_actual_lp = True
        source_lp = str(lp_path)

    status = "feasible_start"
    chamber_idle_slack = sum(
        value
        for name, value in vals.items()
        if (
            name.startswith("full_batch_idle_")
            or name.startswith("full_to_mix_idle_")
            or name.startswith("mix_head_idle_")
            or name.startswith("mix_cycle_to_bridge_idle_")
            or name.startswith("mix_bridge_to_cycle_idle_")
            or name.startswith("mix_tail_idle_")
        )
    )
    post_process_wait = sum(
        value
        for name, value in vals.items()
        if name.startswith("full_pair_post_process_wait_") or name.startswith("mix_pair_post_process_wait_")
    )
    best_obj = (
        vals["c_max"]
        + cfg.pm_balance_penalty * (vals["full_pm_imbalance"] + vals["mix_pm_imbalance"])
        + cfg.chamber_idle_penalty * chamber_idle_slack
        + cfg.post_process_wait_penalty * post_process_wait
        + cfg.chamber_idle_square_penalty * sum(vals[f"chamber_idle_square_{m}"] for m in cfg.pm_ids)
        + cfg.pm_wait_square_penalty
        * sum(value for name, value in vals.items() if name.startswith("prod_pm_wait_") and name.endswith("_square"))
        + cfg.module_wait_square_penalty
        * sum(value for name, value in vals.items() if name.startswith("prod_module_wait_") and name.endswith("_square"))
        + cfg.robot_wait_square_penalty
        * sum(value for name, value in vals.items() if name.startswith("prod_robot_wait_") and name.endswith("_square"))
    )
    solution = _extract_solution_from_values(vals)

    if args.optimize_time_limit > 0:
        solve_model.addSol(solve_sol, free=False)
        solve_model.setRealParam("limits/time", args.optimize_time_limit)
        solve_model.setIntParam("timing/clocktype", 2)
        solve_model.optimize()
        status = str(solve_model.getStatus())
        if solve_model.getNSols() > 0:
            best_obj = float(solve_model.getObjVal())
            solution = _extract_solution_from_scip(solve_model)

    record = {
        "instance": Path(args.lp_path).name if not args.skip_lp_check else "mip_clean_20260508.lp",
        "status": status,
        "solving_time": float(solve_model.getSolvingTime()) if args.optimize_time_limit > 0 else 0.0,
        "ntotal_nodes": int(solve_model.getNTotalNodes()) if args.optimize_time_limit > 0 else 0,
        "primal_dual_gap": float(solve_model.getGap()) if args.optimize_time_limit > 0 and solve_model.getNSols() > 0 else None,
        "primaldualintegral": 0.0,
        "best_obj": best_obj,
        "nonzero_solution_vars": len(solution),
        "verified_generator_model": True,
        "verified_actual_lp": verified_actual_lp,
        "source_lp": source_lp,
        "solution": solution,
    }

    output_path = resolve_path(args.output_json)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps([record], ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote feasible solution: {output_path}")
    print(f"status={record['status']} best_obj={record['best_obj']} nonzero_vars={record['nonzero_solution_vars']}")

    if args.generate_gantt:
        generated = generate_gantt_charts_from_solution_file(str(output_path))
        if generated:
            print(f"wrote gantt outputs under: {Path(generated[0]).parent}")


if __name__ == "__main__":
    main()

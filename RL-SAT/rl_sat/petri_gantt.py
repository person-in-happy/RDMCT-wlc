# -*- coding: utf-8 -*-
# Vendored from ../petri_gantt.py on 2026-07-28.
# Keep this module self-contained so RL-SAT result rendering does not import the MIP project.
import argparse
import json
import math
import os
import re
from pathlib import Path
from typing import Dict, List, Tuple

from .gantt_paths import is_latest_keyword, latest_matching_file, resolve_path


ASSIGN_PROD_RE = re.compile(r"assign_prod_(\d+)_(\d+)_(\d+)$")
ASSIGN_PEC_RE = re.compile(r"assign_pec_(\d+)_(\d+)_(\d+)$")
BATCH_USED_RE = re.compile(r"batch_used_(\d+)_(\d+)$")
BATCH_START_RE = re.compile(r"batch_start_(\d+)_(\d+)$")
BATCH_END_RE = re.compile(r"batch_end_(\d+)_(\d+)$")
BATCH_RELEASE_RE = re.compile(r"batch_release_(\d+)_(\d+)$")
PROD_STAGE_START_RE = re.compile(r"prod_stage_start_(\d+)_(.+)$")
PROD_STAGE_END_RE = re.compile(r"prod_stage_end_(\d+)_(.+)$")
PEC_STAGE_START_RE = re.compile(r"pec_stage_start_(\d+)_(.+)$")
PEC_STAGE_END_RE = re.compile(r"pec_stage_end_(\d+)_(.+)$")
PRODUCT_PAIR_COMPLETION_RE = re.compile(r"product_pair_completion_(\d+)$")
NEW_FULL_PAIR_MEMBER_RE = re.compile(r"wafer_to_full_pair_(\d+)_(\d+)$")
NEW_MIX_PAIR_MEMBER_RE = re.compile(r"wafer_to_mix_pair_(\d+)_(\d+)$")
NEW_FULL_PAIR_COMPLETION_RE = re.compile(r"full_pair_completion_(\d+)$")
NEW_MIX_PAIR_COMPLETION_RE = re.compile(r"mix_pair_completion_(\d+)$")
NEW_WAFER_COMPLETION_RE = re.compile(r"wafer_completion_(\d+)$")
NEW_FULL_ASSIGN_RE = re.compile(r"assign_full_(\d+)_(\d+)_(\d+)_(\d+)$")
NEW_FULL_BATCH_USED_RE = re.compile(r"full_batch_used_(\d+)_(\d+)$")
NEW_FULL_FILLER_SIDE_RE = re.compile(r"full_filler_side_(\d+)_(\d+)_(\d+)$")
NEW_MIX_ASSIGN_RE = re.compile(r"assign_mix_(\d+)_(\d+)_(\d+)$")
NEW_MIX_ACTIVE_RE = re.compile(r"mix_active_(\d+)$")
NEW_MIX_CYCLE_USED_RE = re.compile(r"mix_cycle_used_(\d+)_(\d+)$")
NEW_MIX_LAST_POS_RE = re.compile(r"mix_last_pos_(\d+)_(\d+)$")
NEW_CLEAN_ACTIVE_RE = re.compile(r"clean_active_(\d+)_(\d+)$")
LLUPPER_SLOT_ASSIGN_RE = re.compile(r"llupper_slot_assign_(\d+)_(\d+)$")
LLLOWER_SLOT_ASSIGN_RE = re.compile(r"lllower_slot_assign_(\d+)_(\d+)$")
PEC_TOKEN_ASSIGN_RE = re.compile(r"pec_token_assign_(\d+)_(\d+)$")
PEC_JOB_CHAMBER_RE = re.compile(r"pec_job_chamber_(\d+)_(\d+)$")
ATR_SLOT_ASSIGN_RE = re.compile(r"atr_slot_assign_(.+)_(\d+)$")
VTR_SLOT_ASSIGN_RE = re.compile(r"vtr_slot_assign_(.+)_(\d+)$")
FULL_PAIR_VTR_WINDOW_RE = re.compile(r"full_pair_vtr_(load|unload)_(start|end)_(\d+)$")
CLEAN_START_RE = re.compile(r"clean_start_(\d+)_(\d+)$")
CLEAN_END_RE = re.compile(r"clean_end_(\d+)_(\d+)$")

LEGACY_FULL_ASSIGN_RE = re.compile(r"assign_full_(\d+)_(\d+)_(\d+)$")
LEGACY_FULL_PEC_RE = re.compile(r"full_pec_pairs_(\d+)_(\d+)$")
LEGACY_FULL_START_RE = re.compile(r"full_start_(\d+)_(\d+)$")
LEGACY_FULL_END_RE = re.compile(r"full_end_(\d+)_(\d+)$")
LEGACY_FULL_USED_RE = re.compile(r"full_slot_used_(\d+)_(\d+)$")
LEGACY_MIX_ASSIGN_RE = re.compile(r"assign_mix_(\d+)_(\d+)_(\d+)$")
LEGACY_MIX_START_RE = re.compile(r"mix_cycle_start_(\d+)_(\d+)$")
LEGACY_MIX_END_RE = re.compile(r"mix_cycle_end_(\d+)_(\d+)$")
LEGACY_MIX_USED_RE = re.compile(r"mix_cycle_used_(\d+)_(\d+)$")
LEGACY_PAIR_COMPLETION_RE = re.compile(r"pair_completion_(\d+)$")

SVG_WIDTH = 2160
LEFT_MARGIN = 360
RIGHT_MARGIN = 120
TOP_MARGIN = 118
BOTTOM_MARGIN = 96
LANE_HEIGHT = 74
BAR_HEIGHT = 42
LABEL_ROW_HEIGHT = 24
LABEL_ROW_GAP = 6.0
SECONDS_PER_HOUR = 3600.0
PATH_TIME_TOLERANCE = 1e-3

NEW_PRODUCT_STAGE_ORDER = [
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
NEW_PRODUCT_STAGE_META = {
    "atr_lp_al": ("LP->AL", "#4C78A8"),
    "atr_hold_before_al": ("ATR hold before AL", "#B07AA1"),
    "atr_al_exchange": ("ATR exchange at AL", "#D37295"),
    "al": ("AL", "#9C755F"),
    "atr_hold_after_al": ("ATR hold after AL", "#B07AA1"),
    "atr_al_llupper": ("AL->LLupper", "#72B7B2"),
    "llupper": ("LLupper", "#54A24B"),
    "vtr_load": ("VTR Load", "#F58518"),
    "pm": ("PM", "#E45756"),
    "vtr_unload": ("VTR Unload", "#FF9DA6"),
    "lllower": ("LLlower", "#B279A2"),
    "atr_lllower_lp": ("LLlower->LP", "#79706E"),
}
NEW_PEC_STAGE_ORDER = ["vtr_load", "pm", "vtr_unload"]
NEW_PEC_STAGE_META = {
    "vtr_load": ("PEC->PM", "#72B7B2"),
    "pm": ("PM", "#E45756"),
    "vtr_unload": ("PM->PEC", "#B279A2"),
}


def _float(value):
    try:
        return float(value)
    except Exception:
        return 0.0


def _bool(value, tol=1e-6):
    return _float(value) > 0.5 - tol


def _escape(text: str) -> str:
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _escape_attr(text: str) -> str:
    return _escape(text).replace("\r", "").replace("\n", "&#10;")


def _wrap_text(text: str, max_chars: int, max_lines: int = 3) -> List[str]:
    if max_chars <= 0:
        return []
    pieces = []
    for raw_line in str(text).split("\n"):
        line = raw_line.strip()
        if not line:
            pieces.append("")
            continue
        if len(line) <= max_chars:
            pieces.append(line)
            continue
        start = 0
        while start < len(line):
            pieces.append(line[start:start + max_chars])
            start += max_chars
    if len(pieces) <= max_lines:
        return pieces
    trimmed = pieces[:max_lines]
    if trimmed[-1]:
        trimmed[-1] = trimmed[-1][:-3] + "..."
    return trimmed


def _lane_y(index: int) -> int:
    return TOP_MARGIN + index * LANE_HEIGHT


def _time_to_x(value: float, horizon: float) -> float:
    plot_width = SVG_WIDTH - LEFT_MARGIN - RIGHT_MARGIN
    return LEFT_MARGIN + (value / max(horizon, 1e-9)) * plot_width


def _validate_continuous_entity_lanes(
    lanes: List[str],
    tasks: List[Dict[str, object]],
    tolerance: float = PATH_TIME_TOLERANCE,
) -> None:
    """Reject a path chart that cannot represent one physical wafer per lane."""
    tasks_by_lane: Dict[str, List[Dict[str, object]]] = {}
    for task in tasks:
        tasks_by_lane.setdefault(str(task["lane"]), []).append(task)

    errors = []
    for lane in lanes:
        lane_tasks = sorted(
            tasks_by_lane.get(lane, []),
            key=lambda task: (float(task["start"]), float(task["end"])),
        )
        for previous, current in zip(lane_tasks, lane_tasks[1:]):
            previous_end = float(previous["end"])
            current_start = float(current["start"])
            delta = current_start - previous_end
            if delta > tolerance:
                errors.append(
                    f"{lane}: uncovered interval {previous_end:.6f}..{current_start:.6f} "
                    f"between {previous['label']!r} and {current['label']!r}"
                )
            elif delta < -tolerance:
                errors.append(
                    f"{lane}: overlapping interval {current_start:.6f}..{previous_end:.6f} "
                    f"between {previous['label']!r} and {current['label']!r}"
                )

    if errors:
        preview = "\n".join(errors[:12])
        extra = "" if len(errors) <= 12 else f"\n... and {len(errors) - 12} more"
        raise ValueError(
            "Invalid wafer path schedule: each product/PEC lane must be continuous "
            f"and non-overlapping.\n{preview}{extra}"
        )


def _collect_path_schedule(solution: Dict[str, float]) -> Dict[str, object]:
    assign_prod_by_batch: Dict[Tuple[int, int], List[int]] = {}
    assign_prod_by_wafer: Dict[int, Tuple[int, int]] = {}
    assign_pec_by_batch: Dict[Tuple[int, int], List[int]] = {}
    assign_pec_by_pec: Dict[int, Tuple[int, int]] = {}
    batch_used: Dict[Tuple[int, int], bool] = {}
    batch_start: Dict[Tuple[int, int], float] = {}
    batch_end: Dict[Tuple[int, int], float] = {}
    batch_release: Dict[Tuple[int, int], float] = {}
    prod_stage_start: Dict[Tuple[int, str], float] = {}
    prod_stage_end: Dict[Tuple[int, str], float] = {}
    pec_stage_start: Dict[Tuple[int, str], float] = {}
    pec_stage_end: Dict[Tuple[int, str], float] = {}
    pec_token_by_job: Dict[int, int] = {}
    full_pair_members: Dict[int, List[int]] = {}
    mix_pair_members: Dict[int, List[int]] = {}
    full_assignment: Dict[Tuple[int, int, int], int] = {}
    mix_pair_by_pos: Dict[Tuple[int, int], int] = {}
    c_max = _float(solution.get("c_max", 0.0))

    for name, value in solution.items():
        m = ASSIGN_PROD_RE.match(name)
        if m and _bool(value):
            wafer_id = int(m.group(1))
            pm_id = int(m.group(2))
            slot_id = int(m.group(3))
            assign_prod_by_batch.setdefault((pm_id, slot_id), []).append(wafer_id)
            assign_prod_by_wafer[wafer_id] = (pm_id, slot_id)
            continue
        m = ASSIGN_PEC_RE.match(name)
        if m and _bool(value):
            pec_id = int(m.group(1))
            pm_id = int(m.group(2))
            slot_id = int(m.group(3))
            assign_pec_by_batch.setdefault((pm_id, slot_id), []).append(pec_id)
            assign_pec_by_pec[pec_id] = (pm_id, slot_id)
            continue
        m = BATCH_USED_RE.match(name)
        if m:
            batch_used[(int(m.group(1)), int(m.group(2)))] = _bool(value)
            continue
        m = BATCH_START_RE.match(name)
        if m:
            batch_start[(int(m.group(1)), int(m.group(2)))] = _float(value)
            continue
        m = BATCH_END_RE.match(name)
        if m:
            batch_end[(int(m.group(1)), int(m.group(2)))] = _float(value)
            continue
        m = BATCH_RELEASE_RE.match(name)
        if m:
            batch_release[(int(m.group(1)), int(m.group(2)))] = _float(value)
            continue
        m = PROD_STAGE_START_RE.match(name)
        if m:
            prod_stage_start[(int(m.group(1)), m.group(2))] = _float(value)
            continue
        m = PROD_STAGE_END_RE.match(name)
        if m:
            prod_stage_end[(int(m.group(1)), m.group(2))] = _float(value)
            continue
        m = PEC_STAGE_START_RE.match(name)
        if m:
            pec_stage_start[(int(m.group(1)), m.group(2))] = _float(value)
            continue
        m = PEC_STAGE_END_RE.match(name)
        if m:
            pec_stage_end[(int(m.group(1)), m.group(2))] = _float(value)
            continue
        m = PEC_TOKEN_ASSIGN_RE.match(name)
        if m and _bool(value):
            pec_token_by_job[int(m.group(1))] = int(m.group(2))
            continue
        m = NEW_FULL_PAIR_MEMBER_RE.match(name)
        if m and _bool(value):
            full_pair_members.setdefault(int(m.group(2)), []).append(int(m.group(1)))
            continue
        m = NEW_MIX_PAIR_MEMBER_RE.match(name)
        if m and _bool(value):
            mix_pair_members.setdefault(int(m.group(2)), []).append(int(m.group(1)))
            continue
        m = NEW_FULL_ASSIGN_RE.match(name)
        if m and _bool(value):
            full_assignment[(int(m.group(2)), int(m.group(3)), int(m.group(4)))] = int(m.group(1))
            continue
        m = NEW_MIX_ASSIGN_RE.match(name)
        if m and _bool(value):
            mix_pair_by_pos[(int(m.group(2)), int(m.group(3)))] = int(m.group(1))
            continue

    if not (assign_prod_by_batch or prod_stage_start or batch_used):
        return {}

    new_product_model = any(stage_name in NEW_PRODUCT_STAGE_ORDER for _, stage_name in prod_stage_start.keys())
    if new_product_model:
        lanes: List[str] = []
        tasks: List[Dict[str, object]] = []
        time_candidates = [c_max]

        def add_path_task(
            lane: str,
            start: float,
            end: float,
            label: str,
            entity: str,
            color: str,
            short_label: str = "",
        ) -> None:
            if end <= start + 1e-9:
                return
            tasks.append(
                {
                    "lane": lane,
                    "start": start,
                    "end": end,
                    "label": f"{label}\n{entity}",
                    "short_label": short_label or entity,
                    "color": color,
                }
            )
            time_candidates.extend([start, end])

        def product_start(wafer_id: int, stage_name: str) -> float:
            return prod_stage_start.get((wafer_id, stage_name), 0.0)

        def product_end(wafer_id: int, stage_name: str) -> float:
            return prod_stage_end.get((wafer_id, stage_name), product_start(wafer_id, stage_name))

        def atr_load_unload_time(wafer_id: int, stage_name: str) -> float:
            vtr_time = product_end(wafer_id, "vtr_load") - product_start(wafer_id, "vtr_load")
            if vtr_time <= 1e-9:
                vtr_time = product_end(wafer_id, "vtr_unload") - product_start(wafer_id, "vtr_unload")
            stage_time = product_end(wafer_id, stage_name) - product_start(wafer_id, stage_name)
            return max(0.0, min(vtr_time, 0.5 * stage_time))

        def add_atr_path_transfer(lane_name, wafer_id, stage_name, source, destination, entity):
            start = product_start(wafer_id, stage_name)
            end = product_end(wafer_id, stage_name)
            handling_time = atr_load_unload_time(wafer_id, stage_name)
            load_end = min(end, start + handling_time)
            unload_start = max(load_end, end - handling_time)
            is_double = is_synchronized_pair_stage(wafer_id, stage_name)
            load_action = f"ATR double-pick at {source}" if is_double else f"ATR load at {source}"
            move_action = f"ATR dual-carry {source}->{destination}" if is_double else f"ATR move {source}->{destination}"
            unload_action = f"ATR double-place at {destination}" if is_double else f"ATR unload at {destination}"
            if is_double and destination == "AL":
                members = pair_members_for_wafer(wafer_id)
                unload_action = (
                    "ATR single-place at AL"
                    if members and wafer_id == members[0]
                    else "ATR retain companion at AL"
                )
            elif is_double and source == "AL":
                members = pair_members_for_wafer(wafer_id)
                load_action = (
                    "ATR retain calibrated wafer"
                    if members and wafer_id == members[0]
                    else "ATR single-pick at AL"
                )
            add_path_task(lane_name, start, load_end, load_action, entity, "#4C78A8")
            add_path_task(lane_name, load_end, unload_start, move_action, entity, "#72B7B2")
            add_path_task(lane_name, unload_start, end, unload_action, entity, "#9C755F")

        full_pair_by_wafer = {
            wafer_id: pair_id
            for pair_id, members in full_pair_members.items()
            for wafer_id in members
        }
        mix_pair_by_wafer = {
            wafer_id: pair_id
            for pair_id, members in mix_pair_members.items()
            for wafer_id in members
        }

        def pair_members_for_wafer(wafer_id: int) -> List[int]:
            full_pair = full_pair_by_wafer.get(wafer_id)
            if full_pair is not None:
                return sorted(full_pair_members.get(full_pair, []))
            mix_pair = mix_pair_by_wafer.get(wafer_id)
            if mix_pair is not None:
                return sorted(mix_pair_members.get(mix_pair, []))
            return []

        def is_synchronized_pair_stage(wafer_id: int, stage_name: str) -> bool:
            members = pair_members_for_wafer(wafer_id)
            if len(members) != 2:
                return False
            first, second = members
            return (
                abs(product_start(first, stage_name) - product_start(second, stage_name)) <= 1e-6
                and abs(product_end(first, stage_name) - product_end(second, stage_name)) <= 1e-6
            )
        def paired_stage_interval(wafer_id: int, stage_name: str) -> Tuple[float, float]:
            """Return a shared pair action even when the solution exports it once."""
            start = product_start(wafer_id, stage_name)
            end = product_end(wafer_id, stage_name)
            if end > start + 1e-9:
                return start, end
            for member_id in pair_members_for_wafer(wafer_id):
                member_start = product_start(member_id, stage_name)
                member_end = product_end(member_id, stage_name)
                if member_end > member_start + 1e-9:
                    return member_start, member_end
            return start, end

        full_pair_location = {
            pair_id: (pm_id, batch_id, side_id)
            for (pm_id, batch_id, side_id), pair_id in full_assignment.items()
        }
        mix_pair_location = {
            pair_id: (pm_id, pos_id)
            for (pm_id, pos_id), pair_id in mix_pair_by_pos.items()
        }

        def product_lane_suffix(wafer_id: int) -> str:
            full_pair = full_pair_by_wafer.get(wafer_id)
            if full_pair is not None:
                location = full_pair_location.get(full_pair)
                if location is None:
                    return " | 4x1"
                pm_id, batch_id, side_id = location
                return f" | 4x1 CH{pm_id}-B{batch_id}-S{side_id}"
            mix_pair = mix_pair_by_wafer.get(wafer_id)
            if mix_pair is not None:
                location = mix_pair_location.get(mix_pair)
                if location is None:
                    return " | 2x2"
                pm_id, pos_id = location
                return f" | 2x2 CH{pm_id}-P{pos_id}"
            return ""

        def pm_process_label(wafer_id: int) -> str:
            if wafer_id in full_pair_by_wafer:
                return "4x1 PM process"
            if wafer_id in mix_pair_by_wafer:
                return "2x2 PM process"
            return "PM process"

        def add_pm_path_tasks(lane_name: str, wafer_id: int, entity: str) -> None:
            mix_pair = mix_pair_by_wafer.get(wafer_id)
            location = mix_pair_location.get(mix_pair) if mix_pair is not None else None
            pm_window_start = product_start(wafer_id, "pm")
            pm_window_end = product_end(wafer_id, "pm")
            if location is not None:
                pm_id, _ = location
                cycle_pattern = re.compile(rf"mix_cycle_start_{pm_id}_(\d+)$")
                matching_cycles = []
                for variable_name in solution:
                    match = cycle_pattern.match(variable_name)
                    if not match:
                        continue
                    cycle_id = int(match.group(1))
                    cycle_start = _float(solution.get(variable_name, 0.0))
                    cycle_end = _float(solution.get(f"mix_cycle_end_{pm_id}_{cycle_id}", cycle_start))
                    if (
                        cycle_end > cycle_start + 1e-9
                        and cycle_start >= pm_window_start - PATH_TIME_TOLERANCE
                        and cycle_end <= pm_window_end + PATH_TIME_TOLERANCE
                    ):
                        matching_cycles.append((cycle_start, cycle_end, cycle_id))
                matching_cycles.sort()
                if (
                    len(matching_cycles) >= 2
                    and abs(matching_cycles[0][0] - pm_window_start) <= PATH_TIME_TOLERANCE
                    and abs(matching_cycles[-1][1] - pm_window_end) <= PATH_TIME_TOLERANCE
                ):
                    for cycle_index, (cycle_start, cycle_end, _) in enumerate(matching_cycles, start=1):
                        if cycle_index == 1:
                            cycle_start = pm_window_start
                        if cycle_index == len(matching_cycles):
                            cycle_end = pm_window_end
                        if cycle_index > 1:
                            previous_end = matching_cycles[cycle_index - 2][1]
                            add_path_task(
                                lane_name,
                                previous_end,
                                cycle_start,
                                "2x2 in-chamber bridge/wait",
                                entity,
                                "#BAB0AC",
                            )
                        add_path_task(
                            lane_name,
                            cycle_start,
                            cycle_end,
                            f"2x2 PM process #{cycle_index}",
                            entity,
                            "#E45756",
                        )
                    return
            add_path_task(
                lane_name,
                pm_window_start,
                pm_window_end,
                pm_process_label(wafer_id),
                entity,
                "#E45756",
            )

        product_ids = sorted(
            {wafer_id for wafer_id, _ in prod_stage_start.keys()} | {wafer_id for wafer_id, _ in prod_stage_end.keys()},
            key=lambda wafer_id: (
                prod_stage_start.get((wafer_id, "atr_lp_al"), prod_stage_end.get((wafer_id, "atr_lp_al"), 0.0)),
                wafer_id,
            ),
        )
        for wafer_id in product_ids:
            assignment = assign_prod_by_wafer.get(wafer_id)
            lane_name = f"Product W{wafer_id}{product_lane_suffix(wafer_id)}"
            if assignment is not None:
                lane_name += f" | PM{assignment[0]}-B{assignment[1]}"
            lanes.append(lane_name)
            entity = f"W{wafer_id}"

            add_atr_path_transfer(lane_name, wafer_id, "atr_lp_al", "LP", "AL", entity)
            lp_al_end = product_end(wafer_id, "atr_lp_al")
            hold_before_al_end = product_end(wafer_id, "atr_hold_before_al")
            add_path_task(
                lane_name,
                product_start(wafer_id, "atr_hold_before_al"),
                hold_before_al_end,
                "ATR holding for AL",
                entity,
                "#B07AA1",
            )
            exchange_start, exchange_end = paired_stage_interval(wafer_id, "atr_al_exchange")
            add_path_task(
                lane_name,
                exchange_start,
                exchange_end,
                (
                    "ATR single-wafer exchange at AL"
                    if product_end(wafer_id, "atr_al_exchange")
                    > product_start(wafer_id, "atr_al_exchange") + 1e-9
                    else "ATR holding calibrated wafer during AL exchange"
                ),
                entity,
                "#D37295",
            )
            add_path_task(
                lane_name,
                max(lp_al_end, hold_before_al_end, exchange_end),
                product_start(wafer_id, "al"),
                "AL wait",
                entity,
                "#C6A07A",
            )
            add_path_task(
                lane_name,
                product_start(wafer_id, "al"),
                product_end(wafer_id, "al"),
                "AL align",
                entity,
                "#9C755F",
            )
            hold_after_al_end = product_end(wafer_id, "atr_hold_after_al")
            add_path_task(
                lane_name,
                product_start(wafer_id, "atr_hold_after_al"),
                hold_after_al_end,
                "ATR holding calibrated wafer",
                entity,
                "#B07AA1",
            )
            add_path_task(
                lane_name,
                max(product_end(wafer_id, "al"), hold_after_al_end),
                product_start(wafer_id, "atr_al_llupper"),
                "AL wait",
                entity,
                "#C6A07A",
            )
            add_atr_path_transfer(lane_name, wafer_id, "atr_al_llupper", "AL", "LLupper", entity)
            add_path_task(
                lane_name,
                product_end(wafer_id, "atr_al_llupper"),
                product_start(wafer_id, "llupper"),
                "LLupper wait",
                entity,
                "#8CD17D",
            )
            add_path_task(
                lane_name,
                product_start(wafer_id, "llupper"),
                product_end(wafer_id, "llupper"),
                "LLupper pump: atmosphere->vacuum",
                entity,
                "#54A24B",
            )
            add_path_task(
                lane_name,
                product_end(wafer_id, "llupper"),
                product_start(wafer_id, "vtr_load"),
                "LLupper vacuum ready/wait",
                entity,
                "#8CD17D",
            )
            add_path_task(
                lane_name,
                product_start(wafer_id, "vtr_load"),
                product_end(wafer_id, "vtr_load"),
                "VTR double load" if is_synchronized_pair_stage(wafer_id, "vtr_load") else "VTR load",
                entity,
                "#F58518",
            )
            add_path_task(
                lane_name,
                product_end(wafer_id, "vtr_load"),
                product_start(wafer_id, "pm"),
                "PM wait",
                entity,
                "#F2A09A",
            )
            add_pm_path_tasks(lane_name, wafer_id, entity)
            add_path_task(
                lane_name,
                product_end(wafer_id, "pm"),
                product_start(wafer_id, "vtr_unload"),
                "PM wait",
                entity,
                "#F2A09A",
            )
            add_path_task(
                lane_name,
                product_start(wafer_id, "vtr_unload"),
                product_end(wafer_id, "vtr_unload"),
                "VTR double unload" if is_synchronized_pair_stage(wafer_id, "vtr_unload") else "VTR unload",
                entity,
                "#FF9DA6",
            )
            add_path_task(
                lane_name,
                product_end(wafer_id, "vtr_unload"),
                product_start(wafer_id, "lllower"),
                "LLlower wait",
                entity,
                "#D4A6C8",
            )
            add_path_task(
                lane_name,
                product_start(wafer_id, "lllower"),
                product_end(wafer_id, "lllower"),
                "LLlower vent: vacuum->atmosphere",
                entity,
                "#B279A2",
            )
            add_path_task(
                lane_name,
                product_end(wafer_id, "lllower"),
                product_start(wafer_id, "atr_lllower_lp"),
                "LLlower atmosphere ready/wait",
                entity,
                "#D4A6C8",
            )
            add_atr_path_transfer(lane_name, wafer_id, "atr_lllower_lp", "LLlower", "LP", entity)

        pec_ids = sorted(
            {pec_id for pec_id, _ in pec_stage_start.keys()} | {pec_id for pec_id, _ in pec_stage_end.keys()},
            key=lambda pec_id: (
                pec_stage_start.get((pec_id, "vtr_load"), pec_stage_end.get((pec_id, "vtr_load"), 0.0)),
                pec_id,
            ),
        )
        active_pec_ids = [
            pec_id
            for pec_id in pec_ids
            if any(
                pec_stage_end.get((pec_id, stage_name), 0.0)
                > pec_stage_start.get((pec_id, stage_name), 0.0) + 1e-9
                for stage_name in NEW_PEC_STAGE_ORDER
            )
        ]

        # PEC identity is intentionally anonymous in the scheduling model.
        # Create deterministic display-only token identities in chronological
        # round-robin order. A busy token is skipped, so the coloring remains
        # physically feasible while producing PEC1..PECN, then wrapping.
        configured_pool_size = int(_float(solution.get("_gantt_pec_pool_size", 0.0)))
        inferred_pool_size = max(pec_token_by_job.values(), default=0)
        pec_pool_size = max(configured_pool_size, inferred_pool_size)
        if active_pec_ids and pec_pool_size <= 0:
            raise ValueError(
                "Cannot assign anonymous PEC display lanes: pec_pool_size is missing."
            )

        display_token_by_job: Dict[int, int] = {}
        token_available = {token_id: -math.inf for token_id in range(1, pec_pool_size + 1)}
        next_token = 1
        chronological_jobs = sorted(
            active_pec_ids,
            key=lambda job_id: (
                pec_stage_start.get((job_id, "vtr_load"), 0.0),
                job_id,
            ),
        )
        for pec_id in chronological_jobs:
            load_start = pec_stage_start.get((pec_id, "vtr_load"), 0.0)
            unload_end = pec_stage_end.get((pec_id, "vtr_unload"), load_start)
            selected_token = None
            for offset in range(pec_pool_size):
                token_id = ((next_token - 1 + offset) % pec_pool_size) + 1
                if token_available[token_id] <= load_start + PATH_TIME_TOLERANCE:
                    selected_token = token_id
                    break
            if selected_token is None:
                raise ValueError(
                    f"Anonymous PEC capacity violation at t={load_start:.6f}: "
                    f"all {pec_pool_size} display tokens are still occupied."
                )
            display_token_by_job[pec_id] = selected_token
            token_available[selected_token] = unload_end
            next_token = selected_token % pec_pool_size + 1

        pec_jobs_by_lane: Dict[int, List[int]] = {}
        for pec_id, token_id in display_token_by_job.items():
            pec_jobs_by_lane.setdefault(token_id, []).append(pec_id)

        ordered_pec_lanes = sorted(
            pec_jobs_by_lane.items(),
            key=lambda item: (
                min(pec_stage_start.get((job_id, "vtr_load"), 0.0) for job_id in item[1]),
                item[0],
            ),
        )
        for token_id, job_ids in ordered_pec_lanes:
            job_ids = sorted(
                job_ids,
                key=lambda job_id: (
                    pec_stage_start.get((job_id, "vtr_load"), 0.0),
                    job_id,
                ),
            )
            lane_name = f"PEC P{token_id} | jobs " + ",".join(f"E{job_id}" for job_id in job_ids)
            physical_entity = f"PEC{token_id}"
            lanes.append(lane_name)

            previous_return = None
            for pec_id in job_ids:
                entity = f"{physical_entity}/E{pec_id}"
                load_start = pec_stage_start.get((pec_id, "vtr_load"), 0.0)
                load_end = pec_stage_end.get((pec_id, "vtr_load"), load_start)
                pm_start = pec_stage_start.get((pec_id, "pm"), load_end)
                pm_end = pec_stage_end.get((pec_id, "pm"), pm_start)
                unload_start = pec_stage_start.get((pec_id, "vtr_unload"), pm_end)
                unload_end = pec_stage_end.get((pec_id, "vtr_unload"), unload_start)
                if abs(pm_start - load_end) <= PATH_TIME_TOLERANCE:
                    pm_start = load_end
                if abs(unload_start - pm_end) <= PATH_TIME_TOLERANCE:
                    unload_start = pm_end
                if previous_return is not None:
                    if abs(load_start - previous_return) <= PATH_TIME_TOLERANCE:
                        load_start = previous_return
                    add_path_task(
                        lane_name,
                        previous_return,
                        load_start,
                        "PEC storage wait",
                        physical_entity,
                        "#BAB0AC",
                    )
                add_path_task(lane_name, load_start, load_end, "VTR PEC storage->CH", entity, "#72B7B2")
                add_path_task(lane_name, load_end, pm_start, "CH wait", entity, "#F2A09A")
                add_path_task(lane_name, pm_start, pm_end, "CH process", entity, "#E45756")
                add_path_task(lane_name, pm_end, unload_start, "CH wait", entity, "#F2A09A")
                add_path_task(lane_name, unload_start, unload_end, "VTR CH->PEC storage", entity, "#B279A2")
                previous_return = unload_end
        if not lanes:
            return {}

        _validate_continuous_entity_lanes(lanes, tasks)
        horizon = max(time_candidates) if time_candidates else 0.0
        return {
            "is_petri": True,
            "layout": "path",
            "lanes": lanes,
            "tasks": tasks,
            "markers": [],
            "horizon": max(horizon, 1.0),
            "c_max": c_max,
        }

    used_batches = sorted(
        [
            key
            for key, used in batch_used.items()
            if used and batch_end.get(key, batch_start.get(key, 0.0)) > batch_start.get(key, 0.0)
        ],
        key=lambda item: (batch_start.get(item, 0.0), item[0], item[1]),
    )
    if not used_batches:
        return {}

    lanes: List[str] = []
    tasks: List[Dict[str, object]] = []
    time_candidates = [c_max]

    for pm_id, slot_id in used_batches:
        prod_members = sorted(assign_prod_by_batch.get((pm_id, slot_id), []))
        pec_members = sorted(assign_pec_by_batch.get((pm_id, slot_id), []))
        members = [("prod", pair_id) for pair_id in prod_members] + [("pec", pair_id) for pair_id in pec_members]

        for member_type, member_id in members:
            if member_type == "prod":
                lane_name = f"PM{pm_id}-S{slot_id} | Product P{member_id} (W{2 * member_id - 1},W{2 * member_id})"
                lanes.append(lane_name)
                front_start = prod_stage_start.get((member_id, "atr_lp_al_a"), 0.0)
                front_end = prod_stage_end.get((member_id, "llupper"), front_start)
                load_start = prod_stage_start.get((member_id, "vtr_load"), front_end)
                load_end = prod_stage_end.get((member_id, "vtr_load"), load_start)
                return_start = prod_stage_start.get((member_id, "vtr_unload"), load_end)
                return_end = prod_stage_end.get((member_id, "atr_lllower_lp"), return_start)
                if front_end > front_start:
                    tasks.append(
                        {
                            "lane": lane_name,
                            "start": front_start,
                            "end": front_end,
                            "label": "Front-End Path",
                            "short_label": "Front-End",
                            "color": "#4C78A8",
                        }
                    )
                    time_candidates.append(front_end)
                if load_end > load_start:
                    tasks.append(
                        {
                            "lane": lane_name,
                            "start": load_start,
                            "end": load_end,
                            "label": f"Load to PM{pm_id}",
                            "short_label": "Load",
                            "color": "#F58518",
                        }
                    )
                    time_candidates.append(load_end)
                if return_end > return_start:
                    tasks.append(
                        {
                            "lane": lane_name,
                            "start": return_start,
                            "end": return_end,
                            "label": "Return to LP",
                            "short_label": "Return",
                            "color": "#54A24B",
                        }
                    )
                    time_candidates.append(return_end)
            else:
                lane_name = f"PM{pm_id}-S{slot_id} | PEC E{member_id} (PEC{2 * member_id - 1},PEC{2 * member_id})"
                lanes.append(lane_name)
                load_start = pec_stage_start.get((member_id, "vtr_load"), 0.0)
                load_end = pec_stage_end.get((member_id, "vtr_load"), load_start)
                return_start = pec_stage_start.get((member_id, "vtr_unload"), load_end)
                return_end = pec_stage_end.get((member_id, "vtr_unload"), return_start)
                if load_end > load_start:
                    tasks.append(
                        {
                            "lane": lane_name,
                            "start": load_start,
                            "end": load_end,
                            "label": f"PEC to PM{pm_id}",
                            "short_label": "PEC->PM",
                            "color": "#72B7B2",
                        }
                    )
                    time_candidates.append(load_end)
                if return_end > return_start:
                    tasks.append(
                        {
                            "lane": lane_name,
                            "start": return_start,
                            "end": return_end,
                            "label": "Return to PEC",
                            "short_label": "PM->PEC",
                            "color": "#B279A2",
                        }
                    )
                    time_candidates.append(return_end)

        pm_lane = f"PM{pm_id}-S{slot_id} | Process"
        lanes.append(pm_lane)
        batch_label_parts = [f"P{pair_id}" for pair_id in prod_members] + [f"E{pair_id}" for pair_id in pec_members]
        start = batch_start.get((pm_id, slot_id), 0.0)
        end = batch_end.get((pm_id, slot_id), start)
        release = batch_release.get((pm_id, slot_id), end)
        if end > start:
            tasks.append(
                {
                    "lane": pm_lane,
                    "start": start,
                    "end": end,
                    "label": "PM Process\n" + " + ".join(batch_label_parts),
                    "short_label": "Process",
                    "color": "#E45756",
                }
            )
            time_candidates.append(end)
        if release > end:
            tasks.append(
                {
                    "lane": pm_lane,
                    "start": end,
                    "end": release,
                    "label": "Unload and Release",
                    "short_label": "Release",
                    "color": "#BAB0AC",
                }
            )
            time_candidates.append(release)

    horizon = max(time_candidates) if time_candidates else 0.0
    return {
        "is_petri": True,
        "layout": "path",
        "lanes": lanes,
        "tasks": tasks,
        "markers": [],
        "horizon": max(horizon, 1.0),
        "c_max": c_max,
    }


def _collect_legacy_schedule(solution: Dict[str, float]) -> Dict[str, object]:
    full_pairs_by_slot: Dict[Tuple[str, int], List[int]] = {}
    full_pec_by_slot: Dict[Tuple[str, int], bool] = {}
    full_start: Dict[Tuple[str, int], float] = {}
    full_end: Dict[Tuple[str, int], float] = {}
    full_used: Dict[Tuple[str, int], bool] = {}
    mix_pair_by_pos: Dict[Tuple[str, int], int] = {}
    mix_start: Dict[Tuple[str, int], float] = {}
    mix_end: Dict[Tuple[str, int], float] = {}
    mix_used: Dict[Tuple[str, int], bool] = {}
    full_pair_members: Dict[int, List[int]] = {}
    mix_pair_members: Dict[int, List[int]] = {}
    pair_completion: Dict[str, float] = {}
    wafer_completion: Dict[int, float] = {}
    c_max = _float(solution.get("c_max", 0.0))

    for name, value in solution.items():
        m = NEW_FULL_PAIR_MEMBER_RE.match(name)
        if m and _bool(value):
            full_pair_members.setdefault(int(m.group(2)), []).append(int(m.group(1)))
            continue
        m = NEW_MIX_PAIR_MEMBER_RE.match(name)
        if m and _bool(value):
            mix_pair_members.setdefault(int(m.group(2)), []).append(int(m.group(1)))
            continue
        m = NEW_FULL_PAIR_COMPLETION_RE.match(name)
        if m:
            pair_completion[f"F{int(m.group(1))}"] = _float(value)
            continue
        m = NEW_MIX_PAIR_COMPLETION_RE.match(name)
        if m:
            pair_completion[f"M{int(m.group(1))}"] = _float(value)
            continue
        m = NEW_WAFER_COMPLETION_RE.match(name)
        if m:
            wafer_completion[int(m.group(1))] = _float(value)
            continue
        m = LEGACY_FULL_ASSIGN_RE.match(name)
        if m and _bool(value):
            pair_id = int(m.group(1))
            lane = f"PM{int(m.group(2))} 4x1"
            slot_id = int(m.group(3))
            full_pairs_by_slot.setdefault((lane, slot_id), []).append(pair_id)
            continue
        m = LEGACY_FULL_PEC_RE.match(name)
        if m:
            full_pec_by_slot[(f"PM{int(m.group(1))} 4x1", int(m.group(2)))] = _bool(value)
            continue
        m = LEGACY_FULL_START_RE.match(name)
        if m:
            full_start[(f"PM{int(m.group(1))} 4x1", int(m.group(2)))] = _float(value)
            continue
        m = LEGACY_FULL_END_RE.match(name)
        if m:
            full_end[(f"PM{int(m.group(1))} 4x1", int(m.group(2)))] = _float(value)
            continue
        m = LEGACY_FULL_USED_RE.match(name)
        if m:
            full_used[(f"PM{int(m.group(1))} 4x1", int(m.group(2)))] = _bool(value)
            continue
        m = LEGACY_MIX_ASSIGN_RE.match(name)
        if m and _bool(value):
            mix_pair_by_pos[(f"PM{int(m.group(2))} 2x2", int(m.group(3)))] = int(m.group(1))
            continue
        m = LEGACY_MIX_START_RE.match(name)
        if m:
            mix_start[(f"PM{int(m.group(1))} 2x2", int(m.group(2)))] = _float(value)
            continue
        m = LEGACY_MIX_END_RE.match(name)
        if m:
            mix_end[(f"PM{int(m.group(1))} 2x2", int(m.group(2)))] = _float(value)
            continue
        m = LEGACY_MIX_USED_RE.match(name)
        if m:
            mix_used[(f"PM{int(m.group(1))} 2x2", int(m.group(2)))] = _bool(value)
            continue
        m = LEGACY_PAIR_COMPLETION_RE.match(name)
        if m:
            pair_completion[f"P{int(m.group(1))}"] = _float(value)

    def _full_pair_label(pair_id: int) -> str:
        wafers = sorted(full_pair_members.get(pair_id, []))
        if not wafers:
            return f"F{pair_id}"
        if len(wafers) == 1:
            return f"F{pair_id}(W{wafers[0]}+PEC)"
        return f"F{pair_id}(" + ",".join(f"W{wafer_id}" for wafer_id in wafers) + ")"

    def _mix_pair_label(pair_id: int) -> str:
        wafers = sorted(mix_pair_members.get(pair_id, []))
        if not wafers:
            return f"M{pair_id}"
        if len(wafers) == 1:
            return f"M{pair_id}(W{wafers[0]}+PEC)"
        return f"M{pair_id}(" + ",".join(f"W{wafer_id}" for wafer_id in wafers) + ")"

    lanes: List[str] = []
    tasks: List[Dict[str, object]] = []
    markers: List[Dict[str, object]] = []
    time_candidates = [c_max]

    full_keys = sorted(
        set(full_pairs_by_slot) | set(full_start) | set(full_end) | set(full_used),
        key=lambda item: (item[0], item[1]),
    )
    for lane_name, slot_id in full_keys:
        if not full_used.get((lane_name, slot_id), False):
            continue
        start = full_start.get((lane_name, slot_id), 0.0)
        end = full_end.get((lane_name, slot_id), start)
        if end <= start:
            continue
        if lane_name not in lanes:
            lanes.append(lane_name)
        pairs = sorted(full_pairs_by_slot.get((lane_name, slot_id), []))
        label = ",".join(_full_pair_label(pair_id) for pair_id in pairs) if pairs else "-"
        if full_pec_by_slot.get((lane_name, slot_id), False):
            label = f"{label} + Pure PEC"
        tasks.append(
            {
                "lane": lane_name,
                "start": start,
                "end": end,
                "label": f"slot {slot_id}\n{label}",
                "short_label": f"S{slot_id}",
                "color": "#4C78A8",
            }
        )
        time_candidates.append(end)

    mix_lanes = sorted({lane for lane, _ in set(mix_pair_by_pos) | set(mix_start) | set(mix_end) | set(mix_used)})
    for lane_name in mix_lanes:
        if lane_name not in lanes:
            lanes.append(lane_name)
        lane_positions = [pos_id for (lane, pos_id), _ in mix_pair_by_pos.items() if lane == lane_name]
        max_pos = max(lane_positions, default=0)
        cycle_ids = sorted({cycle_id for (lane, cycle_id) in set(mix_start) | set(mix_end) | set(mix_used) if lane == lane_name})
        for cycle_id in cycle_ids:
            if not mix_used.get((lane_name, cycle_id), False):
                continue
            start = mix_start.get((lane_name, cycle_id), 0.0)
            end = mix_end.get((lane_name, cycle_id), start)
            if end <= start:
                continue
            if cycle_id == 1:
                first_pair = mix_pair_by_pos.get((lane_name, 1))
                label = (
                    f"cycle 1\nPEC + {_mix_pair_label(first_pair)} 1st"
                    if first_pair is not None
                    else "cycle 1\nPEC"
                )
                color = "#F58518"
            elif cycle_id == max_pos + 1 and max_pos > 0:
                prev_pair = mix_pair_by_pos.get((lane_name, max_pos))
                label = (
                    f"cycle {cycle_id}\n{_mix_pair_label(prev_pair)} 2nd + PEC"
                    if prev_pair is not None
                    else f"cycle {cycle_id}\nPEC"
                )
                color = "#F58518"
            else:
                prev_pair = mix_pair_by_pos.get((lane_name, cycle_id - 1))
                curr_pair = mix_pair_by_pos.get((lane_name, cycle_id))
                label = (
                    f"cycle {cycle_id}\n{_mix_pair_label(prev_pair)} 2nd + {_mix_pair_label(curr_pair)} 1st"
                    if prev_pair is not None and curr_pair is not None
                    else f"cycle {cycle_id}"
                )
                color = "#54A24B"
            tasks.append(
                {
                    "lane": lane_name,
                    "start": start,
                    "end": end,
                    "label": label,
                    "short_label": f"C{cycle_id}",
                    "color": color,
                }
            )
            time_candidates.append(end)

    if pair_completion:
        lanes.append("Pair completion")
    for pair_id, completion in sorted(pair_completion.items()):
        markers.append(
            {
                "lane": "Pair completion",
                "time": completion,
                "label": str(pair_id),
            }
        )
        time_candidates.append(completion)

    if wafer_completion:
        lanes.append("Wafer completion")
    for wafer_id, completion in sorted(wafer_completion.items()):
        markers.append(
            {
                "lane": "Wafer completion",
                "time": completion,
                "label": f"W{wafer_id}",
            }
        )
        time_candidates.append(completion)

    if not tasks and not markers:
        return {}
    horizon = max(time_candidates) if time_candidates else 0.0
    return {
        "is_petri": True,
        "layout": "legacy",
        "lanes": lanes,
        "tasks": tasks,
        "markers": markers,
        "horizon": max(horizon, 1.0),
        "c_max": c_max,
    }


def _collect_chamber_schedule(solution: Dict[str, float]) -> Dict[str, object]:
    full_pair_members: Dict[int, List[int]] = {}
    mix_pair_members: Dict[int, List[int]] = {}
    full_assignment: Dict[Tuple[int, int, int], int] = {}
    full_used: Dict[Tuple[int, int], bool] = {}
    full_filler: Dict[Tuple[int, int, int], bool] = {}
    mix_pair_by_pos: Dict[Tuple[int, int], int] = {}
    mix_active: Dict[int, bool] = {}
    mix_cycle_used: Dict[Tuple[int, int], bool] = {}
    mix_last_pos: Dict[int, int] = {}
    clean_active: Dict[Tuple[int, int], bool] = {}
    pec_stage_start: Dict[Tuple[int, str], float] = {}
    pec_stage_end: Dict[Tuple[int, str], float] = {}
    pec_token_by_job: Dict[int, int] = {}
    explicit_pec_pm_by_job: Dict[int, int] = {}
    pm_ids = set()

    for name, value in solution.items():
        m = PEC_STAGE_START_RE.match(name)
        if m:
            pec_stage_start[(int(m.group(1)), m.group(2))] = _float(value)
            continue
        m = PEC_STAGE_END_RE.match(name)
        if m:
            pec_stage_end[(int(m.group(1)), m.group(2))] = _float(value)
            continue
        m = PEC_TOKEN_ASSIGN_RE.match(name)
        if m and _bool(value):
            pec_token_by_job[int(m.group(1))] = int(m.group(2))
            continue
        m = PEC_JOB_CHAMBER_RE.match(name)
        if m and _bool(value):
            chamber_id = int(m.group(2))
            explicit_pec_pm_by_job[int(m.group(1))] = chamber_id
            pm_ids.add(chamber_id)
            continue
        m = NEW_FULL_PAIR_MEMBER_RE.match(name)
        if m and _bool(value):
            full_pair_members.setdefault(int(m.group(2)), []).append(int(m.group(1)))
            continue
        m = NEW_MIX_PAIR_MEMBER_RE.match(name)
        if m and _bool(value):
            mix_pair_members.setdefault(int(m.group(2)), []).append(int(m.group(1)))
            continue
        m = NEW_FULL_ASSIGN_RE.match(name)
        if m and _bool(value):
            pair_id = int(m.group(1))
            pm_id = int(m.group(2))
            batch_id = int(m.group(3))
            side_id = int(m.group(4))
            full_assignment[(pm_id, batch_id, side_id)] = pair_id
            pm_ids.add(pm_id)
            continue
        m = NEW_FULL_BATCH_USED_RE.match(name)
        if m:
            key = (int(m.group(1)), int(m.group(2)))
            full_used[key] = _bool(value)
            if full_used[key]:
                pm_ids.add(key[0])
            continue
        m = NEW_FULL_FILLER_SIDE_RE.match(name)
        if m:
            key = (int(m.group(1)), int(m.group(2)), int(m.group(3)))
            full_filler[key] = _bool(value)
            if full_filler[key]:
                pm_ids.add(key[0])
            continue
        m = NEW_MIX_ASSIGN_RE.match(name)
        if m and _bool(value):
            pair_id = int(m.group(1))
            pm_id = int(m.group(2))
            pos_id = int(m.group(3))
            mix_pair_by_pos[(pm_id, pos_id)] = pair_id
            pm_ids.add(pm_id)
            continue
        m = NEW_MIX_ACTIVE_RE.match(name)
        if m:
            pm_id = int(m.group(1))
            mix_active[pm_id] = _bool(value)
            if mix_active[pm_id]:
                pm_ids.add(pm_id)
            continue
        m = NEW_MIX_CYCLE_USED_RE.match(name)
        if m:
            key = (int(m.group(1)), int(m.group(2)))
            mix_cycle_used[key] = _bool(value)
            if mix_cycle_used[key]:
                pm_ids.add(key[0])
            continue
        m = NEW_MIX_LAST_POS_RE.match(name)
        if m and _bool(value):
            pm_id = int(m.group(1))
            mix_last_pos[pm_id] = int(m.group(2))
            pm_ids.add(pm_id)
            continue
        m = NEW_CLEAN_ACTIVE_RE.match(name)
        if m:
            key = (int(m.group(1)), int(m.group(2)))
            clean_active[key] = _bool(value)
            if clean_active[key]:
                pm_ids.add(key[0])

    def time_var(name: str) -> float:
        return _float(solution.get(name, 0.0))

    def same_time(left: float, right: float) -> bool:
        return abs(left - right) <= 1e-6

    def pec_entity(job_id: int) -> str:
        token_id = pec_token_by_job.get(job_id)
        return f"PEC{token_id}" if token_id is not None else f"E{job_id}"

    pec_job_ids = sorted({job_id for job_id, _ in pec_stage_start} | {job_id for job_id, _ in pec_stage_end})

    def pec_entities_for_refs(
        load_start: float,
        load_end: float,
        pm_start: float,
        pm_end: float,
        unload_start: float,
        unload_end: float,
    ) -> List[str]:
        entities = []
        for job_id in pec_job_ids:
            if (
                same_time(pec_stage_start.get((job_id, "vtr_load"), -1.0), load_start)
                and same_time(pec_stage_end.get((job_id, "vtr_load"), -1.0), load_end)
                and same_time(pec_stage_start.get((job_id, "pm"), -1.0), pm_start)
                and same_time(pec_stage_end.get((job_id, "pm"), -1.0), pm_end)
                and same_time(pec_stage_start.get((job_id, "vtr_unload"), -1.0), unload_start)
                and same_time(pec_stage_end.get((job_id, "vtr_unload"), -1.0), unload_end)
            ):
                entities.append(pec_entity(job_id))
        return sorted(entities, key=_entity_sort_key)

    def pec_entities_for_pm_interval(pm_start: float, pm_end: float) -> List[str]:
        entities = []
        for job_id in pec_job_ids:
            if (
                same_time(pec_stage_start.get((job_id, "pm"), -1.0), pm_start)
                and same_time(pec_stage_end.get((job_id, "pm"), -1.0), pm_end)
            ):
                entities.append(pec_entity(job_id))
        return sorted(entities, key=_entity_sort_key)

    def pec_text(entities: List[str], fallback: str = "PEC") -> str:
        if fallback == "PEC+PEC" and len(entities) == 1:
            return f"{entities[0]}+PEC"
        return _format_entity_list(entities) if entities else fallback

    def full_pair_label(pair_id: int, pec_entities: List[str] = None) -> str:
        wafers = sorted(full_pair_members.get(pair_id, []))
        if not wafers:
            return f"F{pair_id}"
        if len(wafers) == 1:
            return f"F{pair_id}(W{wafers[0]}+{pec_text(pec_entities or [])})"
        return f"F{pair_id}(" + ",".join(f"W{wafer_id}" for wafer_id in wafers) + ")"

    def mix_pair_label(pair_id: int, pec_entities: List[str] = None) -> str:
        wafers = sorted(mix_pair_members.get(pair_id, []))
        if not wafers:
            return f"M{pair_id}"
        if len(wafers) == 1:
            return f"M{pair_id}(W{wafers[0]}+{pec_text(pec_entities or [])})"
        return f"M{pair_id}(" + ",".join(f"W{wafer_id}" for wafer_id in wafers) + ")"

    def full_side_label(pm_id: int, batch_id: int, side_id: int) -> str:
        side_prefix = "front" if side_id == 1 else "back"
        side_pec_entities = pec_entities_for_refs(
            time_var(f"full_{side_prefix}_load_start_{pm_id}_{batch_id}"),
            time_var(f"full_{side_prefix}_load_end_{pm_id}_{batch_id}"),
            time_var(f"full_start_{pm_id}_{batch_id}"),
            time_var(f"full_end_{pm_id}_{batch_id}"),
            time_var(f"full_{side_prefix}_unload_start_{pm_id}_{batch_id}"),
            time_var(f"full_{side_prefix}_unload_end_{pm_id}_{batch_id}"),
        )
        if full_filler.get((pm_id, batch_id, side_id), False):
            return f"S{side_id}: {pec_text(side_pec_entities, 'PEC+PEC')}"
        pair_id = full_assignment.get((pm_id, batch_id, side_id))
        if pair_id is None:
            return f"S{side_id}: -"
        return f"S{side_id}: {full_pair_label(pair_id, side_pec_entities)}"

    if not (full_assignment or mix_pair_by_pos or clean_active):
        return {}

    ordered_pm_ids = [2, 3] if not pm_ids or pm_ids.issubset({2, 3}) else sorted(pm_ids)
    lanes = [f"CH{pm_id} four-pocket module" for pm_id in ordered_pm_ids]
    tasks: List[Dict[str, object]] = []
    time_candidates: List[float] = []

    for pm_id in ordered_pm_ids:
        lane_name = f"CH{pm_id} four-pocket module"

        batch_ids = sorted(
            batch_id
            for this_pm, batch_id in set(full_used) | {(pm, batch) for pm, batch, _ in full_assignment}
            if this_pm == pm_id
        )
        for batch_id in batch_ids:
            if not full_used.get((pm_id, batch_id), False):
                continue
            start = time_var(f"full_front_load_start_{pm_id}_{batch_id}")
            end = time_var(f"full_front_unload_end_{pm_id}_{batch_id}")
            process_start = time_var(f"full_start_{pm_id}_{batch_id}")
            process_end = time_var(f"full_end_{pm_id}_{batch_id}")
            if end <= start + 1e-9:
                start, end = process_start, process_end
            if end <= start + 1e-9:
                continue
            label = (
                f"4x1 batch {batch_id}\n"
                f"{full_side_label(pm_id, batch_id, 1)}\n"
                f"{full_side_label(pm_id, batch_id, 2)}"
            )
            tasks.append(
                {
                    "lane": lane_name,
                    "start": start,
                    "end": end,
                    "label": label,
                    "short_label": f"4x1 B{batch_id}",
                    "color": "#4C78A8",
                }
            )
            time_candidates.extend([start, end])

        has_mix_timing = (
            time_var(f"mix_head_end_{pm_id}") > time_var(f"mix_head_start_{pm_id}") + 1e-9
            or time_var(f"mix_tail_end_{pm_id}") > time_var(f"mix_tail_start_{pm_id}") + 1e-9
            or any(
                key_pm == pm_id
                and used
                and time_var(f"mix_cycle_end_{pm_id}_{cycle_id}")
                > time_var(f"mix_cycle_start_{pm_id}_{cycle_id}") + 1e-9
                for (key_pm, cycle_id), used in mix_cycle_used.items()
            )
        )
        active_mix = (
            mix_active.get(pm_id, False)
            or any(key_pm == pm_id for key_pm, _ in mix_pair_by_pos)
            or has_mix_timing
        )
        if active_mix:
            pos_ids = sorted(pos for key_pm, pos in mix_pair_by_pos if key_pm == pm_id)
            max_pos = mix_last_pos.get(pm_id, max(pos_ids, default=0))
            head_start = time_var(f"mix_head_start_{pm_id}")
            head_end = time_var(f"mix_head_end_{pm_id}")
            cycle1_start = time_var(f"mix_cycle_start_{pm_id}_1")
            cycle1_end = time_var(f"mix_cycle_end_{pm_id}_1")
            head_pec = pec_entities_for_refs(
                head_start,
                head_end,
                cycle1_start,
                cycle1_end,
                time_var(f"mix_bridge_start_{pm_id}_2"),
                time_var(f"mix_bridge_end_{pm_id}_2"),
            )
            last_cycle_id = max_pos + 1 if max_pos > 0 else 0
            tail_pec = pec_entities_for_refs(
                time_var(f"mix_tail_load_start_{pm_id}"),
                time_var(f"mix_tail_load_end_{pm_id}"),
                time_var(f"mix_last_cycle_start_{pm_id}"),
                time_var(f"mix_last_cycle_end_{pm_id}"),
                time_var(f"mix_tail_start_{pm_id}"),
                time_var(f"mix_tail_end_{pm_id}"),
            )

            def add_mix_wait(start: float, end: float, label: str) -> None:
                if end <= start + 1e-9:
                    return
                tasks.append(
                    {
                        "lane": lane_name,
                        "start": start,
                        "end": end,
                        "label": label,
                        "short_label": "wait",
                        "color": "#BAB0AC",
                    }
                )
                time_candidates.extend([start, end])

            first_pair = mix_pair_by_pos.get((pm_id, 1))
            if head_end > head_start + 1e-9:
                head_label = f"2x2 head\n{pec_text(head_pec)}"
                if first_pair is not None:
                    head_label = f"2x2 head\n{pec_text(head_pec)} + {mix_pair_label(first_pair)} 1st"
                tasks.append(
                    {
                        "lane": lane_name,
                        "start": head_start,
                        "end": head_end,
                        "label": head_label,
                        "short_label": "2x2 H",
                        "color": "#72B7B2",
                    }
                )
                time_candidates.extend([head_start, head_end])
            add_mix_wait(head_end, cycle1_start, "2x2 wait before cycle 1")

            cycle_ids = sorted(cycle for key_pm, cycle in mix_cycle_used if key_pm == pm_id and mix_cycle_used[(key_pm, cycle)])
            if not cycle_ids:
                cycle_ids = [
                    cycle_id
                    for cycle_id in range(1, max(max_pos + 2, 2))
                    if time_var(f"mix_cycle_end_{pm_id}_{cycle_id}")
                    > time_var(f"mix_cycle_start_{pm_id}_{cycle_id}") + 1e-9
                ]
            for cycle_id in cycle_ids:
                if cycle_id >= 2:
                    bridge_start = time_var(f"mix_bridge_start_{pm_id}_{cycle_id}")
                    bridge_end = time_var(f"mix_bridge_end_{pm_id}_{cycle_id}")
                    previous_cycle_end = time_var(f"mix_cycle_end_{pm_id}_{cycle_id - 1}")
                    add_mix_wait(previous_cycle_end, bridge_start, "2x2 wait before bridge")
                    if bridge_end > bridge_start + 1e-9:
                        bridge_parts = []
                        if cycle_id == 2:
                            bridge_parts.append(f"{pec_text(head_pec)} out")
                        out_pair = mix_pair_by_pos.get((pm_id, cycle_id - 2))
                        in_pair = mix_pair_by_pos.get((pm_id, cycle_id))
                        if out_pair is not None:
                            bridge_parts.append(f"{mix_pair_label(out_pair)} 2nd out")
                        if in_pair is not None:
                            bridge_parts.append(f"{mix_pair_label(in_pair)} 1st in")
                        if cycle_id == last_cycle_id:
                            bridge_parts.append(f"{pec_text(tail_pec)} in")
                        bridge_label = f"2x2 bridge {cycle_id}"
                        if bridge_parts:
                            bridge_label += "\n" + " + ".join(bridge_parts)
                        tasks.append(
                            {
                                "lane": lane_name,
                                "start": bridge_start,
                                "end": bridge_end,
                                "label": bridge_label,
                                "short_label": f"Br{cycle_id}",
                                "color": "#9C755F",
                            }
                        )
                        time_candidates.extend([bridge_start, bridge_end])

                start = time_var(f"mix_cycle_start_{pm_id}_{cycle_id}")
                end = time_var(f"mix_cycle_end_{pm_id}_{cycle_id}")
                if end <= start + 1e-9:
                    continue
                if cycle_id >= 2:
                    add_mix_wait(bridge_end, start, "2x2 wait after bridge")
                if cycle_id == 1:
                    label = f"cycle 1\n{pec_text(head_pec)}"
                    if first_pair is not None:
                        label = f"cycle 1\n{pec_text(head_pec)} + {mix_pair_label(first_pair)} 1st"
                    color = "#F58518"
                elif cycle_id == max_pos + 1 and max_pos > 0:
                    prev_pair = mix_pair_by_pos.get((pm_id, max_pos))
                    label = f"cycle {cycle_id}\n{pec_text(tail_pec)}"
                    if prev_pair is not None:
                        label = f"cycle {cycle_id}\n{mix_pair_label(prev_pair)} 2nd + {pec_text(tail_pec)}"
                    color = "#F58518"
                else:
                    prev_pair = mix_pair_by_pos.get((pm_id, cycle_id - 1))
                    curr_pair = mix_pair_by_pos.get((pm_id, cycle_id))
                    label = f"cycle {cycle_id}"
                    if prev_pair is not None and curr_pair is not None:
                        label = f"cycle {cycle_id}\n{mix_pair_label(prev_pair)} 2nd + {mix_pair_label(curr_pair)} 1st"
                    color = "#54A24B"
                tasks.append(
                    {
                        "lane": lane_name,
                        "start": start,
                        "end": end,
                        "label": label,
                        "short_label": f"C{cycle_id}",
                        "color": color,
                    }
                )
                time_candidates.extend([start, end])

            tail_start = time_var(f"mix_tail_start_{pm_id}")
            tail_end = time_var(f"mix_tail_end_{pm_id}")
            if cycle_ids:
                add_mix_wait(
                    time_var(f"mix_cycle_end_{pm_id}_{cycle_ids[-1]}"),
                    tail_start,
                    "2x2 wait before tail unload",
                )
            if tail_end > tail_start + 1e-9:
                last_pair = mix_pair_by_pos.get((pm_id, max_pos))
                tail_label = "2x2 tail\n"
                if last_pair is not None:
                    tail_label += f"{mix_pair_label(last_pair)} 2nd out + "
                tail_label += f"{pec_text(tail_pec)} return"
                tasks.append(
                    {
                        "lane": lane_name,
                        "start": tail_start,
                        "end": tail_end,
                        "label": tail_label,
                        "short_label": "2x2 T",
                        "color": "#B279A2",
                    }
                )
                time_candidates.extend([tail_start, tail_end])

        for clean_pm, clean_id in sorted(clean_active):
            if clean_pm != pm_id or not clean_active[(clean_pm, clean_id)]:
                continue
            start = time_var(f"clean_front_load_start_{pm_id}_{clean_id}")
            end = time_var(f"clean_front_unload_end_{pm_id}_{clean_id}")
            if end <= start + 1e-9:
                continue
            clean_pec = pec_entities_for_pm_interval(
                time_var(f"clean_start_{pm_id}_{clean_id}"),
                time_var(f"clean_end_{pm_id}_{clean_id}"),
            )
            tasks.append(
                {
                    "lane": lane_name,
                    "start": start,
                    "end": end,
                    "label": f"cleaning {clean_id}\n{pec_text(clean_pec, 'PEC')}",
                    "short_label": f"Clean {clean_id}",
                    "color": "#79706E",
                }
            )
            time_candidates.extend([start, end])

    if not tasks:
        return {}
    for task in tasks:
        task["max_label_lines"] = 3
    horizon = max(time_candidates) if time_candidates else 0.0
    return {
        "is_petri": True,
        "layout": "chambers",
        "title_suffix": "Chamber Modules Gantt",
        "lanes": lanes,
        "tasks": sorted(tasks, key=lambda task: (lanes.index(task["lane"]), float(task["start"]), float(task["end"]))),
        "markers": [],
        "horizon": max(horizon, 1.0),
        "c_max": _float(solution.get("c_max", 0.0)),
        "show_cmax": False,
    }


def _entity_sort_key(label: str) -> Tuple[int, int, str]:
    text = str(label)
    m = re.match(r"W(\d+)$", text)
    if m:
        return (0, int(m.group(1)), text)
    m = re.match(r"PEC(\d+)$", text)
    if m:
        return (1, int(m.group(1)), text)
    m = re.match(r"E(\d+)$", text)
    if m:
        return (2, int(m.group(1)), text)
    return (9, 0, text)


def _format_entity_list(entities: List[str]) -> str:
    unique = {str(entity).strip() for entity in entities if str(entity).strip()}
    return ", ".join(sorted(unique, key=_entity_sort_key))


def _collect_resource_schedule(solution: Dict[str, float]) -> Dict[str, object]:
    prod_stage_start: Dict[Tuple[int, str], float] = {}
    prod_stage_end: Dict[Tuple[int, str], float] = {}
    pec_stage_start: Dict[Tuple[int, str], float] = {}
    pec_stage_end: Dict[Tuple[int, str], float] = {}
    full_pair_members: Dict[int, List[int]] = {}
    mix_pair_members: Dict[int, List[int]] = {}
    full_assignment: Dict[Tuple[int, int, int], int] = {}
    mix_pair_by_pos: Dict[Tuple[int, int], int] = {}
    mix_last_pos: Dict[int, int] = {}
    llupper_slot_by_wafer: Dict[int, int] = {}
    lllower_slot_by_wafer: Dict[int, int] = {}
    atr_slots_by_task: Dict[str, List[int]] = {}
    vtr_slots_by_task: Dict[str, List[int]] = {}
    full_pair_vtr_windows: Dict[Tuple[int, str, str], float] = {}
    pec_token_by_job: Dict[int, int] = {}
    explicit_pec_pm_by_job: Dict[int, int] = {}
    full_process_start: Dict[Tuple[int, int], float] = {}
    full_process_end: Dict[Tuple[int, int], float] = {}
    mix_cycle_start: Dict[Tuple[int, int], float] = {}
    mix_cycle_end: Dict[Tuple[int, int], float] = {}
    clean_start: Dict[Tuple[int, int], float] = {}
    clean_end: Dict[Tuple[int, int], float] = {}
    pm_ids = set()

    for name, value in solution.items():
        m = PROD_STAGE_START_RE.match(name)
        if m:
            prod_stage_start[(int(m.group(1)), m.group(2))] = _float(value)
            continue
        m = PROD_STAGE_END_RE.match(name)
        if m:
            prod_stage_end[(int(m.group(1)), m.group(2))] = _float(value)
            continue
        m = PEC_STAGE_START_RE.match(name)
        if m:
            pec_stage_start[(int(m.group(1)), m.group(2))] = _float(value)
            continue
        m = PEC_STAGE_END_RE.match(name)
        if m:
            pec_stage_end[(int(m.group(1)), m.group(2))] = _float(value)
            continue
        m = NEW_FULL_PAIR_MEMBER_RE.match(name)
        if m and _bool(value):
            full_pair_members.setdefault(int(m.group(2)), []).append(int(m.group(1)))
            continue
        m = NEW_MIX_PAIR_MEMBER_RE.match(name)
        if m and _bool(value):
            mix_pair_members.setdefault(int(m.group(2)), []).append(int(m.group(1)))
            continue
        m = NEW_FULL_ASSIGN_RE.match(name)
        if m and _bool(value):
            pm_id = int(m.group(2))
            full_assignment[(pm_id, int(m.group(3)), int(m.group(4)))] = int(m.group(1))
            pm_ids.add(pm_id)
            continue
        m = NEW_MIX_ASSIGN_RE.match(name)
        if m and _bool(value):
            pm_id = int(m.group(2))
            mix_pair_by_pos[(pm_id, int(m.group(3)))] = int(m.group(1))
            pm_ids.add(pm_id)
            continue
        m = NEW_MIX_LAST_POS_RE.match(name)
        if m and _bool(value):
            pm_id = int(m.group(1))
            mix_last_pos[pm_id] = int(m.group(2))
            pm_ids.add(pm_id)
            continue
        m = LLUPPER_SLOT_ASSIGN_RE.match(name)
        if m and _bool(value):
            llupper_slot_by_wafer[int(m.group(1))] = int(m.group(2))
            continue
        m = LLLOWER_SLOT_ASSIGN_RE.match(name)
        if m and _bool(value):
            lllower_slot_by_wafer[int(m.group(1))] = int(m.group(2))
            continue
        m = ATR_SLOT_ASSIGN_RE.match(name)
        if m and _bool(value):
            atr_slots_by_task.setdefault(m.group(1), []).append(int(m.group(2)))
            continue
        m = VTR_SLOT_ASSIGN_RE.match(name)
        if m and _bool(value):
            vtr_slots_by_task.setdefault(m.group(1), []).append(int(m.group(2)))
            continue
        m = FULL_PAIR_VTR_WINDOW_RE.match(name)
        if m:
            full_pair_vtr_windows[(int(m.group(3)), m.group(1), m.group(2))] = _float(value)
            continue
        m = PEC_TOKEN_ASSIGN_RE.match(name)
        if m and _bool(value):
            pec_token_by_job[int(m.group(1))] = int(m.group(2))
            continue
        m = PEC_JOB_CHAMBER_RE.match(name)
        if m and _bool(value):
            chamber_id = int(m.group(2))
            explicit_pec_pm_by_job[int(m.group(1))] = chamber_id
            pm_ids.add(chamber_id)
            continue
        m = LEGACY_FULL_START_RE.match(name)
        if m:
            key = (int(m.group(1)), int(m.group(2)))
            full_process_start[key] = _float(value)
            pm_ids.add(key[0])
            continue
        m = LEGACY_FULL_END_RE.match(name)
        if m:
            key = (int(m.group(1)), int(m.group(2)))
            full_process_end[key] = _float(value)
            pm_ids.add(key[0])
            continue
        m = LEGACY_MIX_START_RE.match(name)
        if m:
            key = (int(m.group(1)), int(m.group(2)))
            mix_cycle_start[key] = _float(value)
            pm_ids.add(key[0])
            continue
        m = LEGACY_MIX_END_RE.match(name)
        if m:
            key = (int(m.group(1)), int(m.group(2)))
            mix_cycle_end[key] = _float(value)
            pm_ids.add(key[0])
            continue
        m = CLEAN_START_RE.match(name)
        if m:
            key = (int(m.group(1)), int(m.group(2)))
            clean_start[key] = _float(value)
            pm_ids.add(key[0])
            continue
        m = CLEAN_END_RE.match(name)
        if m:
            key = (int(m.group(1)), int(m.group(2)))
            clean_end[key] = _float(value)
            pm_ids.add(key[0])
            continue

    if not (prod_stage_start or pec_stage_start):
        return _collect_chamber_schedule(solution)

    pm_process_intervals: List[Tuple[int, float, float]] = []

    def add_pm_interval(pm_id: int, start: float, end: float) -> None:
        if end > start + 1e-9:
            pm_process_intervals.append((pm_id, start, end))
            pm_ids.add(pm_id)

    for key in set(full_process_start) | set(full_process_end):
        add_pm_interval(key[0], full_process_start.get(key, 0.0), full_process_end.get(key, 0.0))
    for key in set(mix_cycle_start) | set(mix_cycle_end):
        add_pm_interval(key[0], mix_cycle_start.get(key, 0.0), mix_cycle_end.get(key, 0.0))
    for key in set(clean_start) | set(clean_end):
        add_pm_interval(key[0], clean_start.get(key, 0.0), clean_end.get(key, 0.0))

    def infer_pm_for_interval(start: float, end: float) -> int:
        # First retain the old exact-match behavior for ordinary one-cycle
        # product and PEC intervals.
        for pm_id, pm_start, pm_end in pm_process_intervals:
            if abs(pm_start - start) <= 1e-6 and abs(pm_end - end) <= 1e-6:
                return pm_id
        # A reusable PEC wafer may remain in a chamber across two adjacent
        # 2x2 cycles, including the bridge gap. Its PM interval therefore does
        # not equal either individual cycle. Attribute it to the chamber whose
        # process intervals have the largest total overlap with this span.
        overlap_by_pm: Dict[int, float] = {}
        for pm_id, pm_start, pm_end in pm_process_intervals:
            overlap = max(0.0, min(end, pm_end) - max(start, pm_start))
            overlap_by_pm[pm_id] = overlap_by_pm.get(pm_id, 0.0) + overlap
        if overlap_by_pm:
            best_overlap = max(overlap_by_pm.values())
            best_pm_ids = [
                pm_id for pm_id, overlap in overlap_by_pm.items()
                if overlap > 1e-6 and abs(overlap - best_overlap) <= 1e-6
            ]
            if len(best_pm_ids) == 1:
                return best_pm_ids[0]
        return 0

    wafer_pm: Dict[int, int] = {}
    for (pm_id, _batch_id, _side_id), pair_id in full_assignment.items():
        for wafer_id in full_pair_members.get(pair_id, []):
            wafer_pm[wafer_id] = pm_id
    for (pm_id, _pos_id), pair_id in mix_pair_by_pos.items():
        for wafer_id in mix_pair_members.get(pair_id, []):
            wafer_pm[wafer_id] = pm_id

    product_ids = sorted({wafer_id for wafer_id, _ in prod_stage_start} | {wafer_id for wafer_id, _ in prod_stage_end})
    for wafer_id in product_ids:
        if wafer_id in wafer_pm:
            continue
        start = prod_stage_start.get((wafer_id, "pm"), 0.0)
        end = prod_stage_end.get((wafer_id, "pm"), 0.0)
        pm_id = infer_pm_for_interval(start, end)
        if pm_id:
            wafer_pm[wafer_id] = pm_id
            pm_ids.add(pm_id)

    pec_pm_by_job: Dict[int, int] = dict(explicit_pec_pm_by_job)
    pec_job_ids = sorted({job_id for job_id, _ in pec_stage_start} | {job_id for job_id, _ in pec_stage_end})
    for job_id in pec_job_ids:
        if job_id in pec_pm_by_job:
            continue
        start = pec_stage_start.get((job_id, "pm"), 0.0)
        end = pec_stage_end.get((job_id, "pm"), 0.0)
        pm_id = infer_pm_for_interval(start, end)
        if pm_id:
            pec_pm_by_job[job_id] = pm_id

    # Reusable tokens are chamber-bound. If an old solution has one ambiguous
    # zero-overlap job, reuse the chamber learned from another job assigned to
    # the same PEC token before falling back to an unresolved lane.
    token_pm_candidates: Dict[int, set] = {}
    for job_id, pm_id in pec_pm_by_job.items():
        token_id = pec_token_by_job.get(job_id)
        if token_id is not None:
            token_pm_candidates.setdefault(token_id, set()).add(pm_id)
    for job_id in pec_job_ids:
        if job_id in pec_pm_by_job:
            continue
        token_id = pec_token_by_job.get(job_id)
        candidates = token_pm_candidates.get(token_id, set())
        if len(candidates) == 1:
            resolved_pm_id = next(iter(candidates))
            pec_pm_by_job[job_id] = resolved_pm_id
            pm_ids.add(resolved_pm_id)

    full_pair_by_wafer = {
        wafer_id: pair_id
        for pair_id, members in full_pair_members.items()
        for wafer_id in members
    }
    mix_pair_by_wafer = {
        wafer_id: pair_id
        for pair_id, members in mix_pair_members.items()
        for wafer_id in members
    }
    full_pair_location = {
        pair_id: (pm_id, batch_id, side_id)
        for (pm_id, batch_id, side_id), pair_id in full_assignment.items()
    }
    mix_pair_location = {
        pair_id: (pm_id, pos_id)
        for (pm_id, pos_id), pair_id in mix_pair_by_pos.items()
    }
    max_mix_pos_by_pm = {
        pm_id: mix_last_pos.get(
            pm_id,
            max((pos_id for key_pm, pos_id in mix_pair_by_pos if key_pm == pm_id), default=0),
        )
        for pm_id in set(mix_last_pos) | {key_pm for key_pm, _ in mix_pair_by_pos}
    }

    vtr_task_product_members: Dict[str, List[int]] = {}

    def register_vtr_product_members(task_name: str, members: List[int]) -> None:
        if not task_name or not members:
            return
        bucket = vtr_task_product_members.setdefault(task_name, [])
        for wafer_id in members:
            if wafer_id not in bucket:
                bucket.append(wafer_id)

    for pair_id, members in full_pair_members.items():
        location = full_pair_location.get(pair_id)
        if location is None:
            continue
        pm_id, batch_id, side_id = location
        side_prefix = "front" if side_id == 1 else "back"
        register_vtr_product_members(f"full_{side_prefix}_load_{pm_id}_{batch_id}", sorted(members))
        register_vtr_product_members(f"full_{side_prefix}_unload_{pm_id}_{batch_id}", sorted(members))
    for pair_id, members in mix_pair_members.items():
        location = mix_pair_location.get(pair_id)
        if location is None:
            continue
        pm_id, pos_id = location
        max_pos = max_mix_pos_by_pm.get(pm_id, pos_id)
        load_task = f"mix_head_{pm_id}" if pos_id == 1 else f"mix_bridge_{pm_id}_{pos_id}"
        unload_task = f"mix_tail_{pm_id}" if pos_id == max_pos else f"mix_bridge_{pm_id}_{pos_id + 2}"
        register_vtr_product_members(load_task, sorted(members))
        register_vtr_product_members(unload_task, sorted(members))

    # The pure-4x1 formulation writes LL slot chains directly, so it has no
    # LL slot-assignment variables to parse. Reconstruct those two physical
    # LL lanes for visualization. ATR and VTR remain single robot lanes: their
    # capacity is payload capacity, not permission for different routes to run
    # concurrently.
    pure_full_capacity_chains = bool(full_pair_members) and not mix_pair_members
    if pure_full_capacity_chains:
        if not llupper_slot_by_wafer:
            for members in full_pair_members.values():
                for slot_id, wafer_id in enumerate(sorted(members), start=1):
                    llupper_slot_by_wafer[wafer_id] = slot_id
                    lllower_slot_by_wafer[wafer_id] = slot_id

    ordered_pm_ids = [2, 3] if pm_ids and pm_ids.issubset({2, 3}) else sorted(pm_ids)
    llupper_slots = sorted(set(llupper_slot_by_wafer.values()) | ({1, 2} if llupper_slot_by_wafer else set()))
    lllower_slots = sorted(set(lllower_slot_by_wafer.values()) | ({1, 2} if lllower_slot_by_wafer else set()))
    atr_slots = sorted({slot for slots in atr_slots_by_task.values() for slot in slots})
    vtr_slots = sorted({slot for slots in vtr_slots_by_task.values() for slot in slots})
    if atr_slots_by_task:
        atr_slots = sorted(set(atr_slots) | {1, 2})
    if vtr_slots_by_task:
        vtr_slots = sorted(set(vtr_slots) | {1, 2, 3, 4})
    atr_lanes = [f"ATR slot {slot_id}" for slot_id in atr_slots] if atr_slots else ["ATR robot"]
    vtr_lanes = [f"VTR slot {slot_id}" for slot_id in vtr_slots] if vtr_slots else ["VTR robot"]
    mandatory_resource_lanes = set(atr_lanes + vtr_lanes) if (atr_slots_by_task or vtr_slots_by_task) else set()
    lane_order: List[str] = list(atr_lanes) + ["AL"]
    lane_order.extend(f"LLupper slot {slot_id}" for slot_id in llupper_slots)
    if not llupper_slots:
        lane_order.append("LLupper")
    lane_order.extend(vtr_lanes)
    lane_order.extend(f"CH{pm_id} PM" for pm_id in ordered_pm_ids)
    if not ordered_pm_ids:
        lane_order.append("PM")
    lane_order.extend(f"LLlower slot {slot_id}" for slot_id in lllower_slots)
    if not lllower_slots:
        lane_order.append("LLlower")

    aggregated: Dict[Tuple[str, float, float, str, str], Dict[str, object]] = {}
    time_candidates: List[float] = []
    chamber_wait_intervals: List[Tuple[str, float, float, str, str, str]] = []

    def add_task(lane: str, start: float, end: float, action: str, entity: str, color: str) -> None:
        if end <= start + 1e-9:
            return
        key = (lane, round(start, 6), round(end, 6), action, color)
        item = aggregated.setdefault(
            key,
            {
                "lane": lane,
                "start": start,
                "end": end,
                "action": action,
                "color": color,
                "entities": [],
            },
        )
        item["entities"].append(entity)
        time_candidates.extend([start, end])

    def add_chamber_wait(
        lane: str,
        start: float,
        end: float,
        action: str,
        entity: str,
        color: str,
    ) -> None:
        if end > start + 1e-9:
            chamber_wait_intervals.append((lane, start, end, action, entity, color))

    def product_start(wafer_id: int, stage_name: str) -> float:
        return prod_stage_start.get((wafer_id, stage_name), 0.0)

    def product_end(wafer_id: int, stage_name: str) -> float:
        return prod_stage_end.get((wafer_id, stage_name), product_start(wafer_id, stage_name))

    def atr_load_unload_time(wafer_id: int, stage_name: str) -> float:
        vtr_time = product_end(wafer_id, "vtr_load") - product_start(wafer_id, "vtr_load")
        if vtr_time <= 1e-9:
            vtr_time = product_end(wafer_id, "vtr_unload") - product_start(wafer_id, "vtr_unload")
        stage_time = product_end(wafer_id, stage_name) - product_start(wafer_id, stage_name)
        return max(0.0, min(vtr_time, 0.5 * stage_time))

    atr_motion_actions: Dict[Tuple[float, float, str, str], List[str]] = {}

    def resource_pair_members(wafer_id: int) -> List[int]:
        full_pair = full_pair_by_wafer.get(wafer_id)
        if full_pair is not None:
            return sorted(full_pair_members.get(full_pair, []))
        mix_pair = mix_pair_by_wafer.get(wafer_id)
        if mix_pair is not None:
            return sorted(mix_pair_members.get(mix_pair, []))
        return []

    def resource_stage_is_synchronized(wafer_id: int, stage_name: str) -> bool:
        members = resource_pair_members(wafer_id)
        if len(members) != 2:
            return False
        first, second = members
        return (
            abs(product_start(first, stage_name) - product_start(second, stage_name)) <= 1e-6
            and abs(product_end(first, stage_name) - product_end(second, stage_name)) <= 1e-6
        )

    def add_atr_resource_transfer(lane, wafer_id: int, stage_name: str, source: str, destination: str, entity: str) -> None:
        start = product_start(wafer_id, stage_name)
        end = product_end(wafer_id, stage_name)
        handling_time = atr_load_unload_time(wafer_id, stage_name)
        load_end = min(end, start + handling_time)
        unload_start = max(load_end, end - handling_time)
        synchronized = resource_stage_is_synchronized(wafer_id, stage_name)
        members = resource_pair_members(wafer_id)
        first_member = members[0] if members else wafer_id
        second_member = members[-1] if members else wafer_id
        if not (synchronized and source == "AL" and wafer_id == first_member):
            load_action = "ATR single-pick at AL" if synchronized and source == "AL" else f"ATR load at {source}"
            add_task(lane, start, load_end, load_action, entity, "#4C78A8")
        add_task(lane, load_end, unload_start, f"ATR move {source}->{destination}", entity, "#72B7B2")
        if not (synchronized and destination == "AL" and wafer_id == second_member):
            unload_action = "ATR single-place at AL" if synchronized and destination == "AL" else f"ATR unload at {destination}"
            add_task(lane, unload_start, end, unload_action, entity, "#9C755F")
        key = (round(start, 6), round(end, 6), source, destination)
        atr_motion_actions.setdefault(key, []).append(entity)

    def pm_lane(pm_id: int) -> str:
        return f"CH{pm_id} PM" if pm_id else "PM"

    def ch_suffix(pm_id: int) -> str:
        return f" CH{pm_id}" if pm_id else ""

    def llupper_lane(wafer_id: int) -> str:
        slot_id = llupper_slot_by_wafer.get(wafer_id)
        return f"LLupper slot {slot_id}" if slot_id is not None else "LLupper"

    def lllower_lane(wafer_id: int) -> str:
        slot_id = lllower_slot_by_wafer.get(wafer_id)
        return f"LLlower slot {slot_id}" if slot_id is not None else "LLlower"

    def atr_lane(task_name: str) -> str:
        slots = sorted(atr_slots_by_task.get(task_name, []))
        return f"ATR slot {slots[0]}" if slots else "ATR robot"

    def vtr_lane(task_name: str, wafer_id: int) -> str:
        slots = sorted(vtr_slots_by_task.get(task_name, []))
        if not slots:
            return "VTR robot"
        members = sorted(vtr_task_product_members.get(task_name, []))
        if wafer_id in members:
            member_index = members.index(wafer_id)
        else:
            member_index = 0
        return f"VTR slot {slots[min(member_index, len(slots) - 1)]}"

    def product_mode_label(wafer_id: int) -> str:
        if wafer_id in full_pair_by_wafer:
            return "4x1"
        if wafer_id in mix_pair_by_wafer:
            return "2x2"
        return ""

    def product_vtr_task_name(wafer_id: int, stage_name: str) -> str:
        full_pair = full_pair_by_wafer.get(wafer_id)
        if full_pair is not None:
            location = full_pair_location.get(full_pair)
            if location is None:
                return ""
            pm_id, batch_id, side_id = location
            side_prefix = "front" if side_id == 1 else "back"
            transfer = "load" if stage_name == "vtr_load" else "unload"
            return f"full_{side_prefix}_{transfer}_{pm_id}_{batch_id}"

        mix_pair = mix_pair_by_wafer.get(wafer_id)
        if mix_pair is not None:
            location = mix_pair_location.get(mix_pair)
            if location is None:
                return ""
            pm_id, pos_id = location
            if stage_name == "vtr_load":
                return f"mix_head_{pm_id}" if pos_id == 1 else f"mix_bridge_{pm_id}_{pos_id}"
            max_pos = max_mix_pos_by_pm.get(pm_id, pos_id)
            return f"mix_tail_{pm_id}" if pos_id == max_pos else f"mix_bridge_{pm_id}_{pos_id + 2}"

        return ""

    def add_product_vtr_transfer(
        wafer_id: int,
        stage_name: str,
        pm_id: int,
        task_name: str,
        entity: str,
    ) -> None:
        stage_start = product_start(wafer_id, stage_name)
        stage_end = product_end(wafer_id, stage_name)
        lane = vtr_lane(task_name, wafer_id)
        chamber_name = f"CH{pm_id}" if pm_id else "CH"
        source = "LLupper" if stage_name == "vtr_load" else chamber_name
        destination = chamber_name if stage_name == "vtr_load" else "LLlower"
        operation = "load" if stage_name == "vtr_load" else "unload"
        add_task(
            lane,
            stage_start,
            stage_end,
            f"VTR pickup at {source} + loaded move {source}->{destination} + place at {destination} ({operation})",
            entity,
            "#F58518" if stage_name == "vtr_load" else "#FF9DA6",
        )

    def add_pm_resource_tasks(wafer_id: int, pm_id: int, entity: str) -> None:
        chamber_entry = product_end(wafer_id, "vtr_load")
        chamber_exit = product_start(wafer_id, "vtr_unload")
        mix_pair = mix_pair_by_wafer.get(wafer_id)
        location = mix_pair_location.get(mix_pair) if mix_pair is not None else None
        if location is not None:
            mix_pm_id, pos_id = location
            first_start = mix_cycle_start.get((mix_pm_id, pos_id), 0.0)
            first_end = mix_cycle_end.get((mix_pm_id, pos_id), 0.0)
            second_start = mix_cycle_start.get((mix_pm_id, pos_id + 1), 0.0)
            second_end = mix_cycle_end.get((mix_pm_id, pos_id + 1), 0.0)
            if first_end > first_start + 1e-9 and second_end > second_start + 1e-9:
                lane = pm_lane(mix_pm_id)
                add_chamber_wait(
                    lane,
                    chamber_entry,
                    first_start,
                    "CH wait before process",
                    entity,
                    "#F2A09A",
                )
                add_task(lane, first_start, first_end, "2x2 PM process", entity, "#E45756")
                add_task(
                    lane,
                    first_end,
                    second_start,
                    "2x2 in-chamber bridge/wait",
                    entity,
                    "#BAB0AC",
                )
                add_task(lane, second_start, second_end, "2x2 PM process", entity, "#E45756")
                add_chamber_wait(
                    lane,
                    second_end,
                    chamber_exit,
                    "CH wait for VTR unload",
                    entity,
                    "#F2A09A",
                )
                return
        mode_label = product_mode_label(wafer_id)
        action = f"{mode_label} PM process" if mode_label else "PM process"
        lane = pm_lane(pm_id)
        process_start = product_start(wafer_id, "pm")
        process_end = product_end(wafer_id, "pm")
        add_chamber_wait(
            lane,
            chamber_entry,
            process_start,
            "CH wait before process",
            entity,
            "#F2A09A",
        )
        add_task(lane, process_start, process_end, action, entity, "#E45756")
        add_chamber_wait(
            lane,
            process_end,
            chamber_exit,
            "CH wait for VTR unload",
            entity,
            "#F2A09A",
        )

    for wafer_id in product_ids:
        entity = f"W{wafer_id}"
        pm_id = wafer_pm.get(wafer_id, 0)
        add_atr_resource_transfer(atr_lane(f"lp_al_{wafer_id}"), wafer_id, "atr_lp_al", "LP", "AL", entity)
        add_task(
            "AL",
            product_start(wafer_id, "al"),
            product_end(wafer_id, "al"),
            "AL calibrate",
            entity,
            "#9C755F",
        )
        exchange_start = product_start(wafer_id, "atr_al_exchange")
        exchange_end = product_end(wafer_id, "atr_al_exchange")
        if exchange_end > exchange_start + 1e-9:
            pair_id = full_pair_by_wafer.get(wafer_id)
            members = sorted(full_pair_members.get(pair_id, [])) if pair_id is not None else []
            if not members:
                pair_id = mix_pair_by_wafer.get(wafer_id)
                members = sorted(mix_pair_members.get(pair_id, [])) if pair_id is not None else []
            exchange_entity = " -> ".join(f"W{member}" for member in members) or entity
            add_task(
                "ATR robot",
                exchange_start,
                exchange_end,
                "ATR single-wafer exchange at AL",
                exchange_entity,
                "#D37295",
            )
            add_task(
                "AL",
                exchange_start,
                exchange_end,
                "AL wafer exchange",
                exchange_entity,
                "#D37295",
        )
        add_atr_resource_transfer(atr_lane(f"al_llupper_{wafer_id}"), wafer_id, "atr_al_llupper", "AL", "LLupper", entity)
        upper_lane = llupper_lane(wafer_id)
        llupper_entry = product_end(wafer_id, "atr_al_llupper")
        upper_handling_time = atr_load_unload_time(wafer_id, "atr_al_llupper")
        add_task(
            upper_lane,
            max(product_start(wafer_id, "atr_al_llupper"), llupper_entry - upper_handling_time),
            llupper_entry,
            "LLupper atmosphere: ATR place",
            entity,
            "#4C78A8",
        )
        llupper_state_start = product_start(wafer_id, "llupper")
        llupper_state_end = product_end(wafer_id, "llupper")
        add_task(
            upper_lane,
            llupper_state_start,
            llupper_state_end,
            "LLupper pump: atmosphere->vacuum",
            entity,
            "#59A14F",
        )
        load_task_name = product_vtr_task_name(wafer_id, "vtr_load")
        unload_task_name = product_vtr_task_name(wafer_id, "vtr_unload")
        add_task(
            upper_lane,
            llupper_state_end,
            product_start(wafer_id, "vtr_load"),
            "LLupper vacuum ready/wait",
            entity,
            "#8CD17D",
        )
        add_task(
            upper_lane,
            product_start(wafer_id, "vtr_load"),
            product_end(wafer_id, "vtr_load"),
            "LLupper vacuum: VTR pickup",
            entity,
            "#F58518",
        )
        upper_transition_time = max(0.0, llupper_state_end - llupper_state_start)
        add_task(
            upper_lane,
            product_end(wafer_id, "vtr_load"),
            product_end(wafer_id, "vtr_load") + upper_transition_time,
            "LLupper vent reset: vacuum->atmosphere",
            "empty",
            "#BAB0AC",
        )
        add_product_vtr_transfer(wafer_id, "vtr_load", pm_id, load_task_name, entity)
        add_pm_resource_tasks(wafer_id, pm_id, entity)
        add_product_vtr_transfer(wafer_id, "vtr_unload", pm_id, unload_task_name, entity)
        lower_lane = lllower_lane(wafer_id)
        add_task(
            lower_lane,
            product_start(wafer_id, "vtr_unload"),
            product_end(wafer_id, "vtr_unload"),
            "LLlower vacuum: VTR place",
            entity,
            "#F58518",
        )
        lllower_state_start = product_start(wafer_id, "lllower")
        lllower_state_end = product_end(wafer_id, "lllower")
        add_task(
            lower_lane,
            lllower_state_start,
            lllower_state_end,
            "LLlower vent: vacuum->atmosphere",
            entity,
            "#B279A2",
        )
        lllower_exit_start = product_start(wafer_id, "atr_lllower_lp")
        if lllower_exit_start > lllower_state_end + 1e-9:
            add_task(
                lower_lane,
                lllower_state_end,
                lllower_exit_start,
                "LLlower atmosphere ready/wait",
                entity,
                "#D4A6C8",
            )
        lower_handling_time = atr_load_unload_time(wafer_id, "atr_lllower_lp")
        lower_pickup_end = min(
            product_end(wafer_id, "atr_lllower_lp"),
            lllower_exit_start + lower_handling_time,
        )
        add_task(
            lower_lane,
            lllower_exit_start,
            lower_pickup_end,
            "LLlower atmosphere: ATR pickup",
            entity,
            "#4C78A8",
        )
        lower_transition_time = max(0.0, lllower_state_end - lllower_state_start)
        add_task(
            lower_lane,
            lower_pickup_end,
            lower_pickup_end + lower_transition_time,
            "LLlower pump reset: atmosphere->vacuum",
            "empty",
            "#BAB0AC",
        )
        add_atr_resource_transfer(atr_lane(f"lllower_lp_{wafer_id}"), wafer_id, "atr_lllower_lp", "LLlower", "LP", entity)

    # A physical robot cannot teleport between the endpoint of one loaded move
    # and the source of the next. Reconstruct the mandatory empty relocation
    # from the solved action order so the resource Gantt exposes it explicitly.
    ordered_atr_actions = sorted(atr_motion_actions, key=lambda item: (item[0], item[1], item[2], item[3]))
    location_index = {"LP": 0, "AL": 1, "LLupper": 2, "LLlower": 2}
    if ordered_atr_actions:
        first_start, first_end, _first_source, _first_destination = ordered_atr_actions[0]
        first_entities = atr_motion_actions[ordered_atr_actions[0]]
        reference_wafer = int(first_entities[0][1:]) if first_entities and first_entities[0].startswith("W") else 0
        base_move_time = max(
            0.0,
            product_end(reference_wafer, "atr_lp_al") - product_start(reference_wafer, "atr_lp_al")
            - 2.0 * atr_load_unload_time(reference_wafer, "atr_lp_al"),
        ) if reference_wafer else 0.0
        for previous, following in zip(ordered_atr_actions, ordered_atr_actions[1:]):
            _prev_start, previous_end, _prev_source, previous_destination = previous
            following_start, _following_end, following_source, _following_destination = following
            travel_time = abs(location_index[previous_destination] - location_index[following_source]) * base_move_time
            if travel_time <= 1e-9:
                continue
            empty_end = min(following_start, previous_end + travel_time)
            add_task(
                "ATR robot",
                previous_end,
                empty_end,
                f"ATR empty {previous_destination}->{following_source}",
                "empty",
                "#BAB0AC",
            )

    def pec_entity(job_id: int) -> str:
        token_id = pec_token_by_job.get(job_id)
        return f"PEC{token_id}" if token_id is not None else f"E{job_id}"

    for job_id in pec_job_ids:
        entity = pec_entity(job_id)
        pm_id = pec_pm_by_job.get(job_id, 0)
        chamber_name = f"CH{pm_id}" if pm_id else "CH"
        pec_load_start = pec_stage_start.get((job_id, "vtr_load"), 0.0)
        pec_load_end = pec_stage_end.get((job_id, "vtr_load"), 0.0)
        add_task(
            "VTR robot",
            pec_load_start,
            pec_load_end,
            f"VTR pickup at PEC storage + loaded move PEC storage->{chamber_name} + place at {chamber_name} (load)",
            entity,
            "#F58518",
        )
        add_task(
            pm_lane(pm_id),
            pec_stage_start.get((job_id, "pm"), 0.0),
            pec_stage_end.get((job_id, "pm"), 0.0),
            "PEC chamber support",
            entity,
            "#E45756",
        )
        pec_unload_start = pec_stage_start.get((job_id, "vtr_unload"), 0.0)
        pec_unload_end = pec_stage_end.get((job_id, "vtr_unload"), 0.0)
        add_task(
            "VTR robot",
            pec_unload_start,
            pec_unload_end,
            f"VTR pickup at {chamber_name} + loaded move {chamber_name}->PEC storage + place at PEC storage (unload)",
            entity,
            "#FF9DA6",
        )

    # Several wafers can wait concurrently in different pockets of one CH.
    # Convert their overlapping residence intervals into non-overlapping
    # segments with the active wafer set, so one chamber lane stays readable.
    chamber_wait_groups: Dict[Tuple[str, str, str], List[Tuple[float, float, str]]] = {}
    for lane, start, end, action, entity, color in chamber_wait_intervals:
        chamber_wait_groups.setdefault((lane, action, color), []).append((start, end, entity))
    for (lane, action, color), intervals in chamber_wait_groups.items():
        boundaries = sorted({point for start, end, _entity in intervals for point in (start, end)})
        merged_segments: List[Tuple[float, float, Tuple[str, ...]]] = []
        for start, end in zip(boundaries, boundaries[1:]):
            if end <= start + 1e-9:
                continue
            midpoint = 0.5 * (start + end)
            entities = tuple(sorted(
                {entity for left, right, entity in intervals if left <= midpoint < right},
                key=_entity_sort_key,
            ))
            if not entities:
                continue
            if merged_segments and merged_segments[-1][2] == entities and abs(merged_segments[-1][1] - start) <= 1e-6:
                previous_start, _previous_end, previous_entities = merged_segments[-1]
                merged_segments[-1] = (previous_start, end, previous_entities)
            else:
                merged_segments.append((start, end, entities))
        for start, end, entities in merged_segments:
            for entity in entities:
                add_task(lane, start, end, action, entity, color)

    # A 2x2 bridge (and a product+PEC side) is one VTR motion that can unload
    # and load different wafers in the same interval.  Collapse those exact
    # overlaps into one bar instead of painting several bars over each other.
    vtr_items_by_interval: Dict[Tuple[str, float, float], List[Tuple[Tuple[str, float, float, str, str], Dict[str, object]]]] = {}
    for key, item in list(aggregated.items()):
        lane = str(item["lane"])
        if lane.startswith("VTR"):
            interval_key = (lane, round(float(item["start"]), 6), round(float(item["end"]), 6))
            vtr_items_by_interval.setdefault(interval_key, []).append((key, item))
    for (lane, _rounded_start, _rounded_end), grouped_items in vtr_items_by_interval.items():
        if len(grouped_items) <= 1:
            continue
        actions = sorted({str(item["action"]) for _key, item in grouped_items})
        if any("wait" in action.lower() for action in actions):
            continue
        entities = sorted(
            {entity for _key, item in grouped_items for entity in item["entities"]},
            key=_entity_sort_key,
        )
        joined_actions = " / ".join(actions)
        chambers = sorted(set(re.findall(r"CH\d+", joined_actions)))
        has_load = any("(load)" in action or "+ load" in action for action in actions)
        has_unload = any("(unload)" in action or "+ unload" in action for action in actions)
        if len(chambers) == 1 and has_load and has_unload:
            combined_action = (
                f"VTR bridge LLupper->{chambers[0]}->LLlower "
                "(place incoming + pick outgoing)"
            )
        elif len(chambers) == 1 and has_load:
            combined_action = f"VTR pickup + loaded move LLupper->{chambers[0]} + place (load)"
        elif len(chambers) == 1 and has_unload:
            combined_action = f"VTR pickup + loaded move {chambers[0]}->LLlower + place (unload)"
        else:
            combined_action = "VTR combined transfer"
        start = min(float(item["start"]) for _key, item in grouped_items)
        end = max(float(item["end"]) for _key, item in grouped_items)
        for key, _item in grouped_items:
            aggregated.pop(key, None)
        aggregated[(lane, round(start, 6), round(end, 6), combined_action, "#76B7B2")] = {
            "lane": lane,
            "start": start,
            "end": end,
            "action": combined_action,
            "color": "#76B7B2",
            "entities": entities,
        }

    # Show only mandatory empty relocation between loaded VTR actions. Any
    # remaining gap is true robot idle time and intentionally stays blank.
    def vtr_action_endpoints(action: str) -> Tuple[str, str] | None:
        if action.startswith("VTR bridge LLupper->"):
            return "LLupper", "LLlower"
        route = re.search(
            r"(LLupper|LLlower|PEC storage|CH\d+)->(LLupper|LLlower|PEC storage|CH\d+)",
            action,
        )
        if route:
            return route.group(1), route.group(2)
        return None

    loaded_vtr_items = sorted(
        (
            item
            for item in list(aggregated.values())
            if item["lane"] == "VTR robot"
            and str(item["action"]).startswith("VTR")
            and "empty move" not in str(item["action"])
        ),
        key=lambda item: (float(item["start"]), float(item["end"])),
    )
    loaded_durations = [
        float(item["end"]) - float(item["start"])
        for item in loaded_vtr_items
        if float(item["end"]) > float(item["start"]) + 1e-9
    ]
    empty_move_time = min(loaded_durations) if loaded_durations else 0.0
    for previous, following in zip(loaded_vtr_items, loaded_vtr_items[1:]):
        previous_endpoints = vtr_action_endpoints(str(previous["action"]))
        following_endpoints = vtr_action_endpoints(str(following["action"]))
        if previous_endpoints is None or following_endpoints is None:
            continue
        previous_destination = previous_endpoints[1]
        following_source = following_endpoints[0]
        previous_end = float(previous["end"])
        following_start = float(following["start"])
        available_gap = following_start - previous_end
        if previous_destination == following_source or available_gap <= 1e-9:
            continue
        relocation_end = previous_end + min(empty_move_time, available_gap)
        add_task(
            "VTR robot",
            previous_end,
            relocation_end,
            f"VTR empty move {previous_destination}->{following_source}",
            "empty",
            "#BAB0AC",
        )

    tasks: List[Dict[str, object]] = []
    for item in aggregated.values():
        unique_entities = sorted(set(item["entities"]), key=_entity_sort_key)
        entities = _format_entity_list(unique_entities)
        action = str(item["action"])
        product_count = sum(1 for entity in unique_entities if str(entity).startswith("W"))
        if product_count == 2:
            if action.startswith("ATR load at "):
                action = action.replace("ATR load at ", "ATR double-pick at ", 1)
            elif action.startswith("ATR move "):
                action = action.replace("ATR move ", "ATR dual-carry ", 1)
            elif action.startswith("ATR unload at "):
                action = action.replace("ATR unload at ", "ATR double-place at ", 1)
            elif action.startswith("VTR load"):
                action = action.replace("VTR load", "VTR double load", 1)
            elif action.startswith("VTR unload"):
                action = action.replace("VTR unload", "VTR double unload", 1)
        label = f"{action}\n{entities}" if entities else action
        tasks.append(
            {
                "lane": item["lane"],
                "start": item["start"],
                "end": item["end"],
                "label": label,
                "short_label": entities or action,
                "color": item["color"],
            }
        )

    if not tasks:
        return {}

    active_lanes = {str(task["lane"]) for task in tasks}
    lanes = [lane for lane in lane_order if lane in active_lanes or lane in mandatory_resource_lanes]
    lanes.extend(sorted(active_lanes - set(lanes)))
    lane_rank = {lane: idx for idx, lane in enumerate(lanes)}
    horizon = max(time_candidates) if time_candidates else 0.0
    return {
        "is_petri": True,
        "layout": "resources",
        "title_suffix": "Resource Gantt",
        "lanes": lanes,
        "tasks": sorted(tasks, key=lambda task: (lane_rank.get(task["lane"], 10**6), float(task["start"]), float(task["end"]))),
        "markers": [],
        "horizon": max(horizon, 1.0),
        "c_max": _float(solution.get("c_max", 0.0)),
    }


def _extract_wafer_completion_times(solution: Dict[str, float]) -> Dict[int, float]:
    wafer_completion: Dict[int, float] = {}
    for name, value in solution.items():
        m = NEW_WAFER_COMPLETION_RE.match(name)
        if m:
            completion = _float(value)
            if completion > 0.0:
                wafer_completion[int(m.group(1))] = completion

    if wafer_completion:
        return wafer_completion

    for name, value in solution.items():
        m = PROD_STAGE_END_RE.match(name)
        if m and m.group(2) == "atr_lllower_lp":
            completion = _float(value)
            if completion > 0.0:
                wafer_completion[int(m.group(1))] = completion
    return wafer_completion


def _attach_wph_stats(solution: Dict[str, float], schedule: Dict[str, object]) -> None:
    wafer_completion = _extract_wafer_completion_times(solution)
    if not wafer_completion:
        return

    last_completion = max(wafer_completion.values())
    c_max = _float(schedule.get("c_max", solution.get("c_max", 0.0)))
    processing_time = max(c_max, last_completion)
    if processing_time <= 0.0:
        return

    completed_wafers = len(wafer_completion)
    schedule["wph_stats"] = {
        "completed_wafers": completed_wafers,
        "processing_time": processing_time,
        "wph": completed_wafers * SECONDS_PER_HOUR / processing_time,
    }


def _collect_schedule(solution: Dict[str, float], view: str = "full") -> Dict[str, object]:
    if view == "resources":
        schedule = _collect_resource_schedule(solution)
        if schedule:
            _attach_wph_stats(solution, schedule)
        return schedule
    if view == "chambers":
        schedule = _collect_chamber_schedule(solution)
        if schedule:
            _attach_wph_stats(solution, schedule)
        return schedule
    new_schedule = _collect_path_schedule(solution)
    if new_schedule:
        _attach_wph_stats(solution, new_schedule)
        return new_schedule
    legacy_schedule = _collect_legacy_schedule(solution)
    if legacy_schedule:
        _attach_wph_stats(solution, legacy_schedule)
    return legacy_schedule


def _render_multiline_text(
    text_class: str,
    parts: List[str],
    x: float,
    y: float,
    line_height: float = 14.0,
    text_anchor: str = "start",
) -> str:
    if not parts:
        return ""
    anchor_attr = "" if text_anchor == "start" else f' text-anchor="{text_anchor}"'
    tspan = []
    for idx, line in enumerate(parts):
        dy = 0 if idx == 0 else line_height
        tspan.append(f'<tspan x="{x:.2f}" dy="{dy}">{_escape(line)}</tspan>')
    return f'<text class="{text_class}" x="{x:.2f}" y="{y:.2f}"{anchor_attr}>' + "".join(tspan) + "</text>"


def _render_clipped_task_label(parts: List[str], x: float, bar_y: float, width: float, clip_id: str) -> str:
    if not parts:
        return ""
    clip_x = x + 2.0
    clip_y = bar_y + 1.0
    clip_width = max(width - 4.0, 1.0)
    clip_height = BAR_HEIGHT - 2.0
    text_y = bar_y + 12.5
    tspan = []
    anchor_x = x + min(8.0, max(width - 8.0, 4.0))
    for idx, line in enumerate(parts):
        dy = 0 if idx == 0 else 12
        tspan.append(f'<tspan x="{anchor_x:.2f}" dy="{dy}">{_escape(line)}</tspan>')
    return (
        f'<clipPath id="{clip_id}">'
        f'<rect x="{clip_x:.2f}" y="{clip_y:.2f}" width="{clip_width:.2f}" height="{clip_height:.2f}"/>'
        f'</clipPath>'
        f'<text class="bartext" x="{anchor_x:.2f}" y="{text_y:.2f}" clip-path="url(#{clip_id})">'
        + "".join(tspan)
        + "</text>"
    )


def _render_external_task_label(text: str, x: float, bar_y: float, width: float) -> str:
    label = " ".join(str(text).split())
    if not label:
        return ""
    line = _wrap_text(label, 26, max_lines=1)
    if not line:
        return ""
    text_x = x + width + 5.0
    anchor = "start"
    if text_x > SVG_WIDTH - RIGHT_MARGIN - 90:
        text_x = x - 5.0
        anchor = "end"
    return (
        f'<text class="bartext-outside" x="{text_x:.2f}" y="{bar_y + 13.5:.2f}" '
        f'text-anchor="{anchor}">{_escape(line[0])}</text>'
    )


def _estimate_text_width(lines: List[str]) -> float:
    if not lines:
        return 0.0
    return max(len(line) for line in lines) * 6.4 + 8.0


def _render_floating_task_label(
    lines: List[str],
    text_class: str,
    x: float,
    y: float,
    text_anchor: str = "start",
) -> str:
    if not lines:
        return ""
    anchor_attr = "" if text_anchor == "start" else f' text-anchor="{text_anchor}"'
    tspan = []
    for idx, line in enumerate(lines):
        dy = 0 if idx == 0 else 12
        tspan.append(f'<tspan x="{x:.2f}" dy="{dy}">{_escape(line)}</tspan>')
    return f'<text class="{text_class}" x="{x:.2f}" y="{y:.2f}"{anchor_attr}>' + "".join(tspan) + "</text>"


def _format_meta_value(value) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float):
        if not math.isfinite(value):
            return "n/a"
        return f"{value:.3f}"
    return str(value)


def _format_time_value(value) -> str:
    try:
        numeric = float(value)
    except Exception:
        return "n/a"
    if not math.isfinite(numeric):
        return "n/a"
    return f"{numeric:.3f}"


def _task_tooltip_text(task: Dict[str, object], lane_name: str) -> str:
    full_label = str(task.get("label", "")).strip()
    short_label = str(task.get("short_label", "")).strip()
    label = full_label or short_label or lane_name
    start = _float(task.get("start", 0.0))
    end = _float(task.get("end", 0.0))
    lines = [line for line in label.splitlines() if line.strip()]
    lines.extend(
        [
            f"lane: {lane_name}",
            f"start: {_format_time_value(start)}",
            f"end: {_format_time_value(end)}",
            f"duration: {_format_time_value(end - start)}",
        ]
    )
    return "\n".join(lines)


def _svg_tooltip_markup() -> List[str]:
    return [
        '<g id="gantt-tooltip" visibility="hidden" pointer-events="none">',
        '<rect id="gantt-tooltip-bg" x="0" y="0" width="180" height="42" rx="6" ry="6" fill="#ffffff" stroke="#25313C" stroke-width="1.2" opacity="0.96"/>',
        '<text id="gantt-tooltip-text" class="tooltip-text" x="10" y="18"></text>',
        "</g>",
        '<script type="application/ecmascript"><![CDATA[',
        "(function () {",
        "  var svg = document.documentElement;",
        "  var tooltip = document.getElementById('gantt-tooltip');",
        "  var bg = document.getElementById('gantt-tooltip-bg');",
        "  var text = document.getElementById('gantt-tooltip-text');",
        "  if (!tooltip || !bg || !text || !svg.createSVGPoint) { return; }",
        "  var maxChars = 58;",
        "  function wrapLine(line) {",
        "    line = String(line || '').trim();",
        "    if (!line) { return ['']; }",
        "    var words = line.split(/\\s+/);",
        "    var lines = [];",
        "    var current = '';",
        "    for (var i = 0; i < words.length; i += 1) {",
        "      var word = words[i];",
        "      var next = current ? current + ' ' + word : word;",
        "      if (next.length > maxChars && current) {",
        "        lines.push(current);",
        "        current = word;",
        "      } else {",
        "        current = next;",
        "      }",
        "    }",
        "    if (current) { lines.push(current); }",
        "    return lines.length ? lines : [line];",
        "  }",
        "  function setTooltip(label) {",
        "    while (text.firstChild) { text.removeChild(text.firstChild); }",
        "    var rawLines = String(label || '').split(/\\n/);",
        "    var lines = [];",
        "    for (var i = 0; i < rawLines.length; i += 1) {",
        "      var wrapped = wrapLine(rawLines[i]);",
        "      for (var j = 0; j < wrapped.length; j += 1) { lines.push(wrapped[j]); }",
        "    }",
        "    var widest = 0;",
        "    for (var k = 0; k < lines.length; k += 1) {",
        "      widest = Math.max(widest, lines[k].length);",
        "      var tspan = document.createElementNS('http://www.w3.org/2000/svg', 'tspan');",
        "      tspan.setAttribute('x', '10');",
        "      tspan.setAttribute('dy', k === 0 ? '0' : '16');",
        "      tspan.textContent = lines[k];",
        "      text.appendChild(tspan);",
        "    }",
        "    bg.setAttribute('width', String(Math.max(170, widest * 7.2 + 22)));",
        "    bg.setAttribute('height', String(Math.max(36, lines.length * 16 + 14)));",
        "  }",
        "  function eventPoint(evt) {",
        "    var point = svg.createSVGPoint();",
        "    point.x = evt.clientX;",
        "    point.y = evt.clientY;",
        "    return point.matrixTransform(svg.getScreenCTM().inverse());",
        "  }",
        "  function move(evt) {",
        "    var p = eventPoint(evt);",
        "    var width = parseFloat(bg.getAttribute('width')) || 180;",
        "    var height = parseFloat(bg.getAttribute('height')) || 42;",
        "    var vb = svg.viewBox.baseVal;",
        "    var x = p.x + 14;",
        "    var y = p.y + 14;",
        "    if (x + width > vb.x + vb.width - 10) { x = p.x - width - 14; }",
        "    if (y + height > vb.y + vb.height - 10) { y = p.y - height - 14; }",
        "    tooltip.setAttribute('transform', 'translate(' + Math.max(8, x) + ',' + Math.max(8, y) + ')');",
        "  }",
        "  function show(evt) {",
        "    var label = this.getAttribute('data-tooltip') || '';",
        "    if (!label) { return; }",
        "    setTooltip(label);",
        "    tooltip.setAttribute('visibility', 'visible');",
        "    move(evt);",
        "  }",
        "  function hide() { tooltip.setAttribute('visibility', 'hidden'); }",
        "  var tasks = svg.querySelectorAll('.task[data-tooltip]');",
        "  for (var i = 0; i < tasks.length; i += 1) {",
        "    tasks[i].addEventListener('mouseenter', show);",
        "    tasks[i].addEventListener('mousemove', move);",
        "    tasks[i].addEventListener('mouseleave', hide);",
        "  }",
        "}());",
        "]]></script>",
    ]


def _render_svg(record: Dict[str, object], schedule: Dict[str, object], output_file: Path) -> None:
    lanes = schedule["lanes"]
    horizon = float(schedule["horizon"])
    c_max = float(schedule["c_max"])
    title_suffix = str(schedule.get("title_suffix", "Scheduling Gantt"))
    wph_stats = schedule.get("wph_stats")
    show_static_labels = bool(schedule.get("show_static_labels", False))

    label_rows: Dict[str, List[List[Tuple[float, float]]]] = {}
    label_bottom_by_lane: Dict[str, float] = {}
    task_draws: List[Dict[str, object]] = []
    task_labels: List[Dict[str, object]] = []

    def _make_label(task: Dict[str, object], x: float, width: float) -> Dict[str, object]:
        full_label = str(task.get("label", "")).strip()
        short_label = str(task.get("short_label", "")).strip()
        if not full_label and not short_label:
            return {}
        max_label_lines = int(task.get("max_label_lines", 2))
        if width >= 84.0 and full_label:
            lines = _wrap_text(full_label, max(8, int(width / 7.4)), max_lines=max_label_lines)
            text_width = _estimate_text_width(lines)
            label_left = x + 3.0
            label_right = x + max(width, text_width)
            return {
                "lines": lines,
                "text_class": "bartext",
                "x": x + 7.0,
                "anchor": "start",
                "left": label_left,
                "right": label_right,
                "height": 10.0 + 12.0 * max(0, len(lines) - 1),
            }

        label = " ".join((full_label or short_label).split())
        lines = _wrap_text(label, 30, max_lines=1)
        text_width = _estimate_text_width(lines)
        text_x = x + width + 5.0
        anchor = "start"
        label_left = text_x
        label_right = text_x + text_width
        if label_right > SVG_WIDTH - RIGHT_MARGIN + 4.0:
            text_x = x - 5.0
            anchor = "end"
            label_left = text_x - text_width
            label_right = text_x
        return {
            "lines": lines,
            "text_class": "bartext-outside",
            "x": text_x,
            "anchor": anchor,
            "left": label_left,
            "right": label_right,
            "height": 10.0,
        }

    def _assign_label_row(lane: str, label_spec: Dict[str, object]) -> int:
        left = float(label_spec["left"])
        right = float(label_spec["right"])
        rows = label_rows.setdefault(lane, [])
        row_idx = 0
        while True:
            if row_idx == len(rows):
                rows.append([])
            overlaps = any(
                left < existing_right + LABEL_ROW_GAP and right > existing_left - LABEL_ROW_GAP
                for existing_left, existing_right in rows[row_idx]
            )
            if not overlaps:
                rows[row_idx].append((left, right))
                return row_idx
            row_idx += 1

    for task_idx, task in enumerate(schedule["tasks"]):
        lane_name = str(task["lane"])
        x = _time_to_x(float(task["start"]), horizon)
        width = max(_time_to_x(float(task["end"]), horizon) - x, 2.0)
        draw = {"task": task, "lane": lane_name, "x": x, "width": width}
        task_draws.append(draw)
        if show_static_labels:
            label_spec = _make_label(task, x, width)
            if label_spec:
                row_idx = _assign_label_row(lane_name, label_spec)
                label_spec["row"] = row_idx
                label_spec["lane"] = lane_name
                label_spec["task_idx"] = task_idx
                task_labels.append(label_spec)
                label_bottom = 13.5 + row_idx * LABEL_ROW_HEIGHT + float(label_spec["height"]) + 6.0
                label_bottom_by_lane[lane_name] = max(label_bottom_by_lane.get(lane_name, 0.0), label_bottom)

    lane_heights: Dict[str, float] = {}
    for lane_name in lanes:
        lane_heights[lane_name] = max(float(LANE_HEIGHT), BAR_HEIGHT + 18.0, label_bottom_by_lane.get(lane_name, 0.0) + 12.0)

    lane_tops: Dict[str, float] = {}
    cursor_y = float(TOP_MARGIN)
    for lane_name in lanes:
        lane_tops[lane_name] = cursor_y
        cursor_y += lane_heights[lane_name]
    plot_bottom = cursor_y
    height = int(math.ceil(plot_bottom + BOTTOM_MARGIN))

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{SVG_WIDTH}" height="{height}" viewBox="0 0 {SVG_WIDTH} {height}">',
        '<style>'
        'text { font-family: "Segoe UI", "Microsoft YaHei", sans-serif; fill: #222; }'
        '.title { font-size: 24px; font-weight: 700; }'
        '.subtitle { font-size: 14px; fill: #555; }'
        '.lane { font-size: 13px; font-weight: 600; }'
        '.tick { font-size: 11px; fill: #666; }'
        '.bartext { font-size: 11px; fill: #fff; font-weight: 600; paint-order: stroke; stroke: #1f1f1f; stroke-width: 2px; stroke-linejoin: round; }'
        '.bartext-outside { font-size: 10px; fill: #222; font-weight: 600; paint-order: stroke; stroke: #fff; stroke-width: 3px; stroke-linejoin: round; }'
        '.task rect { cursor: pointer; }'
        '.task:hover rect { fill-opacity: 1; stroke: #111827; stroke-width: 2.4px; }'
        '.marker { font-size: 11px; fill: #333; }'
        '.wph { font-size: 14px; fill: #222; font-weight: 600; }'
        '.wph-detail { font-size: 13px; fill: #555; }'
        '.tooltip-text { font-size: 12px; fill: #111827; font-weight: 600; }'
        '</style>',
        f'<rect x="0" y="0" width="{SVG_WIDTH}" height="{height}" fill="#ffffff"/>',
        f'<text class="title" x="{LEFT_MARGIN}" y="38">{_escape(Path(str(record.get("instance", "instance"))).stem)} {_escape(title_suffix)}</text>',
        f'<text class="subtitle" x="{LEFT_MARGIN}" y="66">method={_escape(record.get("method", "single_result"))} | status={_escape(record.get("status", "unknown"))} | best_obj={_escape(_format_meta_value(record.get("best_obj")))}</text>',
        f'<text class="subtitle" x="{LEFT_MARGIN}" y="88">c_max={c_max:.3f} | horizon={horizon:.3f} | view={_escape(schedule.get("layout", "full"))}</text>',
    ]

    tick_count = min(max(int(math.ceil(horizon / 20.0)), 5), 12)
    for i in range(tick_count + 1):
        t = horizon * i / tick_count
        x = _time_to_x(t, horizon)
        parts.append(
            f'<line x1="{x:.2f}" y1="{TOP_MARGIN - 8}" x2="{x:.2f}" y2="{plot_bottom + 8}" stroke="#efefef" stroke-width="1"/>'
        )
        parts.append(f'<text class="tick" x="{x - 12:.2f}" y="{plot_bottom + 34}">{t:.1f}</text>')

    for lane_name in lanes:
        y = lane_tops[lane_name]
        parts.append(
            f'<line x1="{LEFT_MARGIN}" y1="{y + lane_heights[lane_name] - 10.0:.2f}" x2="{SVG_WIDTH - RIGHT_MARGIN}" y2="{y + lane_heights[lane_name] - 10.0:.2f}" stroke="#dddddd" stroke-width="1"/>'
        )
        lane_lines = _wrap_text(lane_name, max(18, int((LEFT_MARGIN - 42) / 8.6)), max_lines=2)
        parts.append(_render_multiline_text("lane", lane_lines, 18, y + 16, line_height=16))

    for draw in task_draws:
        task = draw["task"]
        y = lane_tops[str(draw["lane"])]
        x = float(draw["x"])
        width = float(draw["width"])
        full_label = str(task.get("label", "")).strip()
        short_label = str(task.get("short_label", "")).strip()
        hover_label = full_label or short_label or str(task["lane"])
        tooltip_label = _task_tooltip_text(task, str(draw["lane"]))
        fill_color = _escape_attr(str(task.get("color", "#999999")))
        parts.append(
            f'<g class="task" data-tooltip="{_escape_attr(tooltip_label)}"><title>{_escape(hover_label)}</title><rect x="{x:.2f}" y="{y:.2f}" width="{width:.2f}" height="{BAR_HEIGHT}" rx="4" ry="4" fill="{fill_color}" fill-opacity="0.88" stroke="#2f2f2f" stroke-width="0.7"/></g>'
        )

    for marker in schedule["markers"]:
        lane_name = marker["lane"]
        if lane_name not in lane_tops:
            continue
        marker_center_y = lane_tops[lane_name] + BAR_HEIGHT / 2
        x = _time_to_x(float(marker["time"]), horizon)
        points = [
            (x, marker_center_y - 8),
            (x + 8, marker_center_y),
            (x, marker_center_y + 8),
            (x - 8, marker_center_y),
        ]
        point_str = " ".join(f"{px:.2f},{py:.2f}" for px, py in points)
        marker_anchor = "start"
        marker_x = x + 10.0
        if x > SVG_WIDTH - RIGHT_MARGIN - 80:
            marker_anchor = "end"
            marker_x = x - 10.0
        parts.append(f'<polygon points="{point_str}" fill="#E45756" stroke="#7A1F1E" stroke-width="0.8"/>')
        parts.append(
            f'<text class="marker" x="{marker_x:.2f}" y="{marker_center_y + 4:.2f}" text-anchor="{marker_anchor}">{_escape(marker["label"])}</text>'
        )

    if c_max > 0.0 and schedule.get("show_cmax", True):
        x = _time_to_x(c_max, horizon)
        cmax_anchor = "start"
        cmax_x = x + 8.0
        if x > SVG_WIDTH - RIGHT_MARGIN - 110:
            cmax_anchor = "end"
            cmax_x = x - 8.0
        parts.append(
            f'<line x1="{x:.2f}" y1="{TOP_MARGIN - 18}" x2="{x:.2f}" y2="{plot_bottom}" stroke="#C00000" stroke-width="2.2" stroke-dasharray="8 4"/>'
        )
        parts.append(
            f'<text class="lane" x="{cmax_x:.2f}" y="{TOP_MARGIN - 24}" text-anchor="{cmax_anchor}">c_max={c_max:.1f}</text>'
        )

    for label in task_labels:
        lane_name = str(label["lane"])
        y = lane_tops[lane_name] + 13.5 + int(label["row"]) * LABEL_ROW_HEIGHT
        parts.append(
            _render_floating_task_label(
                label["lines"],
                str(label["text_class"]),
                float(label["x"]),
                y,
                str(label["anchor"]),
            )
        )

    if isinstance(wph_stats, dict):
        completed_wafers = int(wph_stats.get("completed_wafers", 0))
        processing_time = float(wph_stats.get("processing_time", 0.0))
        wph = float(wph_stats.get("wph", 0.0))
        processing_hours = processing_time / SECONDS_PER_HOUR
        row_y = plot_bottom + 68
        parts.append(
            f'<line x1="{LEFT_MARGIN}" y1="{plot_bottom + 50}" x2="{SVG_WIDTH - RIGHT_MARGIN}" y2="{plot_bottom + 50}" stroke="#dddddd" stroke-width="1"/>'
        )
        parts.append(f'<text class="wph" x="18" y="{row_y:.2f}">WPH</text>')
        parts.append(
            f'<text class="wph-detail" x="{LEFT_MARGIN}" y="{row_y:.2f}">'
            f'WPH={wph:.3f} wafers/hour | completed={completed_wafers} | processing_time={processing_time:.1f}s ({processing_hours:.3f}h)'
            "</text>"
        )

    parts.extend(_svg_tooltip_markup())
    parts.append("</svg>")
    output_file.write_text("\n".join(parts), encoding="utf-8")


def _normalize_records(payload) -> List[Dict[str, object]]:
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        if "solution" in payload:
            return [payload]
        records = payload.get("results", [])
        if isinstance(records, list):
            return records
        if isinstance(records, dict):
            flat_records = []
            for method_name, method_records in records.items():
                if not isinstance(method_records, list):
                    continue
                for record in method_records:
                    if isinstance(record, dict) and "method" not in record:
                        record = {**record, "method": method_name}
                    flat_records.append(record)
            return flat_records
    return []


def _looks_like_runtime_config(payload) -> bool:
    return isinstance(payload, dict) and {"experiment", "env", "algorithm"}.issubset(payload.keys())


def _summarize_status(records: List[Dict[str, object]]) -> str:
    status_counts: Dict[str, int] = {}
    for record in records:
        status = str(record.get("status", "unknown") or "unknown")
        status_counts[status] = status_counts.get(status, 0) + 1
    if not status_counts:
        return "none"
    ordered = sorted(status_counts.items(), key=lambda item: item[0])
    return ", ".join(f"{status}={count}" for status, count in ordered)


def _diagnose_solution_payload(payload, records: List[Dict[str, object]]) -> List[str]:
    if not records:
        if _looks_like_runtime_config(payload):
            return [
                "The provided JSON looks like a runtime/config file, not a solver result file.",
                "Please pass a *_solutions_*.json file generated by testing/inference instead.",
            ]
        return [
            "The provided JSON does not contain any solution records.",
            "Expected one of: a record with a 'solution' field, a list of such records, or a 'results' container.",
        ]

    non_empty_solutions = [record for record in records if record.get("solution", {})]
    if not non_empty_solutions:
        return [
            f"Found {len(records)} record(s), but all of them have empty solution dictionaries.",
            f"Status summary: {_summarize_status(records)}.",
            "A Gantt chart can only be generated when a record contains a non-empty feasible solution.",
        ]

    return [
        f"Found {len(records)} record(s), including {len(non_empty_solutions)} with non-empty solutions.",
        "However, none of the solutions matched the scheduling variable patterns expected by petri_gantt.py.",
        "Please verify that the solution JSON comes from the Petri/MIP pipeline supported by this script.",
    ]


def _load_solution_payload(solution_json: str):
    if is_latest_keyword(solution_json):
        solution_path = latest_matching_file(
            "petri_transfer_use_hrl_Trueheuristics_cutsel",
            "*solutions*.json",
            "solution JSON",
        )
    else:
        solution_path = resolve_path(solution_json)
    with solution_path.open("r", encoding="utf-8") as f:
        payload = json.load(f)
    records = _normalize_records(payload)
    return solution_path, payload, records


def _views_to_generate(view: str) -> List[str]:
    if view == "all":
        return ["full", "chambers", "resources"]
    return [view]


def _gantt_output_name(file_stem: str, view: str) -> str:
    if view == "chambers":
        return f"{file_stem}_chambers_gantt.svg"
    if view == "resources":
        return f"{file_stem}_resources_gantt.svg"
    return f"{file_stem}_gantt.svg"


VIEW_DISPLAY_NAMES = {
    "full": "Full process",
    "chambers": "Chamber modules",
    "resources": "Resources",
}


def _html_relpath(target_path: Path, base_dir: Path) -> str:
    try:
        return os.path.relpath(str(target_path), str(base_dir)).replace("\\", "/")
    except Exception:
        return str(target_path).replace("\\", "/")


def _json_script_payload(payload) -> str:
    return json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")


def _safe_file_part(text: str) -> str:
    cleaned = re.sub(r"[^0-9A-Za-z_-]+", "_", str(text).strip()).strip("_")
    return cleaned or "result"


def _unique_file_stem(base_stem: str, seen_counts: Dict[str, int]) -> str:
    count = seen_counts.get(base_stem, 0)
    seen_counts[base_stem] = count + 1
    if count == 0:
        return base_stem
    return f"{base_stem}_{count + 1}"


def _chart_entry(
    record: Dict[str, object],
    schedule: Dict[str, object],
    view_name: str,
    output_file: Path,
    out_dir: Path,
) -> Dict[str, str]:
    method_name = str(record.get("method", "") or "single_result")
    instance_name = str(record.get("instance", "instance") or "instance")
    wph_stats = schedule.get("wph_stats") if isinstance(schedule.get("wph_stats"), dict) else {}
    wph = _format_meta_value(wph_stats.get("wph")) if isinstance(wph_stats, dict) else "n/a"
    return {
        "path": _html_relpath(output_file, out_dir),
        "view": view_name,
        "view_label": VIEW_DISPLAY_NAMES.get(view_name, view_name),
        "method": method_name,
        "instance": instance_name,
        "status": str(record.get("status", "unknown") or "unknown"),
        "best_obj": _format_meta_value(record.get("best_obj")),
        "solving_time": _format_meta_value(record.get("solving_time")),
        "c_max": _format_meta_value(schedule.get("c_max")),
        "horizon": _format_meta_value(schedule.get("horizon")),
        "wph": wph,
        "title": f"{Path(instance_name).stem} / {method_name} / {VIEW_DISPLAY_NAMES.get(view_name, view_name)}",
    }


def _write_interactive_gantt_frontend(
    out_dir: Path,
    chart_entries: List[Dict[str, str]],
    comparison_svg: str = "",
) -> List[str]:
    comparison_rel = ""
    if comparison_svg:
        comparison_path = resolve_path(comparison_svg)
        comparison_rel = _html_relpath(comparison_path, out_dir)

    manifest = {
        "charts": chart_entries,
        "comparison_svg": comparison_rel,
    }
    manifest_path = out_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    chart_json = _json_script_payload(chart_entries)
    view_label_json = _json_script_payload(VIEW_DISPLAY_NAMES)
    comparison_json = _json_script_payload(comparison_rel)

    index_html = out_dir / "index.html"
    index_html.write_text(
        "\n".join(
            [
                "<!doctype html>",
                '<html lang="en">',
                "<head>",
                '<meta charset="utf-8">',
                '<meta name="viewport" content="width=device-width, initial-scale=1">',
                "<title>Petri Gantt Explorer</title>",
                "<style>",
                ":root { color-scheme: light; --ink: #17212b; --muted: #687385; --line: #d7dde5; --paper: #ffffff; --wash: #f5f7f4; --accent: #236b5c; --accent-2: #bf6f24; }",
                "* { box-sizing: border-box; }",
                "body { margin: 0; font-family: Segoe UI, Microsoft YaHei, Arial, sans-serif; color: var(--ink); background: var(--wash); }",
                ".shell { min-height: 100vh; display: flex; flex-direction: column; }",
                ".topbar { display: flex; align-items: center; justify-content: space-between; gap: 16px; padding: 18px 24px; background: #ffffff; border-bottom: 1px solid var(--line); }",
                ".topbar h1 { margin: 0; font-size: 22px; line-height: 1.2; letter-spacing: 0; }",
                ".badge { color: #ffffff; background: var(--accent); border-radius: 8px; padding: 6px 10px; font-size: 12px; font-weight: 700; white-space: nowrap; }",
                ".toolbar { display: grid; grid-template-columns: repeat(3, minmax(180px, 1fr)) auto; gap: 12px; align-items: end; padding: 14px 24px; background: #fbfcfd; border-bottom: 1px solid var(--line); }",
                ".control { display: grid; gap: 6px; }",
                ".control span { font-size: 12px; font-weight: 700; color: var(--muted); text-transform: uppercase; letter-spacing: 0; }",
                "select, .button { height: 38px; border: 1px solid #b9c2ce; border-radius: 8px; background: #ffffff; color: var(--ink); font: inherit; }",
                "select { width: 100%; padding: 0 34px 0 10px; }",
                ".button { display: inline-flex; align-items: center; justify-content: center; padding: 0 14px; text-decoration: none; font-weight: 700; color: #ffffff; background: var(--accent-2); border-color: var(--accent-2); white-space: nowrap; }",
                "main { display: grid; gap: 18px; padding: 18px 24px 28px; }",
                ".section { background: var(--paper); border: 1px solid var(--line); border-radius: 8px; overflow: hidden; }",
                ".section-head { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 14px 16px; border-bottom: 1px solid var(--line); }",
                ".section h2 { margin: 0; font-size: 16px; line-height: 1.3; letter-spacing: 0; }",
                ".zoom-controls { display: inline-flex; align-items: center; gap: 6px; }",
                ".zoom-button { min-width: 34px; height: 32px; border: 1px solid #b9c2ce; border-radius: 7px; background: #fff; color: var(--ink); font: inherit; font-weight: 700; cursor: pointer; }",
                ".zoom-button:hover { border-color: var(--accent); color: var(--accent); }",
                ".zoom-value { min-width: 54px; text-align: center; color: var(--muted); font-size: 12px; font-weight: 700; }",
                ".meta { display: flex; flex-wrap: wrap; gap: 8px; padding: 10px 16px; border-bottom: 1px solid var(--line); background: #f8fafb; }",
                ".meta-item { display: inline-flex; gap: 6px; align-items: baseline; border: 1px solid #dfe5ec; border-radius: 8px; padding: 6px 8px; background: #ffffff; font-size: 12px; }",
                ".meta-item strong { color: var(--muted); font-size: 11px; text-transform: uppercase; letter-spacing: 0; }",
                ".viewport { background: #ffffff; overflow: auto; }",
                ".chart-viewport { height: 74vh; min-height: 560px; cursor: grab; overscroll-behavior: contain; }",
                ".chart-viewport.dragging { cursor: grabbing; user-select: none; }",
                ".zoom-stage { position: relative; width: 100%; height: 100%; min-width: 100%; min-height: 100%; }",
                ".pan-surface { position: absolute; inset: 0; z-index: 2; background: transparent; cursor: inherit; touch-action: none; }",
                "object { display: block; width: 100%; border: 0; background: #ffffff; }",
                ".chart-object { width: 100%; height: 100%; min-height: 100%; }",
                ".comparison-object { height: 520px; min-height: 420px; }",
                ".empty { padding: 36px 16px; color: var(--muted); font-weight: 700; text-align: center; }",
                "[hidden] { display: none !important; }",
                "@media (max-width: 860px) { .toolbar { grid-template-columns: 1fr; } .topbar { align-items: flex-start; flex-direction: column; } .button { width: 100%; } .chart-viewport { height: 68vh; min-height: 420px; } .section-head { align-items: flex-start; flex-direction: column; } }",
                "</style>",
                "</head>",
                "<body>",
                '<div class="shell">',
                '<header class="topbar">',
                "<h1>Petri Gantt Explorer</h1>",
                '<div id="countBadge" class="badge">0 charts</div>',
                "</header>",
                '<div class="toolbar">',
                '<label class="control"><span>View</span><select id="viewSelect"></select></label>',
                '<label class="control"><span>Algorithm</span><select id="methodSelect"></select></label>',
                '<label class="control"><span>Instance</span><select id="instanceSelect"></select></label>',
                '<a id="openSvg" class="button" href="#" target="_blank" rel="noopener">Open SVG</a>',
                "</div>",
                "<main>",
                '<section class="section">',
                '<div class="section-head"><h2 id="chartTitle">Gantt Chart</h2><div class="zoom-controls" aria-label="Gantt zoom controls"><button id="zoomOut" class="zoom-button" type="button" title="Zoom out">−</button><span id="zoomValue" class="zoom-value">100%</span><button id="zoomIn" class="zoom-button" type="button" title="Zoom in">+</button><button id="zoomReset" class="zoom-button" type="button" title="Reset zoom">Reset</button></div></div>',
                '<div id="chartMeta" class="meta"></div>',
                '<div id="emptyState" class="empty" hidden>No Gantt chart is available.</div>',
                '<div id="chartViewport" class="viewport chart-viewport"><div id="chartStage" class="zoom-stage"><object id="chartObject" class="chart-object" type="image/svg+xml"></object><div id="panSurface" class="pan-surface" aria-hidden="true"></div></div></div>',
                "</section>",
                '<section id="comparisonSection" class="section" hidden>',
                '<div class="section-head"><h2>Ablation Comparison</h2><a id="comparisonLink" class="button" href="#" target="_blank" rel="noopener">Open SVG</a></div>',
                '<div class="viewport"><object id="comparisonObject" class="comparison-object" type="image/svg+xml"></object></div>',
                "</section>",
                "</main>",
                "</div>",
                "<script>",
                "var CHARTS = " + chart_json + ";",
                "var VIEW_LABELS = " + view_label_json + ";",
                "var COMPARISON_SVG = " + comparison_json + ";",
                "(function () {",
                "  var charts = CHARTS || [];",
                "  var viewSelect = document.getElementById('viewSelect');",
                "  var methodSelect = document.getElementById('methodSelect');",
                "  var instanceSelect = document.getElementById('instanceSelect');",
                "  var chartObject = document.getElementById('chartObject');",
                "  var openSvg = document.getElementById('openSvg');",
                "  var emptyState = document.getElementById('emptyState');",
                "  var chartTitle = document.getElementById('chartTitle');",
                "  var chartMeta = document.getElementById('chartMeta');",
                "  var countBadge = document.getElementById('countBadge');",
                "  var chartViewport = document.getElementById('chartViewport');",
                "  var chartStage = document.getElementById('chartStage');",
                "  var zoomValue = document.getElementById('zoomValue');",
                "  var chartZoom = 1;",
                "  var chartBaseHeight = 0;",
                "  function applyZoom(nextZoom, anchorX, anchorY) {",
                "    var oldWidth = Math.max(chartStage.scrollWidth, chartViewport.clientWidth);",
                "    var oldHeight = Math.max(chartStage.scrollHeight, chartViewport.clientHeight);",
                "    var focusX = anchorX == null ? chartViewport.clientWidth / 2 : anchorX;",
                "    var focusY = anchorY == null ? chartViewport.clientHeight / 2 : anchorY;",
                "    var ratioX = (chartViewport.scrollLeft + focusX) / oldWidth;",
                "    var ratioY = (chartViewport.scrollTop + focusY) / oldHeight;",
                "    chartZoom = Math.max(0.5, Math.min(4, nextZoom));",
                "    if (!chartBaseHeight) { chartBaseHeight = Math.max(chartViewport.clientHeight, 560); }",
                "    chartStage.style.width = (chartZoom * 100) + '%';",
                "    chartStage.style.height = (chartBaseHeight * chartZoom) + 'px';",
                "    zoomValue.textContent = Math.round(chartZoom * 100) + '%';",
                "    requestAnimationFrame(function () {",
                "      chartViewport.scrollLeft = ratioX * chartStage.scrollWidth - focusX;",
                "      chartViewport.scrollTop = ratioY * chartStage.scrollHeight - focusY;",
                "    });",
                "  }",
                "  function resetZoom() {",
                "    chartBaseHeight = Math.max(chartViewport.clientHeight, 560);",
                "    chartZoom = 1;",
                "    chartStage.style.width = '100%';",
                "    chartStage.style.height = chartBaseHeight + 'px';",
                "    chartViewport.scrollLeft = 0;",
                "    chartViewport.scrollTop = 0;",
                "    zoomValue.textContent = '100%';",
                "  }",
                "  function unique(key) {",
                "    var seen = Object.create(null);",
                "    var values = [];",
                "    charts.forEach(function (chart) {",
                "      var value = String(chart[key] || '');",
                "      if (value && !seen[value]) { seen[value] = true; values.push(value); }",
                "    });",
                "    return values;",
                "  }",
                "  function setOptions(select, values, labels) {",
                "    var previous = select.value;",
                "    select.innerHTML = '';",
                "    values.forEach(function (value) {",
                "      var option = document.createElement('option');",
                "      option.value = value;",
                "      option.textContent = labels && labels[value] ? labels[value] : value;",
                "      select.appendChild(option);",
                "    });",
                "    if (values.indexOf(previous) >= 0) { select.value = previous; }",
                "  }",
                "  function renderMeta(entry) {",
                "    chartMeta.innerHTML = '';",
                "    [['Status', entry.status], ['Best obj', entry.best_obj], ['Solve time', entry.solving_time], ['c_max', entry.c_max], ['WPH', entry.wph]].forEach(function (item) {",
                "      var node = document.createElement('div');",
                "      var key = document.createElement('strong');",
                "      var value = document.createElement('span');",
                "      node.className = 'meta-item';",
                "      key.textContent = item[0];",
                "      value.textContent = item[1] || 'n/a';",
                "      node.appendChild(key);",
                "      node.appendChild(value);",
                "      chartMeta.appendChild(node);",
                "    });",
                "  }",
                "  function findEntry() {",
                "    var method = methodSelect.value;",
                "    var view = viewSelect.value;",
                "    var instance = instanceSelect.value;",
                "    return charts.find(function (chart) { return chart.method === method && chart.view === view && chart.instance === instance; }) ||",
                "      charts.find(function (chart) { return chart.method === method && chart.view === view; }) ||",
                "      charts.find(function (chart) { return chart.view === view; }) || charts[0];",
                "  }",
                "  function render() {",
                "    if (!charts.length) {",
                "      [viewSelect, methodSelect, instanceSelect].forEach(function (select) { select.disabled = true; });",
                "      chartObject.hidden = true;",
                "      openSvg.removeAttribute('href');",
                "      emptyState.hidden = false;",
                "      chartTitle.textContent = 'Gantt Chart';",
                "      countBadge.textContent = '0 charts';",
                "      return;",
                "    }",
                "    var entry = findEntry();",
                "    if (!entry) { return; }",
                "    viewSelect.value = entry.view;",
                "    methodSelect.value = entry.method;",
                "    instanceSelect.value = entry.instance;",
                "    chartObject.hidden = false;",
                "    emptyState.hidden = true;",
                "    chartObject.data = entry.path;",
                "    resetZoom();",
                "    openSvg.href = entry.path;",
                "    chartTitle.textContent = entry.title;",
                "    renderMeta(entry);",
                "    countBadge.textContent = charts.length + ' charts';",
                "  }",
                "  setOptions(viewSelect, unique('view'), VIEW_LABELS);",
                "  setOptions(methodSelect, unique('method'));",
                "  setOptions(instanceSelect, unique('instance'));",
                "  [viewSelect, methodSelect, instanceSelect].forEach(function (select) { select.addEventListener('change', render); });",
                "  document.getElementById('zoomOut').addEventListener('click', function () { applyZoom(chartZoom / 1.25); });",
                "  document.getElementById('zoomIn').addEventListener('click', function () { applyZoom(chartZoom * 1.25); });",
                "  document.getElementById('zoomReset').addEventListener('click', resetZoom);",
                "  chartViewport.addEventListener('wheel', function (event) {",
                "    event.preventDefault();",
                "    var rect = chartViewport.getBoundingClientRect();",
                "    applyZoom(chartZoom * (event.deltaY < 0 ? 1.12 : 1 / 1.12), event.clientX - rect.left, event.clientY - rect.top);",
                "  }, { passive: false });",
                "  var dragState = null;",
                "  chartViewport.addEventListener('pointerdown', function (event) {",
                "    if (event.button !== 0) { return; }",
                "    dragState = { x: event.clientX, y: event.clientY, left: chartViewport.scrollLeft, top: chartViewport.scrollTop };",
                "    chartViewport.classList.add('dragging');",
                "    chartViewport.setPointerCapture(event.pointerId);",
                "  });",
                "  chartViewport.addEventListener('pointermove', function (event) {",
                "    if (!dragState) { return; }",
                "    chartViewport.scrollLeft = dragState.left - (event.clientX - dragState.x);",
                "    chartViewport.scrollTop = dragState.top - (event.clientY - dragState.y);",
                "  });",
                "  function stopDrag(event) {",
                "    if (!dragState) { return; }",
                "    dragState = null;",
                "    chartViewport.classList.remove('dragging');",
                "    if (event && chartViewport.hasPointerCapture(event.pointerId)) { chartViewport.releasePointerCapture(event.pointerId); }",
                "  }",
                "  chartViewport.addEventListener('pointerup', stopDrag);",
                "  chartViewport.addEventListener('pointercancel', stopDrag);",
                "  chartViewport.addEventListener('dblclick', resetZoom);",
                "  render();",
                "  if (COMPARISON_SVG) {",
                "    document.getElementById('comparisonSection').hidden = false;",
                "    document.getElementById('comparisonObject').data = COMPARISON_SVG;",
                "    document.getElementById('comparisonLink').href = COMPARISON_SVG;",
                "  }",
                "}());",
                "</script>",
                "</body>",
                "</html>",
            ]
        ),
        encoding="utf-8",
    )
    return [str(manifest_path), str(index_html)]


def _adapt_rl_sat_solution(
    record: Dict[str, object], solution: Dict[str, object]
) -> Dict[str, object]:
    """Translate RL-SAT's compatibility map into original-renderer semantics.

    Older RL-SAT result files stored legacy interval bindings in CP-SAT ticks;
    current files mark them as seconds. The two-wafer front-end service also
    needs explicit ATR hold stages so every physical product lane is continuous
    and non-overlapping under the strict path validator.
    """

    if str(record.get("schema", "")).lower() != "rl-sat-result":
        return dict(solution)

    adapted = dict(solution)
    metadata = record.get("metadata", {})
    metadata = metadata if isinstance(metadata, dict) else {}
    legacy = metadata.get("legacy_solution", {})
    legacy = legacy if isinstance(legacy, dict) else {}
    scale = _float(metadata.get("time_scale", 1.0))
    if metadata.get("legacy_time_unit") != "seconds" and scale > 1.0:
        for name in legacy:
            if name not in adapted:
                continue
            if "_start" not in name and "_end" not in name:
                continue
            if name.startswith(("prod_stage_", "pec_stage_", "resource_task_")):
                continue
            adapted[name] = _float(adapted[name]) / scale

    pair_members: Dict[str, set] = {}
    for task in record.get("tasks", []) or []:
        if not isinstance(task, dict):
            continue
        task_meta = task.get("metadata", {})
        if not isinstance(task_meta, dict):
            continue
        pair_id = task_meta.get("pair_id")
        wafer_ids = task_meta.get("wafer_ids", [])
        if pair_id is None or not isinstance(wafer_ids, (list, tuple)):
            continue
        pair_members.setdefault(str(pair_id), set()).update(
            int(wafer_id) for wafer_id in wafer_ids
        )

    def stage_start(wafer_id: int, stage: str) -> float:
        return _float(adapted.get(f"prod_stage_start_{wafer_id}_{stage}", 0.0))

    def stage_end(wafer_id: int, stage: str) -> float:
        return _float(
            adapted.get(
                f"prod_stage_end_{wafer_id}_{stage}",
                stage_start(wafer_id, stage),
            )
        )

    for members in pair_members.values():
        ordered = sorted(members)
        if len(ordered) != 2:
            continue
        exchange_start = min(
            (
                stage_start(wafer_id, "atr_al_exchange")
                for wafer_id in ordered
                if stage_end(wafer_id, "atr_al_exchange")
                > stage_start(wafer_id, "atr_al_exchange") + 1e-9
            ),
            default=0.0,
        )
        exchange_end = max(
            stage_end(wafer_id, "atr_al_exchange") for wafer_id in ordered
        )
        if exchange_end <= exchange_start + 1e-9:
            continue
        for wafer_id in ordered:
            lp_al_end = stage_end(wafer_id, "atr_lp_al")
            al_start = stage_start(wafer_id, "al")
            al_end = stage_end(wafer_id, "al")
            llupper_transfer_start = stage_start(wafer_id, "atr_al_llupper")
            if al_start >= exchange_end - 1e-9 and exchange_start > lp_al_end + 1e-9:
                adapted[f"prod_stage_start_{wafer_id}_atr_hold_before_al"] = lp_al_end
                adapted[f"prod_stage_end_{wafer_id}_atr_hold_before_al"] = exchange_start
            if al_end <= exchange_start + 1e-9 and llupper_transfer_start > exchange_end + 1e-9:
                adapted[f"prod_stage_start_{wafer_id}_atr_hold_after_al"] = exchange_end
                adapted[f"prod_stage_end_{wafer_id}_atr_hold_after_al"] = llupper_transfer_start

    return adapted

def generate_gantt_charts_from_records(
    records: List[Dict[str, object]],
    output_dir: str,
    view: str = "all",
    comparison_svg: str = "",
) -> List[str]:
    out_dir = resolve_path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    generated = []
    chart_entries: List[Dict[str, str]] = []
    seen_stems: Dict[str, int] = {}

    for record in records:
        solution = dict(_adapt_rl_sat_solution(record, record.get("solution", {}) or {}))
        hyperparameters = record.get("hyperparameters", {}) or {}
        if isinstance(hyperparameters, dict) and hyperparameters.get("pec_pool_size") is not None:
            solution["_gantt_pec_pool_size"] = hyperparameters["pec_pool_size"]
        instance_name = Path(str(record.get("instance", "instance"))).stem
        method_name = _safe_file_part(str(record.get("method", "")).strip())
        base_file_stem = instance_name if not method_name or method_name == "result" else f"{instance_name}_{method_name}"
        file_stem = _unique_file_stem(base_file_stem, seen_stems)
        for view_name in _views_to_generate(view):
            schedule = _collect_schedule(solution, view_name)
            if not schedule.get("is_petri"):
                continue
            output_file = out_dir / _gantt_output_name(file_stem, view_name)
            _render_svg(record, schedule, output_file)
            generated.append(str(output_file))
            chart_entries.append(_chart_entry(record, schedule, view_name, output_file, out_dir))

    if chart_entries or comparison_svg:
        generated.extend(_write_interactive_gantt_frontend(out_dir, chart_entries, comparison_svg=comparison_svg))
    return generated


def generate_gantt_charts_from_solution_file(
    solution_json: str,
    output_dir: str = None,
    view: str = "all",
    comparison_svg: str = "",
) -> List[str]:
    solution_path, _, records = _load_solution_payload(solution_json)
    if output_dir is None:
        output_dir = str(solution_path.with_name(solution_path.stem + "_gantt"))
    else:
        output_dir = str(resolve_path(output_dir))
    return generate_gantt_charts_from_records(records, output_dir, view=view, comparison_svg=comparison_svg)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate Petri schedule Gantt charts from solution JSON.")
    parser.add_argument("--solution_json", type=str, required=True)
    parser.add_argument("--output_dir", type=str, default="")
    parser.add_argument(
        "--view",
        choices=["full", "chambers", "resources", "all"],
        default="all",
        help=(
            "full: product/PEC full-flow chart; "
            "chambers: only CH2/CH3 four-pocket module chart; "
            "resources: ATR/AL/LL/VTR/PM resource chart with wafer labels; "
            "all: generate every view."
        ),
    )
    parser.add_argument(
        "--comparison_svg",
        type=str,
        default="",
        help="Optional ablation comparison SVG to show in the generated frontend.",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    solution_path, payload, records = _load_solution_payload(args.solution_json)
    generated = generate_gantt_charts_from_solution_file(
        str(solution_path),
        args.output_dir or None,
        view=args.view,
        comparison_svg=args.comparison_svg,
    )
    if not generated:
        print("No Petri gantt charts were generated from the provided solution file.")
        for line in _diagnose_solution_payload(payload, records):
            print(line)
        return
    print("Generated Gantt outputs:")
    for path in generated:
        print(path)


if __name__ == "__main__":
    main()

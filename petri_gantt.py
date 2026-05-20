# -*- coding: utf-8 -*-
import argparse
import json
import math
import re
from pathlib import Path
from typing import Dict, List, Tuple

from path_utils import resolve_path


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
BAR_HEIGHT = 28

NEW_PRODUCT_STAGE_ORDER = [
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
NEW_PRODUCT_STAGE_META = {
    "atr_lp_al": ("LP->AL", "#4C78A8"),
    "al": ("AL", "#9C755F"),
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

    if not (assign_prod_by_batch or prod_stage_start or batch_used):
        return {}

    new_product_model = any(stage_name in NEW_PRODUCT_STAGE_ORDER for _, stage_name in prod_stage_start.keys())
    if new_product_model:
        lanes: List[str] = []
        tasks: List[Dict[str, object]] = []
        time_candidates = [c_max]

        product_ids = sorted(
            {wafer_id for wafer_id, _ in prod_stage_start.keys()} | {wafer_id for wafer_id, _ in prod_stage_end.keys()},
            key=lambda wafer_id: (
                prod_stage_start.get((wafer_id, "atr_lp_al"), prod_stage_end.get((wafer_id, "atr_lp_al"), 0.0)),
                wafer_id,
            ),
        )
        for wafer_id in product_ids:
            assignment = assign_prod_by_wafer.get(wafer_id)
            lane_name = f"Product W{wafer_id}"
            if assignment is not None:
                lane_name += f" | PM{assignment[0]}-B{assignment[1]}"
            lanes.append(lane_name)
            for stage_name in NEW_PRODUCT_STAGE_ORDER:
                start = prod_stage_start.get((wafer_id, stage_name), 0.0)
                end = prod_stage_end.get((wafer_id, stage_name), start)
                if end <= start + 1e-9:
                    continue
                label, color = NEW_PRODUCT_STAGE_META[stage_name]
                tasks.append(
                    {
                        "lane": lane_name,
                        "start": start,
                        "end": end,
                        "label": label,
                        "short_label": label,
                        "color": color,
                    }
                )
                time_candidates.extend([start, end])

        pec_ids = sorted(
            {pec_id for pec_id, _ in pec_stage_start.keys()} | {pec_id for pec_id, _ in pec_stage_end.keys()},
            key=lambda pec_id: (
                pec_stage_start.get((pec_id, "vtr_load"), pec_stage_end.get((pec_id, "vtr_load"), 0.0)),
                pec_id,
            ),
        )
        for pec_id in pec_ids:
            has_activity = any(
                pec_stage_end.get((pec_id, stage_name), 0.0) > pec_stage_start.get((pec_id, stage_name), 0.0) + 1e-9
                for stage_name in NEW_PEC_STAGE_ORDER
            )
            if not has_activity:
                continue
            assignment = assign_pec_by_pec.get(pec_id)
            lane_name = f"PEC E{pec_id}"
            if assignment is not None:
                lane_name += f" | PM{assignment[0]}-B{assignment[1]}"
            lanes.append(lane_name)
            for stage_name in NEW_PEC_STAGE_ORDER:
                start = pec_stage_start.get((pec_id, stage_name), 0.0)
                end = pec_stage_end.get((pec_id, stage_name), start)
                if end <= start + 1e-9:
                    continue
                label, color = NEW_PEC_STAGE_META[stage_name]
                tasks.append(
                    {
                        "lane": lane_name,
                        "start": start,
                        "end": end,
                        "label": label,
                        "short_label": label,
                        "color": color,
                    }
                )
                time_candidates.extend([start, end])

        if not lanes:
            return {}

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


def _collect_schedule(solution: Dict[str, float]) -> Dict[str, object]:
    new_schedule = _collect_path_schedule(solution)
    if new_schedule:
        return new_schedule
    return _collect_legacy_schedule(solution)


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


def _render_svg(record: Dict[str, object], schedule: Dict[str, object], output_file: Path) -> None:
    lanes = schedule["lanes"]
    height = TOP_MARGIN + BOTTOM_MARGIN + len(lanes) * LANE_HEIGHT
    horizon = float(schedule["horizon"])
    c_max = float(schedule["c_max"])

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{SVG_WIDTH}" height="{height}" viewBox="0 0 {SVG_WIDTH} {height}">',
        '<style>'
        'text { font-family: "Segoe UI", "Microsoft YaHei", sans-serif; fill: #222; }'
        '.title { font-size: 24px; font-weight: 700; }'
        '.subtitle { font-size: 14px; fill: #555; }'
        '.lane { font-size: 13px; font-weight: 600; }'
        '.tick { font-size: 11px; fill: #666; }'
        '.bartext { font-size: 11px; fill: #fff; font-weight: 600; }'
        '.marker { font-size: 11px; fill: #333; }'
        '</style>',
        f'<rect x="0" y="0" width="{SVG_WIDTH}" height="{height}" fill="#ffffff"/>',
        f'<text class="title" x="{LEFT_MARGIN}" y="38">{_escape(Path(str(record.get("instance", "instance"))).stem)} Scheduling Gantt</text>',
        f'<text class="subtitle" x="{LEFT_MARGIN}" y="66">status={_escape(record.get("status", "unknown"))} | best_obj={_escape(record.get("best_obj", "None"))} | c_max={c_max:.3f}</text>',
        f'<text class="subtitle" x="{LEFT_MARGIN}" y="88">Labels are clipped to the bar width. Narrow bars use short labels or hover titles to avoid overlap.</text>',
    ]

    tick_count = min(max(int(math.ceil(horizon / 20.0)), 5), 12)
    for i in range(tick_count + 1):
        t = horizon * i / tick_count
        x = _time_to_x(t, horizon)
        parts.append(
            f'<line x1="{x:.2f}" y1="{TOP_MARGIN - 8}" x2="{x:.2f}" y2="{height - BOTTOM_MARGIN + 8}" stroke="#efefef" stroke-width="1"/>'
        )
        parts.append(f'<text class="tick" x="{x - 12:.2f}" y="{height - BOTTOM_MARGIN + 34}">{t:.1f}</text>')

    lane_index = {lane_name: idx for idx, lane_name in enumerate(lanes)}
    for lane_idx, lane_name in enumerate(lanes):
        y = _lane_y(lane_idx)
        parts.append(
            f'<line x1="{LEFT_MARGIN}" y1="{y + BAR_HEIGHT + 14}" x2="{SVG_WIDTH - RIGHT_MARGIN}" y2="{y + BAR_HEIGHT + 14}" stroke="#dddddd" stroke-width="1"/>'
        )
        lane_lines = _wrap_text(lane_name, max(18, int((LEFT_MARGIN - 42) / 8.6)), max_lines=2)
        parts.append(_render_multiline_text("lane", lane_lines, 18, y + 16, line_height=16))

    for task_idx, task in enumerate(schedule["tasks"]):
        y = _lane_y(lane_index[task["lane"]])
        x = _time_to_x(float(task["start"]), horizon)
        width = max(_time_to_x(float(task["end"]), horizon) - x, 2.0)
        full_label = str(task.get("label", "")).strip()
        short_label = str(task.get("short_label", "")).strip()
        hover_label = full_label or short_label or str(task["lane"])
        parts.append(
            f'<g><title>{_escape(hover_label)}</title><rect x="{x:.2f}" y="{y:.2f}" width="{width:.2f}" height="{BAR_HEIGHT}" rx="4" ry="4" fill="{task["color"]}" fill-opacity="0.9" stroke="#2f2f2f" stroke-width="0.7"/></g>'
        )
        if width >= 96.0 and full_label:
            lines = _wrap_text(full_label, max(8, int(width / 8.2)), max_lines=2)
            parts.append(_render_clipped_task_label(lines, x, y, width, f"task_clip_{task_idx}"))
        elif width >= 52.0 and short_label:
            lines = _wrap_text(short_label, max(4, int(width / 8.6)), max_lines=1)
            parts.append(_render_clipped_task_label(lines, x, y, width, f"task_clip_{task_idx}"))

    for marker in schedule["markers"]:
        lane_name = marker["lane"]
        if lane_name not in lane_index:
            continue
        marker_center_y = _lane_y(lane_index[lane_name]) + BAR_HEIGHT / 2
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

    if c_max > 0.0:
        x = _time_to_x(c_max, horizon)
        cmax_anchor = "start"
        cmax_x = x + 8.0
        if x > SVG_WIDTH - RIGHT_MARGIN - 110:
            cmax_anchor = "end"
            cmax_x = x - 8.0
        parts.append(
            f'<line x1="{x:.2f}" y1="{TOP_MARGIN - 18}" x2="{x:.2f}" y2="{height - BOTTOM_MARGIN}" stroke="#C00000" stroke-width="2.2" stroke-dasharray="8 4"/>'
        )
        parts.append(
            f'<text class="lane" x="{cmax_x:.2f}" y="{TOP_MARGIN - 24}" text-anchor="{cmax_anchor}">c_max={c_max:.1f}</text>'
        )

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
    solution_path = resolve_path(solution_json)
    with solution_path.open("r", encoding="utf-8") as f:
        payload = json.load(f)
    records = _normalize_records(payload)
    return solution_path, payload, records


def generate_gantt_charts_from_records(records: List[Dict[str, object]], output_dir: str) -> List[str]:
    out_dir = resolve_path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    generated = []
    html_items = []

    for record in records:
        solution = record.get("solution", {}) or {}
        schedule = _collect_schedule(solution)
        if not schedule.get("is_petri"):
            continue
        instance_name = Path(str(record.get("instance", "instance"))).stem
        method_name = re.sub(r"[^0-9A-Za-z_-]+", "_", str(record.get("method", "")).strip()).strip("_")
        file_stem = instance_name if not method_name else f"{instance_name}_{method_name}"
        output_file = out_dir / f"{file_stem}_gantt.svg"
        _render_svg(record, schedule, output_file)
        generated.append(str(output_file))
        html_items.append(
            f'<li><a href="{output_file.name}">{_escape(output_file.name)}</a> | status={_escape(record.get("status", "unknown"))} | best_obj={_escape(record.get("best_obj", "None"))}</li>'
        )

    if generated:
        index_html = out_dir / "index.html"
        index_html.write_text(
            "\n".join(
                [
                    "<!doctype html>",
                    '<html><head><meta charset="utf-8"><title>Petri Gantt Charts</title></head><body>',
                    "<h1>Petri Gantt Charts</h1>",
                    "<ul>",
                    *html_items,
                    "</ul>",
                    "</body></html>",
                ]
            ),
            encoding="utf-8",
        )
        generated.append(str(index_html))
    return generated


def generate_gantt_charts_from_solution_file(solution_json: str, output_dir: str = None) -> List[str]:
    solution_path, _, records = _load_solution_payload(solution_json)
    if output_dir is None:
        output_dir = str(solution_path.with_name(solution_path.stem + "_gantt"))
    else:
        output_dir = str(resolve_path(output_dir))
    return generate_gantt_charts_from_records(records, output_dir)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate Petri schedule Gantt charts from solution JSON.")
    parser.add_argument("--solution_json", type=str, required=True)
    parser.add_argument("--output_dir", type=str, default="")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    solution_path, payload, records = _load_solution_payload(args.solution_json)
    generated = generate_gantt_charts_from_solution_file(
        str(solution_path),
        args.output_dir or None,
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

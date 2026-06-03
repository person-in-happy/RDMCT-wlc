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
NEW_FULL_ASSIGN_RE = re.compile(r"assign_full_(\d+)_(\d+)_(\d+)_(\d+)$")
NEW_FULL_BATCH_USED_RE = re.compile(r"full_batch_used_(\d+)_(\d+)$")
NEW_FULL_FILLER_SIDE_RE = re.compile(r"full_filler_side_(\d+)_(\d+)_(\d+)$")
NEW_MIX_ASSIGN_RE = re.compile(r"assign_mix_(\d+)_(\d+)_(\d+)$")
NEW_MIX_ACTIVE_RE = re.compile(r"mix_active_(\d+)$")
NEW_MIX_CYCLE_USED_RE = re.compile(r"mix_cycle_used_(\d+)_(\d+)$")
NEW_CLEAN_ACTIVE_RE = re.compile(r"clean_active_(\d+)_(\d+)$")
LLUPPER_SLOT_ASSIGN_RE = re.compile(r"llupper_slot_assign_(\d+)_(\d+)$")
LLLOWER_SLOT_ASSIGN_RE = re.compile(r"lllower_slot_assign_(\d+)_(\d+)$")
PEC_TOKEN_ASSIGN_RE = re.compile(r"pec_token_assign_(\d+)_(\d+)$")
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
    pec_token_by_job: Dict[int, int] = {}
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
            entity = f"W{wafer_id}"

            add_path_task(
                lane_name,
                product_start(wafer_id, "atr_lp_al"),
                product_end(wafer_id, "atr_lp_al"),
                "ATR LP->AL",
                entity,
                "#4C78A8",
            )
            add_path_task(
                lane_name,
                product_end(wafer_id, "atr_lp_al"),
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
            add_path_task(
                lane_name,
                product_end(wafer_id, "al"),
                product_start(wafer_id, "atr_al_llupper"),
                "AL wait",
                entity,
                "#C6A07A",
            )
            add_path_task(
                lane_name,
                product_start(wafer_id, "atr_al_llupper"),
                product_end(wafer_id, "atr_al_llupper"),
                "ATR AL->LLupper",
                entity,
                "#72B7B2",
            )
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
                "LLupper state",
                entity,
                "#54A24B",
            )
            add_path_task(
                lane_name,
                product_end(wafer_id, "llupper"),
                product_start(wafer_id, "vtr_load"),
                "LLupper ready",
                entity,
                "#8CD17D",
            )
            add_path_task(
                lane_name,
                product_start(wafer_id, "vtr_load"),
                product_end(wafer_id, "vtr_load"),
                "VTR load",
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
            add_path_task(
                lane_name,
                product_start(wafer_id, "pm"),
                product_end(wafer_id, "pm"),
                "PM process",
                entity,
                "#E45756",
            )
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
                "VTR unload",
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
                "LLlower state",
                entity,
                "#B279A2",
            )
            add_path_task(
                lane_name,
                product_end(wafer_id, "lllower"),
                product_start(wafer_id, "atr_lllower_lp"),
                "LLlower wait",
                entity,
                "#D4A6C8",
            )
            add_path_task(
                lane_name,
                product_start(wafer_id, "atr_lllower_lp"),
                product_end(wafer_id, "atr_lllower_lp"),
                "ATR LLlower->LP",
                entity,
                "#79706E",
            )

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
            token_id = pec_token_by_job.get(pec_id)
            entity = f"PEC{token_id}" if token_id is not None else f"E{pec_id}"
            load_start = pec_stage_start.get((pec_id, "vtr_load"), 0.0)
            load_end = pec_stage_end.get((pec_id, "vtr_load"), load_start)
            pm_start = pec_stage_start.get((pec_id, "pm"), load_end)
            pm_end = pec_stage_end.get((pec_id, "pm"), pm_start)
            unload_start = pec_stage_start.get((pec_id, "vtr_unload"), pm_end)
            unload_end = pec_stage_end.get((pec_id, "vtr_unload"), unload_start)
            add_path_task(lane_name, load_start, load_end, "VTR PEC->PM", entity, "#72B7B2")
            add_path_task(lane_name, load_end, pm_start, "PM wait", entity, "#F2A09A")
            add_path_task(lane_name, pm_start, pm_end, "PM process", entity, "#E45756")
            add_path_task(lane_name, pm_end, unload_start, "PM wait", entity, "#F2A09A")
            add_path_task(lane_name, unload_start, unload_end, "VTR PM->PEC", entity, "#B279A2")

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


def _collect_chamber_schedule(solution: Dict[str, float]) -> Dict[str, object]:
    full_pair_members: Dict[int, List[int]] = {}
    mix_pair_members: Dict[int, List[int]] = {}
    full_assignment: Dict[Tuple[int, int, int], int] = {}
    full_used: Dict[Tuple[int, int], bool] = {}
    full_filler: Dict[Tuple[int, int, int], bool] = {}
    mix_pair_by_pos: Dict[Tuple[int, int], int] = {}
    mix_active: Dict[int, bool] = {}
    mix_cycle_used: Dict[Tuple[int, int], bool] = {}
    clean_active: Dict[Tuple[int, int], bool] = {}
    pec_stage_start: Dict[Tuple[int, str], float] = {}
    pec_stage_end: Dict[Tuple[int, str], float] = {}
    pec_token_by_job: Dict[int, int] = {}
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

        active_mix = mix_active.get(pm_id, False) or any(key_pm == pm_id for key_pm, _ in mix_pair_by_pos)
        if active_mix:
            pos_ids = sorted(pos for key_pm, pos in mix_pair_by_pos if key_pm == pm_id)
            max_pos = max(pos_ids, default=0)
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

            cycle_ids = sorted(cycle for key_pm, cycle in mix_cycle_used if key_pm == pm_id and mix_cycle_used[(key_pm, cycle)])
            for cycle_id in cycle_ids:
                if cycle_id >= 2:
                    bridge_start = time_var(f"mix_bridge_start_{pm_id}_{cycle_id}")
                    bridge_end = time_var(f"mix_bridge_end_{pm_id}_{cycle_id}")
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
            if tail_end > tail_start + 1e-9:
                tasks.append(
                    {
                        "lane": lane_name,
                        "start": tail_start,
                        "end": tail_end,
                        "label": f"2x2 tail\n{pec_text(tail_pec)} return",
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
    llupper_slot_by_wafer: Dict[int, int] = {}
    lllower_slot_by_wafer: Dict[int, int] = {}
    pec_token_by_job: Dict[int, int] = {}
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
        m = LLUPPER_SLOT_ASSIGN_RE.match(name)
        if m and _bool(value):
            llupper_slot_by_wafer[int(m.group(1))] = int(m.group(2))
            continue
        m = LLLOWER_SLOT_ASSIGN_RE.match(name)
        if m and _bool(value):
            lllower_slot_by_wafer[int(m.group(1))] = int(m.group(2))
            continue
        m = PEC_TOKEN_ASSIGN_RE.match(name)
        if m and _bool(value):
            pec_token_by_job[int(m.group(1))] = int(m.group(2))
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
        for pm_id, pm_start, pm_end in pm_process_intervals:
            if abs(pm_start - start) <= 1e-6 and abs(pm_end - end) <= 1e-6:
                return pm_id
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

    pec_pm_by_job: Dict[int, int] = {}
    pec_job_ids = sorted({job_id for job_id, _ in pec_stage_start} | {job_id for job_id, _ in pec_stage_end})
    for job_id in pec_job_ids:
        start = pec_stage_start.get((job_id, "pm"), 0.0)
        end = pec_stage_end.get((job_id, "pm"), 0.0)
        pm_id = infer_pm_for_interval(start, end)
        if pm_id:
            pec_pm_by_job[job_id] = pm_id
            pm_ids.add(pm_id)

    ordered_pm_ids = [2, 3] if pm_ids and pm_ids.issubset({2, 3}) else sorted(pm_ids)
    llupper_slots = sorted(set(llupper_slot_by_wafer.values()) | ({1, 2} if llupper_slot_by_wafer else set()))
    lllower_slots = sorted(set(lllower_slot_by_wafer.values()) | ({1, 2} if lllower_slot_by_wafer else set()))
    lane_order: List[str] = ["ATR robot", "AL"]
    lane_order.extend(f"LLupper slot {slot_id}" for slot_id in llupper_slots)
    if not llupper_slots:
        lane_order.append("LLupper")
    lane_order.append("VTR robot")
    lane_order.extend(f"CH{pm_id} PM" for pm_id in ordered_pm_ids)
    if not ordered_pm_ids:
        lane_order.append("PM")
    lane_order.extend(f"LLlower slot {slot_id}" for slot_id in lllower_slots)
    if not lllower_slots:
        lane_order.append("LLlower")

    aggregated: Dict[Tuple[str, float, float, str, str], Dict[str, object]] = {}
    time_candidates: List[float] = []

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

    def product_start(wafer_id: int, stage_name: str) -> float:
        return prod_stage_start.get((wafer_id, stage_name), 0.0)

    def product_end(wafer_id: int, stage_name: str) -> float:
        return prod_stage_end.get((wafer_id, stage_name), product_start(wafer_id, stage_name))

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

    def add_single_product_pair_empty_slot(pair_label: str, members: List[int]) -> None:
        if len(members) != 1:
            return
        wafer_id = members[0]
        upper_slot = llupper_slot_by_wafer.get(wafer_id)
        if upper_slot in (1, 2):
            empty_slot = 2 if upper_slot == 1 else 1
            add_task(
                f"LLupper slot {empty_slot}",
                product_start(wafer_id, "llupper"),
                product_end(wafer_id, "llupper"),
                "LLupper sync empty",
                f"{pair_label} empty",
                "#BAB0AC",
            )
        lower_slot = lllower_slot_by_wafer.get(wafer_id)
        if lower_slot in (1, 2):
            empty_slot = 2 if lower_slot == 1 else 1
            add_task(
                f"LLlower slot {empty_slot}",
                product_start(wafer_id, "lllower"),
                product_end(wafer_id, "lllower"),
                "LLlower sync empty",
                f"{pair_label} empty",
                "#BAB0AC",
            )

    for wafer_id in product_ids:
        entity = f"W{wafer_id}"
        pm_id = wafer_pm.get(wafer_id, 0)
        add_task("ATR robot", product_start(wafer_id, "atr_lp_al"), product_end(wafer_id, "atr_lp_al"), "LP->AL", entity, "#4C78A8")
        add_task(
            "AL",
            product_end(wafer_id, "atr_lp_al"),
            product_end(wafer_id, "atr_al_llupper"),
            "AL occupy",
            entity,
            "#9C755F",
        )
        add_task("ATR robot", product_start(wafer_id, "atr_al_llupper"), product_end(wafer_id, "atr_al_llupper"), "AL->LLupper", entity, "#72B7B2")
        llupper_entry = product_end(wafer_id, "atr_al_llupper")
        llupper_state_start = product_start(wafer_id, "llupper")
        if llupper_state_start > llupper_entry + 1e-9:
            add_task(
                llupper_lane(wafer_id),
                llupper_entry,
                llupper_state_start,
                "LLupper wait",
                entity,
                "#8CD17D",
            )
        add_task(
            llupper_lane(wafer_id),
            llupper_state_start,
            product_end(wafer_id, "llupper"),
            "LLupper state",
            entity,
            "#54A24B",
        )
        add_task("VTR robot", product_start(wafer_id, "vtr_load"), product_end(wafer_id, "vtr_load"), f"VTR load{ch_suffix(pm_id)}", entity, "#F58518")
        add_task(pm_lane(pm_id), product_start(wafer_id, "pm"), product_end(wafer_id, "pm"), "PM process", entity, "#E45756")
        add_task("VTR robot", product_start(wafer_id, "vtr_unload"), product_end(wafer_id, "vtr_unload"), f"VTR unload{ch_suffix(pm_id)}", entity, "#FF9DA6")
        add_task(
            lllower_lane(wafer_id),
            product_start(wafer_id, "lllower"),
            product_end(wafer_id, "lllower"),
            "LLlower state",
            entity,
            "#B279A2",
        )
        lllower_exit_start = product_start(wafer_id, "atr_lllower_lp")
        lllower_state_end = product_end(wafer_id, "lllower")
        if lllower_exit_start > lllower_state_end + 1e-9:
            add_task(
                lllower_lane(wafer_id),
                lllower_state_end,
                lllower_exit_start,
                "LLlower wait",
                entity,
                "#D4A6C8",
            )
        add_task("ATR robot", product_start(wafer_id, "atr_lllower_lp"), product_end(wafer_id, "atr_lllower_lp"), "LLlower->LP", entity, "#79706E")

    for pair_id, members in sorted(full_pair_members.items()):
        add_single_product_pair_empty_slot(f"F{pair_id}", sorted(members))
    for pair_id, members in sorted(mix_pair_members.items()):
        add_single_product_pair_empty_slot(f"M{pair_id}", sorted(members))

    def pec_entity(job_id: int) -> str:
        token_id = pec_token_by_job.get(job_id)
        return f"PEC{token_id}" if token_id is not None else f"E{job_id}"

    for job_id in pec_job_ids:
        entity = pec_entity(job_id)
        pm_id = pec_pm_by_job.get(job_id, 0)
        add_task(
            "VTR robot",
            pec_stage_start.get((job_id, "vtr_load"), 0.0),
            pec_stage_end.get((job_id, "vtr_load"), 0.0),
            f"VTR load{ch_suffix(pm_id)}",
            entity,
            "#F58518",
        )
        add_task(
            pm_lane(pm_id),
            pec_stage_start.get((job_id, "pm"), 0.0),
            pec_stage_end.get((job_id, "pm"), 0.0),
            "PM process",
            entity,
            "#E45756",
        )
        add_task(
            "VTR robot",
            pec_stage_start.get((job_id, "vtr_unload"), 0.0),
            pec_stage_end.get((job_id, "vtr_unload"), 0.0),
            f"VTR unload{ch_suffix(pm_id)}",
            entity,
            "#FF9DA6",
        )

    tasks: List[Dict[str, object]] = []
    for item in aggregated.values():
        entities = _format_entity_list(item["entities"])
        action = str(item["action"])
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
    lanes = [lane for lane in lane_order if lane in active_lanes]
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


def _render_svg(record: Dict[str, object], schedule: Dict[str, object], output_file: Path) -> None:
    lanes = schedule["lanes"]
    horizon = float(schedule["horizon"])
    c_max = float(schedule["c_max"])
    title_suffix = str(schedule.get("title_suffix", "Scheduling Gantt"))
    wph_stats = schedule.get("wph_stats")

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
        '.marker { font-size: 11px; fill: #333; }'
        '.wph { font-size: 14px; fill: #222; font-weight: 600; }'
        '.wph-detail { font-size: 13px; fill: #555; }'
        '</style>',
        f'<rect x="0" y="0" width="{SVG_WIDTH}" height="{height}" fill="#ffffff"/>',
        f'<text class="title" x="{LEFT_MARGIN}" y="38">{_escape(Path(str(record.get("instance", "instance"))).stem)} {_escape(title_suffix)}</text>',
        f'<text class="subtitle" x="{LEFT_MARGIN}" y="66">status={_escape(record.get("status", "unknown"))} | best_obj={_escape(record.get("best_obj", "None"))} | c_max={c_max:.3f}</text>',
        f'<text class="subtitle" x="{LEFT_MARGIN}" y="88">Bar labels and hover titles include product W ids or PEC token ids; narrow bars are clipped to avoid overlap.</text>',
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
        parts.append(
            f'<g><title>{_escape(hover_label)}</title><rect x="{x:.2f}" y="{y:.2f}" width="{width:.2f}" height="{BAR_HEIGHT}" rx="4" ry="4" fill="{task["color"]}" fill-opacity="0.9" stroke="#2f2f2f" stroke-width="0.7"/></g>'
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


def generate_gantt_charts_from_records(records: List[Dict[str, object]], output_dir: str, view: str = "full") -> List[str]:
    out_dir = resolve_path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    generated = []
    html_items = []

    for record in records:
        solution = record.get("solution", {}) or {}
        instance_name = Path(str(record.get("instance", "instance"))).stem
        method_name = re.sub(r"[^0-9A-Za-z_-]+", "_", str(record.get("method", "")).strip()).strip("_")
        file_stem = instance_name if not method_name else f"{instance_name}_{method_name}"
        for view_name in _views_to_generate(view):
            schedule = _collect_schedule(solution, view_name)
            if not schedule.get("is_petri"):
                continue
            output_file = out_dir / _gantt_output_name(file_stem, view_name)
            _render_svg(record, schedule, output_file)
            generated.append(str(output_file))
            html_items.append(
                f'<li><a href="{output_file.name}">{_escape(output_file.name)}</a> | view={_escape(view_name)} | status={_escape(record.get("status", "unknown"))} | best_obj={_escape(record.get("best_obj", "None"))}</li>'
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


def generate_gantt_charts_from_solution_file(solution_json: str, output_dir: str = None, view: str = "full") -> List[str]:
    solution_path, _, records = _load_solution_payload(solution_json)
    if output_dir is None:
        output_dir = str(solution_path.with_name(solution_path.stem + "_gantt"))
    else:
        output_dir = str(resolve_path(output_dir))
    return generate_gantt_charts_from_records(records, output_dir, view=view)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate Petri schedule Gantt charts from solution JSON.")
    parser.add_argument("--solution_json", type=str, required=True)
    parser.add_argument("--output_dir", type=str, default="")
    parser.add_argument(
        "--view",
        choices=["full", "chambers", "resources", "all"],
        default="full",
        help=(
            "full: product/PEC full-flow chart; "
            "chambers: only CH2/CH3 four-pocket module chart; "
            "resources: ATR/AL/LL/VTR/PM resource chart with wafer labels; "
            "all: generate every view."
        ),
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    solution_path, payload, records = _load_solution_payload(args.solution_json)
    generated = generate_gantt_charts_from_solution_file(
        str(solution_path),
        args.output_dir or None,
        view=args.view,
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

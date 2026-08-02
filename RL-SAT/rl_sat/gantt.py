"""Dependency-free SVG Gantt rendering for RL-SAT schedules."""

from __future__ import annotations

import hashlib
import html
import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Mapping, Sequence, Tuple

from .result_io import normalise_tasks, result_to_dict


_PALETTE = (
    "#4E79A7",
    "#F28E2B",
    "#E15759",
    "#76B7B2",
    "#59A14F",
    "#EDC948",
    "#B07AA1",
    "#FF9DA7",
    "#9C755F",
    "#BAB0AC",
    "#2F4B7C",
    "#A05195",
    "#D45087",
    "#F95D6A",
    "#FF7C43",
    "#FFA600",
)


def _escape(value: Any) -> str:
    return html.escape(str(value), quote=True)


def _colour(value: Any) -> str:
    digest = hashlib.sha1(str(value).encode("utf-8")).digest()
    return _PALETTE[int.from_bytes(digest[:2], "big") % len(_PALETTE)]


def _finite(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if math.isfinite(number) else default


def _sort_key(value: Any) -> Tuple[int, Any]:
    text = str(value)
    try:
        return (0, float(text))
    except ValueError:
        return (1, text.lower())


def _ticks(max_time: float, target: int = 10) -> Tuple[float, List[float]]:
    if max_time <= 0:
        return 1.0, [0.0, 1.0]
    raw = max_time / max(target, 1)
    exponent = 10.0 ** math.floor(math.log10(raw))
    fraction = raw / exponent
    if fraction <= 1.0:
        step = exponent
    elif fraction <= 2.0:
        step = 2.0 * exponent
    elif fraction <= 5.0:
        step = 5.0 * exponent
    else:
        step = 10.0 * exponent
    last = math.ceil(max_time / step) * step
    count = int(round(last / step))
    return last, [index * step for index in range(count + 1)]


def _format_time(value: float) -> str:
    if abs(value - round(value)) < 1e-8:
        return str(int(round(value)))
    return f"{value:.2f}".rstrip("0").rstrip(".")


def _svg_document(
    *,
    title: str,
    subtitle: str,
    lanes: Sequence[Tuple[str, Sequence[Mapping[str, Any]]]],
    colour_by: Callable[[Mapping[str, Any]], Any],
    label: Callable[[Mapping[str, Any]], str],
    max_time: float,
    compact: bool = False,
) -> str:
    left = 180
    right = 28
    top = 92
    bottom = 58
    lane_height = 34 if compact else 46
    bar_height = 19 if compact else 27
    plot_width = max(840, int(max_time * 8))
    width = left + plot_width + right
    height = top + max(1, len(lanes)) * lane_height + bottom
    axis_max, ticks = _ticks(max_time)

    def x(time_value: float) -> float:
        return left + max(0.0, time_value) / axis_max * plot_width

    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
            f'viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">'
        ),
        f"<title id=\"title\">{_escape(title)}</title>",
        f"<desc id=\"desc\">{_escape(subtitle)}</desc>",
        "<style>",
        "text{font-family:Inter,Segoe UI,Arial,sans-serif;fill:#263238}",
        ".title{font-size:22px;font-weight:700}.subtitle{font-size:12px;fill:#607d8b}",
        ".lane{font-size:12px;font-weight:600}.tick{font-size:10px;fill:#78909c}",
        ".bar-label{font-size:10px;font-weight:600;fill:#fff;pointer-events:none}",
        ".grid{stroke:#dfe6e9;stroke-width:1}.lane-line{stroke:#eef2f4;stroke-width:1}",
        ".bar{stroke:#fff;stroke-width:1;rx:3;ry:3}",
        "</style>",
        '<rect width="100%" height="100%" fill="#fff"/>',
        f'<text class="title" x="24" y="34">{_escape(title)}</text>',
        f'<text class="subtitle" x="24" y="57">{_escape(subtitle)}</text>',
    ]

    plot_bottom = top + max(1, len(lanes)) * lane_height
    for tick in ticks:
        tick_x = x(tick)
        parts.append(
            f'<line class="grid" x1="{tick_x:.2f}" y1="{top - 10}" '
            f'x2="{tick_x:.2f}" y2="{plot_bottom}"/>'
        )
        parts.append(
            f'<text class="tick" text-anchor="middle" x="{tick_x:.2f}" '
            f'y="{plot_bottom + 22}">{_escape(_format_time(tick))}</text>'
        )

    if not lanes:
        parts.append(
            f'<text x="{left}" y="{top + lane_height / 2:.1f}" '
            'fill="#90a4ae">No scheduled tasks</text>'
        )

    for row, (lane_name, tasks) in enumerate(lanes):
        lane_top = top + row * lane_height
        centre = lane_top + lane_height / 2
        parts.append(
            f'<line class="lane-line" x1="16" y1="{lane_top + lane_height:.2f}" '
            f'x2="{width - right}" y2="{lane_top + lane_height:.2f}"/>'
        )
        parts.append(
            f'<text class="lane" text-anchor="end" x="{left - 12}" '
            f'y="{centre + 4:.2f}">{_escape(lane_name)}</text>'
        )

        for task in sorted(tasks, key=lambda item: (item["start"], item["end"], item["id"])):
            start = _finite(task["start"])
            end = max(start, _finite(task["end"], start))
            bar_x = x(start)
            bar_width = max(1.5, x(end) - bar_x)
            bar_y = centre - bar_height / 2
            colour = _colour(colour_by(task))
            tooltip = (
                f'{task["id"]} | wafer={task["wafer"]} | stage={task["stage"]} | '
                f'resource={task["resource"]} | [{_format_time(start)}, {_format_time(end)}]'
            )
            parts.append(
                f'<g><title>{_escape(tooltip)}</title><rect class="bar" x="{bar_x:.2f}" '
                f'y="{bar_y:.2f}" width="{bar_width:.2f}" height="{bar_height}" '
                f'fill="{colour}"/></g>'
            )
            text = label(task)
            estimated_width = len(text) * (5.7 if compact else 6.0)
            if bar_width >= estimated_width + 8:
                parts.append(
                    f'<text class="bar-label" x="{bar_x + 4:.2f}" y="{centre + 3.5:.2f}">'
                    f"{_escape(text)}</text>"
                )

    parts.extend(
        [
            f'<text class="tick" text-anchor="middle" x="{left + plot_width / 2:.2f}" '
            f'y="{height - 14}">Time</text>',
            "</svg>",
        ]
    )
    return "\n".join(parts) + "\n"


def _group(tasks: Iterable[Mapping[str, Any]], field: str) -> List[Tuple[str, List[Mapping[str, Any]]]]:
    groups: Dict[str, List[Mapping[str, Any]]] = defaultdict(list)
    for task in tasks:
        value = task.get(field)
        label = "unassigned" if value is None or value == "" else str(value)
        groups[label].append(task)
    return [(key, groups[key]) for key in sorted(groups, key=_sort_key)]


def render_overview_svg(result: Any) -> str:
    payload = result_to_dict(result)
    tasks = normalise_tasks(payload["tasks"])
    resources = _group(tasks, "resource")
    cmax = max(_finite(payload["primary_cmax"]), max((task["end"] for task in tasks), default=0.0))
    return _svg_document(
        title=f'{payload["instance"]} — schedule overview',
        subtitle=(
            f'status={payload["status"]} · Cmax={_format_time(cmax)} · '
            f'tasks={len(tasks)} · resources={len(resources)}'
        ),
        lanes=resources,
        colour_by=lambda task: task["stage"],
        label=lambda task: f'W{task["wafer"]}:{task["stage"]}',
        max_time=cmax,
        compact=True,
    )


def render_resource_svg(result: Any) -> str:
    payload = result_to_dict(result)
    tasks = normalise_tasks(payload["tasks"])
    lanes = _group(tasks, "resource")
    cmax = max(_finite(payload["primary_cmax"]), max((task["end"] for task in tasks), default=0.0))
    return _svg_document(
        title=f'{payload["instance"]} — resource Gantt',
        subtitle="Each lane is a physical resource; colour identifies the wafer.",
        lanes=lanes,
        colour_by=lambda task: task["wafer"] if task["wafer"] is not None else task["stage"],
        label=lambda task: f'W{task["wafer"]} · {task["stage"]}',
        max_time=cmax,
    )


def render_product_svg(result: Any) -> str:
    payload = result_to_dict(result)
    tasks = normalise_tasks(payload["tasks"])
    product_tasks: List[Dict[str, Any]] = []
    for task in tasks:
        wafer_values: List[Any] = []
        if task["wafer"] is not None:
            wafer_values.append(task["wafer"])
        metadata_wafers = task.get("metadata", {}).get("wafer_ids", [])
        if isinstance(metadata_wafers, (list, tuple, set)):
            wafer_values.extend(metadata_wafers)
        for wafer in dict.fromkeys(wafer_values):
            product_tasks.append({**task, "wafer": wafer})
    lanes = _group(product_tasks, "wafer")
    cmax = max(
        _finite(payload["primary_cmax"]),
        max((task["end"] for task in tasks), default=0.0),
    )
    return _svg_document(
        title=f'{payload["instance"]} — product Gantt',
        subtitle="Each lane is a wafer; colour identifies the processing or transfer stage.",
        lanes=lanes,
        colour_by=lambda task: task["stage"],
        label=lambda task: f'{task["stage"]} · {task["resource"]}',
        max_time=cmax,
    )


def _index_html(payload: Mapping[str, Any], charts: Sequence[Mapping[str, Any]]) -> str:
    cards = []
    for chart in charts:
        cards.append(
            '<section class="card">'
            f'<h2>{_escape(chart["title"])}</h2>'
            f'<p>{_escape(chart["description"])}</p>'
            f'<a href="{_escape(chart["file"])}" target="_blank" rel="noopener">'
            f'<img src="{_escape(chart["file"])}" alt="{_escape(chart["title"])}"></a>'
            "</section>"
        )
    return (
        "<!doctype html>\n<html lang=\"en\"><head><meta charset=\"utf-8\">\n"
        '<meta name="viewport" content="width=device-width,initial-scale=1">\n'
        f"<title>{_escape(payload['instance'])} RL-SAT Gantt</title>\n"
        "<style>"
        "body{margin:0;background:#f4f7f9;color:#263238;font:14px Inter,Segoe UI,Arial,sans-serif}"
        "header{padding:24px 4vw;background:#17324d;color:#fff}"
        "header h1{margin:0 0 8px;font-size:24px}header p{margin:0;color:#d6e4f0}"
        "main{display:grid;gap:20px;padding:24px 4vw}.card{background:#fff;border-radius:10px;"
        "padding:18px;box-shadow:0 2px 10px #17324d18}.card h2{margin:0 0 6px}"
        ".card p{margin:0 0 14px;color:#607d8b}.card img{display:block;width:100%;height:auto;"
        "border:1px solid #e7ecef;background:#fff}code{background:#ffffff1f;padding:2px 5px;"
        "border-radius:4px}"
        "</style></head><body>"
        f"<header><h1>{_escape(payload['instance'])}</h1>"
        f"<p>Status <code>{_escape(payload['status'])}</code> · "
        f"Cmax <code>{_escape(_format_time(_finite(payload['primary_cmax'])))}</code> · "
        f"Solve time <code>{_escape(_format_time(_finite(payload['solving_time'])))}</code></p>"
        f"</header><main>{''.join(cards)}</main></body></html>\n"
    )


def render_gantt_bundle(result: Any, output_dir: Any) -> Dict[str, Any]:
    """Write three standalone SVGs plus ``manifest.json`` and ``index.html``."""

    payload = result_to_dict(result)
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    charts = [
        {
            "kind": "overview",
            "title": "Schedule overview",
            "description": "Compact resource-level overview, coloured by stage.",
            "file": "overview.svg",
            "content": render_overview_svg(payload),
        },
        {
            "kind": "resource",
            "title": "Resource Gantt",
            "description": "Detailed physical-resource occupancy, coloured by wafer.",
            "file": "resource.svg",
            "content": render_resource_svg(payload),
        },
        {
            "kind": "product",
            "title": "Product Gantt",
            "description": "Wafer progress across transfers and processing stages.",
            "file": "product.svg",
            "content": render_product_svg(payload),
        },
    ]
    for chart in charts:
        (destination / chart["file"]).write_text(chart.pop("content"), encoding="utf-8")

    resources = sorted({str(task["resource"]) for task in payload["tasks"]}, key=_sort_key)
    wafers = sorted(
        {str(task["wafer"]) for task in payload["tasks"] if task["wafer"] is not None},
        key=_sort_key,
    )
    manifest = {
        "format": "rl-sat-gantt-manifest-v1",
        "instance": payload["instance"],
        "status": payload["status"],
        "primary_cmax": payload["primary_cmax"],
        "solving_time": payload["solving_time"],
        "task_count": len(payload["tasks"]),
        "resources": resources,
        "wafers": wafers,
        "charts": charts,
        "index": "index.html",
    }
    (destination / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    (destination / "index.html").write_text(_index_html(payload, charts), encoding="utf-8")
    return {
        "output_dir": str(destination.resolve()),
        "manifest": str((destination / "manifest.json").resolve()),
        "index": str((destination / "index.html").resolve()),
        "charts": {
            chart["kind"]: str((destination / chart["file"]).resolve()) for chart in charts
        },
    }


# Intent-revealing alias for experiment entry points.
render_all_gantts = render_gantt_bundle


__all__ = [
    "render_all_gantts",
    "render_gantt_bundle",
    "render_overview_svg",
    "render_product_svg",
    "render_resource_svg",
]

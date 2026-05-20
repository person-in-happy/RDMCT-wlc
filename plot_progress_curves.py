from __future__ import annotations

import argparse
import csv
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple


Color = str


@dataclass(frozen=True)
class SeriesSpec:
    label: str
    candidates: Sequence[str] = ()
    color: Color = "#1f77b4"
    transform: Optional[Callable[[float], float]] = None
    derived_from: Optional[str] = None


@dataclass(frozen=True)
class PanelSpec:
    title: str
    series: Sequence[SeriesSpec]
    lower_is_better: Optional[bool] = None
    fixed_range: Optional[Tuple[Optional[float], Optional[float]]] = None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Plot convergence curves from a training progress.csv file."
    )
    parser.add_argument(
        "--progress_csv",
        type=str,
        default="",
        help="Path to progress.csv. If omitted, the latest file under --data_dir is used.",
    )
    parser.add_argument(
        "--data_dir",
        type=str,
        default="data",
        help="Directory searched for the latest progress.csv when --progress_csv is omitted.",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="",
        help="Output SVG path. Defaults to <progress_dir>/convergence_curves.svg.",
    )
    parser.add_argument(
        "--window",
        type=int,
        default=3,
        help="Moving-average window for smoothing plotted curves.",
    )
    parser.add_argument(
        "--width",
        type=int,
        default=1600,
        help="Output SVG width in pixels.",
    )
    parser.add_argument(
        "--columns",
        type=int,
        default=2,
        help="Number of dashboard columns.",
    )
    parser.add_argument(
        "--title",
        type=str,
        default="Training Convergence Dashboard",
        help="Custom dashboard title shown at the top of the SVG.",
    )
    parser.add_argument(
        "--subtitle",
        type=str,
        default="",
        help="Optional subtitle shown below the title. If omitted, the progress.csv path is shown unless --hide_source_path is set.",
    )
    parser.add_argument(
        "--hide_source_path",
        action="store_true",
        help="Hide the source progress.csv path in the SVG header.",
    )
    return parser.parse_args()


def resolve_progress_csv(progress_csv_arg: str, data_dir_arg: str) -> Path:
    if progress_csv_arg:
        progress_path = Path(progress_csv_arg).expanduser().resolve()
        if progress_path.is_dir():
            progress_path = progress_path / "progress.csv"
        if not progress_path.exists():
            raise FileNotFoundError(f"progress.csv not found: {progress_path}")
        return progress_path

    data_dir = Path(data_dir_arg).expanduser().resolve()
    candidates = sorted(data_dir.rglob("progress.csv"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not candidates:
        raise FileNotFoundError(f"No progress.csv found under {data_dir}")
    return candidates[0]


def parse_float(text: Optional[str]) -> float:
    if text is None:
        return math.nan
    stripped = text.strip()
    if not stripped:
        return math.nan
    try:
        return float(stripped)
    except ValueError:
        return math.nan


def load_progress(progress_path: Path) -> Dict[str, List[float]]:
    with progress_path.open("r", encoding="utf-8-sig", newline="") as file_obj:
        reader = csv.DictReader(file_obj)
        fieldnames = reader.fieldnames or []
        columns: Dict[str, List[float]] = {fieldname: [] for fieldname in fieldnames}
        for row in reader:
            for fieldname in fieldnames:
                columns[fieldname].append(parse_float(row.get(fieldname)))
    return columns


def get_epochs(columns: Dict[str, List[float]]) -> List[float]:
    epoch_values = columns.get("Epoch")
    if epoch_values:
        finite_epochs = [value for value in epoch_values if math.isfinite(value)]
        if finite_epochs:
            return [value if math.isfinite(value) else float(index + 1) for index, value in enumerate(epoch_values)]

    row_count = 0
    for values in columns.values():
        row_count = max(row_count, len(values))
    return [float(index + 1) for index in range(row_count)]


def moving_average(values: Sequence[float], window: int) -> List[float]:
    if window <= 1:
        return list(values)
    smoothed: List[float] = []
    for index in range(len(values)):
        left = max(0, index - window + 1)
        finite_window = [value for value in values[left : index + 1] if math.isfinite(value)]
        if finite_window:
            smoothed.append(sum(finite_window) / len(finite_window))
        else:
            smoothed.append(math.nan)
    return smoothed


def first_existing_column(columns: Dict[str, List[float]], candidates: Sequence[str]) -> Optional[str]:
    for candidate in candidates:
        if candidate in columns:
            return candidate
    return None


def derive_series(columns: Dict[str, List[float]], spec: SeriesSpec) -> Optional[Tuple[str, List[float]]]:
    if spec.derived_from is None:
        source_name = first_existing_column(columns, spec.candidates)
        if source_name is None:
            return None
        raw_values = columns[source_name]
        if spec.transform is None:
            return source_name, list(raw_values)
        return source_name, [spec.transform(value) if math.isfinite(value) else math.nan for value in raw_values]

    if spec.derived_from not in columns:
        return None
    raw_values = columns[spec.derived_from]
    if spec.transform is None:
        return spec.derived_from, list(raw_values)
    return spec.derived_from, [spec.transform(value) if math.isfinite(value) else math.nan for value in raw_values]


def build_panels() -> List[PanelSpec]:
    return [
        PanelSpec(
            title="Solving Time",
            lower_is_better=True,
            series=[
                SeriesSpec("Evaluating", ("evaluating/solving time Mean", "evaluating/Neg Solving time Mean"), "#1f77b4"),
                SeriesSpec("Online Test", ("testing/solving time Mean",), "#ff7f0e"),
                SeriesSpec("Train Env", ("training/solving_time Mean",), "#2ca02c"),
                SeriesSpec("Train Reward", ("training/Neg Reward Mean",), "#9467bd"),
            ],
        ),
        PanelSpec(
            title="B&B Nodes",
            lower_is_better=True,
            series=[
                SeriesSpec("Evaluating", ("evaluating/neg_total_nodes Mean", "evaluating/Neg Total Nodes Mean"), "#1f77b4"),
                SeriesSpec("Online Test", ("testing/neg_total_nodes Mean",), "#ff7f0e"),
                SeriesSpec("Train Env", ("training/ntotal_nodes Mean",), "#2ca02c"),
            ],
        ),
        PanelSpec(
            title="Primal-Dual Integral",
            lower_is_better=True,
            series=[
                SeriesSpec("Evaluating", ("evaluating/primaldualintegral Mean", "evaluating/PrimalDualIntegral Mean"), "#1f77b4"),
                SeriesSpec("Online Test", ("testing/primaldualintegral Mean",), "#ff7f0e"),
                SeriesSpec("Train Env", ("training/primaldualintegral Mean",), "#2ca02c"),
            ],
        ),
        PanelSpec(
            title="Primal-Dual Gap",
            lower_is_better=True,
            fixed_range=(0.0, 1.05),
            series=[
                SeriesSpec("Evaluating", ("evaluating/primal_dual_gap Mean",), "#1f77b4"),
                SeriesSpec("Online Test", ("testing/primal_dual_gap Mean",), "#ff7f0e"),
                SeriesSpec("Train Env", ("training/primal_dual_gap Mean",), "#2ca02c"),
            ],
        ),
        PanelSpec(
            title="Low-Level Entropy",
            lower_is_better=None,
            fixed_range=(0.0, None),
            series=[
                SeriesSpec("pos_1_entropy", ("pos_1_entropy",), "#d62728"),
            ],
        ),
        PanelSpec(
            title="Low-Level Advantage",
            lower_is_better=None,
            series=[
                SeriesSpec("Neg Advantage", ("training/Neg Advantage",), "#8c564b"),
            ],
        ),
        PanelSpec(
            title="Low-Level REINFORCE Loss",
            lower_is_better=None,
            series=[
                SeriesSpec("REINFORCE", ("training/reinforce loss",), "#e377c2"),
            ],
        ),
        PanelSpec(
            title="High-Level Selected Ratio",
            lower_is_better=None,
            fixed_range=(0.0, 1.0),
            series=[
                SeriesSpec(
                    "Selected Ratio",
                    color="#17becf",
                    derived_from="training_highlevel_policy/cut_percent_actions Mean",
                    transform=lambda value: 0.5 * value + 0.5,
                ),
            ],
        ),
        PanelSpec(
            title="High-Level Entropy",
            lower_is_better=None,
            fixed_range=(0.0, None),
            series=[
                SeriesSpec("Policy Entropy", ("training_highlevel_policyentropy Mean",), "#bcbd22"),
            ],
        ),
        PanelSpec(
            title="High-Level REINFORCE Loss",
            lower_is_better=None,
            series=[
                SeriesSpec("REINFORCE", ("training_highlevel_policy/reinforce loss",), "#7f7f7f"),
            ],
        ),
    ]


def format_number(value: float) -> str:
    if not math.isfinite(value):
        return "nan"
    abs_value = abs(value)
    if abs_value >= 1000:
        return f"{value:.0f}"
    if abs_value >= 100:
        return f"{value:.1f}"
    if abs_value >= 1:
        return f"{value:.2f}"
    return f"{value:.4f}"


def svg_escape(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def polyline_segments(points: Sequence[Tuple[float, float]]) -> List[List[Tuple[float, float]]]:
    if not points:
        return []
    return [list(points)]


def series_points(
    epochs: Sequence[float],
    values: Sequence[float],
    x0: float,
    y0: float,
    width: float,
    height: float,
    x_min: float,
    x_max: float,
    y_min: float,
    y_max: float,
) -> List[List[Tuple[float, float]]]:
    segments: List[List[Tuple[float, float]]] = []
    current: List[Tuple[float, float]] = []
    x_span = max(x_max - x_min, 1e-9)
    y_span = max(y_max - y_min, 1e-9)
    for epoch, value in zip(epochs, values):
        if not (math.isfinite(epoch) and math.isfinite(value)):
            if current:
                segments.append(current)
                current = []
            continue
        x = x0 + (epoch - x_min) / x_span * width
        y = y0 + height - (value - y_min) / y_span * height
        current.append((x, y))
    if current:
        segments.append(current)
    return segments


def axis_range(values: Iterable[float], fixed_range: Optional[Tuple[Optional[float], Optional[float]]]) -> Tuple[float, float]:
    finite_values = [value for value in values if math.isfinite(value)]
    if not finite_values:
        return 0.0, 1.0

    if fixed_range is not None:
        lower_bound, upper_bound = fixed_range
        y_min = min(finite_values) if lower_bound is None else lower_bound
        y_max = max(finite_values) if upper_bound is None else upper_bound
        if math.isclose(y_min, y_max):
            pad = max(abs(y_min) * 0.05, 1.0)
            return y_min - pad, y_max + pad
        return y_min, y_max

    y_min = min(finite_values)
    y_max = max(finite_values)
    if math.isclose(y_min, y_max):
        pad = max(abs(y_min) * 0.05, 1.0)
        return y_min - pad, y_max + pad
    pad = 0.08 * (y_max - y_min)
    return y_min - pad, y_max + pad


def panel_available(columns: Dict[str, List[float]], panel: PanelSpec) -> bool:
    for series_spec in panel.series:
        if derive_series(columns, series_spec) is not None:
            return True
    return False


def draw_panel(
    fragments: List[str],
    panel: PanelSpec,
    columns: Dict[str, List[float]],
    epochs: Sequence[float],
    panel_x: float,
    panel_y: float,
    panel_width: float,
    panel_height: float,
    window: int,
) -> None:
    plot_left = panel_x + 72
    plot_top = panel_y + 42
    plot_width = panel_width - 96
    plot_height = panel_height - 88
    plot_bottom = plot_top + plot_height

    resolved_series = []
    for series_spec in panel.series:
        resolved = derive_series(columns, series_spec)
        if resolved is None:
            continue
        source_name, raw_values = resolved
        smoothed_values = moving_average(raw_values, window)
        resolved_series.append((series_spec, source_name, raw_values, smoothed_values))

    if not resolved_series:
        return

    all_values: List[float] = []
    for _, _, _, smoothed_values in resolved_series:
        all_values.extend(smoothed_values)
    y_min, y_max = axis_range(all_values, panel.fixed_range)
    x_min = min(epochs) if epochs else 0.0
    x_max = max(epochs) if epochs else 1.0

    fragments.append(
        f'<rect x="{panel_x:.1f}" y="{panel_y:.1f}" width="{panel_width:.1f}" height="{panel_height:.1f}" rx="18" fill="#ffffff" stroke="#d8dee9"/>'
    )
    fragments.append(
        f'<text x="{panel_x + 20:.1f}" y="{panel_y + 24:.1f}" font-size="18" font-weight="700" fill="#17212b">{svg_escape(panel.title)}</text>'
    )
    if panel.lower_is_better is True:
        note = "lower is better"
    elif panel.lower_is_better is False:
        note = "higher is better"
    else:
        note = "monitor trend"
    fragments.append(
        f'<text x="{panel_x + 20:.1f}" y="{panel_y + 38:.1f}" font-size="11" fill="#6b7280">{svg_escape(note)}</text>'
    )

    for tick_index in range(5):
        frac = tick_index / 4.0
        y = plot_top + frac * plot_height
        tick_value = y_max - frac * (y_max - y_min)
        fragments.append(
            f'<line x1="{plot_left:.1f}" y1="{y:.1f}" x2="{plot_left + plot_width:.1f}" y2="{y:.1f}" stroke="#edf2f7" stroke-width="1"/>'
        )
        fragments.append(
            f'<text x="{plot_left - 10:.1f}" y="{y + 4:.1f}" font-size="10" text-anchor="end" fill="#6b7280">{svg_escape(format_number(tick_value))}</text>'
        )

    for tick_epoch in [x_min, (x_min + x_max) / 2.0, x_max]:
        x = plot_left if x_max == x_min else plot_left + (tick_epoch - x_min) / (x_max - x_min) * plot_width
        fragments.append(
            f'<line x1="{x:.1f}" y1="{plot_top:.1f}" x2="{x:.1f}" y2="{plot_bottom:.1f}" stroke="#f5f7fa" stroke-width="1"/>'
        )
        fragments.append(
            f'<text x="{x:.1f}" y="{plot_bottom + 18:.1f}" font-size="10" text-anchor="middle" fill="#6b7280">{svg_escape(format_number(tick_epoch))}</text>'
        )

    fragments.append(
        f'<rect x="{plot_left:.1f}" y="{plot_top:.1f}" width="{plot_width:.1f}" height="{plot_height:.1f}" fill="none" stroke="#cbd5e1"/>'
    )

    legend_x = panel_x + 20
    legend_y = panel_y + panel_height - 22
    for series_index, (series_spec, _, _, smoothed_values) in enumerate(resolved_series):
        segments = series_points(
            epochs,
            smoothed_values,
            plot_left,
            plot_top,
            plot_width,
            plot_height,
            x_min,
            x_max,
            y_min,
            y_max,
        )
        for segment in segments:
            point_text = " ".join(f"{x:.2f},{y:.2f}" for x, y in segment)
            fragments.append(
                f'<polyline points="{point_text}" fill="none" stroke="{series_spec.color}" stroke-width="2.5" stroke-linejoin="round" stroke-linecap="round"/>'
            )
            if segment:
                last_x, last_y = segment[-1]
                fragments.append(
                    f'<circle cx="{last_x:.2f}" cy="{last_y:.2f}" r="3.0" fill="{series_spec.color}" />'
                )

        latest_value = next((value for value in reversed(smoothed_values) if math.isfinite(value)), math.nan)
        fragments.append(
            f'<line x1="{legend_x:.1f}" y1="{legend_y + series_index * 16:.1f}" x2="{legend_x + 14:.1f}" y2="{legend_y + series_index * 16:.1f}" stroke="{series_spec.color}" stroke-width="3"/>'
        )
        legend_text = f"{series_spec.label}: {format_number(latest_value)}"
        fragments.append(
            f'<text x="{legend_x + 20:.1f}" y="{legend_y + 4 + series_index * 16:.1f}" font-size="11" fill="#334155">{svg_escape(legend_text)}</text>'
        )


def render_dashboard(
    progress_path: Path,
    output_path: Path,
    columns: Dict[str, List[float]],
    window: int,
    width: int,
    dashboard_columns: int,
    title: str,
    subtitle: str,
    hide_source_path: bool,
) -> Tuple[int, int]:
    epochs = get_epochs(columns)
    panels = [panel for panel in build_panels() if panel_available(columns, panel)]
    if not panels:
        raise ValueError("No supported convergence columns were found in the provided progress.csv.")

    dashboard_columns = max(1, dashboard_columns)
    panel_width = (width - 72 - 24 * (dashboard_columns - 1)) / dashboard_columns
    panel_height = 240
    dashboard_rows = math.ceil(len(panels) / dashboard_columns)
    header_lines = 2
    if subtitle:
        header_lines = 3
    elif hide_source_path:
        header_lines = 2
    else:
        header_lines = 3
    header_height = 56 + 18 * header_lines
    height = int(header_height + dashboard_rows * (panel_height + 24))

    fragments = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#f5f7fb"/>',
    ]
    fragments.append(
        f'<text x="36" y="34" font-size="26" font-weight="700" fill="#0f172a">{svg_escape(title)}</text>'
    )
    next_text_y = 56
    if subtitle:
        fragments.append(
            f'<text x="36" y="{next_text_y}" font-size="12" fill="#475569">{svg_escape(subtitle)}</text>'
        )
        next_text_y += 18
    elif not hide_source_path:
        fragments.append(
            f'<text x="36" y="{next_text_y}" font-size="12" fill="#475569">{svg_escape(str(progress_path))}</text>'
        )
        next_text_y += 18
    fragments.append(
        f'<text x="36" y="{next_text_y}" font-size="12" fill="#475569">moving-average window = {window}</text>'
    )

    for index, panel in enumerate(panels):
        row = index // dashboard_columns
        column = index % dashboard_columns
        panel_x = 36 + column * (panel_width + 24)
        panel_y = header_height + row * (panel_height + 24)
        draw_panel(
            fragments,
            panel,
            columns,
            epochs,
            panel_x,
            panel_y,
            panel_width,
            panel_height,
            max(1, window),
        )

    fragments.append("</svg>")
    output_path.write_text("\n".join(fragments), encoding="utf-8")
    return len(panels), len(epochs)


def main() -> None:
    args = parse_args()
    progress_path = resolve_progress_csv(args.progress_csv, args.data_dir)
    output_path = (
        Path(args.output).expanduser().resolve()
        if args.output
        else progress_path.with_name("convergence_curves.svg")
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    columns = load_progress(progress_path)
    panel_count, epoch_count = render_dashboard(
        progress_path=progress_path,
        output_path=output_path,
        columns=columns,
        window=max(1, args.window),
        width=max(900, args.width),
        dashboard_columns=max(1, args.columns),
        title=args.title,
        subtitle=args.subtitle,
        hide_source_path=bool(args.hide_source_path),
    )
    print(f"progress.csv: {progress_path}")
    print(f"output svg : {output_path}")
    print(f"epochs     : {epoch_count}")
    print(f"panels     : {panel_count}")


if __name__ == "__main__":
    main()

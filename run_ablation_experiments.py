import argparse
import csv
import json
import os
from datetime import datetime
from pathlib import Path

import numpy as np
import torch

from cutsel_agent_parallel import (
    CutSelectAgent,
    HeuristicBeamCutSelectAgent,
    HierarchyCutSelectAgent,
)
from environments import SCIPCutSelEnv
from petri_mip_generator import (
    PetriMIPConfig,
    generate_petri_mip_instance,
    get_petri_model_description_path,
)
from pointer_net import CutsPercentPolicy, PointerNetwork
from pointer_net_end_token import PointerNetworkEndToken
from path_utils import resolve_path
from utilss.mean_std import RunningMeanStd
from utils import set_global_seed


METHOD_ORDER = ["solver_only", "a3c_only", "beam_only", "a3c_beam"]
METHOD_DISPLAY_NAMES = {
    "solver_only": "SCIP Default",
    "a3c_only": "A3C Only",
    "beam_only": "Beam Only",
    "a3c_beam": "A3C + Beam",
}
METHOD_COLORS = {
    "solver_only": "#4C78A8",
    "a3c_only": "#F58518",
    "beam_only": "#54A24B",
    "a3c_beam": "#E45756",
}
INSTANCE_EXTENSIONS = (".lp", ".mps", ".cip")


def _str2bool(value):
    if isinstance(value, bool):
        return value
    return str(value).lower() in {"1", "true", "yes", "y"}


def _parse_args():
    parser = argparse.ArgumentParser(
        description="Run ablation experiments for default SCIP, A3C-only, beam-only, and A3C+beam."
    )
    parser.add_argument("--config_file", type=str, default="configs/petri_mip_test_config.json")
    parser.add_argument("--test_model_path", type=str, default="")
    parser.add_argument("--instance_dir", type=str, default="generated_instances/petri")
    parser.add_argument("--instance_name", type=str, default="petri_batch10_v2.lp")
    parser.add_argument("--generate_petri_instance", type=str, default="True")
    parser.add_argument("--single_instance_file", type=str, default="")
    parser.add_argument("--output_dir", type=str, default="ablation_results")
    parser.add_argument("--instance_type", type=str, default="petri_transfer")
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--scip_seed", type=int, default=1)
    parser.add_argument("--sel_cuts_percent", type=float, default=0.2)
    parser.add_argument("--policy_type", type=str, default="with_token")
    parser.add_argument("--use_cutsel_percent_policy", type=str, default="True")
    parser.add_argument("--a3c_decode_type", type=str, default="greedy")
    parser.add_argument("--a3c_beam_decode_type", type=str, default="beam_search")
    parser.add_argument("--heuristic_beam_size", type=int, default=3)
    parser.add_argument("--heuristic_redundancy_weight", type=float, default=0.15)
    parser.add_argument("--time_limit", type=float, default=-1.0)
    parser.add_argument("--num_batches", type=int, default=10)
    parser.add_argument("--num_pm", type=int, default=2)
    parser.add_argument("--num_steps", type=int, default=13)
    parser.add_argument("--total_wafers", type=int, default=40)
    parser.add_argument("--pec_pool_size", type=int, default=40)
    parser.add_argument("--mode_sequence", type=str, default="")
    return parser.parse_args()


def _resolve_runtime_args(args):
    args.config_file = str(resolve_path(args.config_file))
    args.instance_dir = str(resolve_path(args.instance_dir))
    args.output_dir = str(resolve_path(args.output_dir))
    if args.test_model_path:
        args.test_model_path = str(resolve_path(args.test_model_path))
    if args.single_instance_file:
        single_path = Path(args.single_instance_file)
        if single_path.is_absolute() or single_path.parent != Path("."):
            args.single_instance_file = str(resolve_path(args.single_instance_file))
    instance_name_path = Path(args.instance_name)
    if instance_name_path.parent != Path("."):
        resolved_instance_path = resolve_path(args.instance_name)
        args.instance_dir = str(resolved_instance_path.parent)
        args.instance_name = resolved_instance_path.name
    return args


def _load_config(config_file):
    with open(config_file, "r", encoding="utf-8") as f:
        return json.load(f)


def _ensure_instance(args):
    if _str2bool(args.generate_petri_instance):
        requested_instance_name = args.instance_name
        cfg = PetriMIPConfig(
            num_batches=args.num_batches,
            num_pm=args.num_pm,
            num_steps=args.num_steps,
            total_wafers=args.total_wafers,
            pec_pool_size=args.pec_pool_size,
            mode_sequence=args.mode_sequence,
        )
        lp_path = generate_petri_mip_instance(args.instance_dir, args.instance_name, cfg)
        generated_instance_name = Path(lp_path).name
        args.instance_name = generated_instance_name
        if not args.single_instance_file or args.single_instance_file == requested_instance_name:
            args.single_instance_file = generated_instance_name
        return lp_path
    return os.path.join(args.instance_dir, args.instance_name)


def _get_instance_list(instance_dir, single_instance_file):
    if single_instance_file:
        return [single_instance_file]
    return sorted(
        f_name
        for f_name in os.listdir(instance_dir)
        if f_name.endswith(INSTANCE_EXTENSIONS)
    )


def _load_policy_bundle(cfg, args):
    if not args.test_model_path:
        return None
    if not os.path.isfile(args.test_model_path):
        raise FileNotFoundError(f"test_model_path does not exist: {args.test_model_path}")

    policy_type = args.policy_type
    Pointer = PointerNetworkEndToken if policy_type == "with_token" else PointerNetwork

    net_share_kwargs = cfg["net_share"]
    policy_kwargs = cfg["policy"]
    value_kwargs = cfg["value"]
    use_high_level = _str2bool(args.use_cutsel_percent_policy)

    if torch.cuda.is_available():
        device_str = cfg["devices"]["global_device"]
    else:
        device_str = "cpu"
    device = torch.device(device_str)

    state_dict = torch.load(args.test_model_path, map_location=device)

    policy = Pointer(
        embedding_dim=net_share_kwargs["embedding_dim"],
        hidden_dim=net_share_kwargs["hidden_dim"],
        n_glimpses=policy_kwargs["n_glimpses"],
        tanh_exploration=net_share_kwargs["tanh_exploration"],
        use_tanh=net_share_kwargs["use_tanh"],
        beam_size=policy_kwargs["beam_size"],
        use_cuda=torch.cuda.is_available(),
    ).to(device)
    policy.load_state_dict(state_dict["pointer_net"])
    policy.eval()

    mean_std = None
    if "mean" in state_dict and "std" in state_dict:
        feature_shape = (policy.embedding_dim,)
        mean_std = RunningMeanStd(feature_shape)
        mean_std.set_mean_std(state_dict["mean"], state_dict["std"])

    cutsel_percent_policy = None
    if use_high_level:
        cutsel_percent_policy = CutsPercentPolicy(
            embedding_dim=net_share_kwargs["embedding_dim"],
            hidden_dim=net_share_kwargs["hidden_dim"],
            n_process_block_iters=value_kwargs["n_process_block_iters"],
            tanh_exploration=net_share_kwargs["tanh_exploration"],
            use_tanh=net_share_kwargs["use_tanh"],
            use_cuda=torch.cuda.is_available(),
        ).to(device)
        cutsel_percent_policy.load_state_dict(state_dict["cutsel_percent_net"])
        cutsel_percent_policy.eval()

    return {
        "policy": policy,
        "cutsel_percent_policy": cutsel_percent_policy,
        "mean_std": mean_std,
        "device_str": device_str,
        "policy_type": policy_type,
        "beam_size": policy_kwargs["beam_size"],
        "model_path": args.test_model_path,
        "use_high_level": use_high_level,
    }


def _build_env_kwargs(cfg, args):
    env_kwargs = dict(cfg["env"])
    env_kwargs.pop("instance_file_path", None)
    env_kwargs.pop("single_instance_file", None)
    if args.time_limit > 0:
        env_kwargs["scip_time_limit"] = args.time_limit
    return env_kwargs


def _build_method_hyperparams(method_name, cfg, args, policy_bundle=None):
    env_kwargs = cfg["env"]
    base = {
        "method": method_name,
        "seed": args.seed,
        "scip_seed": args.scip_seed,
        "scip_time_limit": args.time_limit if args.time_limit > 0 else env_kwargs["scip_time_limit"],
        "presolving": env_kwargs["presolving"],
        "separating": env_kwargs["separating"],
        "conflict": env_kwargs["conflict"],
        "heuristics": env_kwargs["heuristics"],
        "sel_cuts_percent": args.sel_cuts_percent,
        "policy_type": args.policy_type,
    }
    if method_name == "solver_only":
        base["solver"] = "SCIP default cut selection"
    elif method_name == "a3c_only":
        base.update(
            {
                "decode_type": args.a3c_decode_type,
                "model_path": policy_bundle["model_path"],
                "beam_size": policy_bundle["beam_size"],
                "use_cutsel_percent_policy": policy_bundle["use_high_level"],
            }
        )
    elif method_name == "beam_only":
        base.update(
            {
                "decode_type": "heuristic_beam",
                "heuristic_beam_size": args.heuristic_beam_size,
                "heuristic_redundancy_weight": args.heuristic_redundancy_weight,
                "score_weights": {
                    "obj_parallelism": 0.15,
                    "efficacy": 0.35,
                    "support_penalty": 0.10,
                    "integral_support": 0.15,
                    "violation": 0.25,
                },
            }
        )
    elif method_name == "a3c_beam":
        base.update(
            {
                "decode_type": args.a3c_beam_decode_type,
                "model_path": policy_bundle["model_path"],
                "beam_size": policy_bundle["beam_size"],
                "use_cutsel_percent_policy": policy_bundle["use_high_level"],
            }
        )
    return base


def _run_solver_only(instance_dir, instance_file, env_kwargs, args):
    env = SCIPCutSelEnv(instance_dir, args.scip_seed, args.seed, single_instance_file=instance_file, **env_kwargs)
    env.reset()
    return env.solve_default()


def _build_rl_agent(env, policy_bundle, args, decode_type):
    if policy_bundle["use_high_level"]:
        return HierarchyCutSelectAgent(
            env.m,
            policy_bundle["policy"],
            policy_bundle["cutsel_percent_policy"],
            None,
            args.sel_cuts_percent,
            policy_bundle["device_str"],
            decode_type,
            policy_bundle["mean_std"],
            policy_bundle["policy_type"],
        )
    return CutSelectAgent(
        env.m,
        policy_bundle["policy"],
        None,
        args.sel_cuts_percent,
        policy_bundle["device_str"],
        decode_type,
        policy_bundle["mean_std"],
        policy_bundle["policy_type"],
    )


def _run_with_agent(instance_dir, instance_file, env_kwargs, args, agent_builder):
    env = SCIPCutSelEnv(instance_dir, args.scip_seed, args.seed, single_instance_file=instance_file, **env_kwargs)
    env.reset()
    agent = agent_builder(env)
    return env.step(agent)


def _run_beam_only(instance_dir, instance_file, env_kwargs, args):
    def _builder(env):
        return HeuristicBeamCutSelectAgent(
            env.m,
            sel_cuts_percent=args.sel_cuts_percent,
            beam_size=args.heuristic_beam_size,
            redundancy_weight=args.heuristic_redundancy_weight,
        )

    return _run_with_agent(instance_dir, instance_file, env_kwargs, args, _builder)


def _run_a3c_only(instance_dir, instance_file, env_kwargs, args, policy_bundle):
    return _run_with_agent(
        instance_dir,
        instance_file,
        env_kwargs,
        args,
        lambda env: _build_rl_agent(env, policy_bundle, args, args.a3c_decode_type),
    )


def _run_a3c_beam(instance_dir, instance_file, env_kwargs, args, policy_bundle):
    return _run_with_agent(
        instance_dir,
        instance_file,
        env_kwargs,
        args,
        lambda env: _build_rl_agent(env, policy_bundle, args, args.a3c_beam_decode_type),
    )


def _safe_float(value):
    if value is None:
        return None
    try:
        return float(value)
    except Exception:
        return None


def _format_instance_result(method_name, instance_file, stats, hyperparams, error=None):
    solution = {}
    if stats is not None:
        solution = stats.get("solution", {})
    return {
        "method": method_name,
        "instance": instance_file,
        "status": None if stats is None else stats.get("status"),
        "solving_time": None if stats is None else _safe_float(stats.get("solving_time")),
        "best_obj": None if stats is None else _safe_float(stats.get("best_obj")),
        "ntotal_nodes": None if stats is None else _safe_float(stats.get("ntotal_nodes")),
        "primal_dual_gap": None if stats is None else _safe_float(stats.get("primal_dual_gap")),
        "primaldualintegral": None if stats is None else _safe_float(stats.get("primaldualintegral")),
        "nonzero_solution_vars": len(solution),
        "solution": solution,
        "hyperparameters": hyperparams,
        "error": error,
    }


def _valid_metric_values(rows, key):
    values = []
    for row in rows:
        value = row.get(key)
        if value is None:
            continue
        try:
            value = float(value)
        except Exception:
            continue
        if np.isfinite(value):
            values.append(value)
    return values


def _aggregate_results(results):
    summary = {}
    for method_name, method_results in results.items():
        valid = [r for r in method_results if r["error"] is None and r["solving_time"] is not None]
        solving_times = _valid_metric_values(valid, "solving_time")
        best_objs = _valid_metric_values(valid, "best_obj")
        total_nodes = _valid_metric_values(valid, "ntotal_nodes")
        primal_dual_gaps = _valid_metric_values(valid, "primal_dual_gap")
        primal_dual_integrals = _valid_metric_values(valid, "primaldualintegral")
        nonzero_solution_vars = _valid_metric_values(valid, "nonzero_solution_vars")
        summary[method_name] = {
            "num_instances": len(method_results),
            "num_valid": len(valid),
            "mean_solving_time": None if not solving_times else float(np.mean(solving_times)),
            "mean_best_obj": None if not best_objs else float(np.mean(best_objs)),
            "mean_ntotal_nodes": None if not total_nodes else float(np.mean(total_nodes)),
            "mean_primal_dual_gap": None if not primal_dual_gaps else float(np.mean(primal_dual_gaps)),
            "mean_primaldualintegral": None if not primal_dual_integrals else float(np.mean(primal_dual_integrals)),
            "mean_nonzero_solution_vars": None if not nonzero_solution_vars else float(np.mean(nonzero_solution_vars)),
        }
    return summary


def _format_display_value(value):
    if value is None:
        return "n/a"
    try:
        value = float(value)
    except Exception:
        return str(value)
    if not np.isfinite(value):
        return "n/a"
    abs_value = abs(value)
    if abs_value >= 1000:
        return f"{value:,.2f}"
    if abs_value >= 100:
        return f"{value:.2f}"
    if abs_value >= 1:
        return f"{value:.3f}"
    return f"{value:.4f}"


def _escape_svg(text):
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _flatten_results(results):
    flat = []
    for method_name in METHOD_ORDER:
        for row in results.get(method_name, []):
            if "method" not in row:
                flat.append({**row, "method": method_name})
            else:
                flat.append(row)
    return flat


def _render_metric_chart(parts, x, y, width, title, metric_key, summary):
    methods = [method_name for method_name in METHOD_ORDER if method_name in summary]
    values = [summary[method_name].get(metric_key) for method_name in methods]
    valid_values = [value for value in values if value is not None and np.isfinite(value)]
    max_value = max(valid_values) if valid_values else 1.0
    row_height = 38
    label_width = 150
    value_width = 160
    plot_x = x + label_width
    plot_width = max(width - label_width - value_width, 120)
    chart_height = 50 + len(methods) * row_height

    parts.append(f'<text x="{x:.2f}" y="{y:.2f}" font-size="18" font-weight="700" fill="#222">{title}</text>')
    parts.append(
        f'<text x="{x:.2f}" y="{y + 22:.2f}" font-size="11" fill="#666">Lower is better. Values are means over valid runs.</text>'
    )
    for idx, method_name in enumerate(methods):
        row_y = y + 46 + idx * row_height
        value = values[idx]
        fill_width = 0.0 if value is None or not np.isfinite(value) else plot_width * (value / max_value if max_value > 0 else 0.0)
        parts.append(
            f'<text x="{x:.2f}" y="{row_y + 13:.2f}" font-size="13" font-weight="600" fill="#2b2b2b">{METHOD_DISPLAY_NAMES[method_name]}</text>'
        )
        parts.append(
            f'<rect x="{plot_x:.2f}" y="{row_y:.2f}" width="{plot_width:.2f}" height="18" rx="9" fill="#EEF1F5"/>'
        )
        if fill_width > 0:
            parts.append(
                f'<rect x="{plot_x:.2f}" y="{row_y:.2f}" width="{fill_width:.2f}" height="18" rx="9" fill="{METHOD_COLORS[method_name]}"/>'
            )
        parts.append(
            f'<text x="{plot_x + plot_width + 10:.2f}" y="{row_y + 13:.2f}" font-size="12" fill="#404040">{_format_display_value(value)} ({summary[method_name]["num_valid"]}/{summary[method_name]["num_instances"]})</text>'
        )
    return chart_height


def _write_comparison_svg(path, summary, meta):
    width = 1780
    left_x = 42
    panel_width = 828
    right_x = left_x + panel_width + 40
    top_y = 132

    left_panel_charts = [
        ("Mean Solving Time", "mean_solving_time"),
        ("Mean Total Nodes", "mean_ntotal_nodes"),
    ]
    right_panel_charts = [
        ("Mean Best Objective", "mean_best_obj"),
        ("Mean Primal-Dual Gap", "mean_primal_dual_gap"),
    ]

    panel_padding_x = 28
    panel_title_y = 40
    panel_gap = 36

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="760" viewBox="0 0 {width} 760">',
        '<rect x="0" y="0" width="1780" height="760" fill="#FFFFFF"/>',
        '<text x="42" y="42" font-size="28" font-weight="700" fill="#202020">Ablation Comparison</text>',
        f'<text x="42" y="72" font-size="14" fill="#565656">Instance directory: {_escape_svg(meta.get("instance_dir", ""))}</text>',
        f'<text x="42" y="96" font-size="14" fill="#565656">Instances: {len(meta.get("instance_files", []))} | Comparison covers efficiency and solution quality.</text>',
        f'<rect x="{left_x}" y="{top_y}" width="{panel_width}" height="560" rx="18" fill="#F8FBFF" stroke="#D6E3F3"/>',
        f'<rect x="{right_x}" y="{top_y}" width="{panel_width}" height="560" rx="18" fill="#FFF9F4" stroke="#F1DFC9"/>',
        f'<text x="{left_x + panel_padding_x}" y="{top_y + panel_title_y}" font-size="22" font-weight="700" fill="#1F3B63">Algorithm Efficiency</text>',
        f'<text x="{right_x + panel_padding_x}" y="{top_y + panel_title_y}" font-size="22" font-weight="700" fill="#7B4A12">Solution Quality</text>',
    ]

    current_y = top_y + 86
    for title, metric_key in left_panel_charts:
        current_y += _render_metric_chart(parts, left_x + panel_padding_x, current_y, panel_width - 2 * panel_padding_x, title, metric_key, summary) + panel_gap

    current_y = top_y + 86
    for title, metric_key in right_panel_charts:
        current_y += _render_metric_chart(parts, right_x + panel_padding_x, current_y, panel_width - 2 * panel_padding_x, title, metric_key, summary) + panel_gap

    parts.append(
        '<text x="42" y="730" font-size="12" fill="#666">Every metric uses its own bar scale to keep labels readable and prevent overlap.</text>'
    )
    parts.append("</svg>")

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(parts))


def _write_json(path, payload):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def _write_csv(path, results):
    fieldnames = [
        "method",
        "instance",
        "status",
        "solving_time",
        "best_obj",
        "ntotal_nodes",
        "primal_dual_gap",
        "primaldualintegral",
        "nonzero_solution_vars",
        "error",
        "hyperparameters",
    ]
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for method_results in results.values():
            for row in method_results:
                writer.writerow(
                    {
                        **{key: row[key] for key in fieldnames if key not in {"hyperparameters"}},
                        "hyperparameters": json.dumps(row["hyperparameters"], ensure_ascii=False),
                    }
                )


def _write_markdown(path, results, summary, meta):
    lines = []
    lines.append("# Ablation Results")
    lines.append("")
    lines.append("## Setup")
    lines.append("")
    lines.append(f"- Instance directory: `{meta['instance_dir']}`")
    lines.append(f"- Instance files: `{', '.join(meta['instance_files'])}`")
    lines.append(f"- Model path: `{meta['model_path']}`")
    lines.append(f"- Generated MIP: `{meta['generated_lp']}`")
    lines.append(f"- Model description: `{meta['model_description']}`")
    if meta.get("comparison_svg"):
        lines.append(f"- Comparison SVG: `{meta['comparison_svg']}`")
    if meta.get("gantt_dir"):
        lines.append(f"- Gantt directory: `{meta['gantt_dir']}`")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append("| Method | Mean Time | Mean Nodes | Mean Best Obj | Mean Gap | Mean Nonzero Vars | Valid Runs |")
    lines.append("| --- | ---: | ---: | ---: | ---: | ---: | ---: |")
    for method_name in METHOD_ORDER:
        if method_name not in summary:
            continue
        item = summary[method_name]
        lines.append(
            f"| {method_name} | {_format_display_value(item['mean_solving_time'])} | "
            f"{_format_display_value(item['mean_ntotal_nodes'])} | {_format_display_value(item['mean_best_obj'])} | "
            f"{_format_display_value(item['mean_primal_dual_gap'])} | {_format_display_value(item['mean_nonzero_solution_vars'])} | "
            f"{item['num_valid']}/{item['num_instances']} |"
        )
    lines.append("")
    lines.append("## Per-Instance Results")
    lines.append("")
    lines.append("| Method | Instance | Status | Time | Best Obj | Nodes | Gap | Nonzero Vars | Error |")
    lines.append("| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | --- |")
    for method_name in METHOD_ORDER:
        for row in results.get(method_name, []):
            lines.append(
                f"| {row['method']} | {row['instance']} | {row['status']} | {_format_display_value(row['solving_time'])} | "
                f"{_format_display_value(row['best_obj'])} | {_format_display_value(row['ntotal_nodes'])} | "
                f"{_format_display_value(row['primal_dual_gap'])} | {row['nonzero_solution_vars']} | {row['error']} |"
            )
    lines.append("")
    lines.append("## Hyperparameters")
    lines.append("")
    for method_name in METHOD_ORDER:
        method_results = results.get(method_name, [])
        lines.append(f"### {method_name}")
        lines.append("")
        if method_results:
            hyper = method_results[0]["hyperparameters"]
            for key, value in hyper.items():
                lines.append(f"- `{key}`: `{value}`")
        lines.append("")
    lines.append("## Solutions")
    lines.append("")
    lines.append("Full variable assignments are stored in the JSON output.")
    lines.append("")

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def main():
    args = _resolve_runtime_args(_parse_args())
    cfg = _load_config(args.config_file)
    set_global_seed(args.seed)

    os.makedirs(args.instance_dir, exist_ok=True)
    os.makedirs(args.output_dir, exist_ok=True)

    generated_lp = _ensure_instance(args)
    model_description = get_petri_model_description_path(args.instance_dir, args.instance_name)

    instance_file = args.single_instance_file or args.instance_name
    instance_files = _get_instance_list(args.instance_dir, instance_file)
    if not instance_files:
        raise ValueError(f"No instance files found in {args.instance_dir}")

    env_kwargs = _build_env_kwargs(cfg, args)
    policy_bundle = _load_policy_bundle(cfg, args) if args.test_model_path else None

    experiment_results = {
        "solver_only": [],
        "a3c_only": [],
        "beam_only": [],
        "a3c_beam": [],
    }

    for instance_name in instance_files:
        solver_hyper = _build_method_hyperparams("solver_only", cfg, args)
        try:
            stats = _run_solver_only(args.instance_dir, instance_name, env_kwargs, args)
            experiment_results["solver_only"].append(
                _format_instance_result("solver_only", instance_name, stats, solver_hyper)
            )
        except Exception as exc:
            experiment_results["solver_only"].append(
                _format_instance_result("solver_only", instance_name, None, solver_hyper, error=str(exc))
            )

        beam_hyper = _build_method_hyperparams("beam_only", cfg, args)
        try:
            stats = _run_beam_only(args.instance_dir, instance_name, env_kwargs, args)
            experiment_results["beam_only"].append(
                _format_instance_result("beam_only", instance_name, stats, beam_hyper)
            )
        except Exception as exc:
            experiment_results["beam_only"].append(
                _format_instance_result("beam_only", instance_name, None, beam_hyper, error=str(exc))
            )

        for method_name, runner in (
            ("a3c_only", _run_a3c_only),
            ("a3c_beam", _run_a3c_beam),
        ):
            if policy_bundle is None:
                hyper = _build_method_hyperparams(
                    method_name,
                    cfg,
                    args,
                    {
                        "model_path": None,
                        "beam_size": cfg["policy"]["beam_size"],
                        "use_high_level": _str2bool(args.use_cutsel_percent_policy),
                    },
                )
                experiment_results[method_name].append(
                    _format_instance_result(
                        method_name,
                        instance_name,
                        None,
                        hyper,
                        error="skipped: test_model_path not provided",
                    )
                )
                continue

            hyper = _build_method_hyperparams(method_name, cfg, args, policy_bundle)
            try:
                stats = runner(args.instance_dir, instance_name, env_kwargs, args, policy_bundle)
                experiment_results[method_name].append(
                    _format_instance_result(method_name, instance_name, stats, hyper)
                )
            except Exception as exc:
                experiment_results[method_name].append(
                    _format_instance_result(method_name, instance_name, None, hyper, error=str(exc))
                )

    summary = _aggregate_results(experiment_results)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    prefix = f"ablation_{args.instance_type}_{timestamp}"
    json_path = os.path.join(args.output_dir, f"{prefix}.json")
    csv_path = os.path.join(args.output_dir, f"{prefix}.csv")
    md_path = os.path.join(args.output_dir, f"{prefix}.md")
    comparison_svg = os.path.join(args.output_dir, f"{prefix}_comparison.svg")
    gantt_dir = os.path.join(args.output_dir, f"{prefix}_gantt")

    _write_comparison_svg(
        comparison_svg,
        summary,
        {
            "instance_dir": args.instance_dir,
            "instance_files": instance_files,
        },
    )

    generated_gantt = []
    gantt_error = None
    try:
        from petri_gantt import generate_gantt_charts_from_records

        generated_gantt = generate_gantt_charts_from_records(_flatten_results(experiment_results), gantt_dir)
    except Exception as exc:
        gantt_error = str(exc)

    payload = {
        "meta": {
            "instance_dir": args.instance_dir,
            "instance_files": instance_files,
            "model_path": args.test_model_path,
            "generated_lp": generated_lp,
            "model_description": model_description,
            "comparison_svg": comparison_svg,
            "gantt_dir": gantt_dir if generated_gantt else "",
        },
        "summary": summary,
        "results": experiment_results,
        "artifacts": {
            "comparison_svg": comparison_svg,
            "gantt_outputs": generated_gantt,
            "gantt_error": gantt_error,
        },
    }
    _write_json(json_path, payload)
    _write_csv(csv_path, experiment_results)
    _write_markdown(md_path, experiment_results, summary, payload["meta"])

    print(f"Ablation JSON: {json_path}")
    print(f"Ablation CSV: {csv_path}")
    print(f"Ablation Markdown: {md_path}")
    print(f"Ablation Comparison SVG: {comparison_svg}")
    if generated_gantt:
        print(f"Ablation Gantt directory: {gantt_dir}")
    if gantt_error:
        print(f"Ablation Gantt warning: {gantt_error}")


if __name__ == "__main__":
    main()

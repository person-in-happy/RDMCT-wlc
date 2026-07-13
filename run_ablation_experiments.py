import argparse
import csv
import hashlib
import json
import os
import re
import time
from datetime import datetime
from pathlib import Path

from runtime_compat import configure_openmp_runtime

configure_openmp_runtime()

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
from petri_warm_start import find_compatible_mixed_warm_start, write_mixed_warm_start
from pointer_net import CutsPercentPolicy, PointerNetwork
from pointer_net_end_token import PointerNetworkEndToken
from path_utils import is_latest_keyword, latest_matching_file, resolve_path
from global_const import (
    validate_checkpoint_feature_schema,
    validate_checkpoint_postprocessor_schema,
)
from utilss.mean_std import RunningMeanStd
from utils import set_global_seed


METHOD_ORDER = ["solver_only", "a3c_only", "beam_only", "a3c_beam"]
METHOD_DISPLAY_NAMES = {
    "solver_only": "SCIP Default",
    "a3c_only": "A3C Only",
    "beam_only": "Structure Rerank Only",
    "a3c_beam": "A3C + Structure Rerank",
}
METHOD_COLORS = {
    "solver_only": "#4C78A8",
    "a3c_only": "#F58518",
    "beam_only": "#54A24B",
    "a3c_beam": "#E45756",
}
INSTANCE_EXTENSIONS = (".lp", ".mps", ".cip")
NO_INCUMBENT_GAP_THRESHOLD = 1e19


def _str2bool(value):
    if isinstance(value, bool):
        return value
    return str(value).lower() in {"1", "true", "yes", "y"}


def _parse_args():
    parser = argparse.ArgumentParser(
        description="Run a fair ablation of SCIP, A3C, structure-only, and A3C + structure reranking."
    )
    parser.add_argument("--config_file", type=str, default="configs/petri_mip_test_config.json")
    parser.add_argument("--test_model_path", type=str, default="")
    parser.add_argument("--instance_dir", type=str, default="generated_instances/petri")
    parser.add_argument("--instance_name", type=str, default="petri_batch10_fullflow_v7.lp")
    parser.add_argument("--generate_petri_instance", type=str, default="True")
    parser.add_argument("--single_instance_file", type=str, default="")
    parser.add_argument(
        "--all_instances",
        type=str,
        default="False",
        help="Evaluate every LP/MPS/CIP in instance_dir; use this for formal multi-instance evidence.",
    )
    parser.add_argument("--output_dir", type=str, default="ablation_results")
    parser.add_argument("--instance_type", type=str, default="petri_transfer")
    parser.add_argument(
        "--methods",
        type=str,
        default=",".join(METHOD_ORDER),
        help="Comma-separated subset used for diagnostic reruns.",
    )
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--scip_seed", type=int, default=1)
    parser.add_argument("--sel_cuts_percent", type=float, default=0.2)
    parser.add_argument("--policy_type", type=str, default="with_token")
    parser.add_argument("--use_cutsel_percent_policy", type=str, default="True")
    parser.add_argument("--a3c_decode_type", type=str, default="greedy")
    parser.add_argument(
        "--a3c_beam_decode_type",
        type=str,
        default="greedy",
        help="Decode type for A3C + structure rerank; greedy avoids beam callback overruns.",
    )
    parser.add_argument("--a3c_max_candidates", type=int, default=128)
    parser.add_argument("--a3c_max_selected_cuts", type=int, default=30)
    parser.add_argument("--proposed_max_candidates", type=int, default=128)
    parser.add_argument("--proposed_max_selected_cuts", type=int, default=30)
    parser.add_argument("--heuristic_beam_size", type=int, default=3)
    parser.add_argument("--heuristic_redundancy_weight", type=float, default=0.15)
    parser.add_argument("--heuristic_max_candidates", type=int, default=128)
    parser.add_argument("--heuristic_max_selected_cuts", type=int, default=30)
    parser.add_argument(
        "--enforce_fair_ablation",
        type=str,
        default="True",
        help=(
            "Require A3C-only, structure-only, and the proposed method to use "
            "the same candidate/selection budgets and learned decode type."
        ),
    )
    parser.add_argument(
        "--validate_instance_label",
        type=str,
        default="True",
        help="Reject project labels such as _41 or _22 when model semantics disagree.",
    )
    parser.add_argument(
        "--allow_duplicate_instances",
        type=str,
        default="False",
        help="Allow byte-identical instances in an all-instances run (not recommended).",
    )
    parser.add_argument(
        "--allow_instance_overwrite",
        type=str,
        default="False",
        help="Allow generation to overwrite an existing LP with the same name.",
    )
    parser.add_argument("--time_limit", type=float, default=-1.0)
    parser.add_argument(
        "--evaluation_node_limit",
        type=int,
        default=-1,
        help="Common SCIP node limit for ablation; -1 disables node-based stopping.",
    )
    parser.add_argument(
        "--evaluation_stall_node_limit",
        type=int,
        default=-1,
        help=(
            "Common SCIP stall-node limit for ablation; -1 disables it so "
            "time-to-optimal is not confused with time-to-stall-limit."
        ),
    )
    parser.add_argument(
        "--warm_start_time_limit",
        type=float,
        default=180.0,
        help="Build one shared feasible Petri start for every ablation method; 0 disables generation.",
    )
    parser.add_argument(
        "--warm_start_solution_file",
        type=str,
        default="",
        help="Existing SCIP .sol file shared by every method.",
    )
    parser.add_argument("--num_batches", type=int, default=10)
    parser.add_argument("--num_pm", type=int, default=2)
    parser.add_argument("--num_steps", type=int, default=13)
    parser.add_argument("--total_wafers", type=int, default=0)
    parser.add_argument("--mode_4x1_wafers", type=int, default=20)
    parser.add_argument("--mode_2x2_wafers", type=int, default=20)
    parser.add_argument("--pec_pool_size", type=int, default=40)
    parser.add_argument("--cleaning_interval", type=int, default=10)
    parser.add_argument("--cleaning_process_time", type=float, default=0.0)
    parser.add_argument("--process_mode", type=str, default="auto")
    parser.add_argument("--mode_sequence", type=str, default="")
    parser.add_argument("--wafer_mode_map", "--wafer_modes", dest="wafer_mode_map", type=str, default="")
    parser.add_argument("--default_wafer_mode", type=str, default="")
    parser.add_argument("--chamber_idle_penalty", type=float, default=1e-4)
    parser.add_argument("--post_process_wait_penalty", type=float, default=0.05)
    parser.add_argument("--ll_wait_penalty", type=float, default=1e-4)
    parser.add_argument("--chamber_nonprocess_wait_square_penalty", type=float, default=1e-2)
    parser.add_argument("--schedule_chamber_idle_square_penalty", "--chamber_idle_square_penalty", dest="schedule_chamber_idle_square_penalty", type=float, default=1e-5)
    parser.add_argument("--atr_capacity", type=int, default=2)
    parser.add_argument("--vtr_capacity", type=int, default=4)
    parser.add_argument("--schedule_pm_wait_square_penalty", "--pm_wait_square_penalty", dest="schedule_pm_wait_square_penalty", type=float, default=1e-3)
    parser.add_argument("--schedule_module_wait_square_penalty", "--module_wait_square_penalty", dest="schedule_module_wait_square_penalty", type=float, default=1e-5)
    parser.add_argument("--schedule_robot_wait_square_penalty", "--robot_wait_square_penalty", dest="schedule_robot_wait_square_penalty", type=float, default=1e-5)
    return parser.parse_args()


def _resolve_runtime_args(args):
    args.config_file = str(resolve_path(args.config_file))
    args.instance_dir = str(resolve_path(args.instance_dir))
    args.output_dir = str(resolve_path(args.output_dir))
    if args.test_model_path:
        if is_latest_keyword(args.test_model_path):
            args.test_model_path = str(latest_matching_file("data", "params.pkl", "trained params.pkl"))
        else:
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


def _validate_ablation_protocol(args):
    if not _str2bool(args.enforce_fair_ablation):
        return
    budgets = {
        "a3c_only": (args.a3c_max_candidates, args.a3c_max_selected_cuts),
        "structure_only": (
            args.heuristic_max_candidates,
            args.heuristic_max_selected_cuts,
        ),
        "proposed": (
            args.proposed_max_candidates,
            args.proposed_max_selected_cuts,
        ),
    }
    if len(set(budgets.values())) != 1:
        readable = ", ".join(
            f"{name}={candidate}/{selected}"
            for name, (candidate, selected) in budgets.items()
        )
        raise ValueError(
            "Unfair cut budgets would confound the ablation: "
            f"{readable}. Set all three candidate/selected pairs equal, or "
            "explicitly pass --enforce_fair_ablation False for a non-ablation run."
        )
    if args.a3c_decode_type != args.a3c_beam_decode_type:
        raise ValueError(
            "A3C-only and A3C + structure rerank use different learned decode "
            f"types ({args.a3c_decode_type!r} vs {args.a3c_beam_decode_type!r}). "
            "Use the same decode type so the measured difference isolates the "
            "structure reranker. Greedy is recommended for wall-time evaluation."
        )


def _selected_methods(args):
    selected = []
    for name in str(args.methods).split(","):
        name = name.strip()
        if not name:
            continue
        if name not in METHOD_ORDER:
            raise ValueError(
                f"Unknown ablation method {name!r}; choose from {METHOD_ORDER}."
            )
        if name not in selected:
            selected.append(name)
    if not selected:
        raise ValueError("--methods selected no ablation methods")
    return selected


def _label_expected_mode(instance_name):
    tokens = set(
        token
        for token in re.split(r"[^a-z0-9x]+", Path(instance_name).stem.lower())
        if token
    )
    if "41" in tokens or "4x1" in tokens:
        return "4x1"
    if "22" in tokens or "2x2" in tokens:
        return "2x2"
    return None


def _validate_mode_label(instance_name, full_count, mix_count, source):
    expected = _label_expected_mode(instance_name)
    if expected == "4x1" and not (full_count > 0 and mix_count == 0):
        raise ValueError(
            f"Instance label/semantics mismatch for {instance_name}: label means "
            f"pure 4x1, but {source} says 4x1={full_count}, 2x2={mix_count}."
        )
    if expected == "2x2" and not (mix_count > 0 and full_count == 0):
        raise ValueError(
            f"Instance label/semantics mismatch for {instance_name}: label means "
            f"pure 2x2, but {source} says 4x1={full_count}, 2x2={mix_count}."
        )


def _read_mode_signature(model_description):
    description_path = Path(model_description)
    if not description_path.is_file():
        return None
    text = description_path.read_text(encoding="utf-8")
    full_match = re.search(r"- `4x1` wafers: `(\d+)`", text)
    mix_match = re.search(r"- `2x2` wafers: `(\d+)`", text)
    if not full_match or not mix_match:
        return None
    return {
        "mode_4x1_wafers": int(full_match.group(1)),
        "mode_2x2_wafers": int(mix_match.group(1)),
    }


def _resolve_instance_path(instance_dir, instance_file):
    path = Path(instance_file)
    if not path.is_absolute():
        path = Path(instance_dir) / path
    return path.resolve()


def _sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _build_instance_manifest(args, instance_files):
    manifest = []
    seen_hashes = {}
    for instance_file in instance_files:
        instance_path = _resolve_instance_path(args.instance_dir, instance_file)
        if not instance_path.is_file():
            raise FileNotFoundError(f"Ablation instance does not exist: {instance_path}")
        model_description = get_petri_model_description_path(
            str(instance_path.parent), instance_path.name
        )
        mode_signature = _read_mode_signature(model_description)
        if mode_signature and _str2bool(args.validate_instance_label):
            _validate_mode_label(
                instance_path.name,
                mode_signature["mode_4x1_wafers"],
                mode_signature["mode_2x2_wafers"],
                "model description",
            )
        fingerprint = _sha256_file(instance_path)
        duplicate_of = seen_hashes.get(fingerprint)
        if duplicate_of and not _str2bool(args.allow_duplicate_instances):
            raise ValueError(
                "Duplicate instance content is not independent evidence: "
                f"{instance_path.name} and {duplicate_of} share SHA-256 {fingerprint}. "
                "Remove the duplicate or pass --allow_duplicate_instances True "
                "only for a non-statistical debugging run."
            )
        seen_hashes[fingerprint] = instance_path.name
        manifest.append(
            {
                "instance": instance_file,
                "resolved_path": str(instance_path),
                "sha256": fingerprint,
                "size_bytes": instance_path.stat().st_size,
                "model_description": str(model_description),
                "mode_signature": mode_signature,
            }
        )
    return manifest


def _build_petri_config(args):
    return PetriMIPConfig(
        num_batches=args.num_batches,
        num_pm=args.num_pm,
        num_steps=args.num_steps,
        total_wafers=args.total_wafers,
        pec_pool_size=args.pec_pool_size,
        cleaning_interval=args.cleaning_interval,
        cleaning_process_time=args.cleaning_process_time,
        process_mode=args.process_mode,
        mode_sequence=args.mode_sequence,
        wafer_mode_map=args.wafer_mode_map,
        default_wafer_mode=args.default_wafer_mode,
        full_mode_wafers=args.mode_4x1_wafers,
        mix_mode_wafers=args.mode_2x2_wafers,
        chamber_idle_penalty=args.chamber_idle_penalty,
        post_process_wait_penalty=args.post_process_wait_penalty,
        ll_wait_penalty=args.ll_wait_penalty,
        chamber_nonprocess_wait_square_penalty=args.chamber_nonprocess_wait_square_penalty,
        atr_capacity=args.atr_capacity,
        vtr_capacity=args.vtr_capacity,
    )


def _ensure_instance(args, petri_cfg):
    if _str2bool(args.generate_petri_instance):
        if _str2bool(args.validate_instance_label):
            _validate_mode_label(
                args.instance_name,
                len(petri_cfg.full_wafer_ids),
                len(petri_cfg.mix_wafer_ids),
                "generation arguments",
            )
        target_path = _resolve_instance_path(args.instance_dir, args.instance_name)
        if target_path.exists() and not _str2bool(args.allow_instance_overwrite):
            raise FileExistsError(
                f"Refusing to overwrite existing instance: {target_path}. "
                "Use --generate_petri_instance False to reuse it, choose a new "
                "name, or explicitly pass --allow_instance_overwrite True."
            )
        requested_instance_name = args.instance_name
        lp_path = generate_petri_mip_instance(
            args.instance_dir,
            args.instance_name,
            petri_cfg,
            warm_start_time_limit=0,
        )
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


def _prepare_shared_warm_start(args, petri_cfg):
    if args.warm_start_solution_file:
        warm_path = resolve_path(args.warm_start_solution_file)
        if not warm_path.is_file():
            raise FileNotFoundError(f"warm_start_solution_file does not exist: {warm_path}")
        return str(warm_path)

    cached = find_compatible_mixed_warm_start(args.instance_dir, args.instance_name)
    if cached:
        print(f"Reusing shared ablation warm start: {cached}")
        return str(resolve_path(cached))

    if (
        _str2bool(args.generate_petri_instance)
        and args.warm_start_time_limit > 0
        and petri_cfg.mix_wafer_ids
    ):
        generated = write_mixed_warm_start(
            args.instance_dir,
            args.instance_name,
            petri_cfg,
            time_limit=args.warm_start_time_limit,
        )
        if generated:
            print(f"Generated shared ablation warm start: {generated}")
            return str(resolve_path(generated))
    return ""


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

    state_dict = torch.load(
        args.test_model_path,
        map_location=device,
        weights_only=False,
    )
    validate_checkpoint_feature_schema(
        state_dict,
        net_share_kwargs["embedding_dim"],
        args.test_model_path,
    )
    validate_checkpoint_postprocessor_schema(
        state_dict,
        net_share_kwargs["embedding_dim"],
        args.test_model_path,
    )

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
    env_kwargs["scip_node_limit"] = args.evaluation_node_limit
    env_kwargs["scip_stall_node_limit"] = args.evaluation_stall_node_limit
    env_kwargs.update(
        {
            "schedule_chamber_idle_square_penalty": args.schedule_chamber_idle_square_penalty,
            "schedule_pm_wait_square_penalty": args.schedule_pm_wait_square_penalty,
            "schedule_module_wait_square_penalty": args.schedule_module_wait_square_penalty,
            "schedule_robot_wait_square_penalty": args.schedule_robot_wait_square_penalty,
        }
    )
    return env_kwargs


def _build_method_hyperparams(method_name, cfg, args, policy_bundle=None, run_env_kwargs=None):
    env_kwargs = run_env_kwargs if run_env_kwargs is not None else cfg["env"]
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
        "post_process_wait_penalty": args.post_process_wait_penalty,
        "chamber_nonprocess_wait_square_penalty": args.chamber_nonprocess_wait_square_penalty,
        "schedule_chamber_idle_square_penalty": args.schedule_chamber_idle_square_penalty,
        "chamber_idle_penalty": args.chamber_idle_penalty,
        "atr_capacity": args.atr_capacity,
        "vtr_capacity": args.vtr_capacity,
        "schedule_pm_wait_square_penalty": args.schedule_pm_wait_square_penalty,
        "schedule_module_wait_square_penalty": args.schedule_module_wait_square_penalty,
        "schedule_robot_wait_square_penalty": args.schedule_robot_wait_square_penalty,
        "warm_start_solution_file": env_kwargs.get("warm_start_solution_file", ""),
        "scip_node_limit": env_kwargs.get("scip_node_limit", -1),
        "scip_stall_node_limit": env_kwargs.get("scip_stall_node_limit", -1),
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
                "use_structure_rerank": False,
                "max_candidates": args.a3c_max_candidates,
                "max_selected_cuts": args.a3c_max_selected_cuts,
            }
        )
    elif method_name == "beam_only":
        base.update(
            {
                "decode_type": "heuristic_beam",
                "heuristic_beam_size": args.heuristic_beam_size,
                "heuristic_redundancy_weight": args.heuristic_redundancy_weight,
                "heuristic_max_candidates": args.heuristic_max_candidates,
                "heuristic_max_selected_cuts": args.heuristic_max_selected_cuts,
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
                "use_structure_rerank": True,
                "max_candidates": args.proposed_max_candidates,
                "max_selected_cuts": args.proposed_max_selected_cuts,
            }
        )
    return base


def _run_solver_only(instance_dir, instance_file, env_kwargs, args):
    env = SCIPCutSelEnv(instance_dir, args.scip_seed, args.seed, single_instance_file=instance_file, **env_kwargs)
    env.reset()
    return env.solve_default()


def _build_rl_agent(
    env,
    policy_bundle,
    args,
    decode_type,
    use_structure_rerank,
    max_candidates,
    max_selected_cuts,
):
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
            max_candidates=max_candidates,
            max_selected_cuts=max_selected_cuts,
            use_structure_rerank=use_structure_rerank,
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
        max_candidates=max_candidates,
        max_selected_cuts=max_selected_cuts,
        use_structure_rerank=use_structure_rerank,
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
            max_candidates=args.heuristic_max_candidates,
            max_selected_cuts=args.heuristic_max_selected_cuts,
        )

    return _run_with_agent(instance_dir, instance_file, env_kwargs, args, _builder)


def _run_a3c_only(instance_dir, instance_file, env_kwargs, args, policy_bundle):
    return _run_with_agent(
        instance_dir,
        instance_file,
        env_kwargs,
        args,
        lambda env: _build_rl_agent(
            env,
            policy_bundle,
            args,
            args.a3c_decode_type,
            False,
            args.a3c_max_candidates,
            args.a3c_max_selected_cuts,
        ),
    )


def _run_a3c_beam(instance_dir, instance_file, env_kwargs, args, policy_bundle):
    return _run_with_agent(
        instance_dir,
        instance_file,
        env_kwargs,
        args,
        lambda env: _build_rl_agent(
            env,
            policy_bundle,
            args,
            args.a3c_beam_decode_type,
            True,
            args.proposed_max_candidates,
            args.proposed_max_selected_cuts,
        ),
    )


def _safe_float(value):
    if value is None:
        return None
    try:
        return float(value)
    except Exception:
        return None


def _has_incumbent(stats):
    if stats is None:
        return False
    n_solutions = stats.get("n_solutions")
    try:
        if n_solutions is not None and int(n_solutions) > 0:
            return True
    except Exception:
        pass
    return stats.get("best_obj") is not None or bool(stats.get("solution"))


def _format_instance_result(method_name, instance_file, stats, hyperparams, error=None):
    solution = {}
    n_solutions = None
    has_solution = False
    if stats is not None:
        solution = stats.get("solution", {})
        n_solutions = stats.get("n_solutions")
        has_solution = _has_incumbent(stats)
    return {
        "method": method_name,
        "instance": instance_file,
        "status": None if stats is None else stats.get("status"),
        "solving_time": None if stats is None else _safe_float(stats.get("solving_time")),
        "wall_time": None if stats is None else _safe_float(stats.get("wall_time")),
        "best_obj": None if stats is None else _safe_float(stats.get("best_obj")),
        "ntotal_nodes": None if stats is None else _safe_float(stats.get("ntotal_nodes")),
        "primal_dual_gap": None if stats is None else _safe_float(stats.get("primal_dual_gap")),
        "primaldualintegral": None if stats is None else _safe_float(stats.get("primaldualintegral")),
        "n_solutions": None if n_solutions is None else int(n_solutions),
        "has_solution": has_solution,
        "comparison_valid": error is None and has_solution,
        "nonzero_solution_vars": len(solution),
        "cutsel_effective_max_candidates": (
            None if stats is None else stats.get("cutsel_effective_max_candidates")
        ),
        "cutsel_effective_max_selected_cuts": (
            None if stats is None else stats.get("cutsel_effective_max_selected_cuts")
        ),
        "cutsel_telemetry": (
            {} if stats is None else stats.get("cutsel_telemetry", {})
        ),
        "solution": solution,
        "hyperparameters": hyperparams,
        "error": error,
    }


def _valid_metric_values(rows, key, max_abs=None):
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
            if max_abs is not None and abs(value) >= max_abs:
                continue
            values.append(value)
    return values


def _status_is_solved(status):
    return str(status).lower() in {"optimal", "gaplimit", "bestsollimit"}


def _aggregate_results(results):
    summary = {}
    for method_name, method_results in results.items():
        completed = [r for r in method_results if r["error"] is None and r["solving_time"] is not None]
        with_solution = [r for r in completed if r.get("has_solution")]
        solved = [r for r in completed if _status_is_solved(r.get("status"))]
        solving_times = _valid_metric_values(completed, "solving_time")
        wall_times = _valid_metric_values(completed, "wall_time")
        callback_times = [
            float(r.get("cutsel_telemetry", {}).get("callback_time_seconds", 0.0))
            for r in completed
            if r.get("cutsel_telemetry")
        ]
        incumbent_solving_times = _valid_metric_values(with_solution, "solving_time")
        best_objs = _valid_metric_values(with_solution, "best_obj")
        total_nodes = _valid_metric_values(completed, "ntotal_nodes")
        primal_dual_gaps = _valid_metric_values(
            with_solution,
            "primal_dual_gap",
            max_abs=NO_INCUMBENT_GAP_THRESHOLD,
        )
        primal_dual_integrals = _valid_metric_values(with_solution, "primaldualintegral")
        nonzero_solution_vars = _valid_metric_values(with_solution, "nonzero_solution_vars")
        summary[method_name] = {
            "num_instances": len(method_results),
            "num_completed": len(completed),
            "num_valid": len(completed),
            "num_with_solution": len(with_solution),
            "num_solved": len(solved),
            "mean_solving_time": None if not solving_times else float(np.mean(solving_times)),
            "mean_wall_time": None if not wall_times else float(np.mean(wall_times)),
            "mean_callback_time": None if not callback_times else float(np.mean(callback_times)),
            "mean_incumbent_solving_time": None if not incumbent_solving_times else float(np.mean(incumbent_solving_times)),
            "mean_best_obj": None if not best_objs else float(np.mean(best_objs)),
            "mean_ntotal_nodes": None if not total_nodes else float(np.mean(total_nodes)),
            "mean_primal_dual_gap": None if not primal_dual_gaps else float(np.mean(primal_dual_gaps)),
            "mean_primaldualintegral": None if not primal_dual_integrals else float(np.mean(primal_dual_integrals)),
            "mean_nonzero_solution_vars": None if not nonzero_solution_vars else float(np.mean(nonzero_solution_vars)),
        }
    return summary


def _build_advantage_analysis(results, time_limit=None):
    """Build paired evidence without cherry-picking unmatched runs."""
    proposed_rows = {
        row["instance"]: row for row in results.get("a3c_beam", [])
    }
    comparisons = {}
    for baseline_name in ("solver_only", "a3c_only", "beam_only"):
        relative_improvements = []
        for baseline in results.get(baseline_name, []):
            proposed = proposed_rows.get(baseline["instance"])
            if proposed is None:
                continue
            if not baseline.get("has_solution") or not proposed.get("has_solution"):
                continue
            baseline_pdi = _safe_float(baseline.get("primaldualintegral"))
            proposed_pdi = _safe_float(proposed.get("primaldualintegral"))
            if baseline_pdi is None or proposed_pdi is None or baseline_pdi <= 0:
                continue
            if time_limit is not None and time_limit > 0:
                if any(
                    row.get("solving_time") is not None
                    and float(row["solving_time"]) > 1.25 * time_limit
                    for row in (baseline, proposed)
                ):
                    continue
            relative_improvements.append(
                100.0 * (baseline_pdi - proposed_pdi) / baseline_pdi
            )

        pair_count = len(relative_improvements)
        wins = sum(value > 0 for value in relative_improvements)
        comparisons[baseline_name] = {
            "paired_runs": pair_count,
            "wins": wins,
            "win_rate": None if pair_count == 0 else wins / pair_count,
            "mean_pdi_improvement_percent": (
                None if pair_count == 0 else float(np.mean(relative_improvements))
            ),
            "median_pdi_improvement_percent": (
                None if pair_count == 0 else float(np.median(relative_improvements))
            ),
            "per_instance_improvement_percent": relative_improvements,
        }

    # This is an evidence gate, not a result-manufacturing rule: the proposed
    # method must beat every component/baseline on at least three paired runs.
    clear_advantage = all(
        item["paired_runs"] >= 3
        and item["mean_pdi_improvement_percent"] is not None
        and item["mean_pdi_improvement_percent"] >= 5.0
        and item["win_rate"] is not None
        and item["win_rate"] >= 2.0 / 3.0
        for item in comparisons.values()
    )
    return {
        "primary_metric": "primaldualintegral",
        "lower_is_better": True,
        "clear_advantage": clear_advantage,
        "evidence_rule": (
            "At least 3 paired time-comparable runs versus every baseline, "
            "mean PDI improvement >= 5%, and win rate >= 2/3."
        ),
        "comparisons": comparisons,
    }


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


def _metric_count_label(item, metric_key):
    if metric_key in {"mean_best_obj", "mean_primal_dual_gap", "mean_primaldualintegral"}:
        return f"{item['num_with_solution']}/{item['num_instances']} inc."
    return f"{item['num_completed']}/{item['num_instances']} run"


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
            f'<text x="{plot_x + plot_width + 10:.2f}" y="{row_y + 13:.2f}" font-size="12" fill="#404040">{_format_display_value(value)} ({_metric_count_label(summary[method_name], metric_key)})</text>'
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
        ("Mean Primal-Dual Integral", "mean_primaldualintegral"),
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
        f'<text x="42" y="96" font-size="14" fill="#565656">Instances: {len(meta.get("instance_files", []))} | Quality metrics only use runs with an incumbent solution.</text>',
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
        "wall_time",
        "best_obj",
        "ntotal_nodes",
        "primal_dual_gap",
        "primaldualintegral",
        "n_solutions",
        "has_solution",
        "comparison_valid",
        "nonzero_solution_vars",
        "cutsel_effective_max_candidates",
        "cutsel_effective_max_selected_cuts",
        "cutsel_telemetry",
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
                        **{
                            key: row[key]
                            for key in fieldnames
                            if key not in {"hyperparameters", "cutsel_telemetry"}
                        },
                        "cutsel_telemetry": json.dumps(
                            row["cutsel_telemetry"], ensure_ascii=False
                        ),
                        "hyperparameters": json.dumps(row["hyperparameters"], ensure_ascii=False),
                    }
                )


def _build_diagnostics(results, summary, meta):
    diagnostics = []
    instance_files = meta.get("instance_files", [])
    if len(instance_files) < 3:
        diagnostics.append(
            "The run covers fewer than 3 instances, so method differences are not statistically meaningful."
        )
    if not any(item["num_with_solution"] > 0 for item in summary.values()):
        diagnostics.append(
            "No method produced an incumbent solution; best objective and gap cannot be used to rank algorithms."
        )

    incumbent_objectives = [
        float(row["best_obj"])
        for row in _flatten_results(results)
        if row.get("has_solution") and row.get("best_obj") is not None
    ]
    if len(incumbent_objectives) > 1 and np.isclose(
        min(incumbent_objectives), max(incumbent_objectives), rtol=1e-9, atol=1e-9
    ):
        diagnostics.append(
            "All methods retained the same incumbent objective, so their Gantt charts are expected to be identical; "
            "compare primal-dual integral and gap trajectory instead of schedule appearance."
        )

    completed_rows = [
        row
        for method_results in results.values()
        for row in method_results
        if row.get("error") is None and row.get("ntotal_nodes") is not None
    ]
    if completed_rows and all(float(row.get("ntotal_nodes") or 0.0) <= 1.0 for row in completed_rows):
        diagnostics.append(
            "All completed runs stayed at the root node, so this experiment mainly measures root LP/presolve difficulty rather than tree-search cut selection."
        )

    solver_time = summary.get("solver_only", {}).get("mean_solving_time")
    beam_time = summary.get("beam_only", {}).get("mean_solving_time")
    if solver_time and beam_time and beam_time > 1.5 * solver_time:
        diagnostics.append(
            "The heuristic beam run is much slower than SCIP default; cap beam candidates/selected cuts or use a smaller cut pool for fair overhead accounting."
        )

    time_limit = _safe_float(meta.get("time_limit"))
    stall_node_limit = _safe_float(meta.get("evaluation_stall_node_limit"))
    if stall_node_limit is not None and stall_node_limit >= 0:
        diagnostics.append(
            "A stall-node limit is enabled. Solving times may measure how fast a "
            "method reaches that node count rather than time-to-quality or "
            "time-to-optimal; disable it for the primary fixed-time comparison."
        )
    if time_limit is not None and time_limit > 0:
        overtime_methods = sorted(
            {
                row["method"]
                for row in _flatten_results(results)
                if row.get("solving_time") is not None
                and float(row["solving_time"]) > 1.25 * time_limit
            }
        )
        if overtime_methods:
            diagnostics.append(
                f"The following methods exceeded the configured {time_limit:g}s limit inside a cut-selection callback: "
                f"{', '.join(overtime_methods)}. Their time and primal-dual integral are not directly comparable until callback overhead is capped."
            )

    solver_pdi = summary.get("solver_only", {}).get("mean_primaldualintegral")
    if solver_pdi is not None and solver_pdi > 0:
        improvements = []
        for method_name in METHOD_ORDER:
            if method_name == "solver_only":
                continue
            method_pdi = summary.get(method_name, {}).get("mean_primaldualintegral")
            method_time = summary.get(method_name, {}).get("mean_solving_time")
            if method_pdi is None:
                continue
            if time_limit and method_time and method_time > 1.25 * time_limit:
                continue
            change = 100.0 * (solver_pdi - method_pdi) / solver_pdi
            improvements.append(f"{method_name}: {change:+.1f}%")
        if improvements:
            diagnostics.append(
                "Primal-dual integral improvement versus solver_only for time-comparable runs "
                f"(positive is better): {', '.join(improvements)}."
            )
    return diagnostics


def _write_markdown(path, results, summary, meta):
    lines = []
    lines.append("# Ablation Results")
    lines.append("")
    lines.append("## Setup")
    lines.append("")
    lines.append(f"- Instance directory: `{meta['instance_dir']}`")
    lines.append(f"- Instance files: `{', '.join(meta['instance_files'])}`")
    for item in meta.get("instance_manifest", []):
        mode = item.get("mode_signature") or {}
        lines.append(
            f"- Fingerprint `{item['instance']}`: SHA-256 `{item['sha256']}`, "
            f"bytes `{item['size_bytes']}`, 4x1 `{mode.get('mode_4x1_wafers', 'n/a')}`, "
            f"2x2 `{mode.get('mode_2x2_wafers', 'n/a')}`"
        )
    lines.append(f"- Model path: `{meta['model_path']}`")
    lines.append(f"- Generated MIP: `{meta['generated_lp']}`")
    lines.append(f"- Model description: `{meta['model_description']}`")
    lines.append(f"- Shared warm start: `{meta.get('warm_start_solution_file', '')}`")
    lines.append(
        f"- Evaluation stopping: time `{meta.get('time_limit')}`, nodes "
        f"`{meta.get('evaluation_node_limit', -1)}`, stall nodes "
        f"`{meta.get('evaluation_stall_node_limit', -1)}`"
    )
    if meta.get("comparison_svg"):
        lines.append(f"- Comparison SVG: `{meta['comparison_svg']}`")
    if meta.get("gantt_dir"):
        lines.append(f"- Gantt directory: `{meta['gantt_dir']}`")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append("| Method | Completed | With Incumbent | Solved | SCIP Time | Wall Time | Callback Time | Mean Nodes | Mean Best Obj | Mean Gap | Mean PDI |")
    lines.append("| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |")
    for method_name in METHOD_ORDER:
        if method_name not in summary:
            continue
        item = summary[method_name]
        lines.append(
            f"| {method_name} | {item['num_completed']}/{item['num_instances']} | "
            f"{item['num_with_solution']}/{item['num_instances']} | {item['num_solved']}/{item['num_instances']} | "
            f"{_format_display_value(item['mean_solving_time'])} | {_format_display_value(item['mean_wall_time'])} | "
            f"{_format_display_value(item['mean_callback_time'])} | "
            f"{_format_display_value(item['mean_ntotal_nodes'])} | {_format_display_value(item['mean_best_obj'])} | "
            f"{_format_display_value(item['mean_primal_dual_gap'])} | {_format_display_value(item['mean_primaldualintegral'])} |"
        )
    advantage = _build_advantage_analysis(results, _safe_float(meta.get("time_limit")))
    lines.append("")
    lines.append("## Advantage Evidence")
    lines.append("")
    lines.append(
        f"- Clear advantage gate: **{'PASS' if advantage['clear_advantage'] else 'NOT YET PASSED'}**"
    )
    lines.append(f"- Rule: {advantage['evidence_rule']}")
    lines.append("")
    lines.append("| Proposed vs. | Paired Runs | Wins | Win Rate | Mean PDI Improvement | Median PDI Improvement |")
    lines.append("| --- | ---: | ---: | ---: | ---: | ---: |")
    for baseline_name, item in advantage["comparisons"].items():
        win_rate = None if item["win_rate"] is None else 100.0 * item["win_rate"]
        lines.append(
            f"| {METHOD_DISPLAY_NAMES[baseline_name]} | {item['paired_runs']} | {item['wins']} | "
            f"{_format_display_value(win_rate)}% | "
            f"{_format_display_value(item['mean_pdi_improvement_percent'])}% | "
            f"{_format_display_value(item['median_pdi_improvement_percent'])}% |"
        )
    diagnostics = _build_diagnostics(results, summary, meta)
    if diagnostics:
        lines.append("")
        lines.append("## Diagnostics")
        lines.append("")
        for diagnostic in diagnostics:
            lines.append(f"- {diagnostic}")
    lines.append("")
    lines.append("## Per-Instance Results")
    lines.append("")
    lines.append("| Method | Instance | Status | SCIP Time | Wall Time | Callback | Best Obj | Nodes | Gap | PDI | Effective Budget | Error |")
    lines.append("| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |")
    for method_name in METHOD_ORDER:
        for row in results.get(method_name, []):
            lines.append(
                f"| {row['method']} | {row['instance']} | {row['status']} | {_format_display_value(row['solving_time'])} | "
                f"{_format_display_value(row['wall_time'])} | "
                f"{_format_display_value(row['cutsel_telemetry'].get('callback_time_seconds'))} | "
                f"{_format_display_value(row['best_obj'])} | {_format_display_value(row['ntotal_nodes'])} | "
                f"{_format_display_value(row['primal_dual_gap'])} | {_format_display_value(row['primaldualintegral'])} | "
                f"{row['cutsel_effective_max_candidates']}/{row['cutsel_effective_max_selected_cuts']} | {row['error']} |"
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
    _validate_ablation_protocol(args)
    selected_methods = _selected_methods(args)
    cfg = _load_config(args.config_file)
    set_global_seed(args.seed)

    os.makedirs(args.instance_dir, exist_ok=True)
    os.makedirs(args.output_dir, exist_ok=True)

    petri_cfg = _build_petri_config(args)
    generated_lp = _ensure_instance(args, petri_cfg)
    model_description = get_petri_model_description_path(args.instance_dir, args.instance_name)

    instance_file = "" if _str2bool(args.all_instances) else (args.single_instance_file or args.instance_name)
    instance_files = _get_instance_list(args.instance_dir, instance_file)
    if not instance_files:
        raise ValueError(f"No instance files found in {args.instance_dir}")
    instance_manifest = _build_instance_manifest(args, instance_files)

    shared_warm_start = _prepare_shared_warm_start(args, petri_cfg)
    if not shared_warm_start:
        print(
            "warning: no shared ablation warm start is available; methods may reach "
            "the time limit without an incumbent, so quality comparison and Gantt charts can be empty."
        )
    env_kwargs = _build_env_kwargs(cfg, args)
    policy_bundle = _load_policy_bundle(cfg, args) if args.test_model_path else None

    experiment_results = {
        "solver_only": [],
        "a3c_only": [],
        "beam_only": [],
        "a3c_beam": [],
    }

    for instance_index, instance_name in enumerate(instance_files):
        instance_warm_start = shared_warm_start
        if _str2bool(args.all_instances) and instance_name != args.instance_name:
            instance_warm_start = find_compatible_mixed_warm_start(
                args.instance_dir,
                instance_name,
            ) or ""
        instance_env_kwargs = dict(env_kwargs)
        instance_env_kwargs["warm_start_solution_file"] = instance_warm_start

        # Rotate execution order across instances so filesystem cache, CPU
        # temperature, and background load do not systematically favor the
        # proposed method or a baseline.
        rotated_method_order = (
            METHOD_ORDER[instance_index % len(METHOD_ORDER):]
            + METHOD_ORDER[:instance_index % len(METHOD_ORDER)]
        )
        method_order = [
            method_name
            for method_name in rotated_method_order
            if method_name in selected_methods
        ]
        for method_name in method_order:
            requires_policy = method_name in {"a3c_only", "a3c_beam"}
            hyper_policy = policy_bundle
            if requires_policy and hyper_policy is None:
                hyper_policy = {
                    "model_path": None,
                    "beam_size": cfg["policy"]["beam_size"],
                    "use_high_level": _str2bool(args.use_cutsel_percent_policy),
                }
            hyper = _build_method_hyperparams(
                method_name,
                cfg,
                args,
                hyper_policy,
                run_env_kwargs=instance_env_kwargs,
            )
            if requires_policy and policy_bundle is None:
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

            try:
                wall_start = time.perf_counter()
                if method_name == "solver_only":
                    stats = _run_solver_only(
                        args.instance_dir, instance_name, instance_env_kwargs, args
                    )
                elif method_name == "beam_only":
                    stats = _run_beam_only(
                        args.instance_dir, instance_name, instance_env_kwargs, args
                    )
                elif method_name == "a3c_only":
                    stats = _run_a3c_only(
                        args.instance_dir, instance_name, instance_env_kwargs, args, policy_bundle
                    )
                else:
                    stats = _run_a3c_beam(
                        args.instance_dir, instance_name, instance_env_kwargs, args, policy_bundle
                    )
                stats["wall_time"] = time.perf_counter() - wall_start
                experiment_results[method_name].append(
                    _format_instance_result(method_name, instance_name, stats, hyper)
                )
            except Exception as exc:
                experiment_results[method_name].append(
                    _format_instance_result(
                        method_name, instance_name, None, hyper, error=str(exc)
                    )
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
    incumbent_count = sum(
        1
        for row in _flatten_results(experiment_results)
        if row.get("has_solution") and row.get("solution")
    )
    gantt_error = None
    if incumbent_count == 0:
        gantt_error = (
            "No method produced an incumbent solution, so no schedule SVG can be drawn. "
            "The Gantt directory contains only the comparison frontend and manifest."
        )
    try:
        from petri_gantt import generate_gantt_charts_from_records

        generated_gantt = generate_gantt_charts_from_records(
            _flatten_results(experiment_results),
            gantt_dir,
            view="all",
            comparison_svg=comparison_svg,
        )
    except Exception as exc:
        gantt_error = str(exc)

    diagnostics = _build_diagnostics(
        experiment_results,
        summary,
        {
            "instance_files": instance_files,
            "instance_manifest": instance_manifest,
            "time_limit": env_kwargs["scip_time_limit"],
            "evaluation_node_limit": args.evaluation_node_limit,
            "evaluation_stall_node_limit": args.evaluation_stall_node_limit,
        },
    )

    payload = {
        "meta": {
            "instance_dir": args.instance_dir,
            "instance_files": instance_files,
            "instance_manifest": instance_manifest,
            "model_path": args.test_model_path,
            "generated_lp": generated_lp,
            "model_description": model_description,
            "time_limit": env_kwargs["scip_time_limit"],
            "evaluation_node_limit": args.evaluation_node_limit,
            "evaluation_stall_node_limit": args.evaluation_stall_node_limit,
            "warm_start_solution_file": shared_warm_start,
            "comparison_svg": comparison_svg,
            "gantt_dir": gantt_dir if generated_gantt else "",
            "fair_ablation_enforced": _str2bool(args.enforce_fair_ablation),
            "methods": selected_methods,
            "generation_config": (
                {
                    "process_mode": args.process_mode,
                    "mode_4x1_wafers": len(petri_cfg.full_wafer_ids),
                    "mode_2x2_wafers": len(petri_cfg.mix_wafer_ids),
                }
                if _str2bool(args.generate_petri_instance)
                else None
            ),
        },
        "diagnostics": diagnostics,
        "advantage_analysis": _build_advantage_analysis(
            experiment_results,
            env_kwargs["scip_time_limit"],
        ),
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

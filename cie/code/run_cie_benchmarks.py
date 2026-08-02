"""Reproducible CIE manufacturing cut-selection benchmark runner.

The default ablation evaluates five controlled method variants under identical SCIP limits:

* ``scip_default``: SCIP's unmodified hybrid cut selector.
* ``hem``: a 13-feature hierarchical policy checkpoint, without structure-aware
  features, beam decoding, or reranking.
* ``hem_beam``: the same HEM checkpoint with beam-search decoding.
* ``hem_structure``: the same 23-feature structure-aware checkpoint as Proposed,
  with greedy decoding and role-submodular reranking.
* ``proposed``: the 23-feature policy with role-submodular completion and reranking.

The legacy names ``rdmct_feature_only`` and ``rdmct_a3c`` remain accepted for
backward-compatible reproduction of earlier ablation files.

It accepts a JSON suite manifest so Petri scheduling instances, MIPLIB files,
and other MILP families can be evaluated by the same command.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import statistics
import sys
import time
import warnings
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

CIE_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = CIE_ROOT.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np
import torch

from cutsel_agent_parallel import CutSelectAgent, HierarchyCutSelectAgent
from environments import SCIPCutSelEnv
from path_utils import resolve_path
from pointer_net import CutsPercentPolicy, PointerNetwork
from pointer_net_end_token import PointerNetworkEndToken
from runtime_compat import configure_openmp_runtime
from utilss.mean_std import RunningMeanStd
from utils import set_global_seed
from global_const import (
    validate_checkpoint_feature_schema,
    validate_checkpoint_postprocessor_schema,
)

configure_openmp_runtime()

INSTANCE_SUFFIXES = (".lp", ".mps", ".cip", ".lp.gz", ".mps.gz")
DEFAULT_ACS_WEIGHTS = {
    "dircutoffdistweight": 0.0,
    "efficacyweight": 1.0,
    "intsupportweight": 0.0,
    "objparalweight": 0.0,
}
EXPECTED_POLICY_REWARD = "primaldualintegral"
METHODS = (
    "scip_default",
    "adaptive_cutsel",
    "hem",
    "hem_beam",
    "hem_structure",
    "a3c",
    "beam_search",
    "proposed",
    "rdmct_feature_only",
    "rdmct_a3c",
)
DEFAULT_METHODS = (
    "scip_default",
    "hem",
    "hem_beam",
    "hem_structure",
    "proposed",
)
METHOD_LABELS = {
    "scip_default": "SCIP",
    "hem": "HEM",
    "hem_beam": "HEM + Beam",
    "hem_structure": "HEM + Structure",
    "proposed": "Proposed",
    "rdmct_feature_only": "23D Features Only",
}
STABILITY_PROFILES = {
    "full": (True, "linear"),
    "stage2_off": (False, "linear"),
    "linear_off": (True, "quadratic"),
}


def _parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest",
        default=str(CIE_ROOT / "configs" / "cie_benchmark_suites.json"),
        help="JSON benchmark-suite manifest.",
    )
    parser.add_argument("--output_dir", default=str(CIE_ROOT / "results"))
    parser.add_argument(
        "--solution_dir",
        default="",
        help=(
            "Optional directory for per-run SCIP .sol files. Solutions are "
            "written only when an incumbent exists; use this for independent "
            "schedule validation and manufacturing-metric extraction."
        ),
    )
    parser.add_argument("--methods", default=",".join(DEFAULT_METHODS))
    parser.add_argument(
        "--splits",
        default="test",
        help="Comma-separated manifest splits to evaluate, or 'all'.",
    )
    parser.add_argument(
        "--suites",
        default="all",
        help="Comma-separated suite names to evaluate, or 'all'.",
    )
    parser.add_argument("--seeds", default="1,2,3,4,5")
    parser.add_argument(
        "--training_seed",
        type=int,
        default=-1,
        help="Training seed of the supplied learned checkpoints; -1 means unspecified.",
    )
    parser.add_argument(
        "--run_label",
        default="",
        help="Optional label included in output filenames.",
    )
    parser.add_argument("--time_limit", type=float, default=300.0)
    parser.add_argument(
        "--stability_profile",
        choices=tuple(STABILITY_PROFILES),
        default="full",
        help=(
            "Schedule-compaction protocol. Main algorithm comparisons use full. "
            "The separate controlled-variable study compares full with "
            "stage2_off and linear_off."
        ),
    )
    parser.add_argument(
        "--lexicographic_stability_time_limit",
        type=float,
        default=-1.0,
        help=(
            "Stage-two seconds within the common SCIP budget. Negative selects "
            "min(60 s, 10%% of the per-instance limit)."
        ),
    )
    parser.add_argument(
        "--lexicographic_stability_node_limit",
        type=int,
        default=5000,
    )
    parser.add_argument(
        "--device",
        default="cuda:0",
        help="Torch device for learned policies. CUDA is required when a learned method is selected.",
    )
    parser.add_argument("--node_limit", type=int, default=-1)
    parser.add_argument("--memory_limit_mb", type=float, default=8192.0)
    parser.add_argument(
        "--warm_start",
        choices=("auto", "none"),
        default="auto",
        help="Load a compatible SPBS solution automatically, or disable warm starts.",
    )
    parser.add_argument("--scip_verbosity", type=int, default=0)
    parser.add_argument("--sel_cuts_percent", type=float, default=0.2)
    parser.add_argument("--decode_type", choices=("greedy", "beam_search"), default="greedy")
    parser.add_argument("--policy_type", choices=("with_token", "without_token"), default="with_token")
    parser.add_argument(
        "--hem_config",
        default=str(CIE_ROOT / "configs" / "cie_hem_train.json"),
    )
    parser.add_argument("--hem_model", default="")
    parser.add_argument(
        "--a3c_config",
        default=str(CIE_ROOT / "configs" / "cie_feature_only_train.json"),
    )
    parser.add_argument("--a3c_model", default="")
    parser.add_argument(
        "--feature_only_config",
        default=str(CIE_ROOT / "configs" / "cie_feature_only_train.json"),
    )
    parser.add_argument("--feature_only_model", default="")
    parser.add_argument(
        "--proposed_config",
        default=str(CIE_ROOT / "configs" / "cie_proposed_inference.json"),
    )
    parser.add_argument("--proposed_model", default="")
    parser.add_argument(
        "--acs_weights",
        default="0,1,0,0",
        help="dircutoff,efficacy,integer-support,objective-parallelism weights.",
    )
    parser.add_argument(
        "--acs_predictions",
        default="",
        help="Optional JSON mapping instance basename/relative path to four ACS weights.",
    )
    parser.add_argument("--cutsel_max_candidates", type=int, default=128)
    parser.add_argument("--cutsel_max_selected_cuts", type=int, default=16)
    parser.add_argument("--structure_pool_factor", type=float, default=2.0)
    parser.add_argument("--structure_anchor_ratio", type=float, default=0.25)
    parser.add_argument("--structure_quality_weight", type=float, default=0.35)
    parser.add_argument("--structure_policy_weight", type=float, default=0.20)
    parser.add_argument("--structure_coverage_weight", type=float, default=0.25)
    parser.add_argument("--structure_representation_weight", type=float, default=0.20)
    parser.add_argument(
        "--max_instances_per_suite",
        type=int,
        default=0,
        help="Deterministic debug cap; 0 evaluates every discovered instance.",
    )
    parser.add_argument(
        "--fail_on_empty_suite",
        action="store_true",
        help="Fail instead of recording an empty suite.",
    )
    parser.add_argument(
        "--no_resume",
        action="store_true",
        help=(
            "Disable the default crash-safe per-evaluation checkpoint. By default, "
            "completed instance-method-seed evaluations are skipped on restart."
        ),
    )
    return parser.parse_args()


def _load_json(path):
    with open(path, "r", encoding="utf-8") as stream:
        return json.load(stream)


def _parse_int_list(text):
    values = [int(item.strip()) for item in str(text).split(",") if item.strip()]
    if not values:
        raise ValueError("At least one random seed is required.")
    return values


def _parse_methods(text):
    methods = [item.strip() for item in str(text).split(",") if item.strip()]
    unknown = sorted(set(methods) - set(METHODS))
    if unknown:
        raise ValueError(f"Unknown methods: {unknown}; supported methods are {METHODS}.")
    return methods


def _normalize_acs_weights(values):
    if isinstance(values, dict):
        values = [
            values.get("dircutoffdistweight", values.get("dircutoff", 0.0)),
            values.get("efficacyweight", values.get("efficacy", 0.0)),
            values.get("intsupportweight", values.get("integer_support", 0.0)),
            values.get("objparalweight", values.get("objective_parallelism", 0.0)),
        ]
    if isinstance(values, str):
        values = [float(item.strip()) for item in values.split(",") if item.strip()]
    values = [max(0.0, float(value)) for value in values]
    if len(values) != 4:
        raise ValueError("ACS weights must contain exactly four nonnegative values.")
    total = sum(values)
    if total <= 0:
        raise ValueError("At least one ACS weight must be positive.")
    values = [value / total for value in values]
    return dict(zip(DEFAULT_ACS_WEIGHTS, values))


def _discover_instances(
    manifest_path,
    max_instances_per_suite=0,
    splits=None,
    suite_names=None,
):
    manifest_path = Path(resolve_path(manifest_path))
    payload = _load_json(manifest_path)
    base_dir = manifest_path.parent
    discovered = []
    empty_suites = []
    for suite in payload.get("suites", []):
        suite_name = suite.get("name", "")
        if suite_names and "all" not in suite_names and suite_name not in suite_names:
            continue
        root_value = suite.get("root", "")
        root = Path(root_value).expanduser()
        if not root.is_absolute():
            root = (base_dir / root).resolve()
        pattern = suite.get("glob", "**/*")
        split = suite.get("split", "test")
        if splits and "all" not in splits and split not in splits:
            continue
        files = []
        if root.is_file():
            files = [root]
        elif root.is_dir():
            files = sorted(
                path
                for path in root.glob(pattern)
                if path.is_file()
                and any(str(path).lower().endswith(suffix) for suffix in INSTANCE_SUFFIXES)
            )
        if max_instances_per_suite > 0:
            files = files[:max_instances_per_suite]
        if not files:
            empty_suites.append(
                {
                    "name": suite.get("name", root.name),
                    "root": str(root),
                    "glob": pattern,
                }
            )
            continue
        for path in files:
            discovered.append(
                {
                    "suite": suite.get("name", root.name),
                    "family": suite.get("family", "unknown"),
                    "scale": str(suite.get("scale", "unknown")),
                    "split": split,
                    "time_limit": float(suite.get("time_limit", 0.0)),
                    "solver_seeds": [int(value) for value in suite.get("seeds", [])],
                    "path": str(path.resolve()),
                    "relative_path": str(path.relative_to(root)) if root.is_dir() else path.name,
                }
            )
    return payload, discovered, empty_suites


def _load_policy_bundle(
    config_path,
    model_path,
    expected_feature_dim,
    policy_type="with_token",
    expected_postprocessor="none",
    device_request="cuda:0",
):
    if not model_path:
        return None
    config_path = str(resolve_path(config_path))
    model_path = str(resolve_path(model_path))
    if not os.path.isfile(model_path):
        raise FileNotFoundError(f"Policy checkpoint does not exist: {model_path}")
    cfg = _load_json(config_path)
    feature_dim = int(cfg["net_share"]["embedding_dim"])
    if feature_dim != expected_feature_dim:
        raise ValueError(
            f"{config_path} has embedding_dim={feature_dim}, expected {expected_feature_dim}."
        )
    requested = cfg["devices"].get("global_device", "cuda:0")
    if device_request != "auto":
        requested = device_request
    try:
        device = torch.device(requested)
    except (TypeError, RuntimeError) as exc:
        raise ValueError(f"Invalid Torch device: {requested!r}") from exc
    if device.type != "cuda":
        raise ValueError(
            "Learned CIE benchmarks are configured for GPU execution; "
            f"received device={requested!r}."
        )
    if not torch.cuda.is_available():
        raise RuntimeError(
            "CUDA is required for learned benchmark methods but is unavailable. "
            "Install a CUDA-enabled PyTorch build and rerun the environment check."
        )
    if device.index is not None and device.index >= torch.cuda.device_count():
        raise RuntimeError(
            f"Requested {device}, but only {torch.cuda.device_count()} CUDA device(s) are available."
        )
    pointer_cls = (
        PointerNetworkEndToken
        if policy_type == "with_token"
        else PointerNetwork
    )
    policy = pointer_cls(
        embedding_dim=feature_dim,
        hidden_dim=cfg["net_share"]["hidden_dim"],
        n_glimpses=cfg["policy"]["n_glimpses"],
        tanh_exploration=cfg["net_share"]["tanh_exploration"],
        use_tanh=cfg["net_share"]["use_tanh"],
        beam_size=cfg["policy"]["beam_size"],
        use_cuda=True,
    ).to(device)
    checkpoint = torch.load(model_path, map_location=device, weights_only=False)
    recorded_reward = checkpoint.get("reward_type")
    if recorded_reward is None:
        variant_path = Path(model_path).with_name("variant.json")
        if variant_path.is_file():
            variant = _load_json(variant_path)
            recorded_reward = variant.get("algorithm", {}).get("reward_type")
    if recorded_reward is None:
        warnings.warn(
            f"Cannot verify reward_type for legacy policy checkpoint: {model_path}",
            RuntimeWarning,
            stacklevel=2,
        )
    elif recorded_reward != EXPECTED_POLICY_REWARD:
        raise ValueError(
            f"Policy checkpoint reward_type={recorded_reward!r}, expected "
            f"{EXPECTED_POLICY_REWARD!r}: {model_path}"
        )
    validate_checkpoint_feature_schema(checkpoint, feature_dim, model_path)
    validate_checkpoint_postprocessor_schema(
        checkpoint,
        feature_dim,
        model_path,
        expected_postprocessor,
    )
    policy.load_state_dict(checkpoint["pointer_net"])
    policy.eval()

    mean_std = None
    if "mean" in checkpoint and "std" in checkpoint:
        mean_std = RunningMeanStd((feature_dim,))
        mean_std.set_mean_std(checkpoint["mean"], checkpoint["std"])

    high_level = None
    use_high_level = bool(
        cfg.get("cutsel_percent_policy", {}).get("use_cutsel_percent_policy", True)
    )
    if use_high_level:
        high_level = CutsPercentPolicy(
            embedding_dim=feature_dim,
            hidden_dim=cfg["net_share"]["hidden_dim"],
            n_process_block_iters=cfg["value"]["n_process_block_iters"],
            tanh_exploration=cfg["net_share"]["tanh_exploration"],
            use_tanh=cfg["net_share"]["use_tanh"],
            use_cuda=True,
        ).to(device)
        high_level.load_state_dict(checkpoint["cutsel_percent_net"])
        high_level.eval()
    return {
        "config": config_path,
        "model": model_path,
        "policy": policy,
        "high_level": high_level,
        "mean_std": mean_std,
        "device": str(device),
        "feature_dim": feature_dim,
    }


def _env_kwargs(args, instance=None):
    suite_time_limit = 0.0 if instance is None else float(instance.get("time_limit", 0.0))
    time_limit = suite_time_limit if suite_time_limit > 0 else args.time_limit
    profile_name = getattr(args, "stability_profile", "full")
    try:
        stage_two_enabled, stability_mode = STABILITY_PROFILES[profile_name]
    except KeyError as exc:
        raise ValueError(
            f"Unknown stability profile {profile_name!r}; "
            f"choose from {tuple(STABILITY_PROFILES)}."
        ) from exc
    requested_stability_time = float(
        getattr(args, "lexicographic_stability_time_limit", -1.0)
    )
    stability_time = (
        requested_stability_time
        if requested_stability_time >= 0
        else min(60.0, max(1.0, 0.10 * float(time_limit)))
    )
    return {
        "scip_time_limit": time_limit,
        "scip_verbosity": args.scip_verbosity,
        "scip_memory_limit_mb": args.memory_limit_mb,
        "scip_node_limit": args.node_limit,
        "cutsel_max_candidates": args.cutsel_max_candidates,
        "cutsel_max_selected_cuts": args.cutsel_max_selected_cuts,
        "warm_start_solution_file": None
        if args.warm_start == "none"
        else "auto",
        # Generic MILPs have no c_max/schedule_stability pair, so the environment
        # records skipped_non_petri_model without changing their solve.
        "lexicographic_schedule_stability": stage_two_enabled,
        "schedule_stability_mode": stability_mode,
        "lexicographic_fix_discrete_decisions": True,
        "lexicographic_free_double_decisions": True,
        "lexicographic_cmax_tolerance": 1e-6,
        "lexicographic_stability_time_limit": stability_time,
        "lexicographic_stability_node_limit": getattr(
            args, "lexicographic_stability_node_limit", 5000
        ),
        "schedule_linear_wait_weight": 1.0,
        "schedule_linear_max_wait_weight": 10.0,
        "schedule_cadence_deviation_weight": 25.0,
        "schedule_max_wait_time": 0.0,
        "schedule_wait_cap_mode": "hard",
        "schedule_wait_cap_excess_weight": 1000.0,
        "presolving": True,
        "separating": True,
        "conflict": True,
        "heuristics": True,
        "max_rounds_root": 1,
    }


def _build_agent(env, bundle, args, use_structure_rerank, decode_type=None):
    common = (
        env.m,
        bundle["policy"],
    )
    if bundle["high_level"] is not None:
        return HierarchyCutSelectAgent(
            *common,
            bundle["high_level"],
            None,
            args.sel_cuts_percent,
            bundle["device"],
            decode_type or args.decode_type,
            bundle["mean_std"],
            args.policy_type,
            max_candidates=args.cutsel_max_candidates,
            max_selected_cuts=args.cutsel_max_selected_cuts,
            use_structure_rerank=use_structure_rerank,
            structure_pool_factor=args.structure_pool_factor,
            structure_anchor_ratio=args.structure_anchor_ratio,
            structure_quality_weight=args.structure_quality_weight,
            structure_policy_weight=args.structure_policy_weight,
            structure_coverage_weight=args.structure_coverage_weight,
            structure_representation_weight=args.structure_representation_weight,
        )
    return CutSelectAgent(
        *common,
        None,
        args.sel_cuts_percent,
        bundle["device"],
        decode_type or args.decode_type,
        bundle["mean_std"],
        args.policy_type,
        max_candidates=args.cutsel_max_candidates,
        max_selected_cuts=args.cutsel_max_selected_cuts,
        use_structure_rerank=use_structure_rerank,
        structure_pool_factor=args.structure_pool_factor,
        structure_anchor_ratio=args.structure_anchor_ratio,
        structure_quality_weight=args.structure_quality_weight,
        structure_policy_weight=args.structure_policy_weight,
        structure_coverage_weight=args.structure_coverage_weight,
        structure_representation_weight=args.structure_representation_weight,
    )


def _load_acs_predictions(path):
    if not path:
        return {}
    payload = _load_json(resolve_path(path))
    raw = payload.get("predictions", payload)
    return {str(key): _normalize_acs_weights(value) for key, value in raw.items()}


def _weights_for_instance(default_weights, predictions, instance):
    for key in (
        instance["path"],
        instance["relative_path"],
        Path(instance["path"]).name,
        Path(instance["path"]).stem,
    ):
        if key in predictions:
            return predictions[key], key
    return default_weights, "global_default"


def _apply_acs_weights(model, weights):
    for parameter, value in weights.items():
        model.setParam(f"cutselection/hybrid/{parameter}", float(value))


def _has_incumbent(stats):
    if not stats:
        return False
    try:
        return int(stats.get("n_solutions", 0)) > 0
    except (TypeError, ValueError):
        return stats.get("best_obj") is not None


def _safe_label(text):
    return "".join(
        char if char.isalnum() or char in {"-", "_"} else "_" for char in str(text).strip()
    )


def _file_identity(path):
    if not path:
        return None
    resolved = Path(resolve_path(path))
    identity = {"path": str(resolved)}
    try:
        stat = resolved.stat()
    except OSError:
        identity["missing"] = True
    else:
        identity.update({"size": stat.st_size, "mtime_ns": stat.st_mtime_ns})
    return identity


def _checkpoint_signature(args, methods, seeds, instances, bundles):
    ignored = {"output_dir", "no_resume"}
    arguments = {
        key: value for key, value in vars(args).items() if key not in ignored
    }
    assets = {
        "manifest": _file_identity(args.manifest),
        "instances": [_file_identity(item["path"]) for item in instances],
        "code": [
            _file_identity(Path(__file__).resolve()),
            _file_identity(PROJECT_ROOT / "environments.py"),
            _file_identity(PROJECT_ROOT / "cutsel_agent_parallel.py"),
            _file_identity(PROJECT_ROOT / "pointer_net.py"),
            _file_identity(PROJECT_ROOT / "pointer_net_end_token.py"),
            _file_identity(PROJECT_ROOT / "beam_search.py"),
            _file_identity(PROJECT_ROOT / "global_const.py"),
            _file_identity(PROJECT_ROOT / "utils.py"),
        ],
        "bundles": {
            name: {
                "config": _file_identity(bundle.get("config")),
                "model": _file_identity(bundle.get("model")),
            }
            for name, bundle in sorted(bundles.items())
        },
        "acs_predictions": _file_identity(args.acs_predictions),
    }
    payload = {
        "checkpoint_version": 1,
        "arguments": arguments,
        "methods": methods,
        "seeds": seeds,
        "training_seed": args.training_seed,
        "instances": instances,
        "assets": assets,
    }
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _evaluation_key(path, method, seed):
    normalized_path = os.path.normcase(str(Path(path).resolve()))
    return json.dumps(
        [normalized_path, str(method), int(seed)],
        ensure_ascii=False,
        separators=(",", ":"),
    )


def _checkpoint_path(args, signature):
    output_dir = Path(resolve_path(args.output_dir))
    safe_label = _safe_label(args.run_label) or "unlabeled"
    filename = (
        f"{safe_label}__trainseed_{args.training_seed}__{signature[:16]}.jsonl"
    )
    return output_dir / ".checkpoints" / filename


def _write_checkpoint_header(path, signature):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    record = {
        "record_type": "meta",
        "checkpoint_version": 1,
        "signature": signature,
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }
    with open(temporary, "w", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(record, ensure_ascii=False) + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def _load_checkpoint(path, signature):
    if not path.exists():
        _write_checkpoint_header(path, signature)
        return {}, None

    rows_by_key = {}
    complete_record = None
    meta_seen = False
    with open(path, "r", encoding="utf-8") as stream:
        lines = stream.readlines()
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            if line_number == len(lines):
                warnings.warn(
                    f"Ignoring an incomplete final checkpoint line in {path}.",
                    RuntimeWarning,
                )
                continue
            raise RuntimeError(
                f"Corrupt checkpoint record at {path}:{line_number}"
            )
        record_type = record.get("record_type")
        if record_type == "meta":
            meta_seen = True
            if record.get("signature") != signature:
                raise RuntimeError(
                    f"Checkpoint signature mismatch: {path}. "
                    "Use a different run label/output directory or --no_resume."
                )
        elif record_type == "row":
            row = record.get("row") or {}
            if row.get("error"):
                continue
            key = record.get("key") or _evaluation_key(
                row["path"], row["method"], row["seed"]
            )
            rows_by_key[key] = row
        elif record_type == "complete":
            complete_record = record
    if not meta_seen:
        raise RuntimeError(f"Checkpoint metadata is missing: {path}")
    return rows_by_key, complete_record


def _append_checkpoint_record(path, record):
    with open(path, "a", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(record, ensure_ascii=False) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def _run_one(method, instance, seed, args, bundles, acs_weights, predictions):
    set_global_seed(seed)
    path = Path(instance["path"])
    env_kwargs = _env_kwargs(args, instance)
    env = SCIPCutSelEnv(
        str(path.parent),
        scip_seed=seed,
        seed=seed,
        single_instance_file=path.name,
        **env_kwargs,
    )
    started = datetime.now().isoformat(timespec="seconds")
    wall_started = time.perf_counter()
    weights = None
    weight_source = None
    requested_solution = None
    bundle = None
    decode_type = None
    if args.solution_dir:
        solution_root = Path(resolve_path(args.solution_dir))
        solution_root.mkdir(parents=True, exist_ok=True)
        safe_suite = "".join(
            char if char.isalnum() or char in "-_" else "_"
            for char in str(instance.get("suite", "suite"))
        )
        safe_instance = "".join(
            char if char.isalnum() or char in "-_" else "_" for char in path.stem
        )
        training_seed = int(getattr(args, "training_seed", -1))
        safe_label = "".join(
            char if char.isalnum() or char in "-_" else "_"
            for char in str(getattr(args, "run_label", "") or "unlabeled")
        )
        requested_solution = solution_root / (
            f"{safe_suite}__{safe_instance}__{method}__"
            f"solverseed_{seed}__trainseed_{training_seed}__{safe_label}.sol"
        )
    try:
        env.reset()
        if method == "scip_default":
            stats = env.solve_default(solution_file=requested_solution)
        elif method == "adaptive_cutsel":
            weights, weight_source = _weights_for_instance(
                acs_weights, predictions, instance
            )
            _apply_acs_weights(env.m, weights)
            stats = env.solve_default(solution_file=requested_solution)
        else:
            method_spec = {
                "hem": ("hem", "greedy", False),
                "hem_beam": ("hem", "beam_search", False),
                "hem_structure": ("proposed", "greedy", True),
                "a3c": ("a3c", "greedy", False),
                "beam_search": ("a3c", "beam_search", False),
                "proposed": ("proposed", "beam_search", True),
                "rdmct_feature_only": ("rdmct_feature_only", "greedy", False),
                "rdmct_a3c": ("proposed", args.decode_type, True),
            }
            bundle_name, decode_type, structure_rerank = method_spec[method]
            bundle = bundles.get(bundle_name)
            if bundle is None:
                raise RuntimeError(f"skipped: no checkpoint supplied for {method}")
            stats = env.step(
                _build_agent(
                    env,
                    bundle,
                    args,
                    use_structure_rerank=structure_rerank,
                    decode_type=decode_type,
                ),
                solution_file=requested_solution,
            )
        error = None
    except Exception as exc:
        stats = {}
        error = f"{type(exc).__name__}: {exc}"
        try:
            env.m.freeProb()
        except Exception:
            pass
    solution_file = stats.get("solution_file")
    if solution_file:
        solution_file = str(Path(solution_file).resolve())
    solution_error = stats.get("solution_write_error")
    wall_time = time.perf_counter() - wall_started
    cutsel_telemetry = stats.get("cutsel_telemetry") or {}
    phase_times = cutsel_telemetry.get("phase_time_seconds") or {}
    return {
        **instance,
        "instance": path.name,
        "method": method,
        "seed": seed,
        "training_seed": getattr(args, "training_seed", -1),
        "run_label": getattr(args, "run_label", ""),
        "stability_profile": getattr(args, "stability_profile", "full"),
        "lexicographic_schedule_stability": env_kwargs[
            "lexicographic_schedule_stability"
        ],
        "schedule_stability_mode": env_kwargs["schedule_stability_mode"],
        "lexicographic_stability_time_limit": env_kwargs[
            "lexicographic_stability_time_limit"
        ],
        "warm_start": getattr(args, "warm_start", "none"),
        "time_limit": float(env_kwargs["scip_time_limit"]),
        "started_at": started,
        "status": stats.get("status"),
        "primary_status": stats.get("primary_status"),
        "stability_status": stats.get("stability_status"),
        "solving_time": stats.get("solving_time"),
        "end_to_end_time": wall_time,
        "cutsel_callback_calls": cutsel_telemetry.get("callback_calls", 0),
        "cutsel_callback_time": cutsel_telemetry.get("callback_time_seconds", 0.0),
        "cutsel_feature_time": phase_times.get("feature_extraction", 0.0),
        "cutsel_device_transfer_time": phase_times.get("device_transfer", 0.0),
        "cutsel_policy_inference_time": phase_times.get("policy_inference", 0.0),
        "cutsel_structure_rerank_time": phase_times.get("structure_rerank", 0.0),
        "cutsel_root_calls": cutsel_telemetry.get("root_calls", 0),
        "cutsel_nonroot_calls": cutsel_telemetry.get("nonroot_calls", 0),
        "nodes": stats.get("ntotal_nodes"),
        "gap": stats.get("primal_dual_gap"),
        "primal_dual_integral": stats.get("primaldualintegral"),
        "best_objective": stats.get("best_obj"),
        "schedule_total_wait": stats.get("schedule_total_wait"),
        "schedule_max_wait": stats.get("schedule_max_wait"),
        "schedule_cadence_cv": stats.get("schedule_cadence_cv"),
        "schedule_cadence_deviation_sum": stats.get("schedule_cadence_deviation_sum"),
        "n_solutions": stats.get("n_solutions"),
        "has_incumbent": _has_incumbent(stats),
        "solution_file": solution_file,
        "solution_write_error": solution_error,
        "acs_weights": weights,
        "acs_weight_source": weight_source,
        "policy_model": None if bundle is None else bundle["model"],
        "feature_dim": None if bundle is None else bundle["feature_dim"],
        "structure_rerank": method in {"hem_structure", "proposed", "rdmct_a3c"},
        "decode_type": decode_type,
        "error": error,
    }


def _finite_values(rows, key):
    values = []
    for row in rows:
        try:
            value = float(row.get(key))
        except (TypeError, ValueError):
            continue
        if math.isfinite(value):
            values.append(value)
    return values


def _mean_std(values):
    if not values:
        return None, None, None
    return (
        float(np.mean(values)),
        float(np.std(values, ddof=1)) if len(values) > 1 else 0.0,
        float(np.median(values)),
    )


def _shifted_geometric_mean(values, shift=1.0):
    if not values:
        return None
    values = np.asarray(values, dtype=np.float64)
    return float(np.exp(np.mean(np.log(np.maximum(values + shift, 1e-12)))) - shift)


def _bootstrap_mean_ci(values, seed=2027, samples=2000):
    if not values:
        return None, None
    values = np.asarray(values, dtype=np.float64)
    if len(values) == 1:
        return float(values[0]), float(values[0])
    rng = np.random.default_rng(seed)
    means = np.mean(
        rng.choice(values, size=(samples, len(values)), replace=True),
        axis=1,
    )
    low, high = np.quantile(means, [0.025, 0.975])
    return float(low), float(high)


def _aggregate(rows):
    grouped = defaultdict(list)
    for row in rows:
        grouped[
            (
                row["method"],
                row["suite"],
                row["family"],
                row["scale"],
                row["split"],
                row.get("stability_profile", "full"),
            )
        ].append(row)

    default_by_pair = {
        (
            row["path"],
            row["seed"],
            row.get("stability_profile", "full"),
        ): row
        for row in rows
        if row["method"] == "scip_default"
    }
    summary = []
    for group_key, group_rows in sorted(grouped.items()):
        method, suite, family, scale, split, stability_profile = group_key
        times = _finite_values(group_rows, "solving_time")
        end_to_end_times = _finite_values(group_rows, "end_to_end_time")
        callback_times = _finite_values(group_rows, "cutsel_callback_time")
        nodes = _finite_values(group_rows, "nodes")
        gaps = _finite_values(
            [row for row in group_rows if row.get("has_incumbent")], "gap"
        )
        pdis = _finite_values(
            [row for row in group_rows if row.get("has_incumbent")],
            "primal_dual_integral",
        )
        objectives = _finite_values(
            [row for row in group_rows if row.get("has_incumbent")],
            "best_objective",
        )
        total_waits = _finite_values(
            [row for row in group_rows if row.get("has_incumbent")],
            "schedule_total_wait",
        )
        max_waits = _finite_values(
            [row for row in group_rows if row.get("has_incumbent")],
            "schedule_max_wait",
        )
        cadence_cvs = _finite_values(
            [row for row in group_rows if row.get("has_incumbent")],
            "schedule_cadence_cv",
        )
        cadence_deviations = _finite_values(
            [row for row in group_rows if row.get("has_incumbent")],
            "schedule_cadence_deviation_sum",
        )
        speedups = []
        node_ratios = []
        for row in group_rows:
            default = default_by_pair.get(
                (
                    row["path"],
                    row["seed"],
                    row.get("stability_profile", "full"),
                )
            )
            if not default:
                continue
            try:
                if float(row["solving_time"]) > 0:
                    speedups.append(float(default["solving_time"]) / float(row["solving_time"]))
                if float(row["nodes"]) > 0:
                    node_ratios.append(float(default["nodes"]) / float(row["nodes"]))
            except (TypeError, ValueError):
                pass
        mean_time, std_time, median_time = _mean_std(times)
        mean_gap, std_gap, median_gap = _mean_std(gaps)
        mean_pdi, std_pdi, median_pdi = _mean_std(pdis)
        mean_objective, std_objective, median_objective = _mean_std(objectives)
        mean_speedup, std_speedup, median_speedup = _mean_std(speedups)
        ci_low, ci_high = _bootstrap_mean_ci(speedups)
        summary.append(
            {
                "method": method,
                "suite": suite,
                "family": family,
                "scale": scale,
                "split": split,
                "stability_profile": stability_profile,
                "runs": len(group_rows),
                "completed": sum(row["error"] is None for row in group_rows),
                "with_incumbent": sum(bool(row["has_incumbent"]) for row in group_rows),
                "optimal": sum(str(row["status"]).lower() == "optimal" for row in group_rows),
                "incumbent_rate": sum(bool(row["has_incumbent"]) for row in group_rows) / len(group_rows),
                "optimal_rate": sum(str(row["status"]).lower() == "optimal" for row in group_rows) / len(group_rows),
                "mean_time": mean_time,
                "std_time": std_time,
                "median_time": median_time,
                "shifted_geomean_time": _shifted_geometric_mean(times),
                "mean_end_to_end_time": _mean_std(end_to_end_times)[0],
                "mean_cutsel_callback_time": _mean_std(callback_times)[0],
                "mean_nodes": _mean_std(nodes)[0],
                "mean_gap": mean_gap,
                "std_gap": std_gap,
                "median_gap": median_gap,
                "mean_primal_dual_integral": mean_pdi,
                "std_primal_dual_integral": std_pdi,
                "median_primal_dual_integral": median_pdi,
                "mean_best_objective": mean_objective,
                "std_best_objective": std_objective,
                "median_best_objective": median_objective,
                "mean_par2_time": _mean_std(
                    [
                        float(row["solving_time"])
                        if str(row.get("status")).lower() == "optimal"
                        else 2.0 * float(row.get("time_limit", 0.0))
                        for row in group_rows
                        if row.get("error") is None
                        and row.get("solving_time") is not None
                        and float(row.get("time_limit", 0.0)) > 0
                    ]
                )[0],
                "mean_schedule_total_wait": _mean_std(total_waits)[0],
                "mean_schedule_max_wait": _mean_std(max_waits)[0],
                "mean_schedule_cadence_cv": _mean_std(cadence_cvs)[0],
                "mean_schedule_cadence_deviation_sum": _mean_std(cadence_deviations)[0],
                "mean_speedup_vs_scip": mean_speedup,
                "std_speedup_vs_scip": std_speedup,
                "median_speedup_vs_scip": median_speedup,
                "speedup_95ci_low": ci_low,
                "speedup_95ci_high": ci_high,
                "mean_node_reduction_factor": _mean_std(node_ratios)[0],
            }
        )
    return summary


def _paired_significance(rows):
    """Paired effect sizes and one-sided Wilcoxon tests with Holm correction."""
    try:
        from scipy.stats import wilcoxon
    except (ImportError, MemoryError):
        wilcoxon = None

    by_method = defaultdict(dict)
    for row in rows:
        if row.get("error") is not None:
            continue
        training_seed = int(row.get("training_seed", -1))
        by_method[row["method"]][
            (row["path"], row["seed"], training_seed)
        ] = row

    proposed = by_method.get("proposed", by_method.get("rdmct_a3c", {}))
    comparisons = []
    for baseline_name in (
        "scip_default",
        "hem",
        "hem_beam",
        "hem_structure",
        "adaptive_cutsel",
        "a3c",
        "beam_search",
        "rdmct_feature_only",
    ):
        baseline = by_method.get(baseline_name, {})
        if not baseline:
            continue
        paired_rows = []
        for proposed_key, proposed_row in proposed.items():
            path, solver_seed, training_seed = proposed_key
            if baseline_name in {"scip_default", "adaptive_cutsel"}:
                matches = [
                    row
                    for (base_path, base_solver_seed, _), row in baseline.items()
                    if base_path == path and base_solver_seed == solver_seed
                ]
                baseline_row = matches[0] if matches else None
            else:
                baseline_row = baseline.get((path, solver_seed, training_seed))
            if baseline_row is not None:
                paired_rows.append((baseline_row, proposed_row))

        def finite_value(row, key):
            try:
                value = float(row.get(key))
            except (TypeError, ValueError):
                return None
            return value if math.isfinite(value) else None

        pdi_values = []
        objective_improvements = []
        gap_reductions = []
        optimal_time_improvements = []
        for baseline_row, proposed_row in paired_rows:
            if baseline_row.get("has_incumbent") and proposed_row.get("has_incumbent"):
                baseline_pdi = finite_value(baseline_row, "primal_dual_integral")
                proposed_pdi = finite_value(proposed_row, "primal_dual_integral")
                if baseline_pdi is not None and proposed_pdi is not None:
                    pdi_values.append((baseline_pdi, proposed_pdi))
                baseline_obj = finite_value(baseline_row, "best_objective")
                proposed_obj = finite_value(proposed_row, "best_objective")
                if baseline_obj is not None and proposed_obj is not None and abs(baseline_obj) > 1e-12:
                    objective_improvements.append(
                        100.0 * (baseline_obj - proposed_obj) / abs(baseline_obj)
                    )
                baseline_gap = finite_value(baseline_row, "gap")
                proposed_gap = finite_value(proposed_row, "gap")
                if baseline_gap is not None and proposed_gap is not None:
                    gap_reductions.append(baseline_gap - proposed_gap)
            if (
                str(baseline_row.get("status")).lower() == "optimal"
                and str(proposed_row.get("status")).lower() == "optimal"
            ):
                baseline_time = finite_value(baseline_row, "solving_time")
                proposed_time = finite_value(proposed_row, "solving_time")
                if baseline_time is not None and proposed_time is not None and baseline_time > 0:
                    optimal_time_improvements.append(
                        100.0 * (baseline_time - proposed_time) / baseline_time
                    )

        improvements = []
        differences = []
        for baseline_pdi, proposed_pdi in pdi_values:
            differences.append(baseline_pdi - proposed_pdi)
            if baseline_pdi > 0:
                improvements.append(100.0 * (baseline_pdi - proposed_pdi) / baseline_pdi)
        nonzero = [value for value in differences if abs(value) > 1e-12]
        p_value = None
        if wilcoxon is not None and len(nonzero) >= 5:
            p_value = float(
                wilcoxon(
                    differences,
                    alternative="greater",
                    zero_method="wilcox",
                    method="auto",
                ).pvalue
            )
        comparisons.append(
            {
                "baseline": baseline_name,
                "paired_total": len(paired_rows),
                "baseline_incumbent_rate": None
                if not paired_rows
                else sum(bool(base.get("has_incumbent")) for base, _ in paired_rows) / len(paired_rows),
                "proposed_incumbent_rate": None
                if not paired_rows
                else sum(bool(prop.get("has_incumbent")) for _, prop in paired_rows) / len(paired_rows),
                "paired_runs": len(pdi_values),
                "wins": sum(value > 0 for value in differences),
                "ties": sum(abs(value) <= 1e-12 for value in differences),
                "win_rate": None
                if not differences
                else sum(value > 0 for value in differences) / len(differences),
                "mean_pdi_improvement_percent": None
                if not improvements
                else float(np.mean(improvements)),
                "median_pdi_improvement_percent": None
                if not improvements
                else float(np.median(improvements)),
                "objective_pairs": len(objective_improvements),
                "mean_objective_improvement_percent": None
                if not objective_improvements
                else float(np.mean(objective_improvements)),
                "gap_pairs": len(gap_reductions),
                "mean_gap_absolute_reduction": None
                if not gap_reductions
                else float(np.mean(gap_reductions)),
                "optimal_time_pairs": len(optimal_time_improvements),
                "mean_optimal_time_improvement_percent": None
                if not optimal_time_improvements
                else float(np.mean(optimal_time_improvements)),
                "wilcoxon_p": p_value,
                "holm_p": None,
            }
        )

    testable = sorted(
        (item for item in comparisons if item["wilcoxon_p"] is not None),
        key=lambda item: item["wilcoxon_p"],
    )
    running_adjusted = 0.0
    total_tests = len(testable)
    for rank, item in enumerate(testable):
        adjusted = min(1.0, (total_tests - rank) * item["wilcoxon_p"])
        running_adjusted = max(running_adjusted, adjusted)
        item["holm_p"] = running_adjusted

    required_claim_baselines = {"scip_default", "hem", "hem_beam", "hem_structure"}
    claim_ready = required_claim_baselines.issubset(
        {item["baseline"] for item in comparisons}
    ) and all(
        item["paired_runs"] >= 10
        and item["mean_pdi_improvement_percent"] is not None
        and item["mean_pdi_improvement_percent"] >= 5.0
        and item["win_rate"] is not None
        and item["win_rate"] >= 0.6
        and item["proposed_incumbent_rate"] is not None
        and item["baseline_incumbent_rate"] is not None
        and item["proposed_incumbent_rate"] >= item["baseline_incumbent_rate"]
        and item["holm_p"] is not None
        and item["holm_p"] < 0.05
        for item in comparisons
        if item["baseline"] in required_claim_baselines
    )
    module_effects = []
    for effect, baseline_name, target_name in (
        ("beam_without_structure", "hem", "hem_beam"),
        ("structure_with_greedy", "hem", "hem_structure"),
        ("structure_with_beam", "hem_beam", "proposed"),
        ("beam_with_structure", "hem_structure", "proposed"),
    ):
        baseline_rows = by_method.get(baseline_name, {})
        target_rows = by_method.get(target_name, {})
        improvements = []
        for key in sorted(set(baseline_rows).intersection(target_rows)):
            baseline_row = baseline_rows[key]
            target_row = target_rows[key]
            if not baseline_row.get("has_incumbent") or not target_row.get("has_incumbent"):
                continue
            try:
                baseline_pdi = float(baseline_row["primal_dual_integral"])
                target_pdi = float(target_row["primal_dual_integral"])
            except (TypeError, ValueError):
                continue
            if math.isfinite(baseline_pdi) and math.isfinite(target_pdi) and baseline_pdi > 0:
                improvements.append(100.0 * (baseline_pdi - target_pdi) / baseline_pdi)
        module_effects.append(
            {
                "effect": effect,
                "baseline": baseline_name,
                "target": target_name,
                "paired_runs": len(improvements),
                "wins": sum(value > 0 for value in improvements),
                "win_rate": None
                if not improvements
                else sum(value > 0 for value in improvements) / len(improvements),
                "mean_pdi_improvement_percent": None
                if not improvements
                else float(np.mean(improvements)),
                "median_pdi_improvement_percent": None
                if not improvements
                else float(np.median(improvements)),
            }
        )
    return {
        "metric": "primal_dual_integral",
        "test": "paired one-sided Wilcoxon signed-rank",
        "multiple_testing": "Holm",
        "claim_ready": claim_ready,
        "claim_rule": (
            "For every baseline: >=10 valid pairs, mean PDI improvement >=5%, "
            "win rate >=60%, no lower incumbent rate, and Holm-adjusted p<0.05."
        ),
        "comparisons": comparisons,
        "module_effects": module_effects,
    }


def _write_csv(path, rows):
    if not rows:
        return
    fieldnames = list(rows[0])
    with open(path, "w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            serializable = {
                key: json.dumps(value, ensure_ascii=False)
                if isinstance(value, (dict, list))
                else value
                for key, value in row.items()
            }
            writer.writerow(serializable)


def _fmt(value):
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return f"{value:.4g}"
    return str(value)


def _write_report(path, meta, summary, significance):
    lines = [
        "# CIE Cut-Selection Benchmark Report",
        "",
        "This report is generated from raw per-instance, per-seed records. "
        "No missing or failed run is imputed.",
        "",
        "## Run configuration",
        "",
        f"- Methods: `{', '.join(meta['methods'])}`",
        f"- Seeds: `{meta['seeds']}`",
        f"- Time limit: `{meta['time_limit']} s` per run",
        f"- Schedule-stability profile: `{meta.get('stability_profile', 'full')}`",
        f"- Instances: `{meta['instance_count']}`",
        f"- Empty suites: `{len(meta['empty_suites'])}`",
        "",
        "## Aggregated results",
        "",
        "| Method | Stability | Suite | Scale | Runs | Inc. rate | Opt. rate | SCIP time | End-to-end | Callback | PAR-2 | Best obj. | Gap | PDI | Max wait | Speedup vs SCIP (95% CI) |",
        "| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in summary:
        speedup = _fmt(row["mean_speedup_vs_scip"])
        if row["speedup_95ci_low"] is not None:
            speedup += (
                f" [{_fmt(row['speedup_95ci_low'])}, "
                f"{_fmt(row['speedup_95ci_high'])}]"
            )
        lines.append(
            f"| {METHOD_LABELS.get(row['method'], row['method'])} | "
            f"{row.get('stability_profile', 'full')} | {row['suite']} | {row['scale']} | "
            f"{row['runs']} | {_fmt(row['incumbent_rate'])} | {_fmt(row['optimal_rate'])} | "
            f"{_fmt(row['mean_time'])}+/-{_fmt(row['std_time'])} | "
            f"{_fmt(row['mean_end_to_end_time'])} | "
            f"{_fmt(row['mean_cutsel_callback_time'])} | "
            f"{_fmt(row['mean_par2_time'])} | {_fmt(row['mean_best_objective'])} | "
            f"{_fmt(row['mean_gap'])} | {_fmt(row['mean_primal_dual_integral'])} | "
            f"{_fmt(row['mean_schedule_max_wait'])} | "
            f"{speedup} |"
        )
    lines.extend(
        [
            "",
            "## Paired evidence for the proposed method",
            "",
            f"- Claim-ready gate: **{'PASS' if significance['claim_ready'] else 'NOT YET PASSED'}**",
            f"- Rule: {significance['claim_rule']}",
            "",
            "| Proposed vs. | All pairs | PDI pairs | Base/Prop incumbent rate | Wins | Win rate | Mean PDI improvement | Wilcoxon p | Holm p |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for item in significance["comparisons"]:
        lines.append(
            f"| {METHOD_LABELS.get(item['baseline'], item['baseline'])} | "
            f"{item['paired_total']} | {item['paired_runs']} | "
            f"{_fmt(item['baseline_incumbent_rate'])}/{_fmt(item['proposed_incumbent_rate'])} | "
            f"{item['wins']} | {_fmt(item['win_rate'])} | "
            f"{_fmt(item['mean_pdi_improvement_percent'])} | "
            f"{_fmt(item['wilcoxon_p'])} | {_fmt(item['holm_p'])} |"
        )
    lines.extend(
        [
            "",
            "## Paired secondary effects",
            "",
            "Positive objective/time improvement and positive absolute gap reduction favor Proposed.",
            "",
            "| Proposed vs. | Objective pairs | Mean objective improvement | Gap pairs | Mean absolute gap reduction | Both-optimal time pairs | Mean time improvement |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for item in significance["comparisons"]:
        lines.append(
            f"| {METHOD_LABELS.get(item['baseline'], item['baseline'])} | "
            f"{item['objective_pairs']} | {_fmt(item['mean_objective_improvement_percent'])}% | "
            f"{item['gap_pairs']} | {_fmt(item['mean_gap_absolute_reduction'])} | "
            f"{item['optimal_time_pairs']} | {_fmt(item['mean_optimal_time_improvement_percent'])}% |"
        )
    lines.extend(
        [
            "",
            "## Controlled module effects (PDI)",
            "",
            "Each row changes one module while holding the paired checkpoint family and decode setting fixed where applicable.",
            "",
            "| Effect | Baseline -> Target | Pairs | Win rate | Mean improvement | Median improvement |",
            "| --- | --- | ---: | ---: | ---: | ---: |",
        ]
    )
    for item in significance.get("module_effects", []):
        lines.append(
            f"| {item['effect']} | {METHOD_LABELS.get(item['baseline'], item['baseline'])} -> "
            f"{METHOD_LABELS.get(item['target'], item['target'])} | {item['paired_runs']} | "
            f"{_fmt(item['win_rate'])} | {_fmt(item['mean_pdi_improvement_percent'])}% | "
            f"{_fmt(item['median_pdi_improvement_percent'])}% |"
        )
    if meta["empty_suites"]:
        lines.extend(["", "## Empty suites", ""])
        for suite in meta["empty_suites"]:
            lines.append(
                f"- `{suite['name']}`: no LP/MPS/CIP file under "
                f"`{suite['root']}` matching `{suite['glob']}`."
            )
    lines.extend(
        [
            "",
            "## Interpretation guardrails",
            "",
            "- Compare methods only on identical instance-seed pairs.",
            "- Metric directions: solving time, PAR-2, best objective, gap, and PDI are all lower-is-better for these minimization models.",
            "- Best objective measures incumbent quality; gap measures remaining certificate uncertainty; PDI measures anytime primal-dual progress; time is a speed claim only when solve outcomes are comparable.",
            "- Mean node count is diagnostic, not a monotone quality metric: fewer nodes can mean an efficient tree or a stalled root relaxation.",
            "- Report timeout-aware gap and primal-dual integral beside wall-clock time.",
            "- `adaptive_cutsel` is the original four-parameter SCIP hybrid selector "
            "interface. It is the full learned ACS method only when `--acs_predictions` "
            "contains held-out predictions from a separately trained ACS model.",
            "- `hem` requires a separately trained 13-feature checkpoint; using the "
            "23-feature checkpoint would invalidate the ablation.",
            "- `hem_beam` reuses the exact HEM checkpoint and changes only greedy to beam decoding.",
            "- `hem_structure` reuses the exact Proposed checkpoint and structure reranking, changing only beam to greedy decoding.",
            "- `a3c` and `beam_search` share the same independently trained flat-A3C "
            "checkpoint and differ only in greedy versus beam decoding.",
            "- `proposed` uses the separately trained 23-feature role-submodular "
            "checkpoint; every method receives the same SCIP, memory, warm-start, "
            "instance, and solver-seed limits.",
            "- Schedule wait and cadence metrics are observational in the benchmark; "
            "no method receives an extra postprocessing budget.",
        ]
    )
    with open(path, "w", encoding="utf-8") as stream:
        stream.write("\n".join(lines) + "\n")


def main():
    args = _parse_args()
    methods = _parse_methods(args.methods)
    if args.stability_profile != "full" and methods != ["proposed"]:
        raise ValueError(
            "stage2_off/linear_off are reserved for the controlled schedule-"
            "stability ablation and require --methods proposed. All algorithm "
            "comparisons must use --stability_profile full."
        )
    seeds = _parse_int_list(args.seeds)
    _, instances, empty_suites = _discover_instances(
        args.manifest,
        args.max_instances_per_suite,
        {item.strip() for item in args.splits.split(",") if item.strip()},
        {item.strip() for item in args.suites.split(",") if item.strip()},
    )
    if empty_suites and args.fail_on_empty_suite:
        raise RuntimeError(f"Empty benchmark suites: {empty_suites}")
    if not instances:
        raise RuntimeError(
            "No benchmark instances were discovered. Check the suite manifest and "
            "place .lp/.mps/.cip files under MILPdata."
        )

    bundles = {}
    proposed_bundle = None
    if {"hem", "hem_beam"}.intersection(methods):
        bundles["hem"] = _load_policy_bundle(
            args.hem_config,
            args.hem_model,
            13,
            args.policy_type,
            "none",
            args.device,
        )
    if {"a3c", "beam_search"}.intersection(methods):
        bundles["a3c"] = _load_policy_bundle(
            args.a3c_config,
            args.a3c_model,
            13,
            args.policy_type,
            "none",
            args.device,
        )
    if "rdmct_feature_only" in methods:
        feature_only_bundle = _load_policy_bundle(
            args.feature_only_config,
            args.feature_only_model,
            23,
            args.policy_type,
            "none",
            args.device,
        )
        bundles["rdmct_feature_only"] = feature_only_bundle
    if {"hem_structure", "proposed", "rdmct_a3c"}.intersection(methods):
        proposed_bundle = _load_policy_bundle(
            args.proposed_config,
            args.proposed_model,
            23,
            args.policy_type,
            "role_submodular_v1",
            args.device,
        )
        bundles["proposed"] = proposed_bundle
    acs_weights = _normalize_acs_weights(args.acs_weights)
    predictions = _load_acs_predictions(args.acs_predictions)

    checkpoint_file = None
    recovered_rows = {}
    if not args.no_resume:
        checkpoint_signature = _checkpoint_signature(
            args, methods, seeds, instances, bundles
        )
        checkpoint_file = _checkpoint_path(args, checkpoint_signature)
        recovered_rows, complete_record = _load_checkpoint(
            checkpoint_file, checkpoint_signature
        )
        print(
            f"Resume checkpoint: {checkpoint_file} "
            f"({len(recovered_rows)} completed evaluations)",
            flush=True,
        )
        if complete_record:
            artifacts = complete_record.get("artifacts") or []
            if artifacts and all(Path(item).exists() for item in artifacts):
                print(
                    "Campaign already complete; all recorded artifacts still exist. "
                    "Skipping this batch.",
                    flush=True,
                )
                for artifact in artifacts:
                    print(f"Artifact: {artifact}", flush=True)
                return

    rows = []
    total = sum(
        len(instance.get("solver_seeds") or seeds) * len(methods)
        for instance in instances
    )
    completed = 0
    pair_index = 0
    for instance in instances:
        for seed in (instance.get("solver_seeds") or seeds):
            rotation = pair_index % len(methods)
            rotated_methods = methods[rotation:] + methods[:rotation]
            pair_index += 1
            for method in rotated_methods:
                completed += 1
                evaluation_key = _evaluation_key(instance["path"], method, seed)
                recovered = recovered_rows.get(evaluation_key)
                print(
                    f"[{completed}/{total}] {method} | {instance['suite']} | "
                    f"{Path(instance['path']).name} | seed={seed}"
                    f"{' | resumed' if recovered is not None else ''}",
                    flush=True,
                )
                if recovered is not None:
                    rows.append(recovered)
                    continue
                row = _run_one(
                    method,
                    instance,
                    seed,
                    args,
                    bundles,
                    acs_weights,
                    predictions,
                )
                rows.append(row)
                if checkpoint_file is not None and not row.get("error"):
                    _append_checkpoint_record(
                        checkpoint_file,
                        {
                            "record_type": "row",
                            "key": evaluation_key,
                            "saved_at": datetime.now().isoformat(timespec="seconds"),
                            "row": row,
                        },
                    )
                    recovered_rows[evaluation_key] = row
                elif row.get("error"):
                    print(
                        f"Not checkpointed; this evaluation will be retried: "
                        f"{row['error']}",
                        flush=True,
                    )

    summary = _aggregate(rows)
    output_dir = Path(resolve_path(args.output_dir))
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_label = _safe_label(args.run_label)
    label_part = f"_{safe_label}" if safe_label else ""
    prefix = output_dir / f"cie_benchmark{label_part}_{timestamp}"
    # Persist the expensive per-run observations before importing/statistically
    # analysing SciPy. This keeps a recoverable raw artifact even if the process
    # is under memory pressure after a long SCIP campaign.
    _write_csv(f"{prefix}_raw.csv", rows)
    significance = _paired_significance(rows)
    meta = {
        "manifest": str(resolve_path(args.manifest)),
        "methods": methods,
        "seeds": seeds,
        "training_seed": args.training_seed,
        "run_label": args.run_label,
        "stability_profile": args.stability_profile,
        "lexicographic_stability_time_limit": args.lexicographic_stability_time_limit,
        "lexicographic_stability_node_limit": args.lexicographic_stability_node_limit,
        "time_limit": args.time_limit,
        "node_limit": args.node_limit,
        "memory_limit_mb": args.memory_limit_mb,
        "instance_count": len(instances),
        "empty_suites": empty_suites,
        "hem_model": None if bundles.get("hem") is None else bundles["hem"]["model"],
        "a3c_model": None if bundles.get("a3c") is None else bundles["a3c"]["model"],
        "feature_only_model": None
        if bundles.get("rdmct_feature_only") is None
        else bundles["rdmct_feature_only"]["model"],
        "proposed_model": None
        if proposed_bundle is None
        else proposed_bundle["model"],
        "acs_global_weights": acs_weights,
        "acs_predictions": args.acs_predictions,
        "warm_start": args.warm_start,
        "structure_submodular": {
            "pool_factor": args.structure_pool_factor,
            "anchor_ratio": args.structure_anchor_ratio,
            "quality_weight": args.structure_quality_weight,
            "policy_weight": args.structure_policy_weight,
            "coverage_weight": args.structure_coverage_weight,
            "representation_weight": args.structure_representation_weight,
        },
    }
    with open(f"{prefix}.json", "w", encoding="utf-8") as stream:
        json.dump(
            {
                "meta": meta,
                "summary": summary,
                "paired_significance": significance,
                "rows": rows,
            },
            stream,
            ensure_ascii=False,
            indent=2,
        )
    _write_csv(f"{prefix}_summary.csv", summary)
    _write_report(f"{prefix}.md", meta, summary, significance)
    artifacts = [
        str(Path(f"{prefix}.json")),
        str(Path(f"{prefix}_raw.csv")),
        str(Path(f"{prefix}_summary.csv")),
        str(Path(f"{prefix}.md")),
    ]
    if checkpoint_file is not None and len(recovered_rows) == total:
        _append_checkpoint_record(
            checkpoint_file,
            {
                "record_type": "complete",
                "completed_at": datetime.now().isoformat(timespec="seconds"),
                "artifacts": artifacts,
            },
        )
    print(f"JSON: {prefix}.json")
    print(f"Raw CSV: {prefix}_raw.csv")
    print(f"Summary CSV: {prefix}_summary.csv")
    print(f"Markdown: {prefix}.md")
    if checkpoint_file is not None:
        print(f"Resume checkpoint: {checkpoint_file}")


if __name__ == "__main__":
    main()

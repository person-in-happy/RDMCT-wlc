import argparse
import json
import os
import subprocess
from pathlib import Path
from typing import List

from path_utils import PROJECT_ROOT, resolve_path
from petri_mip_generator import (
    PetriMIPConfig,
    generate_petri_mip_instance,
    get_petri_model_description_path,
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate Petri MIP and solve by RL cut selection with beam search.")
    parser.add_argument("--config_file", type=str, default="configs/petri_mip_test_config.json")
    parser.add_argument("--test_model_path", type=str, required=True)
    parser.add_argument("--instance_dir", type=str, default="generated_instances/petri")
    parser.add_argument("--instance_name", type=str, default="petri_batch10_fullflow_v7.lp")
    parser.add_argument("--sel_cuts_percent", type=float, default=0.2)
    parser.add_argument("--policy_type", type=str, default="with_token")
    parser.add_argument("--use_cutsel_percent_policy", type=str, default="True")
    parser.add_argument("--test_decode_type", type=str, default="beam_search")
    parser.add_argument("--time_limit", type=float, default=-1.0)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--scip_seed", type=int, default=1)
    parser.add_argument("--instance_type", type=str, default="petri_transfer")
    parser.add_argument("--num_batches", type=int, default=10)
    parser.add_argument("--num_pm", type=int, default=2)
    parser.add_argument("--num_steps", type=int, default=13)
    parser.add_argument("--total_wafers", type=int, default=0)
    parser.add_argument("--mode_4x1_wafers", type=int, default=20)
    parser.add_argument("--mode_2x2_wafers", type=int, default=20)
    parser.add_argument("--pec_pool_size", type=int, default=8)
    parser.add_argument("--process_mode", type=str, default="auto")
    parser.add_argument("--mode_sequence", type=str, default="")
    parser.add_argument("--wafer_mode_map", "--wafer_modes", dest="wafer_mode_map", type=str, default="")
    parser.add_argument("--default_wafer_mode", type=str, default="")
    return parser.parse_args()


def _write_runtime_config(
    base_config_file: str,
    test_model_path: str,
    instance_dir: str,
    runtime_config_file: str,
    time_limit: float = -1.0,
) -> None:
    with open(resolve_path(base_config_file), "r", encoding="utf-8") as f:
        cfg = json.load(f)
    cfg["test_kwargs"]["test_model_path"] = test_model_path
    cfg["test_kwargs"]["test_instance_path"] = instance_dir
    cfg["env"]["instance_file_path"] = instance_dir
    if time_limit > 0:
        cfg["env"]["scip_time_limit"] = time_limit
        for section_name in ("online_test_kwargs", "evaluate_kwargs"):
            section_env = cfg.get(section_name, {}).get("test_env_kwargs")
            if section_env is not None:
                section_env["scip_time_limit"] = time_limit
    experiment_cfg = cfg.setdefault("experiment", {})
    experiment_cfg["base_log_dir"] = str(resolve_path(experiment_cfg.get("base_log_dir") or "data"))
    if "online_test_kwargs" in cfg and cfg["online_test_kwargs"].get("test_instance_path"):
        cfg["online_test_kwargs"]["test_instance_path"] = str(resolve_path(cfg["online_test_kwargs"]["test_instance_path"]))
    if "evaluate_kwargs" in cfg and cfg["evaluate_kwargs"].get("test_instance_path"):
        cfg["evaluate_kwargs"]["test_instance_path"] = str(resolve_path(cfg["evaluate_kwargs"]["test_instance_path"]))
    os.makedirs(os.path.dirname(runtime_config_file), exist_ok=True)
    with open(runtime_config_file, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


def _run(cmd: List[str]) -> None:
    print(" ".join(cmd))
    subprocess.run(cmd, check=True, cwd=str(PROJECT_ROOT))


def main() -> None:
    args = _parse_args()
    args.config_file = str(resolve_path(args.config_file))
    args.test_model_path = str(resolve_path(args.test_model_path))
    args.instance_dir = str(resolve_path(args.instance_dir))
    os.makedirs(args.instance_dir, exist_ok=True)
    if not os.path.isfile(args.test_model_path):
        raise FileNotFoundError(
            f"Model file not found: {args.test_model_path}. "
            "Pass a real trained params.pkl via --test_model_path."
        )

    petri_cfg = PetriMIPConfig(
        num_batches=args.num_batches,
        num_pm=args.num_pm,
        num_steps=args.num_steps,
        total_wafers=args.total_wafers,
        pec_pool_size=args.pec_pool_size,
        process_mode=args.process_mode,
        mode_sequence=args.mode_sequence,
        wafer_mode_map=args.wafer_mode_map,
        default_wafer_mode=args.default_wafer_mode,
        full_mode_wafers=args.mode_4x1_wafers,
        mix_mode_wafers=args.mode_2x2_wafers,
    )
    lp_path = generate_petri_mip_instance(args.instance_dir, args.instance_name, petri_cfg)
    generated_instance_name = os.path.basename(lp_path)
    print(f"generated instance: {lp_path}")
    print(
        "generated model description: "
        f"{get_petri_model_description_path(args.instance_dir, generated_instance_name)}"
    )

    runtime_config = os.path.join(
        args.instance_dir,
        f"runtime_{Path(generated_instance_name).stem}_config.json",
    )
    _write_runtime_config(
        args.config_file,
        args.test_model_path,
        args.instance_dir,
        runtime_config,
        args.time_limit,
    )

    cmd = [
        "python",
        "parallel_reinforce_algorithm.py",
        "--config_file",
        runtime_config,
        "--train_type",
        "test",
        "--generate_petri_instance",
        "True",
        "--petri_instance_dir",
        args.instance_dir,
        "--petri_instance_name",
        generated_instance_name,
        "--petri_batches",
        str(args.num_batches),
        "--petri_num_pm",
        str(args.num_pm),
        "--petri_num_steps",
        str(args.num_steps),
        "--petri_total_wafers",
        str(args.total_wafers),
        "--petri_4x1_wafers",
        str(args.mode_4x1_wafers),
        "--petri_2x2_wafers",
        str(args.mode_2x2_wafers),
        "--petri_pec_pool_size",
        str(args.pec_pool_size),
        "--petri_process_mode",
        args.process_mode,
        "--petri_mode_sequence",
        args.mode_sequence,
        "--petri_wafer_mode_map",
        args.wafer_mode_map,
        "--petri_default_wafer_mode",
        args.default_wafer_mode,
        "--single_instance_file",
        generated_instance_name,
        "--test_decode_type",
        args.test_decode_type,
        "--test_time_limit",
        str(args.time_limit),
        "--policy_type",
        args.policy_type,
        "--use_cutsel_percent_policy",
        args.use_cutsel_percent_policy,
        "--sel_cuts_percent",
        str(args.sel_cuts_percent),
        "--seed",
        str(args.seed),
        "--scip_seed",
        str(args.scip_seed),
        "--instance_type",
        args.instance_type,
    ]
    _run(cmd)


if __name__ == "__main__":
    main()

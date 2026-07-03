import argparse
import json
import os
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from path_utils import PROJECT_ROOT, is_latest_keyword, latest_matching_file, resolve_path
from petri_mip_generator import (
    PetriMIPConfig,
    generate_petri_mip_instance,
    get_petri_model_description_path,
)
from petri_warm_start import find_compatible_mixed_warm_start, write_mixed_warm_start


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
    parser.add_argument(
        "--allow_very_long_run",
        action="store_true",
        help="Allow an explicitly requested SCIP time limit above 7200 seconds.",
    )
    parser.add_argument(
        "--heartbeat_seconds",
        type=float,
        default=30.0,
        help="Seconds between wrapper progress heartbeats; 0 disables heartbeats.",
    )
    parser.add_argument(
        "--wall_time_grace_seconds",
        type=float,
        default=120.0,
        help="Extra wall-clock grace after --time_limit before the child process is terminated.",
    )
    parser.add_argument(
        "--warm_start_time_limit",
        type=float,
        default=180.0,
        help="Seconds used to build a conservative 2x2/Mixed primal start; 0 disables it.",
    )
    parser.add_argument(
        "--scip_verbosity",
        type=int,
        default=4,
        help="SCIP log level (0 is silent; 4 prints the normal solving progress).",
    )
    parser.add_argument(
        "--scip_memory_limit_mb",
        type=float,
        default=8192.0,
        help="SCIP memory cap in MB for this run; a nonpositive value disables the cap.",
    )
    parser.add_argument(
        "--scip_node_limit",
        type=int,
        default=-1,
        help="Maximum branch-and-bound nodes; a negative value disables the cap. Use a finite value only for smoke tests.",
    )
    parser.add_argument(
        "--scip_stall_node_limit",
        type=int,
        default=-2,
        help=(
            "Stop after this many branch-and-bound nodes without improving the incumbent. "
            "-2 selects 10000 automatically for dense mixed instances; -1 disables it."
        ),
    )
    parser.add_argument(
        "--scip_solution_limit",
        type=int,
        default=-1,
        help=(
            "Stop after this many accepted solutions; -1 disables it. "
            "Use 1 for the fastest Gantt/model smoke test when a warm start is available."
        ),
    )
    parser.add_argument(
        "--scip_emphasis",
        choices=("auto", "default", "optimality", "feasibility"),
        default="auto",
        help="SCIP search preset; auto uses feasibility for a large instance containing 2x2 wafers.",
    )
    parser.add_argument(
        "--scip_heuristics_profile",
        choices=("auto", "default", "fast", "aggressive", "off"),
        default="auto",
        help="SCIP heuristic preset; auto uses fast for a dense large mixed/2x2 instance.",
    )
    parser.add_argument(
        "--use_learned_cutsel",
        choices=("auto", "true", "false"),
        default="auto",
        help="Use the learned cut selector; auto disables it for dense large mixed/2x2 instances.",
    )
    parser.add_argument(
        "--cutsel_max_candidates",
        type=int,
        default=128,
        help="Maximum cuts given to the learned pointer policy; 0 means unlimited.",
    )
    parser.add_argument(
        "--cutsel_max_selected_cuts",
        type=int,
        default=16,
        help="Maximum cuts selected by the learned policy per callback; 0 means unlimited.",
    )
    parser.add_argument(
        "--warm_start_solution_file",
        type=str,
        default="",
        help="Existing SCIP .sol file to load as a primal warm start; if set, it takes precedence over generating a new warm start.",
    )
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
    parser.add_argument(
        "--lexicographic_stability_time_limit",
        type=float,
        default=10.0,
        help="Maximum seconds for the secondary schedule-compaction solve; 0 disables it.",
    )
    parser.add_argument(
        "--lexicographic_stability_node_limit",
        type=int,
        default=5000,
        help="Maximum nodes for the secondary schedule-compaction solve; negative disables the cap.",
    )
    return parser.parse_args()


def _write_runtime_config(
    base_config_file: str,
    test_model_path: str,
    instance_dir: str,
    runtime_config_file: str,
    time_limit: float = -1.0,
    schedule_penalty_kwargs=None,
    scip_verbosity: int = 0,
    scip_memory_limit_mb: float = 8192.0,
    scip_node_limit: int = -1,
    scip_stall_node_limit: int = -1,
    scip_solution_limit: int = -1,
    scip_emphasis: str = "default",
    scip_heuristics_profile: str = "default",
    use_learned_cutsel: bool = True,
    cutsel_max_candidates: int = 128,
    cutsel_max_selected_cuts: int = 16,
    warm_start_solution_file: str = "",
    lexicographic_stability_time_limit: float = 10.0,
    lexicographic_stability_node_limit: int = 5000,
) -> None:
    with open(resolve_path(base_config_file), "r", encoding="utf-8") as f:
        cfg = json.load(f)
    cfg["test_kwargs"]["test_model_path"] = test_model_path
    cfg["test_kwargs"]["test_instance_path"] = instance_dir
    # This entry point always passes one generated LP via --single_instance_file.
    # Running it through multiple worker processes only hides the child output
    # and adds CUDA/SCIP start-up overhead; it cannot parallelize one MIP.
    cfg["test_kwargs"]["n_jobs"] = 1
    cfg["env"]["instance_file_path"] = instance_dir
    schedule_penalty_kwargs = schedule_penalty_kwargs or {}
    cfg["env"].update(schedule_penalty_kwargs)
    cfg["env"]["scip_verbosity"] = scip_verbosity
    cfg["env"]["scip_memory_limit_mb"] = scip_memory_limit_mb
    cfg["env"]["scip_node_limit"] = scip_node_limit
    cfg["env"]["scip_stall_node_limit"] = scip_stall_node_limit
    cfg["env"]["scip_solution_limit"] = scip_solution_limit
    cfg["env"]["scip_emphasis"] = scip_emphasis
    cfg["env"]["scip_heuristics_profile"] = scip_heuristics_profile
    cfg["env"]["use_learned_cutsel"] = use_learned_cutsel
    cfg["env"]["cutsel_max_candidates"] = cutsel_max_candidates
    cfg["env"]["cutsel_max_selected_cuts"] = cutsel_max_selected_cuts
    cfg["env"]["warm_start_solution_file"] = warm_start_solution_file
    cfg["env"]["lexicographic_stability_time_limit"] = lexicographic_stability_time_limit
    cfg["env"]["lexicographic_stability_node_limit"] = lexicographic_stability_node_limit
    if time_limit > 0:
        cfg["env"]["scip_time_limit"] = time_limit
    for section_name in ("online_test_kwargs", "evaluate_kwargs"):
        section_env = cfg.get(section_name, {}).get("test_env_kwargs")
        if section_env is not None:
            if time_limit > 0:
                section_env["scip_time_limit"] = time_limit
            section_env.update(schedule_penalty_kwargs)
            section_env["scip_verbosity"] = scip_verbosity
            section_env["scip_memory_limit_mb"] = scip_memory_limit_mb
            section_env["scip_node_limit"] = scip_node_limit
            section_env["scip_stall_node_limit"] = scip_stall_node_limit
            section_env["scip_solution_limit"] = scip_solution_limit
            section_env["scip_emphasis"] = scip_emphasis
            section_env["scip_heuristics_profile"] = scip_heuristics_profile
            section_env["use_learned_cutsel"] = use_learned_cutsel
            section_env["cutsel_max_candidates"] = cutsel_max_candidates
            section_env["cutsel_max_selected_cuts"] = cutsel_max_selected_cuts
            section_env["warm_start_solution_file"] = warm_start_solution_file
            section_env["lexicographic_stability_time_limit"] = lexicographic_stability_time_limit
            section_env["lexicographic_stability_node_limit"] = lexicographic_stability_node_limit
    experiment_cfg = cfg.setdefault("experiment", {})
    experiment_cfg["base_log_dir"] = str(resolve_path(experiment_cfg.get("base_log_dir") or "data"))
    if "online_test_kwargs" in cfg and cfg["online_test_kwargs"].get("test_instance_path"):
        cfg["online_test_kwargs"]["test_instance_path"] = str(resolve_path(cfg["online_test_kwargs"]["test_instance_path"]))
    if "evaluate_kwargs" in cfg and cfg["evaluate_kwargs"].get("test_instance_path"):
        cfg["evaluate_kwargs"]["test_instance_path"] = str(resolve_path(cfg["evaluate_kwargs"]["test_instance_path"]))
    os.makedirs(os.path.dirname(runtime_config_file), exist_ok=True)
    with open(runtime_config_file, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


def _write_json_atomic(path: str, payload: Dict) -> None:
    """Write a small run-state file without exposing a half-written JSON file."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    os.replace(temporary, target)


def _run(
    cmd: List[str],
    status_file: Optional[str] = None,
    status_payload: Optional[Dict] = None,
    heartbeat_seconds: float = 30.0,
    max_wall_seconds: Optional[float] = None,
    log_file: Optional[str] = None,
) -> None:
    """Run the solver visibly and leave an inspectable heartbeat/status file."""
    payload = dict(status_payload or {})
    payload.update(
        {
            "status": "starting",
            "command": cmd,
            "started_at": datetime.now().astimezone().isoformat(),
            "project_root": str(PROJECT_ROOT),
            "solver_log_file": log_file,
        }
    )
    if status_file:
        _write_json_atomic(status_file, payload)

    print(" ".join(cmd), flush=True)
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    env["PYTHONIOENCODING"] = "utf-8:replace"
    started = time.monotonic()
    log_handle = None
    reader_thread = None
    popen_kwargs = {}
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_handle = log_path.open("w", encoding="utf-8", buffering=1)
        popen_kwargs.update(
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )
    process = subprocess.Popen(cmd, cwd=str(PROJECT_ROOT), env=env, **popen_kwargs)
    if process.stdout is not None:
        def relay_output():
            try:
                for line in process.stdout:
                    if log_handle is not None:
                        log_handle.write(line)
                    try:
                        print(line, end="", flush=True)
                    except UnicodeEncodeError:
                        console_encoding = sys.stdout.encoding or "utf-8"
                        safe_line = line.encode(console_encoding, errors="replace").decode(console_encoding)
                        print(safe_line, end="", flush=True)
            finally:
                process.stdout.close()

        reader_thread = threading.Thread(target=relay_output, daemon=True)
        reader_thread.start()
    payload.update({"status": "running", "pid": process.pid})
    if status_file:
        _write_json_atomic(status_file, payload)

    heartbeat = max(0.0, float(heartbeat_seconds))
    try:
        while True:
            elapsed = time.monotonic() - started
            if max_wall_seconds is not None and elapsed >= max_wall_seconds:
                process.terminate()
                try:
                    process.wait(timeout=10.0)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
                if reader_thread is not None:
                    reader_thread.join(timeout=5.0)
                if log_handle is not None:
                    log_handle.close()
                payload.update(
                    {
                        "status": "wall_timeout",
                        "return_code": process.returncode,
                        "elapsed_seconds": round(time.monotonic() - started, 3),
                        "finished_at": datetime.now().astimezone().isoformat(),
                    }
                )
                if status_file:
                    _write_json_atomic(status_file, payload)
                raise subprocess.TimeoutExpired(cmd, max_wall_seconds)

            wait_seconds = heartbeat if heartbeat > 0 else None
            if max_wall_seconds is not None:
                remaining = max(0.05, max_wall_seconds - elapsed)
                wait_seconds = min(wait_seconds or 1.0, remaining)
            try:
                return_code = process.wait(timeout=wait_seconds)
                break
            except subprocess.TimeoutExpired:
                elapsed = time.monotonic() - started
                payload.update(
                    {
                        "status": "running",
                        "elapsed_seconds": round(elapsed, 3),
                        "heartbeat_at": datetime.now().astimezone().isoformat(),
                    }
                )
                if status_file:
                    _write_json_atomic(status_file, payload)
                print(
                    f"[heartbeat] solver pid={process.pid} is running; "
                    f"elapsed={elapsed:.0f}s; status_file={status_file}",
                    flush=True,
                )
    except KeyboardInterrupt:
        payload.update(
            {
                "status": "interrupted",
                "elapsed_seconds": round(time.monotonic() - started, 3),
                "finished_at": datetime.now().astimezone().isoformat(),
            }
        )
        if status_file:
            _write_json_atomic(status_file, payload)
        raise

    elapsed = time.monotonic() - started
    if reader_thread is not None:
        reader_thread.join(timeout=5.0)
    if log_handle is not None:
        log_handle.close()
    payload.update(
        {
            "status": "completed" if return_code == 0 else "failed",
            "return_code": return_code,
            "elapsed_seconds": round(elapsed, 3),
            "finished_at": datetime.now().astimezone().isoformat(),
        }
    )
    if status_file:
        _write_json_atomic(status_file, payload)
    if return_code != 0:
        raise subprocess.CalledProcessError(return_code, cmd)


def main() -> None:
    args = _parse_args()
    args.config_file = str(resolve_path(args.config_file))
    if is_latest_keyword(args.test_model_path):
        args.test_model_path = str(latest_matching_file("data", "params.pkl", "trained params.pkl"))
    else:
        args.test_model_path = str(resolve_path(args.test_model_path))
    args.instance_dir = str(resolve_path(args.instance_dir))
    os.makedirs(args.instance_dir, exist_ok=True)
    if not os.path.isfile(args.test_model_path):
        raise FileNotFoundError(
            f"Model file not found: {args.test_model_path}. "
            "Pass a real trained params.pkl via --test_model_path."
        )
    if args.time_limit > 7200 and not args.allow_very_long_run:
        raise ValueError(
            f"Refusing --time_limit {args.time_limit:g}s ({args.time_limit / 3600:.1f}h) "
            "because an interactive test would appear stuck. Use at most 7200 seconds, "
            "or add --allow_very_long_run when a day-long solve is intentional."
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
        chamber_idle_penalty=args.chamber_idle_penalty,
        post_process_wait_penalty=args.post_process_wait_penalty,
        ll_wait_penalty=args.ll_wait_penalty,
        chamber_nonprocess_wait_square_penalty=args.chamber_nonprocess_wait_square_penalty,
        atr_capacity=args.atr_capacity,
        vtr_capacity=args.vtr_capacity,
    )
    lp_path = generate_petri_mip_instance(args.instance_dir, args.instance_name, petri_cfg)
    generated_instance_name = os.path.basename(lp_path)
    pure_2x2 = bool(petri_cfg.mix_wafer_ids) and not bool(petri_cfg.full_wafer_ids)
    total_mode_wafers = len(petri_cfg.full_wafer_ids) + len(petri_cfg.mix_wafer_ids)
    dense_mixed = bool(petri_cfg.mix_wafer_ids) and total_mode_wafers >= 24
    scip_stall_node_limit = args.scip_stall_node_limit
    if scip_stall_node_limit == -2:
        scip_stall_node_limit = 10000 if dense_mixed else -1
    scip_emphasis = (
        "feasibility" if args.scip_emphasis == "auto" and dense_mixed else
        "optimality" if args.scip_emphasis == "auto" and pure_2x2 else
        "default" if args.scip_emphasis == "auto" else args.scip_emphasis
    )
    use_learned_cutsel = (
        not (pure_2x2 or dense_mixed) if args.use_learned_cutsel == "auto" else
        args.use_learned_cutsel == "true"
    )
    scip_heuristics_profile = (
        "fast" if args.scip_heuristics_profile == "auto" and dense_mixed else
        "default" if args.scip_heuristics_profile == "auto" else
        args.scip_heuristics_profile
    )
    print(
        "Petri solve mode: "
        f"pure_2x2={pure_2x2}, dense_mixed={dense_mixed}, "
        f"scip_emphasis={scip_emphasis}, "
        f"scip_heuristics_profile={scip_heuristics_profile}, "
        f"use_learned_cutsel={use_learned_cutsel}, "
        f"stall_node_limit={scip_stall_node_limit}"
    )
    if dense_mixed and args.use_learned_cutsel == "auto":
        print(
            "large mixed-instance safeguard: learned cut selection is disabled in auto mode; "
            "pass --use_learned_cutsel true only for a controlled comparison run."
        )
    warm_start_solution_file = ""
    if args.warm_start_solution_file:
        warm_start_path = resolve_path(args.warm_start_solution_file)
        if not warm_start_path.is_file():
            raise FileNotFoundError(f"Warm start solution file not found: {warm_start_path}")
        warm_start_solution_file = str(warm_start_path)
        print(f"using existing Petri warm start: {warm_start_solution_file}")
    elif args.warm_start_time_limit > 0 and petri_cfg.mix_wafer_ids:
        try:
            warm_start_solution_file = find_compatible_mixed_warm_start(
                args.instance_dir, generated_instance_name
            ) or ""
            if warm_start_solution_file:
                warm_start_solution_file = str(resolve_path(warm_start_solution_file))
                print(f"reusing compatible Petri warm start: {warm_start_solution_file}")
            else:
                warm_start_solution_file = write_mixed_warm_start(
                    args.instance_dir,
                    generated_instance_name,
                    petri_cfg,
                    time_limit=args.warm_start_time_limit,
                ) or ""
                if warm_start_solution_file:
                    warm_start_solution_file = str(resolve_path(warm_start_solution_file))
                    print(f"generated Petri warm start: {warm_start_solution_file}")
                else:
                    print(
                        "warning: no Petri warm start was found within the warm-start time limit; "
                        "large mixed instances may spend a long time before the first feasible solution. "
                        "Increase --warm_start_time_limit or pass --warm_start_solution_file."
                    )
        except Exception as exc:
            print(f"warning: Petri warm start generation failed; solving without it: {exc}")
    if args.scip_node_limit >= 0:
        print(
            "warning: finite SCIP node limit is active; "
            f"the solve may stop with status=nodelimit at {args.scip_node_limit} nodes"
        )
    if scip_stall_node_limit >= 0:
        print(
            "SCIP incumbent-stagnation safeguard is active: "
            f"stop after {scip_stall_node_limit} nodes without a better solution. "
            "Pass --scip_stall_node_limit -1 for an unrestricted quality run."
        )
    if args.scip_solution_limit > 0:
        print(
            "SCIP solution limit is active: "
            f"stop after {args.scip_solution_limit} accepted solution(s)"
        )
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
        {
            "schedule_chamber_idle_square_penalty": args.schedule_chamber_idle_square_penalty,
            "schedule_pm_wait_square_penalty": args.schedule_pm_wait_square_penalty,
            "schedule_module_wait_square_penalty": args.schedule_module_wait_square_penalty,
            "schedule_robot_wait_square_penalty": args.schedule_robot_wait_square_penalty,
        },
        args.scip_verbosity,
        args.scip_memory_limit_mb,
        args.scip_node_limit,
        scip_stall_node_limit,
        args.scip_solution_limit,
        scip_emphasis,
        scip_heuristics_profile,
        use_learned_cutsel,
        args.cutsel_max_candidates,
        args.cutsel_max_selected_cuts,
        warm_start_solution_file,
        args.lexicographic_stability_time_limit,
        args.lexicographic_stability_node_limit,
    )

    cmd = [
        sys.executable,
        "-u",
        "parallel_reinforce_algorithm.py",
        "--config_file",
        runtime_config,
        "--train_type",
        "test",
        "--generate_petri_instance",
        "False",
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
        "--petri_chamber_idle_penalty",
        str(args.chamber_idle_penalty),
        "--petri_post_process_wait_penalty",
        str(args.post_process_wait_penalty),
        "--petri_ll_wait_penalty",
        str(args.ll_wait_penalty),
        "--petri_chamber_nonprocess_wait_square_penalty",
        str(args.chamber_nonprocess_wait_square_penalty),
        "--petri_atr_capacity",
        str(args.atr_capacity),
        "--petri_vtr_capacity",
        str(args.vtr_capacity),
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
    run_status_file = os.path.join(
        args.instance_dir,
        f"runtime_{Path(generated_instance_name).stem}_run_status.json",
    )
    solver_log_file = os.path.join(
        args.instance_dir,
        f"runtime_{Path(generated_instance_name).stem}_solver.log",
    )
    _run(
        cmd,
        status_file=run_status_file,
        status_payload={
            "instance_file": str(lp_path),
            "runtime_config": runtime_config,
            "warm_start_solution_file": warm_start_solution_file,
            "scip_time_limit": args.time_limit,
            "scip_node_limit": args.scip_node_limit,
            "scip_stall_node_limit": scip_stall_node_limit,
            "scip_solution_limit": args.scip_solution_limit,
            "scip_memory_limit_mb": args.scip_memory_limit_mb,
            "scip_heuristics_profile": scip_heuristics_profile,
            "use_learned_cutsel": use_learned_cutsel,
            "process_mode": args.process_mode,
            "mode_4x1_wafers": len(petri_cfg.full_wafer_ids),
            "mode_2x2_wafers": len(petri_cfg.mix_wafer_ids),
        },
        heartbeat_seconds=args.heartbeat_seconds,
        max_wall_seconds=(
            args.time_limit + max(0.0, args.wall_time_grace_seconds)
            if args.time_limit > 0
            else None
        ),
        log_file=solver_log_file,
    )


if __name__ == "__main__":
    main()

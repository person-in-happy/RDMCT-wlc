"""Matched 300-second S1 supplement, with guarded interruption and resume."""
from __future__ import annotations
import argparse
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys

HERE = Path(__file__).resolve().parent
FORMAL_PATH = HERE.parent / "formal_ablation_20261117/formal_ablation.py"
RESUME_PATH = HERE.parent / "formal_ablation_resume_20261117/resume.py"


def module(name, path):
    loader = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(loader)
    loader.loader.exec_module(value)
    return value


f = module("s1_frozen_formal", FORMAL_PATH)
r = module("s1_resume_controller", RESUME_PATH)
r.f = f
ROOT, JMS = f.ROOT, f.JMS
SOURCE = JMS / "results/s1_initialization_20261117_r1"
RETIMING = JMS / "results/s1_retiming_20261117_r1"
EXISTING = JMS / "results/formal_ablation_20261117_r1"
DEFAULT = JMS / "results/s1_ablation_20261117_r1"
CASES = ("n2_2x2_scenario1", "n2_mixed_scenario1")
SOURCE_BY_CASE = {CASES[0]: SOURCE, CASES[1]: RETIMING}
ORIGINAL_INVENTORY = f.inventory
ORIGINAL_FOREIGN = f.foreign_workers


def source_records():
    records = []
    for name in CASES:
        receipt = f.read(SOURCE_BY_CASE[name] / "qualified" / name / "receipt.json")
        if f.sha(receipt["source"]) != receipt["result_sha256"] or f.sha(receipt["values"]) != receipt["variables_sha256"]:
            raise ValueError("Qualified S1 input changed")
        records.append(dict(case=name, backend="D", source=receipt["source"], values=receipt["values"],
                            budgets=[300], group="main", optimal_control=False))
    return records


def inventory():
    paths = [Path(__file__), HERE / "control.ps1", HERE / "PROTOCOL_CN.txt", HERE / "test_s1.py", RESUME_PATH,
             HERE / "qualify_s1.py", HERE / "retime_s1.py"]
    return ORIGINAL_INVENTORY() | {str(p.relative_to(ROOT)): f.sha(p) for p in paths}


def existing_idle_controller(pid):
    import psutil
    try:
        args = psutil.Process(pid).cmdline()
        i = args.index("--campaign")
        if Path(args[i + 1]).resolve() != EXISTING.resolve():
            return False
        for j, arg in enumerate(args[:-1]):
            try:
                path = Path(arg).resolve()
            except (ValueError, OSError):
                continue
            if path == FORMAL_PATH.resolve() and args[j + 1] == "run":
                return True
            if path == RESUME_PATH.resolve() and args[j + 1] == "resume":
                return True
    except (psutil.NoSuchProcess, psutil.AccessDenied, ValueError, IndexError):
        pass
    return False


def coordinated_foreign(own):
    # Exempt only the existing controller; every existing solve worker still blocks this supplement.
    return [pid for pid in ORIGINAL_FOREIGN(own) if not existing_idle_controller(pid)]


def active_processes(out):
    import psutil
    found = []
    for process in psutil.process_iter(["pid", "name", "cmdline", "create_time"]):
        if process.pid == os.getpid() or "python" not in (process.info["name"] or "").lower():
            continue
        args = process.info["cmdline"] or []
        role = None
        for j, arg in enumerate(args[:-1]):
            try:
                path = Path(arg).resolve()
            except (ValueError, OSError):
                continue
            if path == FORMAL_PATH.resolve() and args[j + 1] == "worker":
                role = "worker"
            if path == Path(__file__).resolve() and args[j + 1] == "run":
                role = "resume"
        if role is None:
            continue
        try:
            i = args.index("--campaign")
            campaign = Path(args[i + 1]).resolve()
        except (ValueError, IndexError):
            campaign = DEFAULT.resolve()
        if campaign == out.resolve():
            found.append(dict(pid=process.pid, role=role, create_time=process.info["create_time"]))
    return found


def prepare(out):
    # The original worker and its immutable deadline/validation behavior are reused unmodified.
    f.SEEDS = (1, 2, 3)
    f.source_records = source_records
    f.inventory = inventory
    f.prepare(out)
    spec = f.read(out / "campaign.json")
    spec.update(supplement=True, cohort="two_missing_S1_instances",
        selection="Both previously missing 2-product S1 cases (pure 2x2 and mixed), fixed before observing ablation outcomes. No instance or seed selected by algorithm advantage.",
        inference="This separate 300-second supplement matches table 10/11 solver seeds 1/2/3, frozen training seeds 1/2/3, normal separation, and 60+240 SPBS allocation. SCIP has 3 observations and learned arms 9 observations per instance. All outcomes retained; not pooled with unfinished 60/120/300-second formal campaigns.",
        source_acquisition=dict(campaigns={name: str(SOURCE_BY_CASE[name]) for name in CASES},
                                selection="first independently validated feasible assignment; mixed-case source acquired by material-flow retiming after two no-incumbent structured attempts and a preserved interrupted attempt; no ablation outcomes used",
                                time_accounting="offline source acquisition excluded from the matched 300-second improvement budget"))
    spec["settings"]["idle_controller_exception"] = str(EXISTING)
    for name in CASES:
        receipt = SOURCE_BY_CASE[name] / "qualified" / name / "receipt.json"
        spec["sources"][str(receipt)] = f.sha(receipt)
    for source in {SOURCE, RETIMING}:
        spec["sources"][str(source / "campaign.json")] = f.sha(source / "campaign.json")
    # No worker can start before this supplementary contract is finalized.
    f.dump(out / "campaign.json", spec)
    f.dump(out / "contract.json", dict(campaign_sha256=f.sha(out / "campaign.json")))
    f.report(out)
    print("FROZEN S1 supplement: 138 main solves + 6 shared SPBS preparations; nominal 10 solver-hours", flush=True)


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("action", choices=("prepare", "run", "stop", "status"))
    parser.add_argument("--campaign", default=str(DEFAULT))
    args = parser.parse_args()
    out = Path(args.campaign).resolve()
    root = (JMS / "results").resolve()
    if not out.is_relative_to(root) or out == root:
        parser.error("Use an isolated results directory")
    f.foreign_workers = coordinated_foreign
    r.active_processes = active_processes
    if args.action == "prepare":
        prepare(out)
    elif args.action == "run":
        r.resume(out)
    elif args.action == "stop":
        r.stop(out)
    else:
        f.checked(out, full=False)
        path = out / "live_status.json"
        processes = active_processes(out)
        print(json.dumps(dict(running=bool(processes), processes=processes,
              progress=f.read(path) if path.exists() else None), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

"""Resume the frozen formal campaign without changing its code or observations."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys
import time

HERE = Path(__file__).resolve().parent
FORMAL = HERE.parent / "formal_ablation_20261117/formal_ablation.py"
loader = importlib.util.spec_from_file_location("frozen_formal", FORMAL)
f = importlib.util.module_from_spec(loader)
loader.loader.exec_module(f)
ROOT = f.ROOT
DEFAULT = f.JMS / "results/formal_ablation_20261117_r1"
INTERRUPTIONS = {"foreground_supervisor_interrupted", "RAM_guard", "wall_guard"}
DEPENDENCY_FAILURES = {"shared_preparation_failed", "shared_preparation_ineligible"}


def active_processes(out):
    """Match exact script, action and campaign arguments, never process name alone."""
    import psutil
    found = []
    for process in psutil.process_iter(["pid", "name", "cmdline", "create_time"]):
        if process.pid == os.getpid() or "python" not in (process.info["name"] or "").lower():
            continue
        args = process.info["cmdline"] or []
        try:
            index = args.index("--campaign")
            if Path(args[index + 1]).resolve() != out.resolve():
                continue
        except (ValueError, IndexError, OSError):
            continue
        role = None
        for i, arg in enumerate(args[:-1]):
            try:
                path = Path(arg).resolve()
            except (OSError, ValueError):
                continue
            if path == FORMAL.resolve() and args[i + 1] in ("run", "worker"):
                role = args[i + 1]
            if path == Path(__file__).resolve() and args[i + 1] == "resume":
                role = "resume"
        if role:
            found.append(dict(pid=process.pid, role=role, create_time=process.info["create_time"]))
    return found


def complete_certificate(directory):
    try:
        evidence = f.read(directory / "evidence.json")
        result = f.read(directory / "result.json")
        return bool(evidence["valid"] and evidence["budget_eligible"] and not evidence.get("resource_interruption")
                    and result["original_model_check"] and result["validation"]["valid"]
                    and f.sha(directory / "result.json") == evidence["result_sha256"]
                    and f.sha(directory / "variables.json") == evidence["assignment_sha256"]
                    and (directory / "trace.json").is_file())
    except (OSError, ValueError, KeyError, TypeError):
        return False


def plan_resume(out, spec):
    actions, completed, retained_failures = [], [], []
    reset = set()
    for cell in spec["cells"]:
        cid = cell["id"]
        directory = out / "runs" / cid
        if not directory.exists():
            continue
        failure = f.read(directory / "failure.json") if (directory / "failure.json").exists() else None
        if failure:
            if failure.get("reason") in INTERRUPTIONS:
                if complete_certificate(directory):
                    actions.append(dict(id=cid, kind="recover_completed", reason=failure["reason"]))
                    completed.append(cid)
                else:
                    actions.append(dict(id=cid, kind="restart_interrupted", reason=failure["reason"]))
                    reset.add(cid)
            else:
                retained_failures.append(dict(id=cid, reason=failure.get("reason", "unknown")))
        elif (directory / "evidence.json").exists():
            evidence = f.read(directory / "evidence.json")
            if evidence.get("resource_interruption"):
                actions.append(dict(id=cid, kind="restart_resource_interruption", reason="resource_interruption"))
                reset.add(cid)
                continue
            # Completed-but-ineligible observations are also retained, never retried for a better outcome.
            completed.append(cid)
        else:
            actions.append(dict(id=cid, kind="restart_incomplete", reason="no_completed_certificate"))
            reset.add(cid)
    by_id = {cell["id"]: cell for cell in spec["cells"]}
    recovered = {a["id"] for a in actions if a["kind"] == "recover_completed"}
    for failure in list(retained_failures):
        dependency = by_id[failure["id"]].get("preparation")
        if failure["reason"] in DEPENDENCY_FAILURES and dependency in (reset | recovered):
            actions.append(dict(id=failure["id"], kind="restart_dependency", reason=failure["reason"]))
            retained_failures.remove(failure)
    return dict(actions=actions, completed=completed, retained_failures=retained_failures)


def safe_move(source, target, out):
    """Archive whole attempts on the same volume after checking both resolved paths."""
    root = out.resolve()
    source, target = source.resolve(), target.resolve()
    if source == root or not source.is_relative_to(root) or not target.is_relative_to(root):
        raise ValueError("Archive paths must stay strictly within the campaign")
    if target.exists():
        raise FileExistsError("Never overwrite an archived attempt: " + str(target))
    target.parent.mkdir(parents=True, exist_ok=True)
    source.rename(target)


def apply_plan(out, archive, plan):
    for action in plan["actions"]:
        directory = out / "runs" / action["id"]
        if action["kind"] == "recover_completed":
            safe_move(directory / "failure.json", archive / "completed_failure_markers" / (action["id"] + ".json"), out)
            continue
        safe_move(directory, archive / "attempts" / action["id"], out)
        for folder in ("logs", "launch_records"):
            suffix = ".log" if folder == "logs" else ".json"
            old = out / folder / (action["id"] + suffix)
            if old.exists():
                safe_move(old, archive / folder / old.name, out)


def make_archive(out):
    name = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S_%fZ") + "_" + str(os.getpid())
    archive = out / "continuations" / name
    archive.mkdir(parents=True, exist_ok=False)
    return archive


def resume(out):
    import psutil
    spec = f.checked(out)
    active = active_processes(out)
    if active:
        print("ALREADY RUNNING; no duplicate supervisor started: " + json.dumps(active), flush=True)
        return
    archive = make_archive(out)
    guard = out / "resume.guard.json"
    if guard.exists():
        try:
            old = f.read(guard)
            process = psutil.Process(old["pid"])
            alive = abs(process.create_time() - old["create_time"]) < .01
        except (psutil.NoSuchProcess, KeyError, ValueError):
            alive = False
        if alive:
            raise RuntimeError("Another resume operation owns the guard")
        safe_move(guard, archive / "stale_resume_guard.json", out)
    fd = os.open(guard, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    os.write(fd, json.dumps(dict(pid=os.getpid(), create_time=psutil.Process().create_time())).encode())
    os.close(fd)
    claimed = False
    lock = out / "supervisor.lock"
    try:
        active = active_processes(out)
        if active:
            print("ALREADY RUNNING; resume cancelled safely: " + json.dumps(active), flush=True)
            return
        if lock.exists():
            safe_move(lock, archive / "stale_supervisor.lock", out)
        # Reserve the original supervisor lock throughout archival, preventing a competing fresh launch.
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(fd, str(os.getpid()).encode())
        os.close(fd)
        claimed = True
        plan = plan_resume(out, spec)
        assets = {str(p.relative_to(ROOT)): f.sha(p) for p in (Path(__file__), HERE / "resume.ps1", HERE / "README_CN.txt")}
        for rel in assets:
            target = archive / "frozen_resume_code" / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / rel, target)
        f.dump(archive / "resume_plan.json", plan | dict(created_utc=f.stamp(), assets=assets,
              campaign_sha256=f.sha(out / "campaign.json"),
              semantics="Completed cells are retained. Interrupted cells restart from their original frozen input and original full budget. No interrupted partial solution is used as a warm start. Raw attempts remain archived. No outcome-based retry."))
        apply_plan(out, archive, plan)
        for name in ("finished.json", "live_status.json"):
            if (out / name).exists():
                safe_move(out / name, archive / name, out)
        coverage = f.report(out)
        print(f'RESUME completed retained={len(plan["completed"])} interrupted archived={len(plan["actions"])} '
              f'failed retained={len(plan["retained_failures"])} remaining={coverage["pending"]}', flush=True)
        if plan["retained_failures"]:
            print("Existing non-interruption errors remain visible: " + json.dumps(plan["retained_failures"]), flush=True)
        f.dump(archive / "ready.json", dict(coverage=coverage, prepared_utc=f.stamp()))
        lock.unlink()
        claimed = False
        # Same Python process: avoids a waiting parent being mistaken for a competing experiment.
        f.run(out)
    finally:
        if claimed and lock.exists() and lock.read_text().strip() == str(os.getpid()):
            lock.unlink()
        if guard.exists() and f.read(guard).get("pid") == os.getpid():
            guard.unlink()


def stop(out):
    """Explicit user command only. Stop this campaign, preserving all output for resume."""
    import psutil
    f.checked(out, full=False)
    found = active_processes(out)
    record = dict(requested_utc=f.stamp(), initial_processes=found, stopped=[])
    # Stop supervisor first so it cannot create further workers; then re-enumerate workers.
    for role in ("supervisor", "workers"):
        targets = [p for p in active_processes(out) if (p["role"] != "worker") == (role == "supervisor")]
        for entry in targets:
            try:
                process = psutil.Process(entry["pid"])
                if abs(process.create_time() - entry["create_time"]) >= .01:
                    raise RuntimeError("PID changed during stop; refusing to terminate a different process")
                process.terminate()
                process.wait(timeout=30)
                record["stopped"].append(entry)
            except psutil.NoSuchProcess:
                pass
    record["remaining"] = active_processes(out)
    archive = make_archive(out)
    f.dump(archive / "explicit_stop.json", record)
    print("STOPPED; completed outputs preserved, interrupted cells will restart on Resume. " + json.dumps(record), flush=True)


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("action", choices=("resume", "stop", "status"))
    parser.add_argument("--campaign", default=str(DEFAULT))
    args = parser.parse_args()
    out = Path(args.campaign).resolve()
    results = (f.JMS / "results").resolve()
    if not out.is_relative_to(results) or out == results:
        parser.error("Campaign must be a dedicated directory under JMS-version/results")
    if args.action == "resume":
        resume(out)
    elif args.action == "stop":
        stop(out)
    else:
        f.checked(out, full=False)
        live = out / "live_status.json"
        processes = active_processes(out)
        print(json.dumps(dict(running=bool(processes), processes=processes,
              progress=f.read(live) if live.exists() else None), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

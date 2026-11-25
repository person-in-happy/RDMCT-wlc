"""Run the registered table 4 comparisons only to the first (10%) endpoint."""
import csv
from datetime import datetime
import msvcrt
import os
from pathlib import Path
import subprocess
import sys
import time

import psutil

import solve

LEVEL = "10pct"
solve.LEVELS = {LEVEL: .10}
HERE = Path(__file__).resolve()
OUTPUT = solve.OUT / "ten_percent"
JOBS = [(case, seed, arm) for case in solve.CASES for seed in solve.SEEDS for arm in ("A", "B", "J")]
ENDPOINTS = [(case, seed, arm) for case in solve.CASES for seed in solve.SEEDS for arm in solve.ARMS]


def key(job):
    return "/".join(map(str, job))


def endpoint(job):
    return solve.directory(*job) / LEVEL / "result.json"


def finished(job, completed):
    case, seed, arm = job
    return job in completed and (arm != "A" or (case, seed, "AB") in completed)


def run_worker(job, memory):
    case, seed, arm = job
    if arm == "A" and endpoint(job).is_file():
        # If interrupted during the second stage, resume from the exact A handoff.
        solve.register()
        solve.finish_second(case, seed, LEVEL, endpoint(job).parent, solve.matched.CASES[case]["assignment_sha256"])
    else:
        solve.solve(case, seed, arm, memory)


def take_over():
    previous = solve.read(OUTPUT / "switch_from_previous.json")["workers"]
    old = {record["pid"]: record for record in previous}
    active = {}
    for process in psutil.process_iter(["name", "cmdline"]):
        if (process.info["name"] or "").lower() != "python.exe":
            continue
        args = process.info["cmdline"] or []
        recorded = old.get(process.pid)
        if recorded and abs(recorded["created"] - process.create_time()) < .01:
            script = solve.ROOT / recorded["script"]
            suffix = recorded["args"]
            if len(args) < 5 or Path(args[-5]) != script or args[-4:] != suffix:
                raise RuntimeError(f"Unexpected command on registered process {process.pid}")
            adopted = True
        elif len(args) >= 6 and Path(args[-6]) == HERE and args[-5] == "worker":
            suffix = args[-4:]
            adopted = False
        else:
            continue
        case, seed, arm, mb = suffix
        job = (case, int(seed), arm)
        if job not in JOBS or job in active:
            raise RuntimeError(f"Duplicate or unregistered job {job}")
        active[job] = (process, int(mb), adopted)
    return active


def new_worker(job, memory):
    folder = solve.directory(*job)
    folder.mkdir(parents=True, exist_ok=True)
    stamp = str(time.time_ns())
    # A retry needs a fresh solver log. Preserve previous attempts separately.
    for name in ("solver.log", "settings.json", "live.json", "last_stop.json"):
        prior = folder / name
        if prior.is_file() and not endpoint(job).exists():
            archived = folder / "prior_attempts" / stamp / name
            archived.parent.mkdir(parents=True, exist_ok=True)
            prior.rename(archived)
    with (folder / f"10pct-console-{stamp}.log").open("w", encoding="utf8") as stream:
        return psutil.Popen([sys.executable, "-B", "-u", "-X", "utf8", str(HERE), "worker",
                             *map(str, job), str(memory)], cwd=solve.ROOT, stdout=stream, stderr=subprocess.STDOUT)


def register():
    solve.register()
    frozen = solve.OUT / "protocol.json"
    original = solve.read(frozen)
    for case, spec in original["inputs"].items():
        if case not in solve.CASES or any(solve.sha(solve.ROOT / spec[k]) != spec[k+"_sha256"]
                                         for k in ("source", "assignment")):
            raise ValueError(f"Frozen input changed for {case}")
    for name, digest in original["scripts"].items():
        if solve.sha(solve.HERE / name) != digest:
            raise ValueError(f"Frozen table 4 source changed: {name}")
    plan = dict(original, thresholds=solve.LEVELS, expected=len(ENDPOINTS), previous_protocol_sha256=solve.sha(frozen),
                threshold_protocol="stop each objective at 10%; AB uses the same seed's A10 witness and a 10% B stop",
                controller=HERE.relative_to(solve.ROOT).as_posix(), endpoint_root=solve.OUT.relative_to(solve.ROOT).as_posix(),
                adopted=solve.read(OUTPUT / "switch_from_previous.json")["workers"])
    protocol = OUTPUT / "protocol.json"
    if protocol.exists() and solve.read(protocol) != plan:
        raise ValueError("Registered 10% plan differs from the requested inputs")
    solve.save(protocol, plan)


def verified_summary():
    # Import after restricting solve.LEVELS. Each model backend is audited in its own process.
    import review
    review.OUT = OUTPUT
    for case in solve.CASES:
        subprocess.run([sys.executable, "-B", "-u", "-X", "utf8", str(HERE), "audit", case],
                       cwd=solve.ROOT, check=True)
    rows = [r for case in solve.CASES for r in solve.read(OUTPUT / "audit" / (case + ".json"))]
    means = review.tabulate(rows)
    for name, table in (("endpoints", rows), ("table4_means", means)):
        with (OUTPUT / (name+".csv")).open("w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(table[0]))
            writer.writeheader()
            writer.writerows(table)
    (OUTPUT / "table4_gap.tex").write_text(review.table_tex(means), encoding="utf8")


def publish(active, completed, failed, elapsed, baseline, status):
    workers = {}
    for job, (process, memory, adopted) in active.items():
        folder = solve.directory(*job)
        last = folder / "live.json"
        workers[key(job)] = dict(pid=process.pid, adopted=adopted, reserved_mb=memory,
                                 last_event=solve.read(last) if last.exists() else None)
    waiting = [j for j in JOBS if j not in active and key(j) not in failed and not finished(j, completed)]
    gained = len(completed) - baseline
    eta = elapsed * (len(ENDPOINTS)-len(completed)) / gained if gained > 0 else None
    now = datetime.now().astimezone().isoformat(timespec="seconds")
    state = dict(updated=now, owner=os.getpid(), state=status, target_percent=10, workers=workers,
                 verified_endpoints=len(completed), expected_endpoints=len(ENDPOINTS), queued_trajectories=len(waiting),
                 failed=failed, eta_seconds=eta, protocol=(OUTPUT / "protocol.json").relative_to(solve.ROOT).as_posix())
    solve.save(OUTPUT / "progress.json", state)
    solve.save(solve.OUT / "progress.json", state)
    eta_label = f"{eta/3600:.1f} h" if eta is not None else "pending completed 10% endpoints"
    print(f"{now} | {status} | {len(completed)}/{len(ENDPOINTS)} at 10% | {len(active)} active | "
          f"{len(waiting)} queued | {len(failed)} failed | ETA {eta_label}", flush=True)


def main():
    register()
    active = take_over()
    completed = {j for j in ENDPOINTS if endpoint(j).is_file()}
    baseline = len(completed)
    retry_file = OUTPUT / "memory_retries.json"
    retries = solve.read(retry_file) if retry_file.exists() else {}
    failed = {}
    start = time.monotonic()
    last_print = -30.
    while True:
        completed.update(j for j in ENDPOINTS if j not in completed and endpoint(j).is_file())
        for job, (proc, memory, adopted) in list(active.items()):
            # Original workers have a multi-level loop already loaded in memory.
            # Reclaim them as soon as their required, atomically saved endpoints exist.
            if adopted and finished(job, completed) and proc.is_running():
                try:
                    proc.terminate()
                    proc.wait(timeout=5)
                except psutil.NoSuchProcess:
                    pass
            if proc.is_running():
                continue
            del active[job]
            # A worker can commit its endpoint between this pass's scan and exit.
            completed.update(j for j in ENDPOINTS if j[:2] == job[:2] and endpoint(j).is_file())
            if finished(job, completed):
                continue
            folder = solve.directory(*job)
            last = folder / "last_stop.json"
            stop = solve.read(last) if last.is_file() else {}
            if stop.get("status") in ("memlimit", "memorylimit") and key(job) not in retries:
                retries[key(job)] = memory + 2500
                solve.save(retry_file, retries)
            else:
                failed[key(job)] = dict(status=stop, directory=folder.relative_to(solve.ROOT).as_posix())
        for job in JOBS:
            if len(active) >= 6:
                break
            if job in active or key(job) in failed or finished(job, completed):
                continue
            mb = retries.get(key(job), 6500 if solve.matched.CASES[job[0]]["n"] == 16 else 2300)
            available = psutil.virtual_memory().available / 2**30
            for proc, reserved, _ in active.values():
                try:
                    available -= max(0., reserved / 1000 + .4 - proc.memory_info().rss / 2**30)
                except psutil.NoSuchProcess:
                    pass
            if available < 2.5 + mb / 1000 + .4:
                continue
            active[job] = (new_worker(job, mb), mb, False)
        elapsed = time.monotonic() - start
        pending = [j for j in JOBS if not finished(j, completed) and key(j) not in failed]
        if not active and not pending:
            break
        if elapsed-last_print >= 15:
            publish(active, completed, failed, elapsed, baseline, "running")
            last_print = elapsed
        time.sleep(1 if any(adopted for _, _, adopted in active.values()) else 5)
    if failed:
        publish(active, completed, failed, elapsed, baseline, "incomplete")
        raise RuntimeError(f"Failed jobs: {failed}")
    publish(active, completed, failed, elapsed, baseline, "auditing")
    verified_summary()
    publish(active, completed, failed, time.monotonic()-start, baseline, "verified")


if __name__ == "__main__":
    if sys.argv[1:2] == ["worker"]:
        _, _, case, seed, arm, memory = sys.argv
        run_worker((case, int(seed), arm), int(memory))
    elif sys.argv[1:2] == ["audit"]:
        import review
        review.OUT = OUTPUT
        review.verify_case(sys.argv[2])
    else:
        with (solve.OUT / "owner.lock").open("a+b") as lock:
            lock.seek(0)
            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
            main()

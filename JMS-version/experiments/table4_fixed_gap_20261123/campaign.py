"""Visible single-owner campaign with bounded memory reservations and live progress."""
from datetime import datetime
import msvcrt
import os
import subprocess
import sys
import time

import psutil
from solve import ARMS, CASES, HERE, LEVELS, OUT, ROOT, SEEDS, directory, matched, read, register, save, sha

GIB = 1024**3
MAX_WORKERS = 6


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    ownership = (OUT / "owner.lock").open("a+b")
    ownership.seek(0)
    msvcrt.locking(ownership.fileno(), msvcrt.LK_NBLCK, 1)
    register()
    inputs = {}
    for case in CASES:
        spec = matched.CASES[case]
        assert (sha(ROOT / spec["source"]), sha(ROOT / spec["assignment"])) == (
            spec["source_sha256"], spec["assignment_sha256"])
        inputs[case] = {k: spec[k] for k in ("source", "assignment", "source_sha256", "assignment_sha256", "config", "backend", "n")}
    jobs = [(c, s, a) for c in CASES for s in SEEDS for a in ("A", "B", "J")]
    total = len(CASES) * len(SEEDS) * len(ARMS) * len(LEVELS)
    plan = dict(inputs=inputs, seeds=SEEDS, arms=ARMS, thresholds=LEVELS, native_threads=1,
                seconds=None, max_workers=MAX_WORKERS, normalized_joint_weight=.1,
                two_stage="share same-seed A terminal assignment at each threshold, fix discrete structure and cap physical f_A",
                threshold_protocol="stop SCIP, extract and replay exact incumbent, tighten gap and resume the search tree",
                score="both from one physical schedule, only product waiting, weights [1,10,25]",
                expected=total, scripts={name:sha(HERE / name) for name in ("solve.py", "campaign.py")})
    path = OUT / "protocol.json"
    if path.is_file():
        if read(path)["inputs"] != inputs:
            raise RuntimeError("Original inputs differ from the registered inputs")
    else:
        save(path, plan)
    def complete(job):
        c, s, a = job
        arms = ("A", "AB") if a == "A" else (a,)
        return all((directory(c, s, arm) / level / "result.json").exists() for arm in arms for level in LEVELS)
    waiting = [j for j in jobs if not complete(j)]
    active, failed, memory_override = {}, {}, {}
    begin = time.monotonic()
    while waiting or active:
        for job, (p, stream, reserve) in list(active.items()):
            if p.poll() is None:
                continue
            stream.close()
            del active[job]
            if p.returncode or not complete(job):
                folder = directory(*job)
                last = folder / "last_stop.json"
                status = read(last)["status"] if last.exists() else None
                if status in ("memlimit", "memorylimit") and job not in memory_override:
                    memory_override[job] = reserve + 2500
                    waiting.append(job)
                else:
                    failed["/".join(map(str,job))] = dict(code=p.returncode, status=status, log=stream.name)
        limit = 2.5
        for job in waiting[:]:
            if len(active) >= MAX_WORKERS:
                break
            n = inputs[job[0]]["n"]
            reserve = memory_override.get(job, 6500 if n == 16 else 2300)
            # OS-reported free RAM already excludes allocated worker memory.
            outstanding = 0.
            for p, _, mem in active.values():
                try:
                    rss = psutil.Process(p.pid).memory_info().rss / GIB
                except psutil.NoSuchProcess:
                    rss = 0.
                outstanding += max(0., (mem / 1000 + .4) - rss)
            if psutil.virtual_memory().available / GIB - outstanding < reserve / 1000 + .4 + limit:
                continue
            folder = directory(*job)
            folder.mkdir(parents=True, exist_ok=True)
            stream = (folder / f"console-{time.time_ns()}.log").open("w", encoding="utf8")
            p = subprocess.Popen([sys.executable, "-B", "-u", "-X", "utf8", str(HERE / "solve.py"),
                                  job[0], str(job[1]), job[2], str(reserve)], cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT)
            active[job] = (p, stream, reserve)
            waiting.remove(job)
        count = sum(1 for _ in (OUT / "runs").glob("*/*/result.json"))
        workers = {}
        for j, (p, _, _) in active.items():
            live = directory(*j) / "live.json"
            workers["/".join(map(str,j))] = dict(pid=p.pid, last_event=read(live) if live.exists() else None)
        eta = (time.monotonic() - begin) / count * (total-count) if count else None
        state = dict(updated=datetime.now().astimezone().isoformat(timespec="seconds"), owner=os.getpid(),
                     verified_endpoints=count, expected_endpoints=total, workers=workers,
                     queued_trajectories=len(waiting), failed=failed, eta_seconds=eta)
        save(OUT / "progress.json", state)
        print(state["updated"], f"{count}/{total} endpoints | {len(workers)} active | {len(failed)} failed |",
              f"ETA {eta/3600:.1f} h" if eta is not None else "ETA pending first completed threshold", flush=True)
        if waiting or active:
            time.sleep(15)
    if failed:
        raise RuntimeError(f"Unfinished trajectories: {failed}")
    from review import finish
    finish()


if __name__ == "__main__":
    main()

"""Exercise controller takeover and worker restart on an isolated copy of eight cells."""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import psutil
from run import HERE, OUT, LEVELS, atomic, load, sha


def wait_until(fn, seconds=45):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        value = fn()
        if value:
            return value
        time.sleep(0.04)
    raise TimeoutError(fn)


def main():
    mode = "4x1"
    test = OUT / "recovery" / time.strftime("%Y%m%d_%H%M%S")
    root = test / mode
    root.mkdir(parents=True)
    canonical = OUT / "certified" / mode
    protocol = load(canonical / "protocol.json")
    protocol["started"] = time.time()
    atomic(root / "protocol.json", protocol)
    job = "0p01pct__0p01pct"
    sealed = {}
    for a in LEVELS:
        shutil.copytree(canonical / a / "A", root / a / "A")
        for b in LEVELS:
            if a + "__" + b == job:
                continue
            reference = canonical / a / b / "B"
            verified = root / a / b / "B"
            verified.mkdir(parents=True)
            for name in ["schedule.json", "assignment.json.gz", "result.json"]:
                shutil.copyfile(reference / name, verified / name)
                sealed[verified / name] = sha(reference / name)
    env = dict(os.environ, TABLE3_PURE8_RECOVERY_ROOT=str(test.resolve()))
    cmd = [sys.executable, "-B", "-u", "-X", "utf8", str(HERE / "certified.py"), mode]

    def launch(n):
        log = test / f"controller{n}.log"
        with log.open("w", encoding="utf8") as f:
            return subprocess.Popen(cmd, env=env, stdout=f, stderr=subprocess.STDOUT), log

    def active():
        p = root / "progress.json"
        return load(p)["active"].get(job) if p.is_file() else None

    p1, _ = launch(1)
    pid = wait_until(active)
    original_worker = psutil.Process(pid)
    assert original_worker.cmdline()[-3:] == cmd[-2:] + [job]
    assert original_worker.environ()["TABLE3_PURE8_RECOVERY_ROOT"] == str(test.resolve())
    p1.terminate()
    p1.wait(timeout=10)
    p2, log2 = launch(2)
    wait_until(lambda: "Adopted active" in log2.read_text(encoding="utf8"))
    assert original_worker.is_running() and active() == pid
    p2.terminate()
    p2.wait(timeout=10)
    original_worker.terminate()
    original_worker.wait(timeout=10)
    pending = root / "0p01pct" / "0p01pct" / "B"
    assert not (pending / "result.json").exists()
    p3, _ = launch(3)
    newpid = wait_until(lambda: active() if active() not in (None, pid) else None)
    assert p3.wait(timeout=120) == 0
    assert all(sha(f) == h for f, h in sealed.items())
    baseline = load(canonical / "0p01pct/0p01pct/B/result.json")
    result = load(pending / "result.json")
    assert result["eligible"] and result["replay"]["valid"]
    for metric in ["cmax", "secondary"]:
        assert abs(result["measured"][metric] - baseline["measured"][metric]) < 1e-6
    assert load(root / "progress.json")["completed"] == 9
    atomic(test / "audit.json", dict(waited_for_controller_adoption=True,
        adopted_pid=pid, restarted_worker_pid=newpid, preserved_native_inputs=len(sealed),
        recovered_valid_cells=9, checked_result=result["measured"],
        official_reference_sha256=sha(canonical / "0p01pct/0p01pct/B/result.json")))
    print("Verified adoption, restart, and reuse:", test, flush=True)


if __name__ == "__main__":
    main()

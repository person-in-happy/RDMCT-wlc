"""Repeat a wall-time overrun once under the same joint-objective protocol."""
import sys

import run
from run import read, save


def main():
    key = sys.argv[1]
    base = run.OUT
    first = read(base / "runs" / key / "result.json")
    job = first["job"]
    assert job["kind"] == "joint" and first["record"]["status"] == "timelimit"
    assert first["record"]["seconds"] > job["seconds"] + 1 and not first["eligible"]
    run.OUT = base / "joint_retries" / key
    run.OUT.mkdir(parents=True, exist_ok=True)
    if (run.OUT / "runs" / key / "result.json").exists():
        return
    save(run.OUT / "protocol.json", dict(jobs={key: job}, solver_threads=1,
         rule="One retry for a wall-time overrun. Use the first budget-eligible attempt."))
    print(f"{key} | 0/1 completed | 0 failed | solver budget {job['seconds']} s", flush=True)
    run.worker(key)
    record = read(run.OUT / "runs" / key / "result.json")
    print(f"1/1 completed | 0 failed | budget eligible {record['eligible']} | ETA 0", flush=True)


if __name__ == "__main__":
    main()

"""Replay the existing 10% handoffs with a 10% secondary stopping rule."""
import csv
from datetime import datetime
import json
import msvcrt
import shutil
from statistics import mean
import subprocess
import sys
import time

import solve

OUTPUT = solve.OUT / "ten_percent"
LEVEL = "10pct"
JOBS = [(s, arm) for s in (1, 2, 3) for arm in solve.ARMS]


def destination(seed, arm, level=LEVEL):
    return OUTPUT / "runs" / f"s{seed}_{arm}" / level


def run_pair(seed, arm):
    source = solve.directory(seed, arm, LEVEL) / "handoff.json"
    target = destination(seed, arm) / source.name
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and solve.sha(target) != solve.sha(source):
        raise ValueError("Different first-stage handoff on resume")
    shutil.copyfile(source, target)
    # Inputs still come from the original frozen initialization. Only the new
    # physical replay and the second-stage solve go into the new output tree.
    solve.directory = destination
    solve.LEVELS = {LEVEL: .10}
    solve.B_GAP = .10
    solve.finish(seed, arm, LEVEL)


def checked(seed, arm):
    folder = destination(seed, arm)
    rec = solve.read(folder / "result.json")
    b = solve.read(folder / "B/runs/endpoint/result.json")
    assert rec["verified"] and (rec["seed"], rec["arm"], rec["level"]) == (seed, arm, LEVEL)
    assert rec["handoff_sha256"] == solve.sha(solve.directory(seed, arm, LEVEL) / "handoff.json")
    assert solve.relative(rec["gate"]["upper"], rec["gate"]["lower"]) <= .10 + 1e-9
    assert b["job"]["gap"] == .10 and b["job"]["seconds"] is None and b["replay"]["valid"]
    assert rec["secondary"]["gap"] <= .10 + 1e-9 and b["eligible"]
    for name, sha in b["files"].items():
        assert solve.sha(folder / "B/runs/endpoint" / name) == sha
    return rec


def main():
    protocol = solve.manifest()
    protocol.update(gap_A={LEVEL: .10}, gap_B=.10, expected=len(JOBS),
                    original_protocol_sha256=solve.sha(solve.OUT / "protocol.json"),
                    handoffs={f"{s}/{a}": solve.sha(solve.directory(s, a, LEVEL) / "handoff.json")
                              for s, a in JOBS})
    path = OUTPUT / "protocol.json"
    if path.exists() and solve.read(path) != json.loads(json.dumps(protocol)):
        raise ValueError("Different registered ten-percent inputs")
    solve.save(path, protocol)
    started = time.monotonic()
    rows = []
    for seed, arm in JOBS:
        if not (destination(seed, arm) / "result.json").is_file():
            log = OUTPUT / "logs" / f"s{seed}_{arm}.log"
            log.parent.mkdir(exist_ok=True)
            with log.open("a", encoding="utf8") as stream:
                subprocess.run([sys.executable, "-B", "-u", "-X", "utf8", __file__, str(seed), arm],
                               cwd=solve.ROOT, stdout=stream, stderr=subprocess.STDOUT, check=True)
        r = checked(seed, arm)
        rows.append(dict(seed=seed, arm=arm, start_s=r["start_cmax"], cmax_s=r["after"]["cmax"],
                         fB_before=r["before"]["secondary"], fB_after=r["after"]["secondary"],
                         calls=r["gate"]["calls"], gap_A=solve.relative(r["gate"]["upper"], r["gate"]["lower"]),
                         gap_B=r["secondary"]["gap"], handoff_sha256=r["handoff_sha256"]))
        eta = (time.monotonic()-started) * (len(JOBS)-len(rows)) / len(rows)
        state = dict(updated=datetime.now().astimezone().isoformat(timespec="seconds"), verified=len(rows),
                     total=len(JOBS), failed={}, eta_seconds=eta, gap_A=.1, gap_B=.1,
                     protocol=path.relative_to(solve.ROOT).as_posix())
        for root in (OUTPUT, solve.OUT):
            solve.save(root / "progress.json", state)
        print(f"{len(rows)}/{len(JOBS)} verified | 0 failed | ETA {eta:.0f} s | {seed} {arm}", flush=True)
    with (OUTPUT / "verified_runs.csv").open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    lines = ["# 4片混跑，两阶段间隙均为10%", "",
             "四种方法使用三个求解种子。第一阶段取原试验首次达到10%的排程，第二阶段按10%重新求解，并在原模型上复核。", "",
             "|方法|种子数|平均工期（s）|交接时的平均工艺目标|结束时的平均工艺目标|选割调用合计|",
             "|---|---:|---:|---:|---:|---:|"]
    for arm, label in zip(solve.ARMS, ["完整策略", "关闭重排", "省略分层初始化", "投影参照"]):
        group = [r for r in rows if r["arm"] == arm]
        lines.append(f"|{label}|{len(group)}|{mean(r['cmax_s'] for r in group):.2f}|"
                     f"{mean(r['fB_before'] for r in group):.2f}|{mean(r['fB_after'] for r in group):.2f}|"
                     f"{sum(r['calls'] for r in group)}|")
    if all(r["calls"] == 0 for r in rows):
        lines.extend(["", "三个种子均在起始排程达到工期门槛。此组能检验初始化与第二阶段的作用，选割重排在本组没有触发。"])
    (OUTPUT / "REPORT_CN.md").write_text("\n".join(lines) + "\n", encoding="utf8")


if __name__ == "__main__":
    if len(sys.argv) == 3:
        run_pair(int(sys.argv[1]), sys.argv[2])
    else:
        OUTPUT.mkdir(exist_ok=True)
        with (solve.OUT / "controller.lock").open("a+b") as lock:
            lock.seek(0)
            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
            main()

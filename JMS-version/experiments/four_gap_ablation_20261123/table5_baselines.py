"""Matched table 5 controls, with the archived preparations and both gaps at 10%."""
import csv
from pathlib import Path
import subprocess
import sys
import time

import solve


OUT = solve.JMS / "results/table5_baselines_20261124"
METHODS = {"full": "full", "hem": "hem_spbs", "scip_default": "default",
           "no_rerank": "no_rerank", "no_spbs": "full"}
GAP = 0.10


def directory(seed, arm, level="10pct"):
    return OUT / "runs" / f"s{seed}_{arm}" / level


def run(seed, arm):
    src, initial, data = solve.source(seed, arm)
    cfg = solve.Config(**data["config"])
    assert cfg.chamber_residency_basis == "nonprocessing"
    assert cfg.module_residency == cfg.robot_residency == 100 and cfg.cleaning_interval == 10
    dest = directory(seed, arm)
    dest.mkdir(parents=True, exist_ok=True)
    solve.directory = directory
    solve.LEVELS = {"10pct": GAP}
    solve.B_GAP = GAP
    method = METHODS[arm]
    task = dict(kind="scip", method=method, n=4, seed=seed, train=1, seconds=None,
                gap=GAP, structure="free", bounds=True)
    checked, gate = solve.cell.primary(task, cfg, data, solve.cell.values(src/"assignment.json.gz"),
                                       dest, initial["assignment_sha256"])
    solve.save(dest/"stage_A.json", dict(task=task, record=gate))
    solve.open_gate(seed, arm, "10pct", src, gate,
                    None if gate.get("initial_proof") else checked[1]["nonzero"], None)
    started = time.perf_counter()
    solve.finish(seed, arm, "10pct")
    after_handoff = time.perf_counter() - started
    r = solve.read(dest/"result.json")
    endpoint = dest/"B/runs/endpoint"
    b = solve.read(endpoint/"result.json")
    assert r["verified"] and b["replay"]["valid"] and b["eligible"]
    assert r["handoff_sha256"] == solve.sha(dest/"handoff.json")
    assert r["start_sha256"] == initial["assignment_sha256"]
    assert b["job"]["gap"] == GAP and b["job"]["seconds"] is None
    assert b["job"]["assignment_sha256"] == solve.sha(dest/"A/assignment.json.gz")
    for name, digest in b["files"].items():
        assert digest == solve.sha(endpoint/name)
    solve.save(dest/"timing.json", dict(seed=seed, arm=arm, method=method,
               start_sha256=r["start_sha256"], result_sha256=solve.sha(dest/"result.json"),
               gate_status=gate["status"], f_A=r["after"]["cmax"],
               f_B_handoff=r["before"]["secondary"], f_B=r["after"]["secondary"],
               prep_s=r["prep_seconds"], A_search_s=gate["seconds"], post_handoff_s=after_handoff,
               total_s=r["prep_seconds"] + gate["seconds"] + after_handoff))


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    manifest = dict(parent_sha256=solve.sha(solve.OUT/"ten_percent/protocol.json"),
                    driver_sha256=solve.sha(Path(__file__)), methods=METHODS,
                    case=solve.CASE, seeds=[1,2,3], training_seed=1, gap_A=GAP, gap_B=GAP,
                    threads=1, concurrency=1, shared_initialization="prepared except no_spbs",
                    hem=solve.policy_record("hem", 1), full=solve.policy_record("proposed", 1),
                    input_hashes={f"{s}/{a}": solve.source(s,a)[1]["assignment_sha256"]
                                  for s in (1,2,3) for a in ("full","no_spbs")},
                    timing="Measured preparation + search to gate + perf_counter around finish(), including replay and validation.")
    path=OUT/"protocol.json"
    if path.exists() and solve.read(path) != manifest:
        raise ValueError("Existing comparison has a different protocol")
    solve.save(path,manifest)
    methods=list(METHODS)
    jobs=[(s,arm) for s in (1,2,3) for arm in methods[s-1:]+methods[:s-1]]
    start=time.monotonic()
    rows=[]
    for seed, arm in jobs:
        dest=directory(seed,arm)
        if not (dest/"timing.json").exists():
            subprocess.run([sys.executable,"-B","-u","-X","utf8",__file__,str(seed),arm],check=True)
        row=solve.read(dest/"timing.json")
        assert row["result_sha256"]==solve.sha(dest/"result.json")
        rows.append(row)
        eta=(time.monotonic()-start)*(len(jobs)-len(rows))/len(rows)
        print(f"{len(rows)}/{len(jobs)} verified | 0 failed | ETA {eta:.0f} s | seed {seed} {arm}",flush=True)
    with (OUT/"verified_runs.csv").open("w",encoding="utf-8-sig",newline="") as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


if __name__=="__main__":
    if len(sys.argv)==3:
        run(int(sys.argv[1]),sys.argv[2])
    else:
        main()

"""Continue makespan search from the verified 6066 s mixed schedule. Run again to resume."""
import argparse
from pathlib import Path
import sys
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scale75_mixed_both0p001pct_20261119"))
import run_equal_gaps as original

runner = original.run_mixed
first, primary, old = runner.first, runner.primary, runner.old
SOURCE = original.OUT
DEST = old.JMS / "results" / "scale75_continue_A0p001pct_D_20261120"


def restore_input():
    report = old.read(SOURCE / "report.json")
    final = SOURCE / "final"
    summary = old.read(final / "summary.json")
    for phase in ("primary", "final"):
        case = SOURCE / phase
        for name, sha in old.read(case / "summary.json")["artifact_sha256"].items():
            if old.digest(case / name) != sha:
                raise ValueError(f"Frozen input changed: {case / name}")
    if (report["final_result_sha256"] != old.digest(final / "result.json")
            or report["certificate_sha256"] != old.digest(final / "continuous_timing_certificate.json")):
        raise ValueError("Source report and schedule hashes disagree")
    with patch.object(first, "BASE", SOURCE / "primary"):
        cfg, blocks, _ = first.restore_seed()
    starts = old.restore(final / "checkpoint.json", summary["protocol_sha256"])["starts"]
    data, _, _, _ = first.check_schedule(first.ChamberIdle(cfg, blocks), blocks, starts)
    if data != old.read(final / "result.json") or data["cmax"] != report["idle_after"]["cmax"]:
        raise ValueError("Source event times do not reproduce the frozen schedule")
    primary_sha = old.read(SOURCE / "primary/summary.json")["protocol_sha256"]
    plan = old.restore(SOURCE / "primary/windows.json", primary_sha)["plan"]
    return cfg, plan, blocks, starts, data


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    handle = first.limit_process()
    with (old.output_lock(DEST), patch.multiple(runner, A_GAP=original.RELATIVE_GAP,
                                               B_GAP=original.RELATIVE_GAP, OUT=DEST), runner.settings()):
        first.wait_for_headroom()
        cfg, plan, blocks, seed, data = restore_input()
        lower = primary.workload_bound(cfg)
        spec = dict(source=SOURCE.name, source_report_sha256=old.digest(SOURCE / "report.json"),
                    code_sha256=old.digest(Path(__file__)), source_schedule_sha256=old.digest(SOURCE / "final/result.json"),
                    solver_code_sha256=old.read(SOURCE / "primary/campaign.json")["source_sha256"],
                    input_cmax=data["cmax"], sweeps=primary.SWEEPS, target=primary.TARGET,
                    primary="four further rolling-window sweeps with the archived grouping and chamber assignment",
                    secondary="one fixed-order idle solve, 40 seconds, with the new makespan cap",
                    global_workload_bound=lower, threads=1, process_limit_mib=1024)
        for name, sha in spec["solver_code_sha256"].items():
            if old.digest(old.JMS.parent / name) != sha:
                raise ValueError(f"Changed solver source {name}")
        token = old.fingerprint(spec)
        manifest, windows, picked = (DEST / name for name in ("campaign.json", "windows.json", "selection.json"))
        if manifest.exists():
            if old.fingerprint(old.read(manifest)) != token:
                raise ValueError("Different campaign in the destination")
        elif args.verify or any(p.name != ".run.lock" for p in DEST.iterdir()):
            raise ValueError("No matching campaign")
        else:
            old.dump(manifest, spec)
        engine = first.ChamberIdle(cfg, blocks)
        if args.verify:
            record = old.read(DEST / "report.json")
            for name, sha in record["artifact_sha256"].items():
                if old.digest(DEST / name) != sha:
                    raise ValueError(f"Changed result {name}")
            chosen = old.restore(picked, token)["starts"]
            witness, _, replay, _ = first.check_schedule(engine, blocks, chosen)
            cert = old.read(DEST / "original_row_audit/certificate.json")
            if (witness != old.read(DEST / "result.json") or record["final"] != engine.measure(chosen)
                    or record["replay"] != replay or cert["status"] != "all_original_rows_satisfied"
                    or cert["result_sha256"] != old.digest(DEST / "result.json") or cert["protocol_sha256"] != token
                    or record["workload_lower_bound_s"] != lower["seconds"]):
                raise ValueError("Independent schedule, constraints or bound verification failed")
            print(f"Verified {replay['checks']:,} replay checks and {cert['original_rows']:,} original rows.", flush=True)
            return
        if (DEST / "report.json").exists():
            print("Campaign already completed; use --verify to recheck the result.", flush=True)
            return
        if not windows.exists():
            old.checkpoint(windows, token, dict(plan=plan, starts=seed, initial_cmax=data["cmax"],
                           sweep=0, index=0, windows=[], records=[]))
        print(f"Start {data['cmax']} s, global workload bound {lower['seconds']} s. One worker, 1 GiB.", flush=True)
        state, _ = primary.optimize(DEST, token, primary.Search(cfg), {"cmax":data["cmax"]}, lower["seconds"], None)
        rows = state["records"]
        if any(row["relative_gap_limit"] != primary.TARGET for row in rows):
            raise ValueError("A makespan window used a different stopping threshold")
        if not picked.is_file():
            starts = state["starts"]
            before_idle = engine.measure(starts)
            print(f"Fixed-order idle optimization under {before_idle['cmax']} s; budget 40 s.", flush=True)
            candidate, row = engine.solve_idle(starts, before_idle, lower["seconds"], first.FIXED, 40)
            if row["relative_gap_limit"] != original.RELATIVE_GAP:
                raise ValueError("Incorrect secondary target")
            def rank(times):
                values = engine.measure(times)
                return (values["cmax"], values["idle"])
            chosen = min((seed, starts, candidate), key=rank)
            old.checkpoint(picked, token, dict(starts=chosen, secondary_solve=row, before_idle=before_idle))
        selection = old.restore(picked, token)
        chosen = selection["starts"]
        witness, paper_objectives, replay, _ = first.check_schedule(engine, blocks, chosen)
        if not (DEST / "result.json").exists():
            old.dump(DEST / "result.json", witness)
        elif old.read(DEST / "result.json") != witness:
            raise ValueError("Saved candidate mismatch")
        print("Replaying and checking all original model rows.", flush=True)
        cert = primary.audit_result(DEST, token, witness)
        final = engine.measure(chosen)
        files = ["campaign.json", "windows.json", "selection.json", "result.json",
                 "original_row_audit/certificate.json", "original_row_audit/assignment.json.gz"]
        record = dict(input=engine.measure(seed), before_idle=selection["before_idle"], final=final,
                      paper_objectives=paper_objectives, workload_lower_bound_s=lower["seconds"],
                      gap_upper_bound=(final["cmax"]-lower["seconds"])/lower["seconds"],
                      primary_target=primary.TARGET, windows=len(rows),
                      window_statuses={s:sum(r["status"] == s for r in rows) for s in sorted({r["status"] for r in rows})},
                      sweeps=[min(r["upper_after"] for r in rows if r["sweep"] == s) for s in sorted({r["sweep"] for r in rows})],
                      replay=replay, original_rows=cert["original_rows"], resources=first.sample(), peers=first.peers(),
                      artifact_sha256={n:old.digest(DEST / n) for n in files})
        old.dump(DEST / "report.json", record)
        primary.report(DEST, "completed", completed=1, failed=0, metrics=final)
        print(f"Complete 1/1 failed=0 ETA=0 | Cmax {data['cmax']} -> {final['cmax']} | idle {final['idle']}", flush=True)


if __name__ == "__main__":
    main()

"""Check the 1-second primary-optimality claim for the archived 6061 s witness."""
from pathlib import Path
import sys
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scale75_idle_20261119" / "refine"))
import extend

first, old = extend.first, extend.old
RUN = old.JMS / "results" / "scale75_idle_gap0p000000001pct_D_20261119"
SOURCE = RUN / "final"
DEST = old.JMS / "results" / "scale75_6061_primary_counterexample_20261120"


def earliest_times(timing):
    """Propagate t_b >= t_a + lag from zero. Every propagated value is a lower bound."""
    edges = sorted(timing.edges)
    if any(lag != int(lag) for _, _, lag in edges):
        raise ValueError("This integer-arithmetic check requires whole-second lags")
    times = [0] * len(timing.actions)
    for _ in range(len(times)):
        changed = False
        for a, b, lag in edges:
            value = times[a] + int(lag)
            if value > times[b]:
                times[b] = value
                changed = True
        if not changed:
            if any(t+tail > timing.cfg.horizon for t, tail in zip(times, timing.tails)):
                raise ValueError("An earliest event violates the time horizon")
            return times
    raise ValueError("Positive cycle in the fixed scheduling order")


def frozen(path, data):
    if path.exists():
        if old.read(path) != data:
            raise ValueError(f"Frozen file does not match replay: {path}")
    else:
        old.dump(path, data)


def main():
    handle = first.limit_process()
    first.wait_for_headroom()
    manifest = old.read(RUN / "run_manifest.json")
    summary = old.read(SOURCE / "summary.json")
    idle_cert = old.read(SOURCE / "continuous_timing_certificate.json")
    old_result = old.read(SOURCE / "result.json")
    source_sha = old.digest(SOURCE / "result.json")
    if (summary["artifact_sha256"]["result.json"] != source_sha or idle_cert["result_sha256"] != source_sha
            or idle_cert["feasible_plotted_idle"] != summary["new"]["idle"]):
        raise ValueError("Source schedule and idle certificate disagree")
    with patch.object(first, "BASE", RUN.parent / manifest["source_case"]):
        cfg, blocks, _ = first.restore_seed()
    starts = old.restore(SOURCE / "checkpoint.json", summary["protocol_sha256"])["starts"]
    timing = first.fixed_timing(cfg, blocks, starts)
    if timing.schedule(starts) != old_result:
        raise ValueError("Fixed-order reconstruction changed the source schedule")
    print("1/3 Source schedule reproduced. Computing earliest starts for the same order.", flush=True)
    times = earliest_times(timing)
    candidate = timing.schedule(times)
    A = timing.solve("A", starts)
    if not (A["status"] == "optimal" and A["fixed_order_bound"] == A["objective"] == candidate["cmax"]):
        raise ValueError("SCIP timing optimum and exact precedence calculation disagree")
    if (candidate["config"] != old_result["config"] or candidate["pairs"] != old_result["pairs"]
            or [e["name"] for e in candidate["events"]] != [e["name"] for e in old_result["events"]]):
        raise ValueError("The retiming changed source decisions")
    metrics, replay = old.tested_metrics(candidate)
    idle = first.ChamberIdle(cfg, blocks).measure(times)
    if metrics["cmax"] != idle["cmax"] or not replay["valid"]:
        raise ValueError("Inconsistent product return time")
    gap_bound = RUN.parent / "scale75_chamber_bound_D_20261120" / "certificate.json"
    global_cert = old.read(gap_bound)
    if global_cert["config_sha256"] != old.fingerprint(old_result["config"]):
        raise ValueError("Global bound is for another model")
    protocol = dict(source_sha256=source_sha, source_checkpoint_sha256=old.digest(SOURCE/"checkpoint.json"),
                    original_idle_certificate_sha256=old.digest(SOURCE/"continuous_timing_certificate.json"),
                    global_certificate_sha256=old.digest(gap_bound), checker_sha256=old.digest(Path(__file__)),
                    method="exact integer propagation and independent continuous makespan LP on the archived event order")
    with old.output_lock(DEST):
        frozen(DEST / "campaign.json", protocol)
        frozen(DEST / "result.json", candidate)
        print("2/3 Timing checked. Auditing all original 75-wafer model rows.", flush=True)
        cert = first.prior.audit_result(DEST, old.fingerprint(protocol), candidate)
        if (cert["status"] != "all_original_rows_satisfied" or cert["cmax"] != metrics["cmax"]
                or cert["result_sha256"] != old.digest(DEST / "result.json")):
            raise ValueError("Original-model row audit failed")
        upper, lower = metrics["cmax"], global_cert["lower_s"]
        report = dict(source_makespan_s=old_result["cmax"], source_idle_s=summary["new"]["idle"],
                      source_fixed_order_idle_bound_s=idle_cert["lower_bound"],
                      source_idle_solver_target_percent=manifest["requested_gap_percent"],
                      retimed_makespan_s=upper, retimed_chamber_metrics=idle,
                      fixed_order_makespan_optimum_s=A["objective"], fixed_order_makespan_lower_s=A["fixed_order_bound"],
                      full_model_makespan_lower_s=lower, full_model_feasible_upper_s=upper,
                      source_suboptimality_at_least_s=old_result["cmax"]-upper,
                      source_suboptimality_at_most_s=old_result["cmax"]-lower,
                      retimed_global_gap_upper=(upper-lower)/lower,
                      original_rows=cert["original_rows"], replay=replay, retimed_result_sha256=cert["result_sha256"],
                      full_model_feasibility_certificate_sha256=old.digest(DEST/"original_row_audit/certificate.json"))
        frozen(DEST / "report.json", report)
        print(f"3/3 Verified {cert['original_rows']:,} rows. Source {old_result['cmax']} s, "
              f"retimed {upper} s, lower bound across orders {lower} s.", flush=True)


if __name__ == "__main__":
    main()

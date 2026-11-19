"""Run the 75-wafer mixed instance from its original seed with two stopping gaps."""
import argparse
from contextlib import ExitStack, contextmanager
from decimal import Decimal
import json
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scale75_idle_20261119" / "refine"))
import extend
import check_bound
import figures
import idle
import neighborhood
import timing

first = extend.first
primary = first.prior
old = first.old
OUT = old.JMS / "results" / "scale75_mixed_A1pct_B0p001pct_D_20261119"
A_GAP = 0.01
B_GAP = 0.00001
PHASES = ("primary", "first", "final")


@contextmanager
def settings():
    """Configure the archived drivers in this process, leaving their source hashes intact."""
    cp = neighborhood.cp_model
    base_window = neighborhood.WindowSearch.solve
    base_lp = timing.BatchTiming.solve
    base_protocol = primary.protocol
    idle_protocol = first.protocol
    base_draw = figures.draw

    def window(engine, *args):
        used = []

        class MakespanSolver(cp.CpSolver):
            def solve(self, model):
                self.parameters.relative_gap_limit = A_GAP
                used.append(self.parameters.relative_gap_limit)
                return super().solve(model)

        api = SimpleNamespace(CpSolver=MakespanSolver, CpModel=cp.CpModel, OPTIMAL=cp.OPTIMAL,
                              FEASIBLE=cp.FEASIBLE, INFEASIBLE=cp.INFEASIBLE, MODEL_INVALID=cp.MODEL_INVALID)
        with patch.object(neighborhood, "cp_model", api):
            candidate, row = base_window(engine, *args)
        if used != [A_GAP]:
            raise ValueError("The makespan window did not use the requested native gap")
        row["relative_gap_limit"] = used[0]
        return candidate, row

    def fixed_lp(engine, stage, initial, cap=None):
        scip = timing.scip
        used = []

        def model(name):
            solver = scip.Model(name)
            if stage == "A":
                solver.setRealParam("limits/gap", A_GAP)
            used.append(solver.getParam("limits/gap"))
            return solver

        with patch.object(timing, "scip", SimpleNamespace(Model=model, quicksum=scip.quicksum)):
            row = base_lp(engine, stage, initial, cap)
        row["relative_gap_limit"], = used
        return row

    def primary_protocol():
        spec = base_protocol()
        for path in (Path(__file__), HERE / "control.ps1"):
            spec["source_sha256"][path.relative_to(old.JMS.parent).as_posix()] = old.digest(path)
        spec.update(fixed_order_makespan_relative_gap=A_GAP, secondary_idle_relative_gap=B_GAP,
                    primary_weighted_wait_tiebreak="archived SCIP default under the attained makespan cap")
        return spec

    def first_protocol():
        spec = idle_protocol()
        spec.update(first_stage_reused=False, first_stage_origin="recomputed in this campaign from original seed",
                    primary_result_sha256=old.digest(primary.OUT / "result.json"))
        return spec

    def labelled_draw(data, lanes, dest):
        plt = figures.plt

        def subplots(**kwargs):
            fig, axis = plt.subplots(**kwargs)
            fig.text(.978, .88, f"完工时间求解间隙阈值 {100*A_GAP:g}%", ha="right", fontsize=11, color="#355266")
            return fig, axis

        with patch.object(figures, "plt", SimpleNamespace(rcParams=plt.rcParams, subplots=subplots, close=plt.close)):
            return base_draw(data, lanes, dest)

    with ExitStack() as stack:
        stack.enter_context(patch.multiple(primary, TARGET=A_GAP, OUT=OUT / "primary", protocol=primary_protocol))
        stack.enter_context(patch.multiple(first, BASE=primary.OUT, OUT=OUT / "first", GAP=B_GAP, protocol=first_protocol))
        stack.enter_context(patch.multiple(extend, OUT=OUT / "final", GAP=B_GAP))
        stack.enter_context(patch.object(idle, "GAP", B_GAP))
        stack.enter_context(patch.multiple(figures, GAP=B_GAP, draw=labelled_draw))
        stack.enter_context(patch.object(neighborhood.WindowSearch, "solve", window))
        stack.enter_context(patch.object(timing.BatchTiming, "solve", fixed_lp))
        yield


def certify():
    path = extend.OUT / "continuous_timing_certificate.json"
    if path.is_file():
        return
    cap = old.read(primary.OUT / "summary.json")["new_metrics"]["cmax"]
    dump = old.dump

    def write(dest, record):
        if dest == path:
            if record["product_return_cap"] != cap:
                raise ValueError("The continuous model used a different makespan cap")
            record["scope"] = f"continuous event times, fixed grouping and resource orders, stage-A cap {cap:g} s"
            record["primary_result_sha256"] = old.digest(primary.OUT / "result.json")
            record["runner_sha256"] = old.digest(Path(__file__))
            gap = relative_gap(record["feasible_plotted_idle"], record["lower_bound"])
            record["plotted_relative_gap"] = float(gap)
            record["plotted_target_met"] = gap <= Decimal(str(B_GAP))
        dump(dest, record)

    with patch.object(old, "dump", write):
        check_bound.certify(extend.OUT)


def relative_gap(upper, lower):
    u, l = Decimal(str(upper)), Decimal(str(lower))
    if l > u or l <= 0:
        raise ValueError(f"Invalid recorded objective bounds {l}, {u}")
    return (u-l)/l


def evidence():
    a, b, final = [old.read(OUT / phase / "summary.json") for phase in PHASES]
    b_input = old.read(first.OUT / "campaign.json")
    cert = old.read(extend.OUT / "continuous_timing_certificate.json")
    primary_sha = old.digest(primary.OUT / "result.json")
    a_solves = old.restore(primary.OUT / "windows.json", a["protocol_sha256"])["records"]
    first_solves = old.restore(first.OUT / "checkpoint.json", b["protocol_sha256"])["records"]
    final_steps = old.restore(extend.OUT / "checkpoint.json", final["protocol_sha256"])["records"]
    proposals = [r["solve"] for r in final_steps if r["step"] == "proposal"]
    idle_solves = first_solves + [r["solve"] for r in final_steps if r["step"] != "proposal"]
    caps = final["baseline"]
    final_metrics = final["new"]
    if not (a_solves and idle_solves and len(first_solves) == len(first.STEPS) and len(final_steps) == len(extend.steps())
            and all(r["relative_gap_limit"] == A_GAP for r in a_solves + proposals)
            and all(r["relative_gap_limit"] == B_GAP for r in idle_solves)
            and a["target_global_relative_gap"] == a["search"]["refine"]["phases"]["A"]["relative_gap_limit"] == A_GAP
            and b_input["first_stage_window_gap"] == A_GAP and final["stage_B_relative_gap"] == B_GAP
            and a["new_metrics"]["cmax"] == b_input["primary_cap"] == caps["cmax"] == cert["product_return_cap"]
            and b_input["primary_result_sha256"] == cert["primary_result_sha256"] == primary_sha
            and cert["result_sha256"] == old.digest(extend.OUT / "result.json")
            and cert["protocol_sha256"] == final["protocol_sha256"] and cert["solver_gap_limit"] == B_GAP
            and cert["runner_sha256"] == old.digest(Path(__file__))
            and cert["code_sha256"] == old.digest(Path(check_bound.__file__))
            and cert["feasible_plotted_idle"] == final_metrics["idle"] and final_metrics["cmax"] <= caps["cmax"]):
        raise ValueError("Recorded solver settings, phase handoff or final certificate disagree")
    gap = relative_gap(final_metrics["idle"], cert["lower_bound"])
    if float(gap) != cert["plotted_relative_gap"] or (gap <= Decimal(str(B_GAP))) != cert["plotted_target_met"]:
        raise ValueError("Certificate does not match its raw bounds")
    ports = b_input["config"]["load_ports"].values()
    return dict(mix={mode:sum(p[mode] for p in ports) for mode in ("4x1", "2x2")},
                original_case=old.DEFAULT.name, original_seed_cmax_s=a["baseline_metrics"]["cmax"],
                primary_relative_gap=A_GAP, idle_relative_gap=B_GAP, primary_recomputed=True,
                makespan_search_windows=len(a_solves), makespan_proposals_in_idle_search=len(proposals),
                idle_search_and_tiebreak_solves=len(idle_solves),
                primary_cmax_s=caps["cmax"], primary_global_lower_bound_s=final["global_primary_lower_bound"],
                primary_global_relative_gap_upper_bound=a["certified_relative_gap_upper_bound"],
                primary_global_target_certified=a["global_target_certified"],
                primary_stop="workload bound target" if a["global_target_certified"] else "completed configured sweeps",
                idle_before=caps, idle_after=final_metrics,
                idle_rate=final_metrics["idle"]/(2*final_metrics["cmax"]),
                fixed_order_continuous_lower_bound_s=cert["lower_bound"],
                fixed_order_relative_gap=float(gap), fixed_order_target_met=cert["plotted_target_met"],
                unrestricted_idle_target_certified=final["unrestricted_secondary_gap_certified"],
                replay=final["replay"], original_constraint_rows=final["full_model_rows_checked"],
                worker_peak_rss_mib=max(a["process_resources"]["peak_rss_mib"], b["resources"]["peak_rss_mib"],
                                         final["resources"]["peak_rss_mib"], cert["resources"]["peak_rss_mib"]),
                primary_result_sha256=primary_sha, final_result_sha256=cert["result_sha256"],
                final_figures=final["figures"]["files"], detail_pages=final["figures"]["detail_pages"],
                certificate_sha256=old.digest(extend.OUT / "continuous_timing_certificate.json"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=(*PHASES, "certify", "verify", "status"))
    parser.add_argument("--pause-after", type=int)
    args = parser.parse_args()
    if args.phase == "status":
        status = {}
        for phase in PHASES:
            path = OUT / phase / "progress.json"
            status[phase] = old.read(path) if path.exists() else {"stage":"pending"}
        status["certified_and_verified"] = (OUT / "report.json").is_file()
        print(json.dumps(status, ensure_ascii=False, indent=2))
        return
    handle = first.limit_process()
    with settings(), old.output_lock(OUT):
        first.wait_for_headroom()
        runners = {"primary":primary.execute, "first":first.execute, "final":extend.run}
        if args.phase in runners:
            dest = OUT / args.phase
            runners[args.phase](dest, args.pause_after)
            if not (dest / "summary.json").is_file():
                raise SystemExit(20)
            return
        primary.verify(primary.OUT)
        first.verify(first.OUT)
        if args.phase == "certify":
            certify()
        extend.verify(extend.OUT)
        report = evidence()
        path = OUT / "report.json"
        if path.exists():
            if old.read(path) != report:
                raise ValueError("Frozen two-stage report mismatch")
        elif args.phase == "certify":
            old.dump(path, report)
        else:
            raise ValueError("Two-stage report missing")
        print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()

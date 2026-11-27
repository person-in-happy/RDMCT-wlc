"""Run RL-DMCT from a Pjob configuration or an already prepared physical schedule."""
import argparse
from contextlib import contextmanager
import math
import os
from pathlib import Path
import statistics
import sys
import threading
import time

HERE = Path(__file__).resolve().parent
JMS = HERE.parents[1]
BACKEND = JMS / "model4_pjob_nonprocessing_20261103"
sys.path.insert(0, str(HERE.parent / "manuscript_certified_gaps_20261119"))
from design import read, save, sha, sparse


def arguments(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="Pjob config or validated schedule (.json or .json.gz)")
    parser.add_argument("output", type=Path, help="dedicated run directory; repeat the command to resume")
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--training-seed", type=int, default=1)
    parser.add_argument("--spbs-seconds", type=float,
                        help="initialization budget (config: 60 s, prepared schedule: 0 s)")
    parser.add_argument("--use-input-candidate-limits", action="store_true",
                        help="retain the input's pair/cycle limits in A (default: full domain)")
    for stage, gap in (("a", .0001), ("b", .01)):
        parser.add_argument(f"--gap-{stage}", type=float, default=gap, help="relative gap as a fraction")
        parser.add_argument(f"--stall-nodes-{stage}", type=int, default=1000,
                            help="nodes without a better incumbent (default 1000; -1 disables)")
        parser.add_argument(f"--seconds-{stage}", type=float, help="optional cumulative SCIP search seconds")
    args = parser.parse_args(argv)
    for k in ("a", "b"):
        gap = getattr(args, f"gap_{k}")
        limit = getattr(args, f"stall_nodes_{k}")
        seconds = getattr(args, f"seconds_{k}")
        if not math.isfinite(gap) or gap < 0 or (limit != -1 and not 1 <= limit < 2**63):
            parser.error("gap must be finite and nonnegative; stall nodes must be positive or -1")
        if seconds is not None and (not math.isfinite(seconds) or seconds <= 0):
            parser.error("search seconds must be finite and positive")
    if args.spbs_seconds is not None and (not math.isfinite(args.spbs_seconds) or args.spbs_seconds < 0):
        parser.error("SPBS seconds must be finite and nonnegative")
    return args


class Progress:
    """Persist elapsed active wall time separately from the native search budgets."""

    def __init__(self, output, budgets, estimates):
        self.path = output / "status.json"
        self.budgets = budgets
        self.estimates = estimates
        previous = read(self.path) if self.path.exists() else {}
        self.spent = previous.get("charged_search_s", {"A": 0., "B": 0.})
        self.carry = previous.get("elapsed_s", 0.)
        if previous.get("in_search"):
            # A hard process exit has no exact end timestamp. Charge the uncertain
            # interval conservatively, bounded by the interrupted stage's budget.
            k = previous["stage"]
            if budgets[k] is not None:
                unknown = max(0., time.time() - previous["updated_at"])
                self.spent[k] = min(budgets[k], self.spent[k] + unknown)
        self.start = time.monotonic()
        self.stage_start = self.start
        self.stage = "A"
        self.done = 0
        self.in_search_since = None
        self.lock = threading.RLock()

    def report(self, status="running", error=None):
        with self.lock:
            now = time.monotonic()
            charged = self.spent.copy()
            if self.in_search_since is not None:
                charged[self.stage] += now - self.in_search_since
            elapsed = self.carry + now - self.start
            remaining = 0.
            for stage in ("A", "B")[self.done:]:
                budget = self.budgets[stage]
                if budget is not None:
                    remaining += max(0., budget - charged[stage])
                elif stage in self.estimates:
                    predicted = self.estimates[stage]
                    if stage == self.stage:
                        predicted -= now - self.stage_start
                    if predicted <= 0:
                        remaining = None
                        break
                    remaining += predicted
                else:
                    remaining = None
                    break
            basis = ("serial remaining search budgets or historical same-size mixed front-first timings; "
                     "model preparation and replay can add time")
            if remaining is None:
                basis = "no comparable estimate for the remaining extended-model search; update at stage handoff"
            total = elapsed + remaining if remaining is not None else None
            record = dict(stage=self.stage, status=status, pid=os.getpid(), updated_at=time.time(),
                          completed=self.done, failed=int(status == "failed"), elapsed_s=elapsed,
                          estimated_total_s=total, remaining_s=remaining, basis=basis,
                          charged_search_s=charged, in_search=self.in_search_since is not None)
            if error:
                record["error"] = error
            save(self.path, record)
            eta = "unknown" if remaining is None else f"~{remaining:.1f}s"
            predicted = "unknown" if total is None else f"~{total:.1f}s"
            print(f"{status} | {self.done}/2 completed | {record['failed']} failed | {self.stage} | "
                  f"elapsed {elapsed:.1f}s | total {predicted} | remaining {eta} | {basis}", flush=True)

    def search_clock(self, active):
        with self.lock:
            if active:
                self.in_search_since = time.monotonic()
            elif self.in_search_since is not None:
                self.spent[self.stage] += time.monotonic() - self.in_search_since
                self.in_search_since = None
            self.report()

    @contextmanager
    def heartbeat(self):
        stop = threading.Event()
        def update():
            while not stop.wait(5):
                self.report()
        thread = threading.Thread(target=update, daemon=True)
        thread.start()
        try:
            yield
        finally:
            stop.set()
            thread.join()


def historical_estimates(cfg):
    counts = [sum(port.get(mode, 0) for port in cfg["load_ports"].values()) for mode in ("4x1", "2x2")]
    if counts != [2, 2] or cfg.get("cleaning_interval", 3) != 10:
        return {}
    timings = [JMS / f"results/huber_residence_20261125/runs/ref5_{seed}/timing.json" for seed in (1, 2, 3)]
    rows = [read(path) for path in timings if path.exists()]
    if not rows:
        return {}
    return {"A": statistics.median(row["prep_seconds"] + row["A_seconds"] for row in rows),
            "B": statistics.median(row["B_wall_seconds"] for row in rows)}


def starting_schedule(cfg):
    from model import Config
    from seed import construct
    config = Config(**cfg)
    for balanced in (False, True):
        try:
            return construct(config, balanced=balanced)
        except ValueError as error:
            failure = error
    raise ValueError(f"Initialization failed to construct a feasible schedule: {failure}. "
                     "Supply a validated schedule for this configuration.") from failure


def run(args):
    from phases import run_phase
    from joint_algorithms import policy_record
    from run_matched_supplement import output_lock
    from scip_imports import scip

    data = read(args.input)
    prepared = "events" in data
    cfg = data.get("config", data)
    init_seconds = args.spbs_seconds if args.spbs_seconds is not None else (0. if prepared else 60.)
    budgets = {"A": args.seconds_a, "B": args.seconds_b}
    policy = policy_record("proposed", args.training_seed)
    sources = ([HERE / "run.py", HERE / "phases.py", HERE.parent / "terminal_unload_20261125/extended_model.py",
                HERE.parent / "square_residence_20261125/score.py", HERE.parent / "component_gap_restore_20261119/component.py"]
               + [BACKEND / name for name in ("model.py", "joint_algorithms.py", "seed.py", "physical_seed.py",
                  "joint_pairing_model.py", "joint_chamber_cycle_model.py", "physical_validate.py", "validate.py",
                  "pjobs.py", "pjob_order.py", "grippers.py")]
               + [JMS.parent / name for name in ("cie/code/run_cie_benchmarks.py", "cutsel_agent_parallel.py",
                                                  "pointer_net.py", "pointer_net_end_token.py", "beam_search.py", "utils.py")])
    signature = dict(input_sha256=sha(args.input), sources={p.relative_to(JMS.parent).as_posix(): sha(p) for p in sources},
                     policy_sha256=policy["sha256"], policy_config_sha256=policy["config_sha256"],
                     pyscipopt=scip.__version__, parameters={k: v for k, v in vars(args).items() if k not in ("input", "output")})
    out = args.output
    with output_lock(out):
        manifest = out / "run.json"
        if manifest.exists():
            if read(manifest) != signature:
                raise ValueError("The saved run has different inputs, model, policy or parameters. Use a separate output directory.")
        else:
            if any(p.name != ".run.lock" for p in out.iterdir()):
                raise ValueError(f"Expected a fresh or matching run directory: {out}")
            save(manifest, signature)
        progress = Progress(out, budgets, historical_estimates(cfg))
        schedule, assignment = None, None
        parent = sha(manifest)
        records = {}
        try:
            for stage in ("A", "B"):
                progress.stage = stage
                progress.stage_start = time.monotonic()
                folder = out / stage
                record_path = folder / "record.json"
                files = [folder / "schedule.json", folder / "assignment.json.gz"]
                if record_path.exists():
                    row = read(record_path)
                    if row["parent_sha256"] != parent or any(sha(p) != row["files"][p.name] for p in files):
                        raise ValueError(f"Cannot verify the saved stage {stage} endpoint")
                    schedule = read(files[0])
                    assignment = read(files[1])["nonzero"]
                else:
                    progress.report()
                    limit = budgets[stage]
                    left = None if limit is None else max(0., limit - progress.spent[stage])
                    k = stage.lower()
                    with progress.heartbeat():
                        if stage == "A":
                            schedule = data if prepared else starting_schedule(cfg)
                        row, schedule, assignment = run_phase(
                            stage, schedule, assignment=assignment, gap=getattr(args, f"gap_{k}"),
                            stall_nodes=getattr(args, f"stall_nodes_{k}"), seed=args.seed,
                            training_seed=args.training_seed, seconds=left,
                            full_domain=stage == "A" and not args.use_input_candidate_limits,
                            spbs_seconds=init_seconds if stage == "A" else 0., search_clock=progress.search_clock)
                    if row["stop_reason"] not in ("gap", "stagnation", "optimal") and not (
                            row["stop_reason"] == "timelimit" and limit is not None):
                        if row["native_status"] == "userinterrupt":
                            raise KeyboardInterrupt
                        raise RuntimeError(f"Unexpected SCIP termination in stage {stage}: {row['native_status']}")
                    save(files[0], schedule)
                    save(files[1], sparse(assignment))
                    row.update(parent_sha256=parent, files={p.name: sha(p) for p in files})
                    save(record_path, row)
                records[stage] = row
                progress.done += 1
                parent = sha(record_path)
            result = dict(stages=records, final_schedule="B/schedule.json", metrics=records["B"]["metrics"])
            final_path = out / "result.json"
            if (final_path.is_file() and progress.path.is_file() and read(final_path) == result
                    and read(progress.path)["status"] == "complete"):
                print("Verified both saved stage endpoints.", flush=True)
            else:
                save(final_path, result)
                progress.report("complete")
            return result
        except KeyboardInterrupt:
            progress.report("interrupted")
            raise
        except Exception as error:
            progress.report("failed", str(error))
            raise


if __name__ == "__main__":
    run(arguments())

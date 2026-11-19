"""One foreground, resumable 75-product mixed-recipe case under current D."""
import argparse
from collections import Counter
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
from importlib.metadata import version
import json
import math
import os
from pathlib import Path
import sys
import time

HERE = Path(__file__).resolve().parent
JMS = HERE.parents[1]
BACKEND = JMS/"model4_pjob_nonprocessing_20261103"
TOOLS = JMS/"tools"
DEFAULT = JMS/"results/scale75_mixed_D_20261118_r1"
WIDTH = 24
for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[name] = "1"
os.environ["CUDA_VISIBLE_DEVICES"] = ""
sys.path[:0] = [str(BACKEND), str(TOOLS), str(JMS/"experiments/finite_budget_20261116")]

from resources import CAP_MIB, RESERVE_MIB, limit_process, peers, sample, wait_for_headroom
from finite_budget import physical_metrics
from model import Config
from packing import Packing
from run_experiments import digest, dump, ports
from run_matched_supplement import output_lock
from timing import BatchTiming
from validate import validate


def stamp():
    return datetime.now(timezone.utc).isoformat()


def read(path):
    return json.loads(path.read_text("utf-8"))


def fingerprint(data):
    raw = json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    return hashlib.sha256(raw.encode()).hexdigest()


def protocol():
    files = [*HERE.glob("*.py"), *(BACKEND/name for name in (
        "model.py", "run_experiments.py", "run_matched_supplement.py", "validate.py", "physical_validate.py",
        "pjobs.py", "pjob_order.py", "seed.py", "grippers.py")), TOOLS/"current_defaults_swimlane.py",
        JMS/"experiments/finite_budget_20261116/finite_budget.py", JMS.parent/"scip_imports.py"]
    files = [p for p in files if not p.name.startswith("test_")]
    return dict(schema=1, case="75 products, current D, one mixed recipe instance",
                config=asdict(Config(ports(75, "mixed"))), beam_width=WIDTH, products_per_group=4,
                fixed_order_primary="min product return Cmax", fixed_order_secondary="sum wait + 10 max wait + 25 rhythm",
                lp_seconds_per_stage=60, scip_memory_mb=256, process_memory_limit_mib=CAP_MIB,
                system_reserve_mib=RESERVE_MIB, workers=1, threads=1, gpu=False, learned_cut_selection=False,
                versions={k: version(k) for k in ("pyscipopt", "numpy", "matplotlib", "psutil")},
                python=sys.version, source_sha256={p.relative_to(JMS.parent).as_posix(): digest(p) for p in files})


def checkpoint(path, contract, payload):
    dump(path, dict(protocol_sha256=contract, payload_sha256=fingerprint(payload), payload=payload))


def restore(path, contract):
    obj = read(path)
    if obj["protocol_sha256"] != contract or obj["payload_sha256"] != fingerprint(obj["payload"]):
        raise ValueError(f"Checkpoint integrity mismatch: {path}")
    return obj["payload"]


def tested_metrics(data):
    replay = validate(data)
    rows = [j for j in data["jobs"] if j["product"]]
    mode = {p["id"]: p["mode"] for p in data["pairs"]}
    expected = {"4x1": 37, "2x2": 38}
    if len(rows) != 75 or Counter(mode[j["pair"]] for j in rows) != expected:
        raise ValueError("Unexpected product inventory")
    if not replay["valid"] or not replay["pjob_release_order_check"]:
        raise ValueError(str(replay["errors"][:8]))
    metrics = physical_metrics(data)
    if abs(metrics["cmax"]-data["cmax"]) > 2e-4:
        raise ValueError("Product finish and event-derived Cmax disagree")
    return metrics, replay


def check_finished(out):
    final = read(out/"summary.json")
    if fingerprint(protocol()) != final["protocol_sha256"] or fingerprint(read(out/"campaign.json")) != final["protocol_sha256"]:
        raise ValueError("Frozen protocol differs")
    for rel, expected in final["sha256"].items():
        if digest(out/rel) != expected:
            raise ValueError(f"Changed output: {rel}")
    data = read(out/"result.json")
    metrics, replay = tested_metrics(data)
    if metrics != final["metrics"] or replay != final["replay"] or data["config"] != read(out/"campaign.json")["config"]:
        raise ValueError("Independent recheck disagrees with the evidence")
    return final


def execute(out, pause_after=None):
    # Bind all choices, checkpoints and final artifacts to one input and code version.
    with output_lock(out):
        spec = protocol()
        contract = fingerprint(spec)
        if (out/"campaign.json").exists():
            if fingerprint(read(out/"campaign.json")) != contract:
                raise ValueError("Configuration or source changed. Use a new output directory.")
        else:
            if any(p.name != ".run.lock" for p in out.iterdir()):
                raise ValueError("Use a new campaign directory")
            dump(out/"campaign.json", spec)
        if (out/"summary.json").exists():
            summary = check_finished(out)
            print(f"Already complete 1/1 | independent replay passed | Cmax={summary['metrics']['cmax']:g} s")
            return
        progress = out/"progress.json"
        attempt = dict(started_utc=stamp(), pid=os.getpid(), parallel_experiments=peers(), start_resources=sample())
        attempt_path = out/f"attempt_{time.time_ns()}.json"
        dump(attempt_path, attempt)
        start = time.monotonic()
        stage = "packing"
        try:
            wait_for_headroom()
            cfg = Config(**spec["config"])
            packing = Packing(cfg)
            saved = out/"search.json"
            beam, depth = [()], 0
            if saved.exists():
                state = restore(saved, contract)
                beam = [tuple(tuple(x) for x in plan) for plan in state["beam"]]
                depth = state["depth"]
            first = depth
            print(f"75 products | CPU threads=1 | process cap={CAP_MIB} MiB | groups restored={depth}/{packing.n}", flush=True)
            while depth < packing.n:
                wait_for_headroom()
                beam = packing.advance(beam, spec["beam_width"])
                depth += 1
                checkpoint(saved, contract, dict(depth=depth, beam=beam))
                elapsed = time.monotonic()-start
                eta = (packing.n-depth)*elapsed/(depth-first)
                mem = sample()
                dump(progress, dict(state="running", stage=stage, groups=depth, total_groups=packing.n, eta_search_s=eta, **mem))
                print(f"groups={depth}/{packing.n} failed=0 | search ETA {eta:.1f}s | RSS {mem['rss_mib']:.0f} MiB", flush=True)
                if depth == pause_after:
                    raise KeyboardInterrupt
            plan = beam[0]
            timing = BatchTiming(packing, plan)
            stages = {}
            for stage in ("A", "B"):
                path = out/f"timing_{stage}.json"
                if path.exists():
                    stages[stage] = restore(path, contract)
                    continue
                wait_for_headroom()
                print(f"Fixed-order LP {stage} | groups={depth}/{packing.n} failed=0 | solve budget 60s", flush=True)
                t0 = timing.initial if stage == "A" else stages["A"]["starts"]
                cap = None if stage == "A" else stages["A"]["metrics"]["cmax"]
                row = timing.solve(stage, t0, cap)
                if row["status"] == "userinterrupt":
                    raise KeyboardInterrupt
                data = timing.schedule(row["starts"])
                row["metrics"], _ = tested_metrics(data)
                key = "cmax" if stage == "A" else "secondary"
                if not math.isclose(row["metrics"][key], row["objective"], abs_tol=2e-4):
                    raise ValueError("Event-derived objective mismatch")
                if cap is not None and (row["metrics"]["cmax"] > cap+2e-4 or
                                        row["metrics"]["secondary"] > stages["A"]["metrics"]["secondary"]+2e-4):
                    raise ValueError("Refinement degraded a bounded objective")
                checkpoint(path, contract, row)
                stages[stage] = row
            data = timing.schedule(stages["B"]["starts"])
            metrics, replay = tested_metrics(data)
            dump(out/"result.json", data)
            stage = "figures"
            wait_for_headroom()
            print("75/75 products validated | failed=0 | rendering resource overview and time windows", flush=True)
            from plot import draw
            staging = out/".rendering"
            fig = draw(data, staging)
            figure_dir = out/"figures"
            figure_dir.mkdir(exist_ok=True)
            outputs = ["gantt_resources.png", "gantt_resources.svg", "gantt_resources.pdf", "gantt_details.pdf"]
            for name in outputs:
                (staging/name).replace(figure_dir/name)
            staging.rmdir()
            final_resources = sample()
            resources = dict(final_resources)
            # Include earlier interrupted executions of the same campaign.
            past = [read(p) for p in out.glob("attempt_*.json")]
            resources["peak_rss_mib"] = max([final_resources["peak_rss_mib"]] +
                [a["end_resources"]["peak_rss_mib"] for a in past if "end_resources" in a])
            names = ["campaign.json", "search.json", "timing_A.json", "timing_B.json", "result.json"] + ["figures/"+s for s in outputs]
            final = dict(state="completed", cases=1, products=75, mode_counts={"4x1":37, "2x2":38},
                         resources=resources, cycles_by_chamber={ch:dict(Counter(c["mode"] for c in data["cycles"]
                             if c["chamber"] == ch)) for ch in cfg.chambers}, metrics=metrics, replay=replay, figures=fig,
                         phases={s:{k:v for k,v in row.items() if k != "starts"} for s, row in stages.items()},
                         global_optimality_claim=False, unrestricted_model_checked=False, learned_policy_used=False,
                         protocol_sha256=contract, sha256={name:digest(out/name) for name in names}, finished_utc=stamp())
            dump(out/"summary.json", final)
            dump(progress, dict(state="completed", groups=depth, total_groups=packing.n, failed=0))
            attempt["outcome"] = "completed"
            print(f"Complete=1/1 failed=0 ETA=0 | Cmax={metrics['cmax']:g}s | peak RSS={resources['peak_rss_mib']:.1f} MiB", flush=True)
        except KeyboardInterrupt:
            saved_depth = restore(out/"search.json", contract)["depth"] if (out/"search.json").exists() else 0
            dump(progress, dict(state="paused", stage=stage, groups=saved_depth,
                                message="Resume from last committed checkpoint"))
            attempt["outcome"] = "paused"
            print("Paused | resume uses the last committed group or LP stage", flush=True)
        except Exception as exc:
            attempt["outcome"] = "failed"
            dump(progress, dict(state="failed", stage=stage, failed=1, error=repr(exc)))
            raise
        finally:
            attempt.update(ended_utc=stamp(), elapsed_s=time.monotonic()-start, end_resources=sample())
            dump(attempt_path, attempt)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("run", "resume", "status", "verify"))
    parser.add_argument("--campaign", type=Path, default=DEFAULT)
    parser.add_argument("--pause-after-groups", type=int, choices=range(1, 21), metavar="1..20")
    args = parser.parse_args()
    out = args.campaign.resolve()
    if args.action == "status":
        info = read(out/"summary.json") if (out/"summary.json").exists() else (
            read(out/"progress.json") if (out/"progress.json").exists() else {"state":"new"})
        print(json.dumps({k:info[k] for k in ("state", "stage", "groups", "total_groups", "metrics", "error") if k in info},
                         ensure_ascii=False, indent=2))
    elif args.action == "verify":
        final = check_finished(out)
        print(f"Verified all file hashes and {final['replay']['checks']} independent checks | Cmax={final['metrics']['cmax']:g}s")
    else:
        if out == JMS/"results" or not out.is_relative_to(JMS/"results"):
            parser.error("Use an isolated subdirectory in JMS-version/results")
        job_handle = limit_process()
        execute(out, args.pause_after_groups)


if __name__ == "__main__":
    main()

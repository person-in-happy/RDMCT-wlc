"""Foreground, restartable stage B using the certified 0.1% run as input."""
import argparse
from collections import Counter
import os
from pathlib import Path
import sys
import time

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scale75_repack_20261118"))
import improve as prior
from idle import ChamberIdle, GAP
from resources import limit_process, peers, sample, wait_for_headroom
from search import Search, fixed_timing, flexible_blocks, utilization

old = prior.old
BASE = prior.OUT
OUT = old.JMS / "results/scale75_idle_gap0p01pct_D_20261119_r1"
FIXED = (0, 0, 0)
# Time windows refer to the current incumbent, with a separate pass over its cleanup tail.
STEPS = [
    ("fixed", 0, 0, 0, 10), ("tail", 500, 0, 1050, 12), ("head", 0, 820, 550, 10),
    *[("forward", i, 650, 160, 4) for i in range(0, 6300, 650)],
    *[("reverse", i, 800, 200, 5) for i in reversed(range(300, 6300, 800))],
    ("head", 0, 690, 500, 10), ("tail", 650, 0, 1100, 12),
    ("certify", 0, 0, 0, 40), ("longest", 0, 0, 0, 15), ("waiting", 0, 0, 0, 20),
]


def protocol():
    saved = old.read(BASE/"summary.json")
    for name, digest in saved["artifact_sha256"].items():
        if old.digest(BASE/name) != digest:
            raise ValueError(f"Changed 0.1% input: {name}")
    for name, digest in old.read(BASE/"campaign.json")["source_sha256"].items():
        if old.digest(old.JMS.parent/name) != digest:
            raise ValueError(f"Changed 0.1% implementation: {name}")
    archived = prior.protocol()
    if old.fingerprint(archived) != saved["protocol_sha256"]:
        raise ValueError("Prior campaign no longer matches its inputs")
    return dict(case=BASE.name, input_summary_sha256=old.digest(BASE/"summary.json"),
                prior_protocol_sha256=saved["protocol_sha256"], config=archived["config"],
                primary_cap=saved["new_metrics"]["cmax"], first_stage_reused=True,
                first_stage_window_gap=archived["restricted_cp_relative_gap"],
                stage_B="min sum of completely empty seconds on CH2 and CH3 until actual product return",
                stage_B_relative_gap=GAP, integer_time_grid_seconds=1,
                guardrails="each chamber: idle and holding time capped at prior levels; equipment end and Cmax capped",
                steps=STEPS, process_limit_mib=1024, workers=1, gpu=False, versions=archived["versions"],
                source_sha256={p.name:old.digest(p) for p in sorted(HERE.glob("*.py")) if not p.name.startswith("test")})


def restore_seed():
    data = old.read(BASE/"result.json")
    cfg = old.Config(**data["config"])
    previous = old.restore(BASE/"windows.json", old.read(BASE/"summary.json")["protocol_sha256"])
    blocks = flexible_blocks(Search(cfg), previous["plan"])
    events, cycles = iter(data["events"]), iter(data["cycles"])
    starts = [int((next(cycles) if action.kind == "exposure" else next(events))["start"])
              for block in blocks for action in block.actions]
    restored = fixed_timing(cfg, blocks, starts).schedule(starts)
    for key in ("config", "events", "jobs", "cycles", "pairs", "cmax"):
        if restored[key] != data[key]:
            raise ValueError(f"Cannot reproduce 0.1% schedule from its saved event order: {key}")
    return cfg, blocks, starts


def check_schedule(engine, blocks, starts):
    data = fixed_timing(engine.cfg, blocks, starts).schedule(starts)
    objective, replay = old.tested_metrics(data)
    lanes = utilization(data)
    metrics = engine.measure(starts)
    for ch, row in lanes.items():
        span = row["longest_empty_interval"]
        expected = dict(idle=row["idle_s"], held=row["seconds_by_state"].get("腔内等待", 0),
                        longest=span[1]-span[0] if span else 0)
        if expected != metrics["chambers"][ch]:
            raise ValueError(f"Event replay and optimization disagree on CH{ch}")
    if objective["cmax"] != metrics["cmax"]:
        raise ValueError("Returned product makespan mismatch")
    return data, objective, replay, lanes


def ranking(values, recipe_metrics):
    return (values["idle"], values["cmax"], max(v["longest"] for v in values["chambers"].values()),
            recipe_metrics["secondary"], values["equipment_end"])


def reported_window(step, metrics):
    label, start, width, band, _ = step
    if label == "tail":
        return (max(0, metrics["cmax"]-start), metrics["equipment_end"]+1, band)
    if label in ("forward", "reverse", "head"):
        return (start, start+width, band)
    return FIXED


def run_steps(out, token, engine, blocks, seed, baseline, lower, pause_after):
    path = out/"checkpoint.json"
    if path.exists():
        state = old.restore(path, token)
    else:
        state = dict(starts=seed, records=[])
        old.checkpoint(path, token, state)
    ref = state["starts"]
    _, actual, _, _ = check_schedule(engine, blocks, ref)
    for index in range(len(state["records"]), len(STEPS)):
        wait_for_headroom()
        step = STEPS[index]
        label, seconds = step[0], step[-1]
        before = engine.measure(ref)
        window = reported_window(step, before)
        purpose = label if label in ("longest", "waiting") else "idle"
        candidate, row = engine.solve_idle(ref, baseline, lower, window, seconds, purpose,
                                           local=label in ("head", "tail", "forward", "reverse"))
        values = row["metrics"]
        if candidate != ref:
            _, candidate_metrics, _, _ = check_schedule(engine, blocks, candidate)
            accepted = ranking(values, candidate_metrics) < ranking(before, actual)
            if accepted:
                ref, actual = candidate, candidate_metrics
        else:
            accepted = False
        best = engine.measure(ref)
        row.update(step=label, accepted=accepted, incumbent=best)
        state["starts"] = ref
        state["records"].append(row)
        old.checkpoint(path, token, state)
        remaining = sum(s[-1] for s in STEPS[index+1:])
        prior.report(out, "secondary", completed=index+1, total=len(STEPS), failed=0,
                     budget_remaining_s=remaining, metrics=best)
        print(f"{index+1}/{len(STEPS)} {label} {row['status']} failed=0 | "
              f"CH2={best['chambers']['2']['idle']}s CH3={best['chambers']['3']['idle']}s "
              f"Cmax={best['cmax']}s | search budget remaining {remaining}s", flush=True)
        if pause_after == index+1:
            raise KeyboardInterrupt
    return state


def verify(out):
    summary = old.read(out/"summary.json")
    token = old.fingerprint(protocol())
    if token != summary["protocol_sha256"] or token != old.fingerprint(old.read(out/"campaign.json")):
        raise ValueError("Campaign fingerprint mismatch")
    for name, digest in summary["artifact_sha256"].items():
        if old.digest(out/name) != digest:
            raise ValueError(f"Changed output: {name}")
    cfg, blocks, seed = restore_seed()
    engine = ChamberIdle(cfg, blocks)
    state = old.restore(out/"checkpoint.json", token)
    data, metrics, replay, lanes = check_schedule(engine, blocks, state["starts"])
    certificate = old.read(out/"original_row_audit/certificate.json")
    if (data != old.read(out/"result.json") or metrics != summary["recipe_metrics"]
            or replay != summary["replay"] or old.fingerprint(lanes) != old.fingerprint(summary["utilization"])
            or engine.measure(seed) != summary["baseline"] or engine.measure(state["starts"]) != summary["new"]
            or certificate["result_sha256"] != old.digest(out/"result.json")
            or certificate["status"] != "all_original_rows_satisfied"):
        raise ValueError("Final evidence does not match replay")
    print(f"Verified schedule, idle objective, {certificate['original_rows']:,} original rows, both versions' files.", flush=True)


def execute(out, pause_after):
    with old.output_lock(out):
        spec = protocol()
        token = old.fingerprint(spec)
        manifest = out/"campaign.json"
        if manifest.exists():
            if old.fingerprint(old.read(manifest)) != token:
                raise ValueError("Campaign fingerprint mismatch. Choose a new output directory.")
        elif any(p.name not in (".run.lock", "campaign.json.tmp") for p in out.iterdir()):
            raise ValueError("Existing output is not an idle campaign")
        else:
            old.dump(manifest, spec)
        if (out/"summary.json").exists():
            verify(out)
            return
        attempt = dict(started_utc=old.stamp(), pid=os.getpid(), parallel_experiments=peers())
        ledger = out/f"attempt_{time.time_ns()}.json"
        old.dump(ledger, attempt)
        try:
            wait_for_headroom()
            cfg, blocks, seed = restore_seed()
            engine = ChamberIdle(cfg, blocks)
            baseline = engine.measure(seed)
            _, base_objective, _, _ = check_schedule(engine, blocks, seed)
            lower = old.read(BASE/"summary.json")["global_workload_lower_bound"]["seconds"]
            print(f"75 wafers | prior Cmax={baseline['cmax']}s idle={baseline['idle']}s | "
                  f"B gap={100*GAP:g}% | 1 thread / 1024 MiB | {len(STEPS)} steps", flush=True)
            state = run_steps(out, token, engine, blocks, seed, baseline, lower, pause_after)
            search_resources = sample()
            ends = engine.measure(state["starts"])
            data, metrics, replay, lanes = check_schedule(engine, blocks, state["starts"])
            old.dump(out/"result.json", data)
            wait_for_headroom()
            prior.report(out, "original_model_audit", metrics=ends)
            print("Checking all original D model rows, then rendering the resource lanes.", flush=True)
            cert = prior.audit_result(out, token, data)
            prior.report(out, "figures", metrics=ends)
            from figures import draw
            figures = draw(data, lanes, out/"figures")
            proof = next(r for r in state["records"] if r["step"] == "certify")
            # Tiebreaks keep the discrete order of the certified candidate.
            bound = proof["conditional_lower_bound"]
            local_gap = (ends["idle"]-bound)/max(1, abs(ends["idle"]))
            if local_gap < -1e-9:
                raise ValueError("Secondary incumbent contradicts its fixed-order bound")
            frozen = ["campaign.json", "checkpoint.json", "result.json", "original_row_audit/certificate.json",
                      "original_row_audit/assignment.json.gz"] + ["figures/"+n for n in figures["files"]]
            if old.fingerprint(protocol()) != token:
                raise ValueError("Source or previous version changed during the run")
            summary = dict(state="completed", protocol_sha256=token, objective=spec["stage_B"],
                           stage_B_relative_gap=GAP, baseline=baseline, new=ends, recipe_metrics=metrics,
                           baseline_recipe_metrics=base_objective, utilization=lanes, replay=replay,
                           fixed_order_report=dict(integer_seconds=True, lower_bound=bound,
                                                   upper_bound=ends["idle"], relative_gap=local_gap,
                                                   target_met=local_gap <= GAP+1e-12, status=proof["status"]),
                           unrestricted_idle_lower_bound=2*(cfg.handling+cfg.vtr_travel),
                           unrestricted_secondary_gap_certified=False, global_primary_lower_bound=lower,
                           global_primary_optimum_certified=False, full_model_rows_checked=cert["original_rows"],
                           search_status_counts=dict(Counter(r["status"] for r in state["records"])),
                           figures=figures, search_resources=search_resources, resources=sample(),
                           artifact_sha256={n:old.digest(out/n) for n in frozen}, ended_utc=old.stamp())
            old.dump(out/"summary.json", summary)
            prior.report(out, "completed", completed=1, failed=0, metrics=ends)
            attempt["outcome"] = "completed"
            print(f"Completed=1/1 failed=0 ETA=0 | {ends}", flush=True)
        except KeyboardInterrupt:
            attempt["outcome"] = "paused"
            prior.report(out, "paused")
            print("Paused. Resume continues from the most recent finished step.", flush=True)
        except Exception as exc:
            attempt["outcome"] = "failed"
            prior.report(out, "failed", error=repr(exc))
            raise
        finally:
            attempt.update(ended_utc=old.stamp(), resources=sample())
            old.dump(ledger, attempt)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("run", "resume", "verify", "status"))
    parser.add_argument("--out", type=Path, default=OUT)
    parser.add_argument("--pause-after", type=int)
    args = parser.parse_args()
    out = args.out.resolve()
    if args.action == "status":
        import json
        print(json.dumps(old.read(out/"progress.json") if (out/"progress.json").exists() else {"stage":"new"}, indent=2))
    elif args.action == "verify":
        verify(out)
    else:
        if out.parent != old.JMS/"results" or out in (BASE, old.DEFAULT):
            parser.error("Select a separate case directory directly under JMS-version/results")
        handle = limit_process()
        execute(out, args.pause_after)


if __name__ == "__main__":
    main()

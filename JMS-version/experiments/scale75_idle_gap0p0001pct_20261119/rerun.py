"""Matched rerun of the two frozen 75-wafer idle searches at a tighter stage-B gap."""
import argparse
from collections import Counter
from contextlib import ExitStack, contextmanager
import json
from pathlib import Path
import sys
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
PREVIOUS = HERE.parent / "scale75_idle_20261119"
sys.path[:0] = [str(PREVIOUS/"refine"), str(PREVIOUS)]
import extend
import check_bound
import figures
import idle

first = extend.first
old = extend.old
ORIGINAL_FIRST = first.OUT
ORIGINAL_FINAL = extend.OUT
DEFAULT = old.JMS / "results/scale75_idle_gap0p0001pct_D_20261119"
TARGET_GAP = 0.000001


@contextmanager
def run_settings(out):
    # The archived modules read these settings from module scope. Override them
    # only in this worker so their source and both original campaigns remain verifiable.
    with ExitStack() as settings:
        for module in (first, extend, idle, figures):
            settings.enter_context(patch.object(module, "GAP", TARGET_GAP))
        settings.enter_context(patch.object(first, "OUT", out/"first"))
        settings.enter_context(patch.object(extend, "OUT", out/"final"))
        yield


def validate_certificate(case, target):
    cert = old.read(case/"continuous_timing_certificate.json")
    summary = old.read(case/"summary.json")
    if (cert["protocol_sha256"] != summary["protocol_sha256"]
            or cert["code_sha256"] != old.digest(Path(check_bound.__file__))
            or cert["result_sha256"] != old.digest(case/"result.json")
            or cert["solver_gap_limit"] != target
            or cert["feasible_plotted_idle"] != summary["new"]["idle"]
            or cert["lower_bound"] > cert["feasible_plotted_idle"]+1e-7):
        raise ValueError(f"Continuous certificate mismatch: {case}")
    return cert


def manifest():
    previous_protocol = extend.protocol()
    snapshots = {}
    for case in (first.BASE, ORIGINAL_FIRST, ORIGINAL_FINAL):
        summary = old.read(case/"summary.json")
        for name, digest in summary["artifact_sha256"].items():
            if old.digest(case/name) != digest:
                raise ValueError(f"Changed prior artifact: {case/name}")
        snapshots[case.name] = old.digest(case/"summary.json")
    archived = old.read(ORIGINAL_FINAL/"summary.json")
    if (old.fingerprint(previous_protocol) != archived["protocol_sha256"]
            or old.fingerprint(old.read(ORIGINAL_FINAL/"campaign.json")) != archived["protocol_sha256"]):
        raise ValueError("Reference final protocol mismatch")
    validate_certificate(ORIGINAL_FINAL, first.GAP)
    return dict(secondary_relative_gap=TARGET_GAP, reference_secondary_relative_gap=first.GAP,
                primary_proposal_relative_gap=previous_protocol["upstream_protocol"]["first_stage_window_gap"],
                source_case=first.BASE.name, reference_case=ORIGINAL_FINAL.name,
                reference_summary_sha256=snapshots,
                reference_certificate_sha256=old.digest(ORIGINAL_FINAL/"continuous_timing_certificate.json"),
                first_steps=len(first.STEPS), final_steps=len(extend.steps()),
                primary_cap=previous_protocol["upstream_protocol"]["primary_cap"],
                source_sha256={p.name:old.digest(p) for p in (Path(__file__), HERE/"control.ps1")})


def steps_with_results(case, final):
    summary = old.read(case/"summary.json")
    records = old.restore(case/"checkpoint.json", summary["protocol_sha256"])["records"]
    return [(r["step"], r["solve"] if final else r, r["incumbent"]) for r in records]


def compare(out, spec):
    before = old.read(ORIGINAL_FINAL/"summary.json")
    after = old.read(out/"final/summary.json")
    cert = validate_certificate(out/"final", TARGET_GAP)
    if before["baseline"] != after["baseline"] or before["objective"] != after["objective"]:
        raise ValueError("Warm-start metrics or objective changed")
    if old.fingerprint(old.read(out/"first/campaign.json")) != old.fingerprint(
            {**old.read(ORIGINAL_FIRST/"campaign.json"), "stage_B_relative_gap": TARGET_GAP}):
        raise ValueError("First-pass settings differ beyond the requested gap")
    previous_final = old.read(ORIGINAL_FINAL/"campaign.json")
    tight_final = old.read(out/"final/campaign.json")
    if tight_final["steps"] != previous_final["steps"] or tight_final["source_sha256"] != previous_final["source_sha256"]:
        raise ValueError("Final order search or budget changed")
    reports, first_difference = [], None
    for previous, new, label in ((ORIGINAL_FIRST, out/"first", "first"), (ORIGINAL_FINAL, out/"final", "final")):
        is_final = label == "final"
        a = steps_with_results(previous, is_final)
        b = steps_with_results(new, is_final)
        if [r[0] for r in a] != [r[0] for r in b] or len(b) != spec[label+"_steps"]:
            raise ValueError("Incomplete or mismatched search")
        direct_counts = Counter()
        previous_counts = Counter()
        proposals = 0
        for index, ((step, prev, prev_best), (_, current, best)) in enumerate(zip(a,b), 1):
            if step != "proposal":
                if (prev["relative_gap_limit"] != spec["reference_secondary_relative_gap"]
                        or current["relative_gap_limit"] != TARGET_GAP):
                    raise ValueError("A direct stage-B solve received the wrong gap")
                direct_counts[current["status"]] += 1
                previous_counts[prev["status"]] += 1
            else:
                proposals += 1
            if first_difference is None and prev_best != best:
                first_difference = dict(pass_name=label, index=index, step=step, previous_status=prev["status"],
                                        new_status=current["status"], previous=prev_best, new=best)
        reports.append(dict(pass_name=label, steps=len(b), proposal_steps=proposals,
                            previous_direct_status=dict(previous_counts), new_direct_status=dict(direct_counts)))
    data_old, data_new = (old.read(case/"result.json") for case in (ORIGINAL_FINAL, out/"final"))
    unchanged = all(data_old[k] == data_new[k] for k in ("config", "events", "cycles", "pairs", "jobs", "cmax"))
    return dict(state="completed", run_manifest_sha256=old.fingerprint(spec),
                requested_solver_gap=TARGET_GAP, previous_solver_gap=spec["reference_secondary_relative_gap"],
                reference=before["new"], matched_rerun=after["new"],
                reference_recipe_metrics=before["recipe_metrics"], matched_recipe_metrics=after["recipe_metrics"],
                same_timed_schedule=unchanged, search=reports, first_different_incumbent=first_difference,
                continuous_fixed_order_bounds=[cert["lower_bound"], cert["feasible_plotted_idle"]],
                continuous_fixed_order_relative_gap=cert["plotted_relative_gap"],
                unrestricted_secondary_gap_certified=after["unrestricted_secondary_gap_certified"],
                replay_checks=after["replay"]["checks"], original_rows=after["full_model_rows_checked"],
                phase_peak_rss_mib={name:old.read(out/name/"summary.json")["resources"]["peak_rss_mib"]
                                    for name in ("first", "final")},
                plot=after["figures"], sha256={rel:old.digest(out/rel) for rel in
                    ("first/summary.json","final/summary.json","final/continuous_timing_certificate.json")})


def execute(out, phase, pause_after):
    spec = manifest()
    file = out/"run_manifest.json"
    if file.exists():
        if old.read(file) != spec:
            raise ValueError("Stored inputs or runner differ from this campaign")
    elif phase == "verify":
        raise ValueError("No campaign to verify")
    elif any(p.name not in (".run.lock", "run_manifest.json.tmp") for p in out.iterdir()):
        raise ValueError("Choose a new output directory")
    else:
        old.dump(file, spec)
    with run_settings(out):
        if phase == "first":
            first.execute(first.OUT, pause_after)
            return (first.OUT/"summary.json").is_file()
        if phase == "final":
            extend.run(extend.OUT, pause_after)
            return (extend.OUT/"summary.json").is_file()
        if phase == "verify":
            first.verify(first.OUT)
            extend.verify(extend.OUT)
        elif not (extend.OUT/"continuous_timing_certificate.json").exists():
            check_bound.certify(extend.OUT)
        result = compare(out, spec)
    if manifest() != spec:
        raise ValueError("Reference artifacts changed")
    target = out/"comparison.json"
    if target.exists() or phase == "verify":
        if result != old.read(target):
            raise ValueError("Stored comparison differs from independent verification")
    else:
        old.dump(target, result)
    print(f"Completed 1/1 failed=0 ETA=0 | gap {100*TARGET_GAP:g}% | "
          f"idle {result['reference']['idle']} -> {result['matched_rerun']['idle']} chamber-seconds", flush=True)
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("first", "final", "certify", "verify", "status"))
    parser.add_argument("--out", type=Path, default=DEFAULT)
    parser.add_argument("--pause-after", type=int)
    args = parser.parse_args()
    out = args.out.resolve()
    if out.parent != old.JMS/"results" or out in (old.DEFAULT, first.BASE, ORIGINAL_FIRST, ORIGINAL_FINAL):
        parser.error("Use a separate case directory under JMS-version/results")
    if args.phase == "status":
        report = {}
        for phase in ("first","final"):
            progress = out/phase/"progress.json"
            report[phase] = old.read(progress) if progress.exists() else {"stage":"pending"}
        report["comparison_complete"] = (out/"comparison.json").is_file()
        print(json.dumps(report, indent=2))
        return
    handle = first.limit_process()
    if args.phase == "verify":
        execute(out,args.phase,None)
    else:
        with old.output_lock(out):
            if not execute(out,args.phase,args.pause_after):
                raise SystemExit(20)


if __name__ == "__main__":
    main()

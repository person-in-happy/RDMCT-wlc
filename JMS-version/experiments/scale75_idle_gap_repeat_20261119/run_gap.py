"""Repeat the frozen 75-wafer stage-B experiment with a user-specified percentage."""
import argparse
from decimal import Decimal, DecimalException
import json
import math
from pathlib import Path
import sys
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent/"scale75_idle_gap0p0001pct_20261119"))
import rerun

REFERENCE = rerun.DEFAULT
REFERENCE_GAP = rerun.TARGET_GAP
old_manifest = rerun.manifest
old_compare = rerun.compare
old = rerun.old


def percentage(raw):
    try:
        value = Decimal(raw)
        if not value.is_finite() or value < 0:
            raise ValueError
        ratio = float(value.scaleb(-2))
        if not math.isfinite(ratio) or (value and not ratio):
            raise ValueError
        return value
    except (DecimalException, OverflowError, ValueError):
        raise argparse.ArgumentTypeError("Enter a finite nonnegative percentage representable by the solver.")


def manifest(percent, ratio):
    # Reproduce the reference comparison with its own settings before binding its hashes.
    with patch.object(rerun, "TARGET_GAP", REFERENCE_GAP):
        archived = old_manifest()
        if archived != old.read(REFERENCE/"run_manifest.json"):
            raise ValueError("Previous run manifest does not match its inputs")
        with rerun.run_settings(REFERENCE):
            if old_compare(REFERENCE, archived) != old.read(REFERENCE/"comparison.json"):
                raise ValueError("Previous comparison no longer verifies")
    snapshots = dict(archived["reference_summary_sha256"])
    for phase in ("first", "final"):
        base = REFERENCE/phase
        summary = old.read(base/"summary.json")
        for name, digest in summary["artifact_sha256"].items():
            if old.digest(base/name) != digest:
                raise ValueError(f"Changed reference artifact: {base/name}")
        snapshots[f"{REFERENCE.name}/{phase}"] = old.digest(base/"summary.json")
    return dict(archived, secondary_relative_gap=ratio, requested_gap_percent=format(percent, "f"),
                reference_secondary_relative_gap=REFERENCE_GAP, reference_case=REFERENCE.name,
                reference_summary_sha256=snapshots,
                reference_certificate_sha256=old.digest(REFERENCE/"final/continuous_timing_certificate.json"),
                reference_manifest_sha256=old.digest(REFERENCE/"run_manifest.json"),
                reference_comparison_sha256=old.digest(REFERENCE/"comparison.json"),
                source_sha256={p.name:old.digest(p) for p in (Path(__file__), HERE/"control.ps1")})


def compare(out, spec):
    with patch.multiple(rerun, ORIGINAL_FIRST=REFERENCE/"first", ORIGINAL_FINAL=REFERENCE/"final"):
        result = old_compare(out, spec)
    lower, upper = (Decimal(str(x)) for x in result["continuous_fixed_order_bounds"])
    if lower > upper:
        raise ValueError("Fixed-order lower bound exceeds the verified feasible objective")
    gap = None
    if upper == lower:
        gap = Decimal(0)
    elif lower > 0:
        gap = (upper-lower)/lower
    # At this scale the additive tolerance in the older display flag can exceed
    # the requested gap. Compare the recorded bounds directly, without that slack.
    result["strict_fixed_order_relative_gap"] = float(gap) if gap is not None else None
    result["strict_fixed_order_target_met"] = gap is not None and gap <= Decimal(spec["requested_gap_percent"])/100
    result["schedule_sha256"] = {label:old.digest(case/"result.json") for label,case in
                                 (("previous", REFERENCE/"final"), ("rerun", out/"final"))}
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("first","final","certify","verify","status"))
    parser.add_argument("--gap-percent", type=percentage, default="0.000000001")
    parser.add_argument("--out", type=Path)
    parser.add_argument("--pause-after", type=int)
    args = parser.parse_args()
    percent = args.gap_percent.normalize()
    ratio = float(percent.scaleb(-2))
    suffix = format(percent, "f").replace(".", "p")
    if len(suffix) > 24:
        suffix = format(percent, "e").replace(".", "p")
    out = (args.out or old.JMS/"results"/f"scale75_idle_gap{suffix}pct_D_20261119").resolve()
    frozen = (old.DEFAULT, rerun.first.BASE, rerun.ORIGINAL_FIRST, rerun.ORIGINAL_FINAL, REFERENCE)
    if out.parent != old.JMS/"results" or out in frozen:
        parser.error("Choose a separate case directory under JMS-version/results.")
    if args.phase == "status":
        status = {}
        for phase in ("first", "final"):
            progress = out/phase/"progress.json"
            status[phase] = old.read(progress) if progress.exists() else {"stage":"pending"}
        status["comparison_complete"] = (out/"comparison.json").is_file()
        print(json.dumps(status, indent=2))
        return
    handle = rerun.first.limit_process()
    with patch.multiple(rerun, TARGET_GAP=ratio, manifest=lambda: manifest(percent,ratio), compare=compare):
        if args.phase == "verify":
            rerun.execute(out,"verify",None)
        else:
            with old.output_lock(out):
                if not rerun.execute(out,args.phase,args.pause_after):
                    raise SystemExit(20)


if __name__ == "__main__":
    main()

"""A global lower bound on continuous product-return makespan for the D75 instance.

Each cleaning-free run has at most H=3 productive exposures. A full exposure
serves at most four 4x1 products. A 2x2 product pair has two successive exposures.
In a run containing k such pairs, at most one pair starts per exposure, and no
new pair starts in its last 2x2 exposure. At least k+1 mixed exposures and
exactly k retained-pair boundaries are therefore necessary. Extra exposures
can only increase the load. Each intermediate cleaning requires one exposure
and a complete exchange on both sides; a terminal clean is excluded.

At a retained boundary the rotation, one outgoing pair and one incoming pair
are sequential. At a complete exchange both old pairs leave before either new
pair loads. The front unload, rotation and back unload cost at least 2h+r.
When the back pair is picked, its two wafers use two of the four VTR hands.
Consequently at least one of the four NEW wafers has yet to be picked outside
the chamber. Following the back unload the robot must travel out and back,
make at least one external pickup and perform both new pair loads. These three
VTR actions cannot overlap. The two new loads also straddle a rotation.
The lower bound on a complete exchange is (2h+r)+max(2h+r,3h+2t).
Rotation time is not added to simultaneous travel. This argument also applies
when the old or new pairs contain dummy wafers. External buffer contention,
shared-robot conflicts between chambers and supply restrictions are relaxed.
"""
from functools import lru_cache
from math import ceil
from pathlib import Path
import sys

from continue_primary import DEST, SOURCE, first, old, primary
from incumbent_sublevel import product_route_margins

OUT = old.JMS / "results" / "scale75_chamber_bound_D_20261120"
OTHER = old.JMS / "results" / "scale75_idle_gap0p000000001pct_D_20261119" / "final"


def compute(cfg):
    if cfg.cleaning_interval != 3 or len(cfg.chambers) != 2:
        raise ValueError("The independent count enumeration is specialized to H=3 and two chambers")
    lead, tail = product_route_margins(cfg)
    h, r, t = cfg.handling, cfg.rotation, cfg.vtr_travel
    retained = r + 2*h
    fresh = 2*h + r + max(2*h+r, 3*h+2*t)
    wash = cfg.cleaning_time
    durations = cfg.full_time, cfg.mix_time
    total_f, total_m = (sum(p[mode] for p in cfg.load_ports.values()) for mode in ("4x1", "2x2"))

    def block_cost(f, k):
        n_mix = k + 1 if k else 0
        return f*durations[0] + n_mix*durations[1] + k*retained + (f+n_mix-1-k)*fresh

    # All nonempty productive blocks before an optional clean. f is the
    # count of full exposures, k the count of double-exposure product pairs.
    blocks = [(f,k,block_cost(f,k)) for f in range(4) for k in range(3)
              if 1 <= f + k + int(k>0) <= 3]

    @lru_cache(None)
    def dp(f, p):
        if f+p == 0:
            return 0
        costs = []
        for use_f, use_p, duration in blocks:
            rest = max(0,f-use_f), max(0,p-use_p)
            if rest == (f,p):
                continue
            costs.append(duration + (wash+2*fresh+dp(*rest) if any(rest) else 0))
        return min(costs)

    @lru_cache(None)
    def count(f, p):
        # Independent enumeration using only the number of clean-separated
        # runs and the number of runs containing mixed processing.
        if f+p == 0:
            return 0
        costs = []
        for runs in range(1, f+p+1):
            for mixed_runs in range(runs+1):
                pairs = max(p, mixed_runs)
                full = max(f, runs-mixed_runs)
                mixed = pairs+mixed_runs
                if pairs > 2*mixed_runs or full+mixed > 3*runs:
                    continue
                clean = runs-1
                fresh_boundaries = full+mixed+clean-1-pairs
                costs.append(full*durations[0]+mixed*durations[1]+clean*wash
                             +fresh_boundaries*fresh+pairs*retained)
        return min(costs)

    def lane(a,b):
        if a+b == 0:
            return 0
        f,p = ceil(a/4), ceil(b/2)
        duration = dp(f,p)
        if count(f,p) != duration:
            raise ValueError(f"Independent chamber workload enumerations disagree at {(f,p)}")
        return lead+duration+tail

    splits = []
    for a in range(total_f+1):
        for b in range(total_m+1):
            loads = [lane(a,b), lane(total_f-a,total_m-b)]
            splits.append(dict(split=[[a,b],[total_f-a,total_m-b]], lower=max(loads), chamber_loads=loads))
    lower = min(s["lower"] for s in splits)
    return dict(lower_s=lower, historical_lower_s=primary.workload_bound(cfg)["seconds"],
                lead_s=lead, tail_s=tail, complete_exchange_s=fresh, retained_exchange_s=retained,
                splits_checked=len(splits), matching_enumerations=True,
                minimizing_splits=[s for s in splits if s["lower"]==lower],
                processing_blocks=[dict(full=f,mixed_pairs=k,seconds=dt) for f,k,dt in blocks])


def check_witness(path, cfg_data, bound):
    data = old.read(path / "result.json")
    sha = old.digest(path / "result.json")
    cert = old.read(path / "original_row_audit/certificate.json")
    if data["config"] != cfg_data or cert["result_sha256"] != sha or cert["status"] != "all_original_rows_satisfied":
        raise ValueError(f"Incompatible configuration or certificate in {path}")
    stats, replay = old.tested_metrics(data)
    actual_gaps = {"complete":[], "retained":[]}
    for ch in cfg_data["chambers"]:
        seq = sorted((c for c in data["cycles"] if c["chamber"]==ch), key=lambda c:c["start"])
        if not seq:
            continue
        productive = [c for c in seq if c["mode"] != "clean"]
        if productive[0]["start"] < bound["lead_s"] or data["cmax"]-productive[-1]["end"] < bound["tail_s"]:
            raise ValueError("Invalid route margin")
        for old_cycle,new_cycle in zip(seq,seq[1:]):
            retained = bool(set(old_cycle["pairs"]) & set(new_cycle["pairs"]))
            gap = new_cycle["start"]-old_cycle["end"]
            kind = "retained" if retained else "complete"
            if gap < bound[kind+"_exchange_s"]:
                raise ValueError(f"Invalid exchange bound: CH{ch} at {old_cycle['end']}")
            actual_gaps[kind].append(gap)
    if data["cmax"] < bound["lower_s"]:
        raise ValueError("Chamber bound exceeds a replayed feasible makespan")
    return dict(case=path.relative_to(old.JMS / "results").as_posix(), result_sha256=sha,
                cmax_s=stats["cmax"], paper_f_B=stats["secondary"], replay_checks=replay["checks"],
                original_rows=cert["original_rows"], relative_gap_upper=(stats["cmax"]-bound["lower_s"])/bound["lower_s"],
                minimum_observed_exchange_s={k:min(v,default=None) for k,v in actual_gaps.items()})


def main():
    cfg_data = old.read(SOURCE / "final/result.json")["config"]
    bound = compute(old.Config(**cfg_data))
    cases = [SOURCE / "primary", SOURCE / "final", OTHER, DEST]
    witnesses = [check_witness(p, cfg_data, bound) for p in cases]
    best = min(w["cmax_s"] for w in witnesses)
    backend = old.BACKEND
    files = [Path(__file__), Path(primary.workload_bound.__code__.co_filename), Path(product_route_margins.__code__.co_filename),
             backend/"model.py", backend/"joint_chamber_cycle_model.py", backend/"joint_pairing_model.py"]
    record = dict(scope="unrestricted continuous-time primary objective, 37 full and 38 mixed products, H=3",
                  derivation=__doc__, config_sha256=old.fingerprint(cfg_data),
                  source_sha256={p.relative_to(old.JMS.parent).as_posix():old.digest(p) for p in files},
                  **bound, verified_witnesses=witnesses, best_verified_upper_s=best,
                  absolute_gap_upper_s=best-bound["lower_s"], relative_gap_upper=(best-bound["lower_s"])/bound["lower_s"])
    with old.output_lock(OUT):
        dest = OUT/"certificate.json"
        if dest.exists():
            if old.read(dest) != record:
                raise ValueError("Certificate changed")
        elif "--verify" in sys.argv:
            raise ValueError("No saved certificate")
        else:
            old.dump(dest,record)
    print(f"Independently enumerated {bound['splits_checked']} splits. Bound [{bound['lower_s']}, {best}], "
          f"gap <= {record['relative_gap_upper']:.6%}. Checked {len(witnesses)} witnesses.", flush=True)


if __name__ == "__main__":
    limit_handle = first.limit_process()
    first.wait_for_headroom()
    main()

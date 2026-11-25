"""Evaluate changes in residence and cleaning preferences on the certified continuous family."""
from fractions import Fraction as F
import hashlib
import json
from pathlib import Path

RESULTS = Path(__file__).resolve().parents[2] / "results"
OUT = RESULTS / "huber_residence_20261125"
certificate = OUT / "frontier/certificate.json"
anchors = RESULTS / "residence_objective_20261125/best_reuse/continuous_frontier/certificate.json"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def penalty(d, delta):
    return d*d/(2*delta) if d <= delta else d-delta/2


def main():
    proof = json.loads(certificate.read_text(encoding="utf8"))
    lower = json.loads(anchors.read_text(encoding="utf8"))
    assert digest(anchors) in proof["anchors"].values()
    for native in lower["native_replays"].values():
        start, end = [r["metrics"] for r in native["endpoints"]]
        assert [(r["mean_residence"],r["residence_range"],r["clean_deficit"]) for r in (start,end)] == [
                (3.25,1,0), (3.5,0,0)]
        assert native["exact_native_linear_rows"] == 281012 and max(native["max_archive_rounding"]) < 1e-10
        assert (start["cmax"],end["cmax"]) == (553,554)
    rows = []
    for delta in map(F,["1/2","1","2"]):
        # rho' = 1/4 exactly compensates the growing average residence.
        t = 1-delta/4
        d = 1-t
        mean = F(13,4)+t/4
        value = mean+penalty(d,delta)
        # On H=3 the unconstrained linear support mean+D/4 >= 3.5 is global.
        assert value == F(7,2)-delta/32
        rows.append(dict(delta_s=float(delta),t_at_min_s=float(t),makespan_s=float(553+t),
                         mean_s=float(mean),spread_s=float(d),penalty_s=float(penalty(d,delta)),
                         E=0,minimum_H3_s=float(value)))
    data=dict(certificate_sha256=digest(certificate),native_affine_family_sha256=digest(anchors),
              delta_sensitivity=rows,
              integer_second_alternative=dict(both_H=[[553,3.75],[554,3.5]],
                        lower_if_D_is_zero=3.5,lower_if_D_is_integer_and_positive=float(F(25,8)+F(1,2)),
                        proof="Both integer-attained endpoints, the conditional bound at 553, the integer makespan, and global lower bounds by spread class."),
              cleaning="For every nonnegative gamma the witnesses have E=0 and their cross-structure lower bounds use only residence. Short branch survives, as do both global B minima.",
              multiplicative="For nonnegative R, R*(1+k*E) is at least R for k>=0 and equals R at E=0. In contrast R*E=0 at the minimum feasible makespan for both H values.")
    (OUT/"frontier/preference_sensitivity.json").write_text(json.dumps(data,indent=2),encoding="utf8")


if __name__ == "__main__":
    main()

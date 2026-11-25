"""Check sensitivity evidence identities and all displayed representative values."""
from fractions import Fraction as F
from pathlib import Path
import sys
here=Path(__file__).resolve().parent
sys.path.insert(0,str(here.parent))
from solver import HERE,read,save,sha
from score import metrics

root=HERE.parents[1]/"results/residence_objective_20261125"
cert_dir=root/"best_reuse/continuous_frontier"
out=root/"preference_review"
ref=read(cert_dir/"certificate.json")
for k,d in ref["proof_records"].items():assert sha(cert_dir/k)==d
assert sha(HERE/"frontier_audit.py")==ref["code_sha256"]
assert F(3,1000)<F(1,8*27) and F(5,1000)<F(1,4*27)
projected=out/"beta2_scale_1000/result.json";beta2=read(projected)
assert beta2["status"]=="INFEASIBLE" and beta2["scale"]==1000 and beta2["cut"]==41999
for file,d in beta2["code"].items():
    path=here/file if (here/file).exists() else HERE/file
    assert sha(path)==d
wants={1:(4.25,3.875,3.5),.5:(3.75,3.625,3.5),2:(5.25,4.375,3.5),0:(3.25,3.375,3.5),.25:(3.5,3.5,3.5)}
lines={}
for h in (3,10):
    tag=root/f"best_reuse/n8_H{h}"
    docs=[read(tag/k/"schedule.json") for k in ("retained_product_times","midpoint","ideal_fixed")]
    for f in ("schedule.json","assignment.json.gz"):
        for src,entry in zip(("retained_product_times","ideal_fixed"),ref["native_replays"][str(h)]["endpoints"]):
            assert sha(tag/src/f)==entry["schedule_sha256" if f=="schedule.json" else "assignment_sha256"]
    for b,requested in wants.items():
        observed=[metrics(d,range_weight=b,clean_weight=1)["secondary"] for d in docs]
        assert all(abs(x-y)<1.e-7 for x,y in zip(observed,requested))
        lines[str(b)]=observed
p=out/"n8_H10_low_beta_retimed";small=read(p/"primary.json")
for f,k in (("schedule.json","schedule_sha256"),("assignment.json.gz","assignment_sha256")):assert sha(p/f)==small[k]
d=read(p/"schedule.json")
assert d["config"]==docs[0]["config"]
assert small["rows"]==281012 and small["replay"]["valid"]
new={str(b):metrics(d,range_weight=b)["secondary"] for b in (0,.25,.5,1,2)}
assert new["0"]==3.125 and new["0.25"]==3.375
save(out/"audit.json",dict(coefficients_gamma="all nonnegative coefficients on closed-clean deficits",
    native_interpolated_family=lines,endpoint_order=["553 seconds","553.5 seconds","554 seconds"],
    complete_frontier_beta=[.5,1,2],short_window_conditionally_optimal_beta025=3.5,
    short_window_conditionally_optimal_beta0=3.25,old_continuous_certificate_sha256=sha(cert_dir/"certificate.json"),
    beta2_grid_certificate_sha256=sha(projected),new_H10_low_mean_witness_sha256=sha(p/"primary.json"),
    long_witness=dict(C=small["metrics"]["cmax"],score_by_beta=new),
    code_sha256=sha(Path(__file__))))

"""Prove the maximum productive exposure at cap 554, independently of the secondary score."""
import hashlib
import itertools
import json
from pathlib import Path
from tight_primary import tightened,cp_model

here=Path(__file__).resolve().parent
root=here.parents[1]/"results/residence_objective_20261125/best_reuse"
source=root/"n8_H10/ideal_fixed/schedule.json"
d=json.loads(source.read_bytes())
m=tightened(d,554)
v={v.name:m.get_int_var_from_proto_index(i) for i,v in enumerate(m.proto.variables)}
w=sorted((j for j in d["jobs"] if j["product"]),key=lambda x:(x["pjob"],x["pjob_index"]))
mode={p["id"]:p["mode"] for p in d["pairs"]}
for c,q in itertools.product(range(2),range(4)):
    keys=(f"w{i}_{c}_{q}_{s}" for i,s in itertools.product(range(8),range(2)))
    active=[v[k] for k in keys if k in v]
    if q:
        active.extend(v[f"w{i}_{c}_{q-1}_1"] for i,j in enumerate(w) if mode[j["pair"]]=="2x2")
    m.add(sum(active)>=v[f"use{c,q}"])
m.add(sum(v[f"use{c,q}"]+v[f"full{c,q}"] for c,q in itertools.product(range(2),range(4)))>=8)
m.clear_objective()
s=cp_model.CpSolver(); s.parameters.num_workers=1
s.parameters.max_time_in_seconds=30
out=root/"continuous_frontier/eight_units_554";out.mkdir(exist_ok=True,parents=True)
s.parameters.log_search_progress=True;s.parameters.log_to_stdout=False
with (out/"cp.log").open("w",encoding="utf8",buffering=1) as log:
    s.log_callback=lambda t:log.write(t.rstrip()+"\n")
    stat=s.solve(m)
result=dict(status=s.status_name(stat),cap=554,minutes=s.wall_time/60,branches=s.num_branches,
            source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),code={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (Path(__file__),here/"primary_relaxation.py",here/"tight_primary.py")})
(out/"result.json").write_text(json.dumps(result,indent=2))
print(result,flush=True)

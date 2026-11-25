"""Outer decision for a beta=2 supporting line on 553 <= C <= 554, omitting E>=0."""
import argparse
import hashlib
import json
import sys
from itertools import product
from pathlib import Path

here=Path(__file__).resolve().parent
sys.path.insert(0,str(here.parent))
from frontier_projection import projected,cp_model


def main(scale,seconds):
    root=here.parents[2]/"results/residence_objective_20261125"
    src=root/"best_reuse/n8_H10/retained_product_times/schedule.json"
    doc=json.loads(src.read_bytes())
    out=root/"preference_review"/f"beta2_scale_{scale}"
    out.mkdir(exist_ok=True,parents=True)
    dependencies=[Path(__file__),*(here.parent/f for f in ("frontier_projection.py","ideal_projection.py","tight_primary.py","primary_relaxation.py"))]
    signature={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in dependencies}
    if (out/"result.json").exists():
        old=json.loads((out/"result.json").read_bytes())
        if old["code"]==signature and old["status"] in ("INFEASIBLE","OPTIMAL","FEASIBLE"):
            print(old["status"],"already checked");return
    m,oldcost=projected(doc,scale,False)
    v={w.name:m.get_int_var_from_proto_index(j) for j,w in enumerate(m.proto.variables)}
    C=v["makespan"]
    m.add(C>=553*scale)
    weighted=oldcost+8*v["spread"]+14*(C-553*scale)
    cut=42*scale-1
    m.add(weighted<=cut)
    # Every physical short-window schedule below this score has no back full wafer:
    # p_full+p_mixed <= 2(mean+D)<=10.5, while p_mixed>=7 and the back requires >=6.
    # With at most seven 90-second units these must be two full cycles and one
    # three-cycle mixed chain. Every product-bearing pair thus has exactly two wafers.
    m.add(v["spread"]<=scale)
    m.add_max_equality(m.new_int_var(7*scale,21*scale//2,"mixed_peak"),[v[f"resident_{i}"] for i in range(4,8)])
    for i in range(8):
        m.add(2*v[f"resident_{i}"]<=(7 if i<4 else 21)*scale)
    for c,q in product(range(2),range(4)):
        for i in range(4):
            m.add(v[f"w{i}_{c}_{q}_0"]==0)
        m.add(sum(v[f"w{i}_{c}_{q}_1"] for i in range(4))==2*v[f"full{c,q}"])
        if q<3:
            used=m.new_bool_var(f"two_product_mixed_{c}_{q}")
            m.add(sum(v[f"w{i}_{c}_{q}_1"] for i in range(4,8))==2*used)
    m.add(sum(v[f"full{c,q}"] for c,q in product(range(2),range(4)))==2)
    m.add(sum(v[f"use{c,q}"] for c,q in product(range(2),range(4)))==5)
    m.add(v["ch0"]==0)
    s=cp_model.CpSolver();s.parameters.num_workers=1;s.parameters.max_time_in_seconds=seconds
    s.parameters.log_search_progress=True;s.parameters.log_to_stdout=False
    print(f"beta=2, grid {scale}, single CPU, remaining budget {seconds}s",flush=True)
    with (out/"cp.log").open("w",encoding="utf8",buffering=1) as f:
        s.log_callback=lambda line:f.write(line.rstrip()+"\n")
        z=s.solve(m)
    payload=dict(status=s.status_name(z),scale=scale,seconds=s.wall_time,cut=cut,code=signature,
                 continuous_lower=5.25-5/scale if z==cp_model.INFEASIBLE else None)
    if z in (cp_model.FEASIBLE,cp_model.OPTIMAL):
        r=[s.value(v[f"resident_{i}"])/scale for i in range(8)]
        spread=max(max(r[:4])-min(r[:4]),max(r[4:])-min(r[4:]))
        payload.update(cmax=s.value(C)/scale,residences=r,spread=spread,fB=sum(r)/8+2*spread,
                       projected_only={k:s.value(x) for k,x in v.items() if k and (k[0].isdigit() or k.startswith(("start","use","full","w","ch_")))})
    tmp=out/"result.tmp";tmp.write_text(json.dumps(payload,indent=2));tmp.replace(out/"result.json")
    print({k:v for k,v in payload.items() if k not in ("projected_only","code")},flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--scale",type=int,default=1000);p.add_argument("--seconds",type=int,default=95)
    a=p.parse_args();main(a.scale,a.seconds)

"""Conditional eight-product certificate using exhaustive counts and an integer-time outer relaxation."""
import argparse
import hashlib
import json
import sys
from pathlib import Path
from itertools import product

HERE=Path(__file__).resolve().parent
OUT=HERE.parents[1]/"results/quota_objective_20261125/conditional_553"
BASE=HERE.parent/"residence_objective_20261125"
sys.path.insert(0,str(BASE))
from tight_primary import tightened, cp_model


def side(h):
    # All production lies within [76,513]. A 500 s clean cannot occur between products.
    # Discard optional final cleans, positive in the objective. Each chamber has <=4
    # ninety-second units. Each 4x1 cycle requires two units, each 2x2 cycle one.
    segments=[(w,0,1,2,6*max(0,w-2)) for w in range(1,5)]
    for pairs in range(1,4):
        for wafers in range(pairs,min(4,2*pairs)+1):
            segments.append((0,wafers,pairs+1,pairs+1,6*wafers+(1 if wafers<2*pairs else 2)))
    rows={}
    def extend(full,mixed,cycles,units,residence):
        key=full,mixed,cycles,units
        rows[key]=min(rows.get(key,float("inf")),residence)
        for f,b,k,u,r in segments:
            if full+f<=4 and mixed+b<=4 and cycles+k<=h and units+u<=4:
                extend(full+f,mixed+b,cycles+k,units+u,residence+r)
    extend(0,0,0,0,0)
    return rows


def lower(h,maxunits):
    rows=side(h)
    winner=float("inf")
    for (fa,ba,pa,ua),ra in rows.items():
        for (fb,bb,pb,ub),rb in rows.items():
            if fa+fb!=4 or ba+bb!=4 or ua+ub>maxunits: continue
            value=(ra+rb)/8+h*(2+int(pa==h)+int(pb==h))-pa-pb
            winner=min(winner,value)
    return winner


def main(seconds):
    import ortools
    OUT.mkdir(parents=True,exist_ok=True)
    results=HERE.parents[1]/"results"
    sources={h:results/f"residence_objective_20261125/best_reuse/n8_H{h}/retained_product_times/schedule.json" for h in (3,10)}
    data=json.loads(sources[10].read_bytes())
    modes={p["id"]:p["mode"] for p in data["pairs"]}
    wafers=sorted((w for w in data["jobs"] if w["product"]),key=lambda w:(w["pjob"],w["pjob_index"]))
    mixed=[i for i,w in enumerate(wafers) if modes[w["pair"]]=="2x2"]
    m=tightened(data,553)
    v={v.name:m.get_int_var_from_proto_index(i) for i,v in enumerate(m.proto.variables)}
    # Native productive cycles always include at least one product. In 2x2 mode the
    # carried pair entered the preceding (q-1) front, unlike full pairs in one cycle.
    for c in range(2):
        for q in range(4):
            names=(f"w{i}_{c}_{q}_{side}" for i,side in product(range(8),range(2)))
            present=[v[name] for name in names if name in v]
            if q:
                present.extend(v[f"w{i}_{c}_{q-1}_1"] for i in mixed)
            m.add(sum(present)>=v[f"use{c,q}"])
    m.clear_objective()
    m.add(sum(v[f"use{c,q}"]+v[f"full{c,q}"] for c in range(2) for q in range(4))>=8)
    solver=cp_model.CpSolver(); solver.parameters.num_workers=1
    solver.parameters.max_time_in_seconds=seconds
    solver.parameters.log_search_progress=True
    solver.parameters.log_to_stdout=False
    with (OUT/"cp.log").open("w",encoding="utf8",buffering=1) as log:
        solver.log_callback=lambda line:log.write(line.rstrip()+"\n")
        status=solver.solve(m)
    cap=7 if status==cp_model.INFEASIBLE else 8
    digest=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    sys.path.remove(str(BASE))
    from score import metrics
    upper={h:metrics(json.loads(p.read_bytes())) for h,p in sources.items()}
    assert all(abs(row["secondary"]-lower(h,cap))<1e-7 for h,row in upper.items()) if status==cp_model.INFEASIBLE else True
    payload=dict(admitted_upper=upper,cap=553,status=solver.status_name(status),tested_units=8,certified_max_units=cap,
                 conditioned_lower={h:lower(h,cap) for h in (3,10)},count_only_lower={h:lower(h,8) for h in (3,10)},
                 seconds=solver.wall_time,branches=solver.num_branches,ortools=ortools.__version__,
                 hashes={p.name:digest(p) for p in (Path(__file__),BASE/"tight_primary.py",BASE/"primary_relaxation.py")},
                 referenced_witnesses={h:{"schedule":str(p),"sha256":digest(p)} for h,p in sources.items()})
    (OUT/"result.json").write_text(json.dumps(payload,indent=2))
    print(payload,flush=True)


if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--seconds",type=int,default=90)
    main(p.parse_args().seconds)

"""Strengthen the independent product projection with pair identity and finite-chain boundaries."""
import argparse
import hashlib
import itertools
import json
from pathlib import Path

from primary_relaxation import DUR, STEPS, cp_model, model


def tightened(doc,cap,fix=False):
    m=model(doc,cap,fix)
    var={v.name:m.get_int_var_from_proto_index(i) for i,v in enumerate(m.proto.variables)}
    wafers=sorted((w for w in doc["jobs"] if w["product"]),key=lambda w:(w["pjob"],w["pjob_index"]))
    pair_mode={p["id"]:p["mode"] for p in doc["pairs"]}
    entries,positions=[],[]
    for i,w in enumerate(wafers):
        options={}
        for c,q,side in itertools.product(range(2),range(4),range(2)):
            key=f"w{i}_{c}_{q}_{side}"
            if key in var:
                options[c,q,side]=var[key]
                if pair_mode[w["pair"]]=="2x2":
                    f=q+1
                    unload=var[f"{i}_unload"]
                    finish=var[f"start{c,f}"]+90
                    if f==3:
                        m.add(unload>=finish+3).only_enforce_if(var[key])
                    else:
                        m.add(unload>=finish+3).only_enforce_if([var[key],var[f"use{c,f+1}"].Not()])
                        m.add(unload>=finish+3).only_enforce_if([var[key],var[f"full{c,f+1}"]])
        entries.append(options)
        pos=m.new_int_var(0,15,f"pair_slot_{i}")
        m.add(pos==sum((8*c+2*q+side)*v for (c,q,side),v in options.items()))
        positions.append(pos)
    for c,q in itertools.product(range(2),range(1,4)):
        for index in (q-1,q):
            m.add(var[f"start{c,q}"]>=var[f"start{c,q-1}"]+90+90*var[f"full{c,q-1}"]+8).only_enforce_if(
                [var[f"use{c,q}"],var[f"full{c,index}"]])
    for i,j in itertools.combinations(range(len(wafers)),2):
        if pair_mode[wafers[i]["pair"]]!=pair_mode[wafers[j]["pair"]]:
            continue
        same=m.new_bool_var(f"same_slot_{i}_{j}")
        m.add(positions[i]==positions[j]).only_enforce_if(same)
        m.add(positions[i]!=positions[j]).only_enforce_if(same.Not())
        for name in ("load","unload"):
            m.add(var[f"{i}_{name}"]==var[f"{j}_{name}"]).only_enforce_if(same)
        for name,duration in zip(STEPS,DUR):
            if name in ("al_put","al_pick"):
                continue
            if name in ("origin_pick","origin_put") and wafers[i]["origin"]!=wafers[j]["origin"]:
                continue
            left,right=var[f"{i}_{name}"],var[f"{j}_{name}"]
            order=m.new_bool_var(f"before_{i}_{j}_{name}")
            sync=m.new_bool_var(f"sync_{i}_{j}_{name}")
            m.add(sync<=same)
            m.add(left==right).only_enforce_if(sync)
            m.add(left+duration<=right).only_enforce_if([order,sync.Not()])
            m.add(right+duration<=left).only_enforce_if([order.Not(),sync.Not()])
    return m


if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--source",type=Path,required=True)
    p.add_argument("--out",type=Path,required=True)
    p.add_argument("--seconds",type=int,default=120)
    a=p.parse_args()
    a.out.mkdir(parents=True,exist_ok=True)
    doc=json.loads(a.source.read_bytes())
    s=cp_model.CpSolver()
    assert s.solve(tightened(doc,round(doc["cmax"]),True)) in (cp_model.FEASIBLE,cp_model.OPTIMAL)
    s.parameters.num_workers=3
    s.parameters.max_time_in_seconds=a.seconds
    s.parameters.log_search_progress=True
    s.parameters.log_to_stdout=False
    with (a.out/"cp.log").open("w",encoding="utf8",buffering=1) as log:
        s.log_callback=lambda msg:log.write(msg.rstrip()+"\n")
        status=s.solve(tightened(doc,552))
    data=dict(cap=552,status=s.status_name(status),wall_seconds=s.wall_time,
              lower=553 if status==cp_model.INFEASIBLE else s.best_objective_bound,
              upper=s.objective_value if status in (cp_model.OPTIMAL,cp_model.FEASIBLE) else None,
              source_sha256=hashlib.sha256(a.source.read_bytes()).hexdigest(),
              driver_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              base_sha256=hashlib.sha256(Path(__file__).with_name("primary_relaxation.py").read_bytes()).hexdigest())
    (a.out/"result.json").write_text(json.dumps(data,indent=2),encoding="utf8")
    print(data,flush=True)

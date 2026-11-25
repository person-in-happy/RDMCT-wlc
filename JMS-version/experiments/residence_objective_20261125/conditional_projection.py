"""Certified outer approximation for the minimum residence score at Cmax <= 553."""
import hashlib
import json
from pathlib import Path

from google.protobuf import text_format
from ortools.sat import cp_model_pb2
from ideal_projection import projection,cp_model


def projected(data,scale,pin):
    original=projection(data,553,pin)
    proto=text_format.Parse(str(original.proto),cp_model_pb2.CpModelProto())
    indices={v.name:i for i,v in enumerate(proto.variables)}
    times={i for i,v in enumerate(proto.variables) if v.name.startswith(("duration_","ch_","start(","makespan"))
           or (v.name and v.name[0].isdigit())}
    def scaled(n):
        if n in (-(2**63),2**63-1):
            return n
        return scale*n
    def duration(expr):
        if any(i in times for i in expr.vars):
            for k,i in enumerate(expr.vars):
                if i not in times:
                    expr.coeffs[k]*=scale
            expr.offset*=scale
        else:
            if expr.vars:
                raise ValueError("Unexpected discrete variable in a time expression")
            expr.offset*=scale
    for i in times:
        v=proto.variables[i]
        v.domain[:]=[scaled(x) for x in v.domain]
    ideal_rows={frozenset([indices[f"{i}_load"],indices[f"{i}_unload"]]) for i in range(8)}
    removed=0
    for c in proto.constraints:
        kind=c.WhichOneof("constraint")
        if kind=="linear":
            row=c.linear
            if (not c.enforcement_literal and len(row.vars)==2 and frozenset(row.vars) in ideal_rows
                    and row.domain[0]==row.domain[-1]):
                # Replace with a tautology so cumulative interval indices remain stable.
                c.ClearField("linear")
                c.bool_and.SetInParent()
                removed+=1
                continue
            if not any(i in times for i in row.vars):
                continue
            row.domain[:]=[scaled(n) for n in row.domain]
            for k,i in enumerate(row.vars):
                if i not in times:
                    row.coeffs[k]*=scale
        elif kind=="interval":
            for t in (c.interval.start,c.interval.end,c.interval.size):
                duration(t)
        elif kind=="lin_max" and any(i in times for i in c.lin_max.target.vars):
            for t in (c.lin_max.target,*c.lin_max.exprs):
                duration(t)
        elif kind not in ("exactly_one","cumulative","lin_max"):
            raise ValueError(kind)
    assert removed==8
    proto.ClearField("solution_hint")
    proto.ClearField("objective")
    m=cp_model.CpModel()
    m.proto.parse_text_format(str(proto))
    products=sorted((w for w in data["jobs"] if w["product"]),key=lambda w:(w["pjob"],w["pjob_index"]))
    modes={p["id"]:p["mode"] for p in data["pairs"]}
    r={"4x1":[],"2x2":[]}
    for i,w in enumerate(products):
        x=m.new_int_var(0,scale*100,f"resident_{i}")
        v=lambda name:m.get_int_var_from_proto_index(indices[f"{i}_{name}"])
        m.add(x==v("unload")-v("load")-181*scale)
        mode=modes[w["pair"]]
        if mode=="2x2":
            m.add(x>=6*scale)
        r[mode].append(x)
    spread=m.new_int_var(0,scale*100,"spread")
    for mode,group in r.items():
        for a in group:
            for b in group:
                if a is not b:
                    m.add(spread>=a-b)
    total=sum(r["4x1"])+sum(r["2x2"])+8*spread
    return m,total


if __name__=="__main__":
    here=Path(__file__).resolve().parent
    root=here.parents[1]/"results/residence_objective_20261125/best_reuse"
    source=root/"n8_H10/retained_product_times/schedule.json"
    data=json.loads(source.read_bytes())
    scale=1000
    out=root/"conditional_553"
    out.mkdir(exist_ok=True)
    test=cp_model.CpSolver()
    test.parameters.num_workers=1
    m,f=projected(data,scale,True)
    m.add(f==34*scale)
    assert test.solve(m)==cp_model.OPTIMAL
    m,f=projected(data,scale,False)
    m.add(f<=34*scale)
    m.minimize(f)
    s=cp_model.CpSolver()
    s.parameters.num_workers=2
    s.parameters.max_time_in_seconds=100
    s.parameters.log_search_progress=True
    s.parameters.log_to_stdout=False
    with (out/"cp.log").open("w",encoding="utf8",buffering=1) as log:
        s.log_callback=lambda msg:log.write(msg.rstrip()+"\n")
        status=s.solve(m)
    result=dict(status=s.status_name(status),cap=553,scale=scale,seconds=s.wall_time,
                lower_integer=s.best_objective_bound,projected_incumbent=s.objective_value,
                lower_physical=max(3.5,s.best_objective_bound/(8*scale)-3/scale),
                feasible_physical=4.25,physical_witness_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                code={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in
                    [Path(__file__),*(here/k for k in ("ideal_projection.py","tight_primary.py","primary_relaxation.py"))]})
    (out/"result.json").write_text(json.dumps(result,indent=2),encoding="utf8")
    print(result,flush=True)

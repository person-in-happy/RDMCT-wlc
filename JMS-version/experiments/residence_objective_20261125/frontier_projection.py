"""Continuous near-Pareto supporting line for batch makespan 553 to 554 seconds."""
import argparse
import time
import hashlib
import json
from pathlib import Path

from google.protobuf import text_format
from ortools.sat import cp_model_pb2
from ideal_projection import projection,cp_model


def projected(data,scale,pin):
    original=projection(data,554,pin)
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


def main(scale,budget,only_midpoint):
    here=Path(__file__).resolve().parent
    root=here.parents[1]/"results/residence_objective_20261125/best_reuse"
    src=root/"n8_H10/retained_product_times/schedule.json"
    doc=json.loads(src.read_bytes())
    test="at_553p5" if only_midpoint else "line_553_to_554"
    out=root/"continuous_frontier"/test/f"scale_{scale}"
    out.mkdir(parents=True,exist_ok=True)
    dependencies=[Path(__file__),*(here/k for k in ("ideal_projection.py","tight_primary.py","primary_relaxation.py"))]
    digest=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    signature={p.name:digest(p) for p in dependencies}
    checkpoint=out/"result.json"
    if checkpoint.exists():
        old=json.loads(checkpoint.read_bytes())
        if old["code"]==signature and old["status"] in ("INFEASIBLE","OPTIMAL","FEASIBLE"):
            print("Already complete",old["status"],flush=True)
            return
    start=time.perf_counter()
    print(f"1 worker, {test}, scaled grid {scale}, elapsed 0 s, remaining budget {budget} s; historical related decision 1--20 s",flush=True)
    m,cost=projected(doc,scale,False)
    vs={v.name:m.get_int_var_from_proto_index(i) for i,v in enumerate(m.proto.variables)}
    C=vs["makespan"]
    m.add(C>=553*scale)
    # Lower line at each grid-cap. Rational theta floor maps a physical time into
    # the grid. Residence error <1/scale, spread error <2/scale, and makespan
    # never increases. E (early-clean deficit) is nonnegative and dropped.
    if only_midpoint:
        m.add(C<=553*scale+scale//2)
        weighted=cost
        cut=31*scale-1
    else:
        weighted=cost+6*(C-553*scale)
        cut=34*scale-1
    m.add(weighted<=cut)
    # Every candidate in this sublevel has unweighted score <=4.25. For recipe
    # peaks x,y, mean >= .5(x+y)-spread, hence x+y<=8.5 and y>=7.
    m.add(vs["spread"]*2<=3*scale)
    for i in range(8):
        m.add(2*vs[f"resident_{i}"]<=(3 if i<4 else 17)*scale)
    m.add_max_equality(m.new_int_var(7*scale,17*scale//2,"mixed_peak"),[vs[f"resident_{i}"] for i in range(4,8)])
    # No full-recipe back position can meet x<=1.5. Both chambers accommodate
    # at most 4 ninety-second units each; four mixed wafers need >=3 such units.
    # Thus exactly two full cycles, each with two front wafers.
    for c in range(2):
        for q in range(4):
            for i in range(4):
                m.add(vs[f"w{i}_{c}_{q}_0"]==0)
            m.add(sum(vs[f"w{i}_{c}_{q}_1"] for i in range(4))==2*vs[f"full{c,q}"])
    m.add(sum(vs[f"full{c,q}"] for c in range(2) for q in range(4))==2)
    m.add(vs["ch0"]==0)
    s=cp_model.CpSolver()
    s.parameters.num_workers=1
    s.parameters.max_time_in_seconds=budget
    s.parameters.log_search_progress=True
    s.parameters.log_to_stdout=False
    with (out/"cp.log").open("w",encoding="utf8",buffering=1) as log:
        s.log_callback=lambda msg:log.write(msg.rstrip()+"\n")
        status=s.solve(m)
    result=dict(status=s.status_name(status),seconds=s.wall_time,scale=scale,integer_cut=cut,test=test,
                continuous_lower=(cut+1)/(8*scale)-3/scale if status==cp_model.INFEASIBLE else None,
                feasible_upper=3.875 if only_midpoint else 4.25,num_workers=1,code=signature,
                input_sha256=digest(src),physical_time_grid="componentwise floor; difference-constraint projected times")
    if status in (cp_model.FEASIBLE,cp_model.OPTIMAL):
        result.update(projected_C=s.value(C)/scale,projected_score=s.value(cost)/(8*scale),
                      times={k:s.value(v) for k,v in vs.items() if k and (k[0].isdigit() or k.startswith(("start","w","full","ch_","use","resident_","spread")))})
    tmp=out/"result.tmp"
    tmp.write_text(json.dumps(result,indent=2),encoding="utf8")
    tmp.replace(checkpoint)
    print({k:v for k,v in result.items() if k not in ("times","code")},flush=True)


if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--scale",type=int,default=1000)
    p.add_argument("--seconds",type=int,default=55)
    p.add_argument("--midpoint",action="store_true")
    a=p.parse_args()
    main(a.scale,a.seconds,a.midpoint)

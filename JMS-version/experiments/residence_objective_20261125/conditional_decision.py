"""Test a near-optimal sublevel with front-pair packing implied by the score cutoff."""
import argparse
import hashlib
import json
from pathlib import Path
from conditional_projection import projected,cp_model


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--scale",type=int,default=500)
    parser.add_argument("--margin",type=int,default=5)
    args=parser.parse_args()
    here=Path(__file__).resolve().parent
    base=here.parents[1]/"results/residence_objective_20261125/best_reuse"
    src=base/"n8_H10/retained_product_times/schedule.json"
    doc=json.loads(src.read_bytes())
    scale=args.scale
    m,cost=projected(doc,scale,False)
    vs={v.name:m.get_int_var_from_proto_index(i) for i,v in enumerate(m.proto.variables)}
    # These rows follow from grid score <=4.25, with half the wafers in each
    # recipe, peak 2x2 residence >=7 and all 2x2 residence >=6. Both recipe peaks
    # sum to at most twice the objective. No 4x1 back wafer can reside <=1.5.
    upper=34*scale-args.margin
    m.add(cost<=upper)
    m.add(vs["spread"]<=3*scale//2)
    for i in range(8):
        x=vs[f"resident_{i}"]
        m.add(x<=(3 if i<4 else 17)*scale//2)
    m.add_max_equality(m.new_int_var(7*scale,17*scale//2,"mixed_peak"),[vs[f"resident_{i}"] for i in range(4,8)])
    for c in range(2):
        for q in range(4):
            for i in range(4):
                m.add(vs[f"w{i}_{c}_{q}_0"]==0)
            # At most four 90s units fit per chamber. Three 2x2 cycles are
            # necessary for four 2x2 products, leaving at most two full cycles.
            m.add(sum(vs[f"w{i}_{c}_{q}_1"] for i in range(4))==2*vs[f"full{c,q}"])
    m.add(sum(vs[f"full{c,q}"] for c in range(2) for q in range(4))==2)
    m.add(vs["ch0"]==0)  # Symmetric chambers with identical qualifications and times.
    out=base/"conditional_decision"/f"scale_{scale}"
    out.mkdir(parents=True,exist_ok=True)
    s=cp_model.CpSolver()
    s.parameters.num_workers=1
    s.parameters.max_time_in_seconds=80
    s.parameters.log_search_progress=True
    s.parameters.log_to_stdout=False
    with (out/"cp.log").open("w",encoding="utf8",buffering=1) as f:
        s.log_callback=lambda line:f.write(line.rstrip()+"\n")
        z=s.solve(m)
    result=dict(status=s.status_name(z),seconds=s.wall_time,grid_scale=scale,grid_cutoff_numerator=upper,
                lower_physical=(upper+1)/(8*scale)-3/scale if z==cp_model.INFEASIBLE else 3.5,
                upper_physical=4.25,projected_score=s.value(cost)/(8*scale) if z in (cp_model.FEASIBLE,cp_model.OPTIMAL) else None,
                source_sha256=hashlib.sha256(src.read_bytes()).hexdigest(),scope="eight-wafer Cmax<=553",
                code={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in
                      [Path(__file__),*(here/k for k in ("conditional_projection.py","ideal_projection.py","tight_primary.py","primary_relaxation.py"))]})
    (out/"result.json").write_text(json.dumps(result,indent=2),encoding="utf8")
    print(result,flush=True)

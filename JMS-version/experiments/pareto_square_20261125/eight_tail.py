"""Find a continuous supporting bound for the low-score three-entry exposure chain."""
from pathlib import Path
import sys,time
from support import HERE,R,OUT,read,write,digest
sys.path.insert(0,str(HERE.parent/"huber_residence_20261125"))
from attainment_hardware import hardware,cp_model
from google.protobuf import text_format
from ortools.sat import cp_model_pb2


def run(member,budget):
    p=OUT/"eight_tail"/f"pair{member}";p.mkdir(exist_ok=True,parents=True)
    signature={x.name:digest(x) for x in (Path(__file__),HERE.parent/"huber_residence_20261125/attainment_hardware.py",
                                           HERE.parent/"huber_residence_20261125/optimum_makespan_bound.py")}
    f=p/"result.json"
    if f.exists():
        old=read(f);assert old["signature"]==signature
        if old["status"]=="OPTIMAL" or old["used"]>=budget-.1:return
    else:old={"used":0}
    src=R/"huber_residence_20261125/witnesses_grid_middle/D_n8_H10_mixed_dual/schedule.json"
    native=read(src)
    base,_=hardware(native,577)
    proto=text_format.Parse(str(base.proto),cp_model_pb2.CpModelProto())
    names=[z.name for z in proto.variables];count=0
    for c in proto.constraints:
        if c.WhichOneof("constraint")!="linear" or c.enforcement_literal:continue
        row=c.linear
        if len(row.domain)!=2 or row.domain[0]!=row.domain[1]:continue
        keys={names[i] for i in row.vars}
        match=any(keys=={f"{i}_load",f"{i}_unload"} if i<4 else keys=={f"{i}_load",f"{i}_unload",f"mixed_last_{i}"} for i in range(8))
        if match:
            c.ClearField("linear");c.bool_and.SetInParent();count+=1
    assert count==8
    m=cp_model.CpModel();m.proto.parse_text_format(str(proto))
    v={z.name:m.get_int_var_from_proto_index(i) for i,z in enumerate(m.proto.variables) if z.name}
    for i in range(8):
        r=v[f"{i}_unload"]-v[f"{i}_load"]-181*8
        # For a strict improvement on 3.46875, physical excess above the chain lower envelope is at most 5/16 s.
        # A common floor phase onto the one-eighth grid rounds these difference bounds outwards.
        m.add(r<=(3 if i<4 else 59))
        if i>=4:m.add(r>=50)
    # At cap 577 only three entering pairs fit on the double-exposure chamber.
    m.add(v["use(1, 4)"]==0)
    residence=v[f"pt1{member+1}bu"]-v[f"pt1{member}fl"]-181*8
    val=v["makespan"]-residence;m.minimize(val)
    if "bound" in old:m.add(val>=round(8*old["bound"]))
    solver=cp_model.CpSolver();solver.parameters.num_workers=1;solver.parameters.random_seed=1
    solver.parameters.max_time_in_seconds=budget-old["used"];solver.parameters.log_to_stdout=False;solver.parameters.log_search_progress=True
    with (p/"search.log").open("a",encoding="utf8") as log:
        solver.log_callback=lambda ln:log.write(ln.rstrip()+"\n")
        stat=solver.solve(m)
    rec=dict(signature=signature,source_sha256=digest(src),status=solver.status_name(stat),bound=solver.best_objective_bound/8,
             used=old["used"]+solver.wall_time,scale=8,member=member,removed_optimum_only_equalities=count)
    if stat in (cp_model.FEASIBLE,cp_model.OPTIMAL):rec["upper"]=solver.objective_value/8
    write(f,rec);print(rec["status"],rec["bound"],rec.get("upper"),flush=True)


if __name__=="__main__":
    start=time.monotonic();(OUT/"eight_tail").mkdir(exist_ok=True,parents=True)
    for i in (0,1):
        spent=time.monotonic()-start;eta=60*(2-i)
        q=dict(completed=i,total=2,failed=0,elapsed=spent,eta_remaining=eta,eta_total=spent+eta,basis="one CPU, 60 s allowance per group")
        write(OUT/"eight_tail/progress.json",q);print(q,flush=True);run(i,60)
    q.update(completed=2,elapsed=time.monotonic()-start,eta_remaining=0);q["eta_total"]=q["elapsed"];write(OUT/"eight_tail/progress.json",q)

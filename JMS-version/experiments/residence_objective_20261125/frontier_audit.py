"""Replay native integral endpoints and audit the difference-constraint projection used in the proof."""
from collections import Counter
from fractions import Fraction
from pathlib import Path
import sys

from google.protobuf import text_format
from ortools.sat import cp_model_pb2
from ideal_projection import projection
from solver import HERE,cell,read,save,sha
from score import metrics
sys.path.insert(0,str(cell.BACKENDS["D"]))
from model import Config,Integrated
from validate import validate

root=HERE.parents[1]/"results/residence_objective_20261125/best_reuse"
out=root/"continuous_frontier"


def audit_proto(doc):
    p=text_format.Parse(str(projection(doc,554).proto),cp_model_pb2.CpModelProto())
    times={i for i,v in enumerate(p.variables) if v.name.startswith(("duration_","ch_","start(","makespan")) or (v.name and v.name[0].isdigit())}
    counts=Counter()
    sizes=set()
    for c in p.constraints:
        kind=c.WhichOneof("constraint");counts[kind]+=1
        if kind=="linear":
            coeffs=[w for i,w in zip(c.linear.vars,c.linear.coeffs) if i in times]
            assert not coeffs or sorted(coeffs) in ([-1,1],[-1],[1])
        elif kind=="interval":
            assert len(c.interval.size.vars)==1
            idx=c.interval.size.vars[0];assert p.variables[idx].name.startswith("duration_")
            sizes.add(idx)
            for end in (c.interval.start,c.interval.end):
                assert len(end.vars)==len(end.coeffs)==1 and end.vars[0] in times and end.coeffs[0]==1
        elif kind=="lin_max":
            if set(c.lin_max.target.vars)&times:
                assert all(len(e.vars)==len(e.coeffs)==1 and e.coeffs[0]==1 for e in [c.lin_max.target,*c.lin_max.exprs])
        elif kind=="cumulative":
            assert not c.cumulative.capacity.vars and all(not d.vars and d.offset==1 for d in c.cumulative.demands)
        else:
            assert kind=="exactly_one"
    assert all(not(set(c.linear.vars)&sizes) for c in p.constraints if c.WhichOneof("constraint")=="linear")
    return dict(constraint_types=dict(counts),independent_interval_lengths=len(sizes))


def exact_number(n):
    return int(n) if n==int(n) else Fraction.from_float(n)


def replay(h):
    base=root/f"n8_H{h}"
    names=("retained_product_times","ideal_fixed")
    docs=[read(base/t/"schedule.json") for t in names]
    x=Integrated(Config(**docs[0]["config"]));m=x.model
    endpoints=[];raw_discrepancy=[]
    for name in names:
        raw=cell.values(base/name/"assignment.json.gz")
        raw_discrepancy.append(max(abs(n-round(n)) for n in raw.values()))
        assert raw_discrepancy[-1]<1e-10
        endpoints.append({k:round(n) for k,n in raw.items() if round(n)!=0})
    a,b=endpoints
    integer_count=0
    for v in m.getVars(transformed=False):
        l,u=v.getLbGlobal(),v.getUbGlobal()
        va,vb=a.get(v.name,0),b.get(v.name,0)
        assert l<=va<=u and l<=vb<=u
        if v.vtype()!="CONTINUOUS":
            assert va==vb
            integer_count+=1
    count=0
    for row in m.getConss():
        assert row.isLinear()
        vals=m.getValsLinear(row)
        lhs,rhs=exact_number(m.getLhs(row)),exact_number(m.getRhs(row))
        av=bv=0
        for k,coef in vals.items():
            w=exact_number(coef)
            av+=w*a.get(k,0); bv+=w*b.get(k,0)
        assert lhs<=av<=rhs and lhs<=bv<=rhs,row.name
        count+=1
    endpoints_rows=[]
    for name,z in zip(names,endpoints):
        s=cell.attach(x,z);doc=x.result(solution=s)
        val=validate(doc);assert val["valid"]
        f=metrics(doc)
        products=[w for w in doc["jobs"] if w["product"]]
        res={w["identity"]:w["unload_start"]-w["load_end"]-180 for w in products}
        final=[w["identity"] for w in products if w["loan_end"]==f["cmax"]]
        assert final==["LP4_W1"]
        endpoints_rows.append(dict(metrics=f,wafer_residence=res,final=final,
            assignment_sha256=sha(base/name/"assignment.json.gz"),schedule_sha256=sha(base/name/"schedule.json")))
        m.freeSol(s)
    m.freeProb()
    return dict(exact_native_linear_rows=count,identical_integral_variables=integer_count,
                max_archive_rounding=raw_discrepancy,endpoints=endpoints_rows)


if __name__=="__main__":
    roots=[out/"line_553_to_554/scale_1000/result.json",out/"eight_units_554/result.json"]
    lower,exposure=map(read,roots)
    assert lower["status"]==exposure["status"]=="INFEASIBLE"
    assert Fraction(3,lower["scale"]) < Fraction(1,8*27)
    res={h:replay(h) for h in (3,10)}
    shape=audit_proto(read(root/"n8_H10/ideal_fixed/schedule.json"))
    save(out/"certificate.json",dict(cmax_interval=[553,554],intercept=4.25,slope=-.75,
        midpoint=[553.5,3.875],integer_row_norm_at_most=3,rank_at_most=3,denominator_at_most=27,
        grid_error="3/1000",minimum_strict_shortfall="1/216",projection_audit=shape,
        native_replays=res,code_sha256=sha(Path(__file__)),proof_records={str(p.relative_to(out)):sha(p) for p in roots}))
    print("validated",[(h,res[h]["exact_native_linear_rows"],res[h]["identical_integral_variables"]) for h in res],flush=True)

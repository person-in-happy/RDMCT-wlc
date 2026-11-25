"""Check the native real-time family and the projected integer supports at each certified endpoint."""
import sys
from pathlib import Path
from sweep import OUT,Config,Integrated,atomic,cell,metrics,read,save,sha,validate


def certify(end):
    assert end in (811,812)
    native=OUT/"cap810/p0020_native"
    target=OUT/"continuous16";target.mkdir(exist_ok=True)
    config=Config(**read(native/"schedule.json")["config"])
    x=Integrated(config);model=x.model
    model.setRealParam("numerics/feastol",1e-8)
    variables=list(model.getVars(transformed=False))
    discrete={v.name for v in variables if v.vtype()!="CONTINUOUS"}
    endpoint_vals={}
    evidence={}
    for cap in range(810,end+1):
        where=OUT/f"cap{cap}"
        cat=read(where/"catalogue.json")
        files=list(where.glob("p????.json"));assert len(files)==len(cat["remaining"])
        feasible={}
        for f in files:
            record=read(f)
            assert record["status"] in ("OPTIMAL","INFEASIBLE")
            if record["status"]=="OPTIMAL":feasible[f.stem]=record["lower16"]/16
        assert feasible.get("p0020")==37.125-(cap-810)*1.125
        assert min(feasible.values())==feasible["p0020"]
        origin=native if cap==810 else OUT/f"sixteen_37/cap_{cap}"
        f=origin/"assignment.json.gz"
        raw=cell.values(f)
        snap={k:round(a) for k,a in raw.items()}
        s=cell.solution(x,snap)
        if not model.checkSol(s,original=True,completely=True):
            model.freeSol(s)
            repaired=cell.lift(config,snap,None,rebuild=True)
            assert repaired
            snap=repaired[1]["nonzero"] if "nonzero" in repaired[1] else repaired[1]["values"]
            s=cell.solution(x,snap)
        assert model.checkSol(s,original=True,completely=True)
        doc=x.result(solution=s);model.freeSol(s)
        score=metrics(doc);assert score["secondary"]==feasible["p0020"] and score["cmax"]==cap
        rec=validate(doc);assert rec["valid"]
        endpoint_vals[cap]=snap
        assert all(snap.get(k,0)==endpoint_vals[810].get(k,0) for k in discrete)
        evidence[cap]=dict(feasible_supports=feasible,total_patterns=cat["total"],audited_results={f.stem:sha(f) for f in files},
            original_source_sha256=sha(origin/"assignment.json.gz"),discrete_variables=len(discrete),
            verified_rows=model.getNConss(),metrics=score,checks=rec["checks"])
        dest=target/f"endpoint{cap}";dest.mkdir(exist_ok=True)
        save(dest/"schedule.json",doc);save(dest/"assignment.json.gz",cell.sparse(snap))
        evidence[cap]["schedule_sha256"]=sha(dest/"schedule.json")
    for cap in range(810,end):
        a,b=endpoint_vals[cap],endpoint_vals[cap+1];checks=[]
        for t in (.25,.5,.75):
            values={k:(1-t)*a.get(k,0)+t*b.get(k,0) for k in set(a)|set(b)}
            sol=cell.solution(x,values);assert model.checkSol(sol,original=True,completely=True)
            doc=x.result(solution=sol);model.freeSol(sol)
            r=metrics(doc);q=validate(doc)
            assert q["valid"] and r["cmax"]==cap+t and r["secondary"]==37.125-1.125*(cap+t-810)
            checks.append(dict(t=t,score=r,physical_checks=q["checks"]))
        evidence[cap]["interpolation_checks"]=checks
    result=dict(interval=[810,end],formula="f_B=37.125-1.125*(C-810)",scope="global original model, continuous event times",
        code_sha256=sha(Path(__file__)),four_finger_support_model=sha(Path(__file__).with_name("cap810.py")),
        evidence=evidence)
    atomic(target/"certificate.json",result)
    print(result["interval"],result["formula"],model.getNConss(),flush=True)


if __name__=="__main__":
    certify(int(sys.argv[1]))

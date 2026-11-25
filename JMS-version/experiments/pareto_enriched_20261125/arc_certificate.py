"""Validate exact original-assignment interpolation and archive clipping of two 16-wafer families."""
from collections import Counter
from fractions import Fraction
import hashlib
import math
from pathlib import Path
import time
import msvcrt
from native_caps import OUT,SQ,OLD,JMS,fixed
from support import read,write,digest
from collect import table

s=fixed.sweep
def main():
    dest=OUT/"curves";dest.mkdir(exist_ok=True)
    jobs={
        "short":(SQ/"fixed/short16/cap_811",SQ/"fixed/short16/cap_812",811.,812.,7.5,-.125,29.,-1.,812.),
        "middle":(OUT/"fixed/cross875/cap_873",OUT/"native/full_first_877_0/p_875_56_0",873.,875.,3.125,.1875,1.,-.5,874.25)}
    check=dest/"families.json";srcs=[v/"assignment.json.gz" for a in jobs.values() for v in a[:2]]
    observed=OUT/"optimization_observations.csv"
    sig={f.relative_to(JMS).as_posix():digest(f) for f in [*srcs,observed,Path(__file__)]}
    if check.exists() and read(check)["signature"]==sig:return
    clock=time.monotonic()
    def status(n,step):
        w=time.monotonic()-clock;eta=(4-n)*(w/n if n else 14)
        q=dict(stage=step,completed=n,total=4,failed=0,elapsed=w,eta_total=w+eta,eta_remaining=eta,basis="native model replay and linear support; current stage mean")
        print(q,flush=True);write(dest/"progress.json",q)
    status(0,"native model")
    x=s.Integrated(s.Config(**read(jobs["short"][0]/"schedule.json")["config"]));m=x.model
    s.cell.scip_settings(m,dict(n=16,seed=1,seconds=40,gap=0),dest);m.setRealParam("numerics/feastol",1e-9)
    rowtypes=Counter(c.getConshdlrName() for c in m.getConss(transformed=False));assert set(rowtypes)=={"linear"}
    variables=m.getVars(transformed=False)
    iv=sorted((v for v in variables if v.vtype()!="CONTINUOUS"),key=lambda v:v.name)
    assert len(iv)==308924
    archive=table(observed)
    roots={};family={}
    for idx,(name,(pa,pb,c0,c1,m0,dm,d0,dd,last)) in enumerate(jobs.items(),1):
        vals=[]
        for folder in (pa,pb):
            raw=s.cell.values(folder/"assignment.json.gz")
            snapped={k:round(a) for k,a in raw.items()}
            if max(abs(a-snapped[k]) for k,a in raw.items())>1e-4:
                # Continuous nuisance slack may take arbitrary fractional values even at integer event times.
                snapped={k:round(a) if abs(a-round(a))<1e-5 else a for k,a in raw.items()}
            vals.append(snapped)
        a,b=vals;md=hashlib.sha256()
        for v in iv:
            value=round(a.get(v.name,0));assert value==b.get(v.name,0)
            md.update(f"{v.name}={value}\n".encode())
        samples=[];docs=[]
        for t in (Fraction(0),Fraction(1,8),Fraction(1,4),Fraction(1,2),Fraction(5,8),Fraction(3,4),Fraction(1)):
            h=float(t);z={k:(1-h)*a.get(k,0)+h*b.get(k,0) for k in a.keys()|b.keys()}
            sol=s.cell.attach(x,z);doc=x.result(solution=sol);m.freeSol(sol);q=s.validate(doc)
            f=fixed.metrics(doc);assert q["valid"] and f["clean_deficit"]==0
            C=c0+h*(c1-c0);r=m0+dm*(C-c0);d=d0+dd*(C-c0)
            assert max(abs(f[k]-v) for k,v in (("cmax",C),("mean_residence",r),("residence_range",d),("secondary",r+d*d/2)))<1e-7
            sample=dest/name/f"t_{t.numerator}_{t.denominator}";sample.mkdir(parents=True,exist_ok=True)
            s.save(sample/"schedule.json",doc);s.save(sample/"assignment.json.gz",s.cell.sparse(z))
            write(sample/"result.json",dict(original_rows=sum(rowtypes.values()),checks=q["checks"],metrics=f,
                       scope="native linear interpolation",files={k:digest(sample/k) for k in ("schedule.json","assignment.json.gz")}))
            samples.append(dict(t=str(t),C=C,mean=r,D=d,fb=r+d*d/2,replay=q["checks"],schedule=(sample/"schedule.json").relative_to(JMS).as_posix()))
            if t in (0,1):docs.append(doc)
        def product_roles(doc):
            modes={p["id"]:p["mode"] for p in doc["pairs"]}
            return {j["identity"]:(modes[j["pair"]],j["unload_start"]-j["load_start"]-181,j["loan_end"]) for j in doc["jobs"] if j["product"]}
        p,q=map(product_roles,docs);assert p.keys()==q.keys()
        commonlast=[k for k in p if abs(p[k][2]-c0)<1e-7 and abs(q[k][2]-c1)<1e-7]
        # Max and min of affine wafer residences can switch inside; a common attaining extremal pair proves the stated full-interval formula.
        pairs=[(i,j) for i in p for j in p if p[i][0]==p[j][0]
               and abs(p[i][1]-p[j][1]-d0)<1e-7 and abs(q[i][1]-q[j][1]-d0-dd*(c1-c0))<1e-7]
        assert commonlast and pairs
        family[name]=dict(C0=c0,C1=c1,strictly_decreasing_until_C=last,mean0=m0,dmean_dC=dm,D0=d0,dD_dC=dd,
                          rows=dict(rowtypes),integer_sha256=md.hexdigest(),common_integer_variables=len(iv),
                          common_last_products=commonlast,common_range_extremal_pair=pairs[0],samples=samples,
                          endpoints=[f.relative_to(JMS).as_posix() for f in (pa,pb)])
        if name=="middle":
            roots={"values":a,"doc":docs[0]}
        status(idx,f"{name} interpolation")
    a=roots["values"]
    for v in iv:
        value=round(a.get(v.name,0));m.chgVarLb(v,value);m.chgVarUb(v,value)
    D=m.addVar(name="family_spread",lb=0,ub=100)
    jobs=[j for j in roots["doc"]["jobs"] if j["product"]]
    for j in jobs:
        for k in jobs:
            if j["pjob"]!=k["pjob"]:continue
            z=x.jobs[j["name"]];w=x.jobs[k["name"]]
            m.addCons(D>=(z["unload_s"]-z["load_e"])-(w["unload_s"]-w["load_e"]))
    m.setObjective(x.cmax+2*D,"minimize");m.optimize();assert str(m.getStatus())=="optimal"
    lb,ub=m.getDualbound(),m.getPrimalbound()
    assert abs(lb-875)<1e-6 and abs(ub-875)<1e-6
    family["middle"]["support"]={"global_within_fixed_integer_decisions":True,"min_C_plus_2D":[lb,ub],
                             "mean_lower":"3.5 - 3*D/8 from two terminal products out of eight double-exposure products"}
    status(3,"fixed-structure support")
    reference=min(float(r["fb"]) for r in archive if float(r["fa"])<873)
    reference=round(reference*1024)/1024
    crossing=874.25-math.sqrt(8*(reference-3.4296875))
    assert 873<crossing<874.25
    for row in archive:
        c,y=float(row["fa"]),float(row["fb"])
        if crossing<c<=874.25:
            assert y>=3.4296875+(874.25-c)**2/8-3e-5
        if 811<c<812:
            assert y>=7.5-.125*(c-811)+.5*(29-(c-811))**2-3e-5
    family["middle"]["archive_interval"]=[crossing,874.25];family["middle"]["left_open"]=True
    family["middle"]["reference_B"]=reference
    family["short"]["archive_interval"]=[811,812];family["short"]["right_open"]=True
    write(check,dict(signature=sig,optimization_archive_sha256=digest(observed),families=family))
    status(4,"complete");m.freeProb()

if __name__=="__main__":
    OUT.mkdir(exist_ok=True,parents=True)
    with (OUT/"arc_cert.lock").open("a+b") as lock:
        try:msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
        except OSError:raise SystemExit("Existing worker")
        main()

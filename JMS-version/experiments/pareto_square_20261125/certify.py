"""Combine the old physical rows and new quadratic supporting hyperplanes on all three scales."""
from math import sqrt
import sys
from pathlib import Path
from support import HERE,JMS,OUT,OLD,R,read,write,digest
sys.path.insert(0,str(HERE.parent/"square_residence_20261125"))
from solver import cell
from score import metrics
sys.path.insert(0,str(cell.BACKENDS["D"]))
from model import Config, Integrated
from validate import validate


def certify_eight():
    lo=OUT/"fixed/long8/cap_576"
    hi=R/"huber_residence_20261125/witnesses_grid_middle/D_n8_H10_mixed_dual"
    cfg=Config(**read(hi/"schedule.json")["config"]);x=Integrated(cfg);m=x.model
    m.setRealParam("numerics/feastol",1e-8)
    a0=cell.values(lo/"assignment.json.gz");a={k:round(t*8)/8 for k,t in a0.items()}
    b=cell.values(hi/"assignment.json.gz")
    discrete=[v.name for v in m.getVars(transformed=False) if v.vtype()!="CONTINUOUS"]
    assert all(a.get(k,0)==b.get(k,0) for k in discrete)
    knots={}
    for t in (0,.25,.5,.75,1):
        vals={k:(1-t)*a.get(k,0)+t*b.get(k,0) for k in set(a)|set(b)}
        sol=cell.solution(x,vals)
        assert m.checkSol(sol,original=True,completely=True)
        doc=x.result(solution=sol);m.freeSol(sol);q=validate(doc);z=metrics(doc)
        u=.625*t
        assert q["valid"] and abs(z["cmax"]-(576+u))<1e-8 and abs(z["mean_residence"]-3.125-.375*u)<1e-8
        assert abs(z["residence_range"]-1+u)<1e-8 and z["clean_deficit"]==0
        assert abs(z["secondary"]-(3.625-.625*u+.5*u*u))<1e-8
        knots[t]=dict(metrics=z,checks=q["checks"])
    rows=m.getNConss();m.freeProb()
    middle=read(OUT/"eight_tail/pair1/result.json");assert middle["status"]=="OPTIMAL" and middle["bound"]==570
    switch=.625-sqrt(5/64)
    return dict(source_sha256=[digest(lo/"assignment.json.gz"),digest(hi/"assignment.json.gz")],rows=rows,
                identical_integer_assignments=len(discrete),native_interpolation=knots,conditional_C_minus_middle=570,
                lower_sha256=digest(OUT/"eight_tail/pair1/result.json"),tail_formula="3.625 - .625*u + .5*u^2, u=C-576",
                tail_interval=[576+switch,576.625],left_open=True,H10_complete_front=True,H3_complete_front=True,
                short_interval=[553,553.75],short_formula="3.75 - .75*t + .5*t^2, t=C-553")


def certify_sixteen():
    slopes={}
    for cap,mean,spread in ((810,7.625,30),(811,7.5,29)):
        dep=OUT/f"support/{cap}_20_30_0_0/result.json";dual=read(dep)
        assert dual["status"]=="OPTIMAL" and abs(dual["lower16"]/16-(mean+30*spread))<1e-8
        old=read(OLD/f"cap{cap}/p0020.json")
        assert abs(old["lower16"]/16+.5-(mean+spread))<1e-8
        cert=read(OLD/"continuous16/certificate.json")
        z=metrics(read(OLD/f"continuous16/endpoint{cap}/schedule.json"))
        assert z["mean_residence"]==mean and z["residence_range"]==spread
        slopes[cap]=dict(slope30_source_sha256=digest(dep),slope1_source_sha256=digest(OLD/f"cap{cap}/p0020.json"),
                         native_event_score=z,native_schedule_sha256=cert["evidence"][str(cap)]["schedule_sha256"])
    assert cert["interval"]==[810,811]
    r812={pat:read(OUT/f"support/812_{pat}_16_{g}_{g}/result.json")["lower16"]/16-128 for pat,g in ((20,0),(26,11))}
    assert r812[20]>r812[26]
    return dict(interval=[810,811],curve="7.625 - .125*t + .5*(30-t)^2, t=C-810",supports=slopes,
                binding_objectives=[457.625,428],scope="all structures and continuous event times",native_interpolation_sha256=digest(OLD/"continuous16/certificate.json"),
                cap812_squared_lower_by_pattern=r812,cap812_squared_global_lower=min(r812.values()))


def main():
    four={}
    for h in (3,10):
        v=[]
        for part in ("short397","417_pinned"):
            f=OLD/f"four_native_H{h}/{part}/schedule.json";z=metrics(read(f))
            assert z["residence_range"]<=1
            v.append(dict(metrics=z,schedule_sha256=digest(f)))
        four[h]=v
    write(OUT/"certificate.json",dict(score="mean + D^2/(2*delta) + gamma*E",delta=1,gamma=1,four_complete=four,
        four_projection_sha256=digest(OLD/"four_bound/2_0.json"),eight=certify_eight(),sixteen=certify_sixteen(),
        eight_short_proof_sha256=digest(R/"huber_residence_20261125/frontier/certificate.json"),
        four_source_proof_sha256=digest(OLD/"four_bound/proof.md"),verification_code_sha256=digest(Path(__file__))))
    print("Replayed exact curves and certified non-dominance for four, eight and sixteen wafers.",flush=True)


if __name__=="__main__":main()

"""Prove the first continuous 4-wafer tradeoff with 24 exhaustive relaxed routing certificates."""
from collections import Counter
from pathlib import Path
from orders import OUT,JMS,EX,sweep,fixed,designs

def main():
    groups={k:v for k,v in designs().items() if len(v[0])==1 and len(v[2])>0}
    code=EX/"pareto_four_enriched_20261125/short_projection.py";signature=sweep.sha(code)
    records={}
    for tag,g in groups.items():
        file=OUT/"short_projection"/f"{tag}.json";r=sweep.read(file)
        assert [list(v) for v in g]==r["groups"] and r["signature"]==signature
        assert r["status"]=="INFEASIBLE" or r["status"]=="OPTIMAL" and r["value"]==r["lower"]==402
        records[tag]=dict(result=file.relative_to(JMS).as_posix(),sha256=sweep.sha(file),status=r["status"],lower=r["lower"])
    assert Counter(r["status"] for r in records.values())=={"INFEASIBLE":23,"OPTIMAL":1}
    lo=OUT/"continuation/low/cap_408.5";hi=OUT/"partitions/1_34_2_d0.25"
    cfg=sweep.Config(**sweep.read(hi/"schedule.json")["config"])
    x=sweep.Integrated(cfg);m=x.model;m.setRealParam("numerics/feastol",1e-8)
    names=[v.name for v in m.getVars(transformed=False) if v.vtype()!="CONTINUOUS"]
    a={k:round(v*4)/4 for k,v in sweep.cell.values(lo/"assignment.json.gz").items()}
    b=sweep.cell.values(hi/"assignment.json.gz");assert all(float(v*4).is_integer() for v in b.values())
    assert all(a.get(k,0)==b.get(k,0) for k in names)
    assert {z.getConshdlrName() for z in m.getConss(transformed=False)}=={"linear"}
    knots=[];n=m.getNConss()
    for i in range(9):
        w=i/8;vals={k:(1-w)*a.get(k,0)+w*b.get(k,0) for k in a.keys()|b.keys()}
        s=sweep.cell.solution(x,vals);assert m.checkSol(s,original=True,completely=True)
        doc=x.result(solution=s);m.freeSol(s);v=fixed.metrics(doc);rep=sweep.validate(doc)
        C=408.5+w/4;D=409-C
        assert rep["valid"] and v["cmax"]==C and v["residence_range"]==D and v["clean_deficit"]==0
        assert v["secondary"]==7-D/4+D**2/2
        dest=OUT/"certified_short"/f"{i:02d}";dest.mkdir(exist_ok=True,parents=True)
        sweep.save(dest/"schedule.json",doc);sweep.save(dest/"assignment.json.gz",sweep.cell.sparse(vals))
        rec=dict(metrics=v,original_rows=n,replay=rep,files={k:sweep.sha(dest/k) for k in ("schedule.json","assignment.json.gz")})
        sweep.atomic(dest/"result.json",rec);knots.append(dict(cap=C,fb=v["secondary"],result=(dest/"result.json").relative_to(JMS).as_posix()))
    m.freeProb()
    proof=dict(interval=[408.5,408.75],left_open=True,formula="D=409-C; V(C)=7-D/4+D^2/2",
        number_layouts=24,structural_coverage="At C<=409 no chamber can contain four 90-second cycles (76+360+40=476). With three terminal wafers one nonterminal product occupies a singleton. The longer chain contains that wafer followed by either one or two terminal products, and all remaining products occupy the one terminal pair on the other chamber. Chamber labels are exchangeable. The choices 4*3 and 4*3 cover the 24 assignments. With four terminal products fB>=7; with one or two terminal products, the 491 s and 425 s lower bounds already exclude the short domain.",
        short_cap=409,primal_score_at_404=7,necessary_residence_window=[6.5,7.5],rationale="In the 3-terminal case, mean>=7-D/4. fB<=7 implies D<=0.5, mean<=7 implies some r<=7, and one terminal r>=7. All residences then lie in [6.5,7.5], all terminal ones are >=7.",
        projection="Each layout retains the product routes, both chambers' front/back load, rotation and unload separations, AL, locks, robot/gripper capacities and paired handling. Dummy-source handling and other rows may be relaxed. Minimize C-r of the single nonterminal product; all infeasible except layout 1_34_2, whose optimum is 402.",
        continuous_proof="The retained durations and each constrained wafer's residence window are integer multiples of 0.5 s. Scale all continuous times by two and take floor(t+u) with a common u uniform on [0,1). The same resource orders, capacities, simultaneity and all integer lags are preserved; interval endpoints and lengths can be reconstructed. Since C is the maximum of translated returns, it rounds the same way. The expectation of C-r is unchanged, hence the discrete optimum lower-bounds the continuous support.",
        range_argument="C>=402+r and D>=7-r give D>=409-C; 7-D/4+D^2/2 is nondecreasing for D>=0.25. The slope reaches zero at C=408.75. At 408.5, an earlier 404-second witness already achieves 7.",
        plateau_before={"interval":[404,408.5],"value":7},verified_knots=knots,native_original_rows=n,fixed_integer_variables=len(names),
        layout_results=records,source_hashes={p.relative_to(JMS).as_posix():sweep.sha(p) for p in (Path(__file__),code,lo/"assignment.json.gz",hi/"assignment.json.gz")})
    sweep.atomic(OUT/"short_certificate.json",proof)
    print(24,"layouts",proof["interval"],n,flush=True)

if __name__=="__main__":main()

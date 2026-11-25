"""Cover every two-terminal-product layout and verify its sharp quadratic branch."""
from math import sqrt
from itertools import product
from pathlib import Path
from probe import OUT,JMS,sweep,fixed

def derive():
    low=OUT/"mid_continuation/split/cap_425"
    high=OUT/"alternate/12_4_3_d0.5"
    target=OUT/"certified_middle"
    cfg=sweep.Config(**sweep.read(high/"schedule.json")["config"])
    x=sweep.Integrated(cfg);m=x.model;m.setRealParam("numerics/feastol",1e-8)
    a={k:round(4*v)/4 for k,v in sweep.cell.values(low/"assignment.json.gz").items()}
    b=sweep.cell.values(high/"assignment.json.gz");assert all(float(v*4).is_integer() for v in b.values())
    integers=[v.name for v in m.getVars(transformed=False) if v.vtype()!="CONTINUOUS"]
    assert all(a.get(k,0)==b.get(k,0) for k in integers)
    n=m.getNConss()
    assert {z.getConshdlrName() for z in m.getConss(transformed=False)}=={"linear"}
    knots=[]
    for j in range(9):
        alpha=j/8
        v={k:(1-alpha)*a.get(k,0)+alpha*b.get(k,0) for k in a.keys()|b.keys()};s=sweep.cell.solution(x,v)
        assert m.checkSol(s,original=True,completely=True)
        doc=x.result(solution=s);m.freeSol(s);q=sweep.validate(doc);z=fixed.metrics(doc)
        c=425+.5*alpha;D=426-c
        assert q["valid"] and z["secondary"]==7-D/2+D**2/2
        assert z["residence_range"]==D and z["cmax"]==c and z["clean_deficit"]==0
        dest=target/f"{j:02d}";dest.mkdir(exist_ok=True,parents=True)
        sweep.save(dest/"schedule.json",doc);sweep.save(dest/"assignment.json.gz",sweep.cell.sparse(v))
        rec=dict(metrics=z,original_rows=n,replay=q,files={k:sweep.sha(dest/k) for k in ("schedule.json","assignment.json.gz")})
        sweep.atomic(dest/"result.json",rec);knots.append(dict(cap=c,fb=z["secondary"],result=(dest/"result.json").relative_to(JMS).as_posix()))
    m.freeProb()
    chains=[p for i in (1,2,3,4) for p in product((1,2),repeat=i) if sum(p)<=4]
    catalogue={tuple(sorted(t)) for count in (1,2) for t in product(chains,repeat=count) if sum(map(sum,t))==4 and sum(c[-1] for c in t)==2}
    proof={
        ((2,2),):"head pair has 2 products. Both must pass the sole aligner, so head load L>=103",
        ((1,1,2),):"four exposure cycles in one chamber, C >= 76+4*90+40=476",
        ((1,),(2,1)):"the two-product head in the longer chain cannot load before 103",
        ((1,),(1,1,1)):"long chain has four exposure cycles, C>=476",
        ((1,1),(1,1)):"the two distinct head products traverse the sole aligner, so at least one head cannot load before 103",
    }
    assert set(proof)==catalogue,catalogue
    early=OUT/"partitions/1_34_2_d0.25/result.json"
    er=sweep.read(early)["metrics"];assert er["secondary"]==6.96875 and er["cmax"]==408.75
    c0=425.5-sqrt(3)/4
    return dict(formula="D=426-C; V(C)=7-D/2+D^2/2",interval=[c0,425.5],left_open=True,transition_expression="425.5-sqrt(3)/4",
        prebranch_plateau=dict(value=6.96875,first_verified=408.75,last=c0),next_plateau=dict(value=6.875,first_verified=425.5,last=491,right_open=True),
        count_argument="With three or more terminal products, mean >= 7-D/4 and fB >= 6.96875. One terminal product requires C>=491. For two terminals mean>=7-D/2.",
        two_terminal_layouts=[dict(chains=t,critical=proof[t]) for t in sorted(catalogue)],
        short_chain_route=["Ld_terminal_dummy >= L_head+182+r_head (head rear unload then new dummy load)",
                           "U_terminal_product >= Ld_terminal_dummy+94 (90s exposure with 1s handling, prior front unload 1s, tail rotation 2s)",
                           "C>=U_terminal_product+40; hence C>=L_head+316+r_head>=419+r_head"],
        resolution="These are necessary real-time inequalities. Therefore D>=7-r_head>=426-C near the transition. The quadratic in D increases for D>=0.5. The other layouts either require C>=476 or share this bound. All auxiliary movements, grippers and pairings are restored at the matching native upper endpoints.",
        original_model_rows=n,fixed_native_integer_variables=len(integers),equal_status_at_switch="an earlier 408.75-second witness attains the switch score; actual tradeoff arc starts strictly after the switch.",
        source_hashes={p.relative_to(JMS).as_posix():sweep.sha(p) for p in (Path(__file__),low/"assignment.json.gz",high/"assignment.json.gz",early)},knots=knots)

if __name__=="__main__":
    out=derive();sweep.atomic(OUT/"middle_certificate.json",out);print(out["interval"],flush=True)

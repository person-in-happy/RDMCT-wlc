"""Exact fixed-integer interpolation and continuous global lower bound for the four-double-wafer tail."""
from itertools import product
from pathlib import Path
from probe import OUT,EX,R,JMS,sweep,fixed
from score import physical_lower

def main():
    low=OUT/"continuation/long/cap_491"
    high=OUT/"long/121/floor_525"
    d=sweep.read(high/"schedule.json")
    cfg=sweep.Config(**d["config"])
    assert cfg.cleaning_interval==10 and list(cfg.chambers)==[2,3] and cfg.dummy_count==8
    assert all(v=={"4x1":0,"2x2":1} for v in cfg.load_ports.values())
    assert (cfg.handling,cfg.atr_handling,cfg.atr_travel,cfg.vtr_travel,cfg.alignment,cfg.rotation,cfg.vent,cfg.pump,cfg.mix_time)==(1,4,3,2,20,2,25,30,90)
    x=sweep.Integrated(cfg);m=x.model;m.setRealParam("numerics/feastol",1e-8)
    variables=m.getVars(transformed=False);nrows=m.getNConss()
    a=sweep.cell.values(low/"assignment.json.gz");b=sweep.cell.values(high/"assignment.json.gz")
    integers=[v.name for v in variables if v.vtype()!="CONTINUOUS"]
    assert all(a.get(k,0)==b.get(k,0) for k in integers)
    assert all(float(4*v).is_integer() for v in [*a.values(),*b.values()])
    constraints=m.getConss(transformed=False)
    types={z.getConshdlrName() for z in constraints}
    assert types=={"linear"},types
    knots=[]
    for j in range(9):
        alpha=j/8
        vals={k:(1-alpha)*a.get(k,0)+alpha*b.get(k,0) for k in a.keys()|b.keys()}
        s=sweep.cell.solution(x,vals);assert m.checkSol(s,original=True,completely=True)
        dd=x.result(solution=s);m.freeSol(s);rep=sweep.validate(dd);z=fixed.metrics(dd)
        C=491+alpha/4;spread=492-C
        assert rep["valid"] and z["residence_range"]==spread and z["cmax"]==C and z["clean_deficit"]==0
        assert z["secondary"]==7-.75*spread+.5*spread**2 and z["mean_residence"]==7-.75*spread
        dest=OUT/"certified_tail"/f"{j:02d}";dest.mkdir(exist_ok=True,parents=True)
        sweep.save(dest/"schedule.json",dd);sweep.save(dest/"assignment.json.gz",sweep.cell.sparse(vals))
        rec=dict(metrics=z,original_rows=nrows,replay=rep,files={k:sweep.sha(dest/k) for k in ("schedule.json","assignment.json.gz")})
        sweep.atomic(dest/"result.json",rec);knots.append(dict(cap=C,fb=z["secondary"],result=str((dest/"result.json").relative_to(JMS))))
    m.freeProb()
    # Each product occupies two consecutive cycles. A product-bearing pair has
    # one or two products, while each productive cycle contains at least one.
    seq=[p for k in range(1,5) for p in product((1,2),repeat=k) if sum(p)==4 and p[-1]==1]
    assert set(seq)=={(1,2,1),(2,1,1),(1,1,1,1)}
    one_load=7+24+7+34+3
    two_load=one_load+28
    output=3+26+7+4
    assert one_load==75 and two_load==103 and output==40
    chamber=1+90+2+1
    assert chamber==94
    # L0,L1,L2 denote product-pair loading-start times; L3 is the final
    # auxiliary front pair. The mid-pair rear unloading time is L1+181+r_mid.
    K=one_load+chamber+182+chamber+output
    assert K==485 and K+6==491
    bounds={"1,2,1":"C >= 485 + r_mid >= 491",
            "2,1,1":"C >= 513 + r_mid >= 519 (second wafer cannot enter the sole aligner before the first leaves)",
            "1,1,1,1":"C >= 76 + 5*90 + 40 = 566 before mandatory chamber changes"}
    signature=[low/"assignment.json.gz", high/"assignment.json.gz",Path(__file__),EX/"square_residence_20261125"/"score.py",
               *(sweep.cell.BACKENDS["D"]/n for n in ("model.py","joint_chamber_cycle_model.py","joint_pairing_model.py","grippers.py"))]
    assert physical_lower(cfg)==6.71875
    a_proof=R/"mixed_controls_20261122/grid_2x2/n4__1pct/A/primary.json"
    ar=sweep.read(a_proof)["record"]
    assert ar["scope"]=="global_product_Cmax" and ar["upper"]==ar["lower"]==404 and ar["gap"]==0
    out=dict(config=cfg.load_ports,H=10,physical_continuous=True,terminal_minimum=7,nonterminal_minimum=6,
        two_or_more_terminal_products={"mean_floor":"7-D/2","objective_floor":6.875},
        exactly_one_terminal_product=dict(requires="all product pairs in one chamber chain ending in one product; dummy-only pairs occupy one cycle",exhaustive_sizes=seq,chain_bounds=bounds),
        assumptions="all displayed lower bounds follow the physical real-time difference inequalities; gripper conflicts, dummy availability and other operations can only add delay; verified upper bounds use every original row",
        route_bounds=dict(single_product_first_load_start=one_load,two_product_first_load_start=two_load,earliest_rear_unload_to_return=output,cycle_change=chamber,
            three_product_pair_chain=["L1>=L0+94","L3>=U2+1=L1+182+r_mid","U3>=L3+94","C>=U3+40"]),
        scope="all original schedules for a continuous cap on [491,491.25]; same global minimum for every larger cap",
        left_competitor_bound="For C<491 only cases with two or more terminal products can beat 7, implying fB>=6.875. The witness at 432.5 already attains 6.875.",
        expression="D=492-C; V(C)=7-3*D/4+D^2/2 for 491<=C<=491.25; V(C)=6.71875 for C>=491.25",
        proof="r_mid<=C-485 and a terminal r>=7 imply D>=492-C. All four satisfy mean>=7-3D/4, so minimize the quadratic over D>=492-C>=0.75. E>=0. The fixed-binary interpolation attains that bound.",
        plateau={"first_verified":425.5,"end":491,"right_open":True,"value":6.875},interval=[491,491.25],minimum=6.71875,
        earliest_minimum=491.25,source_hashes={p.relative_to(JMS).as_posix():sweep.sha(p) for p in [*signature,a_proof]},
        knots=knots,native_rows=nrows,fixed_native_integer_variables=len(integers),native_constraint_types=sorted(types),
        makespan={"proof":str(a_proof.relative_to(JMS)),"primary_archive":{k:ar[k] for k in ("upper","lower","gap")}})
    middle=OUT/"middle_certificate.json"
    out["branch_425"]=sweep.read(middle)
    out["source_hashes"][middle.relative_to(JMS).as_posix()]=sweep.sha(middle)
    out["left_competitor_bound"]="For C<491 the bound fB>=6.875 is universal. The 425.5-second native witness attains it; see branch_425."
    short=OUT/"short_certificate.json"
    out["branch_408"]=sweep.read(short)
    out["source_hashes"][short.relative_to(JMS).as_posix()]=sweep.sha(short)
    switch=out["branch_425"]["interval"][0]
    out["complete_front"]=dict(isolated=[[404,7]],arcs=[
        dict(interval=[408.5,408.75],left_open=True,right_open=False,formula="D=409-C; V=7-D/4+D^2/2"),
        dict(interval=[switch,425.5],left_open=True,right_open=False,formula="D=426-C; V=7-D/2+D^2/2"),
        dict(interval=[491,491.25],left_open=False,right_open=False,formula="D=492-C; V=7-3*D/4+D^2/2")],
        constant_value_intervals=[dict(interval=[404,408.5],V=7),dict(interval=[408.75,switch],V=6.96875),
                                  dict(interval=[425.5,491],right_open=True,V=6.875),dict(interval=[491.25,None],V=6.71875)])
    sweep.atomic(OUT/"pure4_certificate.json",out)
    print(nrows,len(integers),[(k["cap"],k["fb"]) for k in knots],flush=True)

if __name__=="__main__":main()

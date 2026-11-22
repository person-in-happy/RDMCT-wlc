"""Paired, unrestricted epsilon-SCIP subproblems with the pair-count cut off and on."""
import argparse
import gzip
import json
from pathlib import Path
import time

from common import TOL, config, digest, lower_bound, metrics, save
from decoder import Decoder, Retiming
from evaluate import write_csv
from native import Native
from validate import validate


def run(campaign, target, seconds):
    target.mkdir(parents=True,exist_ok=False)
    allrows=[]
    full_start=time.monotonic()
    for case in ("S1","M4"):
        cfg=config(case)
        dec=Decoder(cfg)
        floor=lower_bound(cfg,dec.n,0)
        # The test of one cut uses identical, qualified warm schedules and a new SCIP
        # instance for each query. Preparing the shared inputs is recorded separately.
        build=time.monotonic()
        reference=Native(cfg,1,25)
        split=[]
        try:
            for incoming,outgoing in ((0,0),(0,1),(1,0),(1,1)):
                for chambers in (0,1):
                    genes=tuple(v for i in range(dec.n) for v in (1,i%2 if chambers else i//2%2,incoming,outgoing,0))
                    decoder=Retiming(dec.build(genes,dec.pairing(genes)),25)
                    d=decoder.solve("B",None,4)
                    if d is not None and reference.warm(d):
                        split.append(d)
            prep=time.monotonic()-build
            for seed in (1,2):
                shared=campaign/"shared_initials"/f"{case}_s{seed}.json.gz"
                with gzip.open(shared,"rt",encoding="utf-8") as f:
                    init=json.load(f)
                parents=[]
                for d in [init["constructive"],init["spbs"],*split]:
                    m=metrics(d,25)
                    parents.append(dict(data=d,a=m["cmax"],b=m["secondary"]))
                initial_b=metrics(init["constructive"],25)["secondary"]
                for tag,cap in (("floor",floor),("50N",50*dec.n),("loose",initial_b)):
                    valid=sorted([p for p in parents if p["b"]<=cap+TOL],key=lambda p:(p["a"],p["b"]))[:1]
                    allowed=[p for p in range(dec.n//2+1) if lower_bound(cfg,dec.n,p)<=cap+TOL]
                    for use_cut in ((False,True) if seed==1 else (True,False)):
                        start=time.monotonic()
                        solver=Native(cfg,seed,25)
                        try:
                            setup=time.monotonic()-start
                            deadline=time.monotonic()+seconds
                            found,query=solver.query("A",cap,use_cut,valid,deadline)
                            results=list(valid)
                            for d in found:
                                check=validate(d)
                                metric=metrics(d,25)
                                if check["valid"] and metric["secondary"]<=cap+TOL and reference.warm(d):
                                    results.append(dict(a=metric["cmax"],b=metric["secondary"],data=d))
                            best=min(results,key=lambda r:(r["a"],r["b"])) if results else None
                            allrows.append(dict(case=case,seed=seed,cap_type=tag,B_cap=cap,cut=use_cut,
                                solve_allocation_s=seconds,model_setup_s=setup,common_preparation_s=prep,
                                warm_input_sha256=digest(shared),warm_available=bool(valid),
                                warm_A=valid[0]["a"] if valid else None,warm_B=valid[0]["b"] if valid else None,
                                certified_A=best["a"] if best else None,certified_B=best["b"] if best else None,
                                theoretical_allowed=",".join(map(str,allowed)),excluded_pair_counts=dec.n//2+1-len(allowed) if use_cut else 0,
                                nodes=query["nodes"],dual_A=query.get("dual_bound"),stop=query.get("status"),
                                elapsed_including_setup_and_replay=time.monotonic()-start))
                        finally:
                            solver.close()
                        write_csv(target/"queries.csv",allrows)
                        elapsed=time.monotonic()-full_start
                        print(f"全模型上限子问题 {len(allrows)}/24 | 失败 0 | 预计剩余 "
                              f"{elapsed*(24-len(allrows))/len(allrows):.1f}s",flush=True)
        finally:
            reference.close()
    paired=[]
    for i in range(0,len(allrows),2):
        pair=sorted(allrows[i:i+2],key=lambda r:r["cut"])
        before,after=pair
        if any(before[k]!=after[k] for k in ("case","seed","B_cap","warm_A","warm_B","solve_allocation_s")):
            raise ValueError("Mismatched controls")
        paired.append(dict(case=before["case"],seed=before["seed"],cap_type=before["cap_type"],B_cap=before["B_cap"],
                           excluded_counts=after["excluded_pair_counts"],nodes_off=before["nodes"],nodes_on=after["nodes"],
                           A_off=before["certified_A"],A_on=after["certified_A"],status_off=before["stop"],status_on=after["stop"]))
    write_csv(target/"paired.csv",paired)
    save(target/"summary.json",dict(queries=len(allrows),matched_pairs=len(paired),cut_excluded_a_count=sum(r["excluded_counts"]>0 for r in paired),
         pairs_with_both_warm=sum(r["warm_available"] for r in allrows)//2,
         pairs_improved_conditional_makespan=sum(r["A_on"] is not None and (r["A_off"] is None or r["A_on"]<r["A_off"]-TOL) for r in paired),
         pairs_worse_conditional_makespan=sum(r["A_off"] is not None and (r["A_on"] is None or r["A_off"]<r["A_on"]-TOL) for r in paired),
         solver_wall_limit_excludes_equal_model_build_and_postsolve_replay=True,one_cpu_worker=True,
         elapsed_s=time.monotonic()-full_start))


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("campaign",type=Path)
    p.add_argument("out",type=Path)
    p.add_argument("--seconds",type=float,default=4)
    args=p.parse_args()
    run(args.campaign.resolve(),args.out.resolve(),args.seconds)

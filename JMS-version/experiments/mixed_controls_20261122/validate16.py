"""Uniform 16-wafer retiming tolerance; retain every primary handoff and its budget."""
from pathlib import Path
import sys
import time
from scale import HERE,LARGE,OUT,SCIP,ROOT,POLICIES,cell,execute,product_solve,read,save,sha,validate

BASE=OUT/"ablations_verified"

def worker(seed,arm,suite,folder):
    old=(OUT/suite)/f"s{seed}__{arm}"
    plain=suite=="raw_policies" or arm=="plain_full"
    primary=[old/"A"] if suite=="raw_policies" else ([old/"A1",old/"A2"] if arm=="fixed_free" else [old/"A1"])
    seconds=([60,150] if arm=="fixed_free" else [270 if plain else 210])
    stages=[(read(src/"primary.json")["record"],sec) for src,sec in zip(primary,seconds)]
    src=primary[-1]
    settings=cell.scip_settings
    def strict_settings(model,task,path):
        settings(model,task,path)
        model.setRealParam("numerics/feastol",1e-8)
    cell.scip_settings=strict_settings
    e=product_solve(folder/"B",src/"schedule.json",src/"assignment.json.gz","D",16,seed,"fixed",30)
    native_source=read(LARGE/f"s{seed}"/"source.json")
    archived=read(ROOT/native_source["archive"])["constructive"]
    final=read(folder/"B/runs/endpoint/schedule.json")
    final["config"]=archived["config"]
    physical=validate(final)
    assert physical["valid"]
    ok=e["eligible"] and all(r["status"] not in ("memlimit","unknown","userinterrupt") and r["seconds"]<=b+1 for r,b in stages)
    raw=LARGE/f"s{seed}"/"raw";prep=LARGE/f"s{seed}"/"prepared"
    save(folder/"result.json",dict(seed=seed,arm=("plain_"+arm if suite=="raw_policies" else arm),
         initial=sha(raw/"assignment.json.gz"),start=sha((raw if plain else prep)/"assignment.json.gz"),
         primary_source=str(src.relative_to(ROOT)),stages=stages,secondary=e["record"],metrics=e["measured"],
         physical_replay=physical,eligible=ok,feasibility_tolerance=1e-8))

if __name__=="__main__":
    if len(sys.argv)>1:
        seed,arm,suite,path=sys.argv[1:];worker(int(seed),arm,suite,Path(path))
    else:
        while any(read((OUT/s)/"progress.json")["remaining"] for s in ("mixed16","raw_policies")):time.sleep(6)
        jobs=[]
        for suite,arms in (("mixed16",POLICIES),("raw_policies",("default","hem_spbs","feature_only","no_rerank","greedy"))):
            for seed in (1,2,3):
                for arm in arms:
                    key=("plain_"+arm if suite=="raw_policies" else arm)
                    folder=str(BASE/f"s{seed}__{key}")
                    jobs.append((SCIP,__file__,[str(seed),arm,suite,folder],folder))
        sys.exit(execute(jobs,3,BASE))

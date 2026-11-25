"""Create the common SPBS schedule. Unused pair and cycle slots are fixed in all five neighborhoods."""
import sys
import time
from dataclasses import asdict, replace
from common16 import HERE, OUT, load, save, sha, setup, config

def main(recipe):
    cell=setup()
    from model import Integrated
    from decoder import Decoder, Retiming
    from seed import normalize_schedule
    from validate import validate
    from witness import sparse_witness
    from joint_algorithms import improve_skeleton
    from protocol import save as native_save
    cfg=config(recipe)
    root=OUT/recipe
    raw=root/"raw/schedule.json"
    if not raw.exists():
        dec=Decoder(cfg)
        genes=tuple(v for i in range(dec.n) for v in (0,i//2%2,0,0,0))
        dat=Retiming(dec.build(genes,dec.pairing(genes)),25).solve("A",None,5)
        dat=normalize_schedule(cfg,dat)
        assert validate(dat)["valid"]
        save(raw,dat)
    data=load(raw)
    compact=replace(cfg,max_pairs=max(16,max(p["id"] for p in data["pairs"])+1),
        max_cycles=max(c["index"] for c in data["cycles"])+1)
    dst=root/"prepared"
    final=dst/"primary.json"
    if final.exists():
        r=load(final)
        assert r["source_sha256"]==sha(raw) and r["schedule_sha256"]==sha(dst/"schedule.json")
        return
    if not (dst/"compact.json").exists():
        x=Integrated(compact)
        cell.scip_settings(x.model,dict(n=16,seed=1,seconds=60),dst)
        vals=sparse_witness(compact,normalize_schedule(compact,data))
        sol=cell.attach(x,vals)
        x.model.freeSol(sol)
        vals={v.name:vals.get(v.name,0) for v in x.model.getVars(transformed=False)}
        new,logs=improve_skeleton(x,vals,60)
        sol=cell.attach(x,new)
        sched=x.result(solution=sol)
        x.model.freeSol(sol)
        x.model.freeProb()
        data=normalize_schedule(cfg,sched)
        assert validate(data)["valid"]
        save(dst/"compact.json",dict(schedule=data,stages=logs))
    rec=load(dst/"compact.json")
    data=rec["schedule"]
    checked=cell.lift(cfg,sparse_witness(cfg,data),None,rebuild=True)
    if not checked: raise ValueError("Full model rejected prepared schedule")
    sched,vals,_,replay,rows=checked
    assert replay["valid"]
    native_save(dst/"schedule.json",sched)
    native_save(dst/"assignment.json.gz",vals)
    save(final,dict(cmax=max(w["loan_end"] for w in sched["jobs"] if w["product"]),rows=rows,
        schedule_sha256=sha(dst/"schedule.json"),assignment_sha256=sha(dst/"assignment.json.gz"),
        replay=replay,source_sha256=sha(raw),stages=rec["stages"]))

if __name__=="__main__":
    main(sys.argv[1])

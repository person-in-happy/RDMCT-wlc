"""Optimize actual transport orders near checked incumbents in the original SCIP model."""
import argparse
import itertools
import msvcrt
import os
import time
from pathlib import Path
from native_caps import CASES,OUT,SQ,OLD,HERE,fixed
from support import read,write,digest

sweep=fixed.sweep
JOBS={
    "paired":(CASES["return981"][0],38,[979,967,955,935,915,895,875,985,1005,1035]),
    "blocks":(CASES["blocks"][0],80,[1140,1110,1080,1050,1030,1010,990,970,950]),
    "fast":(CASES["p823"][0],56,[850,880,910,940,830,825,820,815,813,812]),
}


def neighborhood(name,budget):
    source,radius,caps=JOBS[name]
    home=OUT/"neighbors"/name;home.mkdir(parents=True,exist_ok=True)
    identity={str(p):digest(p) for p in [Path(__file__),source/"assignment.json.gz",source/"schedule.json",
                                             Path(sweep.__file__),HERE.parent/"square_residence_20261125/solver.py"]}
    tag=home/"identity.json"
    if tag.exists():assert read(tag)==identity
    else:write(tag,identity)
    doc=read(source/"schedule.json");cfg=sweep.Config(**doc["config"])
    pending=[]
    for cap in caps:
        dest=home/f"cap_{cap}";dest.mkdir(exist_ok=True)
        p=dest/"result.json"
        if p.exists():
            rec=read(p)
            assert all(digest(dest/k)==h for k,h in rec.get("files",{}).items())
            continue
        pending.append((cap,dest))
    if not pending:return
    x=sweep.Integrated(cfg);model=x.model
    native=model.getVars(transformed=False);original=model.getNConss()
    vals=sweep.cell.values(source/"assignment.json.gz")
    seed=sweep.cell.attach(x,vals);model.freeSol(seed)
    sweep.cell.scip_settings(model,dict(seed=4,n=16,seconds=budget,gap=0),home)
    model.setRealParam("numerics/feastol",1e-8)
    events=[e for e in doc["events"] if e.get("robot") in ("ATR","VTR")]
    free=set()
    for a,b in itertools.combinations(events,2):
        if a["robot"]!=b["robot"] or abs(a["start"]-b["start"])>radius:continue
        for i,j in ((a,b),(b,a)):
            free.add(f"order_{i['name']}_{j['name']}")
            if a["location"]==b["location"] and a["kind"]==b["kind"]:
                free.add(f"sync_{i['name']}_{j['name']}")
    released=set()
    for var in native:
        if var.vtype()=="CONTINUOUS":continue
        if var.name in free:
            released.add(var.name);continue
        val=round(vals.get(var.name,0));model.chgVarLb(var,val);model.chgVarUb(var,val)
    assert len(released)>8
    objective,extras=fixed.objective_terms(x,vals,True)
    model.setObjective(objective,"minimize")
    first=dict(vals,**extras)
    ref=sweep.cell.solution(x,first)
    assert model.checkSol(ref,original=True,completely=True,printreason=True)
    model.addSol(ref,free=True)
    elapsed_start=time.monotonic()
    for i,(cap,dest) in enumerate(pending):
        spent=time.monotonic()-elapsed_start
        eta=(len(pending)-i)*(budget+1 if i==0 else spent/i)
        q=dict(stage=name,cap=cap,total=len(caps),completed=len(caps)-len(pending)+i,failed=0,
               pid=os.getpid(),elapsed=spent,eta_total=spent+eta,eta_remaining=eta,
               estimate="one original-model SCIP worker with active transport orders; measured time after first cap")
        print(q,flush=True);write(home/"progress.json",q)
        # Each cap is a separate fixed-budget cell. SCIP's solve clock resets with freeTransform.
        model.chgVarUb(x.cmax,cap);clock=time.monotonic();model.optimize()
        sol=model.getBestSol();status=str(model.getStatus())
        result=dict(status=status,scope="selected original robot order neighborhood",source_schedule=str(source/"schedule.json"),
                    radius=radius,freed_discrete=len(released),cap=cap,original_rows=original,lower=model.getDualbound(),
                    seconds_budget=budget,seconds_used=time.monotonic()-clock)
        if sol:
            saved,assignment,z,replay=sweep.schedule_checks(x,cfg,native,sol)
            assert z["cmax"]<=cap+2e-5 and abs(z["secondary"]-model.getPrimalbound())<3e-5
            recovered=assignment.get("nonzero",assignment.get("values",assignment))
            changes=sum(round(recovered.get(k,0))!=round(vals.get(k,0)) for k in released)
            sweep.save(dest/"schedule.json",saved);sweep.save(dest/"assignment.json.gz",assignment)
            result.update(metrics=z,checks=replay["checks"],order_changes=changes,files={k:digest(dest/k) for k in ("schedule.json","assignment.json.gz")})
        write(dest/"result.json",result);model.freeTransform()
    q.update(completed=len(caps),elapsed=time.monotonic()-elapsed_start,eta_remaining=0);q["eta_total"]=q["elapsed"]
    write(home/"progress.json",q);model.freeProb()


if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("case",choices=[*JOBS,"all"]);p.add_argument("--seconds",type=int,default=12)
    o=p.parse_args();OUT.mkdir(exist_ok=True,parents=True)
    for name in JOBS if o.case=="all" else [o.case]:
        with (OUT/f"neighbors_{name}.lock").open("a+b") as lock:
            try:msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
            except OSError:print("Active worker already running.",flush=True);continue
            neighborhood(name,o.seconds)

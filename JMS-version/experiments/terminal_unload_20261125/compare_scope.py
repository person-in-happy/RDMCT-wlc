"""At an unchanged return cap, compare timing, resource reordering and repairing.

All arms use the same verified start, candidate domain, one SCIP thread and
40 solver seconds. Re-run to resume by endpoint with the remaining time budget.
"""
from dataclasses import replace
import hashlib
import json
import msvcrt
from pathlib import Path
import sys
import time

from extended_model import Config, Integrated, JMS
from seed import constrain_seed, release_fixed, normalize_schedule
from validate import validate
sys.path.insert(0,str(JMS/"experiments/square_residence_20261125"))
from score import metrics

SOURCES = {"two": "results/huber_residence_20261125/runs/t4_1_2_3_1_fixed/B/schedule.json",
           "four":"results/pareto_scales_20261125/four_native_H3/short397/schedule.json"}
OUT = JMS/"results/terminal_unload_20261125/scope"
LIMIT = 40


def write(path, data):
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(data,indent=2,allow_nan=False),encoding="utf8")
    temp.replace(path)


def run(name, source, scope, folder, duration):
    data = json.loads(source.read_text(encoding="utf8"))
    cfg = Config(**data["config"])
    data = normalize_schedule(cfg,data)
    cfg = replace(cfg,max_pairs=max(p["id"] for p in data["pairs"])+1,
                  max_cycles=max(c["index"] for c in data["cycles"])+1)
    start=time.perf_counter()
    x=Integrated(cfg)
    m=x.model
    m.setIntParam("parallel/maxnthreads",1)
    m.setRealParam("numerics/feastol",1e-8)
    cap=metrics(data)["cmax"]
    m.addCons(x.cmax<=cap+1e-6)
    x.minimize_process_score()
    # Construct the common start by satisfying the exact archived event times.
    fixed=constrain_seed(x,data,times=True)
    for bit in x.product_first.values():
        m.chgVarUb(bit,0)
    m.optimize()
    if m.getNSols()==0:
        raise RuntimeError("Unable to lift the archived input schedule")
    best=m.getBestSol()
    warm={v.name:m.getSolVal(best,v) for v in m.getVars(transformed=False)}
    m.freeTransform()
    release_fixed(m,fixed)
    for bit in x.product_first.values():
        m.chgVarUb(bit,1)
    if scope=="timing":
        for v in m.getVars(transformed=False):
            if v.vtype() != "CONTINUOUS" and not v.name.startswith("sync_"):
                value=round(warm[v.name])
                m.chgVarLb(v,value)
                m.chgVarUb(v,value)
    if scope=="order":
        constrain_seed(x,data,times=False)
    # This inequality uses the allowed product-first operation.
    n=sum(sum(row.values()) for row in cfg.load_ports.values())
    mix=sum(row.get("2x2",0) for row in cfg.load_ports.values())
    lb=(2*cfg.handling+2*cfg.rotation)*mix/n
    objective=m.getObjective()
    m.addCons(objective>=lb)
    sol=m.createSol()
    for v in m.getVars(transformed=False):
        m.setSolVal(sol,v,warm[v.name])
    if not m.checkSol(sol,original=True,completely=True):
        raise ValueError("Starting point changed between arms")
    m.addSol(sol)
    prepared=time.perf_counter()-start
    m.setRealParam("limits/time",duration)
    m.optimize()
    best=m.getBestSol()
    schedule=x.result(solution=best)
    replay=validate(schedule)
    observed=metrics(schedule)
    if not replay["valid"] or observed["cmax"]>cap+.0002 or abs(m.getSolObjVal(best)-observed["secondary"])>.0002:
        raise ValueError(("Event and solver outputs disagree",replay["errors"][:3],observed))
    write(folder/"schedule.json",schedule)
    return dict(case=name,scope=scope,candidate_pairs=x.P,cycles_per_chamber=x.Q,cap=cap,
                before=metrics(data),after=observed,domain_lower=max(lb,m.getDualbound()),
                status=str(m.getStatus()),preparation_s=prepared,solver_s=m.getSolvingTime(),
                replay_checks=replay["checks"],rows=m.getNConss(transformed=False),
                priority=sum(m.getSolVal(best,b)>.5 for b in x.product_first.values()))


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    lock=(OUT/"controller.lock").open("a+b")
    try:
        msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
    except OSError:
        print("The foreground queue is already running.",flush=True)
        return
    results=[]
    started=time.time()
    for name,relative in SOURCES.items():
        source=JMS/relative
        for scope in ("timing","order","free"):
            folder=OUT/(name+"_"+scope)
            folder.mkdir(exist_ok=True)
            checkpoint=folder/"record.json"
            digest=lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
            identity=[digest(source),digest(Path(__file__)),digest(Path(__file__).with_name("extended_model.py"))]
            if checkpoint.exists():
                row=json.loads(checkpoint.read_text())
                if identity!=row["identity"] or digest(folder/"schedule.json")!=row["schedule_sha256"]:
                    raise ValueError("Input or endpoint has changed")
            else:
                clock=folder/"attempt.json"
                spent=0.
                if clock.exists():
                    previous=json.loads(clock.read_text())
                    if previous["identity"]!=identity:
                        raise ValueError("Attempt input changed")
                    # A stopped native solve cannot restore its search tree.
                    # Charge at most its reserved time. A spent cell can always
                    # deliver its original verified input and physical bound.
                    spent=min(LIMIT,previous["spent"]+max(0,time.time()-previous["start"]))
                elapsed=time.time()-started
                remaining=(6-len(results))*LIMIT-spent
                state=dict(completed=len(results),failed=0,elapsed_s=elapsed,remaining_s=remaining,
                           estimated_total_s=elapsed+remaining,basis="remaining sequential solver budgets plus model preparation",
                           active=name+"_"+scope)
                print(state,flush=True)
                write(OUT/"status.json",state)
                write(clock,dict(spent=spent,start=time.time(),identity=identity))
                try:
                    row=run(name,source,scope,folder,max(.001,LIMIT-spent))
                except Exception as exc:
                    write(OUT/"status.json",dict(state,failed=1,error=str(exc)))
                    raise
                row.update(identity=identity,schedule_sha256=digest(folder/"schedule.json"))
                write(checkpoint,row)
            results.append(row)
    write(OUT/"summary.json",results)
    write(OUT/"status.json",dict(completed=6,failed=0,elapsed_s=time.time()-started,
                                 estimated_total_s=time.time()-started,remaining_s=0))
    lock.close()


if __name__=="__main__":
    main()

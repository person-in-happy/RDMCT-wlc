"""Epsilon-constraint runs on archived original-model structures, retaining each native solution."""
import argparse
import json
import os
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
JMS = HERE.parents[1]
R = JMS / "results"
OUT = R / "pareto_scales_20261125"
sys.path.insert(0, str(HERE.parent / "huber_residence_20261125"))
from solver import cell, objective_terms, read, save, sha
from score import metrics

sys.path.insert(0, str(cell.BACKENDS["D"]))
from model import Config, Integrated
from validate import validate

MIX = R / "table3_mixed16_20261125"
HUB = R / "huber_residence_20261125"
CASES = {
    "four_slow": (HUB / "witnesses_tight/D_n4_H10_mixed_dual", [397,400,408,416,424,432,440,448,456,465]),
    "sixteen_810": (MIX / "grid/0p01pct/0p01pct", [810,811,812,814,817,821,826,834,850,870,910,1100]),
    "sixteen_817": (MIX / "grid/1pct/0p01pct", [810,812,817,821,826,834,850,870,910,1100]),
}


def atomic(path, value):
    p = path.with_suffix(f".{os.getpid()}.tmp")
    p.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf8")
    os.replace(p, path)


def schedule_checks(x, cfg, native, sol):
    m = x.model
    assert m.checkSol(sol, original=True, completely=True)
    values = {v.name: m.getSolVal(sol,v) for v in native}
    doc = x.result(solution=sol)
    score = metrics(doc)
    replay = validate(doc)
    assert replay["valid"] and abs(replay["product_return_cmax"]-score["cmax"])<1e-5
    values[x.cmax.name] = score["cmax"]
    return doc, cell.sparse(values), score, replay


def run(name, stop_after=None):
    source, caps = CASES[name]
    out = OUT / name
    out.mkdir(exist_ok=True, parents=True)
    cfg = Config(**read(source/"schedule.json")["config"])
    sig = {k:sha(source/k) for k in ("schedule.json","assignment.json.gz")}
    sig["implementation"] = sha(Path(__file__))
    work = []
    for cap in caps:
        dest = out / f"cap_{cap}"
        dest.mkdir(exist_ok=True)
        checkpoint = dest/"result.json"
        if checkpoint.exists():
            previous=read(checkpoint)
            assert previous["signature"] == sig
            assert all(sha(dest/k)==v for k,v in previous.get("files",{}).items())
        else:
            work.append((cap,dest))
    if not work:
        return
    t = time.monotonic()
    previous = read(out/"progress.json")["elapsed"] if (out/"progress.json").exists() else 0
    def progress(cap, done):
        elapsed = time.monotonic()-t
        completed = len(caps)-len(work)+done
        per_cell = elapsed/done if done else (9 if cfg.horizon>20000 and "sixteen" in name else 2)
        remaining = (len(work)-done)*per_cell
        record = dict(case=name,cap=cap,completed=completed,failed=0,total=len(caps),elapsed=round(previous+elapsed,1),
                      eta_remaining=round(remaining,1),eta_total=round(previous+elapsed+remaining,1),pid=os.getpid(),
                      basis="current serial cell mean" if done else "historical fixed-structure SCIP, shared native model",
                      recovery="original-model verified cap files; interrupted current cap restarts")
        atomic(out/"progress.json",record)
        print(record,flush=True)
    progress(work[0][0],0)
    x = Integrated(cfg)
    m = x.model
    orig = m.getNConss()
    vs = cell.values(source/"assignment.json.gz")
    native = list(m.getVars(transformed=False))
    cell.scip_settings(m,dict(n=x.N,seed=1,seconds=50,gap=0),out)
    m.setRealParam("numerics/feastol",1e-8)
    if any(abs(t-round(t))<1.1e-6 and t!=round(t) for t in vs.values()):
        vs = {k:round(v) if abs(v-round(v))<1.1e-6 else v for k,v in vs.items()}
    start = cell.attach(x,vs)
    m.freeSol(start)
    for v in native:
        if v.vtype()!="CONTINUOUS":
            val = round(vs.get(v.name,0))
            m.chgVarLb(v,val)
            m.chgVarUb(v,val)
    obj,extra = objective_terms(x,vs,True)
    m.setObjective(obj,"minimize")
    for index,(cap,dest) in enumerate(work,1):
        timer=time.monotonic()
        m.chgVarUb(x.cmax,cap)
        m.optimize()
        status = str(m.getStatus())
        lower = m.getDualbound()
        result=dict(signature=sig,cap=cap,scope="one fixed original-model integer assignment",status=status,
                    lower=lower,original_rows=orig)
        sol=m.getBestSol()
        if sol is not None:
            doc,assignment,score,replay=schedule_checks(x,cfg,native,sol)
            assert score["cmax"]<=cap+2e-6 and abs(score["secondary"]-m.getPrimalbound())<3e-5
            save(dest/"schedule.json",doc)
            save(dest/"assignment.json.gz",assignment)
            result.update(metrics=score,checks=replay["checks"],files={k:sha(dest/k) for k in ("schedule.json","assignment.json.gz")})
        else:
            assert status=="infeasible",status
        result["wall_seconds"]=time.monotonic()-timer
        atomic(dest/"result.json",result)
        m.freeTransform()
        progress(cap,index)
        if stop_after and index==stop_after:
            break
    m.freeProb()


if __name__=="__main__":
    import msvcrt
    p=argparse.ArgumentParser()
    p.add_argument("name", choices=list(CASES))
    p.add_argument("--stop-after", type=int)
    a=p.parse_args()
    dest=OUT/a.name
    dest.mkdir(exist_ok=True,parents=True)
    with (dest/"worker.lock").open("a+b") as lock:
        lock.seek(0)
        try:
            msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
        except OSError:
            print("Existing foreground worker owns this case.",flush=True)
        else:
            run(a.name,a.stop_after)

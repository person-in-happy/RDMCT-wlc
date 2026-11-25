"""Native epsilon-constraint retiming on independent 4-wafer configurations."""
import argparse
from copy import deepcopy
from dataclasses import asdict,replace
from pathlib import Path
import sys
import time
import msvcrt
HERE=Path(__file__).resolve().parent
EX=HERE.parent
JMS=EX.parent
R=JMS/"results"
OUT=R/HERE.name
sys.path.insert(0,str(EX/"pareto_square_20261125"))
import fixed
sweep=fixed.sweep
sys.path.insert(0,str(EX/"pareto_rl_dmct_20261119"))
from witness import sparse_witness
from pjobs import products_from_load_ports

CONFIGS={"separated":(1,2,3,4),"mixed_ports":(1,2,1,2),"one_port":(1,1,1,1),
         "two_recipe_ports":(1,1,2,2),"three_ports":(1,1,2,3),"double_only":None}
MIXSOURCES={"short":R/"pareto_scales_20261125/four_native_H10/short397",
            "long":R/"pareto_scales_20261125/four_native_H10/417_pinned",
            "A406":R/"mixed_controls_20261122/grid4/mixed__10pct/A"}
PURESOURCES={k:R/f"mixed_controls_20261122/grid_2x2/n4__{g}/A" for k,g in (("A404","1pct"),("A427","10pct"))}

def prepare(case,variant,source):
    input_path=source/"schedule.json"
    out=OUT/"sources"/case/variant
    out.mkdir(exist_ok=True,parents=True)
    flag=out/"result.json"
    sig={str(p.relative_to(JMS)):sweep.sha(p) for p in (Path(__file__),input_path,EX/"pareto_rl_dmct_20261119/witness.py",EX/"square_residence_20261125/score.py")}
    if flag.exists():
        record=sweep.read(flag)
        assert record["signature"]==sig
        for k,v in record.get("files",{}).items():assert sweep.sha(out/k)==v
        return out if record["valid"] else None
    doc=sweep.read(input_path);cfg=sweep.Config(**doc["config"])
    if case not in ("separated","double_only"):
        ports=CONFIGS[case]
        hist={f"LP{i}":{"4x1":0,"2x2":0} for i in range(1,5)}
        for v,recipe in zip(ports,("4x1","4x1","2x2","2x2")):hist[f"LP{v}"][recipe]+=1
        wp=products_from_load_ports(hist)
        tasks=deepcopy(cfg.pjobs);mapping={}
        for task in tasks:
            labels=[w.identifier for w in wp if w.mode==task["mode"]]
            mapping.update(zip(task["wafers"],labels));task["wafers"]=labels
        cfg=replace(cfg,pjobs=tasks,load_ports=hist)
        doc["config"]=asdict(cfg)
        for pair in doc["pairs"]:pair["members"]=[mapping.get(w,w) for w in pair["members"]]
        for job in doc["jobs"]:
            if job["product"]:
                job["identity"]=mapping[job["identity"]]
                job["origin"]=job["identity"].split("_")[0];job["load_port"]=int(job["origin"][2:])
                for ev in doc["events"]:
                    if ev.get("job")==job["name"] and ev["kind"] in ("origin_pick","origin_put"):ev["location"]=job["origin"]
        # Native groups are port-specific and therefore need a fresh sparse assignment.
        values=sparse_witness(cfg,doc)
    else:values=sweep.cell.values(source/"assignment.json.gz")
    values={k:round(v) if abs(v-round(v))<1.1e-6 else v for k,v in values.items()}
    result=sweep.cell.lift(cfg,values,None,rebuild=True)
    if result is None:
        sweep.atomic(flag,dict(signature=sig,valid=False,reason="native original-row replay rejected remapped handoff"))
        return None
    d,a,_,rep,n=result
    assert rep["valid"];sweep.save(out/"schedule.json",d);sweep.save(out/"assignment.json.gz",a)
    sweep.atomic(flag,dict(signature=sig,valid=True,configuration=asdict(cfg),original_rows=n,
        replay=rep,metrics=fixed.metrics(d),source=str(input_path.relative_to(JMS)),
        files={k:sweep.sha(out/k) for k in ("assignment.json.gz","schedule.json")}))
    return out


def run(case,stop):
    out=OUT/"cells"/case;out.mkdir(parents=True,exist_ok=True)
    sweep.OUT=out
    if case=="double_only":
        sources=PURESOURCES
        caps=[404,404.25,404.5,405,406,407,408,410,412,414,417,422,427,438,460]
    else:
        sources=MIXSOURCES
        caps=[380,385,390,393,395,396,397,398,400,404,408,412,415,416,417,418,424,435]
    print(f"{case}: {len(sources)} native configurations x {len(caps)} makespan caps; ETA 8–40s (historical four-wafer native timing).",flush=True)
    for tag,source in sources.items():
        handoff=prepare(case,tag,source)
        if handoff:
            sweep.CASES={tag:(handoff,caps)}
            with (out/(tag+".lock")).open("a+b") as lock:
                try:msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
                except OSError:continue
                sweep.run(tag,stop)
        if stop:break


if __name__=="__main__":
    cli=argparse.ArgumentParser();cli.add_argument("case",choices=[*CONFIGS,"all"]);cli.add_argument("--stop-after",type=int)
    a=cli.parse_args()
    for case in (CONFIGS if a.case=="all" else (a.case,)):run(case,a.stop_after)

"""Check multiple dyadic assignments against the unmodified, complete row generator, lane by lane."""
from collections import Counter
from contextlib import ExitStack
from types import SimpleNamespace
from unittest.mock import patch
import sys
import time
from pathlib import Path
from case_setup import CASES, OUT, OLD, Config, digest, load_schedule, metrics, read, save, signature, validate
from large75 import PATTERNS, GRID
from witness import sparse_witness
import numpy as np
sys.path.append(str(PATTERNS/"audit"))
import check_model as ck
from paired import execute, jobs, log

DEST=OUT/"audits"
PACK=12
AUDIT_WORKERS=4


class VectorRows:
    def __init__(self,assignments):
        self.width=len(assignments)
        self.types=Counter()
        self.rows=0
        self.values={}
        for name in set().union(*(a.keys() for a in assignments)):
            v=[float(a.get(name,0)) for a in assignments]
            self.values[name]=v[0] if all(t==v[0] for t in v) else np.asarray(v,dtype=np.float64)
        self.cmax=np.array([a["Cmax"] for a in assignments])

    def hideOutput(self):
        pass

    def addVar(self,name,vtype="C",lb=0,ub=None):
        self.types[vtype]+=1
        v=self.values.get(name,0)
        ub=1 if vtype=="B" else ub
        if isinstance(v,np.ndarray):
            if (v<lb).any() or (ub is not None and (v>ub).any()) or (vtype in ("I","B") and (v!=v.round()).any()):
                raise ValueError("Variable domain: "+name)
            return v
        if v<lb or (ub is not None and v>ub) or (vtype in ("I","B") and v!=int(v)):
            raise ValueError("Variable domain: "+name)
        # Preserve object identity of *named* variables even for zero-valued entries.
        return ck.Number(v)

    def addCons(self,satisfied,name=None):
        self.rows+=1
        if satisfied is True:
            return
        if isinstance(satisfied,np.ndarray):
            if satisfied.shape==(self.width,) and bool(satisfied.all()):
                return
            bad=np.flatnonzero(~satisfied).tolist()
        elif bool(satisfied):
            return
        else:
            bad=list(range(self.width))
        raise ValueError(f"Original row {self.rows} rejected lanes {bad}")

    def setObjective(self,value,sense):
        assert sense=="minimize" and np.array_equal(np.broadcast_to(value,(self.width,)),self.cmax)
        raise ck.RowsComplete


def generate(cfg,rows):
    assert not cfg.max_pairs and not cfg.max_cycles
    instance=ck.model.Integrated.__new__(ck.model.Integrated)
    with ExitStack() as stack:
        api=SimpleNamespace(Model=lambda name:rows,quicksum=sum)
        for module in (ck.model,ck.joint_pairing_model,ck.joint_chamber_cycle_model):
            stack.enter_context(patch.object(module,"scip",api))
        try:
            instance.__init__(cfg)
        except ck.RowsComplete:
            quality=instance.secondary_objective
        else:
            raise RuntimeError("The original model did not finish emitting rows")
    return (rows.rows,dict(rows.types)),quality


def physical(case,path):
    data=load_schedule(path)
    cfg=Config(**data["config"])
    info=read(OUT/"shared"/(case+".json"))
    assert cfg==Config(**info["config"]) and signature(data)==path.name.split(".")[0]
    inventory=[j["identity"] for j in data["jobs"] if j["product"]]
    assert len(inventory)==75 and sorted(inventory)==sorted(w for j in cfg.pjobs for w in j["wafers"])
    assert validate(data)["valid"]
    m=metrics(data,25)
    values=sparse_witness(cfg,data)
    assert all(v*GRID==round(v*GRID) for v in values.values())
    assert m["cmax"]==values["Cmax"]
    return cfg,values,m


def parity(case):
    info=read(OUT/"shared"/(case+".json"))
    cfg,values,m=physical(case,OUT/"shared"/info["file"])
    dim,quality=generate(cfg,ck.RowCheck(values))
    assert quality==m["secondary"]
    if case=="mix37":
        assert dim[0]==24271470 and sum(dim[1].values())==6764011
    # Two distinct positive schedules and an injected error confined to lane 1.
    others=[OUT/case/f"{method}_{seed}"/"run.json" for _,method,seed in jobs() if (OUT/case/f"{method}_{seed}"/"run.json").is_file()]
    example=None
    for path in others:
        example=next((path.parent/r["file"] for r in read(path)["archive"] if r["sig"]!=info["sig"]),None)
        if example:
            break
    if not example:
        raise RuntimeError("No second feasible timetable available for positive parity check")
    _,other,om=physical(case,example)
    dim2,other_q=generate(cfg,ck.RowCheck(other))
    many_dim,many_q=generate(cfg,VectorRows([values,other]))
    assert dim==dim2==many_dim and np.array_equal(many_q,[quality,other_q]) and other_q==om["secondary"]
    try:
        generate(cfg,VectorRows([values,{**other,"Cmax":0}]))
    except ValueError as e:
        assert "rejected lanes [1]" in str(e),str(e)
    else:
        raise RuntimeError("One invalid witness accepted")
    save(DEST/(case+"_dimensions.json"),dict(case=case,rows=dim[0],types=dim[1],variables=sum(dim[1].values()),
         scalar_vector_positive_match=True,corrupt_single_lane_rejected=True,reference=info["sig"],other=example.name))


def verify_pack(job):
    case,paths=job
    started=time.monotonic()
    assignments=[]
    summary=[]
    for name in paths:
        path=Path(name)
        cfg,values,actual=physical(case,path)
        assignments.append(values)
        summary.append(dict(sig=path.name.split(".")[0],case=case,metrics=actual))
    (rows,types),quality=generate(cfg,VectorRows(assignments))
    expected=read(DEST/(case+"_dimensions.json"))
    assert rows==expected["rows"] and types==expected["types"]
    computed=np.broadcast_to(quality,(len(paths),))
    assert np.array_equal(computed,[r["metrics"]["secondary"] for r in summary])
    for i,r in enumerate(summary):
        r.update(rows=rows,variables=sum(types.values()),original_A=assignments[i]["Cmax"],original_B=float(computed[i]),
                 physical=True,pack=len(paths),pack_seconds=time.monotonic()-started)
    return summary


def checkpoint(job,records):
    for r in records:
        save(DEST/(r["sig"]+".json"),r)


def main(phase):
    DEST.mkdir(parents=True,exist_ok=True)
    if phase=="parity":
        for c in CASES:
            if not (DEST/(c+"_dimensions.json")).exists():
                log("Checking original scalar and vector validators: "+c)
                parity(c)
        log("Both scalar/vector checks passed")
        return
    assert (OUT/"finished.json").exists()
    pending=[]
    total=0
    for c in CASES:
        assert (DEST/(c+"_dimensions.json")).exists()
        schedules={}
        for case,m,s in jobs():
            if c!=case:
                continue
            folder=OUT/c/f"{m}_{s}"
            for r in read(folder/"run.json")["archive"]:
                schedules.setdefault(r["sig"],(tuple(r["genes"]),str(folder/r["file"])))
        total+=len(schedules)
        candidates=[path for sig,(g,path) in sorted(schedules.items(),key=lambda v:(v[1][0],v[0]))
                    if not (DEST/(sig+".json")).exists()]
        pending.extend((c,candidates[i:i+PACK]) for i in range(0,len(candidates),PACK))
    log(f"Original-row validation: {total} distinct internal schedules; {len(pending)} packs, up to {PACK} witnesses per pack, {AUDIT_WORKERS} one-thread workers")
    execute("full original rows",pending,verify_pack,checkpoint,AUDIT_WORKERS,65)
    save(DEST/"complete.json",dict(distinct=total,batch_width=PACK,workers=AUDIT_WORKERS))
    log(f"FULL ORIGINAL ROWS PASS: {total} distinct schedules")


if __name__=="__main__":
    main(sys.argv[1] if len(sys.argv)>1 else "all")

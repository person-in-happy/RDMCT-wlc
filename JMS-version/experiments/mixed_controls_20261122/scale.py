"""Create the larger threshold grid and the paired 16-wafer mixed ablations."""
from dataclasses import asdict,replace
from pathlib import Path
import sys

from controls import CP,HERE,JMS,OUT,ROOT,SCIP,cell,execute,product,product_solve,read,save,sha,store_primary

sys.path.insert(0,str(HERE.parent/"pareto_rl_dmct_20261119"))
sys.path.insert(0,str(cell.BACKENDS["D"]))
from model import Config,Integrated
from validate import validate
from witness import sparse_witness
from joint_algorithms import improve_skeleton

GRID=OUT/"grid4"
LARGE=OUT/"mixed16"
LEVELS={"10pct":0.1,"1pct":0.01,"0p01pct":0.0001}
POLICIES=("full","plain_full","default","hem_spbs","feature_only","no_rerank","greedy","fixed","fixed_free")

def prepare(folder,cfg,data,seed):
    folder.mkdir(parents=True,exist_ok=True)
    x=Integrated(cfg)
    cell.scip_settings(x.model,dict(n=sum(sum(d.values()) for d in cfg.load_ports.values()),seed=seed,seconds=60),folder)
    vals=sparse_witness(cfg,data)
    checked=cell.lift(cfg,vals,None,rebuild=True)
    if not checked:raise ValueError("Constructive assignment rejected by native model")
    store_primary(folder/"raw",checked,dict(seconds=0,status="constructive"))
    vals={v.name:checked[1]["nonzero"].get(v.name,0.) for v in x.model.getVars(transformed=False)}
    new,stages=improve_skeleton(x,vals,60)
    x.model.freeProb()
    checked=cell.lift(cfg,new,None,rebuild=True)
    if not checked:raise ValueError("SPBS assignment rejected")
    store_primary(folder/"prepared",checked,dict(seconds=sum(v["seconds"] for v in stages),stages=stages))

def prepare_grid():
    from decoder import Decoder,Retiming
    folder=GRID/"pure"
    if not (folder/"prepared/primary.json").exists():
        ports={f"LP{i}":{"4x1":1,"2x2":0} for i in range(1,5)}
        cfg=Config(load_ports=ports,cleaning_interval=10,dummy_count=8)
        dec=Decoder(cfg)
        genes=tuple(v for i in range(dec.n) for v in (0,i//2%2,0,0,0))
        data=Retiming(dec.build(genes,dec.pairing(genes)),25).solve("A",None,5)
        prepare(folder,cfg,data,1)

def prepare_large(seed):
    folder=LARGE/f"s{seed}"
    if (folder/"prepared/primary.json").exists():return
    base=HERE.parent/"pareto_rl_dmct_20261119/runs/formal02/shared_initials"
    key=f"H16_s{seed}"
    ref=read(base/"manifest.json")[key]
    src=base/ref["file"];assert sha(src)==ref["sha256"]
    data=read(src)["constructive"]
    assert validate(data)["valid"]
    cfg=replace(Config(**data["config"]),max_pairs=1+max(p["id"] for p in data["pairs"]),
                max_cycles=1+max(c["index"] for c in data["cycles"]))
    save(folder/"source.json",dict(archive=src.relative_to(ROOT).as_posix(),sha256=sha(src),config=asdict(cfg)))
    prepare(folder,cfg,data,seed)

def first(src,folder,n,seed,method,kind,seconds,gap=None,reduce=False,structure="free"):
    d=read(src/"schedule.json");v=cell.values(src/"assignment.json.gz")
    folder.mkdir(parents=True,exist_ok=True)
    checked,record=cell.primary(dict(n=n,seed=seed,train=1,bounds=reduce,structure=structure,
        method=method,kind=kind,seconds=seconds,gap=gap),Config(**d["config"]),d,v,folder,sha(src/"assignment.json.gz"))
    store_primary(folder,checked,record)
    return record

def grid(case,a,folder):
    src=(GRID/"pure/prepared" if case=="pure" else
         JMS/"results/manuscript_certified_gaps_20261119_r3/runs/D_n4_mixed_H10/prep")
    primary=folder/"A"
    if not (primary/"primary.json").exists():
        first(src,primary,4,1,"default","cp",None,LEVELS[a],True)
    record=read(primary/"primary.json")["record"]
    assert record["gate"] and record["gap"]<=LEVELS[a]+1e-9
    results={}
    for b,tau in LEVELS.items():
        e=product_solve(folder/b,primary/"schedule.json",primary/"assignment.json.gz","D",4,1,"fixed",gap=tau)
        assert e["eligible"] and e["replay"]["valid"]
        results[b]=dict(metrics=e["measured"],record=e["record"])
    save(folder/"result.json",dict(case=case,a=a,primary=record,start=sha(src/"assignment.json.gz"),results=results))

def ablate(seed,arm,folder):
    raw=LARGE/f"s{seed}"/"raw"
    prep=LARGE/f"s{seed}"/"prepared"
    src=raw if arm=="plain_full" else prep
    method="full" if arm in ("plain_full","fixed","fixed_free") else arm
    stages=[]
    segments=([("fixed",60),("free",150)] if arm=="fixed_free" else
              [("fixed" if arm=="fixed" else "free",270 if arm=="plain_full" else 210)])
    for i,(structure,seconds) in enumerate(segments):
        target=folder/f"A{i+1}"
        rec=first(src,target,16,seed,method,"scip",seconds,structure=structure)
        stages.append((rec,seconds));src=target
    endpoint=product_solve(folder/"B",src/"schedule.json",src/"assignment.json.gz","D",16,seed,"fixed",30)
    valid=endpoint["eligible"] and all(r["status"] not in ("memlimit","unknown","userinterrupt") and
                                      r["seconds"]<=sec+1 for r,sec in stages)
    original=read(LARGE/f"s{seed}"/"source.json")["archive"]
    expected=read(ROOT/original)["constructive"]["config"]
    final=read(folder/"B/runs/endpoint/schedule.json")
    final["config"]=expected
    check=validate(final)
    assert check["valid"]
    save(folder/"result.json",dict(seed=seed,arm=arm,initial=sha(raw/"assignment.json.gz"),
         start=sha((raw if arm=="plain_full" else prep)/"assignment.json.gz"),stages=stages,
         secondary=endpoint["record"],metrics=endpoint["measured"],physical_replay=check,eligible=valid))

if __name__=="__main__":
    mode=sys.argv[1]
    if mode=="grid-cell":grid(sys.argv[2],sys.argv[3],Path(sys.argv[4]))
    elif mode=="ablate":ablate(int(sys.argv[2]),sys.argv[3],Path(sys.argv[4]))
    elif mode=="grid":
        prepare_grid()
        jobs=[]
        for a in LEVELS:
            for case in ("pure","mixed"):
                folder=str(GRID/f"{case}__{a}")
                jobs.append((CP,__file__,["grid-cell",case,a,folder],folder))
        sys.exit(execute(jobs,3,GRID))
    elif mode=="large":
        jobs=[]
        for seed in (1,2,3):
            prepare_large(seed)
            for arm in POLICIES:
                folder=str(LARGE/f"s{seed}__{arm}")
                jobs.append((SCIP,__file__,["ablate",str(seed),arm,folder],folder))
        sys.exit(execute(jobs,2,LARGE))

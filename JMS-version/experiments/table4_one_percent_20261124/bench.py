"""One-percent, warm-started Table 4, with one physical A handoff per seed."""
from dataclasses import asdict, replace
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "table45_20261124"))
import three_arms as old
from inputs import sparse_witness, validate
from queue_runs import endpoint as old_endpoint

cell, product, read, save, sha = old.cell, old.product, old.read, old.save, old.sha
Config, store = old.Config, old.store_primary
CASES = ((2,3),(4,3),(4,10),(8,3),(8,10))
RESULTS = old.OUT.parent
OUT = RESULTS / HERE.name
GAP = .01
SEEDS = (1,2,3)
ARMS = ("A","B","AB")


def group(n,h):
    return old.case_id(n,h)


def archive(n,h,seed,arm):
    path = old_endpoint(old.OUT,n,h,seed,arm)
    record = read(path)
    assert (record["case"],record["seed"],record["arm"]) == (group(n,h),seed,arm)
    base = old.OUT if path.is_relative_to(old.OUT) else old.LEGACY
    return base/record["path"], record, path


def import_pair(cfg, folder, files):
    assert sha(folder/"schedule.json")==files["schedule.json"]
    assert sha(folder/"assignment.json.gz")==files["assignment.json.gz"]
    data = read(folder/"schedule.json")
    metrics = product.product_metrics(data)
    data["config"] = asdict(cfg)
    assert validate(data)["valid"]
    checked = cell.lift(cfg,cell.values(folder/"assignment.json.gz"),None,rebuild=True)
    if not checked:
        checked = cell.lift(cfg,sparse_witness(cfg,data),None,rebuild=True)
    assert checked and checked[3]["valid"]
    scores = product.product_metrics(checked[0])
    assert all(abs(metrics[k]-scores[k])<cell.EPS for k in ("cmax","secondary"))
    return checked


def preparation(n,h):
    key = group(n,h)
    folder = OUT/"inputs"/key
    if (folder/"input.json").is_file(): return
    if n==2:
        start = RESULTS/"mixed_controls_20261122/grid2/D_n2_mixed_scenario3__0p01pct/1pct/runs/endpoint"
        original = read(start/"schedule.json")["config"]
        common = read(old.LEGACY/"inputs"/group(4,3)/"input.json")["config"]
        cfg = Config(**(common | {k:original[k] for k in ("load_ports","pjobs")}))
    else:
        cfg = Config(**read(old.LEGACY/"inputs"/key/"input.json")["config"])
        if n==4:
            start = RESULTS/"mixed_controls_20261122/grid4/mixed__1pct/1pct/runs/endpoint"
    assert cfg.cleaning_interval==h and cfg.module_residency==cfg.robot_residency==100
    assert cfg.chamber_residency_basis=="nonprocessing" and cfg.source=="dual"
    if n<8:
        proof = start/"result.json"
        files = read(proof)["files"]
    else:
        start,record,proof = archive(n,h,2,"AB")
        files = {k:record[v] for k,v in (("schedule.json","schedule_sha256"),("assignment.json.gz","assignment_sha256"))}
    warm = import_pair(cfg,start,files)
    store(folder/"A",warm,dict(source=str(proof),evidence_sha256=sha(proof)))
    a = read(folder/"A/primary.json")
    candidates = {"A":a["assignment_sha256"]}
    if n>2:
        for seed in SEEDS:
            source,r,p = archive(n,h,seed,"B")
            assert r["record"]["upper"]==r["record"]["lower"]==r["metrics"]["secondary"]==0.
            assert read(source/"schedule.json")["config"]==asdict(cfg)
            verified = import_pair(cfg,source,{"schedule.json":r["schedule_sha256"],"assignment.json.gz":r["assignment_sha256"]})
            store(folder/f"B_s{seed}",verified,dict(source=str(p),evidence_sha256=sha(p),upper=0.,lower=0.))
            candidates[f"B_s{seed}"]=read(folder/f"B_s{seed}/primary.json")["assignment_sha256"]
    save(folder/"input.json",dict(n=n,H=h,case=key,config=asdict(cfg),metrics=a["metrics"],
         schedule_sha256=a["schedule_sha256"],assignment_sha256=a["assignment_sha256"],
         pool=candidates,model_sha256=sha(cell.BACKENDS["D"]/"model.py")))


def reload(folder,cfg):
    meta=read(folder/"primary.json")
    return import_pair(cfg,folder,{"schedule.json":meta["schedule_sha256"],"assignment.json.gz":meta["assignment_sha256"]})


def run(n,h,seed,arm):
    if (n,h) not in CASES or seed not in SEEDS or arm not in ("A","B"): raise ValueError((n,h,seed,arm))
    old.worker.OUT=OUT
    old.worker.TAU=GAP
    base=OUT/"inputs"/group(n,h)
    spec=read(base/"input.json")
    cfg=Config(**spec["config"])
    work=OUT/"runs"/f"{group(n,h)}__s{seed}"
    folder=work/arm
    folder.mkdir(parents=True,exist_ok=True)
    if not (folder/"endpoint.json").exists():
        if arm=="A":
            from primary import search
            sol,rec=search(cfg,base,folder,seed,spec)
            store(folder,sol,rec)
            old.worker.endpoint(folder,folder,arm,spec,seed,rec)
        elif n>2:
            src=base/f"B_s{seed}"
            verified=reload(src,cfg)
            rec=read(src/"primary.json")["record"]
            assert product.product_metrics(verified[0])["secondary"]==0
            rec=dict(rec,status="optimal",engine="archived same-seed feasible solution and nonnegative objective",seconds=0.)
            store(folder,verified,rec)
            old.worker.endpoint(folder,folder,arm,spec,seed,rec)
        else:
            old.process_control(folder,base/"A",spec,seed)
    if arm=="A" and not (work/"AB/endpoint.json").exists():
        old.worker.secondary(work/"AB",folder,spec,seed)


if __name__=="__main__":
    if sys.argv[1]=="prepare-all":
        for i,(n,h) in enumerate(CASES,1):
            print(f"Preparing {n} wafers H={h} | {i-1}/{len(CASES)} ready",flush=True)
            preparation(n,h)
        print("All common inputs verified",flush=True)
    elif sys.argv[1]=="prepare":
        preparation(*map(int,sys.argv[2:]))
    else:
        run(*map(int,sys.argv[2:5]),sys.argv[5])

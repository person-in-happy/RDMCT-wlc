"""Construct shared SPBS inputs serially and charge the measured cost to every method."""
from dataclasses import asdict, replace
import gzip
import json
import time

from common import config, digest, save
from decoder import Decoder, Retiming
from native import Native
from joint_algorithms import improve_skeleton
from validate import validate
from witness import sparse_witness


def initialize(folder, case, seed, budget):
    cfg = config(case)
    dec = Decoder(cfg)
    start = time.monotonic()
    genes = tuple(v for i in range(dec.n) for v in (0,i//2%2,0,0,0))
    neutral = Retiming(dec.build(genes,dec.pairing(genes)),25).solve("A",None,5)
    compact = replace(cfg,max_pairs=max(p["id"] for p in neutral["pairs"])+1,
                      max_cycles=max(c["index"] for c in neutral["cycles"])+1)
    native = Native(compact,seed,25)
    try:
        if not native.warm(neutral):
            raise ValueError("Shared constructive input rejected")
        sparse = sparse_witness(cfg,neutral)
        values = {v.name:float(sparse.get(v.name,0)) for v in native.variables}
        values, stages = improve_skeleton(native.x,values,min(4.,.06*budget))
        sol = native.m.createSol()
        for v in native.variables:
            native.m.setSolVal(sol,v,values[v.name])
        if not native.m.checkSol(sol,original=True,completely=True):
            raise ValueError("SPBS assignment rejected")
        data = native.x.result(solution=sol)
        native.m.freeSol(sol)
        data["config"] = asdict(cfg)
        data["validation"] = validate(data)
        if not data["validation"]["valid"]:
            raise ValueError(data["validation"])
    finally:
        native.close()
    elapsed = time.monotonic()-start
    target = folder/f"{case}_s{seed}.json.gz"
    with gzip.open(target,"wt",encoding="utf-8") as f:
        json.dump(dict(constructive=neutral,spbs=data),f,separators=(",",":"),allow_nan=False)
    return dict(case=case,seed=seed,elapsed=elapsed,stages=stages,file=target.name,sha256=digest(target))


def prepare_all(out,items):
    dest = out/"shared_initials"
    dest.mkdir(exist_ok=True)
    path = dest/"manifest.json"
    existing = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    keys = sorted({(c["case"],c["seed"]) for c in items})
    start = time.monotonic()
    for i,(case,seed) in enumerate(keys):
        key = f"{case}_s{seed}"
        if key in existing:
            rec = existing[key]
            if digest(dest/rec["file"])!=rec["sha256"]:
                raise ValueError("Changed shared input")
            continue
        budget = min(s["budget"] for s in items if (s["case"],s["seed"])==(case,seed))
        existing[key] = initialize(dest,case,seed,budget)
        save(path,existing)
        used = time.monotonic()-start
        print(f"共同初始化 {i+1}/{len(keys)} | 失败 0 | 预计剩余 {used*(len(keys)-i-1)/(i+1):.1f}s",flush=True)

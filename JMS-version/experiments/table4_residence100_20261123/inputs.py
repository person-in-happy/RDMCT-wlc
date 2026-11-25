"""Prepare the five matched table-4 inputs on the nonprocessing-residence backend."""
from dataclasses import asdict, replace
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "mixed_controls_20261122"))
from scale import Config, Integrated, JMS, ROOT, cell, product, read, save, sha, store_primary, validate
from controls import CP, SCIP, product_solve
from decoder import Decoder, Retiming
from witness import sparse_witness

OUT = JMS / "results/table4_residence100_20261123"
OLD = JMS / "results/table4_fixed_gap_20261123"
CASES = tuple((n,h) for n,h in ((4,3),(4,10),(8,3),(8,10),(16,6)))
TAU = .1


def case_id(n, h):
    return f"D_n{n}_H{h}_mixed_dual"


def certified_capacity(cfg, upper):
    plan = cell.capacity(replace(cfg, max_pairs=0, max_cycles=0), upper)
    for k, cap in (("pairs", cfg.max_pairs), ("cycles", cfg.max_cycles)):
        if cap:
            plan[k] = min(plan[k], cap)
    return plan


def prepare(n, h):
    key = case_id(n, h)
    dest = OUT / "inputs" / key
    original = read(OLD / "protocol.json")["inputs"][key if n == 16 else "E"+key[1:]]
    cfg = Config(**(original["config"] | dict(module_residency=100, robot_residency=100,
                                              chamber_residency_basis="nonprocessing")))
    if n == 16:
        src, vals = ROOT / original["source"], ROOT / original["assignment"]
        assert (sha(src),sha(vals)) == (original["source_sha256"],original["assignment_sha256"])
        raw = read(src)
        checked = cell.certify_start(cfg,raw,cell.values(vals))
        provenance = dict(schedule=str(src.relative_to(ROOT)), sha256=sha(src))
    elif n == 4:
        src = JMS / "results/four_gap_ablation_20261123/inputs/s1/raw/schedule.json"
        raw = read(src)
        provenance = dict(schedule=str(src.relative_to(ROOT)), sha256=sha(src))
        src_cfg = raw["config"]
        assert all(src_cfg[k] == v for k,v in original["config"].items()
                   if k not in ("cleaning_interval","horizon","module_residency","robot_residency"))
        raw["config"] = asdict(cfg)
        assert validate(raw)["valid"]
        vals = cell.values(src.with_name("assignment.json.gz"))
        checked = cell.lift(cfg, vals, None, rebuild=True)
        if not checked:
            checked = cell.lift(cfg,sparse_witness(cfg,raw),None,rebuild=True)
    else:
        dec = Decoder(cfg)
        candidates = []
        for layout in ("by_recipe", "alternate_pairs", "one_chamber"):
            genes = tuple(v for i in range(n) for v in
                          (0, {"by_recipe":int(i>=n//2),"alternate_pairs":i//2%2,"one_chamber":0}[layout],0,0,0))
            batch = dec.build(genes, dec.pairing(genes))
            schedule = Retiming(batch,25).solve("A",None,20)
            if schedule and validate(schedule)["valid"]:
                measures = product.product_metrics(schedule)
                candidates.append((measures["cmax"],measures["secondary"],layout,schedule))
        checked = None
        for _, _, layout, raw in sorted(candidates,key=lambda r:r[:3]):
            checked = cell.lift(cfg,sparse_witness(cfg,raw),None,rebuild=True)
            if checked:
                break
        provenance = dict(generator="Decoder + continuous timing LP", selected=layout,
                          trials=[r[:3] for r in candidates])
    if not checked or not checked[3]["valid"]:
        raise ValueError(f"Invalid corrected input {key}")
    metrics = product.product_metrics(checked[0])
    assert all(abs(metrics[k]-v)<cell.EPS for k,v in product.product_metrics(raw).items())
    store_primary(dest,checked,dict(kind="common_start",provenance=provenance))
    record = dict(case=key,n=n,H=h,config=asdict(cfg),metrics=metrics,source=provenance,
                  assignment_sha256=sha(dest/"assignment.json.gz"),schedule_sha256=sha(dest/"schedule.json"),
                  original_config=original["config"],model_sha256=sha(cell.BACKENDS["D"]/"model.py"))
    save(dest / "input.json",record)
    print(key, metrics, flush=True)


if __name__ == "__main__":
    for n,h in CASES:
        prepare(n,h)

"""Construct a product-only witness and verify its analytical bound in the original model."""
from pathlib import Path
import sys
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from inputs import Config, Decoder, OUT, Retiming, TAU, case_id, cell, product, read, sha, sparse_witness, store_primary, validate
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from worker import endpoint


def snap(value):
    # Rounding is just a proposed new solution. Check every original row and event afterward.
    if isinstance(value,float) and abs(value-round(value))<1e-6:
        return float(round(value))
    if isinstance(value,list):
        return [snap(v) for v in value]
    if isinstance(value,dict):
        return {k:snap(v) for k,v in value.items()}
    return value


def product_lp(batch):
    ids={base+event for pattern,base in batch.blocks for i,pair in enumerate(pattern.members)
         for r,wafer in enumerate(pair) if wafer.startswith("LP") for event in pattern.routes[2*i+r].values()}
    batch.waits=[leg for leg in batch.waits if leg[0] in ids or leg[1] in ids]
    n=sum(sum(port.values()) for port in batch.cfg.load_ports.values())
    assert len(batch.waits)==8*n
    return Retiming(batch,25)


def run(n,h,seed):
    key=case_id(n,h)
    src=OUT/"inputs"/key
    spec=read(src/"input.json")
    assert sha(src/"assignment.json.gz")==spec["assignment_sha256"]
    cfg=Config(**spec["config"])
    # Begin at the exact shared incumbent. The construction proposes a different pair
    # structure, and then continuously retimes it to the active product objective.
    start=cell.certify_start(cfg,read(src/"schedule.json"),cell.values(src/"assignment.json.gz"))
    assert start[3]["valid"] and product.product_metrics(start[0])==spec["metrics"]
    decoder=Decoder(cfg)
    genes=tuple(v for i in range(n) for v in (1,i//2%2,1,0,0))
    began=time.perf_counter()
    batch=decoder.build(genes,decoder.pairing(genes))
    result=product_lp(batch).solve("B",None,15)
    if result is None:
        return False
    proposed=snap(result)
    if not validate(proposed)["valid"] or (cfg.max_cycles and
            max(row["index"] for row in proposed["cycles"])>=cfg.max_cycles) or (cfg.max_pairs and
            max(row["id"] for row in proposed["pairs"])>=cfg.max_pairs):
        return False
    checked=cell.lift(cfg,sparse_witness(cfg,proposed),None,rebuild=True)
    if not checked or not checked[3]["valid"]:
        return False
    score=product.product_metrics(checked[0])
    if any(score[k]!=0. for k in ("wait_sum","wait_max","rhythm","secondary")):
        return False
    folder=OUT/"portfolio"/"runs"/f"{key}__s{seed}"/"B"
    r=dict(status="optimal",engine="constructive scheduling + product timing LP + original MILP replay",
           upper=0.,lower=0.,seconds=time.perf_counter()-began,seed=seed,
           lower_bound_source="Nonnegative physical waiting terms, nonnegative absolute rhythm deviations and positive weights.")
    store_primary(folder,checked,r)
    endpoint(folder,folder,"B",spec,seed,r)
    print(key,seed,score["cmax"],score["secondary"],flush=True)
    return True


if __name__=="__main__":
    for n,h in ((4,3),(4,10),(8,3),(8,10),(16,6)):
        for seed in (1,2,3):
            if not run(n,h,seed):
                print(case_id(n,h),"retain unrestricted search",flush=True)
                break

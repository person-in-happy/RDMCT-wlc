"""Generate a common 16-wafer mixed start and run the five SPBS neighborhoods."""
from dataclasses import asdict, replace
from pathlib import Path
import sys
import time

HERE = Path(__file__).resolve().parent
JMS = HERE.parents[1]
OUT = JMS / "results/table3_mixed16_20261125"
sys.path.insert(0, str(HERE.parent / "mixed_controls_20261122"))
from scale import Config, Integrated, cell, improve_skeleton, read, save, sha, store_primary, validate
from decoder import Decoder, Retiming
from witness import sparse_witness
from seed import normalize_schedule


def configuration():
    return Config(load_ports={f"LP{k}": {"4x1": 2, "2x2": 2} for k in range(1, 5)},
                  cleaning_interval=10, dummy_count=8, horizon=100000)


def main():
    cfg = configuration()
    assert cfg.module_residency == cfg.robot_residency == 100
    assert cfg.source == "dual" and (cfg.full_time,cfg.mix_time)==(180,90)
    OUT.mkdir(exist_ok=True,parents=True)
    table = OUT / "input.json"
    fp = dict(config=asdict(cfg), model=sha(cell.BACKENDS["D"]/"model.py"), program=sha(Path(__file__)))
    if table.exists():
        assert read(table) == fp
    else:
        save(table,fp)
    dec = Decoder(cfg)
    trial = OUT / "constructive.json"
    if not trial.exists():
        tested = []
        for layout in ("by_recipe", "alternate_pairs", "one_chamber"):
            genes=tuple(v for i in range(16) for v in (0,{"by_recipe":int(i>=8),"alternate_pairs":i//2%2,"one_chamber":0}[layout],0,0,0))
            candidate=Retiming(dec.build(genes,dec.pairing(genes)),25).solve("A",None,20)
            if candidate is not None and validate(candidate)["valid"]:
                tested.append((candidate["cmax"],layout,candidate))
        upper,layout,candidate=min(tested,key=lambda x:x[:2])
        save(trial,dict(upper=upper,layout=layout,trials=[r[:2] for r in tested],schedule=candidate))
    start=read(trial)["schedule"]
    compact=replace(cfg,max_pairs=1+max(p["id"] for p in start["pairs"]),max_cycles=1+max(q["index"] for q in start["cycles"]))
    small=normalize_schedule(compact,start)
    work=OUT/"spbs_compact"
    work.mkdir(exist_ok=True)
    if not (work/"primary.json").exists():
        vals=sparse_witness(compact,small)
        verified=cell.lift(compact,vals,None,rebuild=True)
        if not verified:raise ValueError("Constructive start rejected")
        x=Integrated(compact)
        cell.scip_settings(x.model,dict(n=16,seed=1,seconds=60),work)
        initial={v.name:verified[1]["nonzero"].get(v.name,0.) for v in x.model.getVars(transformed=False)}
        improved,stages=improve_skeleton(x,initial,60)
        x.model.freeProb()
        checked=cell.lift(compact,improved,None,rebuild=True)
        if not checked:raise ValueError("Compact SPBS output rejected")
        store_primary(work,checked,dict(stages=stages,initial_cmax=verified[2]["cmax"],nominal_seconds=60))
    folder=OUT/"prepared"
    if not (folder/"primary.json").exists():
        doc=normalize_schedule(cfg,read(work/"schedule.json"))
        verified=cell.lift(cfg,sparse_witness(cfg,doc),None,rebuild=True)
        if not verified:raise ValueError("Full native replay of SPBS failed")
        store_primary(folder,verified,dict(source=(work/"primary.json").relative_to(JMS).as_posix(),
            source_sha256=sha(work/"primary.json"),config_sha256=sha(table)))
    rec=read(folder/"primary.json")
    assert rec["replay"]["valid"] and rec["schedule_sha256"]==sha(folder/"schedule.json") and rec["assignment_sha256"]==sha(folder/"assignment.json.gz")
    print("SPBS native start", rec["metrics"]["cmax"], "native rows",rec["rows"],flush=True)


if __name__ == "__main__":
    main()

"""Common, physically validated 16-wafer inputs for gap-stopped ablations."""
from dataclasses import asdict, replace
import math
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "mixed_controls_20261122"))
from scale import Config, JMS, LARGE, ROOT, cell, prepare, read, save, sha, store_primary, validate
from decoder import Decoder, Retiming
from witness import sparse_witness

BASE = JMS / "results/mixed_gap_ablation_20261122"
TAU = 0.0001
SCENARIOS = {
    "H6": ([(5, 0), (3, 0), (0, 3), (0, 5)], 6, 8),
    "S1": ([(8, 8), (0, 0), (0, 0), (0, 0)], 2, 4),
    "S2": ([(2, 2)] * 4, 3, 6),
    "S3": ([(4, 4), (4, 4), (0, 0), (0, 0)], 5, 8),
}


def configuration(case):
    loads, clean, inventory = SCENARIOS[case]
    ports = {f"LP{i}": {"4x1": n, "2x2": m} for i, (n, m) in enumerate(loads, 1)}
    return Config(load_ports=ports, cleaning_interval=clean, dummy_count=inventory)


def prepare_pair(case, seed):
    dest = BASE / "inputs" / case / f"s{seed}"
    manifest = dest / "input.json"
    if manifest.exists():
        return read(manifest)
    cfg = configuration(case)
    if case == "H6":
        src = LARGE / f"s{seed}"
    else:
        src = dest / "initialization"
        if not (src / "prepared/primary.json").exists():
            dec = Decoder(cfg)
            genes = tuple(x for i in range(dec.n) for x in (0, i//2 % 2, 0, 0, 0))
            neutral = Retiming(dec.build(genes, dec.pairing(genes)), 25).solve("A", None, 30)
            assert neutral and validate(neutral)["valid"], "Invalid constructive schedule"
            compact = replace(cfg, max_pairs=1+max(p["id"] for p in neutral["pairs"]),
                              max_cycles=1+max(c["index"] for c in neutral["cycles"]))
            prepare(src, compact, neutral, seed)
    raw = read(src / "raw/schedule.json")
    original = replace(Config(**raw["config"]), max_pairs=0, max_cycles=0)
    assert json.dumps(asdict(original), sort_keys=True) == json.dumps(asdict(cfg), sort_keys=True)
    ceiling = math.ceil(raw["cmax"])
    plan = cell.capacity(cfg, ceiling)
    # Both initialization arms use identical label capacities. The count relaxation covers
    # every schedule that could improve the common validated constructive upper bound.
    domain = replace(cfg, max_pairs=max(plan["pairs"], raw["config"]["max_pairs"]),
                     max_cycles=max(plan["cycles"], raw["config"]["max_cycles"]))
    record = dict(case=case, seed=seed, unrestricted=asdict(cfg), domain=asdict(domain),
                  constructive_upper=ceiling, capacity=plan, sources={})
    for version in ("raw", "prepared"):
        old = src / version
        evidence = read(old / "primary.json")
        schedule = read(old / "schedule.json")
        assert evidence["schedule_sha256"] == sha(old / "schedule.json")
        assert evidence["assignment_sha256"] == sha(old / "assignment.json.gz")
        assert schedule["cmax"] <= ceiling+cell.EPS and validate(schedule)["valid"]
        output = dest / version
        values = cell.values(old / "assignment.json.gz")
        checked = cell.lift(domain, dict(values), schedule["config"]["max_cycles"], rebuild=True)
        if checked is None:
            checked = cell.lift(domain, sparse_witness(domain, schedule), None, rebuild=True)
        assert checked and abs(checked[2]["cmax"]-schedule["cmax"]) <= cell.EPS
        old_metrics = cell.metrics(schedule)[0]
        assert all(abs(old_metrics[k]-checked[2][k]) <= cell.EPS for k in old_metrics)
        store_primary(output, checked, evidence["record"])
        record["sources"][version] = dict(original=str(old.relative_to(ROOT)), original_hash=evidence["assignment_sha256"],
            assignment=sha(output/"assignment.json.gz"), schedule=sha(output/"schedule.json"),
            cmax=checked[2]["cmax"], initialization=evidence["record"])
    save(manifest, record)
    return record


if __name__ == "__main__":
    prepare_pair(sys.argv[1], int(sys.argv[2]))

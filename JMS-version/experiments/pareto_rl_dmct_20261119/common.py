"""Isolated paths, input configurations and objective definitions for the Pareto campaign."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
JMS = HERE.parents[1]
ROOT = JMS.parent
BACKEND = JMS / "model4_pjob_nonprocessing_20261103"
PATTERNS = JMS / "experiments/scale75_20261118"
for path in (BACKEND, PATTERNS, JMS / "experiments/finite_budget_20261116", ROOT):
    sys.path.append(str(path))
# The repository root also contains older versions of these modules.
sys.path.remove(str(BACKEND))
sys.path.insert(0, str(BACKEND))
for key in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[key] = "1"
from model import Config
from finite_budget import physical_metrics

TOL = 2e-5


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def config(name):
    # These are inventory and process inputs only. No solution archives are read.
    cases = {"S1": ([(0, 2)], 4, 2), "M4": ([(1, 0), (1, 0), (0, 1), (0, 1)], 8, 10),
             "H4": ([(2, 0), (1, 0), (0, 1), (0, 0)], 6, 4),
             "H8": ([(3, 0), (1, 0), (0, 1), (0, 3)], 8, 5),
             "H16": ([(5, 0), (3, 0), (0, 3), (0, 5)], 8, 6),
             "R8": ([(0, 3), (0, 5)], 8, 6)}
    base, *change = name.split("-")
    loads, inventory, clean = cases[base]
    for item in change:
        if item[0] == "D":
            inventory = int(item[1:])
        elif item[0] == "H":
            clean = int(item[1:])
        else:
            raise ValueError(name)
    ports = {f"LP{i+1}": {"4x1": a, "2x2": b} for i, (a, b) in enumerate(loads)}
    for i in range(len(ports), 4):
        ports[f"LP{i+1}"] = {"4x1": 0, "2x2": 0}
    return Config(load_ports=ports, dummy_count=inventory, cleaning_interval=clean)


def metrics(schedule, rhythm_weight):
    m = physical_metrics(schedule)
    m["secondary"] = m["wait_sum"] + 10*m["wait_max"] + rhythm_weight*m["rhythm"]
    return m


def lower_bound(cfg, products, pp):
    if cfg.source != "dual":
        raise ValueError("The pair bound requires the vacuum-side dummy source")
    pd = products - 2*pp
    if not 0 <= pp <= products//2:
        raise ValueError((products, pp))
    gap = 2*cfg.atr_handling + cfg.alignment
    cross = cfg.handling + cfg.vtr_travel
    return gap*pp + 2*cross*pd + 10*max(gap/3 if pp else 0, cross if pd else 0)


def dominates(a, b):
    return all(x <= y + TOL for x, y in zip(a, b)) and any(x < y - TOL for x, y in zip(a, b))

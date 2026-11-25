"""Evaluate residence, within-recipe variation, and unused quota before actual cleans."""
from collections import defaultdict
from math import isfinite


def metrics(schedule, range_weight=1.0, clean_weight=1.0):
    cfg = schedule["config"]
    durations = {"4x1": cfg["full_time"], "2x2": cfg["mix_time"], "clean": cfg["cleaning_time"]}
    n_expected = sum(sum(counts.values()) for counts in cfg["load_ports"].values())
    h = cfg["cleaning_interval"]
    times = defaultdict(float)
    cycle_modes = defaultdict(list)
    quota = 0
    for chamber in cfg["chambers"]:
        cycles = sorted((v for v in schedule["cycles"] if v["chamber"] == chamber), key=lambda v: v["index"])
        counter = 0
        for cycle in cycles:
            mode = cycle["mode"]
            if mode == "clean":
                if not 1 <= counter <= h:
                    raise ValueError("Unexpected cleaning counter")
                quota += h - counter
                counter = 0
            else:
                counter += 1
            if counter > h or abs(counter - cycle["counter"]) > 2e-4:
                raise ValueError("Cycle count disagrees with archived events")
            for pair in cycle["pairs"]:
                times[pair] += durations[mode]
                cycle_modes[pair].append(mode)
    by_mode = defaultdict(list)
    products = [w for w in schedule["jobs"] if w["product"]]
    if len(products) != n_expected or len({w["identity"] for w in products}) != n_expected:
        raise ValueError("Product inventory mismatch")
    for wafer in products:
        pair = wafer["pair"]
        modes = cycle_modes[pair]
        if modes not in (["4x1"], ["2x2", "2x2"]):
            raise ValueError("Unexpected product exposure count")
        residence = wafer["unload_start"] - wafer["load_end"] - times[pair]
        if not isfinite(residence) or residence < -2e-4:
            raise ValueError("Invalid nonprocessing residence")
        by_mode[modes[0]].append(max(0.0, residence))
    mean = sum(sum(vals) for vals in by_mode.values()) / n_expected
    spread = max(max(vals) - min(vals) for vals in by_mode.values())
    return dict(cmax=max(w["loan_end"] for w in products), mean_residence=mean, residence_range=spread,
                clean_deficit=quota, secondary=mean + range_weight * spread + clean_weight * quota)


def physical_lower(cfg, range_weight=1.0):
    """Lower bound from the two-exposure exchange and last product of its finite chain."""
    n = sum(sum(counts.values()) for counts in cfg.load_ports.values())
    share = sum(counts.get("2x2", 0) for counts in cfg.load_ports.values()) / n
    # Every retained product spans a rotation/unload/load exchange, then at least
    # one more rotation. The last retained product of a chain also waits for the
    # front-pair unloading before this last rotation. The recipe range makes up
    # any shortfall of earlier products below that final product's residence.
    minimum = 2 * cfg.rotation + 2 * cfg.handling
    return share * minimum + min(share, range_weight) * cfg.handling

"""Event-level score for the quadratic residence objective."""
from functools import lru_cache

DELTA_SECONDS = 1.0
OBJECTIVE = "mean_plus_spread_squared_over_2delta_plus_gamma_E_v1"


from collections import defaultdict
from math import isfinite


def square_penalty(spread, scale=DELTA_SECONDS):
    if scale <= 0 or spread < 0:
        raise ValueError("The time scale must be positive and the spread nonnegative")
    return spread ** 2 / (2 * scale)


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
                clean_deficit=quota, square_penalty=square_penalty(spread), secondary=mean + range_weight * square_penalty(spread) + clean_weight * quota)


@lru_cache(maxsize=None)
def final_wafers(m,h):
    """At least one last pair per finite 2x2 chain of up to H-1 entering pairs."""
    dp=[0]+[m+1]*m
    for total in range(1,m+1):
        for pairs in range(1,min(h-1,total)+1):
            for count in range(pairs,min(2*pairs,total)+1):
                end=2 if count==2*pairs else 1
                dp[total]=min(dp[total],dp[total-count]+end)
    return dp[m]


def physical_lower(cfg,range_weight=1.):
    if range_weight<0:
        raise ValueError("Negative quadratic weight")
    n=sum(sum(counts.values()) for counts in cfg.load_ports.values())
    m=sum(counts.get("2x2",0) for counts in cfg.load_ports.values())
    hnd=cfg.handling
    basic=2*cfg.rotation+2*hnd
    a=(m-final_wafers(m,cfg.cleaning_interval))/n
    # The per-wafer exposure constraint also gives residence >= basic.
    # Past one handling time the linear lower bound on mean is constant.
    d = min(hnd, DELTA_SECONDS * a / range_weight) if range_weight else hnd
    return m * (basic + hnd) / n - a * d + range_weight * square_penalty(d)

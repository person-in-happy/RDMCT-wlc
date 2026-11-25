"""Enumerate order-statistic bounds for eight-product pure-recipe batches."""
from hashlib import sha256
from itertools import product
import json
from pathlib import Path
from time import monotonic

HERE = Path(__file__).resolve().parent
RESULTS = HERE.parents[1] / "results"
SOURCES = RESULTS / "table3_pure8_20261125"
OUT = RESULTS / "table3_grid8_20261125/pure_batch_bounds.json"


def earliest_load(count, config):
    a, v = config["atr_handling"], config["handling"]
    at, vt = config["atr_travel"], config["vtr_travel"]
    align = 2*a + config["alignment"]
    inlet_slot = a + config["pump"] + v + config["upper_reset"]
    entry = []
    for k in range(1, count+1):
        first = a + 2*at + k*align
        entry.append(max(first, entry[-2]+inlet_slot) if k > 2 else first)
    return [t+a+config["pump"]+2*v+vt for t in entry]


def batch_sizes(total, maximum):
    if total == 0:
        yield ()
        return
    for n in range(1, min(maximum, total)+1):
        for suffix in batch_sizes(total-n, maximum):
            yield (n, *suffix)


def calculate(source, mode):
    schedule = json.loads(source.read_bytes())
    config = schedule["config"]
    assert len(config["chambers"])==2 and len(config["pjobs"])==1
    assert config["pjobs"][0]["mode"]==mode and len(config["pjobs"][0]["wafers"])==8
    ready = earliest_load(8, config)
    a, v = config["atr_handling"], config["handling"]
    rot, vt = config["rotation"], config["vtr_travel"]
    tail = 2*v+vt+config["vent"]+2*a+config["atr_travel"]
    outlet_slot = v+config["vent"]+a+config["lower_reset"]
    pure = mode=="4x1"
    exposure = config["full_time"] if pure else 2*config["mix_time"]
    step = exposure+4*v+2*rot if pure else config["mix_time"]+2*v+rot
    best, cases, histogram, minimizers = None, 0, {}, []
    for counts in batch_sizes(8, 4 if pure else 2):
        # Ordered production cycles (4x1) or newly entering product pairs (2x2).
        # Initial chamber label is immaterial because both chambers have identical eligibility.
        for others in product(range(2), repeat=len(counts)-1):
            chambers = (0,*others)
            last = [-step,-step]
            starts, used, releases = [], 0, []
            for n, c in zip(counts,chambers):
                used += n
                t = max(ready[used-1], last[c]+step, starts[-1] if starts else 0)
                starts.append(t)
                last[c] = t
            for i,(n,c,t) in enumerate(zip(counts,chambers,starts)):
                # On 2x2 the last entering pair in each chamber must be a chain end.
                extra = 0 if pure else 2*rot+2*v+v*int(c not in chambers[i+1:])
                releases.extend([t+exposure+extra+tail]*n)
            # If m products remain, the two LL slots require at least (m-1)//2 more reuse epochs.
            bound = max(r+outlet_slot*((7-i)//2) for i,r in enumerate(sorted(releases)))
            cases += 1
            histogram[bound] = histogram.get(bound,0)+1
            if best is None or bound < best:
                best, minimizers = bound, []
            if bound == best:
                minimizers.append(dict(sizes=counts, chambers=chambers, earliest_starts=starts))
    return dict(source=str(source.relative_to(RESULTS)),source_sha256=sha256(source.read_bytes()).hexdigest(),
                lower=best, last_transfer_tail=tail, outlet_slot_reuse=outlet_slot,
                ordered_earliest_chamber_load_ends=ready, minimum_same_chamber_step=step,
                patterns=cases, minimizers=minimizers, lower_bound_histogram=histogram)


if __name__=="__main__":
    signature = sha256(Path(__file__).read_bytes()).hexdigest()
    sources = {mode:SOURCES/mode/"prepared/schedule.json" for mode in ("4x1","2x2")}
    if OUT.exists():
        stored = json.loads(OUT.read_bytes())
        assert signature==stored["program_sha256"] and all(
                sha256(src.read_bytes()).hexdigest()==stored[m]["source_sha256"] for m,src in sources.items())
        print("Previously verified 2/2; ETA 0 s")
    else:
        start = monotonic()
        print("Enumerating two eight-wafer patterns. ETA < 2 s (bounded exhaustive enumeration).",flush=True)
        answers = {mode:calculate(src,mode) for mode,src in sources.items()}
        temp = OUT.with_suffix(".tmp")
        temp.write_text(json.dumps(dict(program_sha256=signature,elapsed_s=monotonic()-start,
                                        recovery="Recompute an interrupted subsecond enumeration.",**answers),indent=2),
                        encoding="utf8")
        temp.replace(OUT)
        print("Completed 2/2; ETA 0 s.", {m:v["lower"] for m,v in answers.items()})

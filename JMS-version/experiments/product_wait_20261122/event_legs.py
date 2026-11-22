"""Independently total the eight physical intervals of each product's route."""
import csv
from collections import defaultdict
from pathlib import Path

from run import OUT, ROOT, read


def product_intervals(schedule):
    events = defaultdict(dict)
    for event in schedule["events"]:
        if "job" in event:
            events[event["job"]][event["kind"]] = event
    intervals = defaultdict(list)
    products = [j for j in schedule["jobs"] if j["product"]]
    cfg = schedule["config"]
    for job in products:
        event = events[job["name"]]
        legs = [
            ("LP_pick_to_AL_put", event["origin_pick"]["end"], event["al_put"]["start"], cfg["atr_travel"]),
            ("AL_residence", event["al_put"]["end"], event["al_pick"]["start"], cfg["alignment"]),
            ("AL_pick_to_upper_LL_put", event["al_pick"]["end"], event["upper_put"]["start"], cfg["atr_travel"]),
            ("upper_LL_residence", event["upper_put"]["end"], event["source_pick"]["start"], cfg["pump"]),
            ("VTR_pick_to_chamber_load", event["source_pick"]["end"], job["load_start"], cfg["vtr_travel"]),
            ("chamber_unload_to_VTR_put", job["unload_end"], event["destination_put"]["start"], cfg["vtr_travel"]),
            ("lower_LL_residence", event["destination_put"]["end"], event["lower_pick"]["start"], cfg["vent"]),
            ("lower_LL_pick_to_LP_put", event["lower_pick"]["end"], event["origin_put"]["start"], cfg["atr_travel"]),
        ]
        for name, start, end, required in legs:
            wait = end - start - required
            if wait < -0.0002:
                raise ValueError((job["identity"], name, wait))
            intervals[name].append(max(0.,wait))
    return intervals


def main():
    rows = []
    with (OUT / "corrected_results.csv").open(encoding="utf-8-sig", newline="") as f:
        for endpoint in csv.DictReader(f):
            record = ROOT / endpoint["source"]
            result = read(record)
            path = record.parent / "schedule.json"
            if result["job"]["kind"] == "score":
                path = ROOT / result["job"]["schedule"]
            intervals = product_intervals(read(path))
            sums = {k: sum(values) for k, values in intervals.items()}
            maxima = {k: max(values) for k, values in intervals.items()}
            measured = result["measured"]
            if max(abs(sum(sums.values()) - measured["wait_sum"]),
                   abs(max(maxima.values()) - measured["wait_max"])) > 0.0002:
                raise ValueError(f"Product route measurements differ: {record}")
            for name, values in intervals.items():
                rows.append(dict(job=endpoint["job"], source=endpoint["source"], eligible=endpoint["eligible"],
                                 leg=name, products=len(values), wait_sum_s=sums[name], wait_max_s=maxima[name]))
    with (OUT / "wait_by_leg.csv").open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(f"{len(rows)} product interval aggregates verified")


if __name__ == "__main__":
    main()

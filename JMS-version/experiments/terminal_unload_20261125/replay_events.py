"""Audit the published terminal-order comparisons directly from event exports."""
from hashlib import sha256
from dataclasses import replace
from math import floor
import gzip
import json
from pathlib import Path
import sys


JMS = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(JMS / "model4_pjob_nonprocessing_20261103"))
from validate import validate
sys.path.insert(0, str(JMS / "experiments/square_residence_20261125"))
from score import metrics

OUT = JMS / "results/terminal_unload_20261125"
SOURCES = {
    "two": "results/huber_residence_20261125/runs/t4_1_2_3_1_fixed/B/schedule.json",
    "four": "results/pareto_scales_20261125/four_native_H3/short397/schedule.json",
}
TOL = 2e-4


def audit(path):
    data = json.loads(path.read_bytes())
    checked = validate(data)
    if not checked["valid"]:
        raise ValueError((path, checked["errors"]))
    cfg = data["config"]
    events, cycles, jobs = data["events"], data["cycles"], data["jobs"]
    pairs = {p["id"]: p for p in data["pairs"]}
    is_product = {w["identity"] for w in jobs if w["product"]}
    exposure = {p: sum(c["end"] - c["start"] for c in cycles if p in c["pairs"]) for p in pairs}
    residence = {w["identity"]: round(w["unload_start"] - w["load_end"] - exposure[w["pair"]], 5)
                 for w in jobs if w["product"]}
    term = []
    for rotation in [e for e in events if e["name"].startswith("rot_priority_")]:
        chamber, index = rotation["chamber"], rotation["cycle"]
        cycle = next(c for c in cycles if (c["chamber"], c["index"]) == (chamber, index))
        front = cycle["front"]
        rear = next(p for p in cycle["pairs"] if p != front)
        assert is_product.isdisjoint(pairs[front]["members"])
        assert is_product.intersection(pairs[rear]["members"])
        unloads = {e["pair"]: e for e in events if e["kind"] == "pair_unload"}
        restore = next(e for e in events if e["name"] == f"rot_after_{chamber}_{index}")
        steps = [cycle, rotation, unloads[rear], restore, unloads[front]]
        assert all(a["end"] <= b["start"] + TOL for a, b in zip(steps, steps[1:]))
        assert all(abs(e["end"] - e["start"] - cfg["rotation"]) < TOL for e in (rotation, restore))
        term.append(dict(chamber=chamber, cycle_index=index, front_members=pairs[front]["members"],
                         rear_members=pairs[rear]["members"], sequence=[
                             [label, round(e["start"], 5), round(e["end"], 5)] for label, e in
                             zip(("process", "rotate", "rear_unload", "rotate", "front_unload"), steps)]))
    release = max(
        [e["end"] for e in events] + [c["end"] for c in cycles]
        + [e["end"] + cfg["upper_reset"] for e in events if e["kind"] == "source_pick" and e["location"] == "U"]
        + [e["end"] + cfg["lower_reset"] for e in events if e["kind"] == "lower_pick"])
    return dict(path=path.relative_to(JMS).as_posix(), input_sha256=sha256(path.read_bytes()).hexdigest(),
                checks=checked["checks"], product_return=round(checked["product_return_cmax"], 5),
                equipment_release=round(release, 5), residence=residence, priority_events=term)


def eight_witness(H):
    """Change only the two unloads and the post-exposure rotations at CH2."""
    source = JMS / f"results/huber_residence_20261125/reuse/epsilon/H{H}_short_cap553/schedule.json"
    full = json.loads(source.read_bytes())
    old = audit(source)
    expected = metrics(full)
    assert expected["clean_deficit"] == 0 and abs(expected["secondary"]-3.75) < TOL
    data = {key: full[key] for key in ("config", "pairs", "jobs", "events", "cycles", "cmax")}
    data.update(schema=full["schema"], solutions=1, status="constructed", model_scope="extended terminal unload")
    tail = next(c for c in data["cycles"] if (c["chamber"],c["index"]) == (2,2))
    assert tail["pairs"] == [2,11] and tail["front"] == 11 and tail["end"] == 448
    by_name = {e["name"]: e for e in data["events"]}
    turn = by_name["rot_after_2_2"]
    first = dict(turn, name="rot_priority_2_2", start=448, end=450)
    data["events"].append(first)
    turn.update(start=451, end=453)
    for p,start in ((2,450), (11,457)):
        by_name[f"unload_{p}"].update(start=start,end=start+1)
        for w in data["jobs"]:
            if w["pair"] == p:
                w.update(unload_start=start,unload_end=start+1)
    result = validate(data)
    assert result["valid"], result["errors"]
    after = metrics(data)
    assert abs(after["cmax"]-553)<TOL and abs(after["secondary"]-3)<TOL
    folder = OUT / "eight_event_replay" / f"H{H}"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "schedule.json"
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(data,indent=2)+"\n",encoding="utf8")
    temp.replace(path)
    observation = audit(path)
    assert observation["equipment_release"] == old["equipment_release"]
    return dict(source=old, result=observation, before=expected, after=after,
                native_assignment=check_extended_model(data))


def check_extended_model(data):
    """Lift the independently constructed event list into the native inequalities."""
    from extended_model import Config, Integrated
    from seed import constrain_seed

    cfg = replace(Config(**data["config"]), max_pairs=1+max(p["id"] for p in data["pairs"]),
                  max_cycles=1+max(c["index"] for c in data["cycles"]))
    x = Integrated(cfg)
    model = x.model
    model.hideOutput()
    model.setIntParam("parallel/maxnthreads", 1)
    model.setRealParam("numerics/feastol", 1e-8)
    model.setRealParam("limits/time", 20)
    score = x.minimize_process_score()
    model.addCons(score <= 3.0000001)
    constrain_seed(x, data, times=True)
    model.optimize()
    assert model.getNSols() > 0, str(model.getStatus())
    sol = model.getBestSol()
    assert model.checkSol(sol, original=True, completely=True)
    row = dict(status=str(model.getStatus()), rows=model.getNConss(transformed=False),
               columns=model.getNVars(transformed=False), all_original_rows_satisfied=True,
               product_first_boundaries=sum(model.getSolVal(sol, b) > .5 for b in x.product_first.values()))
    assert row["product_first_boundaries"] == 1
    model.freeProb()
    return row


def raw_objectives(data):
    """Measure the score from physical operations without cached job timestamps."""
    pairs = {p["id"]: p for p in data["pairs"]}
    events = data["events"]
    load = {e["pair"]: e["end"] for e in events if e["kind"]=="pair_load"}
    unload = {e["pair"]: e["start"] for e in events if e["kind"]=="pair_unload"}
    ret = {e["job"]: e["end"] for e in events if e["kind"]=="origin_put"}
    product = [j for j in data["jobs"] if j["product"]]
    dwell={}
    for j in product:
        p=j["pair"]
        used=sum(c["end"]-c["start"] for c in data["cycles"] if p in c["pairs"])
        dwell.setdefault(pairs[p]["mode"],[]).append(unload[p]-load[p]-used)
    total=sum(sum(g) for g in dwell.values())
    spread=max(max(g)-min(g) for g in dwell.values())
    threshold=data["config"]["cleaning_interval"]
    deficit=0
    for c in data["config"]["chambers"]:
        count=0
        for cycle in sorted((x for x in data["cycles"] if x["chamber"]==c),key=lambda x:x["index"]):
            if cycle["mode"]=="clean":
                assert 1<=count<=threshold
                deficit+=threshold-count
                count=0
            else:
                count+=1
                assert count<=threshold
        assert count < threshold
    return dict(cmax=max(ret[j["name"]] for j in product), mean_residence=total/len(product),
                residence_range=spread, clean_deficit=deficit,
                secondary=total/len(product)+spread**2/2+deficit)


def eight_ideal(h):
    source=OUT/"eight/H10/schedule.json"
    donor=JMS/"results/huber_residence_20261125/reuse/epsilon/H3_short_cap553/schedule.json"
    native=json.loads(source.read_bytes())
    data={k:native[k] for k in ("schema","pairs","jobs","events","cycles","cmax","config")}
    data.update(status="constructed",solutions=1,model_scope="extended terminal unload")
    offset=0
    if h==3:
        template=json.loads(donor.read_bytes())
        permitted=set(data["config"]) - {"cleaning_interval","max_pairs","max_cycles"}
        assert all(data["config"][k]==template["config"][k] for k in permitted)
        data["config"]=template["config"]
        clean,=[c for c in template["cycles"] if c["mode"]=="clean"]
        ids=set(clean["pairs"])
        assert not ids.intersection(p["id"] for p in data["pairs"])
        jobs=[j for j in template["jobs"] if j["pair"] in ids]
        names={j["name"] for j in jobs}
        operations=[e for e in template["events"] if e.get("pair") in ids or e.get("job") in names
                    or (e["kind"]=="rotate" and (e["chamber"],e["cycle"])==(clean["chamber"],clean["index"]))]
        clearance=audit(source)["equipment_release"]+data["config"]["vtr_travel"]
        offset=int(clearance-min(e["start"] for e in operations))
        assert offset>=0 and offset+min(e["start"] for e in operations)>=clearance
        for e in operations+[clean]:
            for k in ("start","end"):
                e[k]+=offset
        for j in jobs:
            for k in ("loan_start","loan_end","load_start","load_end","unload_start","unload_end"):
                j[k]+=offset
        data["pairs"].extend(p for p in template["pairs"] if p["id"] in ids)
        data["events"].extend(operations)
        data["cycles"].append(clean)
        data["jobs"].extend(jobs)
    for node in data["events"]+data["cycles"]:
        for k in ("start","end"):
            node[k]=floor(node[k]+1e-5)
    for j in data["jobs"]:
        for k in ("loan_start","loan_end","load_start","load_end","unload_start","unload_end"):
            j[k]=floor(j[k]+1e-5)
    data["cmax"]=max(j["loan_end"] for j in data["jobs"] if j["product"])
    z=raw_objectives(data)
    assert z==dict(cmax=552,mean_residence=3,residence_range=0,clean_deficit=0,secondary=3)
    assert all(metrics(data)[k]==value for k,value in z.items())
    folder=OUT/"eight_ideal_replay"/f"H{h}"
    folder.mkdir(parents=True,exist_ok=True)
    path=folder/"schedule.json"
    tmp=path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data,indent=2)+"\n",encoding="utf8")
    tmp.replace(path)
    return dict(source=source.relative_to(JMS).as_posix(), source_sha256=sha256(source.read_bytes()).hexdigest(),
                cleanup_donor=donor.relative_to(JMS).as_posix() if h==3 else None,
                cleanup_donor_sha256=sha256(donor.read_bytes()).hexdigest() if h==3 else None,
                cleanup_time_offset=offset, raw_event_metrics=z, result=audit(path),
                native_assignment=check_extended_model(data))


def shortest_deliveries():
    groups={}
    for path in sorted([*OUT.rglob("schedule.json"),*OUT.rglob("schedule.json.gz")]):
        raw=path.read_bytes()
        data=json.loads(gzip.decompress(raw) if path.suffix==".gz" else raw)
        n=sum(w["product"] for w in data["jobs"])
        if n not in (2,4,8):
            continue
        key=f"n{n}_H{data['config']['cleaning_interval']}"
        z=raw_objectives(data)
        groups.setdefault(key,[]).append(dict(path=path.relative_to(JMS).as_posix(),sha256=sha256(raw).hexdigest(),
                                              cmax=z["cmax"],secondary=z["secondary"]))
    for key,rows in groups.items():
        groups[key]=dict(minimum=min(r["cmax"] for r in rows),schedules=rows)
    return groups


def integral_witness(case, h):
    source = OUT/f"scope/{case}_order/schedule.json"
    reference = (JMS / f"results/pareto_scales_20261125/four_native_H{h}/short397/schedule.json"
                 if case=="four" else JMS/SOURCES["two"])
    data = json.loads(source.read_bytes())
    archived = json.loads(reference.read_bytes())
    cfg = dict(data["config"])
    for key in ("cleaning_interval","max_pairs","max_cycles"):
        cfg[key] = archived["config"][key]
    assert cfg == archived["config"] and cfg["cleaning_interval"] == h
    assert max(c["counter"] for c in data["cycles"])==2 and not any(c["mode"]=="clean" for c in data["cycles"])
    data = {key:data[key] for key in ("schema","events","cycles","pairs","jobs","cmax")}
    data.update(config=cfg, status="constructed", solutions=1, model_scope="extended terminal unload")
    # One common floor with a small offset removes SCIP's endpoint tolerances.
    def snapped(value):
        return floor(value+1e-5)
    for node in data["events"]+data["cycles"]:
        for field in ("start","end"):
            node[field]=snapped(node[field])
    for j in data["jobs"]:
        for field in ("loan_start","loan_end","load_start","load_end","unload_start","unload_end"):
            j[field]=snapped(j[field])
    data["cmax"]=max(w["loan_end"] for w in data["jobs"] if w["product"])
    z = metrics(data)
    assert z["cmax"]=={"two":324,"four":397}[case] and z["secondary"]==3
    folder=OUT/f"{case}_event_replay/H{h}"
    folder.mkdir(parents=True,exist_ok=True)
    path=folder/"schedule.json"
    tmp=path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data,indent=2)+"\n",encoding="utf8")
    tmp.replace(path)
    return dict(source_sha256=sha256(source.read_bytes()).hexdigest(), reference=audit(reference),
                result=audit(path), metrics=z, native_assignment=check_extended_model(data))


def main():
    report = {}
    for case, source in SOURCES.items():
        rows = {scope: audit(OUT / "scope" / f"{case}_{scope}" / "schedule.json")
                for scope in ("timing", "order")}
        rows["input"] = audit(JMS / source)
        assert rows["order"]["priority_events"] and not rows["timing"]["priority_events"]
        assert abs(rows["order"]["product_return"] - rows["timing"]["product_return"]) < TOL
        report[case] = rows
    for case,h in (("two",3),("four",3),("four",10)):
        report[f"{case}_H{h}"]=integral_witness(case,h)
    report["eight"] = {str(h): eight_witness(h) for h in (3,10)}
    report["eight_ideal"] = {str(h): eight_ideal(h) for h in (3,10)}
    report["shortest_deliveries"]=shortest_deliveries()
    target = OUT / "event_replay.json"
    temp = target.with_suffix(".tmp")
    temp.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf8")
    temp.replace(target)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()

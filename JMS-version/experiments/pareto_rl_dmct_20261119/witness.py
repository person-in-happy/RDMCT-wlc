"""Sparse full-model primal witness, including fractional times and simultaneous handling."""
from collections import defaultdict
from common import TOL, metrics
from grippers import HANDS
from pjobs import task_for_product


def sparse_witness(cfg, data):
    pairs = {p["id"]:p for p in data["pairs"]}
    ev = {e["name"]:e for e in data["events"]}
    jobs = data["jobs"]
    groups = task_for_product(cfg)
    values = {"Cmax":data["cmax"], "max_wait":metrics(data,25)["wait_max"]}
    resources = defaultdict(list)
    for p, pair in pairs.items():
        products = [w for w in pair["members"] if w in groups]
        mode, ch = pair["mode"], pair["chamber"]
        values.update({f"jp_active_{p}":1,f"jp_mode_{p}_{mode}":1,f"jp_chamber_{p}_{ch}":1,
                       f"jc_product_pair_{p}":bool(products),f"jc_mixed_product_{p}":bool(products) and mode=="2x2",
                       f"pj_product_{p}_1":len(products)==2})
        for r,w in enumerate(pair["members"]):
            if w in groups:
                values[f"pj_x_{groups[w].identifier}_{p}_{r}"] = 1
            else:
                values[f"jp_identity_{w}_{p}_{r}"] = 1
                values[f"identity_code_{p}_{r}"] = int(w[1:])
    for ch in cfg.chambers:
        rows = sorted((c for c in data["cycles"] if c["chamber"]==ch),key=lambda c:c["index"])
        previous, carried = set(), False
        for q, cy in enumerate(rows):
            current = set(cy["pairs"])
            following = set(rows[q+1]["pairs"]) if q+1<len(rows) else set()
            keep, tail = bool(previous & current), not bool(following & current)
            values.update({f"jc_kind_{ch}_{q}_{cy['mode']}":1,f"jc_start_{ch}_{q}":cy["start"],
                           f"jc_count_{ch}_{q}":cy["counter"],f"carry_{ch}_{q}":keep,f"tail_{ch}_{q}":tail})
            for p in current:
                values.update({f"jc_occ_{p}_{ch}_{q}":1,f"jc_first_{p}_{ch}_{q}":p not in previous,
                               f"jc_po_{p}_{ch}_{q}":any(w in groups for w in pairs[p]["members"]),
                               f"front_{p}_{ch}_{q}":p==cy["front"],f"bt_{p}_{ch}_{q}":tail and p!=cy["front"]})
            boundary = max(ev[f"unload_{p}"]["end"] for p in current-following)
            values[f"empty_boundary_{ch}_{q+1}"] = boundary
            if not tail:
                values[f"exchange_boundary_{ch}_{q+1}"] = boundary
            if q>=2 and keep and carried:
                values[f"rhythm_active_{ch}_{q}"] = 1
                values[f"rhythm_{ch}_{q}"] = abs(cy["start"]-2*rows[q-1]["start"]+rows[q-2]["start"])
            previous, carried = current, keep
    for e in ev.values():
        values[e["name"]+"_s"] = e["start"]
    for robot in ("ATR","VTR"):
        sequence = sorted((e for e in ev.values() if e["robot"]==robot),key=lambda e:(round(e["start"],6),e["name"]))
        for i,a in enumerate(sequence):
            for b in sequence[i+1:]:
                values[f"order_{a['name']}_{b['name']}"] = 1
                if abs(a["start"]-b["start"]) < TOL:
                    values[f"sync_{a['name']}_{b['name']}"] = values[f"sync_{b['name']}_{a['name']}"] = 1
    width = cfg.horizon+max(cfg.upper_reset,cfg.lower_reset)
    for j in jobs:
        name = j["name"]
        values[name+"_ch_load_s"],values[name+"_ch_unload_s"] = j["load_start"],j["unload_start"]
        if j["product"]:
            key = f"pjob_release_boundary_{j['pjob']}_{j['load_port']}"
            values[key] = max(values.get(key,0),ev[name+"_origin_pick"]["start"])
            resources["AL"].append((ev[name+"_al_put"]["start"],name))
        else:
            resources["identity"].append((j["loan_start"]+width*int(j["identity"][1:]),name.removeprefix("aux_")))
        for leg,start in (("in",ev[name+"_source_pick"]["start"]),("out",j["unload_start"])):
            code = 1+HANDS.index(j["vtr_hand_"+leg])
            key = f"{name}_{leg}"
            values[f"slot_VTR_hand_{key}_{code-1}"],values[f"code_VTR_hand_{key}"] = 1,code
            resources["VTR_hand"].append((start+width*code,key))
    for loc,put,pick,reset in (("U","upper_put","source_pick",cfg.upper_reset),("L","destination_put","lower_pick",cfg.lower_reset)):
        free = [-1.,-1.]
        items = sorted((ev[j["name"]+"_"+put]["start"],j["name"]) for j in jobs if j["origin"]!="VS")
        for start,name in items:
            slot = min(range(2),key=free.__getitem__)
            if free[slot]>start+TOL:
                raise ValueError(f"Cannot color {loc} at {start}")
            free[slot] = ev[name+"_"+pick]["end"]+reset
            values[f"slot_{loc}_{name}_{slot}"],values[f"code_{loc}_{name}"] = 1,slot+1
            resources[loc].append((start+width*(slot+1),name))
    for resource, items in resources.items():
        items.sort()
        for i,(_,a) in enumerate(items):
            for _,b in items[i+1:]:
                values[f"order_{resource}_{a}_{b}"] = 1
    return values

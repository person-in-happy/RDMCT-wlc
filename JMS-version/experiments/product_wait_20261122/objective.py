"""Product-route waiting and physical pitch on D/E full schedule models."""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
JMS = HERE.parents[1]
ROOT = JMS.parent
sys.path.insert(0, str(HERE.parent / "finite_budget_20261116"))
from finite_budget import physical_metrics


def product_metrics(schedule):
    jobs = [j for j in schedule["jobs"] if j["product"]]
    expected = sum(sum(port.values()) for port in schedule["config"]["load_ports"].values())
    if not jobs or len(jobs) != expected or len({j["identity"] for j in jobs}) != expected:
        raise ValueError("Product event inventory is incomplete")
    return physical_metrics(dict(schedule, jobs=jobs))


def objective_terms(x, values, fixed, weight):
    from scip_imports import scip
    m, cfg = x.model, x.cfg
    variables = {v.name: v for v in m.getVars(transformed=False)}
    maximum = m.addVar(name="product_route_max_wait", lb=0)
    events = {}
    for event in x.events:
        if "job" in event:
            events.setdefault(event["job"], {})[event["kind"]] = event
    waits = []
    for name, j in x.jobs.items():
        if j["product"] is None:
            continue
        ev = events[name]
        legs = [(j["load_s"], ev["source_pick"]["e"], cfg.vtr_travel),
                (ev["destination_put"]["s"], j["unload_e"], cfg.vtr_travel)]
        for a,b,t in (("origin_pick","al_put",cfg.atr_travel),("al_put","al_pick",cfg.alignment),
                      ("al_pick","upper_put",cfg.atr_travel),("upper_put","source_pick",cfg.pump),
                      ("destination_put","lower_pick",cfg.vent),("lower_pick","origin_put",cfg.atr_travel)):
            legs.append((ev[b]["s"],ev[a]["e"],t))
        for end,start,duration in legs:
            wait = end-start-duration*j["active"]
            m.addCons(maximum >= wait)
            waits.append(wait)
    pitches, extra = [], {}
    for c in cfg.chambers:
        for q in range(2, x.Q):
            k,h=x.keep[c,q],x.keep[c,q-1]
            active=values.get(k.name,0)>.5 and values.get(h.name,0)>.5
            v=variables[f"rhythm_{c}_{q}"]
            if fixed:
                if active: pitches.append(v)
            else:
                z=m.addVar(lb=0,ub=cfg.horizon,name=f"product_pitch_{c}_{q}")
                m.addCons(z>=v-cfg.horizon*(2-k-h))
                pitches.append(z)
                extra[z.name]=max(0.,values.get(v.name,0.)-cfg.horizon*(2-values.get(k.name,0.)-values.get(h.name,0.)))
    return scip.quicksum(waits)+10*maximum+weight*scip.quicksum(pitches),maximum,extra

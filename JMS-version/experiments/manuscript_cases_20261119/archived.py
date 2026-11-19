"""Translate an arbitrary manuscript incumbent into the 75-wafer time-window interface."""
from collections import defaultdict
from copy import deepcopy
from math import floor

from patterns import Action


class ArchivedOrder:
    def __init__(self, cfg, data):
        self.cfg, self.source = cfg, data
        self.actions, self.times, self.edges, self.waits, self.returns = [], [], [], [], []
        self.robots, self.slots = defaultdict(list), defaultdict(list)
        self.picks, self.chamber_ops, self.mode, self.chamber = [], [], "archived", 0
        self.events, self.cycles, self.rhythms = {}, {}, []
        synced, chamber_ops = {}, defaultdict(list)
        for e in data["events"]:
            robot, kind, loc = e["robot"], e["kind"], e["location"]
            key = (robot, kind, loc, round(e["start"],4), round(e["end"],4))
            idx = synced.get(key) if robot else None
            if idx is None:
                idx = self.add(kind, robot, loc, e)
                if robot:
                    synced[key] = idx
                    self.robots[robot].append(idx)
                if loc.startswith("CH"):
                    chamber_ops[int(loc[2:])].append(idx)
            self.events[e["name"]] = idx
        by_chamber = defaultdict(list)
        for cycle in data["cycles"]:
            ch, q = cycle["chamber"], cycle["index"]
            idx = self.add("exposure", None, f"CH{ch}", cycle)
            self.cycles[ch,q] = idx
            by_chamber[ch].append(cycle)
            chamber_ops[ch].append(idx)
            load = self.events[f"load_{cycle['front']}"]
            self.edges.append((idx,load,-self.actions[load].duration))
        for ch, ops in chamber_ops.items():
            seq = sorted(ops, key=self.times.__getitem__)
            for a,b in zip(seq,seq[1:]):
                self.edge(a,b)
            cycles = sorted(by_chamber[ch], key=lambda c:c["index"])
            for a,b,c in zip(cycles,cycles[1:],cycles[2:]):
                if (all(x["mode"]=="2x2" for x in (a,b,c)) and set(a["pairs"]) & set(b["pairs"])
                        and set(b["pairs"]) & set(c["pairs"])):
                    self.rhythms.append(tuple(self.cycles[ch,x["index"]] for x in (a,b,c)))
        intervals = defaultdict(list)
        releases, bypasses = defaultdict(list), defaultdict(dict)
        observed = {(e["job"],e["kind"]):self.events[e["name"]] for e in data["events"] if "job" in e}
        self.job_events = observed
        for j in data["jobs"]:
            name,p = j["name"],j["pair"]
            load,unload = self.events[f"load_{p}"], self.events[f"unload_{p}"]
            ev = {k:v for (job,k),v in observed.items() if job == name}
            pick,put=ev["source_pick"],ev["destination_put"]
            self.leg(pick,load,cfg.vtr_travel)
            self.leg(unload,put,cfg.vtr_travel)
            self.cap(pick,load,cfg.robot_residency-self.actions[load].duration)
            self.cap(unload,put,cfg.robot_residency-self.actions[put].duration)
            self.slots[j["vtr_hand_in"]].append((pick,load,0))
            self.slots[j["vtr_hand_out"]].append((unload,put,0))
            head,tail = pick,put
            if j["origin"] != "VS":
                head,tail=ev["origin_pick"],ev["origin_put"]
                up,low=ev["upper_put"],ev["lower_pick"]
                if "al_put" in ev:
                    self.carry(head,ev["al_put"],intervals)
                    self.leg(ev["al_put"],ev["al_pick"],cfg.alignment)
                    self.cap(ev["al_put"],ev["al_pick"],cfg.atr_handling+cfg.module_residency)
                    self.slots["AL"].append((ev["al_put"],ev["al_pick"],0))
                    self.carry(ev["al_pick"],up,intervals)
                    if j["product"]:
                        bypasses[p]["al"] = ev["al_put"]
                else:
                    self.carry(head,up,intervals)
                    bypasses[p]["bypass"] = (head,up)
                self.leg(up,pick,cfg.pump)
                self.cap(up,pick,cfg.atr_handling+cfg.module_residency)
                self.leg(put,low,cfg.vent)
                self.cap(put,low,cfg.handling+cfg.module_residency)
                intervals["U"].append((up,pick,cfg.upper_reset))
                intervals["L"].append((put,low,cfg.lower_reset))
                self.carry(low,tail,intervals)
            if j["product"]:
                self.returns.append(tail)
                releases[j["pjob"]].append((j["wafer_number"],head))
            else:
                self.slots[j["identity"]].append((head,tail,0))
        for tasks in releases.values():
            ordered=[i for _,i in sorted(tasks)]
            self.edges.extend((a,b,0) for a,b in zip(ordered,ordered[1:]) if a!=b)
        for bounds in bypasses.values():
            if "al" in bounds and "bypass" in bounds:
                al, (a,b) = bounds["al"], bounds["bypass"]
                if self.times[b]+self.actions[b].duration <= self.times[al]+1e-5:
                    self.edge(b,al)
                elif self.times[al]+self.actions[al].duration <= self.times[a]+1e-5:
                    self.edge(al,a)
                else:
                    self.edge(a,al)  # An escorted upper placement is a shared robot action.
        for resource,items in intervals.items():
            ends = [-1.,-1.]
            for a,b,reset in sorted(items,key=lambda v:(self.times[v[0]],self.times[v[1]],v)):
                slot=min(range(2),key=ends.__getitem__)
                if ends[slot] > self.times[a]+2e-4:
                    raise ValueError(f"Archived {resource} capacity mismatch")
                ends[slot] = self.times[b]+self.actions[b].duration+reset
                self.slots[f"{resource}_{slot}"].append((a,b,reset))
        for pair in data["pairs"]:
            p,ch=pair["id"],pair["chamber"]
            exposed=sum(c["end"]-c["start"] for c in by_chamber[ch] if p in c["pairs"])
            span=cfg.handling+cfg.module_residency
            if getattr(cfg,"chamber_residency_basis",None)=="nonprocessing":
                span+=round(exposed)
            self.cap(self.events[f"load_{p}"],self.events[f"unload_{p}"],span)

    def add(self,kind,robot,loc,event):
        idx=len(self.actions)
        duration=round(event["end"]-event["start"])
        if abs(duration-(event["end"]-event["start"]))>2e-4:
            raise ValueError("Unexpected noninteger action duration")
        self.actions.append(Action(kind,robot,loc,duration,idx))
        self.times.append(event["start"])
        return idx

    def edge(self,a,b,lag=0):
        self.edges.append((a,b,self.actions[a].duration+lag))

    def cap(self,a,b,span):
        self.edges.append((b,a,-span))

    def leg(self,a,b,lag):
        self.edge(a,b,lag)
        self.waits.append(self.edges[-1])

    def carry(self,a,b,intervals):
        self.leg(a,b,self.cfg.atr_travel)
        self.cap(a,b,self.cfg.robot_residency-self.cfg.atr_handling)
        intervals["ATR"].append((a,b,0))

    def integer_times(self):
        return [floor(t+1e-4) for t in self.times]

    def schedule(self,starts):
        data = {k:deepcopy(self.source[k]) for k in ("config","events","jobs","pairs","cycles")}
        for event in data["events"]:
            i=self.events[event["name"]]
            event.update(start=starts[i],end=starts[i]+self.actions[i].duration)
        for c in data["cycles"]:
            i=self.cycles[c["chamber"],c["index"]]
            c.update(start=starts[i],end=starts[i]+self.actions[i].duration)
        for j in data["jobs"]:
            p,name=j["pair"],j["name"]
            a,b=self.events[f"load_{p}"],self.events[f"unload_{p}"]
            h,t=(("origin_pick","origin_put") if j["origin"]!="VS" else ("source_pick","destination_put"))
            head,tail=self.job_events[name,h],self.job_events[name,t]
            j.update(loan_start=starts[head],loan_end=starts[tail]+self.actions[tail].duration,
                     load_start=starts[a],load_end=starts[a]+self.actions[a].duration,
                     unload_start=starts[b],unload_end=starts[b]+self.actions[b].duration)
        data.update(schema=1,solutions=1,cmax=max(j["loan_end"] for j in data["jobs"] if j["product"]))
        return data

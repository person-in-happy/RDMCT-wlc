"""Active event routes for a group of up to four products or one cleaning."""
from collections import defaultdict
from dataclasses import dataclass


def travel(cfg, robot, origin, destination, next_kind):
    if origin == destination or {origin, destination} <= {"U", "L"}:
        return 0
    if robot == "ATR" and origin in ("U", "L") and destination.startswith("LP") and next_kind == "origin_pick":
        return cfg.atr_empty_ll_to_lp
    return cfg.atr_travel if robot == "ATR" else cfg.vtr_travel


@dataclass(frozen=True)
class Action:
    kind: str
    robot: str | None
    location: str
    duration: float
    owner: int


class Pattern:
    """All edges are minimum differences between *start* times, in seconds."""

    def __init__(self, cfg, mode, chamber, products):
        self.cfg, self.mode, self.chamber = cfg, mode, chamber
        self.actions, self.edges, self.waits, self.cycles = [], [], [], []
        self.routes, self.handling, self.chamber_ops = {}, {}, []
        self.robots, self.slots = defaultdict(list), defaultdict(list)
        self.picks, self.returns = [], []
        self.members = self.make_pairs(products)
        self.incoming_count = self.outgoing_count = 0
        self.at_chamber()
        for robot, sequence in self.robots.items():
            self.order_robot(robot, sequence)
        for intervals in self.slots.values():
            for (_, end, tail), (start, _, _) in zip(intervals, intervals[1:]):
                self.after(end, start, tail)
        for a, b in zip(self.chamber_ops, self.chamber_ops[1:]):
            self.after(a, b)
        self.times = self.earliest()

    def make_pairs(self, products):
        # Each chamber draws from four physical VS wafers. The two support
        # wafers of a 2x2 chain return to VS before their second loan.
        ds = [f"D{i + 1 + 4 * self.cfg.chambers.index(self.chamber)}" for i in range(4)]
        if self.mode == "clean":
            return [ds[:2], ds[2:]]
        if self.mode == "4x1":
            wafers = list(products) + ds[:4-len(products)]
            return [wafers[:2], wafers[2:]]
        wafers = list(products)
        if len(wafers) % 2:
            wafers.append(ds[2])
        return [ds[:2], *[wafers[i:i+2] for i in range(0, len(wafers), 2)], ds[:2]]

    def add(self, kind, robot, location, owner, duration):
        i = len(self.actions)
        self.actions.append(Action(kind, robot, location, duration, owner))
        if robot:
            self.robots[robot].append(i)
        if location.startswith("CH"):
            self.chamber_ops.append(i)
        return i

    def after(self, a, b, lag=0):
        self.edges.append((a, b, self.actions[a].duration + lag))

    def leg(self, a, b, lag):
        self.after(a, b, lag)
        self.waits.append(self.edges[-1])

    def max_span(self, a, b, span):
        self.edges.append((b, a, -span))

    def order_robot(self, robot, sequence):
        latest = {}
        for i in sequence:
            action = self.actions[i]
            for location, previous in latest.items():
                self.after(previous, i, travel(self.cfg, robot, location, action.location, action.kind))
            latest[action.location] = i

    def pair_action(self, p, load):
        cfg = self.cfg
        loc = f"CH{self.chamber}"
        kind = "pair_load" if load else "pair_unload"
        if not load:
            handling = self.add(kind, "VTR", loc, p, cfg.handling)
        for r, wafer in enumerate(self.members[p]):
            j = 2*p + r
            origin = wafer.split("_")[0] if wafer.startswith("LP") else "VS"
            events = self.routes.setdefault(j, {})
            def route_event(tag, robot, location):
                duration = cfg.atr_handling if robot == "ATR" else cfg.handling
                events[tag] = self.add(tag, robot, location, j, duration)
                return events[tag]
            if load:
                if origin != "VS":
                    pick = route_event("origin_pick", "ATR", origin)
                    put_al = route_event("al_put", "ATR", "AL")
                    pick_al = route_event("al_pick", "ATR", "AL")
                    put_u = route_event("upper_put", "ATR", "U")
                    self.picks.append(pick)
                    for a, b, lag in ((pick, put_al, cfg.atr_travel), (put_al, pick_al, cfg.alignment),
                                      (pick_al, put_u, cfg.atr_travel)):
                        self.leg(a, b, lag)
                    self.max_span(put_al, pick_al, cfg.atr_handling + cfg.module_residency)
                    for a, b in ((pick, put_al), (pick_al, put_u)):
                        self.max_span(a, b, cfg.robot_residency - cfg.atr_handling)
                        self.slots["ATR hand"].append((a, b, 0))
                    self.slots["AL"].append((put_al, pick_al, 0))
                source = route_event("source_pick", "VTR", "VS" if origin == "VS" else "U")
                if origin != "VS":
                    self.leg(put_u, source, cfg.pump)
                    self.max_span(put_u, source, cfg.atr_handling + cfg.module_residency)
                    self.slots[f"U{self.incoming_count % 2}"].append((put_u, source, cfg.upper_reset))
                    self.incoming_count += 1
            else:
                dest = route_event("destination_put", "VTR", "VS" if origin == "VS" else "L")
                self.leg(handling, dest, cfg.vtr_travel)
                self.max_span(handling, dest, cfg.robot_residency - cfg.handling)
                self.slots[f"VTR out {r}"].append((handling, dest, 0))
                if origin == "VS":
                    self.slots[wafer].append((events["source_pick"], dest, 0))
                else:
                    pick_l = route_event("lower_pick", "ATR", "L")
                    home = route_event("origin_put", "ATR", origin)
                    self.returns.append(home)
                    self.leg(dest, pick_l, cfg.vent)
                    self.leg(pick_l, home, cfg.atr_travel)
                    self.max_span(dest, pick_l, cfg.handling + cfg.module_residency)
                    self.max_span(pick_l, home, cfg.robot_residency - cfg.atr_handling)
                    self.slots["ATR hand"].append((pick_l, home, 0))
                    self.slots[f"L{self.outgoing_count % 2}"].append((dest, pick_l, cfg.lower_reset))
                    self.outgoing_count += 1
        if load:
            handling = self.add(kind, "VTR", loc, p, cfg.handling)
            for r in range(2):
                source = self.routes[2*p + r]["source_pick"]
                self.leg(source, handling, cfg.vtr_travel)
                self.max_span(source, handling, cfg.robot_residency - cfg.handling)
                self.slots[f"VTR in {r}"].append((source, handling, 0))
        self.handling[p, kind] = handling
        return handling

    def at_chamber(self):
        cfg, mode = self.cfg, self.mode
        loc = f"CH{self.chamber}"
        duration = {"4x1": cfg.full_time, "2x2": cfg.mix_time, "clean": cfg.cleaning_time}[mode]
        self.pair_action(0, True)
        for q in range(len(self.members)-1):
            self.add("rot_before", None, loc, q, cfg.rotation)
            if q:
                self.pair_action(q-1, False)
            front = self.pair_action(q+1, True)
            exposure = self.add("exposure", None, loc, q, duration)
            self.max_span(front, exposure, cfg.handling)
            self.cycles.append((exposure, q, q+1))
        last = len(self.members)-1
        self.pair_action(last, False)
        self.add("rot_after", None, loc, last-1, cfg.rotation)
        self.pair_action(last-1, False)
        for p in range(len(self.members)):
            exposures = sum(p in (back, front) for _, back, front in self.cycles)
            self.max_span(self.handling[p, "pair_load"], self.handling[p, "pair_unload"],
                          cfg.handling + duration*exposures + cfg.module_residency)

    def earliest(self):
        # Longest-path relaxation also handles the backwards residency edges.
        starts = [0] * len(self.actions)
        for _ in self.actions:
            changed = False
            for a, b, lag in self.edges:
                if starts[b] < starts[a] + lag:
                    starts[b] = starts[a] + lag
                    changed = True
            if not changed:
                return starts
        raise ValueError(f"Inconsistent event order for {self.mode} {self.members}")

    def end(self, i):
        return self.times[i] + self.actions[i].duration

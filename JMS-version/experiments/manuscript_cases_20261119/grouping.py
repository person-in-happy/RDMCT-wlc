"""75-wafer beam and time windows on manuscript inventories, supplies and Pjob eligibility."""
from collections import defaultdict
from math import ceil
from types import SimpleNamespace
from unittest.mock import patch

from neighborhood import WindowSearch
import neighborhood
import packing
import patterns
from ortools.sat.python import cp_model
from pjob_order import encoding
from search import ActivePattern, Search, fixed_timing, flexible_blocks
import timing

GAP = 1e-5


def include_atmospheric_store():
    # The 75-wafer code visits VS exclusively. The manuscript's single-source
    # backend applies its empty-return time to both LP and atmospheric store AS.
    original = patterns.travel
    def travel(cfg,robot,origin,destination,kind):
        if robot=="ATR" and origin in ("U","L") and destination=="AS" and kind=="origin_pick":
            return cfg.atr_empty_ll_to_lp
        return original(cfg,robot,origin,destination,kind)
    for module in (patterns,packing,timing,neighborhood):
        module.travel=travel


class InstancePattern(ActivePattern):
    def make_pairs(self, products):
        groups = super().make_pairs(products)
        # The two chamber-local pools can overlap on 4- and 6-dummy instances.
        # The existing per-identity interval resource then serializes their loans.
        return [[f"D{(int(w[1:])-1) % self.cfg.dummy_count+1}" if w.startswith("D") else w
                 for w in group] for group in groups]

    def pair_action(self, p, load):
        if self.cfg.source == "dual":
            return super().pair_action(p, load)
        cfg = self.cfg
        kind, chamber = ("pair_load" if load else "pair_unload"), f"CH{self.chamber}"
        if not load:
            move = self.add(kind, "VTR", chamber, p, cfg.handling)
        for r, wafer in enumerate(self.members[p]):
            j = 2*p+r
            product = wafer.startswith("LP")
            origin = wafer.split("_")[0] if product else "AS"
            route = self.routes.setdefault(j, {})

            def event(tag, robot, location):
                duration = cfg.atr_handling if robot == "ATR" else cfg.handling
                route[tag] = self.add(tag, robot, location, j, duration)
                return route[tag]

            def carry(a, b):
                self.leg(a, b, cfg.atr_travel)
                self.max_span(a, b, cfg.robot_residency-cfg.atr_handling)
                self.slots["ATR hand"].append((a, b, 0))

            if load:
                pick = event("origin_pick", "ATR", origin)
                if product:
                    self.picks.append(pick)
                first = pick
                if product or cfg.dummy_alignment == "legacy_align_all":
                    put = event("al_put", "ATR", "AL")
                    first = event("al_pick", "ATR", "AL")
                    carry(pick, put)
                    self.leg(put, first, cfg.alignment)
                    self.max_span(put, first, cfg.atr_handling+cfg.module_residency)
                    self.slots["AL"].append((put, first, 0))
                elif r and self.members[p][0].startswith("LP"):
                    self.after(self.routes[j-1]["al_put"], pick)
                put = event("upper_put", "ATR", "U")
                carry(first, put)
                source = event("source_pick", "VTR", "U")
                self.leg(put, source, cfg.pump)
                self.max_span(put, source, cfg.atr_handling+cfg.module_residency)
                self.slots[f"U{self.incoming_count % 2}"].append((put, source, cfg.upper_reset))
                self.incoming_count += 1
            else:
                dest = event("destination_put", "VTR", "L")
                self.leg(move, dest, cfg.vtr_travel)
                self.max_span(move, dest, cfg.robot_residency-cfg.handling)
                self.slots[f"VTR out {r}"].append((move, dest, 0))
                pick = event("lower_pick", "ATR", "L")
                home = event("origin_put", "ATR", origin)
                self.leg(dest, pick, cfg.vent)
                self.max_span(dest, pick, cfg.handling+cfg.module_residency)
                carry(pick, home)
                self.slots[f"L{self.outgoing_count % 2}"].append((dest, pick, cfg.lower_reset))
                self.outgoing_count += 1
                if product:
                    self.returns.append(home)
                else:
                    self.slots[wafer].append((route["origin_pick"], home, 0))
        if load:
            move = self.add(kind, "VTR", chamber, p, cfg.handling)
            for r in range(2):
                first = self.routes[2*p+r]["source_pick"]
                self.leg(first, move, cfg.vtr_travel)
                self.max_span(first, move, cfg.robot_residency-cfg.handling)
                self.slots[f"VTR in {r}"].append((first, move, 0))
        self.handling[p, kind] = move
        return move

    def at_chamber(self):
        super().at_chamber()
        if not hasattr(self.cfg, "chamber_residency_basis"):
            for p in range(len(self.members)):
                self.max_span(self.handling[p, "pair_load"], self.handling[p, "pair_unload"],
                              self.cfg.handling+self.cfg.module_residency)
            self.route_edges = tuple(self.edges)


class InstanceSearch(Search):
    def __init__(self, cfg):
        self.cfg, self.groups, self.eligible, self.task_groups = cfg, [], [], []
        codes = encoding(cfg)
        for task in cfg.pjobs:
            labels = sorted(task["wafers"], key=lambda w: codes[w]["pjob_index"])
            size = min(4, 2*(cfg.cleaning_interval-1)) if task["mode"] == "2x2" else 4
            ids = []
            for i in range(0, len(labels), size):
                ids.append(len(self.groups))
                self.groups.append((task["mode"], labels[i:i+size]))
                self.eligible.append(task["chambers"])
            self.task_groups.append(ids)
        self.n = len(self.groups)
        self.patterns = {(k, ch):InstancePattern(cfg, mode, ch, products)
                         for k, (mode, products) in enumerate(self.groups+[("clean", [])]) for ch in cfg.chambers}

    def next_layer(self, beam, width):
        buckets = defaultdict(dict)
        for plan in beam:
            used = {k for k, _, _ in plan if k != self.n}
            counts, _ = self.loads(plan)
            for ids in self.task_groups:
                k = next((i for i in ids if i not in used), None)
                if k is None:
                    continue
                remaining = set(range(self.n)) - used - {k}
                done_full = sum(self.groups[i][0] == "4x1" for i in used | {k})
                future_work = sum(self.group_work(i) for i in remaining)
                future_cycles = sum(len(self.patterns[i,self.cfg.chambers[0]].cycles) for i in remaining)
                for ch in self.eligible[k]:
                    candidate = plan
                    if counts[ch]+len(self.patterns[k,ch].cycles) > self.cfg.cleaning_interval:
                        candidate = self.place(candidate, self.n, ch)
                    candidate = self.place(candidate, k, ch)
                    counters, ends = self.loads(candidate)
                    finish = self.product_finish(candidate)
                    if remaining:
                        free = sum(self.cfg.cleaning_interval-counters[c] for c in self.cfg.chambers)
                        washes = max(0, ceil((future_cycles-free)/self.cfg.cleaning_interval))
                        projected = (sum(ends.values())+future_work+washes*self.cfg.cleaning_time)/2
                        score = (max(projected, max(ends.values())), sum(ends.values()), finish)
                    else:
                        for other in self.cfg.chambers:
                            if counters[other] == self.cfg.cleaning_interval:
                                candidate = self.place(candidate, self.n, other)
                        score = (self.extent(candidate)>self.cfg.horizon, finish, self.extent(candidate))
                    signature = (tuple(counters[c] for c in self.cfg.chambers), tuple(ends.values()), finish)
                    buckets[done_full].setdefault(signature, (score,candidate))
        return [p for bucket in buckets.values() for _,p in sorted(bucket.values())[:width]]


def solve_window(engine, starts, lo, hi, band, seconds):
    recorded = []

    class Solver(cp_model.CpSolver):
        def solve(self, model):
            self.parameters.relative_gap_limit = GAP
            recorded.append((self.parameters.relative_gap_limit, self.parameters.random_seed,
                             self.parameters.num_search_workers, self.parameters.max_time_in_seconds))
            return super().solve(model)

    api = SimpleNamespace(CpSolver=Solver, CpModel=cp_model.CpModel, OPTIMAL=cp_model.OPTIMAL,
                          FEASIBLE=cp_model.FEASIBLE, INFEASIBLE=cp_model.INFEASIBLE, MODEL_INVALID=cp_model.MODEL_INVALID)
    with patch.object(neighborhood, "cp_model", api):
        solution, row = engine.solve(starts, lo, hi, band, seconds)
    if recorded != [(GAP,1,1,seconds)]:
        raise ValueError("Window solver did not receive the 75-wafer settings")
    row.update(relative_gap_limit=GAP, seed=1, workers=1, time_limit_s=seconds)
    return solution, row


def solve_fixed(model, stage, starts, cap=None):
    scip = timing.scip
    used = []

    def create(name):
        solver = scip.Model(name)
        solver.setRealParam("limits/gap", GAP)
        used.append(solver.getParam("limits/gap"))
        return solver

    with patch.object(timing, "scip", SimpleNamespace(Model=create, quicksum=scip.quicksum)):
        result = model.solve(stage, starts, cap)
    if used != [GAP]:
        raise ValueError("SCIP gap mismatch")
    result["relative_gap_limit"] = used[0]
    return result


def grouped_schedule(model, starts):
    normalize = timing.normalize_schedule

    def with_atmospheric_loans(cfg, raw):
        events = {(e.get("job"),e["kind"]):e for e in raw["events"] if "job" in e}
        for j in raw["jobs"]:
            if not j["product"]:
                j.update(origin="AS", loan_start=events[j["name"],"origin_pick"]["start"],
                         loan_end=events[j["name"],"origin_put"]["end"])
        return normalize(cfg, raw)

    if model.cfg.source == "single":
        with patch.object(timing, "normalize_schedule", with_atmospheric_loans):
            return model.schedule(starts)
    return model.schedule(starts)

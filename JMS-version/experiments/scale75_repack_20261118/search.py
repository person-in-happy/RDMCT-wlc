"""Search alternative chamber assignments and priorities for the same 75 products."""
from collections import Counter, defaultdict
from copy import copy
from functools import lru_cache
import math
from types import SimpleNamespace

from incumbent_sublevel import product_route_margins
from packing import Packing
from patterns import Pattern
from timing import BatchTiming


def workload_bound(cfg):
    """Enumerate product splits in a relaxation of the full two-chamber problem."""
    full = sum(x["4x1"] for x in cfg.load_ports.values())
    mixed = sum(x["2x2"] for x in cfg.load_ports.values())
    if len(cfg.chambers) != 2 or cfg.cleaning_interval < 2:
        raise ValueError("Two chambers and a selectable two-exposure chain are required")
    lead, tail = product_route_margins(cfg)
    def one(a, b):
        if not a+b:
            return 0
        f = math.ceil(a/4)
        pairs = math.ceil(b/2)
        m = pairs + math.ceil(pairs/(cfg.cleaning_interval-1))
        washes = (f+m-1)//cfg.cleaning_interval
        # Even a retained-pair transition has one rotation, one outgoing
        # unload and one incoming load, all between the two exposures.
        between = (f+m+washes-1)*(cfg.rotation+2*cfg.handling)
        return lead + tail + f*cfg.full_time + m*cfg.mix_time + washes*cfg.cleaning_time + between
    bound, a, b = min((max(one(i,j), one(full-i,mixed-j)), i, j)
                       for i in range(full+1) for j in range(mixed+1))
    return dict(seconds=bound, lead=lead, tail=tail, minimizing_relaxed_split=[[a,b],[full-a,mixed-b]],
                splits_checked=(full+1)*(mixed+1), terminal_cleaning_charged=False,
                scope="Lower bound for unrestricted product-return makespan")


class ActivePattern(Pattern):
    def at_chamber(self):
        super().at_chamber()
        # These edges encode routes, both residency limits and the process
        # links. The parent subsequently adds its discretionary local orders.
        self.route_edges = tuple(self.edges)


class Search(Packing):
    def __init__(self, cfg):
        super().__init__(cfg)
        for (k, ch) in list(self.patterns):
            mode, wafers = self.groups[k] if k < self.n else ("clean", [])
            self.patterns[k, ch] = ActivePattern(cfg, mode, ch, wafers)

    @lru_cache(maxsize=64)
    def group_work(self, k):
        p = self.patterns[k, self.cfg.chambers[0]]
        return sum(p.actions[i].duration for i, _, _ in p.cycles)

    def next_layer(self, beam, width_per_mix):
        buckets = defaultdict(dict)
        for plan in beam:
            used = {k for k, _, _ in plan if k != self.n}
            counts, _ = self.loads(plan)
            for ids in self.choices.values():
                k = next((i for i in ids if i not in used), None)
                if k is None:
                    continue
                remaining = set(range(self.n)) - used - {k}
                done_full = sum(i not in remaining for i in self.choices["4x1"])
                future_work = sum(self.group_work(i) for i in remaining)
                future_cycles = sum(len(self.patterns[i, self.cfg.chambers[0]].cycles) for i in remaining)
                for ch in self.cfg.chambers:
                    candidate = plan
                    cycles = len(self.patterns[k,ch].cycles)
                    if counts[ch]+cycles > self.cfg.cleaning_interval:
                        candidate = self.place(candidate, self.n, ch)
                    candidate = self.place(candidate, k, ch)
                    counters, ends = self.loads(candidate)
                    finish = self.product_finish(candidate)
                    if remaining:
                        # Compare prefixes with matching recipe counts. Reserve
                        # chamber time for the productive and intermediate clean cycles still due.
                        free_cycles = sum(self.cfg.cleaning_interval-counters[c] for c in self.cfg.chambers)
                        washes = max(0, math.ceil((future_cycles-free_cycles)/self.cfg.cleaning_interval))
                        projected = (sum(ends.values())+future_work+washes*self.cfg.cleaning_time)/2
                        score = (max(projected, max(ends.values())), sum(ends.values()), finish)
                    else:
                        for other in self.cfg.chambers:
                            if counters[other] == self.cfg.cleaning_interval:
                                candidate = self.place(candidate, self.n, other)
                        score = (self.extent(candidate)>self.cfg.horizon, finish, self.extent(candidate))
                    signature = (tuple(counters[c] for c in self.cfg.chambers), tuple(ends.values()), finish)
                    buckets[done_full].setdefault(signature, (score, candidate))
        return [plan for bucket in buckets.values() for _, plan in sorted(bucket.values())[:width_per_mix]]


def flexible_blocks(packing, plan):
    blocks = []
    for k, ch, _ in plan:
        p = copy(packing.patterns[k, ch])
        p.edges = p.route_edges
        p.slots = {key:list(intervals) for key, intervals in p.slots.items()}
        # The original model has two ATR grippers. Each route keeps the same
        # gripper through a carry leg. Chamber and VTR-hand constraints still apply.
        for a, b, reset in p.slots.pop("ATR hand", []):
            hand = p.actions[a].owner % 2
            p.slots.setdefault(f"ATR hand {hand}", []).append((a, b, reset))
        blocks.append(p)
    return blocks


def fixed_timing(cfg, blocks, starts):
    """Rebuild ordering rows from the actual new starts, including across groups."""
    by_key, placement, base = {}, [], 0
    for k, original in enumerate(blocks):
        p = copy(original)
        p.times = starts[base:base+len(p.actions)]
        base += len(p.actions)
        by_key[k, p.chamber] = p
        placement.append((k, p.chamber, 0))
    return BatchTiming(SimpleNamespace(cfg=cfg, patterns=by_key), placement)


def utilization(data):
    from current_defaults_swimlane import build
    _, bars, _, _ = build(data)
    horizon = data["cmax"]
    report = {}
    for ch in data["config"]["chambers"]:
        rows = sorted((b["start"], min(horizon, b["end"]), b["action"])
                      for b in bars if b["lane"] == f"旋转腔 CH{ch}" and b["start"] < horizon)
        totals = Counter()
        last, holes = 0., []
        for a, b, action in rows:
            if a > last:
                holes.append((last,a))
            totals[action] += b-a
            last = b
        if last < horizon:
            holes.append((last,horizon))
        idle = sum(b-a for a,b in holes)
        if abs(sum(totals.values())+idle-horizon) > 2e-4:
            raise ValueError("Chamber lane coverage mismatch")
        report[str(ch)] = dict(idle_s=idle, idle_fraction=idle/horizon, seconds_by_state=dict(totals),
                               longest_empty_interval=max(holes, key=lambda x:x[1]-x[0], default=None))
    return report

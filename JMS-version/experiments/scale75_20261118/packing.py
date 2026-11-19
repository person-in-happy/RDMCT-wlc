"""Place active event patterns on one shared machine timeline."""
from collections import Counter
from functools import lru_cache
from itertools import product
from math import ceil, floor

from patterns import Pattern, travel
from pjob_order import encoding


def merged(ranges):
    result = []
    for low, high in sorted(ranges):
        if low > high:
            continue
        if result and low <= result[-1][1] + 1:
            result[-1] = (result[-1][0], max(high, result[-1][1]))
        else:
            result.append((low, high))
    return result


class Packing:
    def __init__(self, cfg):
        self.cfg = cfg
        codes = encoding(cfg)
        self.groups, self.choices = [], {}
        for task in cfg.pjobs:
            labels = sorted(task["wafers"], key=lambda w: codes[w]["pjob_index"])
            ids = []
            for i in range(0, len(labels), 4):
                ids.append(len(self.groups))
                self.groups.append((task["mode"], labels[i:i+4]))
            self.choices[task["mode"]] = ids
        self.n = len(self.groups)
        self.patterns = {(k, ch): Pattern(cfg, mode, ch, wafers)
                         for k, (mode, wafers) in enumerate(self.groups + [("clean", [])])
                         for ch in cfg.chambers}

    @lru_cache(maxsize=2048)
    def conflicts(self, left_id, right_id):
        """Integer relative shifts that violate a shared robot, hand, slot or loan."""
        a, b = self.patterns[left_id], self.patterns[right_id]
        ranges = []
        for robot in ("ATR", "VTR"):
            for i, j in product(a.robots[robot], b.robots[robot]):
                x, y = a.actions[i], b.actions[j]
                left_first = a.end(i) + travel(self.cfg, robot, x.location, y.location, y.kind) - b.times[j]
                right_first = a.times[i] - b.end(j) - travel(self.cfg, robot, y.location, x.location, x.kind)
                ranges.append((floor(right_first)+1, ceil(left_first)-1))
        for slot in a.slots.keys() & b.slots.keys():
            for (s, e, tail), (u, v, reset) in product(a.slots[slot], b.slots[slot]):
                ranges.append((floor(a.times[s] - b.end(v) - reset)+1,
                               ceil(a.end(e) + tail - b.times[u])-1))
        return merged(ranges)

    def place(self, plan, k, ch):
        b = self.patterns[k, ch]
        start, forbidden = 0, []
        for old, other, offset in plan:
            a = self.patterns[old, other]
            if other == ch:
                start = max(start, offset + a.end(a.chamber_ops[-1]) - b.times[b.chamber_ops[0]])
            if a.mode == b.mode and b.picks:
                start = max(start, offset + a.times[a.picks[-1]] - b.times[b.picks[0]])
            forbidden.extend((offset+lo, offset+hi) for lo, hi in self.conflicts((old, other), (k, ch)))
        for low, high in sorted(forbidden):
            if low > start:
                break
            start = max(start, high+1)
        return plan + ((k, ch, start),)

    def loads(self, plan):
        counts, end = Counter(), dict.fromkeys(self.cfg.chambers, 0)
        for k, ch, start in plan:
            p = self.patterns[k, ch]
            counts[ch] = 0 if p.mode == "clean" else counts[ch] + len(p.cycles)
            end[ch] = start + p.end(p.chamber_ops[-1])
        return counts, end

    def advance(self, beam, width):
        # Keep alternative splits between the two recipes as well as different
        # chamber/cleaning states. All comparisons are internal to one search.
        candidates = {}
        for plan in beam:
            used = {k for k, _, _ in plan}
            counts, _ = self.loads(plan)
            for ids in self.choices.values():
                k = next((i for i in ids if i not in used), None)
                if k is None:
                    continue
                for ch in self.cfg.chambers:
                    cycles = len(self.patterns[k, ch].cycles)
                    candidate = plan
                    counter = counts[ch]
                    if counter + cycles > self.cfg.cleaning_interval:
                        candidate = self.place(candidate, self.n, ch)
                        counter = 0
                    candidate = self.place(candidate, k, ch)
                    if counter + cycles == self.cfg.cleaning_interval:
                        candidate = self.place(candidate, self.n, ch)
                    counters, ends = self.loads(candidate)
                    finish = self.product_finish(candidate)
                    mode_count = sum(i in self.choices["4x1"] for i, _, _ in candidate)
                    signature = (mode_count, tuple(counters.values()), tuple(ends.values()), finish)
                    # Reserve room for the remaining work. At the last layer
                    # score the product return, including any obligatory clean tail in the horizon test.
                    depth = sum(i != self.n for i, _, _ in candidate)
                    if depth == self.n:
                        score = (self.extent(candidate) > self.cfg.horizon, finish, self.extent(candidate))
                    else:
                        score = (max(ends.values()) + .3*min(ends.values()), finish, sum(ends.values()))
                    candidates.setdefault(signature, (score, candidate))
        ranked = sorted(candidates.values())
        if not ranked:
            raise ValueError("No remaining product group")
        return [x[1] for x in ranked[:width]]

    def product_finish(self, plan):
        return max((start + p.end(i) for k, ch, start in plan
                    for p in [self.patterns[k, ch]] for i in p.returns), default=0)

    def extent(self, plan):
        end = 0
        for k, ch, start in plan:
            p = self.patterns[k, ch]
            end = max(end, start + max(p.end(i) for i in range(len(p.actions))),
                      start + max((p.end(i)+tail for slots in p.slots.values() for _, i, tail in slots), default=0))
        return end

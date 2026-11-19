"""Reorder robot moves and slot occupations in a moving window of the full batch."""
from collections import defaultdict
from math import ceil

from ortools.sat.python import cp_model
from patterns import travel


class WindowSearch:
    def __init__(self, cfg, blocks):
        self.cfg, self.actions, self.edges, self.returns = cfg, [], set(), []
        self.resources, picks, chambers = defaultdict(list), defaultdict(list), defaultdict(list)
        self.tails = []
        for p in blocks:
            base = len(self.actions)
            self.actions.extend(p.actions)
            self.tails.extend(a.duration for a in p.actions)
            self.edges.update((base+a, base+b, int(lag)) for a,b,lag in p.edges)
            self.returns.extend(base+i for i in p.returns)
            picks[p.mode].extend(base+i for i in p.picks)
            chambers[p.chamber].extend(base+i for i in p.chamber_ops)
            for resource, items in p.slots.items():
                for a,b,reset in items:
                    tail = int(p.actions[b].duration+reset)
                    self.resources[resource].append((base+a,base+b,tail))
                    self.tails[base+b] = max(self.tails[base+b], tail)
            for robot, seq in p.robots.items():
                self.resources[robot].extend((base+i,base+i,int(p.actions[i].duration)) for i in seq)
        for seq in chambers.values():
            self.edges.update((a,b,int(self.actions[a].duration)) for a,b in zip(seq, seq[1:]))
        for seq in picks.values():
            self.edges.update((a,b,0) for a,b in zip(seq, seq[1:]))

    def finish(self, starts):
        return int(max(starts[i]+self.actions[i].duration for i in self.returns))

    def solve(self, previous, lo, hi, reorder_band, budget):
        ref = [round(t) for t in previous]
        if any(abs(a-b)>1e-7 for a,b in zip(ref, previous)):
            raise ValueError("Window hints must describe integer-second events")
        m = cp_model.CpModel()
        span = hi-lo
        shift = m.new_int_var(0, span, "suffix_advance")
        m.add_hint(shift, 0)
        region = [-1 if t < lo else 1 if t >= hi else 0 for t in ref]
        starts = []
        for i,(t, part) in enumerate(zip(ref, region)):
            if part < 0:
                v = t
            elif part > 0:
                v = t-shift
                if t < span:
                    m.add(shift <= t)
            else:
                v = m.new_int_var(max(0,lo-200), min(hi+200, int(self.cfg.horizon-self.tails[i])), f"t{i}")
                m.add_hint(v,t)
            starts.append(v)

        def precedence(i, j, distance):
            if region[i] != 0 and region[i] == region[j]:
                if ref[i]+distance > ref[j]:
                    raise ValueError("Frozen section violates a temporal constraint")
            else:
                m.add(starts[j] >= starts[i]+distance)

        for a,b,lag in sorted(self.edges):
            precedence(a,b,lag)
        alternatives = 0
        for resource, items in self.resources.items():
            robot = resource in ("ATR","VTR")
            def separation(left, right):
                x, y = self.actions[left[0]], self.actions[right[0]]
                return left[2] + (int(travel(self.cfg, resource, x.location, y.location, y.kind)) if robot else 0)
            before, movable, after = [], [], []
            for item in sorted(items, key=lambda x:(ref[x[0]],x[0])):
                (before, movable, after)[region[item[0]]+1].append(item)
            latest = {}
            def follow(item):
                for group in latest.values():
                    for other in group:
                        precedence(other[1], item[0], separation(other,item))
            def location(item):
                return self.actions[item[0]].location if robot else resource
            for item in before:
                follow(item)
                latest[location(item)] = [item]
            if movable:
                intervals = []
                for j,item in enumerate(movable):
                    a,b,tail = item
                    follow(item)
                    if robot:
                        intervals.append(m.new_fixed_size_interval_var(starts[a], tail, ""))
                        for other in movable[:j]:
                            fwd, rev = separation(other,item), separation(item,other)
                            if ref[a]-ref[other[0]] > reorder_band:
                                precedence(other[1],a,fwd)
                            elif fwd != other[2] or rev != tail:
                                direction = m.new_bool_var("")
                                m.add(starts[a] >= starts[other[1]]+fwd).only_enforce_if(direction)
                                m.add(starts[other[0]] >= starts[b]+rev).only_enforce_if(~direction)
                                m.add_hint(direction, 1)
                                alternatives += 1
                    else:
                        duration = m.new_int_var(1, int(self.cfg.horizon), "")
                        m.add_hint(duration, ref[b]+tail-ref[a])
                        intervals.append(m.new_interval_var(starts[a], duration, starts[b]+tail, ""))
                m.add_no_overlap(intervals)
                ends = defaultdict(list)
                for item in movable:
                    ends[location(item)].append(item)
                latest.update(ends)
            for item in after:
                follow(item)
                latest[location(item)] = [item]

        upper = self.finish(ref)
        obj = m.new_int_var(0, upper, "product_return")
        m.add_max_equality(obj, [starts[i]+int(self.actions[i].duration) for i in self.returns])
        m.minimize(obj)
        m.add_hint(obj,upper)
        solver = cp_model.CpSolver()
        solver.parameters.num_search_workers = 1
        solver.parameters.random_seed = 1
        solver.parameters.max_time_in_seconds = budget
        solver.parameters.max_memory_in_mb = 256
        solver.parameters.relative_gap_limit = .001
        solver.parameters.linearization_level = 0
        solver.parameters.symmetry_level = 0
        status = solver.solve(m)
        if status in (cp_model.MODEL_INVALID, cp_model.INFEASIBLE):
            raise ValueError(f"Known-feasible neighborhood rejected: {solver.status_name(status)} | {m.validate()}")
        feasible = status in (cp_model.OPTIMAL, cp_model.FEASIBLE)
        candidate = [solver.value(v) if not isinstance(v,int) else v for v in starts] if feasible else ref
        after = self.finish(candidate)
        if after > upper:
            raise ValueError("Window increased makespan")
        return candidate, dict(lo=lo, hi=hi, reorder_band=reorder_band, movable=region.count(0),
            alternative_robot_orders=alternatives, status=solver.status_name(status), upper_before=upper,
            upper_after=after, restricted_bound=solver.best_objective_bound, wall_s=solver.wall_time)


def window_sequence(horizon, width, backward):
    # Each sweep covers the whole schedule. The offset changes on the reverse
    # sweep so an interaction on an earlier window boundary can be released.
    offset = -(width//2) if backward else 0
    windows = [(max(0,i), min(horizon+1,i+width)) for i in range(offset, ceil(horizon)+1, width)]
    windows = [(a,b) for a,b in windows if b>a]
    return windows[::-1] if backward else windows

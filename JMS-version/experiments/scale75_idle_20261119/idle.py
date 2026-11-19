"""Second-stage optimization of the two chambers' empty time up to product return."""
from collections import defaultdict

from neighborhood import WindowSearch
from ortools.sat.python import cp_model
from patterns import travel


GAP = 0.0001


class ChamberIdle(WindowSearch):
    def __init__(self, cfg, blocks):
        super().__init__(cfg, blocks)
        self.groups = defaultdict(list)
        self.waits, self.rhythms = [], []
        offset = 0
        for block in blocks:
            ops = [offset + i for i in block.chamber_ops]
            if self.actions[ops[0]].kind != "pair_load" or self.actions[ops[-1]].kind != "pair_unload":
                raise ValueError("Unexpected chamber entry or exit")
            # These templates retain at least one pair through all internal cycles.
            self.groups[block.chamber].append((block.mode, ops))
            self.waits.extend((offset+a, offset+b, int(lag)) for a, b, lag in block.waits)
            if block.mode == "2x2":
                exposures = [offset+i for i, _, _ in block.cycles]
                self.rhythms.extend(zip(exposures, exposures[1:], exposures[2:]))
            offset += len(block.actions)

    def measure(self, starts):
        """Integer arithmetic independent of the plot's event-union implementation."""
        finish = self.finish(starts)
        per_chamber = {}
        for ch, groups in self.groups.items():
            previous, occupied, mechanical, longest = 0, 0, 0, 0
            for _, ops in groups:
                first, last = ops[0], ops[-1]
                begin = min(finish, starts[first])
                end = min(finish, starts[last] + int(self.actions[last].duration))
                longest = max(longest, begin-previous)
                occupied += end-begin
                for i in ops:
                    mechanical += min(finish, starts[i]+int(self.actions[i].duration)) - min(finish, starts[i])
                previous = end
            per_chamber[str(ch)] = dict(idle=finish-occupied, held=occupied-mechanical,
                                        longest=max(longest, finish-previous))
        return dict(cmax=finish, chambers=per_chamber,
                    idle=sum(v["idle"] for v in per_chamber.values()),
                    equipment_end=max(t+int(tail) for t, tail in zip(starts, self.tails)))

    def add_order(self, model, times, ref, window):
        """Keep orders outside the window. Inside it allow nearby moves to exchange."""
        for a, b, lag in sorted(self.edges):
            model.add(times[b] >= times[a]+lag)
        lo, hi, band = window
        alternatives = 0
        for resource, all_items in self.resources.items():
            robot = resource in ("ATR", "VTR")
            ordered = sorted(all_items, key=lambda item: (ref[item[0]], item[0]))
            before, movable, after = [], [], []
            for item in ordered:
                at = ref[item[0]]
                target = before if at < lo else after if at >= hi else movable
                target.append(item)
            latest = {}

            def location(item):
                return self.actions[item[0]].location if robot else resource

            def lag(left, right):
                if not robot:
                    return left[2]
                return left[2] + int(travel(self.cfg, resource, location(left), location(right),
                                            self.actions[right[0]].kind))

            def follow(item):
                for group in latest.values():
                    for other in group:
                        model.add(times[item[0]] >= times[other[1]] + lag(other, item))

            for item in before:
                follow(item)
                latest[location(item)] = [item]
            ends = defaultdict(list)
            for j, item in enumerate(movable):
                follow(item)
                for other in movable[:j]:
                    forward = times[item[0]] >= times[other[1]] + lag(other, item)
                    if ref[item[0]] - ref[other[0]] > band:
                        model.add(forward)
                    else:
                        choice = model.new_bool_var("")
                        model.add(forward).only_enforce_if(choice)
                        model.add(times[other[0]] >= times[item[1]] + lag(item, other)).only_enforce_if(~choice)
                        model.add_hint(choice, 1)
                        alternatives += 1
                ends[location(item)].append(item)
            latest.update(ends)
            for item in after:
                follow(item)
                latest[location(item)] = [item]
        return alternatives

    def add_idle(self, model, times, finish, ref, baseline):
        initial = self.measure(ref)
        idle_vars, longest_gaps = [], []
        for ch, groups in self.groups.items():
            key = str(ch)
            last_product = max(idx for idx, (mode, _) in enumerate(groups) if mode != "clean")
            occupied, active, previous = [], 0, 0
            for idx, (_, ops) in enumerate(groups):
                def clipped(i, offset=0):
                    value = times[i] + offset
                    # Every earlier block leaves this chamber before its last product enters.
                    if idx < last_product:
                        return value
                    clipped_time = model.new_int_var(0, initial["cmax"], "")
                    model.add_min_equality(clipped_time, [finish, value])
                    model.add_hint(clipped_time, min(initial["cmax"], ref[i]+offset))
                    return clipped_time

                first, last = ops[0], ops[-1]
                begin = clipped(first)
                end = clipped(last, int(self.actions[last].duration))
                occupied.append(end-begin)
                longest_gaps.append(begin-previous)
                previous = end
                if idx < last_product:
                    active += sum(int(self.actions[i].duration) for i in ops)
                else:
                    for i in ops:
                        active += clipped(i, int(self.actions[i].duration)) - clipped(i)
            longest_gaps.append(finish-previous)
            busy = sum(occupied)
            idle = model.new_int_var(0, baseline["chambers"][key]["idle"], f"empty_CH{ch}")
            model.add(idle == finish-busy)
            model.add(busy-active <= baseline["chambers"][key]["held"])
            model.add_hint(idle, initial["chambers"][key]["idle"])
            idle_vars.append(idle)
        return sum(idle_vars), longest_gaps

    def solve_idle(self, ref, baseline, lower, window, seconds, purpose="idle", local=False):
        initial = self.measure(ref)
        model = cp_model.CpModel()
        times = []
        lo, hi, _ = window
        if local:
            advance = model.new_int_var(0, hi-lo, "suffix_advance")
            model.add_hint(advance, 0)
        for i, tail in enumerate(self.tails):
            var = model.new_int_var(0, int(baseline["equipment_end"]-tail), f"t{i}")
            model.add_hint(var, ref[i])
            if local and ref[i] < lo:
                model.add(var == ref[i])
            elif local and ref[i] >= hi:
                model.add(var == ref[i]-advance)
            times.append(var)
        alternatives = self.add_order(model, times, ref, window)
        finish = model.new_int_var(lower, initial["cmax"], "products_returned")
        model.add_max_equality(finish, [times[i] + int(self.actions[i].duration) for i in self.returns])
        model.add_hint(finish, initial["cmax"])
        idle, gaps = self.add_idle(model, times, finish, ref, baseline)
        model.add(idle <= initial["idle"])
        if purpose == "longest":
            obj = model.new_int_var(0, max(v["longest"] for v in initial["chambers"].values()), "largest_empty")
            model.add_max_equality(obj, gaps)
            model.add_hint(obj, max(v["longest"] for v in initial["chambers"].values()))
        elif purpose == "waiting":
            worst_gap = max(v["longest"] for v in initial["chambers"].values())
            for gap in gaps:
                model.add(gap <= worst_gap)
            worst = model.new_int_var(0, int(self.cfg.horizon), "worst_wait")
            waits = [times[b]-times[a]-lag for a, b, lag in self.waits]
            model.add_max_equality(worst, waits)
            model.add_hint(worst, max(ref[b]-ref[a]-lag for a, b, lag in self.waits))
            rhythms = []
            for a, b, c in self.rhythms:
                rhythm = model.new_int_var(0, 2*int(self.cfg.horizon), "")
                model.add_abs_equality(rhythm, times[c]-2*times[b]+times[a])
                model.add_hint(rhythm, abs(ref[c]-2*ref[b]+ref[a]))
                rhythms.append(rhythm)
            obj = sum(waits) + 10*worst + 25*sum(rhythms)
        else:
            obj = idle
        model.minimize(obj)
        solver = cp_model.CpSolver()
        solver.parameters.num_search_workers = 1
        solver.parameters.random_seed = 1
        solver.parameters.max_memory_in_mb = 256
        solver.parameters.max_time_in_seconds = seconds
        solver.parameters.relative_gap_limit = GAP
        solver.parameters.linearization_level = 2
        status = solver.solve(model)
        if status in (cp_model.MODEL_INVALID, cp_model.INFEASIBLE):
            raise ValueError(f"Feasible reference rejected: {solver.status_name(status)} {model.validate()}")
        found = status in (cp_model.OPTIMAL, cp_model.FEASIBLE)
        starts = [solver.value(t) for t in times] if found else ref
        measured = self.measure(starts)
        if found and measured["idle"] != solver.value(idle):
            raise ValueError("Modeled and reconstructed idle time disagree")
        return starts, dict(purpose=purpose, window=window, local=local, alternatives=alternatives,
                            status=solver.status_name(status), wall_s=solver.wall_time,
                            objective=solver.objective_value if found else None,
                            conditional_lower_bound=solver.best_objective_bound,
                            relative_gap_limit=solver.parameters.relative_gap_limit, metrics=measured)

"""Two timing LPs for the complete batch after fixing its discrete resource order."""
from collections import defaultdict
from dataclasses import asdict

from grippers import HANDS
from patterns import travel
from scip_imports import scip
from seed import normalize_schedule
from validate import validate


class BatchTiming:
    def __init__(self, packing, plan):
        self.cfg = packing.cfg
        self.blocks, self.actions, self.initial, self.tails = [], [], [], []
        self.waits, self.rhythms, self.returns, self.edges = [], [], [], set()
        slots, robots, picks, chambers = (defaultdict(list) for _ in range(4))
        for k, ch, start in plan:
            p = packing.patterns[k, ch]
            base = len(self.actions)
            self.blocks.append((p, base))
            self.actions.extend(p.actions)
            self.initial.extend(start+t for t in p.times)
            self.tails.extend(a.duration for a in p.actions)
            self.edges.update((base+a, base+b, lag) for a, b, lag in p.edges)
            self.waits.extend((base+a, base+b, lag) for a, b, lag in p.waits)
            for r, seq in p.robots.items():
                robots[r].extend(base+i for i in seq)
            for resource, intervals in p.slots.items():
                for a, b, tail in intervals:
                    slots[resource].append((base+a, base+b, tail))
                    self.tails[base+b] = max(self.tails[base+b], p.actions[b].duration+tail)
            picks[p.mode].extend(base+i for i in p.picks)
            chambers[ch].extend(base+i for i in p.chamber_ops)
            self.returns.extend(base+i for i in p.returns)
            if p.mode == "2x2":
                starts = [base+i for i, _, _ in p.cycles]
                self.rhythms.extend(zip(starts, starts[1:], starts[2:]))
        for robot, seq in robots.items():
            latest = {}
            for i in sorted(seq, key=self.initial.__getitem__):
                a = self.actions[i]
                for loc, j in latest.items():
                    self.edges.add((j, i, self.actions[j].duration + travel(self.cfg, robot, loc, a.location, a.kind)))
                latest[a.location] = i
        for seq in slots.values():
            order = sorted(seq, key=lambda s: self.initial[s[0]])
            for (_, b, tail), (a, _, _) in zip(order, order[1:]):
                self.edges.add((b, a, self.actions[b].duration+tail))
        for seq in chambers.values():
            for a, b in zip(seq, seq[1:]):
                self.edges.add((a, b, self.actions[a].duration))
        for seq in picks.values():
            self.edges.update((a, b, 0) for a, b in zip(seq, seq[1:]))
        if any(self.initial[b] < self.initial[a]+lag for a, b, lag in self.edges):
            raise ValueError("Placement violates the selected event order")

    def solve(self, stage, initial, cap=None):
        m = scip.Model(f"D75_fixed_event_order_{stage}")
        m.hideOutput()
        try:
            m.setIntParam("parallel/maxnthreads", 1)
            m.setIntParam("lp/threads", 1)
            m.setRealParam("limits/memory", 256)
            m.setRealParam("limits/time", 60)
            t = [m.addVar(f"start_{i}", ub=self.cfg.horizon-tail) for i, tail in enumerate(self.tails)]
            for a, b, delta in sorted(self.edges):
                m.addCons(t[b] >= t[a]+delta)
            cmax = m.addVar("product_return", ub=self.cfg.horizon if cap is None else cap)
            for i in self.returns:
                m.addCons(cmax >= t[i] + self.actions[i].duration)
            x0 = initial
            sol = m.createSol()
            for i, var in enumerate(t):
                m.setSolVal(sol, var, x0[i])
            m.setSolVal(sol, cmax, max(x0[i]+self.actions[i].duration for i in self.returns))
            obj = cmax
            if stage == "B":
                worst = m.addVar("wait_max", ub=self.cfg.horizon)
                waits = [t[b]-t[a]-dt for a, b, dt in self.waits]
                for w in waits:
                    m.addCons(worst >= w)
                m.setSolVal(sol, worst, max(x0[b]-x0[a]-dt for a, b, dt in self.waits))
                rhythm = []
                for a, b, c in self.rhythms:
                    d = m.addVar(f"rhythm_{b}", ub=2*self.cfg.horizon)
                    delta = t[c]-2*t[b]+t[a]
                    m.addCons(d >= delta)
                    m.addCons(d >= -delta)
                    m.setSolVal(sol, d, abs(x0[c]-2*x0[b]+x0[a]))
                    rhythm.append(d)
                obj = scip.quicksum(waits) + 10*worst + 25*scip.quicksum(rhythm)
            m.setObjective(obj, "minimize")
            accepted = bool(m.checkSol(sol, printreason=False, completely=True, original=True))
            if accepted:
                m.addSol(sol)
            else:
                m.freeSol(sol)
            variables, rows = m.getNVars(), m.getNConss()
            m.optimize()
            if not m.getNSols():
                raise RuntimeError(f"Fixed event order phase {stage}: {m.getStatus()}, no schedule")
            best = m.getBestSol()
            if not m.checkSol(best, printreason=True, completely=True, original=True):
                raise ValueError("Timing LP assignment failed its original-row check")
            starts = [m.getSolVal(best, v) for v in t]
            return dict(starts=starts, stage=stage, status=str(m.getStatus()), objective=m.getSolObjVal(best),
                        lp_original_check=True, initial_accepted=accepted, variables=variables,
                        constraints=rows, solve_s=m.getSolvingTime(), fixed_order_bound=m.getDualbound())
        finally:
            m.freeProb()

    def schedule(self, starts):
        cfg = self.cfg
        events, jobs, pairs, cycles = [], [], [], []
        counters, indices = defaultdict(int), defaultdict(int)
        for p, base in self.blocks:
            offset = len(pairs)
            ch, first_q = p.chamber, indices[p.chamber]
            for pi, members in enumerate(p.members):
                pairs.append(dict(id=offset+pi, members=members, chamber=ch, mode=p.mode))
            def interval(i):
                return starts[base+i], starts[base+i]+p.actions[i].duration
            for i, a in enumerate(p.actions):
                begin, end = interval(i)
                item = dict(kind=a.kind, location=a.location, robot=a.robot, start=begin, end=end)
                if a.kind == "exposure":
                    _, back, front = p.cycles[a.owner]
                    counters[ch] = 0 if p.mode == "clean" else counters[ch]+1
                    cycles.append(dict(chamber=ch, index=first_q+a.owner, mode=p.mode, start=begin, end=end,
                                       counter=counters[ch], pairs=[offset+back, offset+front], front=offset+front))
                    indices[ch] += 1
                    continue
                if a.kind.startswith("rot_"):
                    item.update(kind="rotate", cycle=first_q+a.owner, chamber=ch, name=f"{a.kind}_{ch}_{first_q+a.owner}")
                elif a.kind in ("pair_load", "pair_unload"):
                    item.update(pair=offset+a.owner, name=f"{a.kind[5:]}_{offset+a.owner}")
                else:
                    job = f"w_{offset+a.owner//2}_{a.owner%2}"
                    item.update(job=job, name=f"{job}_{a.kind}")
                events.append(item)
            for j, route in p.routes.items():
                pi, r = divmod(j, 2)
                wafer = p.members[pi][r]
                product = wafer.startswith("LP")
                origin = wafer.split("_")[0] if product else "VS"
                first, last = (("origin_pick", "origin_put") if product else ("source_pick", "destination_put"))
                ls, le = interval(p.handling[pi, "pair_load"])
                us, ue = interval(p.handling[pi, "pair_unload"])
                jobs.append(dict(name=f"w_{offset+pi}_{r}", identity=wafer, product=product, origin=origin,
                                 pair=offset+pi, loan_start=interval(route[first])[0], loan_end=interval(route[last])[1],
                                 load_start=ls, load_end=le, unload_start=us, unload_end=ue,
                                 vtr_hand_in=HANDS[r], vtr_hand_out=HANDS[r+2]))
        raw = dict(schema=1, solutions=1, config=asdict(cfg), events=events, jobs=jobs, pairs=pairs, cycles=cycles,
                   cmax=max(j["loan_end"] for j in jobs if j["product"]))
        data = normalize_schedule(cfg, raw)
        replay = validate(data)
        if not replay["valid"] or abs(replay["product_return_cmax"]-data["cmax"]) > 2e-4:
            raise ValueError(f"Independent D replay failed: {replay['errors'][:8]}")
        data.update(validation=replay, model_scope="current_D_fixed_structure_timing",
                    primary_objective="product_return_cmax", cleaning_policy="optional_before_threshold",
                    status="physically_validated_feasible", original_model_check=False,
                    primary_bound=None, primary_gap=None, global_optimality_claim=False)
        return data

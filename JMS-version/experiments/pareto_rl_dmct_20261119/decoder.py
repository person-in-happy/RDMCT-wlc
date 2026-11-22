"""Decode wafer pairing, chamber choice and local robot order into continuous-time schedules."""
from __future__ import annotations

from collections import defaultdict
from itertools import groupby
from types import SimpleNamespace
import math
import numpy as np
from scipy.optimize import linprog
from scipy.sparse import coo_matrix, vstack

from common import TOL
from packing import Packing
from patterns import Pattern, travel
from timing import BatchTiming
from pjob_order import encoding


class OrderPattern(Pattern):
    def __init__(self, cfg, mode, chamber, product_pairs, controls):
        self.product_pairs, self.controls = product_pairs, controls
        super().__init__(cfg, mode, chamber, [])

    def make_pairs(self, unused):
        offset = 4*self.cfg.chambers.index(self.chamber)
        ds = [f"D{1+(offset+i)%self.cfg.dummy_count}" for i in range(4)]
        if self.mode == "clean":
            return [ds[:2], ds[2:]]
        chamber_index = self.cfg.chambers.index(self.chamber)
        pairs = [list(members) if len(members) == 2 else [members[0], ds[2+(i+chamber_index)%2]]
                 for i, members in enumerate(self.product_pairs)]
        if self.mode == "4x1":
            return pairs if len(pairs) == 2 else [pairs[0], ds[:2]]
        return [ds[:2], *pairs, ds[:2]]

    def at_chamber(self):
        super().at_chamber()
        for a, b, rest in self.slots.pop("ATR hand", []):
            self.slots[f"ATR hand {self.actions[a].owner%2}"].append((a, b, rest))

    def order_robot(self, robot, sequence):
        # Route generation has already recorded both members; reorder the actual robot actions.
        act = self.actions
        inbound = {"origin_pick", "al_put", "al_pick", "upper_put", "source_pick"}
        def grouping(i):
            a = act[i]
            if a.kind in ("pair_load", "pair_unload"):
                return (a.kind, i)
            return (a.owner//2, a.kind in inbound)
        ordered = []
        for key, group in groupby(sequence, grouping):
            ids = list(group)
            if isinstance(key[0], str):
                ordered.append(ids)
                continue
            pair, arriving = key
            members = self.members[pair]
            choice = self.controls.get(next((w for w in members if w.startswith("LP")), ""),
                                       (0, 0))[0 if arriving else 1]
            if robot == "VTR" and len(ids) == 2:
                if choice % 2:
                    ids.reverse()
                if act[ids[0]].location == act[ids[1]].location and (choice < 2 or all(w.startswith("D") for w in members)):
                    ordered.append(ids)
                    continue
            if robot == "ATR" and len(ids) == 8 and arriving:
                orders = (range(8), (0,4,1,2,3,5,6,7), (0,1,4,2,5,3,6,7), (0,1,4,2,5,6,3,7))
                ids = [ids[i] for i in orders[choice]]
            elif robot == "ATR" and len(ids) == 4 and not arriving and choice % 2:
                ids = [ids[i] for i in (0,2,1,3)]
            # Same-site simultaneous service requires the same action kind and different wafers.
            chunks = [[ids[0]]]
            for i in ids[1:]:
                a, b = act[chunks[-1][-1]], act[i]
                sync = (robot == "ATR" and choice > 0 and a.kind == b.kind
                        and a.kind not in ("al_put", "al_pick") and a.location == b.location)
                if sync:
                    chunks[-1].append(i)
                else:
                    chunks.append([i])
            ordered.extend(chunks)
        latest = {}
        sequence.clear()
        for group in ordered:
            i = group[0]
            for j in group[1:]:
                self.edges.extend(((i, j, 0), (j, i, 0)))
            a = act[i]
            for loc, j in latest.items():
                self.after(j, i, travel(self.cfg, robot, loc, a.location, a.kind))
            latest[a.location] = i
            sequence.append(i)


class Placement(Packing):
    """Reuse the repository's conflict intervals with a per-decode cache."""
    def __init__(self, cfg, patterns):
        self.cfg, self.patterns, self.memo = cfg, patterns, {}

    def conflicts(self, a, b):
        if (a,b) not in self.memo:
            self.memo[a,b] = Packing.conflicts.__wrapped__(self, a, b)
        return self.memo[a,b]


class Decoder:
    # Per wafer: split, chamber, incoming order, outgoing order, inter-task priority.
    bounds = (2, 2, 4, 4, 4)

    def __init__(self, cfg):
        self.cfg = cfg
        codes = encoding(cfg)
        self.labels = [w for task in cfg.pjobs for w in sorted(task["wafers"],key=lambda w:codes[w]["pjob_index"])]
        self.index = {w:i for i,w in enumerate(self.labels)}
        self.n = len(self.labels)

    def pairing(self, genes):
        groups = []
        for task in self.cfg.pjobs:
            labels = sorted(task["wafers"],key=self.index.__getitem__)
            pairs = []
            i = 0
            while i < len(labels):
                lead = self.index[labels[i]]
                size = 2 if genes[5*lead] == 0 and i+1 < len(labels) and genes[5*self.index[labels[i+1]]] == 0 else 1
                ch = task["chambers"][genes[5*lead+1] % len(task["chambers"])]
                pairs.append((ch, tuple(labels[i:i+size])))
                i += size
            blocks = []
            limit = 2 if task["mode"] == "4x1" else min(2, self.cfg.cleaning_interval-1)
            for ch, members in pairs:
                if not blocks or ch != blocks[-1][0] or len(blocks[-1][1]) >= limit:
                    blocks.append((ch, []))
                blocks[-1][1].append(members)
            groups.append([(task["mode"], ch, ms) for ch, ms in blocks])
        result = []
        while any(groups):
            ready = [i for i,seq in enumerate(groups) if seq]
            task = min(ready, key=lambda k:(genes[5*self.index[groups[k][0][2][0][0]]+4], k))
            result.append(groups[task].pop(0))
        return result

    def build(self, genes, blocks):
        cfg = self.cfg
        controls = {w:genes[5*i+2:5*i+4] for i,w in enumerate(self.labels)}
        patterns = {}
        packing = Placement(cfg, patterns)
        counts = defaultdict(int)
        plan = ()
        def add(mode, ch, pairs):
            nonlocal plan
            k = len(plan)
            p = OrderPattern(cfg, mode, ch, pairs, controls)
            patterns[k,ch] = p
            plan = packing.place(plan, k, ch)
            return len(p.cycles)
        for mode, ch, pairs in blocks:
            cycles = 1 if mode == "4x1" else 1+len(pairs)
            if counts[ch]+cycles > cfg.cleaning_interval:
                add("clean", ch, [])
                counts[ch] = 0
            counts[ch] += add(mode, ch, pairs)
        # Mandatory terminal cleans use physical loans and robot time. Place their initial
        # shifts after production, allowing both chambers to finish the products first.
        end_products = max(start+max(packing.patterns[k,ch].times)+max(a.duration for a in packing.patterns[k,ch].actions)
                           for k,ch,start in plan)
        for ch in cfg.chambers:
            if counts[ch] == cfg.cleaning_interval:
                add("clean", ch, [])
                k, _, start = plan[-1]
                plan = (*plan[:-1], (k, ch, max(start, end_products)))
                end_products = plan[-1][2]+max(patterns[k,ch].times)+cfg.cleaning_time
        # Pjob ordering across blocks is enforced by the packing and retiming edges.
        batch = BatchTiming(packing, plan)
        shifts = []
        for p,base in batch.blocks:
            labels = [w for pair in p.members for w in pair if w in self.index]
            level = genes[5*self.index[labels[0]]+4] if labels else 0
            shifts.append(-level*cfg.mix_time/2)
        if any(shifts):
            reorder_shared_resources(batch, shifts)
        return batch


def reorder_shared_resources(batch, shifts):
    """Release inter-block robot, lock and loan orders together, then let the LP repair time."""
    robots, slots, chambers, picks = (defaultdict(list) for _ in range(4))
    edges = set()
    priority = list(batch.initial)
    for (p,base),shift in zip(batch.blocks,shifts):
        for i in range(len(p.actions)):
            priority[base+i] += shift
        edges.update((base+a,base+b,lag) for a,b,lag in p.edges)
        for name,seq in p.robots.items():
            robots[name].extend(base+i for i in seq)
        for slot,intervals in p.slots.items():
            slots[slot].extend((base+a,base+b,lag) for a,b,lag in intervals)
        chambers[p.chamber].extend(base+i for i in p.chamber_ops)
        picks[p.mode].extend(base+i for i in p.picks)
    for robot,seq in robots.items():
        latest = {}
        for i in sorted(seq,key=lambda j:(priority[j],j)):
            a = batch.actions[i]
            for place,j in latest.items():
                edges.add((j,i,batch.actions[j].duration+travel(batch.cfg,robot,place,a.location,a.kind)))
            latest[a.location] = i
    for seq in slots.values():
        ordered = sorted(seq,key=lambda r:(priority[r[0]],r[0]))
        for (_,end,reset),(start,_,_) in zip(ordered,ordered[1:]):
            edges.add((end,start,batch.actions[end].duration+reset))
    for seq in chambers.values():
        edges.update((a,b,batch.actions[a].duration) for a,b in zip(seq,seq[1:]))
    for seq in picks.values():
        edges.update((a,b,0) for a,b in zip(seq,seq[1:]))
    batch.edges = edges


class Retiming:
    """Lexicographic continuous LP on the decoded discrete schedule."""
    def __init__(self, batch, weight):
        self.batch = batch
        n = len(batch.actions)
        av, mx = n, n+1
        cols = n+2+len(batch.rhythms)
        rows, rhs = [], []
        def row(terms, bound):
            rows.append(terms)
            rhs.append(bound)
        for a,b,d in sorted(batch.edges):
            row(((a,1),(b,-1)), -d)
        for i in batch.returns:
            row(((i,1),(av,-1)), -batch.actions[i].duration)
        quality = np.zeros(cols)
        self.offset = 0.
        for a,b,d in batch.waits:
            row(((a,-1),(b,1),(mx,-1)), d)
            quality[a] -= 1
            quality[b] += 1
            self.offset += d
        quality[mx] = 10
        for k,(a,b,c) in enumerate(batch.rhythms, n+2):
            row(((a,1),(b,-2),(c,1),(k,-1)),0)
            row(((a,-1),(b,2),(c,-1),(k,-1)),0)
            quality[k] = weight
        # Empty cycles in the full D model have start zero. Its relaxation for an
        # inactive rhythm row still bounds the second difference by the original M.
        by_chamber = defaultdict(list)
        for pattern,base in batch.blocks:
            by_chamber[pattern.chamber].extend(base+i for i,_,_ in pattern.cycles)
        cfg = batch.cfg
        big_m = cfg.horizon+max(cfg.pump,cfg.vent,cfg.upper_reset,cfg.lower_reset,cfg.alignment,
                                cfg.atr_travel,cfg.atr_empty_ll_to_lp,cfg.vtr_travel,cfg.rotation,cfg.handling,cfg.atr_handling)
        active = set(batch.rhythms)
        for order in by_chamber.values():
            order = [*order,None,None]
            for a,b,c in zip(order,order[1:],order[2:]):
                if (a,b,c) in active:
                    continue
                terms = [(i,v) for i,v in ((a,1),(b,-2),(c,1)) if i is not None]
                row(terms,big_m)
                row([(i,-v) for i,v in terms],big_m)
        rr, cc, dd = [], [], []
        for i,terms in enumerate(rows):
            for j,v in terms:
                rr.append(i); cc.append(j); dd.append(v)
        self.matrix = coo_matrix((dd,(rr,cc)),shape=(len(rows),cols)).tocsr()
        self.rhs = np.array(rhs)
        self.primary = np.zeros(cols)
        self.primary[av] = 1
        self.quality = quality
        self.limits = [(0,batch.cfg.horizon-tail) for tail in batch.tails]+[(0,None)]*(cols-n)
        self.n = n

    def solve(self, goal, cap, seconds):
        if seconds < .01:
            return None
        import time
        deadline = time.monotonic()+seconds
        matrix, rhs = self.matrix, self.rhs
        if cap is not None:
            matrix = vstack((matrix,self.quality),format="csr")
            rhs = np.append(rhs,cap+self.offset+1e-8)
        objectives = (self.quality,self.primary) if goal == "B" else (self.primary,self.quality)
        answer = None
        earliest = np.zeros(len(self.primary))
        earliest[:self.n] = 1
        for objective in (*objectives,earliest):
            remaining = deadline-time.monotonic()
            if remaining < .005:
                break
            result = linprog(objective,A_ub=matrix,b_ub=rhs,bounds=self.limits,method="highs",
                             options={"time_limit":remaining,"dual_feasibility_tolerance":1e-8,
                                      "primal_feasibility_tolerance":1e-8})
            if not result.success:
                break
            answer = result.x
            matrix = vstack((matrix,objective),format="csr")
            rhs = np.append(rhs,result.fun+1e-8)
        if answer is None:
            return None
        return self.batch.schedule(answer[:self.n].tolist())

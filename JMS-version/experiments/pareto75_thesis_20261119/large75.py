"""75-product adapter for the existing physical decoder and continuous retiming LP."""
from __future__ import annotations

import gzip
import hashlib
import json
import random
import sys
import time
import warnings
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
PARETO = HERE.parent / "pareto_rl_dmct_20261119"
sys.path.insert(0, str(PARETO))
from common import Config, JMS, PATTERNS, TOL, digest, dominates, lower_bound, metrics, save
from decoder import OrderPattern, Placement, Retiming
from evolution import run_evolution
from packing import Packing
from timing import BatchTiming
from validate import validate
import decoder
from scipy.optimize import linprog as scipy_linprog, OptimizeWarning

SOURCE = JMS / "results/scale75_mixed_D_20261118_r1"
GRID = 16
METHODS = ("domain", "nsga2", "moead", "fixed")
SEEDS = (1, 2, 3)
BUDGET = 90
WORKERS = 3
REF_B = 3932
BOUNDS = ((0, 12945), (0, 7864))
REF = (1.1, 1.1)


def read(p):
    return json.loads(p.read_text(encoding="utf-8"))


def single_thread_lp(*args, **kwargs):
    kwargs["options"] = {**kwargs.get("options", {}), "threads": 1, "parallel": False}
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=OptimizeWarning, message="Unrecognized options.*")
        return scipy_linprog(*args, **kwargs)


decoder.linprog = single_thread_lp


class GridTiming(BatchTiming):
    def schedule(self, starts):
        return super().schedule([round(t * GRID) / GRID for t in starts])


class Routes:
    """Bounded structural edits around one common frozen plan, in fixed Pjob order."""
    def __init__(self):
        raw = read(SOURCE / "result.json")
        self.cfg = Config(**raw["config"])
        self.base = Packing(self.cfg)
        self.plan = tuple(tuple(row) for row in read(SOURCE / "search.json")["payload"]["beam"][0])
        self.order = [(k, ch) for k, ch, _ in self.plan if k < self.base.n]
        assert sorted(k for k, _ in self.order) == list(range(self.base.n))
        self.place = Placement(self.cfg, {})
        self.groups = self.base.groups
        self.n = self.base.n
        self.lookup = {w: k for k, (_, wafers) in enumerate(self.groups) for w in wafers}
        self.initial = (0, 0, 0, 0)
        # family 0 uses the historical serial handling. Families 1..5 share
        # five synchronous/sequential action orders. Three local edits follow.
        self.limits = (6,) + (1 + 6 * self.n,) * 3
        self.preset = ((0, 0), (1, 1), (2, 1), (3, 1), (3, 3))
        self.warm = GridTiming(self.base, self.plan).schedule(read(SOURCE / "timing_B.json")["payload"]["starts"])
        m = metrics(self.warm, 25)
        assert (m["cmax"], m["secondary"]) == (8630, REF_B)

    def batch(self, genes):
        family, *edits = genes
        order = list(self.order)
        changes = {}
        splits = set()
        for code in edits:
            if code == 0:
                continue
            op, k = divmod(code - 1, self.n)
            i = next(i for i, row in enumerate(order) if row[0] == k)
            if op == 0:
                order[i] = (k, next(ch for ch in self.cfg.chambers if ch != order[i][1]))
            elif op == 1:
                if i + 1 < len(order) and self.groups[k][0] != self.groups[order[i+1][0]][0]:
                    order[i], order[i+1] = order[i+1], order[i]
            elif op == 2:
                splits.add(k)
            else:
                changes[k] = self.preset[op-2]
        if family == 0 and not changes and not splits:
            if order == self.order:
                return GridTiming(self.base, self.plan), frozenset()
            storage = self.base
        else:
            storage = self.place
        plan = ()
        counts = Counter()
        cfg = self.cfg

        def add(k, ch, mode, pairs, ctrl):
            nonlocal plan
            if storage is self.place:
                key = (k, tuple(map(tuple, pairs)), ctrl)
                if (key, ch) not in storage.patterns:
                    storage.patterns[key, ch] = OrderPattern(cfg, mode, ch, pairs, {p[0]: ctrl for p in pairs})
            else:
                key = self.n if mode == "clean" else k
            plan = storage.place(plan, key, ch)

        def clean(ch):
            add(-1, ch, "clean", [], (0, 0))
            counts[ch] = 0

        for k, ch in order:
            mode, wafers = self.groups[k]
            pairs = [wafers[i:i+2] for i in range(0, len(wafers), 2)]
            if k in splits and len(pairs[0]) == 2:
                pairs = [[w] for w in pairs[0]] + pairs[1:]
            for i in range(0, len(pairs), 2):
                block = pairs[i:i+2]
                cycles = 1 if mode == "4x1" else 1 + len(block)
                if counts[ch] + cycles > cfg.cleaning_interval:
                    clean(ch)
                add(k, ch, mode, block, changes.get(k, self.preset[max(0, family-1)]))
                counts[ch] += cycles
                if counts[ch] == cfg.cleaning_interval:
                    clean(ch)
        return GridTiming(storage, plan), frozenset(splits)


def signature(data):
    core = {k: data[k] for k in ("config", "events", "cycles", "jobs", "pairs", "cmax")}
    return hashlib.sha256(json.dumps(core, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


class Search:
    def __init__(self, seed):
        self.routes = Routes()
        self.cfg = self.routes.cfg
        self.rng = random.Random(seed)
        self.initial, self.limits = self.routes.initial, self.routes.limits
        self.initial_ab, self.initial_b = (8630, REF_B), REF_B
        self.floor = lower_bound(self.cfg, 75, 0)
        self.cache, self.archive, self.trace = {}, {}, []
        self.stats = Counter()
        self.started = time.monotonic()

    @staticmethod
    def remaining(end):
        return max(0, end - time.monotonic())

    def admit(self, data, genes, end, cap=None):
        m = metrics(data, 25)
        ab = m["cmax"], m["secondary"]
        now = time.monotonic()
        if now > end:
            self.stats["late"] += 1
            return None
        if cap is not None and ab[1] > cap + TOL:
            self.stats["grid_cap_rejected"] += 1
            return None
        self.stats["physically_validated"] += 1
        if ab not in self.archive and not any(dominates(point, ab) for point in self.archive):
            for point in [p for p in self.archive if dominates(ab, p)]:
                del self.archive[point]
            self.archive[ab] = (genes, data, now - self.started)
            self.trace.append((now - self.started, *ab))
        return ab

    def evaluate(self, genes, goal, cap, screen, end):
        self.stats["evaluations"] += 1
        if self.remaining(end) < 0.02:
            return None
        genes = tuple(genes)
        if genes not in self.cache:
            try:
                batch, _ = self.routes.batch(genes)
                pp = sum(sum(w.startswith("LP") for w in pair) == 2
                         for pattern, _ in batch.blocks for pair in pattern.members)
                item = Retiming(batch, 25), pp
            except ValueError as error:
                if "event order" not in str(error).lower():
                    raise
                self.stats["invalid_structure"] += 1
                item = None
            if len(self.cache) >= 12:
                del self.cache[next(iter(self.cache))]
            self.cache[genes] = item
        item = self.cache[genes]
        if item is None:
            return None
        lp, pp = item
        if screen and cap is not None and lower_bound(self.cfg, 75, pp) > cap:
            self.stats["bound_screened"] += 1
            return None
        self.stats["lp_attempts"] += 1
        try:
            data = lp.solve(goal, cap, self.remaining(end))
        except ValueError as error:
            if "Independent D replay failed" not in str(error):
                raise
            self.stats["physical_replay_rejected"] += 1
            return None
        return self.admit(data, genes, end, cap) if data is not None else None

    def domain(self, end):
        k = 0
        while self.remaining(end) > .04:
            archive = sorted(self.archive)
            parent = self.rng.choice(archive)
            genes, data, _ = self.archive[parent]
            if k < 12:
                child = (k//2, 0, 0, 0)
            else:
                child = list(genes)
                if self.rng.random() < .25:
                    child[0] = self.rng.randrange(self.limits[0])
                else:
                    # Select either the longest in-tool product visit or a random
                    # product group. Work content is fixed within a recipe.
                    jobs = sorted((j for j in data["jobs"] if j["product"]),
                                  key=lambda j:j["loan_end"]-j["loan_start"], reverse=True)
                    candidate = self.rng.choice(jobs[:12] if self.rng.random()<.65 else jobs)
                    group = self.routes.lookup[candidate["identity"]]
                    child[self.rng.randrange(1,4)] = 1 + group + self.routes.n*self.rng.randrange(6)
                child = tuple(child)
            goal = "B" if k % 4 == 1 or k < 12 and k % 2 else "A"
            cap = None
            if k >= 12 and k % 4 in (2,3):
                if len(archive) > 1:
                    i = self.rng.randrange(len(archive)-1)
                    cap = (archive[i][1]+archive[i+1][1])/2
                else:
                    cap = parent[1]*self.rng.uniform(.72,1)
            self.evaluate(child, goal, cap, True, end)
            k += 1

    def run(self, method, seconds):
        self.started = time.monotonic()
        end = self.started + seconds
        self.admit(self.routes.warm, self.initial, end)
        if method in ("nsga2","moead"):
            run_evolution(self, method, end)
        elif method == "domain":
            self.domain(end)
        elif method == "fixed":
            # Each refines the largest remaining B interval on the shared fixed
            # route. Deterministic exact repeats are unnecessary once intervals close.
            self.evaluate(self.initial, "A", None, False, end)
            self.evaluate(self.initial, "B", None, False, end)
            intervals = [(a[1], b[1]) for a,b in zip(sorted(self.archive), sorted(self.archive)[1:])]
            while intervals and self.remaining(end) > .04:
                hi, lo = max(intervals, key=lambda x:x[0]-x[1])
                intervals.remove((hi,lo))
                if hi-lo < 1/GRID:
                    continue
                cap = (hi+lo)/2
                ans = self.evaluate(self.initial, "A", cap, False, end)
                if ans and lo < ans[1] < hi:
                    intervals.extend(((hi,ans[1]), (ans[1],lo)))
                elif cap-lo > 1/GRID:
                    intervals.append((cap,lo))
        else:
            raise ValueError(method)
        return time.monotonic()-self.started


def write_run(out, method, seed):
    search = Search(seed)
    elapsed = search.run(method, BUDGET)
    records = []
    points = sorted(search.archive)
    kept = {points[0], points[-1]}
    scales = [max(1, max(p[i] for p in points)-min(p[i] for p in points)) for i in range(2)]
    while len(kept) < min(7, len(points)):
        def separation(p):
            return min(sum(((p[i]-q[i])/scales[i])**2 for i in range(2)) for q in kept)
        kept.add(max((p for p in points if p not in kept), key=separation))
    for a,b in sorted(kept):
        genes, data, found = search.archive[a,b]
        sig = signature(data)
        obj = out / (sig + ".json.gz")
        with gzip.open(obj, "wt", encoding="utf-8") as stream:
            json.dump(data, stream, ensure_ascii=False, allow_nan=False)
        records.append(dict(a=a,b=b,genes=genes,found_s=found,schedule_sha256=sig,file=obj.name))
    result = dict(method=method, seed=seed, budget=BUDGET, elapsed=elapsed,
                  stats=search.stats, archive=records, internal_nondominated=points, trace=search.trace)
    save(out / "run.json", result)
    return len(records)

"""Anytime search. Only external evaluation reads the independently certified S1 front."""
from collections import Counter, OrderedDict
from dataclasses import asdict
import gzip
import json
import math
import random
import time

from common import TOL, config, dominates, lower_bound, metrics, save
from decoder import Decoder, Retiming
from evolution import run_evolution


class Search:
    def __init__(self, spec, dest, shared):
        self.spec, self.dest = spec, dest
        self.start = time.monotonic()
        self.end = self.start+spec["budget"]
        self.cfg = config(spec["case"])
        self.dec = Decoder(self.cfg)
        self.rng = random.Random(spec["seed"])
        self.weight = spec.get("weight",25)
        self.limits = self.dec.bounds*self.dec.n
        self.initial = tuple(v for i in range(self.dec.n) for v in (0,(i//2)%2,0,0,0))
        self.archive, self.trace, self.subproblems = [],[],[]
        self.stats = Counter()
        self.cache, self.seen = OrderedDict(), {}
        self.floor = lower_bound(self.cfg,self.dec.n,0)
        self.policy = None
        self.certifier = None
        manifest = json.loads((shared/"manifest.json").read_text(encoding="utf-8"))
        ref = manifest[f"{spec['case']}_s{spec['seed']}"]
        self.shared_cost = ref["elapsed"]
        self.start -= self.shared_cost
        self.end = self.start+spec["budget"]
        with gzip.open(shared/ref["file"],"rt",encoding="utf-8") as f:
            schedules = json.load(f)
        self.initial_ab = self.admit(schedules["constructive"],self.initial,None)
        self.admit(schedules["spbs"],None,None)
        if not self.initial_ab:
            raise RuntimeError("Instance has no validated common initial timetable")
        self.initial_b = self.initial_ab[1]

    def remaining(self, deadline):
        return deadline-time.monotonic()

    def admit(self, data, genome, cap):
        stat = metrics(data,self.weight)
        a,b = stat["cmax"],stat["secondary"]
        now = time.monotonic()-self.start
        if not data["validation"]["valid"] or not all(map(math.isfinite,(a,b))):
            raise ValueError("Invalid physical timetable")
        if cap is not None and b>cap+TOL:
            raise ValueError(f"Physical upper limit violated {b}, {cap}")
        if now>self.spec["budget"]:
            self.stats["late_excluded"] += 1
            return None
        self.stats["validated"] += 1
        ab = a,b
        if not any(dominates((r["a"],r["b"]),ab) or
                   max(abs(a-r["a"]),abs(b-r["b"]))<=TOL for r in self.archive):
            # A compact sub-MIP can schedule a terminal clean too late to reproduce
            # the physical objective on the unused cycles of the original model.
            # Charge the full witness check, and never let such a point remove a valid incumbent.
            if self.certifier is None:
                from native import Native
                self.certifier = Native(self.cfg,self.spec["seed"],self.weight)
            if not self.certifier.warm(data):
                self.stats["rejected_original_rows"] += 1
                return None
            now = time.monotonic()-self.start
            if now>self.spec["budget"]:
                self.stats["late_excluded"] += 1
                return None
            self.archive = [r for r in self.archive if not dominates(ab,(r["a"],r["b"]))]
            self.archive.append(dict(a=a,b=b,data=data,genes=genome,t=now,metrics=stat))
            self.trace.append([now,a,b])
            self.stats["insertions"] += 1
        return ab

    def evaluate(self, genes, goal, cap, screen, end):
        if self.remaining(end)<.012:
            return None
        capkey = None if cap is None else round(cap,5)
        key = (genes,goal,capkey)
        if key in self.seen:
            return self.seen[key]
        self.stats["attempts"] += 1
        blocks = self.dec.pairing(genes)
        pp = sum(len(p)==2 for _,_,pairs in blocks for p in pairs)
        if screen and cap is not None and lower_bound(self.cfg,self.dec.n,pp)>cap+TOL:
            self.stats["screened"] += 1
            return None
        if genes not in self.cache:
            try:
                batch = self.dec.build(genes,blocks)
            except ValueError as exc:
                if "Inconsistent event order" not in str(exc) and "Placement violates" not in str(exc):
                    raise
                self.stats["unusable_order"] += 1
                self.seen[key] = None
                return None
            self.cache[genes] = Retiming(batch,self.weight)
            if len(self.cache)>32:
                self.cache.popitem(last=False)
        self.cache.move_to_end(genes)
        self.stats["timing_lp_calls"] += 1
        data = self.cache[genes].solve(goal,cap,self.remaining(end))
        if data is None:
            self.stats["no_lp_candidate"] += 1
            return None
        ab = self.admit(data,genes,cap)
        if ab:
            self.seen[key] = ab
        return ab

    def parents(self,cap):
        known = [r for r in self.archive if r["genes"] is not None]
        if not known:
            return self.initial, self.initial
        if cap is None:
            key = self.rng.choice(("a","b"))
            picks = sorted(known,key=lambda r:r[key])
        else:
            picks = sorted(known,key=lambda r:abs(r["b"]-cap))
        return picks[0]["genes"],picks[1%len(picks)]["genes"]

    def cap(self,k):
        # Prespecified cap fractions in factorial runs prevent divergent thresholds from confounding the ablation.
        if k%9==0:
            return "B",None
        if k%9==1:
            return "A",None
        targets = (self.floor, 50*self.dec.n,
                   *(self.floor+(self.initial_b-self.floor)*f for f in (.04,.12,.25,.5,.75)))
        if self.spec.get("adaptive") and k%3==0 and len(self.archive)>1:
            points = sorted(self.archive,key=lambda r:r["a"])
            a,b = max(zip(points,points[1:]),key=lambda ab:(ab[1]["a"]-ab[0]["a"])*(ab[0]["b"]-ab[1]["b"]))
            return "A",(a["b"]+b["b"])/2
        return "A",targets[(k%9)-2]

    def modify(self, genes, other, coupled, within, width):
        rng = self.rng
        n = self.dec.n
        parts = [i for i in range(5*n) if within or i%5 not in (2,3)]
        count = max(2,min(len(parts),round(width*len(parts))))
        different = [i for i in parts if genes[i]!=other[i]]
        if coupled:
            target = (rng.choice(different)//5) if different and rng.random()<.65 else rng.randrange(n)
            blocks = self.dec.pairing(genes)
            group = next((pair for _,_,pairs in blocks for pair in pairs if self.dec.labels[target] in pair),())
            near = {target, *(self.dec.index[w] for w in group)}
            ch = genes[target*5+1]
            noise = {i:rng.random() for i in parts}
            parts.sort(key=lambda i:(i//5 in near, abs(i//5-target)<=1 or genes[(i//5)*5+1]==ch,
                                     i in different,noise[i]),reverse=True)
            chosen = parts[:count]
        else:
            # Raw agreement crossover, then randomly open matching variables to the identical size.
            rng.shuffle(different)
            same = [i for i in parts if genes[i]==other[i]]
            rng.shuffle(same)
            chosen = (different+same)[:count]
        child = list(genes)
        if coupled and rng.random()<.4:
            for i in chosen:
                if i%5==0:
                    child[i] = 1-child[i]
        for i in chosen:
            if rng.random()<.55:
                child[i] = rng.randrange(self.limits[i]) if rng.random()<.75 else other[i]
        return tuple(child)

    def local(self,end,method):
        coupled = method in ("domain","domain_no_bound","rl_domain","no_order","adaptive")
        within = method!="no_order"
        screen = method not in ("domain_no_bound","generic")
        k = 0
        while self.remaining(end)>.035:
            goal,cap = self.cap(k)
            a,b = self.parents(cap)
            if k%11==0:
                child = tuple(self.rng.randrange(v) if within or i%5 not in (2,3) else 0
                              for i,v in enumerate(self.limits))
            else:
                child = self.modify(a,b,coupled,within,self.spec.get("width",.3))
            self.evaluate(child,goal,cap,screen,end)
            k += 1

    def repair(self,end,method):
        from neighborhood import improve
        if self.remaining(end)<.15:
            return
        k = 0
        while self.remaining(end)>.25:
            goal,cap = self.cap(k)
            parents = sorted(self.archive,key=lambda r:abs(r["b"]-cap) if cap is not None else
                             r["b"] if goal=="B" else r["a"])
            parent = parents[0]
            partner = parents[min(1,len(parents)-1)]
            deadline = min(end,time.monotonic()+max(.65,self.spec["budget"]*.04))
            out,info = improve(self.cfg,parent,partner,goal,cap,deadline,self.rng,
                               method not in ("generic","generic_bound"),self.spec.get("width",.3),self.weight)
            self.subproblems.append(info)
            for d in out:
                self.admit(d,parent["genes"],cap)
            k += 1

    def global_search(self,end,method):
        from native import Native
        if self.remaining(end)<.1:
            return
        native = Native(self.cfg,self.spec["seed"],self.weight,learned=method in ("rl_domain","legacy"))
        self.policy = native.policy
        try:
            if method=="legacy":
                parent = min(self.archive,key=lambda r:(r["a"],r["b"]))
                stage1_end = self.start+self.spec["budget"]*.77
                solutions,entry = native.query("A",None,False,[parent],stage1_end)
                self.subproblems.append(entry)
                for d in solutions:
                    self.admit(d,None,None)
                parent = min(self.archive,key=lambda r:(r["a"],r["b"]))
                if self.remaining(end)>.1:
                    from witness import sparse_witness
                    values = sparse_witness(self.cfg,parent["data"])
                    for v in native.variables:
                        if v.vtype()!="CONTINUOUS" and not v.name.startswith("sync_"):
                            lo = float(values.get(v.name,0))
                            native.m.chgVarLb(v,lo)
                            native.m.chgVarUb(v,lo)
                    native.m.addCons(native.x.cmax<=parent["a"]+1e-6)
                    solutions,entry = native.query("B",None,False,[parent],end)
                    self.subproblems.append(entry|{"scope":"fixed first-stage structure and makespan"})
                    for d in solutions:
                        self.admit(d,None,None)
                self.archive = [min(self.archive,key=lambda r:(round(r["a"],5),r["b"]))]
                return
            k = 0
            while self.remaining(end)>.25:
                goal,cap = self.cap(k+1)
                parents = sorted(self.archive,key=lambda r:r["b"] if goal=="B" else r["a"])
                if cap is not None:
                    parents = [r for r in parents if r["b"]<=cap+TOL]
                deadline = min(end,time.monotonic()+max(1.2,self.spec["budget"]*(.14 if method=="epsilon" else .08)))
                out,info = native.query(goal,cap,method in ("domain","adaptive","rl_domain","no_order","generic_bound"),parents[:1],deadline)
                self.subproblems.append(info)
                for d in out:
                    self.admit(d,None,cap)
                k += 1
        finally:
            if native.agent is not None:
                self.policy = dict(native.policy,callback_calls=int(native.agent._callback_calls))
            native.close()

    def run(self):
        method = self.spec["method"]
        if self.spec.get("paired"):
            from neighborhood import improve
            parents = [self.archive[0]]
            g = tuple((i//5)%4 if i%5 in (2,3) else val for i,val in enumerate(self.initial))
            rr = Retiming(self.dec.build(g,self.dec.pairing(g)),self.weight)
            alt = rr.solve("B",None,self.remaining(self.end))
            if alt is not None:
                ab = self.admit(alt,g,None)
                if ab:
                    parents.append(dict(data=alt, a=ab[0], b=ab[1], genes=g))
            for idx in range(6):
                if self.remaining(self.end)<.3:
                    break
                first,second = parents[idx%len(parents)],parents[(idx+1)%len(parents)]
                goal,cap = (("A",None),("B",None),("A",self.initial_b*.8))[idx%3]
                deadline = min(self.end,self.start+self.spec["budget"]*(idx+1)/6)
                out,info = improve(self.cfg,first,second,goal,cap,deadline,random.Random(self.spec["seed"]+idx),
                                   method=="domain",self.spec.get("width",.3),self.weight)
                self.subproblems.append(info|{"parent_ab":[first["a"],first["b"]],"other_ab":[second["a"],second["b"]]})
                for data in out:
                    self.admit(data,first["genes"],cap)
        elif method in ("nsga2","moead"):
            run_evolution(self,method,self.end)
        elif method in ("epsilon","legacy"):
            self.global_search(self.end,method)
        else:
            budget = self.spec["budget"]
            share = self.spec.get("repair",.22)
            native_share = .32
            self.local(self.start+budget*(1-share-native_share),method)
            self.repair(self.start+budget*(1-native_share),method)
            self.global_search(self.end,method)
        if self.certifier is not None:
            self.certifier.close()
        elapsed = time.monotonic()-self.start
        front = []
        for i,r in enumerate(sorted(self.archive,key=lambda v:v["a"])):
            file = f"point_{i:03}.json.gz"
            with gzip.open(self.dest/file,"wt",encoding="utf-8",compresslevel=3) as f:
                json.dump(r["data"],f,separators=(",",":"),allow_nan=False)
            front.append({k:v for k,v in r.items() if k not in ("data","genes")} | {"schedule":file})
        result = dict(spec=self.spec,initial=self.initial_ab,config=asdict(self.cfg),front=front,
                      history=self.trace,stats=dict(self.stats),subproblems=self.subproblems,policy=self.policy,
                      search_wall_s=elapsed,shared_spbs_seconds=self.shared_cost,last_eligible_s=max(r["t"] for r in front))
        save(self.dest/"result.json",result)
        return result

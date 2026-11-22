"""Equal-evaluation comparisons and single-feature ablation. Use the unmodified evolutionary selectors."""
from collections import Counter, deque
import random
import time
from case_setup import CaseRoutes, EXPORT, NFE, OUT, Search, lower_bound, save, save_schedule, signature


def founders():
    return [(family,0,0,0,level) for family in range(6) for level in (17,0)]


class SeededPopulation(random.Random):
    """Supply the twelve common genotypes to the original random-population constructor."""
    def __init__(self,seed,limits):
        super().__init__(seed)
        self.prefix=deque((limit,x) for g in founders() for limit,x in zip(limits+(18,),g))

    def randrange(self,*args):
        if self.prefix:
            bound,value=self.prefix.popleft()
            assert args==(bound,)
            return value
        return super().randrange(*args)


def exported(points):
    points=sorted(points)
    kept={points[0],points[-1]}
    span=[max(1,max(p[i] for p in points)-min(p[i] for p in points)) for i in range(2)]
    while len(kept)<min(EXPORT,len(points)):
        def distance(p):
            return min(sum(((p[i]-q[i])/span[i])**2 for i in range(2)) for q in kept)
        kept.add(max((p for p in points if p not in kept),key=distance))
    return sorted(kept)


class Trial(Search):
    def __init__(self,case,seed,method):
        self.routes=CaseRoutes(case)
        self.cfg=self.routes.cfg
        self.initial,self.limits=self.routes.initial,self.routes.limits
        self.rng=SeededPopulation(seed,self.limits) if method in ("nsga2","moead") else random.Random(seed)
        self.initial_ab=self.routes.ab
        self.initial_b=self.initial_ab[1]
        self.floor=lower_bound(self.cfg,75,0)
        self.cache,self.archive,self.trace={},{},[]
        self.stats=Counter()
        self.checkpoints,self.starting_records={},[]
        self.inside=False
        self.method=method
        self.started=time.monotonic()

    def remaining(self,end):
        if not self.inside and self.stats["evaluations"]>=NFE:
            return 0
        return max(0,end-time.monotonic())

    def evaluate(self,genes,goal,cap,screen,end):
        assert self.stats["evaluations"]<NFE and self.remaining(end)>1
        self.inside=True
        try:
            value=super().evaluate(genes,goal,cap,screen,end)
        finally:
            self.inside=False
        count=self.stats["evaluations"]
        if self.method!="fixed" and count<=12:
            plan=tuple(genes)+(17 if goal=="A" else 0,)
            assert plan==founders()[count-1] and cap is None
            self.starting_records.append([plan,value])
        if count in (12,40,80,160):
            self.checkpoints[count]=sorted(self.archive)
        return value

    def domain(self,end):
        for g in founders():
            self.evaluate(g[:-1],"A" if g[-1]==17 else "B",None,False,end)
        rng=self.rng
        while self.remaining(end)>.04:
            k=self.stats["evaluations"]
            front=sorted(self.archive)
            point=rng.choice(front)
            genes,data,_=self.archive[point]
            child=list(genes)
            if rng.random()<.25:
                child[0]=rng.randrange(self.limits[0])
            else:
                jobs=sorted((j for j in data["jobs"] if j["product"]),
                            key=lambda j:j["loan_end"]-j["loan_start"],reverse=True)
                focus=rng.random()<.65
                priority=focus and self.method=="domain"
                self.stats["biased_selections"]+=int(priority)
                chosen=rng.choice(jobs[:12] if priority else jobs)
                group=self.routes.lookup[chosen["identity"]]
                child[rng.randrange(1,4)]=1+group+self.routes.n*rng.randrange(6)
            goal="B" if k%4==1 else "A"
            cap=None
            if k%4>=2:
                if len(front)>1:
                    i=rng.randrange(len(front)-1)
                    cap=(front[i][1]+front[i+1][1])/2
                else:
                    cap=point[1]*rng.uniform(.72,1)
            self.evaluate(tuple(child),goal,cap,True,end)


def run_cell(job):
    case,method,seed=job
    trial=Trial(case,seed,method)
    # Search.run dispatches the frozen NSGA-II, MOEA/D and fixed-route methods.
    elapsed=trial.run("domain" if method=="uniform" else method,900)
    if method!="fixed":
        assert trial.stats["evaluations"]==NFE and len(trial.starting_records)==12
    folder=OUT/case/f"{method}_{seed}"
    folder.mkdir(parents=True,exist_ok=True)
    selected=set(exported(trial.archive))
    entries=[]
    for (a,b),(genes,data,found) in sorted(trial.archive.items()):
        sig=signature(data)
        path=folder/(sig+".json.gz")
        save_schedule(path,data)
        entries.append(dict(a=a,b=b,genes=genes,found_s=found,sig=sig,file=path.name,submitted=(a,b) in selected))
    save(folder/"run.json",dict(case=case,method=method,seed=seed,warm=trial.initial_ab,cap=NFE,elapsed_s=elapsed,
         stats=trial.stats,archive=entries,trace=trial.trace,common_population=trial.starting_records,checkpoints=trial.checkpoints))
    return len(entries)

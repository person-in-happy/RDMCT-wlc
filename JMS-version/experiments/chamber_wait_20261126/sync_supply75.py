"""Allow same-pair, same-place simultaneous transfers in the first-parallel-cycle window."""
from collections import defaultdict
from pathlib import Path

import first_parallel75 as campaign
from ortools.sat.python import cp_model
from scale75 import source_timing

ORIGINAL = campaign.solve


class SynchronizableOrder:
    def __init__(self, engine, records, doc):
        self.engine=engine
        self.actions=engine.actions
        which={j["name"]:j["pair"] for j in doc["jobs"]}
        self.groups={i:(r.get("robot"),r["kind"],r["location"],which[r["job"]])
                     for i,r in enumerate(records) if r.get("job") in which
                     and r["kind"] not in ("al_pick","al_put")}

    def add_order(self,model,times,ref,window):
        from patterns import travel
        for a,b,lag in self.engine.edges:model.add(times[b]>=times[a]+lag)
        lo,hi,band=window
        for name,items in self.engine.resources.items():
            robot=name in ("ATR","VTR")
            seq=sorted(items,key=lambda item:(ref[item[0]],item[0]))
            def lag(a,b):
                if not robot:return a[2]
                x,y=self.actions[a[0]],self.actions[b[0]]
                return a[2]+int(travel(self.engine.cfg,name,x.location,y.location,y.kind))
            # Dominated transitive arcs may be dropped only for fixed prefixes/suffixes.
            before=[z for z in seq if ref[z[0]]<lo]
            loose=[z for z in seq if lo<=ref[z[0]]<hi]
            after=[z for z in seq if ref[z[0]]>=hi]
            latest={}
            loc=lambda z:self.actions[z[0]].location if robot else name
            def follows(b):
                for group in latest.values():
                    for a in group:model.add(times[b[0]]>=times[a[1]]+lag(a,b))
            for v in before:
                follows(v);latest[loc(v)]=[v]
            tails=defaultdict(list)
            for j,b in enumerate(loose):
                follows(b)
                for a in loose[:j]:
                    fwd=times[b[0]]>=times[a[1]]+lag(a,b)
                    if ref[b[0]]-ref[a[0]]>band:
                        model.add(fwd);continue
                    reverse=times[a[0]]>=times[b[1]]+lag(b,a)
                    can_sync=robot and a[0] in self.groups and self.groups[a[0]]==self.groups.get(b[0])
                    if can_sync:
                        x,y,z=[model.new_bool_var("") for _ in range(3)]
                        model.add_exactly_one(x,y,z);model.add(fwd).only_enforce_if(x)
                        model.add(reverse).only_enforce_if(y)
                        model.add(times[b[0]]==times[a[0]]).only_enforce_if(z)
                        is_equal=ref[b[0]]==ref[a[0]]
                        model.add_hint(x,int(not is_equal));model.add_hint(y,0);model.add_hint(z,int(is_equal))
                    else:
                        x=model.new_bool_var("");model.add(fwd).only_enforce_if(x)
                        model.add(reverse).only_enforce_if(~x);model.add_hint(x,1)
                tails[loc(b)].append(b)
            latest.update(tails)
            for b in after:
                follows(b);latest[loc(b)]=[b]


def solve(timing,engine,ref,limits,score,stage,budget):
    _,_,records,_,doc=source_timing()
    return ORIGINAL(timing,SynchronizableOrder(engine,records,doc),ref,limits,score,stage,budget)


if __name__=="__main__":
    campaign.solve=solve
    campaign.STAGES=[(2500,5200,220,0,22),(2500,5200,400,0,26),(2350,5300,560,0,32),
                     (2100,5200,660,0,36),(2320,5200,450,40,25),(2320,5200,450,120,28)]
    campaign.OUT=campaign.PARENT.parent/"n75_first_parallel_sync"
    campaign.__file__=__file__
    import argparse
    p=argparse.ArgumentParser();p.add_argument("--pause-after",type=int)
    campaign.run(p.parse_args().pause_after)


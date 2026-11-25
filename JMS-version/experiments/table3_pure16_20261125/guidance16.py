"""Use a product projection's chronology as a feasible-schedule neighborhood."""
from itertools import combinations

def set_times(cp, variables, x, template, labels, projected, distance):
    by_name={w["identity"]:i for i,w in enumerate(labels)}
    target={}
    for pair,group in template.items():
        for side,label in enumerate(group):
            if label not in by_name:continue
            i=by_name[label]
            prefix=f"prod_{pair}_{side}"
            for kind in ("origin_pick","al_put","al_pick","upper_put","source_pick","load","unload","destination_put","lower_pick","origin_put"):
                name=f"{kind}_{pair}" if kind in ("load","unload") else prefix+"_"+kind
                value=projected.get(f"{i}_{kind}",0)
                if name in target:assert value==target[name]
                target[name]=value
    hints={}
    for name,t in target.items():hints[name+"_s"]=t
    for robot,events in x.robots.items():
        active=[e["name"] for e in events if e["name"] in target]
        for left,right in combinations(active,2):
            name=f"order_{left}_{right}"
            if name not in variables:continue
            a,b=target[left],target[right]
            if a==b:continue
            hints[name]=int(a<b)
            if abs(a-b)>distance:cp.add(variables[name]==hints[name])
    for key,t in hints.items():
        if key in variables:cp.add_hint(variables[key],t)

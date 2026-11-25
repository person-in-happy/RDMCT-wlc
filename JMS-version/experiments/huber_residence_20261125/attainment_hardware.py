"""Bound shortest C at the H=10 Huber global B optimum, retaining all physical chamber-side transfers."""
import argparse
import hashlib
import json
from itertools import combinations,product
from pathlib import Path
from optimum_makespan_bound import conditioned,cp_model,STEPS,DUR,SLOTS

def hardware(doc,cap):
    scale=8
    m=conditioned(doc,cap)
    v={z.name:m.get_int_var_from_proto_index(j) for j,z in enumerate(m.proto.variables)}
    actions={}
    for c,howmany in ((0,2),(1,SLOTS)):
        for q in range(howmany):
            active=v[f"use{c,q}"];first=active if not c or q==0 else m.new_constant(0)
            if not c or q==SLOTS-1:last=active
            elif q==SLOTS-2:last=v["use(1, 4)"].Not()
            else:last=m.new_constant(0)
            for name,on in (("fl",active),("bu",active),("bl",first),("fu",last)):
                t=m.new_int_var(0,scale*int(doc["config"]["horizon"]),f"pt{c}{q}{name}")
                m.add(t==0).only_enforce_if(on.Not())
                actions[c,q,name]=(t,on)
            def act(tag):return actions[c,q,tag][0]
            start=v[f"start{c,q}"];end=start+(90 if c else 180)*scale
            m.add(act("fl")+scale==start).only_enforce_if(active)
            m.add(act("fl")>=act("bl")+3*scale).only_enforce_if(first)
            m.add(act("fu")>=end).only_enforce_if(last)
            m.add(act("bu")>=act("fu")+3*scale).only_enforce_if(last)
            m.add(act("bu")>=end+2*scale).only_enforce_if(active)
            if q:
                prev=actions[c,q-1,"bu"][0]
                m.add((act("bl") if not c else act("fl"))>=prev+scale).only_enforce_if(active)
    for i in range(8):
        c=0 if i<4 else 1
        for q in range(2 if c==0 else 4):
            select=v[f"w{i}_{c}_{q}_1"]
            m.add(v[f"{i}_load"]==actions[c,q,"fl"][0]).only_enforce_if(select)
            f,tag=(q,"fu") if not c else (q+1,"bu")
            m.add(v[f"{i}_unload"]==actions[c,f,tag][0]).only_enforce_if(select)
    ops=[(c,t,on) for (c,q,k),(t,on) in actions.items()]
    for (c,t,on),(d,u,un) in combinations(ops,2):
        first=m.new_bool_var("")
        lag=(1+(2 if c!=d else 0))*scale
        m.add(u>=t+lag).only_enforce_if([on,un,first])
        m.add(t>=u+lag).only_enforce_if([on,un,first.Not()])
    for c,t,on in ops:
        for i,k in product(range(8),("source_pick","destination_put")):
            u=v[f"{i}_{k}"];first=m.new_bool_var("")
            m.add(u>=t+3*scale).only_enforce_if([on,first])
            m.add(t>=u+3*scale).only_enforce_if([on,first.Not()])
    for c,items in ((0,range(4)),(1,range(4,8))):
        pos={}
        for i in items:
            pos[i]=m.new_int_var(0,3,f"pos{i}")
            m.add(pos[i]==sum(q*v[f"w{i}_{c}_{q}_1"] for q in range(2 if not c else 4)))
        for i,j in combinations(items,2):
            same=m.new_bool_var("")
            m.add(pos[i]==pos[j]).only_enforce_if(same)
            m.add(pos[i]!=pos[j]).only_enforce_if(same.Not())
            for name,dur in zip(STEPS,DUR):
                if name in ("al_put","al_pick","origin_pick","origin_put"):continue
                left,right=v[f"{i}_{name}"],v[f"{j}_{name}"]
                order=m.new_bool_var("");sy=m.new_bool_var("")
                m.add(sy<=same);m.add(left==right).only_enforce_if(sy)
                m.add(left+scale*dur<=right).only_enforce_if([order,sy.Not()])
                m.add(right+scale*dur<=left).only_enforce_if([order.Not(),sy.Not()])
    C=v["makespan"];m.minimize(C);return m,C

if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--seconds",type=int,default=90);p.add_argument("--cap",type=int,default=610)
    a=p.parse_args();root=Path(__file__).resolve().parents[2]/"results/huber_residence_20261125"
    src=root/"witnesses/D_n8_H10_mixed_dual/schedule.json"
    out=root/"frontier"/f"H10_attainment_hardware_{a.cap}";out.mkdir(exist_ok=True,parents=True)
    doc=json.loads(src.read_bytes());s=cp_model.CpSolver()
    s.parameters.num_workers=1;s.parameters.max_time_in_seconds=a.seconds;s.parameters.log_search_progress=True;s.parameters.log_to_stdout=False
    m,C=hardware(doc,a.cap)
    with (out/"cp.log").open("w",encoding="utf8",buffering=1) as f:
        s.log_callback=lambda line:f.write(line.rstrip()+"\n");status=s.solve(m)
    bound=a.cap+0.125 if status==cp_model.INFEASIBLE else s.best_objective_bound/8
    record=dict(status=s.status_name(status),cap=a.cap,seconds=s.wall_time,workers=1,lower_C=bound,
                projected_C=s.objective_value/8 if status in (cp_model.OPTIMAL,cp_model.FEASIBLE) else None,
                source_sha256=hashlib.sha256(src.read_bytes()).hexdigest(),code={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (Path(__file__),Path(__file__).with_name("optimum_makespan_bound.py"))})
    (out/"result.json").write_text(json.dumps(record,indent=2));print(record,flush=True)

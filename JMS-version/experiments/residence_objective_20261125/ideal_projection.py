"""Retain every chamber-side VTR action, including counterpart pairs containing only dummies."""
import argparse
import hashlib
import itertools
import json
from pathlib import Path

from tight_primary import tightened,cp_model


def projection(doc,cap,pin=False):
    m=tightened(doc,cap,pin)
    vs={v.name:m.get_int_var_from_proto_index(i) for i,v in enumerate(m.proto.variables)}
    products=sorted((w for w in doc["jobs"] if w["product"]),key=lambda w:(w["pjob"],w["pjob_index"]))
    modes={p["id"]:p["mode"] for p in doc["pairs"]}
    cycles={(c["chamber"]-2,c["index"]):c for c in doc["cycles"] if c["mode"]!="clean"}
    pe={(e["pair"],e["kind"]):e["start"] for e in doc["events"] if "pair" in e}
    keep={}
    for c in range(2):
        keep[c,0]=m.new_constant(0)
        keep[c,4]=m.new_constant(0)
        for q in range(1,4):
            carried=m.new_bool_var(f"carried_{c}_{q}")
            starts=[vs[f"w{i}_{c}_{q-1}_1"] for i,w in enumerate(products) if modes[w["pair"]]=="2x2"]
            m.add_max_equality(carried,starts)
            keep[c,q]=carried
    actions={}
    for c,q in itertools.product(range(2),range(4)):
        active=vs[f"use{c,q}"]
        s=vs[f"start{c,q}"]
        end=s+90+90*vs[f"full{c,q}"]
        first=m.new_bool_var(f"new_chain_{c}_{q}")
        last=m.new_bool_var(f"end_chain_{c}_{q}")
        m.add(first==active-keep[c,q])
        m.add(last==active-keep[c,q+1])
        for tag,enabled in (("front_load",active),("back_unload",active),("back_load",first),("front_unload",last)):
            t=m.new_int_var(0,int(doc["config"]["horizon"]),f"ch_{c}_{q}_{tag}")
            actions[c,q,tag]=(t,enabled)
            m.add(t==0).only_enforce_if(enabled.Not())
            cy=cycles.get((c,q))
            if pin and cy is not None:
                front=cy["front"]
                back,=(p for p in cy["pairs"] if p!=front)
                pair=front if tag.startswith("front") else back
                kind="pair_load" if tag.endswith("load") and not tag.endswith("unload") else "pair_unload"
                m.add(t==round(pe[pair,kind])).only_enforce_if(enabled)
        def a(i,tag): return actions[c,i,tag][0]
        m.add(a(q,"front_load")+1==s).only_enforce_if(active)
        m.add(a(q,"front_load")>=a(q,"back_load")+3).only_enforce_if(first)
        m.add(a(q,"front_unload")>=end).only_enforce_if(last)
        m.add(a(q,"back_unload")>=a(q,"front_unload")+3).only_enforce_if(last)
        m.add(a(q,"back_unload")>=end+2).only_enforce_if(keep[c,q+1])
        if q:
            m.add(a(q,"front_load")>=a(q-1,"back_unload")+1).only_enforce_if(keep[c,q])
            m.add(a(q,"back_load")>=a(q-1,"back_unload")+1).only_enforce_if(first)
    for i,w in enumerate(products):
        mode=modes[w["pair"]]
        m.add(vs[f"{i}_unload"]-vs[f"{i}_load"]==181+(7 if mode=="2x2" else 0))
        for c,q,side in itertools.product(range(2),range(4),range(2)):
            key=f"w{i}_{c}_{q}_{side}"
            if key not in vs: continue
            m.add(vs[f"{i}_load"]==actions[c,q,"front_load" if side else "back_load"][0]).only_enforce_if(vs[key])
            exit_q=q+1 if mode=="2x2" else q
            exit_tag="front_unload" if mode=="4x1" and side else "back_unload"
            m.add(vs[f"{i}_unload"]==actions[c,exit_q,exit_tag][0]).only_enforce_if(vs[key])
    ops=[(c,t,on) for (c,q,k),(t,on) in actions.items()]
    for (c,t,on),(d,u,un) in itertools.combinations(ops,2):
        earlier=m.new_bool_var("")
        lag=1+(2 if c!=d else 0)
        m.add(u>=t+lag).only_enforce_if([on,un,earlier])
        m.add(t>=u+lag).only_enforce_if([on,un,earlier.Not()])
    for c,t,on in ops:
        for i,w in enumerate(products):
            for name in ("source_pick","destination_put"):
                u=vs[f"{i}_{name}"]
                earlier=m.new_bool_var("")
                m.add(u>=t+3).only_enforce_if([on,earlier])
                m.add(t>=u+3).only_enforce_if([on,earlier.Not()])
    return m


if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--h",type=int,default=10)
    p.add_argument("--seconds",type=int,default=90)
    args=p.parse_args()
    base=Path(__file__).resolve().parents[2]/"results/residence_objective_20261125"
    src=base/f"best_reuse/n8_H{args.h}/ideal_fixed/schedule.json"
    doc=json.loads(src.read_bytes())
    ref=cp_model.CpSolver()
    ref.parameters.num_workers=1
    assert ref.solve(projection(doc,554,True))==cp_model.OPTIMAL
    out=base/"best_reuse/ideal_projection"
    out.mkdir(parents=True,exist_ok=True)
    s=cp_model.CpSolver()
    s.parameters.num_workers=2
    s.parameters.max_time_in_seconds=args.seconds
    s.parameters.log_search_progress=True
    s.parameters.log_to_stdout=False
    m=projection(doc,553)
    with (out/"cp.log").open("w",encoding="utf8",buffering=1) as f:
        s.log_callback=lambda log:f.write(log.rstrip()+"\n")
        status=s.solve(m)
    result=dict(status=s.status_name(status),seconds=s.wall_time,cap=553,branches=s.num_branches,
                pinned_native_witness_sha256=hashlib.sha256(src.read_bytes()).hexdigest(),
                code={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in
                      (Path(__file__),Path(__file__).with_name("tight_primary.py"),Path(__file__).with_name("primary_relaxation.py"))})
    if status in (cp_model.OPTIMAL,cp_model.FEASIBLE):
        result["projected_only"]={v.name:s.value(m.get_int_var_from_proto_index(i)) for i,v in enumerate(m.proto.variables)
                                  if v.name and (v.name[0].isdigit() or v.name.startswith(("w","ch_","use","full","start")))}
    (out/"result.json").write_text(json.dumps(result,indent=2),encoding="utf8")
    print(result["status"],result["seconds"],flush=True)

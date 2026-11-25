"""Chamber handoffs and vacuum-store trips for one exhaustive chronological batch pattern."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
import itertools
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
import msvcrt

import ordered_projection as order
from port_projection import add_ports
from partition import prepare,atom
from batch_lower import OUT
from ortools.sat.python import cp_model

HERE=Path(__file__).resolve()


def exact_sides(m,v,pattern,cap,store_moves):
    groups=dict(pattern);keys=sorted(groups)
    tmax=cap+500
    true=m.new_constant(1)
    def t(name):return m.new_int_var(0,tmax,name)
    def approx_interval(a,b,active,where):
        size=t("")
        where.append(m.new_optional_interval_var(a,size,b,active,""))
    def sep(a,b,delay,flags):
        z=m.new_bool_var("")
        m.add(a>=b+delay).only_enforce_if([*flags,z]);m.add(b>=a+delay).only_enforce_if([*flags,~z])
    chain={}
    for g,mode in groups.items():
        if mode==2 and groups.get(g+1)==2 and g//10==(g+1)//10:
            chain[g]=m.new_bool_var(f"next_chain_{g}")
    second={g:t(f"second_{g}") for g,k in groups.items() if k==2}
    # One pair item consists of (first load, final unload, active, incoming products).
    sides={}
    dummy_head={};dummy_tail={}
    events=[]
    for j,g in enumerate(keys):
        start,bl,fl,fu,bu=(v[f"{s}_{g}"] for s in ("start","bl","fl","fu","bu"))
        members=[i for i,item in enumerate(pattern) if item[0]==g]
        if groups[g]==1:
            for side,ld,ul in ((0,bl,bu),(1,fl,fu)):
                nprod=sum(v[f"front_{i}"] if side else 1-v[f"front_{i}"] for i in members)
                sides[g,side]=(ld,ul,true,nprod)
                events.extend([(ld,true,g//10),(ul,true,g//10)])
            continue
        keep=chain.get(g,m.new_constant(0))
        incoming=chain.get(g-1,m.new_constant(0)) if (g-1)//10==g//10 else m.new_constant(0)
        lead=~incoming
        tail=~keep
        m.add(second[g]>=start+94)
        if g in chain:
            m.add(second[g]==v[f"start_{g+1}"]).only_enforce_if(keep)
            m.add(bu>=second[g]+92).only_enforce_if(keep)
            m.add(second[g+1]-1>=bu+1).only_enforce_if(keep)
        m.add(bu>=second[g]+93).only_enforce_if(tail)
        dl,du=t(f"dhead_load_{g}"),t(f"dhead_unload_{g}")
        tl,tu=t(f"dtail_load_{g}"),t(f"dtail_unload_{g}")
        m.add(fl>=dl+3).only_enforce_if(lead)
        m.add(du>=start+92).only_enforce_if(lead)
        m.add(second[g]-1>=du+1).only_enforce_if(lead)
        m.add(tl+1==second[g]).only_enforce_if(tail)
        m.add(tu>=second[g]+90).only_enforce_if(tail)
        m.add(bu>=tu+3).only_enforce_if(tail)
        dummy_head[g]=(dl,du,lead); dummy_tail[g]=(tl,tu,tail)
        sides[g,"prod"]=(fl,bu,true,len(members))
        sides[g,"head"]=(dl,du,lead,0)
        sides[g,"tail"]=(tl,tu,tail,0)
        events.extend([(fl,true,g//10),(bu,true,g//10),(dl,lead,g//10),(du,lead,g//10),(tl,tail,g//10),(tu,tail,g//10)])
    for g in keys:
        if g-1 in groups and g//10==(g-1)//10:
            ld=v[f"bl_{g}"] if groups[g]==1 else dummy_head[g][0]
            prev=v[f"bu_{g-1}"]
            flags=[] if g-1 not in chain else [~chain[g-1]]
            m.add(ld>=prev+1).only_enforce_if(flags)
    for (a,on,c),(b,un,d) in itertools.combinations(events,2):
        sep(a,b,1+2*(c!=d),[on,un])
    vin=[];vout=[];stock=[];vault=[]
    for i in range(16):
        ld,ul,sp,dp=(v[f"{s}_{i}"] for s in ("ld","ul","sp","dp"))
        m.add(ld+1-sp<=100)
        m.add(dp+1-ul<=100)
        m.add(ul-ld-1<=280)
        for left,r,s in (("al","origin_pick",4),("up","ap",4),("origin_put","lp",4),
                         ("ap","al",-4),("sp","up",-4),("lp","dp",-1)):
            m.add(v[f"{left}_{i}"]-v[f"{r}_{i}"]+s<=100)
        approx_interval(sp,ld+1,true,vin);approx_interval(ul,dp+1,true,vout)
        for op,on,c in events:
            sep(op,sp,3,[on]);sep(op,dp,3,[on])
    if not store_moves:
        return
    for pair,(ld,ul,on,nprod) in sides.items():
        mode=groups[pair[0]]
        duration=180 if pair[1] in (0,1,"prod") else 90
        m.add(ul-ld-1<=duration+100).only_enforce_if(on)
        for r in (0,1):
            if isinstance(nprod,int):
                if nprod>=2-r:continue
                active=on
            else:
                active=m.new_bool_var("")
                # Product counts in a full batch are known per pattern but free per side.
                m.add(nprod<2-r).only_enforce_if(active)
                m.add(nprod>=2-r).only_enforce_if(~active)
            sp,dp=t(f"vs_in_{pair}_{r}"),t(f"vs_out_{pair}_{r}")
            m.add(ld>=sp+3).only_enforce_if(active)
            m.add(dp>=ul+3).only_enforce_if(active)
            m.add(ld+1-sp<=100).only_enforce_if(active)
            m.add(dp+1-ul<=100).only_enforce_if(active)
            approx_interval(sp,ld+1,active,vin);approx_interval(ul,dp+1,active,vout)
            approx_interval(sp,dp+1,active,stock)
            vault.extend([(sp,active,pair,0),(dp,active,pair,1)])
    # Product-only inflow and outflow already have their separate two-gripper
    # limits in the parent projection. Dummies can use any of the four grippers.
    for events_cap,capn in ((vin+vout,4),(stock,8)):
        if events_cap:m.add_cumulative(events_cap,[1]*len(events_cap),capn)
    for vtime,on,pair,direction in vault:
        for t0,ok,ch in events:sep(vtime,t0,3,[on,ok])
        for i,typ in itertools.product(range(16),("sp","dp")):sep(vtime,v[f"{typ}_{i}"],3,[on])
    for (a,on,pa,da),(b,un,pb,db) in itertools.combinations(vault,2):
        if pa!=pb or da!=db:sep(a,b,1,[on,un])


def cache_dir(kind,cap,treatment):
    dest=OUT/treatment/f"{kind}_{cap}"
    dest.mkdir(parents=True,exist_ok=True)
    return dest


def array(items):
    return tuple(tuple(row) for row in items)


def inherited(kind,cap,table,with_vault):
    result={}
    for typ in ["partitions","exposures"]+(["tool_capacity"] if with_vault else []):
        for directory in (OUT/typ).glob(kind+"_*"):
            previous_cap=int(directory.name.split("_")[-1])
            for file in directory.glob("p*/result.json"):
                try:
                    item=json.loads(file.read_bytes())
                except (OSError,json.JSONDecodeError):
                    continue
                if "batch_pattern" not in item:continue
                key=array(item["batch_pattern"])
                # An identical pattern has a global lower bound truncated by the ancestor cap.
                lb=min(item["lower"],previous_cap+1)
                if lb>result.get(key,(0,None))[0]:
                    result[key]=(lb,file)
    return result


def worker(kind,cap,budget,index,with_vault):
    root=cache_dir(kind,cap,"tool_capacity" if with_vault else "exposures")
    where=root/f"p{index:04d}";where.mkdir(exist_ok=True)
    lock=(where/"active.lock").open("a+b")
    try: msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
    except OSError:return
    f=where/"result.json"
    table=prepare(kind,cap); ptn,cycles=table[index]
    identity={p:sha256(HERE.with_name(p).read_bytes()).hexdigest() for p in
              ("batch_lower.py","ordered_projection.py","port_projection.py","partition.py",HERE.name)}
    rec=json.loads(f.read_bytes()) if f.exists() else dict(signature=identity,batch_pattern=ptn,used=0,lower=0,upper=None)
    assert rec["signature"]==identity
    if rec.get("status") in ("INFEASIBLE","OPTIMAL") or rec["used"]>=budget:return
    lb,w=inherited(kind,cap,table,with_vault).get(ptn,(0,None))
    if w!=f and lb>rec["lower"]:
        rec.update(lower=lb,parent=str(w.relative_to(OUT)),parent_sha256=sha256(w.read_bytes()).hexdigest())
    if rec["lower"]>cap:
        rec["status"]="INFEASIBLE";atom(f,rec);return
    order.patterns=lambda nf,nd,cap,ready:{ptn:cycles}
    m,c=add_ports(kind,cap)
    v={s.name:m.get_int_var_from_proto_index(i) for i,s in enumerate(m.proto.variables) if s.name}
    exact_sides(m,v,ptn,cap,with_vault)
    v={s.name:m.get_int_var_from_proto_index(i) for i,s in enumerate(m.proto.variables) if s.name}
    m.add(c>=int(rec["lower"]))
    hint=where/"projection.json"
    if hint.exists():
        for k,val in json.loads(hint.read_bytes()).items():
            if k in v:m.add_hint(v[k],val)
        m.add(c<=rec["upper"])
    solver=cp_model.CpSolver();solver.parameters.num_workers=1;solver.parameters.random_seed=1
    solver.parameters.max_time_in_seconds=budget-rec["used"]
    solver.parameters.log_search_progress=True;solver.parameters.log_to_stdout=False
    prior=rec["used"];start=time.monotonic();mutex=threading.Lock();stop=threading.Event()
    def store():
        rec["used"]=min(budget,prior+time.monotonic()-start);atom(f,rec)
    def bound(lb):
        with mutex:
            if lb>rec["lower"]:rec["lower"]=lb;store()
    class Recorder(cp_model.CpSolverSolutionCallback):
        def on_solution_callback(self):
            with mutex:
                if rec["upper"] is None or self.objective_value<rec["upper"]:
                    rec["upper"]=int(self.objective_value)
                    doc={k:self.value(var) for k,var in v.items()};doc["C"]=int(self.objective_value)
                    atom(hint,doc);store()
    def heart():
        while not stop.wait(3):
            with mutex:store()
    beat=threading.Thread(target=heart,daemon=True);beat.start()
    solver.best_bound_callback=bound
    try:
        with (where/"cp.log").open("a",encoding="utf8",buffering=1) as logfile:
            solver.log_callback=lambda s:logfile.write(s.rstrip()+"\n")
            result=solver.solve(m,Recorder())
    finally:
        stop.set();beat.join()
    rec["status"]=solver.status_name(result)
    if rec["status"]=="MODEL_INVALID":raise ValueError(m.validate())
    rec["lower"]=cap+1 if result==cp_model.INFEASIBLE else max(rec["lower"],solver.best_objective_bound)
    store()


def controller(kind,cap,budget,workers,vault):
    root=cache_dir(kind,cap,"tool_capacity" if vault else "exposures")
    lock=(root/"controller.lock").open("a+b")
    try: msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
    except OSError:return
    start=time.monotonic();table=prepare(kind,cap)
    old=inherited(kind,cap,table,vault)
    count=len(table)
    cmd=[sys.executable,"-B","-X","utf8",str(HERE),kind,str(cap),"--budget",str(budget)]
    if vault:cmd+=["--vault"]
    def dispatch(i):return subprocess.run(cmd+["--index",str(i)],check=True)
    order_=sorted(range(count),key=lambda i:0 if old.get(table[i][0],(0,None))[0]>cap else 1)
    with ThreadPoolExecutor(max_workers=workers) as ex:
        jobs=[ex.submit(dispatch,i) for i in order_]
        while True:
            done=sum(j.done() for j in jobs)
            records=[json.loads(f.read_bytes()) for f in root.glob("p*/result.json")]
            estimates={array(r["batch_pattern"]):r["lower"] for r in records}
            lower=min(max(old.get(ptn,(0,None))[0],estimates.get(ptn,0)) for ptn,_ in table)
            best=min((r["upper"] for r in records if r["upper"] is not None),default=None)
            elapsed=time.monotonic()-start
            eta=(count-done)*((budget+2)/workers if done<1 else elapsed/done)
            data=dict(count=count,completed=done,failed=sum(j.done() and j.exception() is not None for j in jobs),
                      lower=lower,upper=best,infeasible=sum(r.get("status")=="INFEASIBLE" for r in records),
                      elapsed_s=elapsed,remaining_s=eta,estimated_total_s=elapsed+eta,cap=cap,workers=workers,
                      budget_per_pattern_s=budget,full_inventory=vault)
            atom(root/"summary.json",data)
            print(f"Cap {cap} {kind}, {done}/{count}, failed {data['failed']}, LB {lower}, relaxed UB {best}, wall {elapsed:.0f}s, ETA {eta:.0f}s",flush=True)
            if done==count:break
            time.sleep(3)
        for j in jobs:j.result()


if __name__=="__main__":
    a=argparse.ArgumentParser();a.add_argument("kind");a.add_argument("cap",type=int)
    a.add_argument("--budget",type=int,default=24);a.add_argument("--workers",type=int,default=2)
    a.add_argument("--vault",action="store_true");a.add_argument("--index",type=int)
    args=a.parse_args()
    if args.index is None:controller(args.kind,args.cap,args.budget,args.workers,args.vault)
    else:worker(args.kind,args.cap,args.budget,args.index,args.vault)

"""Product-only chamber and load-lock relaxation with chronological batch enumeration."""
import argparse
from functools import partial
from hashlib import sha256
import itertools
import json
from pathlib import Path
import time

from ortools.sat.python import cp_model
from batch_lower import OUT, SOURCE


def patterns(nf,nd,cap,ready):
    """Each wafer is indexed by its first productive batch; within-batch labels are exchangeable."""
    found = {}
    n = nf+nd
    def possible(tails):
        return all(t+55*((n-1-i)//2)<=cap for i,t in enumerate(sorted(tails)))
    def visit(f,d,prev,clock,releases,assign,modes):
        if not (f or d):
            if possible(releases):
                found[tuple(assign)] = tuple(tuple(x) for x in modes)
            return
        k=n-f-d
        if not possible(releases+[max(clock,ready[j])+220 for j in range(k,n)]):
            return
        for mode,rem,max_load,tail in ((1,f,4,220),(2,d,2,226)):
            for count in range(1,min(rem,max_load)+1):
                for c,(prior,last) in enumerate(prev):
                    if not k and c:
                        continue
                    lag = (188 if prior==1 else 94 if mode==2 else 192) if prior else 0
                    start=max(clock,ready[k+count-1],last+lag)
                    if start+tail>cap:
                        continue
                    p=prev.copy()
                    p[c]=(mode,start)
                    group=10*c+len(modes[c])
                    modes[c].append(mode)
                    visit(f-(count if mode==1 else 0),d-(count if mode==2 else 0),
                          p,start,releases+[start+tail]*count,assign+[(group,mode)]*count,modes)
                    modes[c].pop()
    visit(nf,nd,[(0,0),(0,0)],0,[],[],[[],[]])
    return found


def build(kind,cap):
    nf,nd = {"4x1":(16,0),"2x2":(0,16),"mixed":(8,8)}[kind]
    archive=OUT/f"batch_bound_{'mixed' if nf and nd else 'pure_'+kind}.json"
    base=json.loads(archive.read_bytes())
    ready=base["ready"]
    collection=patterns(nf,nd,cap,ready)
    model=cp_model.CpModel()
    H=cap+160
    var = partial(model.new_int_var,0,H)
    def ge(a,b,delta,flags=()):
        return model.add(a>=b+delta).only_enforce_if(flags)
    def different_time(t,u,lag_forward,lag_back,flags):
        z=model.new_bool_var("")
        ge(u,t,lag_forward,[*flags,z])
        ge(t,u,lag_back,[*flags,~z])
    def occupancy(t,u,res,tail,name):
        d=var("")
        resources[res].append(model.new_interval_var(t,d,u+tail,name))

    if not collection:
        raise ValueError("Cap is below every aggregate batch pattern")
    mkeys=sorted({g for key in collection for (g,k) in key})
    ids={g:i for i,g in enumerate(mkeys)}
    body=[]; columns=[]
    for idx in range(16):
        body.append(model.new_int_var(0,len(mkeys)-1,f"batch_{idx}"))
    columns.extend(body)
    kinds={g:model.new_int_var(0,2,f"kind_{g}") for g in mkeys}
    columns.extend(kinds.values())
    configs=[]
    for batches,modes in collection.items():
        vals=dict(batches)
        configs.append(tuple(ids[g] for g,k in batches)+tuple(vals.get(g,0) for g in mkeys))
    model.add_allowed_assignments(columns,configs)
    groups={}
    v_events=[]
    for g in mkeys:
        active=model.new_bool_var("")
        full=model.new_bool_var("")
        dual=model.new_bool_var("")
        model.add(active==full+dual)
        model.add(kinds[g]==full+2*dual)
        start,bl,fl,fu,bu=[var(f"{s}_{g}") for s in ("start","bl","fl","fu","bu")]
        model.add(fl+1==start).only_enforce_if(active)
        ge(fl,bl,3,[full])
        ge(fu,start,180,[full])
        ge(bu,fu,3,[full])
        # A double exposure enters the front and exits the back of its second visit.
        ge(bu,start,186,[dual])
        if g-1 in groups and (g-1)//10==g//10:
            a=groups[g-1]
            ge(bl,a["bu"],1,[full,a["full"]])
            ge(start,a["start"],188,[active,a["full"]])
            ge(start,a["start"],94,[dual,a["dual"]])
            ge(start,a["start"],192,[full,a["dual"]])
        events=[(bl,full),(fl,active),(fu,full),(bu,active)]
        for u,on in events:
            v_events.append((u,on,g//10))
        groups[g]=dict(start=start,bl=bl,fl=fl,fu=fu,bu=bu,full=full,dual=dual)
    # Every chamber-side action blocks the single VTR, including all-dummy sides in a full cycle.
    for (t,on,c),(u,un,d) in itertools.combinations(v_events,2):
        lag=1+2*(c!=d)
        different_time(t,u,lag,lag,[on,un])
    side_load=[]; side_unload=[]
    for g in mkeys:
        z=groups[g]
        # Front-side (side=1) unloads through the back in a dual exposure.
        uf=var("")
        model.add(uf==z["fu"]).only_enforce_if(z["full"])
        model.add(uf==z["bu"]).only_enforce_if(z["dual"])
        side_load.extend([z["bl"],z["fl"]])
        side_unload.extend([z["bu"],uf])
    resources={key:[] for key in ("AL","U","L","Vin","Vout")}
    atr=[]; slot_ids=[]; rows=[]; all_start=[]; finish=[]
    for i,grow in enumerate(body):
        side=model.new_bool_var(f"front_{i}")
        place=model.new_int_var(0,2*len(mkeys)-1,f"pair_{i}")
        model.add(place==2*grow+side)
        slot_ids.append(place)
        mode=model.new_int_var(1,2,"")
        model.add_element(grow,list(kinds.values()),mode)
        model.add(side>=mode-1)
        al,ap,up,sp,load,unload,dp,lp=[var(f"{k}_{i}") for k in ("al","ap","up","sp","ld","ul","dp","lp")]
        stage=var("")
        model.add_element(grow,[z["start"] for z in groups.values()],stage)
        all_start.append(stage)
        model.add(stage>=ready[i])
        if i:
            ge(stage,all_start[i-1],0)
            same=model.new_bool_var("")
            model.add(grow==body[i-1]).only_enforce_if(same)
            model.add(grow!=body[i-1]).only_enforce_if(~same)
            ge(al,rows[-1][0],28,[same])
        model.add_element(place,side_load,load)
        model.add_element(place,side_unload,unload)
        model.add(al>=7)
        for a,b,l in ((ap,al,24),(up,ap,7),(sp,up,34),(load,sp,3),(dp,unload,3),(lp,dp,26)):
            ge(a,b,l)
        occupancy(al,ap,"AL",4,"")
        occupancy(up,sp,"U",31,"")
        occupancy(dp,lp,"L",29,"")
        occupancy(sp,load,"Vin",1,"")
        occupancy(unload,dp,"Vout",1,"")
        atr.append((al,ap,up,lp))
        rows.append((al,ap,up,sp,load,unload,dp,lp))
        finish.append(lp+11)
        for t,on,c in v_events:
            for transfer in (sp,dp):
                different_time(t,transfer,3,3,[on])
    for p in range(2*len(mkeys)):
        occupants=[]
        for s in slot_ids:
            present=model.new_bool_var("")
            model.add(s==p).only_enforce_if(present)
            model.add(s!=p).only_enforce_if(~present)
            occupants.append(present)
        model.add(sum(occupants)<=2)
    for name,intervals in resources.items():
        model.add_cumulative(intervals,[1]*len(intervals),1 if name=="AL" else 2)
    # Aligner/LL access competes for the atmospheric robot. Potential paired transfers at one
    # LL are left free. Operations involving the aligner are always individual products.
    for i,j in itertools.combinations(range(16),2):
        for t in atr[i][:2]:
            for u in atr[j][2:]:
                different_time(t,u,7,7,[])
        for t in atr[j][:2]:
            for u in atr[i][2:]:
                different_time(t,u,7,7,[])
        for t,u in ((atr[i][2],atr[j][3]),(atr[j][2],atr[i][3])):
            different_time(t,u,4,4,[])
        for t,u in ((rows[i][3],rows[j][6]),(rows[j][3],rows[i][6])):
            different_time(t,u,1,1,[])
    cmax=model.new_int_var(base["lower"],cap,"C")
    model.add_max_equality(cmax,finish)
    model.minimize(cmax)
    return model,cmax,collection


def run(args):
    target=OUT/"ordered"/f"{args.kind}_{args.cap}"
    target.mkdir(parents=True,exist_ok=True)
    path=target/"status.json"
    sig=sha256(Path(__file__).read_bytes()).hexdigest()
    old=json.loads(path.read_bytes()) if path.exists() else dict(code=sig,charged=0,lower=0)
    assert old["code"]==sig
    if old.get("status") in ("INFEASIBLE","OPTIMAL") or old["charged"]>=args.budget:
        print(f"Cached {old.get('status')}, remaining 0s.",flush=True)
        return
    model,cmax,pats=build(args.kind,args.cap)
    if old["lower"]:
        model.add(cmax>=int(old["lower"]))
    solver=cp_model.CpSolver()
    solver.parameters.num_workers=args.workers
    solver.parameters.random_seed=1
    spent=old["charged"]
    solver.parameters.max_time_in_seconds=args.budget-spent
    solver.parameters.log_search_progress=True
    solver.parameters.log_to_stdout=False
    begin=time.monotonic()
    def save():
        old["charged"]=min(args.budget,spent+time.monotonic()-begin)
        old["remaining_s"]=max(0,args.budget-old["charged"])
        tmp=path.with_suffix(".tmp")
        tmp.write_text(json.dumps(old,indent=2),encoding="utf8")
        tmp.replace(path)
    def progress(bound):
        old["lower"]=max(old["lower"],bound)
        save()
        print(f"{args.kind} ≤ {args.cap} | {len(pats)} patterns | completed 0/1 | elapsed {old['charged']:.0f}s | allotted {args.budget}s | remaining budget {old['remaining_s']:.0f}s | LB {old['lower']}",flush=True)
    progress(0)
    solver.best_bound_callback=progress
    last=[0.]
    with (target/"cp.log").open("a",encoding="utf8",buffering=1) as f:
        def log(line):
            f.write(line.rstrip()+"\n")
            if time.monotonic()-last[0]>=5:
                last[0]=time.monotonic()
                progress(old["lower"])
        solver.log_callback=log
        result=solver.solve(model)
    old["status"]=solver.status_name(result)
    old["lower"]=args.cap+1 if result==cp_model.INFEASIBLE else max(old["lower"],solver.best_objective_bound)
    if result in (cp_model.OPTIMAL,cp_model.FEASIBLE):
        old["upper"]=solver.value(cmax)
        values={v.name:solver.value(model.get_int_var_from_proto_index(i)) for i,v in enumerate(model.proto.variables) if v.name}
        (target/"projection.json").write_text(json.dumps(values),encoding="utf8")
    save()
    print("Completed 1/1, remaining 0s.", {k:v for k,v in old.items() if k!="code"},flush=True)


if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("kind",choices=("4x1","2x2","mixed"))
    p.add_argument("cap",type=int)
    p.add_argument("--budget",type=int,default=150)
    p.add_argument("--workers",type=int,default=2)
    run(p.parse_args())

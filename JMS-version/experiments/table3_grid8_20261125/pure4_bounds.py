"""Independent eight-wafer single-exposure projection and original-model witnesses."""
import argparse
from dataclasses import replace
from itertools import combinations, product
from pathlib import Path
import sys
import time

HERE = Path(__file__).resolve().parent
JMS = HERE.parents[1]
sys.path.insert(0,str(HERE.parent/"huber_residence_20261125"))
sys.path.insert(0,str(HERE.parent/"table3_pure8_20261125"))
from solver import cell, read, save, sha
from projection import STEPS, cp_model, tightened
from score import metrics

SOURCE=JMS/"results/table3_pure8_20261125/4x1/prepared/schedule.json"
OUT=JMS/"results/table3_grid8_20261125/pure4_proof"


def product_projection(doc, cap):
    """A full exposure loads/unloads both chamber sides once, including all-dummy sides."""
    m=tightened(doc,cap)
    variables={v.name:m.get_int_var_from_proto_index(i) for i,v in enumerate(m.proto.variables)}
    m.clear_hints()
    assert all(w["mode"]=="4x1" for w in doc["config"]["pjobs"])
    assert doc["config"]["chambers"]==doc["config"]["pjobs"][0]["chambers"]==[2,3]
    # The two identical chambers are exchangeable.
    m.add(variables["ch0"]==0)
    occupied=[]
    for c in range(2):
        last_back=None
        for q in range(4):
            active=variables[f"use{c,q}"]
            m.add(variables[f"full{c,q}"]==active)
            if q>=2:
                assert cap-76-40 < 3*180
                m.add(active==0)
                continue
            count=sum(variables[f"w{i}_{c}_{q}_{side}"] for i,side in product(range(8),range(2)))
            m.add(count>=active)
            start=variables[f"start{c,q}"]
            bl,fl,fu,bu=[m.new_int_var(0,cap+500,f"side_{c}_{q}_{kind}") for kind in ("bl","fl","fu","bu")]
            m.add(fl+1==start).only_enforce_if(active)
            m.add(fl>=bl+3).only_enforce_if(active)
            m.add(fu>=start+180).only_enforce_if(active)
            m.add(bu>=fu+3).only_enforce_if(active)
            if last_back is not None:
                m.add(bl>=last_back+1).only_enforce_if(active)
            last_back=bu
            for t in (bl,fl,fu,bu):
                occupied.append((c,t,active))
            for i,side in product(range(8),range(2)):
                flag=variables[f"w{i}_{c}_{q}_{side}"]
                m.add(variables[f"{i}_load"]==(fl if side else bl)).only_enforce_if(flag)
                m.add(variables[f"{i}_unload"]==(fu if side else bu)).only_enforce_if(flag)
    for (c,t,on),(d,u,un) in combinations(occupied,2):
        order=m.new_bool_var("")
        lag=1+(2 if c!=d else 0)
        m.add(u>=t+lag).only_enforce_if([on,un,order])
        m.add(t>=u+lag).only_enforce_if([on,un,order.Not()])
    for c,t,on in occupied:
        for i,name in product(range(8),("source_pick","destination_put")):
            other=variables[f"{i}_{name}"]
            order=m.new_bool_var("")
            m.add(t>=other+3).only_enforce_if([on,order])
            m.add(other>=t+3).only_enforce_if([on,order.Not()])
    return m,variables


def full_cycle_witness(doc, target, order):
    """Permit an independent timing search for each of the two fully loaded cycles."""
    sys.path.insert(0,str(cell.BACKENDS["D"]))
    from model import Integrated,Config
    from project import export
    cfg=Config(**doc["config"])
    compact=replace(cfg,max_pairs=8,max_cycles=2)
    x=Integrated(compact)
    model=x.model
    model.hideOutput()
    def pin(symbol, value):
        if hasattr(symbol,"getLbOriginal"):
            model.chgVarLb(symbol,value)
            model.chgVarUb(symbol,value)
        elif isinstance(symbol,(float,int)):
            assert symbol==value
        else:
            model.addCons(symbol==value)
    members=[g.labels for g in x.groups]
    assert len(members)==4 and all(len(g)==2 for g in members)
    if order=="projection":
        pool=read(OUT/"lower/result.json")["slots"]
        assert len(pool)==4 and all(q==0 and len(w)==2 for c,q,side,w in pool)
        labels=[None]*8
        for c,q,side,indices in pool:
            for r,i in enumerate(indices):
                labels[(2*c+side)*2+r]=doc["config"]["pjobs"][0]["wafers"][i]
    else:
        labels=[wafer for group in members for wafer in group]
    for p in range(x.P):
        active=p<4
        pin(x.pair.active[p],int(active))
        for r in range(2):
            for group in x.groups:
                pin(x.pair.member[group.identifier,p,r],int(active and labels[2*p+r] in group.labels))
            for d in range(1,cfg.dummy_count+1):
                pin(x.pair.dummy_identity[f"D{d}",p,r],0)
        for c in cfg.chambers:
            pin(x.pair.chamber[p,c],int(active and c==2+p//2))
        for k in ("4x1","2x2","clean"):
            pin(x.pair.mode[p,k],int(active and k=="4x1"))
    for c,q in product(cfg.chambers,range(x.Q)):
        pin(x.cy.used[c,q],int(q==0))
        for k in ("4x1","2x2","clean"):
            pin(x.cy.kind[c,q,k],int(q==0 and k=="4x1"))
        for p in range(x.P):
            pin(x.cy.occupancy[p,c,q],int(q==0 and p//2==c-2))
            pin(x.front[p,c,q],int(q==0 and p==2*(c-2)+1))
    model.addCons(x.cmax<=target)
    cp,vm,_=export(x,{})
    model.freeProb()
    return cp,vm,compact,cfg


def run(args):
    from contextlib import ExitStack
    import msvcrt
    doc=read(SOURCE)
    where=OUT/args.mode
    where.mkdir(parents=True,exist_ok=True)
    with (where/"active.lock").open("a+b") as lock:
        lock.seek(0)
        try: msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
        except OSError: return
        result=where/"result.json"
        provenance=dict(schedule=sha(SOURCE),code=sha(Path(__file__)),projection=sha(HERE.parent/"table3_pure8_20261125/projection.py"),
                        cap=args.cap,budget=args.seconds,threads=2)
        if result.exists():
            assert read(result)["inputs"]==provenance
            print("Verified cached certificate; ETA 0 s.",flush=True)
            return
        cpfile=where/"checkpoint.json"
        old=read(cpfile) if cpfile.exists() else {"charged":0,"bound":0,"values":{},"inputs":provenance}
        assert old["inputs"]==provenance
        if args.mode=="lower":
            cp,vm=product_projection(doc,args.cap)
        else:
            cp,vm,compact,cfg=full_cycle_witness(doc,args.cap,args.mode)
        solver=cp_model.CpSolver()
        solver.parameters.num_workers=2
        solver.parameters.random_seed=1
        solver.parameters.max_time_in_seconds=max(0,args.seconds-old["charged"])
        solver.parameters.log_search_progress=True
        solver.parameters.log_to_stdout=False
        var="makespan" if args.mode=="lower" else "Cmax"
        if old["bound"]:
            cp.add(vm[var]>=int(old["bound"]))
        if old["values"]:
            cp.clear_hints()
            for name,value in old["values"].items():
                if name in vm: cp.add_hint(vm[name],value)
        clock=time.monotonic()
        spent=old["charged"]
        def pulse():
            elapsed=spent+time.monotonic()-clock
            old["charged"]=min(args.seconds,elapsed)
            old["remaining_s"]=max(0,args.seconds-elapsed)
            save(cpfile,old)
            print(f"{args.mode}: completed 0/1 | failed 0 | elapsed {elapsed:.1f}s | allotted {args.seconds}s | remaining budget {old['remaining_s']:.1f}s | lower {old['bound']}",flush=True)
        class Capture(cp_model.CpSolverSolutionCallback):
            def on_solution_callback(self):
                old["values"]={k:self.value(v) for k,v in vm.items()}
                old["bound"]=max(old["bound"],self.best_objective_bound)
                pulse()
        last=[0.]
        with (where/"cp.log").open("a",encoding="utf8") as log:
            def monitor(line):
                log.write(line.rstrip()+"\n")
                if time.monotonic()-last[0]>=4:
                    last[0]=time.monotonic()
                    pulse()
            solver.log_callback=monitor
            state=solver.solve(cp,Capture())
        out=dict(inputs=provenance,status=solver.status_name(state),lower=solver.best_objective_bound,
                 seconds=spent+solver.wall_time)
        if state==cp_model.INFEASIBLE and args.mode=="lower":
            out["lower"]=args.cap+1
        if state in (cp_model.FEASIBLE,cp_model.OPTIMAL):
            out["upper"]=solver.objective_value
            if args.mode=="lower":
                slots=[]
                for c,q,side in product(range(2),range(2),range(2)):
                    indices=[i for i in range(8) if solver.value(vm[f"w{i}_{c}_{q}_{side}"])]
                    if indices:slots.append((c,q,side,indices))
                out["slots"]=slots
            else:
                native={k:solver.value(v) for k,v in vm.items() if solver.value(v)}
                check=cell.lift(cfg,native,compact.max_cycles,rebuild=True)
                if check:
                    sched,assignment,_,replay,rows=check
                    save(where/"schedule.json",sched)
                    save(where/"assignment.json.gz",assignment)
                    report=dict(metrics=metrics(sched),replay=replay,rows=rows,schedule_sha256=sha(where/"schedule.json"),
                                assignment_sha256=sha(where/"assignment.json.gz"))
                    save(where/"primary.json",report)
                    out["witness"]=report
        save(result,out)
        print(args.mode,out["status"],out.get("lower"),out.get("upper")," | completed 1/1; ETA 0",flush=True)


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("mode",choices=("lower","paired","projection"))
    parser.add_argument("--cap",type=int,default=575)
    parser.add_argument("--seconds",type=int,default=120)
    run(parser.parse_args())

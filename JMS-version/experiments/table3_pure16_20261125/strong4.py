"""Pure 4x1 global sublevel with both physical chamber sides and all feasible ordered batch counts."""
from collections import Counter
from itertools import combinations,groupby,product
from pathlib import Path
import sys
import time
from threading import Event,Lock,Thread
from common16 import HERE,JMS,OUT,load,save,sha
from projection16 import tightened,cp_model
sys.path.insert(0,str(HERE.parent/"table3_grid16_20261125"))
from ordered_projection import patterns

def build(cap):
    base=JMS/"results/table3_grid16_20261125/batch_bound_pure_4x1.json"
    rows=patterns(16,0,cap,load(base)["ready"])
    m=tightened(load(OUT/"4x1/raw/schedule.json"),cap)
    v={z.name:m.get_int_var_from_proto_index(i) for i,z in enumerate(m.proto.variables)}
    m.clear_hints()
    Q=1+(cap-76-40-180)//188
    slots=list(product(range(2),range(Q)))
    counts=[];ranks=[];sides=[]
    for c,q in slots:
        on=v[f"use{c,q}"];m.add(v[f"full{c,q}"]==on)
        n=m.new_int_var(0,4,f"count_{c}_{q}")
        rank=m.new_int_var(0,2*Q,f"rank_{c}_{q}")
        m.add(n==sum(v[f"w{i}_{c}_{q}_{s}"] for i,s in product(range(16),range(2))))
        m.add(n>0).only_enforce_if(on)
        m.add(n==0).only_enforce_if(~on)
        counts.append(n);ranks.append(rank)
        times={k:m.new_int_var(0,cap+120,f"{k}_{c}_{q}") for k in ["bl","fl","fu","bu"]}
        start=v[f"start{c,q}"]
        m.add(times["fl"]+1==start).only_enforce_if(on)
        m.add(times["fl"]>=times["bl"]+3).only_enforce_if(on)
        m.add(times["fu"]>=start+180).only_enforce_if(on)
        m.add(times["bu"]>=times["fu"]+3).only_enforce_if(on)
        if q:m.add(times["bl"]>=sides[-1][2]["bu"]+1).only_enforce_if(on)
        for i,s in product(range(16),range(2)):
            flag=v[f"w{i}_{c}_{q}_{s}"]
            m.add(v[f"{i}_load"]==times["fl" if s else "bl"]).only_enforce_if(flag)
            m.add(v[f"{i}_unload"]==times["fu" if s else "bu"]).only_enforce_if(flag)
        sides.append((c,on,times))
    records=set()
    for row in rows:
        seq=[g for g,k in row];totals=Counter(seq);order=[k for k,_ in groupby(seq)]
        entries=[10*c+q for c,q in slots]
        record=tuple(totals[k] for k in entries)+tuple(order.index(k) if k in order else 2*Q for k in entries)
        records.add(record)
    m.add_allowed_assignments(counts+ranks,records)
    for i,j in combinations(range(len(slots)),2):
        c,q=slots[i];e,t=slots[j]
        prior=m.new_bool_var("")
        m.add(ranks[i]<ranks[j]).only_enforce_if(prior)
        m.add(ranks[i]>=ranks[j]).only_enforce_if(~prior)
        flags=[v[f"use{c,q}"],v[f"use{e,t}"]]
        m.add(v[f"start{c,q}"]<=v[f"start{e,t}"]).only_enforce_if([*flags,prior])
        m.add(v[f"start{e,t}"]<=v[f"start{c,q}"]).only_enforce_if([*flags,~prior])
    events=[(c,t,on) for c,on,s in sides for t in s.values()]
    for (c,t,on),(d,u,other) in combinations(events,2):
        z=m.new_bool_var("")
        lag=1+2*(c!=d)
        m.add(u>=t+lag).only_enforce_if([on,other,z])
        m.add(t>=u+lag).only_enforce_if([on,other,~z])
    for c,t,on in events:
        for i,k in product(range(16),("source_pick","destination_put")):
            u=v[f"{i}_{k}"];z=m.new_bool_var("")
            m.add(u>=t+3).only_enforce_if([on,z])
            m.add(t>=u+3).only_enforce_if([on,~z])
    m.add(v["makespan"]>=load(base)["lower"])
    return m,v,len(records)

def main(cap,seconds):
    root=OUT/"4x1";out=root/"strong"/str(cap)
    out.mkdir(parents=True,exist_ok=True)
    ck=out/"progress.json"
    sig=dict(cap=cap,seconds=seconds,code=sha(Path(__file__)),projection=sha(HERE/"projection16.py"),
        batch=sha(HERE.parent/"table3_grid16_20261125/ordered_projection.py"),seed=1)
    record=load(ck) if ck.exists() else dict(identity=sig,used=0,upper=None,lower=824)
    assert record["identity"]==sig
    if (out/"result.json").exists():return
    model,v,pats=build(cap)
    model.add(v["makespan"]>=int(record["lower"]))
    if record["upper"] is not None:
        candidate=load(out/f"candidate_{int(record['upper'])}.json")
        for k,x in v.items():model.add_hint(x,candidate.get(k,0))
        model.add(v["makespan"]<=int(record["upper"]))
    engine=cp_model.CpSolver();engine.parameters.num_workers=1;engine.parameters.random_seed=1
    engine.parameters.log_search_progress=True;engine.parameters.log_to_stdout=False
    used=record["used"];engine.parameters.max_time_in_seconds=max(0,seconds-used)
    start=time.monotonic();stop=Event();lock=Lock()
    def progress():
        record["used"]=min(seconds,used+time.monotonic()-start+1)
        save(ck,record)
    def pulse():
        while not stop.wait(3):
            with lock:progress()
            print(f"4x1 at {cap} s, completed 0/1, LB {record['lower']}, UB {record['upper']}, spent {record['used']:.0f}s; budget ETA {seconds-record['used']:.0f}s",flush=True)
    def lower(lb):
        with lock:
            if lb<=record["lower"]:return
            record["lower"]=lb
            cert=out/f"lb_{int(lb)}.json"
            save(cert,dict(signature=sig,global_lower=lb,patterns=pats))
            save(root/"external_bounds"/f"strong_{cap}_{int(lb)}.json",dict(lower=lb,received=time.time(),proof=cert.relative_to(JMS).as_posix(),sha256=sha(cert)))
            progress()
    class Capture(cp_model.CpSolverSolutionCallback):
        def on_solution_callback(self):
            val=self.objective_value
            with lock:
                if record["upper"] is None or val<record["upper"]:
                    save(out/f"candidate_{int(val)}.json",{k:self.value(x) for k,x in v.items() if self.value(x)})
                    record["upper"]=val
                    progress()
    th=Thread(target=pulse,daemon=True);th.start()
    engine.best_bound_callback=lower
    with (out/"solver.log").open("a",encoding="utf8",buffering=1) as log:
        engine.log_callback=lambda s:log.write(s.rstrip()+"\n")
        status=engine.solve(model,Capture())
    stop.set();th.join()
    if status==cp_model.INFEASIBLE:
        assert record["upper"] is None
        lower(cap+1)
    record.update(status=engine.status_name(status),used=used+engine.wall_time,patterns=pats)
    save(ck,record);save(out/"result.json",record)

if __name__=="__main__":main(int(sys.argv[1]),int(sys.argv[2]))

"""Global pure-4x1 dual search initialized by a feasible full native handoff."""
from itertools import product
from pathlib import Path
import sys
import threading
import time
from common16 import HERE,JMS,OUT,save,load,sha
from strong4 import build,cp_model
from projection16 import STEPS

def mapped_times(doc):
    cycles=sorted((r for r in doc["cycles"] if r["mode"]!="clean"),key=lambda r:r["start"])
    chambers=[cycles[0]["chamber"],5-cycles[0]["chamber"]]
    index={c:i for i,c in enumerate(chambers)}
    pairs={p["id"]:p for p in doc["pairs"]}
    loc={}
    values={}
    for cy in cycles:
        c,q=index[cy["chamber"]],cy["index"]
        values[f"start{c,q}"]=round(cy["start"]);values[f"use{c,q}"]=1
        for p in cy["pairs"]:loc[p]=(c,q,int(p==cy["front"]))
    byjob={(e["job"],e["kind"]):e["start"] for e in doc["events"] if "job" in e}
    jobs=sorted((w for w in doc["jobs"] if w["product"]),key=lambda w:w["pjob_index"])
    for i,w in enumerate(jobs):
        c,q,s=loc[w["pair"]]
        values[f"w{i}_{c}_{q}_{s}"]=1
        for k in STEPS:
            val=w[k+"_start"] if k in ("load","unload") else byjob[w["name"],k]
            assert abs(val-round(val))<1e-6
            values[f"{i}_{k}"]=round(val)
    return values

def main(path,budget):
    source=Path(path).resolve()
    data=load(source)
    cap=round(max(w["loan_end"] for w in data["jobs"] if w["product"]))
    root=OUT/"4x1";folder=root/"warm_dual"/str(cap)
    folder.mkdir(parents=True,exist_ok=True)
    id_=dict(seed=1,threads=2,input=sha(source),code=sha(Path(__file__)),strong=sha(HERE/"strong4.py"),cap=cap,budget=budget)
    ck=folder/"progress.json"
    state=load(ck) if ck.exists() else dict(identity=id_,used=0,lower=824,upper=cap)
    assert state["identity"]==id_
    if (folder/"result.json").exists():return
    m,v,n=build(cap)
    arr=mapped_times(data)
    derived=folder/"checked_hint.json"
    if not derived.exists():
        copy=m.clone()
        for k,t in arr.items():
            copy.add(copy.get_int_var_from_proto_index(v[k].index)==t)
        verify=cp_model.CpSolver()
        verify.parameters.random_seed=1;verify.parameters.num_workers=1;verify.parameters.max_time_in_seconds=25
        selected=verify.solve(copy)
        assert selected in (cp_model.OPTIMAL,cp_model.FEASIBLE),verify.status_name(selected)
        hint={i:verify.value(copy.get_int_var_from_proto_index(i)) for i in range(len(copy.proto.variables))}
        save(derived,dict(input=sha(source),all_variable_count=len(hint),values=hint))
    for i,t in load(derived)["values"].items():m.add_hint(m.get_int_var_from_proto_index(int(i)),t)
    m.add(v["makespan"]>=int(state["lower"]))
    m.add(v["makespan"]<=int(state["upper"]))
    engine=cp_model.CpSolver();engine.parameters.num_workers=2;engine.parameters.random_seed=1
    engine.parameters.log_search_progress=True;engine.parameters.log_to_stdout=False
    used=state["used"];engine.parameters.max_time_in_seconds=max(0,budget-used)
    start=time.monotonic();stop=threading.Event();lock=threading.Lock()
    def sync():
        state["used"]=min(budget,used+time.monotonic()-start+2)
        save(ck,state)
    def pulse():
        while not stop.wait(2):
            with lock:sync()
            print(f"Validated incumbent {cap}, global LB {state['lower']}, projection UB {state['upper']}, completed 0/1, failed 0, allocated {budget}s, ETA {budget-state['used']:.0f}s",flush=True)
    def lower(lb):
        with lock:
            if lb<=state["lower"]:return
            state["lower"]=lb
            proof=folder/f"lb_{int(lb)}.json"
            save(proof,dict(signature=id_,source=str(source.relative_to(JMS)),global_lower=lb,patterns=n))
            save(root/"external_bounds"/f"warm_{cap}_{int(lb)}.json",dict(lower=lb,received=time.time(),proof=proof.relative_to(JMS).as_posix(),sha256=sha(proof)))
            sync()
    class Capture(cp_model.CpSolverSolutionCallback):
        def on_solution_callback(self):
            val=self.objective_value
            with lock:
                if val<state["upper"]:
                    save(folder/f"candidate_{int(val)}.json",{k:self.value(x) for k,x in v.items() if self.value(x)})
                    state["upper"]=val;sync()
    th=threading.Thread(target=pulse,daemon=True);th.start()
    engine.best_bound_callback=lower
    with (folder/"solver.log").open("a",encoding="utf8",buffering=1) as log:
        engine.log_callback=lambda s:log.write(s.rstrip()+"\n")
        status=engine.solve(m,Capture())
    stop.set();th.join()
    assert status!=cp_model.INFEASIBLE
    state.update(status=engine.status_name(status),used=used+engine.wall_time,patterns=n)
    save(ck,state);save(folder/"result.json",state)

if __name__=="__main__":main(sys.argv[1],int(sys.argv[2]))

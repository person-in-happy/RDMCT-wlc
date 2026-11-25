"""Global product-only projection after removing dummy and clean operations."""
import itertools
from pathlib import Path
import sys
import threading
import time
from common16 import HERE,JMS,OUT,load,save,sha
from projection16 import tightened, cp_model

def main(mode):
    folder=OUT/mode/"projection"
    folder.mkdir(parents=True,exist_ok=True)
    source=OUT/mode/"raw/schedule.json"
    physical=JMS/"results/table3_grid16_20261125"/f"batch_bound_pure_{mode}.json"
    cap={"4x1":920,"2x2":880}[mode]
    pure=mode=="4x1"
    qmax=1+(cap-76-40-(180 if pure else 90))//(188 if pure else 94)
    identity=dict(seed=1,threads=1,cap=cap,seconds=600,projection=sha(HERE/"projection16.py"),
        worker=sha(Path(__file__)),input_sha256=sha(source),base_sha256=sha(physical))
    statefile=folder/"progress.json"
    state=load(statefile) if statefile.exists() else dict(identity=identity,used=0,lower=load(physical)["lower"],upper=None)
    if state["identity"]!=identity:raise ValueError("Unmatched projection checkpoint")
    if (folder/"result.json").exists():return
    model=tightened(load(source),cap)
    v={x.name:model.get_int_var_from_proto_index(i) for i,x in enumerate(model.proto.variables)}
    model.add(v["ch0"]==0)
    model.add(v["makespan"]>=int(state["lower"]))
    for c,q in itertools.product(range(2),range(qmax)):
        active=v[f"use{c,q}"];full=v[f"full{c,q}"]
        model.add(full==(active if pure else 0))
        products=[v[k] for i in range(16) for side in range(2) if (k:=f"w{i}_{c}_{q}_{side}") in v]
        if not pure and q>0:products.extend(v[f"w{i}_{c}_{q-1}_1"] for i in range(16))
        model.add(active<=sum(products))
    model.clear_hints()
    if state["upper"] is not None:
        hint=load(folder/f"candidate_{int(state['upper'])}.json")
        for key in v:model.add_hint(v[key],hint.get(key,0))
        model.add(v["makespan"]<=int(state["upper"]))
    solver=cp_model.CpSolver()
    solver.parameters.num_workers=1
    solver.parameters.random_seed=1
    solver.parameters.max_time_in_seconds=max(0,600-state["used"])
    solver.parameters.log_search_progress=True
    solver.parameters.log_to_stdout=False
    prior=state["used"]
    started=time.monotonic()
    lock=threading.Lock()
    stop=threading.Event()
    def sync():
        state["used"]=min(600,prior+time.monotonic()-started+1)
        state["wall_utc_epoch"]=time.time()
        save(statefile,state)
    def heartbeat():
        while not stop.wait(1):
            with lock:sync()
    def improve(bound):
        with lock:
            if bound<=state["lower"]:return
            state["lower"]=bound
            sync()
            save(folder/f"lb_{int(bound)}.json",dict(identity=identity,global_lower=bound,timestamp=time.time()))
    class Capture(cp_model.CpSolverSolutionCallback):
        def on_solution_callback(self):
            coords={key:self.value(x) for key,x in v.items() if self.value(x)}
            with lock:
                val=self.objective_value
                if state["upper"] is None or val<state["upper"]:
                    save(folder/f"candidate_{int(val)}.json",coords)
                    state["upper"]=val
                sync()
    worker=threading.Thread(target=heartbeat,daemon=True)
    sync();worker.start()
    with (folder/"solver.log").open("a",encoding="utf8",buffering=1) as log:
        solver.log_callback=lambda s:log.write(s.rstrip()+"\n")
        solver.best_bound_callback=improve
        status=solver.solve(model,Capture())
    stop.set();worker.join()
    state["used"]=prior+solver.wall_time
    state["lower"]=max(state["lower"],cap+1 if status==cp_model.INFEASIBLE else solver.best_objective_bound)
    state["status"]=solver.status_name(status)
    state["scope"]="Global relaxed bound at cap: all real product routes, two identical chambers; omit dummy and clean handling."
    state["timestamp"]=time.time()
    save(statefile,state)
    save(folder/"result.json",state)
    print(mode,state["status"],state["lower"],state["upper"],flush=True)

if __name__=="__main__":main(sys.argv[1])

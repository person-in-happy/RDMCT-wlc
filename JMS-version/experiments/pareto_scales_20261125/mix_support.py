"""Try other convex combinations of the two guaranteed 4x1 side differences at cap 812."""
from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path
import time
from neighbor import OUT,atomic,enumerate_cap,rank,cp_model,read,sha


def trial(weights):
    a,b=weights
    cap=812;i=26
    folder=OUT/"cap812"/f"support_{a}_{b}";folder.mkdir(exist_ok=True,parents=True)
    target=folder/"result.json"
    if target.exists() and read(target)["implementation"]==sha(Path(__file__)):return read(target)
    table,_,_=enumerate_cap(cap);pattern,cycles=table[i]
    rank.tool.order.patterns=lambda nf,nd,cap,ready:{pattern:cycles}
    m,c=rank.tool.add_ports("mixed",cap)
    v={z.name:m.get_int_var_from_proto_index(j) for j,z in enumerate(m.proto.variables) if z.name}
    rank.rank_propagation(m,v,pattern,cap,True)
    v={z.name:m.get_int_var_from_proto_index(j) for j,z in enumerate(m.proto.variables) if z.name}
    delta=lambda g:v[f"bu_{g}"]-v[f"bl_{g}"]-v[f"fu_{g}"]+v[f"fl_{g}"]
    cost=b*(sum(v[f"ul_{j}"]-v[f"ld_{j}"]-181 for j in range(16))-8)+16*(a*delta(10)+(b-a)*delta(11))
    m.minimize(cost)
    hint=read(OUT/"cap812/p0026_hint.json")
    for k,val in hint.items():
        if k in v:m.add_hint(v[k],val)
    s=cp_model.CpSolver();s.parameters.num_workers=2;s.parameters.max_time_in_seconds=22
    s.parameters.log_search_progress=True;s.parameters.log_to_stdout=False
    with (folder/"solver.log").open("w",encoding="utf8") as f:
        s.log_callback=lambda ln:f.write(ln.rstrip()+"\n")
        stat=s.solve(m)
    r=dict(implementation=sha(Path(__file__)),status=s.status_name(stat),lower=s.best_objective_bound/(16*b),used=s.wall_time,weights=weights)
    if stat in (cp_model.FEASIBLE,cp_model.OPTIMAL):
        vals={k:s.value(z) for k,z in v.items()};atomic(folder/"projection.json",vals)
        r["upper"]=s.objective_value/(16*b)
    atomic(target,r);return r


if __name__=="__main__":
    jobs=[(0,1),(1,2),(3,4),(1,4)]
    started=time.monotonic()
    print("4 support solves, two concurrent, 22 s per solve, estimated total 50 s",flush=True)
    with ProcessPoolExecutor(max_workers=2,max_tasks_per_child=1) as pool:
        for n,f in enumerate(as_completed([pool.submit(trial,x) for x in jobs]),1):
            print(f.result(),flush=True)
            wall=time.monotonic()-started
            atomic(OUT/"cap812/support_progress.json",dict(completed=n,total=4,failed=0,elapsed=wall,eta_remaining=wall*(4-n)/n,eta_total=wall*4/n))

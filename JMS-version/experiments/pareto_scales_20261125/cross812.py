"""Use the late full-batch back pair and early full-batch front pair for the 812 s point."""
import time
from pathlib import Path
from neighbor import OUT,atomic,enumerate_cap,rank,cp_model,read,sha


def run():
    dest=OUT/"cap812/cross_11b_10f";dest.mkdir(exist_ok=True,parents=True)
    target=dest/"result.json"
    if target.exists() and read(target)["implementation"]==sha(Path(__file__)):return
    table,_,_=enumerate_cap(812);pattern,cycles=table[26]
    assert pattern.count((10,1))>=3 and pattern.count((11,1))>=3
    rank.tool.order.patterns=lambda nf,nd,cap,ready:{pattern:cycles}
    m,c=rank.tool.add_ports("mixed",812)
    v={z.name:m.get_int_var_from_proto_index(j) for j,z in enumerate(m.proto.variables) if z.name}
    rank.rank_propagation(m,v,pattern,812,True)
    v={z.name:m.get_int_var_from_proto_index(j) for j,z in enumerate(m.proto.variables) if z.name}
    delta=v["bu_11"]-v["bl_11"]-v["fu_10"]+v["fl_10"]
    m.minimize(sum(v[f"ul_{j}"]-v[f"ld_{j}"]-181 for j in range(16))+16*delta-8)
    hint=read(OUT/"cap812/p0026_hint.json")
    for k,val in hint.items():
        if k in v:m.add_hint(v[k],val)
    s=cp_model.CpSolver();s.parameters.num_workers=2;s.parameters.max_time_in_seconds=22
    s.parameters.log_to_stdout=False;s.parameters.log_search_progress=True
    print("Cross-group certificate: 0/1, 22 s solver budget",flush=True)
    with (dest/"solver.log").open("w",encoding="utf8") as f:
        s.log_callback=lambda ln:f.write(ln.rstrip()+"\n")
        stat=s.solve(m)
    r=dict(implementation=sha(Path(__file__)),status=s.status_name(stat),lower=s.best_objective_bound/16,used=s.wall_time)
    if stat in (cp_model.FEASIBLE,cp_model.OPTIMAL):
        r["upper"]=s.objective_value/16;atomic(dest/"projection.json",{k:s.value(z) for k,z in v.items()})
    atomic(target,r);print(r,flush=True)


if __name__=="__main__":
    run()

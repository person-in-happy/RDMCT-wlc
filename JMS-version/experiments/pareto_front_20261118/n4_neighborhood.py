"""Mix-case search from validated starts. Only the last query has global scope."""
from itertools import combinations
from pathlib import Path
import argparse
import traceback

from slices import Config, Integrated, Projected, log, np, read, save
from probes import physically_checked, progress, read_candidates, set_assignment


def search(source, out, selected=None):
    meta = read(source / "slices.json")
    cfg = Config(**meta["config"])
    archive = min(read_candidates(source, meta), key=lambda p: (p[0], p[1]))[2]
    chain = dict(zip(meta["variables"], np.load(source / "secondary_endpoint/chain.npz")["v"]))
    queries = [("chain_orders", chain), ("archive_orders", archive), ("global_makespan_at_54", chain)]
    if selected:
        queries = [q for q in queries if q[0] == selected]
    records = []
    audit = Integrated(cfg)
    projection = Projected(audit)
    for index, (name, start) in enumerate(queries):
        model = Integrated(cfg)
        solver = model.model
        warm = set_assignment(model, start)
        assert solver.checkSol(warm, completely=True, original=True)
        seed = model.result(solution=warm)
        if name == "global_makespan_at_54":
            solver.addCons(model.secondary_objective <= 54.0000001)
            # Reaching this bound forces four product-dummy pairs (single aligner).
            for p in range(model.N):
                solver.addCons(model.pair.product[p, 1] == 0)
            solver.addCons(model.max_wait == 3)
            for value in model.rhythm:
                solver.addCons(value == 0)
            local = False
        else:
            # Keep the local integer choices; allow nearby active robot events to reorder.
            near = set()
            for e, f in combinations(seed["events"], 2):
                if e.get("robot") and e.get("robot") == f.get("robot") and abs(e["start"] - f["start"]) < 140:
                    near.add("order_" + e["name"] + "_" + f["name"])
                    near.add("order_" + f["name"] + "_" + e["name"])
            for var in solver.getVars(transformed=False):
                if var.vtype() != "CONTINUOUS" and var.name not in near:
                    solver.fixVar(var, round(start[var.name]))
            local = True
        solver.setObjective(model.cmax, "minimize")
        assert solver.checkSol(warm, completely=True, original=True)
        solver.addSol(warm)
        solver.setIntParam("parallel/maxnthreads", 1)
        solver.setRealParam("limits/time", 50)
        solver.setRealParam("limits/memory", 3500)
        solver.setRealParam("numerics/feastol", 1e-8)
        solver.setLogfile(str(out / (name + ".log")))
        log(out, f"{name}, completed={index}/{len(queries)}, failed=0, remaining budget={(len(queries)-index)*50}s")
        with progress(out, name, index, len(queries), 50):
            solver.optimize()
        sol = solver.getBestSol()
        vals = {v.name: solver.getSolVal(sol, v) for v in solver.getVars(transformed=False)}
        optimum, schedule = physically_checked(audit, vals)
        save(out / (name + "_schedule.json"), schedule)
        bound = solver.getDualbound()
        row = dict(name=name, local=local, status=str(solver.getStatus()), lower_A=bound,
                   metrics=optimum, elapsed_seconds=solver.getSolvingTime(), vertices=[])
        assignment = np.asarray([round(vals[projection.names[i]]) for i in projection.id], dtype=np.int32)
        projection.setup(assignment)
        vertices = projection.front()
        np.savez_compressed(out/(name+"_variables.npz"),discrete=assignment,continuous=np.asarray(vertices))
        for i, continuous in enumerate(vertices):
            full = np.empty(len(projection.names))
            full[projection.ic], full[projection.id] = continuous, assignment
            metrics, schedule = physically_checked(audit, dict(zip(projection.names, full)))
            file = name + "_slice_" + str(i) + ".json"
            save(out / file, schedule)
            row["vertices"].append(dict(metrics=metrics, schedule=file))
        row["midpoints"] = []
        for i,(a,b) in enumerate(zip(vertices,vertices[1:])):
            full[projection.ic] = (a+b)/2
            m,d = physically_checked(audit,dict(zip(projection.names,full)))
            pts = row["vertices"][i:i+2]
            assert all(abs(m[k]-(pts[0]["metrics"][k]+pts[1]["metrics"][k])/2)<2e-5 for k in ("cmax","secondary"))
            file = name+"_mid_"+str(i)+".json"
            save(out/file,d)
            row["midpoints"].append(dict(metrics=m,schedule=file))
        records.append(row)
        save(out / "results.json", records)
        log(out, f"{name}, status={row['status']}, bound={bound:.4f}, physical A,B={[ (v['metrics']['cmax'],v['metrics']['secondary']) for v in row['vertices'] ]}")
        solver.freeProb()
    audit.model.freeProb()
    log(out, f"completed={len(queries)}/{len(queries)} failed=0")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("out", type=Path)
    parser.add_argument("--query",choices=("chain_orders","archive_orders","global_makespan_at_54"))
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    try:
        search(args.source, args.out, args.query)
    except BaseException:
        log(args.out, traceback.format_exc())
        raise

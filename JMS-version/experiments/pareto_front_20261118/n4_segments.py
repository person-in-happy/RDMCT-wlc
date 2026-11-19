"""Save shared discrete assignments and physically replay fixed-assignment trade-off segments."""
import argparse
from pathlib import Path
import traceback

from slices import Config, Integrated, Projected, TOL, digest, log, np, read, save
from seed import constrain_seed
from probes import physically_checked


def infer(cfg, schedule, pg):
    x = Integrated(cfg)
    constrain_seed(x, read(schedule))
    x.model.setObjective(x.secondary_objective, "minimize")
    x.model.optimize()
    if not x.model.getNSols():
        raise ValueError(str(schedule))
    s = x.model.getBestSol()
    values = {v.name:x.model.getSolVal(s,v) for v in x.model.getVars(transformed=False)}
    x.model.freeProb()
    return np.asarray([round(values[pg.names[j]]) for j in pg.id], dtype=int)


def run(n4, out):
    meta = read(n4 / "slices.json")
    cfg = Config(**meta["config"])
    audit = Integrated(cfg)
    pg = Projected(audit)
    assert pg.names == meta["variables"]
    origin = n4 / "endpoint_search"
    results = []
    for row in read(origin / "results.json"):
        points = row["vertices"]
        if len(points) < 2:
            continue
        tag = row["name"]
        target = np.asarray([(p["metrics"]["cmax"],p["metrics"]["secondary"]) for p in points])
        options = [origin / p["schedule"] for p in points]
        if tag == "global_makespan_at_54":
            options.insert(0, n4 / "secondary_endpoint/chain.npz")
        for candidate in options:
            if candidate.suffix == ".npz":
                discrete = np.rint(np.load(candidate)["v"][pg.id]).astype(int)
            else:
                discrete = infer(cfg,candidate,pg)
            pg.setup(discrete)
            vs = pg.front()
            actual = np.asarray([pg.verify(v) for v in vs])
            if actual.shape != target.shape or not np.allclose(actual,target,rtol=0,atol=TOL):
                continue
            evidence = out / (tag + ".npz")
            np.savez_compressed(evidence,discrete=discrete,continuous=np.asarray(vs))
            mids = []
            for i,(first,last) in enumerate(zip(vs,vs[1:])):
                full = np.empty(len(pg.names))
                full[pg.ic],full[pg.id] = (first+last)/2,discrete
                observed,sch = physically_checked(audit,dict(zip(pg.names,full)))
                assert np.max(np.abs((actual[i]+actual[i+1])/2-[observed["cmax"],observed["secondary"]]))<TOL
                file = f"{tag}_mid_{i}.json"
                save(out / file,sch)
                mids.append(dict(metrics=observed,file=file))
            results.append(dict(name=tag,vertices=actual.tolist(),midpoints=mids,
                                assignment=evidence.name,sha256=digest(evidence)))
            save(out / "segments.json",results)
            break
        else:
            log(out,f"{tag}: unable to recover an assignment for all listed vertices")
        log(out,f"completed={len(results)}/2 verified polylines, expected remaining under 30s")
    audit.model.freeProb()


if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("source",type=Path)
    p.add_argument("out",type=Path)
    args=p.parse_args()
    args.out.mkdir(parents=True,exist_ok=False)
    try:
        run(args.source,args.out)
    except BaseException:
        log(args.out,traceback.format_exc())
        raise

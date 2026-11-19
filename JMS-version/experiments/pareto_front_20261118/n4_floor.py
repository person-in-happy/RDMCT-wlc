"""Certify the mixed instance at its quality optimum in the short-makespan region."""
import argparse
from pathlib import Path
import traceback

from slices import Config, TOL, log, read, save
from seed import constrain_seed
from probes import progress, set_assignment
from n4 import topology
from n4_fast import model_for
from family import lift


def floor_model(cfg):
    x = model_for(cfg, True, True)
    topology(x, "chain")
    return x


def run(source, out):
    cfg = Config(**read(source / "slices.json")["config"])
    seed = floor_model(cfg)
    constrain_seed(seed, read(source / "secondary_endpoint/chain_schedule.json"))
    seed.model.setObjective(0, "minimize")
    seed.model.optimize()
    assert seed.model.getNSols()
    values = {v.name:seed.model.getSolVal(seed.model.getBestSol(),v) for v in seed.model.getVars(transformed=False)}
    seed.model.freeProb()
    rows = []
    for index, (name, cap, seconds) in enumerate([("at_429", 429.00001, 40), ("best_chain", 497.00001, 65)]):
        x = floor_model(cfg)
        m = x.model
        m.addCons(x.cmax <= cap)
        if cap >= 497:
            warm = set_assignment(x, values)
            assert m.checkSol(warm, completely=True, original=True)
            m.addSol(warm)
        m.setObjective(x.cmax, "minimize")
        m.setIntParam("parallel/maxnthreads", 1)
        m.setRealParam("limits/time", seconds)
        m.setRealParam("numerics/feastol", 1e-8)
        m.setRealParam("limits/memory", 3500)
        m.setLogfile(str(out / (name + ".log")))
        log(out, f"{name}, completed={index}/2, failed=0, remaining nominal seconds={105 - 40*index}")
        with progress(out, name, index, 2, seconds):
            m.optimize()
        bound = m.getDualbound()
        row = dict(name=name, cap=cap, status=str(m.getStatus()), lower_A=bound if abs(bound)<1e19 else None,
                   seconds=m.getSolvingTime(), nodes=m.getNNodes())
        if m.getNSols():
            d = x.result(solution=m.getBestSol())
            metrics, schedule = lift(cfg, d)
            assert abs(metrics["secondary"] - 54) < TOL
            save(out / (name + "_schedule.json"), schedule)
            row["metrics"] = metrics
        rows.append(row)
        save(out / "results.json", rows)
        log(out, str(row))
        m.freeProb()
    log(out, "completed=2/2 failed=0")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("source",type=Path)
    p.add_argument("out",type=Path)
    args = p.parse_args()
    args.out.mkdir(parents=True,exist_ok=False)
    try:
        run(args.source,args.out)
    except BaseException:
        log(args.out,traceback.format_exc())
        raise

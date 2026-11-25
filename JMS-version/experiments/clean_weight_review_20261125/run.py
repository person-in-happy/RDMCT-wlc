"""Cold-start reoptimization of two cleaning structures from the 2-wafer mixed case."""
import hashlib
import json
import msvcrt
import os
from pathlib import Path
import statistics
import sys
import threading
import time

HERE = Path(__file__).resolve().parent
JMS = HERE.parents[1]
OUT = JMS / "results" / HERE.name
BACKEND = JMS / "model4_pjob_nonprocessing_20261103"
SQUARE = HERE.parent / "square_residence_20261125"
sys.path.insert(0, str(SQUARE))
from solver import cell, objective_terms
from score import metrics
sys.path.insert(0, str(BACKEND))
from model import Config, Integrated
from validate import validate

SOURCES = {
    "no_clean": "results/sublevel_projection_20261120_r1/D_n2_mixed_scenario3/proposal",
    "two_cleans": "results/manuscript_certified_gaps_20261119_r3/runs/D_n2_mixed_scenario3/full/A_0p01pct",
}
WEIGHTS = (0, 0.5, 1, 2)
CAP = 324


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    os.replace(tmp, path)


def schedule_stats(data):
    loans = [j for j in data["jobs"] if not j["product"]]
    events = sorted((t, change) for j in loans for t, change in
                    ((round(j["loan_start"], 6), 1), (round(j["loan_end"], 6), -1)))
    peak = current = 0
    for _, change in events:
        current += change
        peak = max(peak, current)
    return dict(cleans=[{k: c[k] for k in ("chamber", "start", "end")}
                        for c in data["cycles"] if c["mode"] == "clean"],
                production=sum(c["mode"] != "clean" for c in data["cycles"]),
                peak_borrowed_dummies=peak, dummy_loans=len(loans),
                dummy_wafer_seconds=sum(j["loan_end"] - j["loan_start"] for j in loans),
                last_return=max(j["loan_end"] for j in data["jobs"]))


def optimize(structure, gamma, folder):
    start = time.monotonic()
    source = JMS / SOURCES[structure]
    data = read(source / "schedule.json")
    values = cell.values(source / "assignment.json.gz")
    model = Integrated(Config(**data["config"]))
    m = model.model
    native = list(m.getVars(transformed=False))
    for var in native:
        if var.vtype() != "CONTINUOUS" and not var.name.startswith("sync_"):
            value = round(values.get(var.name, 0))
            m.chgVarLb(var, value)
            m.chgVarUb(var, value)
    m.addCons(model.cmax <= CAP)
    cost, _ = objective_terms(model, values, fixed=True, clean_weight=gamma)
    release = model.cont("last_physical_return")
    for job in model.jobs.values():
        m.addCons(release >= job["last"]["e"])
    cell.scip_settings(m, dict(n=2, seed=1, seconds=None, gap=0), folder)
    m.setRealParam("numerics/feastol", 1e-8)
    stages = {}
    for phase, objective in (("process", cost), ("last_return", release)):
        m.setObjective(objective, "minimize")
        m.optimize()
        if str(m.getStatus()) != "optimal":
            raise RuntimeError(f"{structure}, {phase}: {m.getStatus()}")
        upper, lower = m.getPrimalbound(), m.getDualbound()
        if abs(upper - lower) > 1e-5:
            raise RuntimeError(f"Unresolved {phase} bounds")
        stages[phase] = dict(upper=upper, lower=lower, seconds=m.getSolvingTime(), nodes=m.getNNodes())
        if phase == "process":
            m.freeTransform()
            m.addCons(cost <= upper + 1e-8)
    data = model.result(solution=m.getBestSol())
    valid = validate(data)
    assert valid["valid"], valid["errors"]
    score = metrics(data, clean_weight=gamma)
    stats = schedule_stats(data)
    assert score["cmax"] <= CAP + 1e-5
    assert abs(score["secondary"] - stages["process"]["lower"]) < 1e-5
    assert abs(stats["last_return"] - stages["last_return"]["lower"]) < 1e-5
    assert len(stats["cleans"]) == (0 if structure == "no_clean" else 2)
    assert score["clean_deficit"] == (0 if structure == "no_clean" else 7)
    save(folder / "schedule.json", data)
    m.freeProb()
    return dict(structure=structure, gamma=gamma, stages=stages, physical=score, auxiliary=stats,
                validated=valid["valid"], checks=valid["checks"], schedule_sha256=sha(folder/"schedule.json"),
                seconds=time.monotonic()-start)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    lock = (OUT / "runner.lock").open("a+b")
    if lock.tell() == 0:
        lock.write(b"0")
        lock.flush()
    lock.seek(0)
    try:
        msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError:
        print(f"Active foreground worker owns {OUT}; see status.json.", flush=True)
        return
    configs = [read(JMS / path / "schedule.json")["config"] for path in SOURCES.values()]
    assert configs[0] == configs[1]
    deps = [Path(__file__), SQUARE / "solver.py", SQUARE / "score.py", Path(cell.__file__)]
    deps += sorted(BACKEND.glob("*.py"))
    deps += [JMS / p / name for p in SOURCES.values() for name in ("schedule.json", "assignment.json.gz")]
    hashes = {p.relative_to(JMS).as_posix(): sha(p) for p in deps}
    tasks = [(s, g, OUT / f"gamma_{g}_{s}") for g in WEIGHTS for s in SOURCES]
    results = []
    tick = time.monotonic()
    active = "validating endpoints"
    failed = 0
    saved_work = 0
    def progress():
        elapsed = time.monotonic() - tick + saved_work
        sample = [r["seconds"] for r in results]
        unit = statistics.median(sample) if sample else 5
        remaining = (len(tasks)-len(results))*unit
        status = dict(completed=len(results), failed=failed, total=len(tasks), active=active, pid=os.getpid(),
                      elapsed_s=round(elapsed, 2), estimated_total_s=round(elapsed+remaining, 2),
                      estimated_remaining_s=round(remaining, 2), workers=1, threads_per_solver=1,
                      basis="median verified endpoint wall time" if sample else "initial estimate, 5 s per two-stage small case",
                      recovery="verified per-weight/structure endpoints; both exact stages of an interrupted endpoint restart")
        save(OUT / "status.json", status)
        print(f"{len(results)}/{len(tasks)}, failed {failed}, {active}, elapsed {elapsed:.1f}s, "
              f"estimated total {elapsed+remaining:.1f}s, remaining {remaining:.1f}s", flush=True)
    import_lock = threading.Lock()
    def emit():
        with import_lock:
            progress()
    stop = threading.Event()
    def heartbeat():
        while not stop.wait(8):
            emit()
    thread = threading.Thread(target=heartbeat, daemon=True)
    thread.start()
    try:
        emit()
        for structure, gamma, folder in tasks:
            active = f"{structure} gamma={gamma}"
            folder.mkdir(exist_ok=True)
            record = folder / "result.json"
            if record.exists():
                result = read(record)
                assert result["input_sha256"] == hashes and result["schedule_sha256"] == sha(folder / "schedule.json")
                saved_work += result["seconds"]
            else:
                result = optimize(structure, gamma, folder)
                result["input_sha256"] = hashes
                save(record, result)
            results.append(result)
            emit()
            if os.environ.get("CLEAN_REVIEW_STOP_AFTER") == str(len(results)):
                active = "checkpoint reached"
                return
        winners = {}
        for gamma in WEIGHTS:
            group = [r for r in results if r["gamma"] == gamma]
            lower = min(r["stages"]["process"]["lower"] for r in group)
            winners[str(gamma)] = dict(lower=lower, structures=[r["structure"] for r in group
                if r["physical"]["secondary"] <= lower+1e-5])
        save(OUT / "summary.json", dict(scope="union of two fixed archived physical orders, conventional unload; free synchronization/times, product makespan <=324 s; last physical return minimized within each tied optimum",
             cold_start=True, config=configs[0], sources=SOURCES, winners=winners,
             results=[{k:v for k,v in r.items() if k != "input_sha256"} for r in results]))
        active = "verified"
    except BaseException:
        failed = 1
        raise
    finally:
        stop.set()
        thread.join()
        emit()
        lock.close()


if __name__ == "__main__":
    main()

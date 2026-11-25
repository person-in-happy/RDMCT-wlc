"""Matched fixed-gap controls. Read both physical objectives from one native incumbent."""
from pathlib import Path
import math
import sys
import time

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "mixed_controls_20261122"))
from controls import JMS, ROOT, cell, matched, product, product_solve, read, save, sha
from objective16 import register

OUT = JMS / "results/table4_fixed_gap_20261123"
LEVELS = {"10pct": .1, "1pct": .01, "0p01pct": .0001}
CASES = ("E_n4_H10_mixed_dual", "E_n4_H3_mixed_dual",
         "E_n8_H10_mixed_dual", "E_n8_H3_mixed_dual", "D_n16_H6_mixed_dual")
SEEDS = (1, 2, 3)
ARMS = ("A", "B", "J", "AB")


def directory(case, seed, arm):
    return OUT / "runs" / f"{case}__s{seed}__{arm}"


def relative(upper, lower):
    if not math.isfinite(upper) or not math.isfinite(lower) or lower > upper + 1e-8:
        return math.inf
    if upper == lower == 0:
        return 0.
    if upper * lower > 0:
        return abs(upper - lower) / min(abs(upper), abs(lower))
    return math.inf


def objective(arm, scores, start):
    if arm == "A":
        return scores["cmax"]
    if arm == "J":
        return scores["cmax"] / start["cmax"] + .1 * scores["secondary"] / start["secondary"]
    return scores["secondary"]


def require_threshold(record, level):
    gap = relative(record["upper"], record["lower"])
    if record["status"] not in ("optimal", "gaplimit") or gap > LEVELS[level] + 1e-9:
        raise ValueError(f"Unmet {level}: {record}")
    return gap


def finish_second(case, seed, level, parent, start_hash):
    folder = directory(case, seed, "AB") / level
    if (folder / "result.json").is_file():
        return
    spec = matched.CASES[case]
    endpoint = product_solve(folder, parent / "schedule.json", parent / "assignment.json.gz",
                             spec["backend"], spec["n"], seed, "fixed", gap=LEVELS[level])
    dest = folder / "runs/endpoint"
    handoff = read(parent / "result.json")
    measured = product.product_metrics(read(dest / "schedule.json"))
    rec = endpoint["record"]
    rec["gap"] = require_threshold(rec, level)
    if (not endpoint["eligible"] or not endpoint["replay"]["valid"]
            or measured["cmax"] > handoff["metrics"]["cmax"] + cell.EPS
            or abs(measured["secondary"] - rec["upper"]) > cell.EPS
            or measured["secondary"] > handoff["metrics"]["secondary"] + cell.EPS):
        raise ValueError("Stage B differs from the feasible physical handoff or native objective")
    save(folder / "result.json", dict(case=case, seed=seed, arm="AB", level=level,
         start=start_hash, metrics=measured, record=rec, handoff_hash=sha(parent / "result.json"),
         schedule=(dest / "schedule.json").relative_to(ROOT).as_posix(),
         assignment=(dest / "assignment.json.gz").relative_to(ROOT).as_posix(),
         hashes=endpoint["files"], replay=True))


def solve(case, seed, arm, memory):
    from pyscipopt import Eventhdlr, SCIP_EVENTTYPE
    register()
    spec = matched.CASES[case]
    sys.path.insert(0, str(cell.BACKENDS[spec["backend"]]))
    import model
    from validate import validate
    folder = directory(case, seed, arm)
    folder.mkdir(parents=True, exist_ok=True)
    source, assignment = ROOT / spec["source"], ROOT / spec["assignment"]
    if (sha(source), sha(assignment)) != (spec["source_sha256"], spec["assignment_sha256"]):
        raise ValueError("Frozen input changed")
    initial, raw = read(source), cell.values(assignment)
    config = model.Config(**spec["config"])
    x = model.Integrated(config)
    m = x.model
    cell.scip_settings(m, dict(n=spec["n"], seed=seed, seconds=None, gap=.1), folder)
    m.setRealParam("limits/memory", memory)
    original = m.getVars(transformed=False)
    orig_start = cell.attach(x, raw)
    start = product.product_metrics(initial)
    decoded = product.product_metrics(x.result(solution=orig_start))
    if not validate(initial)["valid"] or any(abs(decoded[k] - start[k]) > cell.EPS for k in start):
        raise ValueError("Starting assignment and physical schedule disagree")
    m.freeSol(orig_start)
    if min(start["cmax"], start["secondary"]) <= 0:
        raise ValueError("Nonpositive normalization at the common start")
    for chamber in config.chambers:
        for q in range(2, x.Q):
            active = all(raw.get(x.keep[chamber, i].name, 0) > .5 for i in (q, q-1))
            a, b, c = (raw.get(x.cy.start[chamber, i].name, 0.) for i in (q, q-1, q-2))
            raw[f"rhythm_{chamber}_{q}"] = max(0., abs(a-2*b+c) - (0 if active else x.M))
    secondary, maximum, extra = product.objective_terms(x, raw, False, 25)
    weights = {"A": x.cmax, "B": secondary,
               "J": x.cmax / start["cmax"] + .1 * secondary / start["secondary"]}
    m.setObjective(weights[arm], "minimize")
    warm = cell.attach(x, raw | extra | {maximum.name: start["wait_max"], x.cmax.name: start["cmax"]})
    if abs(m.getSolObjVal(warm) - objective(arm, start, start)) > cell.EPS:
        raise ValueError("Starting native/physical objective mismatch")
    m.addSol(warm)
    save(folder / "settings.json", dict(seed=seed, arm=arm, case=case, native_gap_levels=LEVELS,
         initial=start, start_assignment=spec["assignment_sha256"], start_schedule=spec["source_sha256"],
         threads=m.getParam("lp/threads"), seconds=None, memory_mb=memory,
         original_model=m.getVersion() if hasattr(m, "getVersion") else str(m.getMajorVersion())))

    class Progress(Eventhdlr):
        last_update = 0
        events = SCIP_EVENTTYPE.NODESOLVED | SCIP_EVENTTYPE.DUALBOUNDIMPROVED | SCIP_EVENTTYPE.BESTSOLFOUND

        def eventinit(self):
            self.model.catchEvent(self.events, self)

        def eventexit(self):
            self.model.dropEvent(self.events, self)

        def eventexec(self, event):
            now = time.monotonic()
            if now - self.last_update < 30:
                return
            self.last_update = now
            upper, lower = m.getPrimalbound(), m.getDualbound()
            gap = relative(upper, lower)
            save(folder / "live.json", dict(upper=upper, lower=lower, gap=gap if math.isfinite(gap) else None,
                 nodes=m.getNNodes(), seconds=m.getSolvingTime(), target=m.getParam("limits/gap")))

    m.includeEventhdlr(Progress(), "table4_progress", "Log search progress without changing termination")
    for level, target in LEVELS.items():
        dest = folder / level
        m.setRealParam("limits/gap", target)
        m.optimize()
        record = dict(status=str(m.getStatus()), lower=m.getDualbound(), upper=m.getPrimalbound(),
                      seconds=m.getSolvingTime(), nodes=m.getNNodes())
        save(folder / "last_stop.json", dict(level=level, **record))
        record["gap"] = require_threshold(record, level)
        best = m.getBestSol()
        values = {v.name: m.getSolVal(best, v) for v in original}
        checked = cell.lift(config, values, None)
        if not checked or not checked[3]["valid"]:
            raise ValueError("Original assignment or physical replay failed")
        schedule, sparse = checked[:2]
        measured = product.product_metrics(schedule)
        tolerance = objective(arm, {"cmax": cell.EPS, "secondary": cell.EPS}, start)
        if abs(objective(arm, measured, start) - record["upper"]) > tolerance:
            raise ValueError("Native stopping objective differs from final scheduled events")
        if (dest / "result.json").is_file():
            old = read(dest / "result.json")
            if any(abs(old["metrics"][k] - measured[k]) > cell.EPS for k in measured):
                raise ValueError("A replay of this trajectory changed its recorded endpoint")
        else:
            save(dest / "schedule.json", schedule)
            save(dest / "assignment.json.gz", sparse)
            files = {name: sha(dest / name) for name in ("schedule.json", "assignment.json.gz")}
            save(dest / "result.json", dict(case=case, seed=seed, arm=arm, level=level,
                 start=spec["assignment_sha256"], metrics=measured, record=record, replay=True, hashes=files,
                 schedule=(dest / "schedule.json").relative_to(ROOT).as_posix(),
                 assignment=(dest / "assignment.json.gz").relative_to(ROOT).as_posix()))
        print(case, seed, arm, level, record, measured, flush=True)
        if arm == "A":
            finish_second(case, seed, level, dest, spec["assignment_sha256"])
    m.freeProb()


if __name__ == "__main__":
    case, seed, arm, memory = sys.argv[1:]
    solve(case, int(seed), arm, int(memory))

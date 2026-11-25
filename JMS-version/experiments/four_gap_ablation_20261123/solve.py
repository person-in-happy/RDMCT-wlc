"""Paired four-wafer switch experiment, using the manuscript's frozen policy and product objective."""
import math
from pathlib import Path
import sys
import time
from dataclasses import replace

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "mixed_controls_20261122"))
from controls import JMS, ROOT, cell, product, product_solve, read, save, sha, store_primary

sys.path.insert(0, str(cell.BACKENDS["D"]))
from model import Config, Integrated
from joint_algorithms import improve_skeleton, policy_record
from validate import validate

OUT = JMS / "results/four_gap_ablation_20261123"
CASE = "D_n4_mixed_H10"
LEVELS = {"10pct": .10, "1pct": .01, "0p01pct": .0001}
B_GAP = .0001
ARMS = ("full", "no_rerank", "no_spbs", "projection")
ARCHIVE = JMS / "results/manuscript_projection_20261120_r1/protocol.json"


def input_dir(seed, arm):
    return OUT / "inputs" / f"s{seed}" / ("raw" if arm == "no_spbs" else "prepared")


def directory(seed, arm, level=None):
    folder = OUT / "runs" / f"s{seed}_{arm}"
    return folder / level if level else folder


def manifest():
    record = read(ARCHIVE)["inputs"][CASE + "/cert_raw"]
    return dict(case=CASE, raw=record, seeds=[1, 2, 3], training_seed=1,
                checkpoint=policy_record("proposed", 1), arms=ARMS, gap_A=LEVELS, gap_B=B_GAP,
                seconds_A=None, seconds_B=None, preparation_budget=60, threads=1, inference="CPU",
                native_domain="Count relaxation and strengthened MILP at common raw incumbent cap.",
                native_switch="First observed eligible incumbent and global bound on one trajectory per arm and seed.",
                projection="Separate prepared-start CP-SAT reference using the established grid solver.",
                contrasts={"initialization":"full vs no_spbs including preparation time",
                           "stage_B":"same assignment before and after B",
                           "reranking":"full vs no_rerank, same checkpoint and prepared assignment"})


def prepare(seed):
    spec = read(OUT / "protocol.json")["raw"]
    sched, assignment = ROOT / spec["schedule"], ROOT / spec["assignment"]
    assert (sha(sched), sha(assignment)) == (spec["schedule_sha256"], spec["assignment_sha256"])
    data = read(sched)
    cfg = Config(**data["config"])
    values = cell.values(assignment)
    raw = cell.certify_start(cfg, data, values)
    dest = input_dir(seed, "no_spbs")
    store_primary(dest, raw, dict(seconds=0, source=spec))
    prepared = input_dir(seed, "full")
    prepared.mkdir(parents=True, exist_ok=True)
    x = Integrated(cfg)
    cell.scip_settings(x.model, dict(n=4, seed=seed, seconds=60), prepared)
    values = {v.name: values.get(v.name, 0.) for v in x.model.getVars(transformed=False)}
    started = time.perf_counter()
    values, stages = improve_skeleton(x, values, 60)
    elapsed = time.perf_counter() - started
    x.model.freeProb()
    checked = cell.lift(cfg, values, None, rebuild=True)
    assert checked and checked[2]["cmax"] <= raw[2]["cmax"] + cell.EPS
    store_primary(prepared, checked, dict(seconds=elapsed, stages=stages, raw_sha=sha(dest/"assignment.json.gz")))
    for name in ARMS:
        initial_gates(seed, name)
    save(prepared.parent/"ready.json", dict(seed=seed, raw=raw[2]["cmax"], prepared=checked[2]["cmax"],
                                          seconds=elapsed, cap=math.ceil(raw[2]["cmax"])))


def relative(upper, lower):
    if lower <= 0 or lower > upper + cell.EPS:
        raise ValueError(f"Inconsistent first-stage bounds: {lower}, {upper}")
    return max(0., upper-lower) / lower


def source(seed, arm):
    src = input_dir(seed, arm)
    rec = read(src/"primary.json")
    assert (sha(src/"assignment.json.gz"), sha(src/"schedule.json")) == (rec["assignment_sha256"], rec["schedule_sha256"])
    return src, rec, read(src/"schedule.json")


def open_gate(seed, arm, level, src, record, assignment, cycles):
    dest = directory(seed, arm, level)
    if (dest/"handoff.json").exists():
        return
    assert relative(record["upper"], record["lower"]) <= LEVELS[level]+1e-9
    if assignment is not None:
        save(dest/"candidate.json.gz", cell.sparse(assignment))
        path = dest/"candidate.json.gz"
    else:
        path = src/"assignment.json.gz"
    save(dest/"handoff.json", dict(seed=seed, arm=arm, level=level, record=record, cycles=cycles,
         assignment=str(path.relative_to(ROOT)), sha256=sha(path), start_sha256=sha(src/"assignment.json.gz")))


def initial_gates(seed, arm):
    src, evidence, data = source(seed, arm)
    upper = evidence["metrics"]["cmax"]
    lower = cell.lock_bound(Config(**data["config"]))["lower"]
    for level, target in LEVELS.items():
        if relative(upper, lower) <= target+1e-9:
            open_gate(seed, arm, level, src, dict(upper=upper, lower=lower, seconds=0., calls=0,
                      nodes=0, status="analytic_gap"), None, None)


def native(seed, arm):
    from scip_imports import scip
    sys.path.insert(0, str(HERE.parent/"component_gap_restore_20261119"))
    from component import POLICIES, policy_on_cpu
    src, evidence, data = source(seed, arm)
    base = Config(**data["config"])
    cap = read(src.parent/"ready.json")["cap"]
    plan = cell.capacity(base, cap)
    x = Integrated(replace(base, max_pairs=plan["pairs"], max_cycles=plan["cycles"]))
    raw = read(input_dir(seed, "no_spbs")/"schedule.json")
    cell.strengthen(x, plan, raw, cap)
    m = x.model
    root = directory(seed, arm)
    root.mkdir(parents=True, exist_ok=True)
    cell.scip_settings(m, dict(seed=seed, n=4, seconds=None, gap=min(LEVELS.values())), root)
    m.setRealParam("numerics/feastol", 1e-8)
    policy = POLICIES["no_rerank" if arm == "no_rerank" else "full"]
    agent, weights = policy_on_cpu(m, policy[0], policy, seed, 1)
    assert weights["sha256"] == read(OUT/"protocol.json")["checkpoint"]["sha256"]
    save(root/"settings.json", dict(plan=plan, cap=cap, checkpoint=weights, target=min(LEVELS.values()),
                                    max_seconds=m.getParam("limits/time"), threads=m.getParam("lp/threads")))
    m.setObjective(x.cmax, "minimize")
    m.addSol(cell.attach(x, cell.values(src/"assignment.json.gz")))
    variables = m.getVars(transformed=False)
    analytic = cell.lock_bound(base)["lower"]
    pending = {k for k in LEVELS if not (root/k/"handoff.json").is_file()}

    def observe():
        best = m.getBestSol()
        if best is None:
            return
        upper = m.getSolObjVal(best)
        lower = max(analytic, m.getDualbound())
        if lower > upper + cell.EPS or not math.isfinite(upper):
            return
        gap = relative(upper, lower)
        reached = [k for k in pending if gap <= LEVELS[k]+1e-9]
        if reached:
            seconds = m.getSolvingTime()
            values = {v.name: m.getSolVal(best, v) for v in variables}
            record = dict(upper=upper, lower=lower, seconds=seconds, calls=agent.get_telemetry()["callback_calls"],
                          nodes=m.getNNodes(), status="gap_reached")
            for k in reached:
                open_gate(seed, arm, k, src, record, values, x.Q)
                pending.remove(k)

    class Switch(scip.Eventhdlr):
        events = scip.SCIP_EVENTTYPE.BESTSOLFOUND | scip.SCIP_EVENTTYPE.DUALBOUNDIMPROVED | scip.SCIP_EVENTTYPE.NODESOLVED
        def eventinit(self):
            self.model.catchEvent(self.events, self)
        def eventexit(self):
            self.model.dropEvent(self.events, self)
        def eventexec(self, event):
            observe()

    m.includeEventhdlr(Switch(), "thresholds", "Save paired schedules at the requested switch gaps")
    m.optimize()
    observe()
    save(root/"search.json", dict(status=str(m.getStatus()), seconds=m.getSolvingTime(),
         upper=m.getPrimalbound(), lower=m.getDualbound(), remaining=sorted(pending), calls=agent.get_telemetry()["callback_calls"]))
    m.freeProb()
    if pending:
        raise RuntimeError(f"Search ended before {sorted(pending)}")


def projection(seed, level):
    src, rec, data = source(seed, "projection")
    d = directory(seed, "projection", level)
    if (d/"handoff.json").exists():
        return
    work = d/"projection"
    work.mkdir(parents=True, exist_ok=True)
    checked, r = cell.primary(dict(n=4, seed=seed, train=1, kind="cp", method="default", structure="free",
                              gap=LEVELS[level], seconds=None, bounds=True), Config(**data["config"]),
                              data, cell.values(src/"assignment.json.gz"), work, rec["assignment_sha256"])
    assert r["gate"]
    open_gate(seed, "projection", level, src, dict(upper=r["upper"], lower=r["lower"], seconds=r["seconds"],
              calls=0, nodes=r.get("search", {}).get("branches", 0), status=r["status"]), checked[1]["nonzero"], None)


def finish(seed, arm, level):
    dest = directory(seed, arm, level)
    h = read(dest/"handoff.json")
    src, rec, data = source(seed, arm)
    assert h["start_sha256"] == rec["assignment_sha256"] and sha(ROOT/h["assignment"]) == h["sha256"]
    cfg = Config(**data["config"])
    checked = cell.lift(cfg, cell.values(ROOT/h["assignment"]), h["cycles"], rebuild=True)
    a = h["record"]
    assert checked and abs(checked[2]["cmax"]-a["upper"]) < cell.EPS
    assert relative(checked[2]["cmax"], a["lower"]) <= LEVELS[level]+1e-8
    store_primary(dest/"A", checked, a)
    ordinary = cell.scip_settings
    def strict(model, params, folder):
        ordinary(model, params, folder)
        model.setRealParam("numerics/feastol", 1e-8)
    cell.scip_settings = strict
    e = product_solve(dest/"B", dest/"A/schedule.json", dest/"A/assignment.json.gz", "D", 4, seed,
                      "fixed", seconds=None, gap=B_GAP)
    final = dest/"B/runs/endpoint"
    before = product.product_metrics(checked[0])
    after = product.product_metrics(read(final/"schedule.json"))
    assert sha(final/"schedule.json") == e["files"]["schedule.json"] and sha(final/"assignment.json.gz") == e["files"]["assignment.json.gz"]
    assert e["eligible"] and e["replay"]["valid"] and validate(read(final/"schedule.json"))["valid"]
    assert e["job"]["assignment_sha256"] == sha(dest/"A/assignment.json.gz")
    assert abs(after["secondary"]-e["record"]["upper"]) < cell.EPS and e["record"]["gap"] <= B_GAP+1e-9
    assert after["cmax"] <= before["cmax"]+cell.EPS
    save(dest/"result.json", dict(verified=True, seed=seed, arm=arm, level=level, before=before,
         after=after, start_cmax=rec["metrics"]["cmax"], start_sha256=rec["assignment_sha256"],
         prep_seconds=rec["record"]["seconds"], gate=a, secondary=e["record"], handoff_sha256=sha(dest/"handoff.json")))


if __name__ == "__main__":
    action, seed, *rest = sys.argv[1:]
    seed = int(seed)
    if action == "prepare":
        prepare(seed)
    elif action == "native":
        native(seed, *rest)
    elif action == "projection":
        projection(seed, *rest)
    elif action == "finish":
        finish(seed, *rest)

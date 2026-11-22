"""Run one paired SCIP condition. Both optimization stages have only gap stops."""
from pathlib import Path
import math
import sys
import time

from inputs import BASE, ROOT, TAU, Config, cell, read, save, sha, store_primary, validate
from controls import product, product_solve
from scip_imports import scip


def gap(upper, lower):
    if not all(map(math.isfinite, (upper, lower))) or lower > upper+1e-7:
        return math.inf
    if upper == lower == 0:
        return 0.
    return abs(upper-lower)/min(abs(upper), abs(lower)) if upper*lower > 0 else math.inf


def require_gate(rec, measured):
    if rec["status"] not in ("analytic_gap", "optimal", "gaplimit"):
        raise ValueError(f"Invalid stop status: {rec['status']}")
    if abs(rec["upper"]-measured) > cell.EPS or gap(measured, rec["lower"]) > TAU+1e-9:
        raise ValueError(f"Replayed gap exceeds threshold: {measured}, {rec}")


def run(key, mem_mb):
    spec = read(BASE/"protocol.json")["jobs"][key]
    case, seed, version = spec["case"], spec["seed"], spec["initialization"]
    inputs = BASE/"inputs"/case/f"s{seed}"
    manifest = read(inputs/"input.json")
    src = inputs/version
    old = manifest["sources"][version]
    assert sha(src/"schedule.json") == old["schedule"]
    assert sha(src/"assignment.json.gz") == old["assignment"]
    task = dict(n=16, seed=seed, method=spec["method"], train=spec["training_seed"],
                seconds=None, gap=TAU, kind="scip", structure="free", bounds=False)
    folder = BASE/"runs"/key
    A = folder/"A"
    A.mkdir(parents=True, exist_ok=True)
    state = dict(stage="A", upper=old["cmax"], lower=cell.lock_bound(Config(**manifest["domain"]))["lower"])
    def status(**entries):
        state.update(entries, updated=time.time())
        save(folder/"live.json", state)
    status(activity="building_model")
    ordinary = cell.scip_settings

    class Progress(scip.Eventhdlr):
        def eventinit(self):
            self.model.catchEvent(self.types, self)
            self.saved = 0.

        def eventexit(self):
            self.model.dropEvent(self.types, self)

        def eventexec(self, event):
            if time.monotonic()-self.saved < 15:
                return
            lb = self.model.getDualbound()
            ub = self.model.getPrimalbound()
            if -1e18 < lb <= ub < 1e18:
                status(activity="search", lower=max(state["lower"], lb), upper=min(state["upper"], ub),
                       nodes=self.model.getNNodes(), solver_seconds=self.model.getSolvingTime())
                self.saved = time.monotonic()

    def settings(model, params, target):
        assert params.get("seconds") is None and params["gap"] == TAU
        ordinary(model, params, target)
        model.setRealParam("limits/memory", mem_mb)
        if state["stage"] == "B":
            model.setRealParam("numerics/feastol", 1e-8)
        observer = Progress()
        observer.types = (scip.SCIP_EVENTTYPE.NODESOLVED | scip.SCIP_EVENTTYPE.BESTSOLFOUND |
                          scip.SCIP_EVENTTYPE.DUALBOUNDIMPROVED)
        model.includeEventhdlr(observer, "gap_monitor", "observe bounds and nodes",)
        save(target/"limits.json", dict(relative=model.getParam("limits/gap"),
             time=model.getParam("limits/time"), memory_MB=model.getParam("limits/memory"),
             threads=model.getParam("lp/threads"), feastol=model.getParam("numerics/feastol")))
        status(activity="solver_ready")

    cell.scip_settings = settings
    if not (A/"primary.json").is_file():
        data = read(src/"schedule.json")
        checked, rec = cell.primary(task, Config(**manifest["domain"]), data,
                                    cell.values(src/"assignment.json.gz"), A, old["assignment"])
        require_gate(rec, checked[2]["cmax"])
        if spec["method"] != "default":
            assert rec["policy"]["sha256"] == spec["checkpoint_sha256"]
        store_primary(A, checked, rec)
    primary = read(A/"primary.json")
    assert primary["replay"]["valid"] and primary["schedule_sha256"] == sha(A/"schedule.json")
    assert primary["assignment_sha256"] == sha(A/"assignment.json.gz")
    require_gate(primary["record"], primary["metrics"]["cmax"])
    status(stage="B", activity="building_model", upper=primary["metrics"]["secondary"], lower=0., nodes=0)
    e = product_solve(folder/"B", A/"schedule.json", A/"assignment.json.gz", "D", 16,
                      seed, "fixed", seconds=None, gap=TAU)
    end = folder/"B/runs/endpoint"
    final = read(end/"schedule.json")
    measured = product.product_metrics(final)
    require_gate(e["record"], measured["secondary"])
    assert e["eligible"] and e["replay"]["valid"]
    assert sha(end/"schedule.json") == e["files"]["schedule.json"]
    assert sha(end/"assignment.json.gz") == e["files"]["assignment.json.gz"]
    assert e["job"]["assignment_sha256"] == primary["assignment_sha256"]
    assert measured["cmax"] <= primary["record"]["upper"] + cell.EPS
    for schedule in (read(A/"schedule.json"), final):
        schedule["config"] = manifest["unrestricted"]
        assert validate(schedule)["valid"]
    save(folder/"result.json", dict(key=key, **spec, initial=old["assignment"],
         input_manifest_sha256=sha(inputs/"input.json"), A=primary["record"], B=e["record"],
         physical_replay=True, metrics=measured, verified=True,
         primary_sha256=sha(A/"primary.json"), secondary_sha256=sha(end/"result.json")))
    status(activity="complete", upper=measured["secondary"], lower=e["record"]["lower"])


if __name__ == "__main__":
    run(sys.argv[1], int(sys.argv[2]))

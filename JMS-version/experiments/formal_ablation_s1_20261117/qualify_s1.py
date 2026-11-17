"""Independent S1 feasible-start acquisition, followed by unrestricted validation."""
from __future__ import annotations
import argparse
from dataclasses import asdict
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import traceback

HERE = Path(__file__).resolve().parent
FORMAL_PATH = HERE.parent / "formal_ablation_20261117/formal_ablation.py"
loader = importlib.util.spec_from_file_location("frozen_formal", FORMAL_PATH)
f = importlib.util.module_from_spec(loader)
loader.loader.exec_module(f)
ROOT, JMS = f.ROOT, f.JMS
DEFAULT = JMS / "results/s1_initialization_20261117_r1"
EXISTING = JMS / "results/formal_ablation_20261117_r1"
CASES = ("n2_2x2_scenario1", "n2_mixed_scenario1")


def specification(case, alternative=False):
    """Only finite configuration fixed; transport, waits, slots and dummy reuse are free."""
    if case == "n2_2x2_scenario1":
        chamber = 3 if alternative else 2
        pairs = {0: ("2x2", chamber, ["LP1_W1", "LP1_W2"]),
                 2: ("2x2", chamber, []), 3: ("2x2", chamber, []),
                 4: ("clean", chamber, []), 5: ("clean", chamber, [])}
        cycles = {(chamber, 0): ("2x2", [2, 0], 0),
                  (chamber, 1): ("2x2", [0, 3], 3),
                  (chamber, 2): ("clean", [4, 5], 5)}
    elif case == "n2_mixed_scenario1":
        full, mixed = (3, 2) if alternative else (2, 3)
        pairs = {0: ("4x1", full, ["LP1_W1"]), 1: ("2x2", mixed, ["LP1_W2"]),
                 2: ("4x1", full, []), 3: ("2x2", mixed, []), 4: ("2x2", mixed, []),
                 5: ("clean", mixed, []), 6: ("clean", mixed, [])}
        cycles = {(full, 0): ("4x1", [2, 0], 2 if alternative else 0),
                  (mixed, 0): ("2x2", [3, 1], 1),
                  (mixed, 1): ("2x2", [1, 4], 4),
                  (mixed, 2): ("clean", [5, 6], 6)}
    else:
        raise ValueError("Unknown fixed S1 case")
    return pairs, cycles


def prepare(out):
    if out.exists():
        raise FileExistsError("Never overwrite acquisition records")
    configs = JMS / "results/journal_d_qualification_20261109_r1/configs"
    assets = f.inventory() | {str(Path(__file__).relative_to(ROOT)): f.sha(__file__),
                             str((HERE / "qualify.ps1").relative_to(ROOT)): f.sha(HERE / "qualify.ps1")}
    cases = []
    for case in CASES:
        path = configs / (case + ".json")
        cfg = f.read(path)
        assert cfg["dummy_count"] == 4 and cfg["cleaning_interval"] == 2
        assert sum(cfg["load_ports"]["LP1"].values()) == 2
        cases.append(dict(case=case, config=cfg, source_config=str(path), config_sha256=f.sha(path)))
    attempts = [dict(name="structured", seed=17, seconds=120., alternative=False, emphasis="feasibility"),
                dict(name="structured_alternative", seed=19, seconds=300., alternative=True, emphasis="feasibility"),
                dict(name="structured_default", seed=23, seconds=600., alternative=False, emphasis="default"),
                dict(name="unrestricted", seed=29, seconds=3600., alternative=None, emphasis="feasibility")]
    spec = dict(created_utc=f.stamp(), cases=cases, attempts=attempts, assets=assets,
                sources={c["source_config"]: c["config_sha256"] for c in cases},
                settings=dict(threads=1, workers=1, min_available_gib=8., launch_gib=12., refresh_seconds=10.),
                source_selection="First independently validated feasible result in the prospectively listed attempts, no comparison-method performance used.",
                scope="Offline common initial assignment acquisition only. Temporary structure restrictions are removed before full original-model and physical validation. Original S1 parameters unchanged. Acquisition cost is not part of the later 300-second ablation budget.",
                resource_coordination="Existing frozen formal supervisor is allowed to remain idle. Wait for all its active workers to finish. Its existing external-worker guard will defer new launches while this foreground acquisition is active.")
    out.mkdir(parents=True)
    f.dump(out / "campaign.json", spec)
    f.dump(out / "contract.json", dict(campaign_sha256=f.sha(out / "campaign.json")))
    for rel in assets:
        target = out / "frozen_code" / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / rel, target)
    print("PREPARED two original S1 cases; no solve started", flush=True)


def idle_existing_supervisor(pid):
    import psutil
    try:
        args = psutil.Process(pid).cmdline()
        i = args.index("--campaign")
        return (Path(args[i + 1]).resolve() == EXISTING.resolve()
                and "run" in args and "worker" not in args)
    except (psutil.NoSuchProcess, psutil.AccessDenied, ValueError, IndexError):
        return False


def blockers(own):
    return [pid for pid in f.foreign_workers(own) if not idle_existing_supervisor(pid)]


def fix_configuration(x, pairs, cycles):
    from pjobs import task_for_product
    groups = task_for_product(x.cfg)
    m, constraints = x.model, []
    def equal(var, value):
        if isinstance(var, (int, float)):
            if abs(var - value) > 1e-7:
                raise ValueError("Configuration contradicts a model constant")
        elif hasattr(var, "getLbOriginal"):
            m.chgVarLb(var, value)
            m.chgVarUb(var, value)
        else:
            constraints.append(m.addCons(var == value))
    for p in range(x.P):
        chosen = pairs.get(p)
        equal(x.pair.active[p], int(chosen is not None))
        for mode in ("4x1", "2x2", "clean"):
            equal(x.pair.mode[p, mode], int(chosen is not None and chosen[0] == mode))
        for chamber in x.cfg.chambers:
            equal(x.pair.chamber[p, chamber], int(chosen is not None and chosen[1] == chamber))
        if p < x.N:
            for r in (0, 1):
                product = chosen[2][r] if chosen is not None and r < len(chosen[2]) else None
                for group in x.groups:
                    equal(x.pair.member[group.identifier, p, r], int(product is not None and groups[product].identifier == group.identifier))
    for chamber in x.cfg.chambers:
        for q in range(x.Q):
            chosen = cycles.get((chamber, q))
            for mode in ("4x1", "2x2", "clean"):
                equal(x.cy.kind[chamber, q, mode], int(chosen is not None and chosen[0] == mode))
            for p in range(x.P):
                equal(x.cy.occupancy[p, chamber, q], int(chosen is not None and p in chosen[1]))
                equal(x.front[p, chamber, q], int(chosen is not None and p == chosen[2]))
    return constraints


def worker(out, case_name, attempt_name):
    spec = f.checked(out)
    case = next(c for c in spec["cases"] if c["case"] == case_name)
    attempt = next(a for a in spec["attempts"] if a["name"] == attempt_name)
    directory = out / "attempts" / case_name / attempt_name
    directory.mkdir(parents=True, exist_ok=False)
    backend, validate = f.backend_modules()
    from scip_imports import scip
    import psutil
    started = time.monotonic()
    x = backend.Integrated(backend.Config(**case["config"]))
    m = x.model
    original_bounds = {v.name: (v.getLbOriginal(), v.getUbOriginal()) for v in m.getVars(transformed=False)}
    original_constraints = m.getNConss()
    m.setLogfile(str(directory / "solver.log"))
    m.setIntParam("parallel/maxnthreads", 1)
    m.setIntParam("lp/threads", 1)
    m.setIntParam("randomization/randomseedshift", attempt["seed"])
    m.setIntParam("limits/solutions", 1)
    m.setRealParam("limits/time", attempt["seconds"])
    if attempt["emphasis"] == "feasibility":
        m.setEmphasis(scip.SCIP_PARAMEMPHASIS.FEASIBILITY, quiet=True)
    extra = []
    if attempt["alternative"] is not None:
        pairs, cycles = specification(case_name, attempt["alternative"])
        f.dump(directory / "configuration.json", dict(pairs=pairs, cycles={str(k): v for k, v in cycles.items()}))
        extra = fix_configuration(x, pairs, cycles)
    interrupted = False
    class Guard(scip.Eventhdlr):
        def eventinit(self):
            self.model.catchEvent(scip.SCIP_EVENTTYPE.LPSOLVED | scip.SCIP_EVENTTYPE.BESTSOLFOUND, self)
        def eventexit(self):
            self.model.dropEvent(scip.SCIP_EVENTTYPE.LPSOLVED | scip.SCIP_EVENTTYPE.BESTSOLFOUND, self)
        def eventexec(self, event):
            nonlocal interrupted
            if psutil.virtual_memory().available / 1024**3 < spec["settings"]["min_available_gib"]:
                interrupted = True
                m.interruptSolve()
    m.includeEventhdlr(Guard(), "source_guard", "source resource guard")
    build_seconds = time.monotonic() - started
    solving = time.monotonic()
    m.optimize()
    seconds = time.monotonic() - solving
    state = str(m.getStatus())
    evidence = dict(case=case_name, attempt=attempt, status=state, solutions=m.getNSols(),
                    build_seconds=build_seconds, solve_wall_seconds=seconds,
                    scip_seconds=m.getSolvingTime(), resource_interruption=interrupted,
                    restricted_search=bool(attempt["alternative"] is not None),
                    full_variables=len(original_bounds), full_constraints=original_constraints,
                    valid=False, ended_utc=f.stamp())
    if m.getNSols():
        best = m.getBestSol()
        values = {v.name: m.getSolVal(best, v) for v in m.getVars(transformed=False)}
        m.freeTransform()
        for constraint in extra:
            m.delCons(constraint)
        for var in m.getVars(transformed=False):
            lb, ub = original_bounds[var.name]
            m.chgVarLb(var, lb)
            m.chgVarUb(var, ub)
        assert m.getNConss() == original_constraints
        sol = f.assignment(m, values)
        accepted = bool(m.checkSol(sol, printreason=True, completely=True, original=True))
        result = x.result(solution=sol)
        verdict = validate(result)
        metrics = f.physical_metrics(result)
        # Tighten Cmax to the actual final product return without altering the schedule.
        m.setSolVal(sol, x.cmax, metrics["cmax"])
        accepted = accepted and bool(m.checkSol(sol, printreason=True, completely=True, original=True))
        values = {v.name: m.getSolVal(sol, v) for v in m.getVars(transformed=False)}
        result = x.result(solution=sol)
        result.update(validation=verdict, original_model_check=accepted, global_optimality_claim=False,
                      experiment_scope="offline_S1_common_initial_assignment", source_attempt=attempt_name)
        evidence.update(valid=bool(accepted and verdict["valid"] and not interrupted), metrics=metrics,
                        validation=verdict, temporary_restrictions_removed=True)
        f.dump(directory / "result.json", result)
        f.dump(directory / "variables.json", dict(values=values))
        evidence.update(result_sha256=f.sha(directory / "result.json"), variables_sha256=f.sha(directory / "variables.json"))
        m.freeSol(sol)
    f.dump(directory / "evidence.json", evidence)
    m.freeProb()
    print("ATTEMPT " + json.dumps(evidence, ensure_ascii=False), flush=True)


def archive_incomplete(out, directory):
    source = directory.resolve()
    root = out.resolve()
    if source == root or not source.is_relative_to(root / "attempts"):
        raise ValueError("Refuse archive outside this acquisition directory")
    target = root / "interrupted_attempts" / (directory.parent.name + "__" + directory.name + "__" + str(time.time_ns()))
    assert target.is_relative_to(root)
    target.parent.mkdir(parents=True, exist_ok=True)
    source.rename(target)


def run(out):
    import psutil
    spec = f.checked(out)
    own = os.getpid()
    lock = out / "supervisor.lock"
    if lock.exists():
        old = int(lock.read_text())
        if psutil.pid_exists(old):
            raise RuntimeError("Acquisition supervisor still exists: " + str(old))
        lock.rename(out / ("stale_lock_" + str(time.time_ns())))
    fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    os.write(fd, str(own).encode()); os.close(fd)
    active = None
    qualified = []
    try:
        for case in spec["cases"]:
            name = case["case"]
            receipt_path = out / "qualified" / name / "receipt.json"
            if receipt_path.exists():
                receipt = f.read(receipt_path)
                assert f.sha(receipt["source"]) == receipt["result_sha256"]
                assert f.sha(receipt["values"]) == receipt["variables_sha256"]
                qualified.append(name)
                continue
            for attempt in spec["attempts"]:
                directory = out / "attempts" / name / attempt["name"]
                if directory.exists() and not (directory / "evidence.json").exists():
                    archive_incomplete(out, directory)
                if not (directory / "evidence.json").exists():
                    while True:
                        waiters = blockers({own})
                        free = psutil.virtual_memory().available / 1024**3
                        if not waiters and free >= spec["settings"]["launch_gib"]:
                            break
                        state = dict(updated_utc=f.stamp(), supervisor_pid=own, phase="waiting_for_existing_workers",
                             completed=len(qualified), expected=2, blocked_by_pids=waiters, available_gib=free)
                        f.dump(out / "live_status.json", state)
                        print("WAIT " + json.dumps(state), flush=True)
                        time.sleep(10)
                    logs = out / "logs"; logs.mkdir(exist_ok=True)
                    log = (logs / (name + "__" + attempt["name"] + "__" + str(time.time_ns()) + ".log")).open("wb")
                    env = dict(os.environ, OMP_NUM_THREADS="1", MKL_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1")
                    active = subprocess.Popen([sys.executable, "-X", "utf8", "-u", str(__file__), "worker",
                             "--campaign", str(out), "--case", name, "--attempt", attempt["name"]], cwd=ROOT,
                             env=env, stdout=log, stderr=subprocess.STDOUT)
                    start = time.monotonic()
                    while active.poll() is None:
                        elapsed = time.monotonic() - start
                        state = dict(updated_utc=f.stamp(), supervisor_pid=own, worker_pid=active.pid,
                             phase="searching_common_initial_assignment", completed=len(qualified), expected=2,
                             case=name, attempt=attempt["name"], elapsed_seconds=elapsed,
                             attempt_limit=attempt["seconds"], current_attempt_remaining_seconds=max(0., attempt["seconds"]-elapsed),
                             available_gib=psutil.virtual_memory().available/1024**3)
                        f.dump(out / "live_status.json", state)
                        print(f'qualified={len(qualified)}/2 case={name} attempt={attempt["name"]} elapsed={elapsed:.0f}s '
                              f'current_remaining~{max(0.,attempt["seconds"]-elapsed):.0f}s RAM={state["available_gib"]:.1f}GiB', flush=True)
                        if state["available_gib"] < spec["settings"]["min_available_gib"] or elapsed > attempt["seconds"] + 180:
                            active.terminate(); active.wait(timeout=30)
                            break
                        time.sleep(10)
                    code = active.returncode
                    active = None
                    log.close()
                    if code != 0 or not (directory / "evidence.json").exists():
                        raise RuntimeError("Acquisition worker failed; preserved logs: " + str(directory))
                evidence = f.read(directory / "evidence.json")
                print("RESULT " + name + " " + attempt["name"] + " valid=" + str(evidence["valid"]), flush=True)
                if evidence["valid"]:
                    receipt = dict(case=name, source=str(directory / "result.json"), values=str(directory / "variables.json"),
                         result_sha256=evidence["result_sha256"], variables_sha256=evidence["variables_sha256"],
                         config_sha256=case["config_sha256"], metrics=evidence["metrics"],
                         selected_attempt=attempt["name"], qualified_utc=f.stamp())
                    f.dump(receipt_path, receipt)
                    qualified.append(name)
                    print("QUALIFIED " + name + " A=" + str(evidence["metrics"]["cmax"]), flush=True)
                    break
            if name not in qualified:
                f.dump(out / "needs_review.json", dict(case=name, reason="all_predeclared_attempts_without_qualified_incumbent", ended_utc=f.stamp()))
                raise RuntimeError("S1 acquisition requires further inspection; no data fabricated")
        f.dump(out / "finished.json", dict(expected=2, qualified=qualified, valid=len(qualified), ended_utc=f.stamp()))
        print("BOTH S1 COMMON INITIAL ASSIGNMENTS VALIDATED", flush=True)
        # Keep the existing queue quiescent while the separately frozen ablation is prepared.
        deadline = time.monotonic() + 600
        while not (out / "release_resources.json").exists() and time.monotonic() < deadline:
            f.dump(out / "live_status.json", dict(updated_utc=f.stamp(), supervisor_pid=own,
                   completed=2, expected=2, phase="qualified_waiting_for_ablation_handoff", seconds_until_auto_release=deadline-time.monotonic()))
            print("qualified=2/2; ready for ablation handoff", flush=True)
            time.sleep(10)
    finally:
        if active is not None and active.poll() is None:
            active.terminate(); active.wait(timeout=30)
        if lock.exists() and lock.read_text().strip() == str(own):
            lock.unlink()


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("action", choices=("prepare", "run", "worker"))
    parser.add_argument("--campaign", default=str(DEFAULT))
    parser.add_argument("--case"); parser.add_argument("--attempt")
    args = parser.parse_args()
    out = Path(args.campaign).resolve()
    if not out.is_relative_to((JMS / "results").resolve()) or out == (JMS / "results").resolve():
        parser.error("Use an isolated results subdirectory")
    if args.action == "prepare": prepare(out)
    elif args.action == "run": run(out)
    else: worker(out, args.case, args.attempt)


if __name__ == "__main__":
    try:
        main()
    except BaseException:
        traceback.print_exc()
        raise

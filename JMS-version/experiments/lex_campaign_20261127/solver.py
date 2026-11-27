"""Protected-makespan lexicographic search on the extended unload model."""
from dataclasses import replace
import math
from pathlib import Path
import sys
import time

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parent / "stall_nodes_20261127"),
                str(HERE.parent / "sublevel_bounds_20261120")]
from phases import (CAP_TOL, CHECK_TOL, Config, Integrated, check_start_matches,
                    checked_assignment, lift_schedule, normalize_schedule,
                    physical_bound, process_auxiliaries, relative_gap, verify_events)
from bounds import capacity
from scip_imports import scip

EPS = CAP_TOL + 1e-9
SCOPES = {
    "A": "full extended domain under the verified incumbent makespan",
    "B1": "handoff integer decisions fixed except synchronization; continuous retiming",
    "B2": "fixed pairing, chamber, cycles and front positions; resource order, hands and terminal priority free",
    "B3": "full extended domain under the stage-A protected makespan",
}


class CandidateRejected(ValueError):
    """A pool candidate did not pass independent replay or native row checks."""


def _compact(cfg, schedule):
    canonical = normalize_schedule(cfg, schedule)
    return replace(cfg, max_pairs=max(p["id"] for p in canonical["pairs"]) + 1,
                   max_cycles=max(c["index"] for c in canonical["cycles"]) + 1)


def _model(cfg, spec):
    x = Integrated(cfg)
    m = x.model
    m.setIntParam("parallel/maxnthreads", 1)
    m.setIntParam("lp/threads", 1)
    m.setIntParam("timing/clocktype", 2)
    m.setIntParam("randomization/randomseedshift", int(spec.get("seed", 1)))
    m.setRealParam("numerics/feastol", 1e-8)
    m.setRealParam("limits/memory", float(spec.get("memory_mib", 10000)))
    m.setRealParam("limits/gap", 0.)
    m.setRealParam("limits/absgap", 0.)
    m.setLongintParam("limits/stallnodes", -1)
    return x


def _remaining(deadline):
    return max(0., deadline - time.monotonic())


def _fix_binary(m, var, value):
    m.chgVarLb(var, round(value))
    m.chgVarUb(var, round(value))


def _start(x, schedule, assignment, deadline):
    m = x.model
    # Inactive time/order variables and cycle labels depend on candidate dimensions.
    # Carry a native handoff exactly when rebuilding the same original model.
    same_shape = (schedule.get("candidate_pairs"), schedule.get("candidate_cycles")) == (x.P, x.Q)
    if assignment is not None and same_shape:
        values = assignment
        reference = schedule
    else:
        m.setRealParam("limits/time", _remaining(deadline))
        values, reference = lift_schedule(x, schedule)
    sol = checked_assignment(x, values)
    try:
        decoded, observed = check_start_matches(x, sol, reference)
    finally:
        m.freeSol(sol)
    values = {v.name: values.get(v.name, 0.) for v in m.getVars(transformed=False)}
    values[x.cmax.name] = decoded["cmax"] = observed["cmax"]
    return decoded, values


class Archive:
    def __init__(self, stage, schedule, assignment, spec, checkpoint):
        self.stage = stage
        self.key = "cmax" if stage == "A" else "secondary"
        self.spec = spec
        self.checkpoint = checkpoint
        self.started = time.monotonic()
        self.replay, self.initial = verify_events(schedule)
        self.cfg = replace(Config(**schedule["config"]), max_pairs=0, max_cycles=0)
        self.cap = float(spec.get("primary_cap", self.initial["cmax"])
                         if stage != "A" else self.initial["cmax"])
        if self.initial["cmax"] > self.cap + EPS:
            raise ValueError("Input violates the registered makespan cap")
        objective = "A" if stage == "A" else "B"
        self.global_lower = max(physical_bound(objective, self.cfg), float(spec["lb_" + objective]))
        self.local_lower = self.global_lower
        self.status = "not_started"
        self.best = (schedule, assignment, self.initial)
        self.shortest = self.initial["cmax"]
        self.frontier = [self.best]
        self.details = dict(spbs=[], spbs_completed=False, spbs_wall_seconds=0.,
                            native_primal=None, native_dual=None, rejected_pool_solutions=0,
                            solver_seconds=0., nodes=0, policy=None, policy_calls=0,
                            total_search_solutions_scored=0, original_rows_checked=0)

    def record(self, reason):
        score = self.best[2]
        upper = score[self.key]
        if self.local_lower > upper + EPS:
            raise ValueError(f"{self.stage} lower bound {self.local_lower} exceeds {upper}")
        lower = min(upper, self.local_lower)
        return dict(stage=self.stage, valid=True, upper=upper, lower=lower,
                    global_lower=min(upper, self.global_lower), gap=relative_gap(upper, lower),
                    gap_met=upper - lower <= EPS, certified_global=upper-self.global_lower <= EPS,
                    target_gap=0., stall_nodes=-1, native_status=self.status, stop_reason=reason,
                    scope=SCOPES[self.stage], cmax_cap=self.cap, primary_cap=self.cap,
                    metrics=score, initial_metrics=self.initial, validation=self.replay,
                    wall_seconds=time.monotonic()-self.started, **self.details)

    def publish(self, reason):
        schedule, assignment, _ = self.best
        result = self.record(reason), schedule, assignment
        if self.checkpoint is not None:
            self.checkpoint(*result)
        return result

    def witness(self, x, sol, score_hint=None, replace_equal=False):
        m = x.model
        if score_hint is not None:
            c, b = score_hint
            if c > self.shortest + EPS or (c >= self.shortest and b >= self.best[2]["secondary"]):
                return
        try:
            schedule = x.result(solution=sol)
            replay, score = verify_events(schedule)
        except (ValueError, KeyError, StopIteration, IndexError) as exc:
            raise CandidateRejected(f"Event decode/replay failed: {exc}") from exc
        c, b = score["cmax"], score["secondary"]
        if c > self.cap + EPS:
            raise CandidateRejected(f"Physical makespan {c} exceeds registered cap {self.cap}")
        if c > self.shortest + EPS:
            return
        if not replace_equal and any(s[2]["cmax"] <= c and s[2]["secondary"] <= b for s in self.frontier):
            return
        if not m.checkSol(sol, original=True, completely=True, printreason=False):
            raise CandidateRejected("Native candidate does not satisfy all original rows")
        variables = m.getVars(transformed=False)
        values = {v.name: val for v in variables
                  if (val := m.getSolVal(sol, v)) != 0.}
        schedule["cmax"] = values[x.cmax.name] = c
        if self.stage != "A":
            values.update(process_auxiliaries(x, schedule, score))
        polished = m.createOrigSol()
        try:
            for v in variables:
                if values.get(v.name):
                    m.setSolVal(polished, v, values[v.name])
            if not m.checkSol(polished, original=True, completely=True, printreason=False):
                raise CandidateRejected("Polished candidate violates original model rows")
            if abs(m.getSolObjVal(polished)-score[self.key]) > CHECK_TOL:
                raise CandidateRejected("Native and physical scores differ after polishing")
        finally:
            m.freeSol(polished)
        self.shortest = min(self.shortest, c)
        self.frontier = [s for s in self.frontier if s[2]["cmax"] <= self.shortest + EPS
                         and not (c <= s[2]["cmax"] and b <= s[2]["secondary"])]
        if replace_equal:
            # The lift is the native representation of the identical physical seed.
            self.frontier = [s for s in self.frontier if s[1] is not None or
                             abs(s[2]["cmax"]-c) > EPS or abs(s[2]["secondary"]-b) > EPS]
        self.frontier.append((schedule, values, score))
        previous = self.best
        self.best = min(self.frontier, key=lambda s: (s[2]["secondary"], s[2]["cmax"]))
        if self.best is not previous:
            self.replay = replay if self.best[0] is schedule else verify_events(self.best[0])[0]
            self.details["original_rows_checked"] = m.getNConss(transformed=False)
            self.publish("verified_native_incumbent")


class Observer(scip.Eventhdlr):
    """Archive solutions from SCIP's primal pool at solution events and on return."""
    def __init__(self, x, archive, track_dual):
        self.x, self.archive = x, archive
        self.seen = set()
        self.error = None
        self.track_dual = track_dual
        self.met_bound = False
        self.next_bound_save = time.monotonic()+30
        self.next_poll = 0.
        self.products = [(p, j) for j in x.jobs.values() if j["product"] is not None
                         for p, _ in [j["product"]]]

    def eventinit(self):
        self.model.catchEvent(scip.SCIP_EVENTTYPE.SOLFOUND | scip.SCIP_EVENTTYPE.NODEFOCUSED, self)

    def eventexit(self):
        self.model.dropEvent(scip.SCIP_EVENTTYPE.SOLFOUND | scip.SCIP_EVENTTYPE.NODEFOCUSED, self)

    def eventexec(self, event):
        if self.error is not None:
            return
        if event.getType() == scip.SCIP_EVENTTYPE.NODEFOCUSED and time.monotonic() < self.next_poll:
            return
        self.next_poll = time.monotonic() + 5.
        try:
            self.inspect()
            if self.archive.record("checking")["certified_global"]:
                self.met_bound = True
                self.model.interruptSolve()
            elif self.track_dual and time.monotonic() >= self.next_bound_save and self.model.getStage() == 9:
                self.next_bound_save = time.monotonic()+30
                dual = self.model.getDualbound()
                if (math.isfinite(dual) and not self.model.isInfinity(abs(dual))
                        and dual > self.archive.local_lower + EPS):
                    self.archive.local_lower = dual
                    if self.archive.stage in ("A", "B3"):
                        self.archive.global_lower = max(self.archive.global_lower, dual)
                    self.archive.details["native_dual"] = dual
                    self.archive.publish("native_bound_improvement")
        except Exception as exc:
            self.error = exc
            self.model.interruptSolve()

    def inspect(self):
        x, m = self.x, self.x.model
        for sol in m.getSols():
            v = lambda var: float(var) if isinstance(var, (float, int)) else m.getSolVal(sol, var)
            c = 0.
            dwells = {False: [], True: []}
            for p, j in self.products:
                if v(j["active"]) < .5:
                    continue
                mixed = v(x.pair.mode[p,"2x2"]) > .5
                duration = 2*x.cfg.mix_time if mixed else x.cfg.full_time
                dwells[mixed].append(max(0., v(j["unload_s"]) - v(j["load_e"]) - duration))
                c = max(c, v(j["last"]["e"]))
            if c > self.archive.shortest + EPS:
                continue
            spread = max(max(d)-min(d) for d in dwells.values() if d)
            deficit = sum(x.cfg.cleaning_interval-round(v(x.cy.counter[ch,q-1]))
                          for ch in x.cfg.chambers for q in range(1, x.Q)
                          if v(x.cy.kind[ch,q,"clean"]) > .5)
            b = sum(map(sum, dwells.values()))/x.N + spread**2/2 + deficit
            signature = (c, b)
            if signature not in self.seen:
                self.archive.details["total_search_solutions_scored"] += 1
                try:
                    self.archive.witness(x, sol, signature)
                except CandidateRejected as exc:
                    # A pool may still expose a solution from the preceding
                    # freeTransform/re-fixing cycle. Keep verified witnesses.
                    self.archive.details["rejected_pool_solutions"] += 1
                    self.archive.details["last_pool_rejection"] = str(exc)
                else:
                    self.seen.add(signature)


def _install_observer(x, archive, track_dual=False):
    observer = Observer(x, archive, track_dual)
    x.model.includeEventhdlr(observer, "verified_lex_pool", "replay retained lexicographic improvements")
    return observer


def _warm(x, schedule, values, archive):
    m = x.model
    warm = checked_assignment(x, values)
    archive.witness(x, warm, replace_equal=True)
    if not m.addSol(warm) and not m.getNSols():
        raise ValueError("Native model lost its verified starting witness")


def _optimize(x, observer, deadline):
    m = x.model
    m.setRealParam("limits/time", _remaining(deadline))
    m.optimize()
    if observer.error:
        raise observer.error
    if str(m.getStatus()) == "userinterrupt" and not observer.met_bound:
        raise KeyboardInterrupt
    observer.inspect()


def _spbs(archive, deadline):
    schedule, assignment, _ = archive.best
    started = time.monotonic()
    seconds = min(float(archive.spec.get("spbs_seconds", 60.)), _remaining(deadline))
    end = started + seconds
    x = _model(_compact(archive.cfg, schedule), archive.spec)
    m = x.model
    try:
        if _remaining(end) == 0:
            return
        schedule, values = _start(x, schedule, assignment, end)
        _warm(x, schedule, values, archive)
        observer = _install_observer(x, archive)
        vtr_prefixes = tuple("order_" + e["name"] + "_" for e in x.robots["VTR"])
        for level in range(1, 6):
            if not _remaining(end) or archive.record("checking")["certified_global"]:
                break
            fixed = []
            for v in m.getVars(transformed=False):
                name = v.name
                if v.vtype() == "CONTINUOUS" or name.startswith("sync_"):
                    continue
                if (level >= 5 and not name.startswith(("jp_", "pj_", "jc_used_", "jc_kind_"))
                    or level >= 4 and name.startswith("order_")
                    or level >= 3 and name.startswith(("order_U_", "order_L_"))
                    or level >= 2 and name.startswith(vtr_prefixes)):
                    continue
                fixed.append((v, v.getLbOriginal(), v.getUbOriginal()))
                _fix_binary(m, v, values.get(name, 0.))
            warm = checked_assignment(x, values)
            m.addSol(warm)
            began = time.monotonic()
            _optimize(x, observer, min(end, began+seconds/5))
            archive.details["spbs"].append(dict(level=level, status=str(m.getStatus()),
                solver_s=m.getSolvingTime(), wall_s=time.monotonic()-began, fixed=len(fixed),
                best_cmax=archive.best[2]["cmax"]))
            m.freeTransform()
            for var, lb, ub in fixed:
                m.chgVarLb(var, lb)
                m.chgVarUb(var, ub)
            winner, chosen_values, _ = archive.best
            if chosen_values is not None and (winner.get("candidate_pairs"), winner.get("candidate_cycles")) == (x.P, x.Q):
                schedule, values = winner, chosen_values
            archive.details["spbs_wall_seconds"] = time.monotonic()-started
            archive.publish("spbs_level_finished")
    except ValueError as exc:
        if "Cannot lift the starting events" not in str(exc) or _remaining(end) > .1:
            raise
        archive.details["spbs_preparation_status"] = "timelimit_during_lift"
    finally:
        m.freeProb()
        archive.details["spbs_wall_seconds"] = time.monotonic()-started
        archive.details["spbs_completed"] = True
        archive.publish("spbs_finished")


def _native(archive, deadline):
    stage, cfg, spec = archive.stage, archive.cfg, archive.spec
    schedule, assignment, _ = archive.best
    if stage == "A":
        archive.cap = archive.shortest
    if stage in ("A", "B3"):
        # Every productive cycle contains a product. The shortest product route
        # brackets the production window with either terminal unload order.
        # Count all possible splits, supports, intermediate and terminal cleanings.
        bound = capacity(cfg, archive.cap + CAP_TOL)
        cfg = replace(cfg, max_pairs=bound["pairs"], max_cycles=bound["cycles"])
        archive.details["capacity"] = bound
    elif assignment is not None:
        cfg = Config(**schedule["config"])
    else:
        cfg = _compact(cfg, schedule)
    x = _model(cfg, spec)
    m = x.model
    try:
        schedule, values = _start(x, schedule, assignment, deadline)
        m.addCons(x.cmax <= archive.cap + CAP_TOL, name="verified_protected_return_cap")
        if stage in ("B1", "B2"):
            for v in m.getVars(transformed=False):
                if v.vtype() == "CONTINUOUS" or v.name.startswith("sync_"):
                    continue
                if stage == "B1" or v.name.startswith(("jp_", "pj_", "jc_used_", "jc_kind_",
                                                      "jc_occ_", "front_")):
                    _fix_binary(m, v, values[v.name])
        objective = x.cmax if stage == "A" else x.minimize_process_score()
        m.addCons(objective >= archive.global_lower, name="registered_global_lower_bound")
        if stage != "A":
            values.update(process_auxiliaries(x, schedule, verify_events(schedule)[1]))
        archive.details.update(candidate_pairs=x.P, candidate_cycles=x.Q,
                               native_dimensions=x.original_dimensions)
        _warm(x, schedule, values, archive)
        if archive.record("checking")["certified_global"]:
            return
        agent = None
        if stage == "A":
            from component import POLICIES, policy_on_cpu
            agent, archive.details["policy"] = policy_on_cpu(m, "proposed", POLICIES["full"],
                                                              int(spec.get("seed", 1)), 1)
        observer = _install_observer(x, archive, track_dual=True)
        _optimize(x, observer, deadline)
        archive.status = str(m.getStatus())
        if archive.status in ("infeasible", "unbounded", "inforunbd"):
            raise RuntimeError("Native status contradicts the verified, bounded feasible start")
        dual = m.getDualbound()
        if math.isfinite(dual) and not m.isInfinity(abs(dual)):
            archive.details["native_dual"] = dual
            archive.local_lower = max(archive.local_lower, dual)
            if stage in ("A", "B3"):
                archive.global_lower = max(archive.global_lower, dual)
        archive.details.update(native_primal=m.getPrimalbound(), nodes=m.getNTotalNodes(),
                               solver_seconds=m.getSolvingTime(),
                               policy_calls=agent.get_telemetry()["callback_calls"] if agent else 0)
        if stage != "A" and m.getBestSol() is not None:
            # The survivor for the fixed-cap secondary objective can have a
            # longer primary time than the lexicographic archive.
            native = m.getBestSol()
            if m.checkSol(native, original=True, completely=True, printreason=False):
                try:
                    selected = x.result(solution=native)
                    replay, observed = verify_events(selected)
                except (ValueError, KeyError, StopIteration, IndexError) as exc:
                    archive.details["protected_native_replay_error"] = str(exc)
                else:
                    if observed["cmax"] <= archive.cap + EPS:
                        archive.details["protected_domain_native_incumbent"] = dict(
                            metrics=observed, replay_checks=replay["checks"])
    finally:
        m.freeProb()


def solve_stage(stage, schedule, assignment, spec, deadline, checkpoint=None):
    """Return (record, physical schedule, sparse assignment). Deadline is monotonic."""
    if stage not in SCOPES:
        raise ValueError(stage)
    archive = Archive(stage, schedule, assignment, spec, checkpoint)
    archive.publish("validated_input")
    try:
        if (stage == "A" and _remaining(deadline) and spec.get("spbs_seconds", 60.) > 0
                and not archive.record("checking")["certified_global"]):
            _spbs(archive, deadline)
        if _remaining(deadline) and not archive.record("checking")["certified_global"]:
            _native(archive, deadline)
    except MemoryError:
        archive.status = "memlimit"
    except ValueError as exc:
        if "Cannot lift the starting events" not in str(exc) or _remaining(deadline) > 0.1:
            raise
        archive.status = "timelimit_during_lift"
    if archive.record("checking")["certified_global"]:
        reason = "global_bound_met"
    elif archive.status == "not_started":
        reason = "timelimit"
    else:
        reason = archive.status
    return archive.publish(reason)

"""Apply the frozen paired Table 5 protocol to residence-based targets."""
from pathlib import Path
import importlib.util
import json
import re
import sys
import time

from jobs import HERE, MATCHED, folder, read, sha, write
from score import metrics
from solver import objective_terms

sys.path.insert(0, str(HERE.parent/"table45_20261124"))
import matched_ablation as original


class PhysicalObjective:
    @staticmethod
    def product_metrics(data):
        return metrics(data)


class Method:
    product = PhysicalObjective

    @staticmethod
    def save(path,data):
        for attempt in range(12):
            try:
                return original.old.solve.save(path,data)
            except PermissionError:
                if attempt==11:
                    raise
                time.sleep(.03*(attempt+1))

    def __getattr__(self, name):
        return getattr(original.old.solve, name)


def reference_timing(directory):
    timing = read(directory/"timing.json")
    b = read(directory/"B/result.json")
    assert sha(directory/"B/result.json")==timing["new_B_sha256"]
    assert b["eligible"] and b["replay"]["valid"] and b["target_gap"]==.01
    assert all(sha(directory/"B"/name)==digest for name,digest in b["files"].items())
    return timing


class ResidenceTrial(original.Trial):
    def optimize(self,x,stage):
        if stage=="A":
            trial=self
            from pyscipopt import SCIP_RESULT
            from pyscipopt.scip import Cutsel
            class TraceCut(Cutsel):
                def cutselselect(self,cuts,forcedcuts,root,maxnselectedcuts):
                    at=trial.elapsed()
                    if at<=trial.limit and not trial.s["hit"]:
                        with (trial.dest/"A_cut_times.jsonl").open("a",encoding="utf8") as f:
                            f.write(json.dumps([at,trial.s["calls"]+1])+"\n")
                    return dict(result=SCIP_RESULT.DIDNOTFIND)
            x.model.includeCutsel(TraceCut(),"archive_cut_clock","observe and delegate",2000001)
            self.trace_keys=set()
            other="quota_objective_20261125" if HERE.name.startswith("residence") else "residence_objective_20261125"
            spec=importlib.util.spec_from_file_location("paired_other_score",HERE.parent/other/"score.py")
            self.other_score=importlib.util.module_from_spec(spec)
            spec.loader.exec_module(self.other_score)
        super().optimize(x,stage)

    def observe(self,x,sol,at):
        if at>self.limit or self.s["hit"]:
            return
        data=x.result(solution=sol)
        f=metrics(data)
        a,b=f["cmax"],f["secondary"]
        witness=None
        if self.s["stage"]=="A":
            other=self.other_score.metrics(data)["secondary"]
            coordinate=tuple(round(t,7) for t in [a,b,other])
            if coordinate not in self.trace_keys:
                witness=self.witness(x,sol,at,f)
                record=dict(witness,other_b=other,score_variant=HERE.name)
                with (self.dest/"A_objectives.jsonl").open("a",encoding="utf8") as file:
                    file.write(json.dumps(record)+"\n")
                self.trace_keys.add(coordinate)
        best=self.s["best"]
        hit=self.meets(a,b)
        ahead=a<best["a"]-original.TOL or (abs(a-best["a"])<=original.TOL and b<best["b"]-original.TOL)
        if ahead or hit:
            self.s["best"]=witness or self.witness(x,sol,at,f)
            self.s["hit"]=hit
            self.persist()

    def phase_b(self):
        self.start()
        checked = self.replay(self.s["handoff"])
        values = checked[1]["nonzero"]
        score = metrics(checked[0])
        method = original.solve
        x = method.Integrated(self.cfg)
        m = x.model
        logs = self.dest/f"B_attempt{self.s['attempt']}"
        logs.mkdir(exist_ok=True)
        method.cell.scip_settings(m,dict(n=4,seed=self.seed,seconds=None,gap=.01),logs)
        m.setRealParam("numerics/feastol",1e-8)
        for variable in m.getVars(transformed=False):
            if variable.vtype()!="CONTINUOUS" and not variable.name.startswith("sync_"):
                assignment=round(values.get(variable.name,0))
                m.chgVarLb(variable,assignment)
                m.chgVarUb(variable,assignment)
        m.addCons(x.cmax<=score["cmax"]+1e-6)
        objective, extras = objective_terms(x,values,True)
        m.setObjective(objective,"minimize")
        m.addSol(method.cell.attach(x,values|extras))
        if self.s["best"].get("from_stage")=="B":
            restored = self.replay(self.s["best"])[1]["nonzero"]
            archived=method.cell.values(Path(self.s["best"]["path"]))
            restored.update({name:archived.get(name,0) for name in extras})
            m.addSol(method.cell.attach(x,restored))
        self.optimize(x,"B")
        status=str(m.getStatus())
        self.freeze()
        m.freeProb()
        if not self.s["hit"] and status not in ("optimal","timelimit","userinterrupt","unknown"):
            raise RuntimeError(f"Unexpected Table 5 secondary stop {status}")
        self.s["exhausted"]=status=="optimal" and not self.s["hit"]
        if self.s["exhausted"]:
            self.s["search_end_s"]=self.s["charged_s"]
        self.persist()


def adopt_other_A(trial,seed,arm,dest):
    """Use a fully accounted real primary trace, then consume any residual wall budget."""
    other="quota_objective_20261125" if HERE.name.startswith("residence") else "residence_objective_20261125"
    source=dest.parents[2]/other/"runs"/dest.name
    result=source/"result.json"
    if not result.exists():
        return False
    r=read(result)
    state=read(source/"progress.json")
    if any(state["key"][k]!=trial.key[k] for k in ("seed","arm","start","tolerance")):
        return False
    if state["attempt"]!=1 or (source/"A_reuse.json").exists():
        return False
    handoff=state["handoff"]
    primary_end=handoff["at"] if handoff else r["observed_s"]
    cutoff=min(primary_end,trial.limit)
    trace=source/"A_objectives.jsonl"
    proof={}
    hit=False
    if trace.exists() and (source/"A_cut_times.jsonl").exists():
        initial=dict(trial.s["best"])
        rows=[dict(j,b=j["other_b"]) for line in trace.read_text(encoding="utf8").splitlines()
              if (j:=json.loads(line))["at"]<=cutoff]
        rows.append(initial)
        hits=[w for w in rows if trial.meets(w["a"],w["b"])]
        if hits:
            best=min(hits,key=lambda w:w["at"])
            cutoff=best["at"]
            hit=True
        else:
            best=initial
            for w in sorted(rows,key=lambda w:w["at"]):
                if w["a"]<best["a"]-original.TOL or (abs(w["a"]-best["a"])<=original.TOL and w["b"]<best["b"]-original.TOL):
                    best=w
        ordered=[json.loads(z) for z in (source/"A_cut_times.jsonl").read_text(encoding="utf8").splitlines()]
        assert not ordered or ordered[-1][1]==state["calls"]
        assert all(k==i for i,(_,k) in enumerate(ordered,1))
        assert all(a[0]<=b[0] for a,b in zip(ordered,ordered[1:]))
        calls=max((k for at,k in ordered if at<=cutoff),default=0)
        proof=dict(trace_sha256=sha(trace),cut_times_sha256=sha(source/"A_cut_times.jsonl"))
    else:
        if (state["stage"]!="A" or r["reason"]!="time_budget" or trial.limit<primary_end
                or r["f_A"]<=trial.ref["f_A"]+original.TOL):
            return False
        log=source/"A_attempt1/solver.log"
        count=int(re.findall(r"Primal Bound\s*:[^\n]*\((\d+) solutions?\)",
                log.read_text(encoding="utf8",errors="replace"))[-1])
        saved=sorted(source.glob("witness*.json.gz"))
        if count!=len(saved)+1:
            return False
        values=[original.solve.cell.values(path) for path in saved]
        if any(v==other for i,v in enumerate(values) for other in values[:i]):
            return False
        if count>1 and (state["best"]["a"]>=trial.s["best"]["a"]-original.TOL or
                sum(abs(v["Cmax"]-state["best"]["a"])<=original.TOL for v in values)!=1):
            return False
        best=dict(state["best"])
        calls=state["calls"]
        proof=dict(A_native_accepted_solutions=count,native_log_sha256=sha(log))
    vals=original.solve.cell.values(Path(best["path"]))
    checked=original.solve.cell.lift(trial.cfg,vals,best["cycles"],rebuild=True)
    assert checked and checked[3]["valid"] and sha(Path(best["path"]))==best["digest"]
    f=metrics(checked[0])
    assert abs(f["cmax"]-best["a"])<original.TOL and hit==trial.meets(f["cmax"],f["secondary"])
    trial.offset=cutoff
    trial.s.update(best=dict(best,a=f["cmax"],b=f["secondary"]),calls=calls,stage="A",hit=hit)
    if cutoff>=primary_end:
        trial.s["lower"]=max(trial.s["lower"],state["lower"])
        if handoff and not hit:
            hp=Path(handoff["path"])
            assert sha(hp)==handoff["digest"]
            checked=original.solve.cell.lift(trial.cfg,original.solve.cell.values(hp),handoff["cycles"],rebuild=True)
            assert checked and checked[3]["valid"]
            hscore=metrics(checked[0])
            assert abs(hscore["cmax"]-handoff["a"])<original.TOL
            trial.s.update(handoff=dict(handoff,b=hscore["secondary"]),stage="B")
    trial.persist()
    write(dest/"A_reuse.json",dict(source=str(source),source_sha256=sha(result),reference_s=trial.limit,
          actual_source_s=primary_end,restored_s=cutoff,residual_s=max(0.,trial.limit-cutoff),first_hit_reused=hit,
          restored_calls=calls,new_score=f,scope="same method and seed, fully supported native primary prefix",**proof))
    return True


def compare(seed, arm, dest):
    original.solve=Method()
    original.load_reference=reference_timing
    trial=ResidenceTrial(seed,arm,dest,folder(f"ref5_{seed}"))
    if trial.s["stage"]=="A" and trial.s["attempt"]==1:
        adopt_other_A(trial,seed,arm,dest)
    if seed==3 and arm in ("no_spbs","no_rerank","hem") and trial.s["stage"]=="A" and trial.s["attempt"]==1:
        prior=MATCHED/"runs"/f"s{seed}_{arm}"
        state=read(prior/"progress.json")
        hand=state["handoff"]
        source=Path(hand["path"])
        assert hand["from_stage"]=="A" and sha(source)==hand["digest"] and hand["at"]<trial.limit
        first=sorted(w for w in prior.glob("witness*.json.gz") if w.name<source.name)
        # The native solver's entire accepted A pool is accounted for by the
        # initial feasible point and these distinct improve/tie snapshots.
        count=int(re.findall(r"Primal Bound\s*:[^\n]*\((\d+) solutions?\)",
            (prior/"A_attempt1/solver.log").read_text(encoding="utf8",errors="replace"))[-1])
        assert count==len(first)+1 and original.solve.cell.values(first[-1])==original.solve.cell.values(source)
        physical=[original.solve.cell.values(f) for f in first]
        assert all(v!=other for index,v in enumerate(physical) for other in physical[:index])
        # Verify there is exactly one A witness attaining the final primary optimum.
        assert all(v["Cmax"]>hand["a"]+original.TOL for v in physical[:-1])
        assert trial.s["best"]["a"]>hand["a"]+original.TOL and hand["a"]>trial.ref["f_A"]+original.TOL
        assert state["key"]["start"]==trial.key["start"] and state["key"]["seed"]==seed
        full=original.solve.cell.lift(trial.cfg,original.solve.cell.values(source),hand["cycles"],rebuild=True)
        assert full and full[3]["valid"]
        f=metrics(full[0])
        assert abs(f["cmax"]-hand["a"])<original.TOL
        new_hand=dict(hand,b=f["secondary"])
        trial.offset=hand["at"]
        trial.s.update(handoff=new_hand,best=new_hand,stage="B",calls=state["calls"])
        trial.persist()
        write(dest/"A_reuse.json",dict(source=str(prior),number_of_native_A_solutions=count,
              handoff_file=hand["digest"],A_log_sha256=sha(prior/"A_attempt1/solver.log"),
              restored_seconds=trial.offset,restored_calls=state["calls"],source_progress_sha256=sha(prior/"progress.json"),
              initial=trial.initial["assignment_sha256"],all_preceding_native_solutions_had_larger_makespan=True))
        if HERE.name=="quota_objective_20261125":
            import_equivalent_B(trial,dest,seed,arm)
    trial.run()
    result=read(dest/"result.json")
    score=metrics(read(dest/"endpoint/schedule.json"))
    assert abs(score["secondary"]-result["f_B"]) < original.TOL
    assert read(dest/"endpoint/primary.json")["replay"]["valid"]
    return result


def import_equivalent_B(trial,dest,seed,arm):
    previous=dest.parents[2]/"residence_objective_20261125"/"runs"/dest.name
    state=read(previous/"progress.json")
    assert state["stage"]=="B" and state.get("exhausted") and not state["hit"]
    log=previous/f"B_attempt{state['attempt']}/solver.log"
    text=log.read_text(encoding="utf8",errors="replace")
    assert "optimal solution found" in text and re.search(r"Primal Bound\s*:[^\n]*\(1 solutions?\)",text)
    hand=trial.s["handoff"]
    assert hand["digest"]==state["handoff"]["digest"] and trial.s["calls"]==state["calls"]
    checked=trial.replay(hand)
    data=checked[0]
    recipe_of={group["id"]:group["mode"] for group in data["config"]["pjobs"]}
    recipe_pairs={}
    for w in data["jobs"]:
        if w["product"]:
            recipe_pairs.setdefault(recipe_of[w["pjob"]],set()).add(w["pair"])
    assert all(len(s)==1 for s in recipe_pairs.values())
    f=metrics(data)
    assert f["residence_range"]<original.TOL and abs(f["secondary"]-hand["b"])<original.TOL
    assert abs(state["best"]["a"]-hand["a"])<original.TOL
    # Identical PW pairs have identical load/unload times under all retimings.
    # The two fixed-structure objectives differ by the constant quota-minus-deficit.
    shift=f["quota_unused"]-f["clean_deficit"]
    assert abs(state["best"]["b"]+shift-hand["b"])<original.TOL
    assert not trial.meets(hand["a"],hand["b"]) and state["search_end_s"]<=trial.limit
    trial.offset=min(trial.limit,state["charged_s"])
    trial.s.update(stage="B",exhausted=True,search_end_s=state["search_end_s"])
    trial.persist()
    write(dest/"B_reuse.json",dict(source=str(previous),source_A_sha256=sha(previous/"A_reuse.json"),
          solver_log_sha256=sha(log),fixed_recipe_pairs={k:list(v) for k,v in recipe_pairs.items()},
          objective_offset_seconds=shift,number_of_native_B_solutions=1,matched_A_calls=state["calls"],
          search_end_s=state["search_end_s"],previous_observation_reused_until=trial.offset,
          requested_observation_s=trial.limit,proof="Zero within-recipe spread on every retiming of the fixed PW pairs; both cleaning counts are fixed. One native solution and optimal termination."))

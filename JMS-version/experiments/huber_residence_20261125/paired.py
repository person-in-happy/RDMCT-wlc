from shared_source import load_shared
load_shared(globals())

from jobs import EPS, JMS, RES
from reuse_fixed import PREV, one_pair
from pathlib import Path
import shutil


def direct(seed,arm,dest):
    previous=PREV/"runs"/dest.name
    if not (previous/"complete.json").is_file():
        return None
    prev=read(previous/"result.json")
    assert prev==read(previous/"complete.json")["report"]
    assert all(sha(previous/"endpoint"/k)==prev[v] for k,v in (("schedule.json","schedule_sha256"),("assignment.json.gz","assignment_sha256")))
    state=read(previous/"progress.json")
    if prev["reason"]!="time_budget" or prev["f_A"]<=prev["reference_f_A"]+EPS:
        return None
    ref=read(folder(f"ref5_{seed}")/"timing.json")
    assert abs(prev["reference_s"]-ref["total_s"])<1e-6 and abs(prev["reference_f_A"]-ref["f_A"])<EPS
    schedule=read(previous/"endpoint/schedule.json")
    score=metrics(schedule)
    replacement=None
    replacement_at=None
    hproof=dict(source=str(previous.relative_to(JMS)),source_sha256=sha(previous/"result.json"),
                unchanged_time_budget_s=prev["reference_s"],unchanged_rounds=prev["calls"],
                target_unreachable_on_primary=prev["f_A"])
    if state["stage"]=="B":
        assert (previous/"A_reuse.json").exists() and one_pair(schedule)
        assert state["handoff"]["a"]>ref["f_A"]+EPS
        assert abs(score["secondary"]-prev["f_B"])<EPS
        handoff=prev["f_B_handoff"]
        hproof.update(reason="Unique primary handoff verified by full native solution archive. Every fixed secondary retiming has D=0.",
                      orig_A_proof=sha(previous/"A_reuse.json"))
    elif score["residence_range"]>=1.-1e-8:
        assert abs(score["secondary"]-(prev["f_B"]-.5))<EPS
        handoff=None
        hproof["reason"]="Old lexicographic winner achieves the maximum score reduction of 0.5; no competing same-makespan solution can improve upon it."
    else:
        log=previous/"A_attempt1/solver.log"
        if log.is_file():
            count=int(re.findall(r"Primal Bound\s*:[^\n]*\((\d+) solutions?\)",log.read_text(encoding="utf8",errors="replace"))[-1])
            stored=sorted(previous.glob("witness*.json.gz"))
            if count!=1+len(stored):
                return None
            original.solve=Method()
            values=[original.solve.cell.values(f) for f in stored]
            if any(v==other for i,v in enumerate(values) for other in values[:i]):
                return None
            if count>1:
                initial=read(original.solve.source(seed,arm)[0]/"schedule.json")
                if (sum(abs(v["Cmax"]-prev["f_A"])<EPS for v in values)!=1 or
                        initial["config"]!=schedule["config"] or metrics(initial)["cmax"]<=prev["f_A"]+EPS):
                    return None
            hproof.update(reason="Every accepted primary solution is accounted for; the minimum makespan has one winning witness.",
                          number_of_native_A_solutions=count,primary_log_sha256=sha(log))
        else:
            earlier=read(previous/"A_reuse.json")
            peer=Path(earlier["source"])
            native=peer/"A_attempt1/solver.log"
            count=int(re.findall(r"Primal Bound\s*:[^\n]*\((\d+) solutions?\)",native.read_text(encoding="utf8",errors="replace"))[-1])
            reason="Only the initial solution was accepted in the entire native shared A run."
            if count>1:
                trace=peer/"A_objectives.jsonl"
                all_rows=[json.loads(line) for line in trace.read_text().splitlines()]
                rows=[w for w in all_rows if w["at"]<=prev["reference_s"] and abs(w["a"]-prev["f_A"])<EPS]
                if not rows:
                    return None
                original.solve=Method()
                cfg=original.solve.Config(**schedule["config"])
                options=[(score,None,None)]
                for w in rows:
                    file=Path(w["path"])
                    assert sha(file)==w["digest"]
                    chk=original.solve.cell.lift(cfg,original.solve.cell.values(file),w["cycles"],rebuild=True)
                    assert chk and chk[3]["valid"]
                    actual=metrics(chk[0])
                    assert abs(actual["cmax"]-prev["f_A"])<EPS
                    options.append((actual,chk,w["at"]))
                score,replacement,replacement_at=min(options,key=lambda z:z[0]["secondary"])
                # If multiple native schedules collapsed onto one recorded pair of
                # scores, their old score still bounds their new score from below.
                if count!=len(all_rows) and score["secondary"]>min(w["other_b"] for w in rows)-.5+EPS:
                    return None
                reason="The complete native shared A pool was rescored, or its strongest possible Huber correction is attained."
                hproof["scores_sha256"]=sha(trace)
            hproof.update(reason=reason,
                          number_of_native_A_solutions=count,primary_log_sha256=sha(native),prefix_proof=sha(previous/"A_reuse.json"))
        handoff=None
    if replacement is None:
        shutil.copytree(previous/"endpoint",dest/"endpoint",dirs_exist_ok=True)
    else:
        original.solve.store_primary(dest/"endpoint",replacement,dict(reason="time_budget"))
    write(dest/"endpoint/huber_metrics.json",score)
    report=dict(prev,f_A=score["cmax"],f_B=score["secondary"],f_B_handoff=handoff,
                key=dict(prev["key"],reference=sha(folder(f"ref5_{seed}")/"timing.json")))
    report.update(reference_f_A=ref["f_A"],reference_f_B=ref["f_B"])
    if replacement is not None:
        report.update(witness_s=replacement_at,schedule_sha256=sha(dest/"endpoint/schedule.json"),
                      assignment_sha256=sha(dest/"endpoint/assignment.json.gz"))
    write(dest/"A_reuse.json",dict(hproof,restored_s=prev["observed_s"]))
    write(dest/"result.json",report)
    return report


def compare(seed,arm,dest):
    if archive:=direct(seed,arm,dest):
        return archive
    original.solve=Method()
    original.load_reference=reference_timing
    trial=ResidenceTrial(seed,arm,dest,folder(f"ref5_{seed}"))
    trial.run()
    return read(dest/"result.json")

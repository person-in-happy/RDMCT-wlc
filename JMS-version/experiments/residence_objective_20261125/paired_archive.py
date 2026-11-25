"""Extract Table 5 results that the original time-stamped A traces already imply."""
import re
from jobs import MATCHED, METHODS, OUT, folder, read, sha, write
from score import metrics


def audit():
    records=[]
    for seed in (1,2,3):
        ref=read(folder(f"ref5_{seed}")/"timing.json")
        for method in METHODS:
            d=MATCHED/f"runs/s{seed}_{method}"
            record=read(d/"result.json")
            state=read(d/"progress.json")
            log=d/"A_attempt1/solver.log"
            text=log.read_text(encoding="utf8",errors="replace")
            count=int(re.findall(r"Primal Bound\s*:[^\n]*\((\d+) solutions?\)",text)[-1])
            assert sha(d/"endpoint/schedule.json")==record["schedule_sha256"]
            assert sha(d/"endpoint/assignment.json.gz")==record["assignment_sha256"]
            assert read(d/"endpoint/primary.json")["replay"]["valid"]
            score=metrics(read(d/"endpoint/schedule.json"))
            if state["stage"]!="A":
                continue
            assert state["best"]["at"]<=ref["total_s"]<=record["reference_s"]
            assert abs(state["best"]["a"]-score["cmax"])<0.0002 and score["cmax"]>ref["f_A"]+.0002
            rec=dict(seed=seed,method=method,new_reference_s=ref["total_s"],old_coverage_s=record["reference_s"],
                     best_witness_s=state["best"]["at"],minimum_observed_Cmax=score["cmax"],
                     target_reached=False,frozen_witness_new_score=score["secondary"],native_solutions=count,
                     exact_new_tie_score=score["secondary"] if count==1 else None,
                     cutoff_count="native per-cut count at the new observation point is measured in the new run",
                     schedule_sha256=record["schedule_sha256"],log_sha256=sha(log),
                     old_result_sha256=sha(d/"result.json"),new_reference_sha256=sha(folder(f"ref5_{seed}")/"timing.json"))
            records.append(rec)
    assert len(records)==9 and sum(r["native_solutions"]==1 for r in records)==6
    write(OUT/"reuse/paired_A_trace_evidence.json",records)


if __name__=="__main__":
    audit()

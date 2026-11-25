"""Publish the final OR-Tools bound even if the intermediate bound callback did not fire at finish."""
import re
import time
from pathlib import Path
from common16 import HERE,JMS,OUT,load,save,sha

def main():
    root=OUT/"4x1";folder=root/"warm_dual/830"
    info=load(folder/"result.json")
    log=folder/"solver.log"
    summary=log.read_text(encoding="utf8").rsplit("CpSolverResponse summary:",1)[-1]
    status=re.search(r"^status: (\w+)$",summary,re.M).group(1)
    primal=float(re.search(r"^objective: (\S+)$",summary,re.M).group(1))
    dual=float(re.search(r"^best_bound: (\S+)$",summary,re.M).group(1))
    assert status==info["status"]=="OPTIMAL" and dual==primal==info["upper"]
    assert info["identity"]["strong"]==sha(HERE/"strong4.py") and info["identity"]["code"]==sha(HERE/"warm_bound4.py")
    assert info["identity"]["input"]==sha(root/"search/active_order_validation/schedule_830.json")
    assert load(folder/"checked_hint.json")["input"]==info["identity"]["input"]
    exact=folder/"global_bound.json"
    save(exact,dict(lower=dual,upper_relaxation=primal,scope="global product-return makespan for the 16-wafer pure 4x1 model",
        method="24 chronological occupancy and batch-count patterns exhaust cap 830, two-sided chamber handoffs and all labelled product routes; omit dummy loading and cleaning operations. Integral difference constraints/cumulative endpoint orders remain satisfied after flooring native event times. Native schedule 830 fixes no decision during search; it seeds the model and the cutoff.",
        relaxation_inputs=info["identity"],patterns=info["patterns"],status=status,solver_seconds=info["used"],
        source_log=log.relative_to(JMS).as_posix(),source_log_sha256=sha(log),
        native_verified_start_sha256=sha(root/"search/active_order_validation/schedule_830.json"),
        optimum_projected_candidate_sha256=sha(folder/f"candidate_{int(primal)}.json"),
        lower_callback_before_final=info["lower"],projection_code_sha256=sha(HERE/"projection16.py"),
        chronological_patterns_code_sha256=sha(HERE.parent/"table3_grid16_20261125/ordered_projection.py"),
        capacity_code_sha256=sha(HERE.parent/"table3_grid16_20261125/batch_lower.py")))
    event=root/"external_bounds"/f"optimum_{int(primal)}.json"
    if not event.exists():
        save(event,dict(lower=dual,received=time.time(),proof=exact.relative_to(JMS).as_posix(),sha256=sha(exact)))
    else:assert load(event)["sha256"]==sha(exact)
    print("Published the original final solver lower bound:",dual,flush=True)

if __name__=="__main__":main()

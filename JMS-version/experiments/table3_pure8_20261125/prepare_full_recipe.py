"""Freeze the pure 4x1 candidate stream and the independent lower-bound certificate."""
import time
from pathlib import Path
from run import OUT,JMS,load,sha,atomic

out=OUT/"certified/4x1"
protocol=out/"protocol.json"
if not protocol.exists():
    folder=OUT/"projection/4x1/575"
    proof=folder/"proof.json"
    second=JMS/"results/table3_grid8_20261125/pure4_proof/lower"
    extra=out/"independent_projection/structural_566.json"
    assert load(proof)["status"]==load(second/"result.json")["status"]=="OPTIMAL"
    lower=round(load(proof)["lower"])
    assert load(second/"result.json")["lower"]==lower
    atomic(extra,load(second/"checkpoint.json")["values"])
    candidates=[dict(source=p.relative_to(JMS).as_posix(),sha256=sha(p),cap=int(p.stem.split("_")[1]))
                for p in sorted(folder.glob("projected_*.json"),key=lambda f:-int(f.stem.split("_")[1]))]
    candidates.append(dict(source=extra.relative_to(JMS).as_posix(),sha256=sha(extra),cap=lower))
    atomic(protocol,dict(lower=lower,lower_source=proof.relative_to(JMS).as_posix(),lower_sha256=sha(proof),started=time.time(),
        initial_sha256=sha(OUT/"4x1/prepared/assignment.json.gz"),initial_record_sha256=sha(OUT/"4x1/prepared/primary.json"),
        corroborated_by=(second/"result.json").relative_to(JMS).as_posix(),corroborating_proof_sha256=sha(second/"result.json"),
        candidates=candidates,order="SPBS then strictly improving, chronologically discovered product-projection incumbents; second independently sourced skeleton is a fallback. Native retiming emits the first verified incumbent satisfying each threshold."))

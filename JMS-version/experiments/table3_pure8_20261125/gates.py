"""Handoff on the first validated native candidate satisfying each predeclared relative gap."""
from pathlib import Path
import os
import shutil
import time
from run import HERE,JMS,OUT,LEVELS,load,sha,atomic

GATES=Path(os.environ.get("TABLE3_PURE8_RECOVERY_ROOT",str(OUT/"certified"))).resolve()

def done(mode,a):
    d=GATES/mode/a/"A"
    if not (d/"primary.json").is_file():return False
    r=load(d/"primary.json")
    return r["gate"] and r["seed"]==1 and r["gap"]<=LEVELS[a]+1e-8 and all(
        sha(d/name)==r[k] for name,k in (("schedule.json","schedule_sha256"),("assignment.json.gz","assignment_sha256")))

def register(mode,source,lower,how):
    protocol=load(GATES/mode/"protocol.json")
    assert lower==protocol["lower"] and sha(JMS/protocol["lower_source"])==protocol["lower_sha256"]
    rec=load(source/"primary.json")
    assert rec["replay"]["valid"] and rec["rows"]>0
    for n,k in (("schedule.json","schedule_sha256"),("assignment.json.gz","assignment_sha256")):
        assert sha(source/n)==rec[k]
    schedule=load(source/"schedule.json")
    assert schedule["config"]==load(OUT/mode/"prepared/schedule.json")["config"]
    cmax=max(w["loan_end"] for w in schedule["jobs"] if w["product"])
    assert cmax>=lower-1e-6
    gap=max(0,(cmax-lower)/lower)
    now=time.time()
    for a,g in LEVELS.items():
        if done(mode,a) or gap>g+1e-9:continue
        d=GATES/mode/a/"A"
        d.mkdir(parents=True,exist_ok=True)
        for n in ("schedule.json","assignment.json.gz"):shutil.copyfile(source/n,d/n)
        atomic(d/"primary.json",dict(seed=1,target_gap=g,gap=gap,gate=True,lower=lower,upper=cmax,elapsed_s=now-protocol["started"],
            source=how,source_record=(source/"primary.json").relative_to(JMS).as_posix(),source_sha256=sha(source/"primary.json"),
            lower_source=protocol["lower_source"],lower_sha256=protocol["lower_sha256"],initial_sha256=protocol["initial_sha256"],
            rows=rec["rows"],replay=rec["replay"],schedule_sha256=rec["schedule_sha256"],assignment_sha256=rec["assignment_sha256"]))
        print(f"8 {mode}: first A handoff at {a}: {cmax:g}/{lower:g}, gap {gap:.6%}",flush=True)

"""Transport old fixed-structure bounds through the nonnegative Huber score correction."""
import shutil
from pathlib import Path

from score import metrics
from jobs import EPS, JMS, OUT, RES, folder, primary_source, read, sha, write

PREV=RES/"residence_objective_20261125"


def one_pair(schedule):
    mode={g["id"]:g["mode"] for g in schedule["config"]["pjobs"]}
    pairs={}
    for wafer in schedule["jobs"]:
        if wafer["product"]:
            pairs.setdefault(mode[wafer["pjob"]],set()).add(wafer["pair"])
    return all(len(v)==1 for v in pairs.values())


def transformed(previous,target,initial,level):
    old=read(previous/"result.json")
    assert old["replay"]["valid"] and old["original_rows"]>0 and old["replayed_rows"]>0
    assert all(sha(previous/k)==v for k,v in old["files"].items())
    sched=read(previous/"schedule.json")
    score=metrics(sched)
    const=one_pair(sched)
    if const:
        assert score["residence_range"]<EPS and initial["residence_range"]<EPS
    lower=max(0.,old["record"]["lower"]-(0 if const else .5))
    upper=score["secondary"]
    gap=max(0.,(upper-lower)/max(1e-10,min(abs(lower),abs(upper))))
    assert lower<=upper+EPS
    if gap>level/100+1e-8:
        return None
    target.mkdir(parents=True,exist_ok=True)
    for name in old["files"]:
        shutil.copy2(previous/name,target/name)
    proof=dict(source=str(previous.relative_to(JMS)),sha256=sha(previous/"result.json"),
               source_upper=old["record"]["upper"],source_lower=old["record"]["lower"],
               identically_zero_D=const,maximum_objective_reduction=0 if const else .5)
    record=dict(old["record"],status="equivalent_fixed_objective" if const else "transported_lower_bound",
                upper=upper,lower=lower,gap=gap,seconds=0.,nodes=0)
    result={k:old[k] for k in ("mode","backend","scope","seed","target_gap","parents","original_rows","replayed_rows","replay","files")}
    result.update(initial=initial,measured=score,eligible=True,weights=dict(range=1,clean=1,huber_delta=1),
                  record=record,proof=proof)
    write(target/"result.json",result)
    return result


def stage_a(n,h,seed,dest):
    previous=PREV/"runs"/dest.name
    for name in ("schedule.json","assignment.json.gz","primary.json"):
        shutil.copy2(previous/name,dest/name)
    old=read(previous/"complete.json")
    assert old["report"]["schedule_sha256"]==sha(dest/"schedule.json")
    assert old["report"]["assignment_sha256"]==sha(dest/"assignment.json.gz")
    return dict(old["report"],reused_source=str(previous.relative_to(JMS)))


def full_reference(seed,dest):
    previous=PREV/"runs"/dest.name
    old=read(previous/"timing.json")
    assert old["new_B_sha256"]==sha(previous/"B/result.json")
    from jobs import reference
    source=reference(seed)/"A"
    a=read(source/"schedule.json")
    assert one_pair(a)
    b=transformed(previous/"B",dest/"B",metrics(a),1)
    assert b and b["proof"]["identically_zero_D"]
    doc=dict(old,new_B_sha256=sha(dest/"B/result.json"),f_A=b["measured"]["cmax"],
             f_B=b["measured"]["secondary"],f_B_handoff=b["initial"]["secondary"],
             scope="same physical primary and identically zero D on all allowed fixed retimings",
             previous_reference=str((previous/"timing.json").relative_to(JMS)),previous_reference_sha256=sha(previous/"timing.json"))
    assert max(abs(doc[k]-old[k]) for k in ("f_A","f_B","f_B_handoff"))<EPS
    write(dest/"timing.json",doc)
    return doc


def four(n,h,seed,level,arm,dest):
    from solver import run
    old_dir=PREV/"runs"/dest.name
    old=read(old_dir/"complete.json")["report"]
    src=JMS/old["source"]
    initial=metrics(read(src/"schedule.json"))
    if arm=="fixed":
        actual,proof=primary_source(n,h,seed,level)
        assert sha(actual/"schedule.json")==sha(src/"schedule.json")
        b=transformed(old_dir/"B",dest/"B",initial,level)
        if not b:
            run("fixed",actual,dest/"B",seed=seed,gap=level/100)
            b=read(dest/"B/result.json")
    else:
        candidates=read(OUT/"warm_pool.json")[f"D_n{n}_H{h}_mixed_dual"]
        run("free",src,dest/"B",seed=seed,gap=level/100,warm=tuple(Path(x) for x in candidates))
        b=read(dest/"B/result.json")
    assert b["eligible"] and b["replay"]["valid"]
    return dict(old,initial=initial,measured=b["measured"],record=b["record"],result_sha256=sha(dest/"B/result.json"))

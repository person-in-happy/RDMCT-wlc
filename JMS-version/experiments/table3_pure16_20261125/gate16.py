"""Apply chronological UB/LB events and replay a native 16-wafer handoff."""
import sys
import time
from pathlib import Path
from common16 import HERE,JMS,OUT,LEVELS,save,load,sha,setup,config

def read_events(mode):
    root=OUT/mode
    inputs=load(root/"native/protocol.json")
    base=JMS/inputs["batch_proof"]
    assert sha(base)==inputs["batch_sha256"]
    stream=[(0.,"L",load(base)["lower"],base),(0.,"U",load(root/"prepared/primary.json")["cmax"],root/"prepared/schedule.json")]
    for file in (root/"search").glob("*/event_*.json"):
        event=load(file)
        p=file.with_name("schedule_"+file.stem.split("_")[1]+".json")
        assert sha(p)==event["schedule_sha256"]
        stream.append((event["timestamp"],"U",event["cmax"],p))
    for file in (root/"projection").glob("lb_*.json"):
        event=load(file)
        stream.append((event["timestamp"],"L",event["global_lower"],file))
    result=root/"projection/result.json"
    if result.exists():
        rec=load(result)
        stream.append((rec["timestamp"],"L",rec["lower"],result))
    for file in (root/"external_bounds").glob("*.json"):
        rec=load(file)
        assert sha(JMS/rec["proof"])==rec["sha256"]
        stream.append((rec["received"],"L",rec["lower"],file))
    return sorted(stream,key=lambda x:(x[0],x[1]))

def main(mode):
    cell=setup()
    from witness import sparse_witness
    from protocol import save as native_save
    cfg=config(mode)
    root=OUT/mode
    best=None;bound=0;witness=proof=None
    recorded={}
    for t,kind,score,p in read_events(mode):
        if kind=="L" and score>bound:bound,proof=score,p
        elif kind=="U" and (best is None or score<best):best,witness=score,p
        else:continue
        if best is None or not bound:continue
        assert best>=bound-1e-6
        for a,threshold in LEVELS.items():
            gap=(best-bound)/bound
            if a in recorded or gap>threshold+1e-9:continue
            recorded[a]=dict(timestamp=t,source=witness.relative_to(JMS).as_posix(),lower_source=proof.relative_to(JMS).as_posix(),
                source_sha256=sha(witness),lower_sha256=sha(proof),lower=bound,upper=best,gap=gap,threshold=threshold,seed=1)
    save(root/"gates_progress.json",dict(as_of=time.time(),upper=best,lower=bound,best_source=witness.relative_to(JMS).as_posix(),proof=proof.relative_to(JMS).as_posix(),eligible=recorded))
    for a,meta in recorded.items():
        dest=root/a/"A";record=dest/"primary.json"
        if record.exists():
            old=load(record)
            for k,v in meta.items():assert old[k]==v
            continue
        data=load(JMS/meta["source"])
        checked=cell.lift(cfg,sparse_witness(cfg,data),None,rebuild=True)
        if not checked or not checked[3]["valid"]:raise ValueError(f"Failure replaying {a} {mode}")
        sched,values,_,replay,rows=checked
        assert abs(max(w["loan_end"] for w in sched["jobs"] if w["product"])-meta["upper"])<1e-6
        native_save(dest/"schedule.json",sched);native_save(dest/"assignment.json.gz",values)
        save(record,dict(**meta,rows=rows,gate=True,schedule_sha256=sha(dest/"schedule.json"),assignment_sha256=sha(dest/"assignment.json.gz"),replay=replay))

if __name__=="__main__":main(sys.argv[1])

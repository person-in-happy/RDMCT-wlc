"""One-CPU second neighborhood; each pair's transport legs may shift independently."""
import os
import statistics
import sys
import time

from pack_quota_blocks import OUT, pack, read, save, sha
from shorten_witness import shorten

if __name__=="__main__":
    import msvcrt
    atomic="--atomic" in sys.argv
    repeat=int(sys.argv[sys.argv.index("--round")+1]) if "--round" in sys.argv else 1
    if repeat>1 and not atomic:raise ValueError("Extra rounds use the atomic neighborhood")
    output=OUT/(("atomic" if repeat==1 else f"atomic_r{repeat}") if atomic else "transport")
    output.mkdir(parents=True,exist_ok=True)
    with (output/"controller.lock").open("a+b") as lock:
        lock.seek(0);msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
        ready=OUT/"alternating/validated.json"
        while not ready.exists():time.sleep(.5)
        witnesses=read(ready)
        if atomic:
            prior=OUT/("transport" if repeat==1 else "atomic" if repeat==2 else f"atomic_r{repeat-1}")
            while not (prior/"progress.json").exists() or read(prior/"progress.json")["validated"]+len(read(prior/"progress.json")["failed"])<4:time.sleep(.5)
            for name in witnesses:
                p=prior/name/"retimed"
                if (p/"primary.json").exists():
                    witnesses[name]=dict(path=str(p),sha256=sha(p/"primary.json"),metrics=read(p/"primary.json")["metrics"])
        done=[];failed=[]
        for i,name in enumerate(sorted(witnesses)):
            planned=[12,12,20,20][i]
            estimated=statistics.median(done) if done else 17
            eta=(4-i)*estimated
            print(f"Complete {i-len(failed)}/4, failed {len(failed)}, elapsed {sum(done):.1f}s, estimated total {sum(done)+eta:.1f}s, remaining {eta:.1f}s, 1 worker",flush=True)
            start=time.monotonic()
            try:
                from pathlib import Path
                src=Path(witnesses[name]["path"])
                assert sha(src/"primary.json")==witnesses[name]["sha256"]
                out=output/name
                cp=out/"translation"
                candidate=pack(src,cp,planned,"atomic" if atomic else True)
                normalized=out/"native_input"
                normalized.mkdir(parents=True,exist_ok=True)
                for k,h in candidate["files"].items():
                    if not (normalized/k).exists():os.link(cp/k,normalized/k)
                    assert sha(normalized/k)==h
                if not (normalized/"primary.json").exists():
                    save(normalized/"primary.json",candidate|dict(assignment_sha256=candidate["files"]["assignment.json.gz"]))
                native=shorten(normalized,out/"retimed")
                print(name,witnesses[name]["metrics"]["cmax"],candidate["metrics"]["cmax"],native["metrics"]["cmax"],flush=True)
            except Exception as exc:
                import traceback
                traceback.print_exc()
                failed.append(name)
            done.append(time.monotonic()-start)
            eta=(3-i)*statistics.median(done)
            save(output/"progress.json",dict(validated=i+1-len(failed),failed=failed,total=4,elapsed_s=sum(done),
                 remaining_s=eta,estimated_total_s=sum(done)+eta,cpu_workers=1,
                 basis="median completed neighborhood and verification wall times",
                 recovery="reuse completed SHA-bound solutions; an interrupted short search restarts from the compressed witness"))

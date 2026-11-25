"""Alternate whole-chain translations and fixed-order native continuous retiming."""
from pathlib import Path
import os
import statistics
import time

from pack_quota_blocks import OUT, pack, read, save, sha
from shorten_witness import shorten

if __name__=="__main__":
    import msvcrt
    dest=OUT/"alternating"
    dest.mkdir(parents=True,exist_ok=True)
    with (dest/"controller.lock").open("a+b") as lock:
        lock.seek(0);msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
        elapsed=[];failed=[]
        names=sorted(p.name for p in OUT.glob("D_*") if (p/"primary.json").exists())
        sources={n:OUT/n for n in names}
        for iteration in range(1,4):
            improvement=False
            for n in names:
                t=time.monotonic()
                start=sources[n]
                cert=read(start/"primary.json")
                src=dest/f"r{iteration}"/n/"input"
                lp=src.parent/"native_retime"
                cp=src.parent/"translations"
                src.mkdir(parents=True,exist_ok=True)
                for k,h in cert["files"].items():
                    assert sha(start/k)==h
                    if not (src/k).exists():os.link(start/k,src/k)
                    assert sha(src/k)==h
                if not (src/"primary.json").exists():
                    save(src/"primary.json",cert|dict(lower=cert["metrics"]["secondary"],assignment_sha256=cert["files"]["assignment.json.gz"]))
                try:
                    a=shorten(src,lp)
                    b=pack(lp,cp,10)
                    sources[n]=cp
                    improvement|=b["metrics"]["cmax"]<cert["metrics"]["cmax"]-1e-6
                    print(iteration,n,cert["metrics"]["cmax"],a["metrics"]["cmax"],b["metrics"]["cmax"],flush=True)
                except Exception:
                    import traceback
                    traceback.print_exc();failed.append((n,iteration))
                elapsed.append(time.monotonic()-t)
                eta=(3*len(names)-len(elapsed))*statistics.median(elapsed)
                save(dest/"progress.json",dict(done=len(elapsed)-len(failed),failed=failed,total=3*len(names),elapsed_s=sum(elapsed),
                     estimated_remaining_s=eta,estimated_total_s=sum(elapsed)+eta,concurrency=1,
                     basis="median completed LP and translation stage; early termination if a sweep has no improvement",
                     recovery="verified independent LP and CP endpoints. Interrupted neighborhood replays from its feasible parent."))
                print(f"Verified {len(elapsed)-len(failed)}/{3*len(names)}, failed {len(failed)}, elapsed {sum(elapsed):.1f}s, estimated total {sum(elapsed)+eta:.1f}s, remaining {eta:.1f}s",flush=True)
            if not improvement:break
        save(dest/"validated.json",{n:{"path":str(p),"sha256":sha(p/"primary.json"),"metrics":read(p/"primary.json")["metrics"]} for n,p in sources.items()})

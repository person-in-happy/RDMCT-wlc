"""Try alternate product release orders on the three audited high-throughput packings."""
from pathlib import Path
import subprocess
import sys
import time
import psutil
import os
import msvcrt
from campaign import OUT,HERE,read,save
from from_schedule import export

PLAN=(("guidedinter",835,"01234567"),("guided31",838,"01243567"),("guidedinter",835,"01423567"),
      ("guided22",841,"01243567"),("guided31",838,"01423567"),("guidedinter",835,"01243567"),
      ("guided22",841,"01423567"),("guided31",838,"01234567"),("guidedinter",835,"01425367"))


def main():
    folder=OUT/"aligner_orders";folder.mkdir(exist_ok=True)
    with (folder/"controller.lock").open("a+b") as l:
        l.seek(0)
        try:msvcrt.locking(l.fileno(),msvcrt.LK_NBLCK,1)
        except OSError:return
        target=HERE/"lift_projection.py"
        active={}
        for p in psutil.process_iter(["cmdline"]):
            c=p.info["cmdline"] or []
            if len(c)>3 and os.path.normcase(c[-4])==os.path.normcase(str(target)) and c[-2].startswith("align_"):
                active[c[-2]]=p
        previous=read(folder/"status.json").get("elapsed",0) if (folder/"status.json").exists() else 0
        started=time.monotonic()
        while True:
            completed=[]
            for k,p in list(active.items()):
                if not p.is_running():
                    if not (OUT/"proposals"/k/"result.json").exists():raise RuntimeError(k)
                    del active[k]
            remaining=[]
            for shape,cmax,sequence in PLAN:
                key=f"align_{shape}_{sequence}"
                dest=OUT/"proposals"/key
                if (dest/"result.json").exists():
                    completed.append(key);continue
                used=read(dest/"checkpoint.json")["elapsed"] if (dest/"checkpoint.json").exists() else 0
                remaining.append(max(0,180-used))
                if key in active or len(active)>=3:continue
                src=OUT/"proposals"/shape/f"candidate_{cmax}.json"
                hint=folder/(key+".json")
                if not hint.exists():export(src,hint,[int(s) for s in sequence])
                with (folder/(key+".log")).open("a",encoding="utf8") as log:
                    q=subprocess.Popen([sys.executable,"-B","-u","-X","utf8",str(target),str(hint),key,"al"],stdout=log,stderr=subprocess.STDOUT)
                active[key]=psutil.Process(q.pid)
            elapsed=previous+time.monotonic()-started
            eta=sum(remaining)/3
            save(folder/"status.json",dict(completed=len(completed),expected=len(PLAN),failed=0,elapsed=elapsed,
                active={k:p.pid for k,p in active.items()},estimated_total_s=eta+elapsed,estimated_remaining_s=eta,
                basis="180s cumulative native CP allowance per packing/release order, 3 concurrent slots; may stop earlier."))
            print(f"Native release orders {len(completed)}/{len(PLAN)}; failed 0; elapsed {elapsed:.0f}s, total budget ETA {eta:.0f}s",flush=True)
            if not active:return
            time.sleep(4)

if __name__=="__main__":main()

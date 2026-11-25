"""Visible recoverable two-recipe worker queue, with separate immutable solver endpoints."""
import os
import sys
import time
import msvcrt
from pathlib import Path
import subprocess
import psutil
from common16 import HERE,OUT,LEVELS,save,load

def main(stage):
    OUT.mkdir(parents=True,exist_ok=True)
    folder=OUT/"controllers"/stage
    folder.mkdir(parents=True,exist_ok=True)
    starting=folder/"start.json"
    if not starting.exists():save(starting,dict(wall=time.time()))
    start=load(starting)["wall"]
    with (folder/"controller.lock").open("a+b") as lock:
        lock.seek(0)
        try:msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
        except OSError:return
        jobs={}
        for mode in ("4x1","2x2"):
            if stage=="prepare":
                jobs[mode]=([str(HERE/"prepare.py"),mode],OUT/mode/"prepared/primary.json")
            elif stage=="project":
                jobs[mode]=([str(HERE/"project16.py"),mode],OUT/mode/"projection/result.json")
            elif stage=="native":
                jobs[mode]=([str(HERE/"native16.py"),mode],OUT/mode/"native/result.json")
            elif stage=="B":
                for a in LEVELS:
                    for b in LEVELS:
                        jobs[f"{mode}_{a}_{b}"]=([str(HERE/"retime16.py"),mode,a,b],OUT/mode/a/b/"B/result.json")
            else:raise ValueError(stage)
        live={}
        for proc in psutil.process_iter(["cmdline"]):
            cmd=proc.info["cmdline"] or []
            for key,(suffix,target) in jobs.items():
                if cmd[-len(suffix):]==suffix:live[key]=proc
        if live:print("Adopted",list(live),flush=True)
        fail={}
        while True:
            completed={k for k,(_,p) in jobs.items() if p.exists()}
            for k,proc in list(live.items()):
                if not proc.is_running():
                    if k not in completed:fail[k]=str(folder/(k+".log"))
                    del live[k]
            slots=1 if stage in ("prepare","B") else 2
            for key,(args,target) in jobs.items():
                if len(live)>=slots:break
                if key in completed|fail.keys()|live.keys():continue
                with (folder/(key+".log")).open("a",encoding="utf8") as log:
                    p=subprocess.Popen([sys.executable,"-B","-u","-X","utf8",*args],stdout=log,stderr=subprocess.STDOUT)
                live[key]=psutil.Process(p.pid)
            elapsed=time.time()-start
            bases={"prepare":140,"project":600,"native":480,"B":90}
            eta=(len(jobs)-len(completed))*bases[stage]/slots
            live_status={}
            for key in live:
                cp=jobs[key][1].parent/"progress.json"
                if cp.exists():live_status[key]=load(cp)
            state=dict(stage=stage,completed=len(completed),expected=len(jobs),failed=fail,active={k:p.pid for k,p in live.items()},
                worker_progress=live_status,elapsed_s=elapsed,estimated_remaining_s=eta,estimated_total_s=elapsed+eta,
                basis="16-product pilot; stage allowance from projected workload and 8-wafer history. Incomplete proofs never count as certified gates.")
            save(folder/"progress.json",state)
            print(f"{stage}: {len(completed)}/{len(jobs)} complete, failed {len(fail)}, elapsed {elapsed:.0f}s, estimated total {elapsed+eta:.0f}s, ETA {eta:.0f}s",flush=True)
            if not live:break
            time.sleep(5)
        if fail:raise SystemExit(1)

if __name__=="__main__":main(sys.argv[1])


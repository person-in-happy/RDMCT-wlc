"""Dispatch one incremental timing-guided recovery stream from each available product optimum."""
from pathlib import Path
import sys
import subprocess
import time
import psutil
from common16 import HERE,JMS,OUT,load,save,sha

def run(mode):
    base=OUT/mode
    out=base/"timed"
    out.mkdir(parents=True,exist_ok=True)
    protocol=out/"protocol.json"
    if not protocol.exists():
        save(protocol,dict(declared=time.time(),method="First retrospectively selected globally optimal relaxed timing for the same case; freeze nonadjacent product-robot order, free all dummy events; raw schedule discoveries join native stream at their true timestamp; no retrospective change to previous handoffs.",
            plan=[[5,80,120],[15,30,120],[8,9,180],[4,0,150]],seed=1))
    if (out/"result.json").exists():return
    result=base/"projection/result.json"
    if not result.exists():return
    data=load(result)
    sources=sorted((base/"projection").glob("candidate_*.json"),key=lambda p:int(p.stem.split("_")[1]))
    if not sources: return
    source=sources[0]
    optimal_score=int(source.stem.split("_")[1])
    results=[]
    for index,(distance,slack,seconds) in enumerate(load(protocol)["plan"]):
        tag=f"timed_{index}_{source.stem}"
        endpoint=base/"search"/tag/"result.json"
        cmd=[sys.executable,"-B","-u","-X","utf8",str(HERE/"timed16.py"),mode,str(source),str(optimal_score+slack),str(seconds),tag,str(distance)]
        if not endpoint.exists():
            for proc in psutil.process_iter(["cmdline"]):
                a=proc.info["cmdline"] or []
                if a[-7:]==cmd[-7:]:proc.wait()
            if not endpoint.exists():
                with (out/(tag+".log")).open("a",encoding="utf8") as log:
                    job=subprocess.Popen(cmd,stdout=log,stderr=subprocess.STDOUT)
                begin=time.monotonic()
                while job.poll() is None:
                    used=time.monotonic()-begin
                    progress=dict(completed=len(results),expected=4,failed=0,job=tag,elapsed_s=used,
                        estimated_remaining_s=max(0,seconds-used)+sum(k[2] for k in load(protocol)["plan"][index+1:]),basis="Current plus queued seed-1 search budgets, one active solver.")
                    save(out/"progress.json",progress)
                    print(mode,progress,flush=True)
                    time.sleep(4)
                if job.returncode:raise RuntimeError(tag+" failed")
        results.append(dict(record=str(endpoint.relative_to(JMS)),sha256=sha(endpoint)))
        native=load(endpoint)
        if native["upper"] is not None and abs(native["upper"]-data["lower"])<1e-7:break
    save(out/"result.json",dict(completed=len(results),records=results))

if __name__=="__main__":run(sys.argv[1])

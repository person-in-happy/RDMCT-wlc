"""Interrupt and resume the actual native projection solver in an isolated result folder."""
from pathlib import Path
import shutil
import subprocess
import sys
import time
from campaign import HERE,OUT,JMS,sha,read,save

FIX=OUT/"restore_check"
HINT=JMS/"results/table3_grid16_20261125/ports/mixed_814/native_hint.json"
KEY="restore_fixture"


def run():
    import lift_projection
    lift_projection.OUT=FIX
    lift_projection.main(str(HINT),KEY,"al")


def main():
    FIX.mkdir(exist_ok=True)
    target=FIX/"proof.json"
    if target.exists():
        assert read(target)["status"]=="passed"
        return
    shutil.copyfile(OUT/"input.json",FIX/"input.json")
    folder=FIX/"proposals"/KEY
    clock=folder/"checkpoint.json"
    observations=[]
    for attempt in (1,2):
        before=read(clock)["elapsed"] if clock.exists() else 0
        with (FIX/f"attempt_{attempt}.log").open("a",encoding="utf8") as log:
            proc=subprocess.Popen([sys.executable,"-B","-u","-X","utf8",str(Path(__file__).resolve()),"--isolated-worker"],stdout=log,stderr=subprocess.STDOUT)
        limit=time.monotonic()+70
        try:
            while time.monotonic()<limit:
                if proc.poll() is not None:raise RuntimeError(f"Fixture exited {proc.returncode}")
                if clock.exists():
                    d=read(clock)
                    if d["elapsed"]>before+5:
                        observations.append(dict(pid=proc.pid,elapsed=d["elapsed"],signature=d["identity"]))
                        break
                time.sleep(.3)
            else:raise TimeoutError("Fixture did not save its cumulative budget")
        finally:
            proc.terminate();proc.wait()
    assert observations[0]["signature"]==observations[1]["signature"]
    assert observations[1]["elapsed"]>observations[0]["elapsed"]
    save(target,dict(status="passed",isolated=True,attempts=observations,grid_input_sha256=sha(OUT/"input.json"),
         shared_results_modified=False,recovery="Interrupted kernel resumed same identity with cumulative CP budget charged. Completed original-model grid cells are hash-verified independently."))
    print("Passed isolated restart with charges", [r["elapsed"] for r in observations])

if __name__=="__main__":
    if len(sys.argv)==2:run()
    else:main()

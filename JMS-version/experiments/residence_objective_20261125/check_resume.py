"""Interrupt an isolated, short Table 5 CPU trial and verify its restored clock."""
from pathlib import Path
import subprocess
import sys
import time
from jobs import OUT, folder, read, sha, write


def trial(dest):
    import paired
    paired.original.solve=paired.Method()
    ref=folder("ref5_1")
    original_load=paired.reference_timing
    def short(directory):
        timing=original_load(directory)
        return dict(timing,total_s=timing["prep_seconds"]+18.,f_A=0.)
    paired.original.load_reference=short
    t=paired.ResidenceTrial(1,"scip_default",dest,ref)
    t.run()


def check():
    dest=OUT/"qa/paired_interrupt"
    dest.mkdir(parents=True,exist_ok=True)
    if (dest/"checked.json").exists():
        print(read(dest/"checked.json"),flush=True)
        return
    cmd=[sys.executable,"-B","-u","-X","utf8",str(Path(__file__).resolve()),"trial",str(dest)]
    with (dest/"test.log").open("a",encoding="utf8") as log:
        if not (dest/"interrupt.json").exists():
            proc=subprocess.Popen(cmd,stdout=log,stderr=subprocess.STDOUT)
            deadline=time.monotonic()+80
            while not (dest/"clock.json").exists():
                if time.monotonic()>deadline or proc.poll() is not None:
                    raise RuntimeError("No clock checkpoint for isolated trial")
                time.sleep(.15)
            proc.terminate()
            proc.wait(timeout=10)
            state=read(dest/"progress.json")
            pulse=read(dest/"clock.json")
            write(dest/"interrupt.json",dict(key=state["key"],charged=max(state["charged_s"],pulse["charged_s"]),
                  attempt=state["attempt"],pid=proc.pid))
        old=read(dest/"interrupt.json")
        subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT,check=True)
    result=read(dest/"result.json")
    last=read(dest/"progress.json")
    assert result["reason"]=="time_budget" and last["attempt"]>=old["attempt"]+1
    assert old["key"]==last["key"] and last["charged_s"]>=old["charged"]
    assert read(dest/"endpoint/primary.json")["replay"]["valid"]
    assert abs(result["reference_s"]-result["observed_s"])<1e-6
    write(dest/"checked.json",dict(scope="isolated 18s single-thread paired search after prep",first_attempt=old["attempt"],
          resumed_attempt=last["attempt"],checkpoint_s=old["charged"],final_charged_s=last["charged_s"],
          reference_s=result["reference_s"],schedule_sha256=sha(dest/"endpoint/schedule.json"),
          replay_valid=True,matching_key=True))
    print(read(dest/"checked.json"),flush=True)


if __name__=="__main__":
    if sys.argv[1:2]==["trial"]:
        trial(Path(sys.argv[2]))
    else:
        check()

"""Interrupt a separate copy of the primary search and verify its published handoff survives."""
from pathlib import Path
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time

HERE=Path(__file__).resolve().parent
RESULT=HERE.parents[1]/"results/table3_mixed8_20261125"
QA=RESULT/"resume_check"

def read(path):
    return json.loads(path.read_bytes())

def main():
    if (QA/"audit.json").exists():
        print(read(QA/"audit.json"));return
    QA.mkdir(parents=True,exist_ok=True)
    assert not (QA/"primary_search.json").exists()
    shutil.copytree(RESULT/"prepared",QA/"prepared",dirs_exist_ok=True)
    state=QA/"primary_search.json"
    def wait(proc,predicate):
        start=time.monotonic()
        while time.monotonic()-start<60:
            if proc.poll() is not None:raise RuntimeError(proc.returncode)
            if state.exists():
                data=read(state)
                if predicate(data):return data
            time.sleep(.2)
        raise RuntimeError("Fixture checkpoint not observed")
    def launch():
        return subprocess.Popen([sys.executable,"-B","-u",str(Path(__file__).resolve()),"--isolated-worker"])
    first=launch()
    try:before=wait(first,lambda d:"10pct" in d["gates"] and d["elapsed_s"]>4)
    finally:first.terminate();first.wait()
    second=launch()
    try:after=wait(second,lambda d:d["attempt"]==before["attempt"]+1 and d["elapsed_s"]>before["elapsed_s"]+3)
    finally:second.terminate();second.wait()
    assert before["identity"]==after["identity"] and before["gates"]==after["gates"]
    for e in before["events"]:
        assert e in after["events"] and hashlib.sha256((QA/e["path"]/"primary.json").read_bytes()).hexdigest()==e["record_sha256"]
    audit=dict(attempts=[before["attempt"],after["attempt"]],elapsed_s=[before["elapsed_s"],after["elapsed_s"]],
        restored_gate=before["gates"]["10pct"],isolated=True,terminated_pids=[first.pid,second.pid],result="passed")
    (QA/"audit.json").write_text(json.dumps(audit,indent=2),encoding="utf8")
    print(audit,flush=True)

if __name__=="__main__":
    if len(sys.argv)>1:
        import primary
        primary.OUT=QA
        primary.main()
    else:main()

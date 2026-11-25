"""Interrupt a small separate sublevel and verify checkpoint identity and cumulative CP budget."""
import subprocess
import sys
import time
from common16 import HERE,OUT,load,save,sha

def main():
    directory=OUT/"4x1/strong/825"
    audit=OUT/"recovery"/"sublevel_825.json"
    if audit.exists():return
    args=[sys.executable,"-B","-u","-X","utf8",str(HERE/"strong4.py"),"825","18"]
    if (directory/"result.json").exists():raise ValueError("Test requires an unused short-budget sublevel.")
    print("Recovery check | 0/1 complete, estimated elapsed total 25–40 s",flush=True)
    p=subprocess.Popen(args)
    checkpoint=directory/"progress.json"
    start=time.monotonic()
    while time.monotonic()-start<45:
        if checkpoint.exists() and load(checkpoint)["used"]>5:break
        time.sleep(.15)
    before=load(checkpoint)
    assert 0<before["used"]<18 and p.poll() is None
    p.terminate();p.wait(timeout=15)
    pre_hash=sha(checkpoint)
    restored=load(checkpoint)
    assert restored["used"]>=before["used"]
    subprocess.run(args,check=True)
    final=load(directory/"result.json")
    assert final["identity"]==restored["identity"] and 18.5>=final["used"]>=restored["used"]
    save(audit,dict(interrupted_cp_seconds=restored["used"],checkpoint_sha256=pre_hash,
        total_cp_seconds=final["used"],budget=18,identity=final["identity"],replayed_lower=restored["lower"],
        final_lower=final["lower"],status=final["status"],code_sha256=sha(HERE/"strong4.py")))
    print("Resumption verified | 1/1 complete, ETA 0 s",flush=True)

if __name__=="__main__":main()

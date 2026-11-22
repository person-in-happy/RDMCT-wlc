"""Compare all four objectives on the same mixed 16-wafer input used in the ablations."""
from pathlib import Path
import sys
import time
import psutil
from controls import OUT,ROOT,SCIP,compare,execute,matched,read,sha

CASE="D_n16_H6_mixed_dual"

def register():
    src=OUT/"mixed16/s1/raw"
    s,v=src/"schedule.json",src/"assignment.json.gz"
    for seed in (2,3):
        other=OUT/"mixed16"/f"s{seed}"/"raw"
        assert (sha(s),sha(v))==(sha(other/s.name),sha(other/v.name))
    matched.CASES[CASE]=dict(n=16,backend="D",source=s.relative_to(ROOT).as_posix(),
        assignment=v.relative_to(ROOT).as_posix(),source_sha256=sha(s),assignment_sha256=sha(v),config=read(s)["config"])

if __name__=="__main__":
    register()
    if len(sys.argv)>1:
        seed,arm,path=sys.argv[1:]
        while psutil.virtual_memory().available<10*1024**3:time.sleep(4)
        compare(CASE,int(seed),arm,Path(path))
    else:
        jobs=[]
        for seed in (1,2,3):
            for arm in ("A","B","J","AB"):
                path=str(OUT/"objectives16"/f"{CASE}__s{seed}__{arm}")
                jobs.append((SCIP,__file__,[str(seed),arm,path],path))
        sys.exit(execute(jobs,2,OUT/"objectives16"))

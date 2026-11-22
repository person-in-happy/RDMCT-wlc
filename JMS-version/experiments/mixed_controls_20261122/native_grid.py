"""Check the four-wafer primary switch directly with the learned SCIP policy."""
from pathlib import Path
import sys
from scale import GRID,HERE,JMS,LEVELS,OUT,SCIP,execute,first,product_solve,read,save,sha

DEST=OUT/"native_grid4"

def worker(case,a,folder):
    src=GRID/"pure/prepared" if case=="pure" else JMS/"results/manuscript_certified_gaps_20261119_r3/runs/D_n4_mixed_H10/prep"
    primary=folder/"A"
    try:
        r=first(src,primary,4,1,"full","scip",600,LEVELS[a],True)
    except ValueError as exc:
        if "Gap stop without verified gap" not in str(exc): raise
        save(folder/"result.json",dict(case=case,a=a,gate=False,reason=str(exc),budget=600))
        return
    results={}
    for b,gap in LEVELS.items():
        e=product_solve(folder/b,primary/"schedule.json",primary/"assignment.json.gz","D",4,1,"fixed",gap=gap)
        results[b]=dict(metrics=e["measured"],record=e["record"])
    save(folder/"result.json",dict(case=case,a=a,gate=True,start=sha(src/"assignment.json.gz"),primary=r,results=results))

if __name__=="__main__":
    if len(sys.argv)>1:worker(sys.argv[1],sys.argv[2],Path(sys.argv[3]))
    else:
        jobs=[]
        for a in LEVELS:
            for case in ("pure","mixed"):
                path=str(DEST/f"{case}__{a}");jobs.append((SCIP,__file__,[case,a,path],path))
        sys.exit(execute(jobs,2,DEST))

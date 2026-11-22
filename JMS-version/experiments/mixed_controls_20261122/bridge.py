"""Use the saved two-wafer projection handoffs with the current product objective."""
from pathlib import Path
import sys

from controls import JMS,OUT,SCIP,execute,product_solve,read,save,sha

BASE=JMS/"results/manuscript_projection_20261120_r1/runs"
TARGET=OUT/"grid2"
LEVELS={"10pct":.1,"1pct":.01,"0p01pct":.0001}

def worker(case,a,folder):
    src=BASE/f"{case}__grid_A_{a}"
    e=read(src/"evidence.json")
    s,v=src/"schedule.json",src/"assignment.json.gz"
    assert e["valid"] and e["record"]["gate"] and e["record"]["gap"]<=LEVELS[a]+1e-9
    assert (sha(s),sha(v))==(e["schedule_sha256"],e["assignment_sha256"])
    rows={}
    for b,gap in LEVELS.items():
        endpoint=product_solve(folder/b,s,v,"D",2,1,"fixed",gap=gap)
        assert endpoint["eligible"] and endpoint["replay"]["valid"]
        rows[b]=dict(record=endpoint["record"],metrics=endpoint["measured"])
    save(folder/"result.json",dict(case=case,a=a,primary=e["record"],start=e["input_sha256"],results=rows))

if __name__=="__main__":
    if len(sys.argv)>1:worker(sys.argv[1],sys.argv[2],Path(sys.argv[3]))
    else:
        jobs=[]
        for c in ("D_n2_4x1_scenario1","D_n2_mixed_scenario3"):
            for a in LEVELS:
                folder=str(TARGET/f"{c}__{a}")
                jobs.append((SCIP,__file__,[c,a,folder],folder))
        sys.exit(execute(jobs,3,TARGET))

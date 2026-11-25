"""Fixed-structure Huber retiming with the stated threshold and original physical row replay."""
import sys
from common16 import HERE,JMS,OUT,LEVELS,load,sha
sys.path.insert(0,str(HERE.parent/"huber_residence_20261125"))
from solver import run
import cell

def main(mode,a,b):
    root=OUT/mode/a
    f=root/"A/primary.json"
    meta=load(f)
    assert meta["gate"] and meta["gap"]<=LEVELS[a]+1e-9
    assert sha(root/"A/assignment.json.gz")==meta["assignment_sha256"]
    destination=root/b/"B"
    result=destination/"result.json"
    set_base=cell.scip_settings
    def settings(m,task,path):
        set_base(m,task,path)
        m.setRealParam("limits/memory",11500.)
    cell.scip_settings=settings
    if not result.exists():
        run("fixed",root/"A",destination,seed=1,gap=LEVELS[b])
    data=load(result)
    assert data["eligible"] and data["replay"]["valid"] and data["record"]["gap"]<=LEVELS[b]+1e-8
    assert data["parents"][0]["assignment_sha256"]==meta["assignment_sha256"]
    assert all(sha(destination/n)==s for n,s in data["files"].items())

if __name__=="__main__":main(*sys.argv[1:])

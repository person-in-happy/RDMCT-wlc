"""Use the Table 3 initializer on the archived eight-wafer, dual-recipe input."""
from pathlib import Path
import sys
import time

HERE=Path(__file__).resolve().parent
JMS=HERE.parents[1]
OUT=JMS/"results/table3_mixed8_20261125"
sys.path.insert(0,str(HERE.parent/"mixed_controls_20261122"))
from scale import Config, prepare, read, save, sha

if __name__=="__main__":
    OUT.mkdir(parents=True,exist_ok=True)
    src=JMS/"results/table4_residence100_20261123/inputs/D_n8_H10_mixed_dual"
    protocol=read(src/"input.json")
    raw=read(src/"schedule.json")
    assert sha(src/"schedule.json")==protocol["schedule_sha256"] and protocol["config"]==raw["config"]
    assert protocol["source"]["selected"]=="alternate_pairs"
    start=time.monotonic()
    if not (OUT/"prepared/primary.json").exists():
        prepare(OUT,Config(**raw["config"]),raw,1)
    rec=read(OUT/"prepared/primary.json")
    assert rec["replay"]["valid"] and rec["assignment_sha256"]==sha(OUT/"prepared/assignment.json.gz")
    assert rec["schedule_sha256"]==sha(OUT/"prepared/schedule.json")
    save(OUT/"preparation.json",dict(source=str(src.relative_to(JMS)),source_sha256=sha(src/"input.json"),
         prepared_sha256=sha(OUT/"prepared/primary.json"),seconds=time.monotonic()-start,script_sha256=sha(Path(__file__))))
    print("Prepared one common SPBS start:",rec["metrics"]["cmax"],flush=True)

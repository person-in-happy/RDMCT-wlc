"""Decode the optimal supporting relaxation and independently check every original constraint."""
import argparse
import sys
from sweep import HERE,OUT,Config,atomic,cell,metrics,read,save,sha,validate
sys.path.insert(0,str(HERE.parent/"table3_mixed16_20261125"))
from replay_moves import reconstruct,attach_hands
sys.path.insert(0,str(HERE.parent/"pareto_rl_dmct_20261119"))
from witness import sparse_witness


def verify(folder,tag):
    path=OUT/folder/f"{tag}_hint.json"
    target=OUT/folder/f"{tag}_native";target.mkdir(exist_ok=True,parents=True)
    doc=reconstruct(read(path))
    assert attach_hands(doc)
    replay=validate(doc)
    assert replay["valid"],replay["errors"][:10]
    cfg=Config(**doc["config"])
    native=cell.lift(cfg,sparse_witness(cfg,doc),None,rebuild=True)
    assert native
    doc,a,_,replay,rows=native
    save(target/"schedule.json",doc);save(target/"assignment.json.gz",a)
    score=metrics(doc)
    atomic(target/"result.json",dict(metrics=score,rows=rows,replay=replay,projection_sha256=sha(path),
                                   files={k:sha(target/k) for k in ("schedule.json","assignment.json.gz")}))
    print(rows,score,flush=True)


if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("folder");p.add_argument("tag");a=p.parse_args();verify(a.folder,a.tag)

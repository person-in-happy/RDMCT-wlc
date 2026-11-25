"""Certify the integral 397 s endpoint under both cleaning intervals."""
from sweep import Config,HUB,OUT,atomic,cell,metrics,read,save,sha


def verify(h):
    src=HUB/f"runs/t4_1_4_{h}_1_fixed/B"
    dest=OUT/f"four_native_H{h}/short397";dest.mkdir(exist_ok=True,parents=True)
    cfg=Config(**read(src/"schedule.json")["config"])
    v=cell.values(src/"assignment.json.gz")
    vals={k:round(t) if abs(t-round(t))<1e-5 else t for k,t in v.items()}
    checked=cell.lift(cfg,vals,None,rebuild=True)
    assert checked
    doc,assignment,_,replay,rows=checked
    a=metrics(doc)
    assert a["cmax"]==397 and a["secondary"]==3.5
    save(dest/"schedule.json",doc);save(dest/"assignment.json.gz",assignment)
    atomic(dest/"result.json",dict(metrics=a,rows=rows,replay=replay,source_sha256=sha(src/"assignment.json.gz"),
                                  files={k:sha(dest/k) for k in ("schedule.json","assignment.json.gz")}))
    print(h,a,flush=True)


if __name__=="__main__":
    for h in (3,10):verify(h)

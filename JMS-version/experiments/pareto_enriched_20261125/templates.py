"""Vary the first productive recipe and the order of chamber handoffs in the 823–853 s gap."""
import msvcrt
import time
import reroute as rr
from native_caps import OUT
from support import read,write,digest

P=OUT/"search/last_855_2/p_853_80_0.json"
TEMPLATES={
 "last_refined":[(0,2),(10,1),(1,2),(2,2),(11,1),(3,2),(12,1),(4,1)],
 "full_first":[(10,1),(0,2),(1,2),(2,2),(11,1),(3,2),(12,1),(4,1)],
 "early_single":[(0,2),(10,1),(1,2),(11,1),(2,2),(3,2),(12,1),(4,1)],
 "latter_swap":[(0,2),(10,1),(1,2),(2,2),(11,1),(3,2),(4,1),(12,1)],
}
JOBS=[("last_refined",i,p) for i,p in [(834,2),(840,2),(844,2),(847,2),(849,2),(850,2),(851,2),(852,2),
                                        (854,4),(856,4),(859,2),(875,2),(905,2)]]
JOBS+= [(name,cap,2 if name!="full_first" else 0) for name in ("early_single","full_first","latter_swap") for cap in (842,856,877,910)]

if __name__=="__main__":
    lock=(OUT/"templates.lock").open("a+b")
    try:msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
    except OSError:raise SystemExit("Active worker")
    start=time.monotonic()
    for i,job in enumerate(JOBS):
        tag,cap,prefix=job
        rr.GROUPS=TEMPLATES[tag]
        groups0=[k for _,k in TEMPLATES["last_refined"] for _ in range(2)]
        groups1=[k for _,k in rr.GROUPS for _ in range(2)]
        slots={k:iter(i for i,r in enumerate(groups0) if r==k) for k in (1,2)}
        old=read(P);mapped=old.copy()
        for j,k in enumerate(groups1):
            orig=next(slots[k])
            for stage in ("origin_pick","al","ap","up","sp","ld","ul","dp","lp","origin_put","port","front"):
                mapped[f"{stage}_{j}"]=old[f"{stage}_{orig}"]
        rr.SRC=OUT/f"hint_{tag}.json"
        if rr.SRC.exists():assert read(rr.SRC)==mapped
        else:write(rr.SRC,mapped)
        wall=time.monotonic()-start;eta=(len(JOBS)-i)*(wall/i if i else 8)
        rec=dict(stage=job,completed=i,total=len(JOBS),failed=0,elapsed=wall,eta_remaining=eta,eta_total=wall+eta,
                 basis="one CP worker; eight seconds per cell until measured cells finish")
        rec.update(driver_sha256=digest(rr.HERE/"templates.py"),seed_sha256=digest(P))
        write(OUT/"templates_progress.json",rec);print(rec,flush=True);rr.run(*job,8)
    rec.update(completed=len(JOBS),elapsed=time.monotonic()-start,eta_remaining=0);rec["eta_total"]=rec["elapsed"]
    write(OUT/"templates_progress.json",rec)

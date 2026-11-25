"""Additional chamber-rerouting cells targeting the first feasible low-spread schedules."""
from reroute import run,OUT,write,time,msvcrt

if __name__=="__main__":
    jobs=[("last",i,p) for i,p in ((850,4),(860,4),(864,6),(865,6),(866,6),(867,6),(870,4),
                                      (855,2),(875,3),(880,4))]+[("split",890,4),("split",910,4),("early",920,4)]
    lock=(OUT/"extend.lock").open("a+b")
    try:msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
    except OSError:raise SystemExit("Active worker")
    clock=time.monotonic()
    for n,x in enumerate(jobs):
        used=time.monotonic()-clock;eta=(len(jobs)-n)*(used/n if n else 12)
        rec=dict(completed=n,total=len(jobs),failed=0,elapsed=used,eta_remaining=eta,eta_total=eta+used,
                 current=x,estimate="one worker, 12 s allowance per cell; measured thereafter")
        write(OUT/"extend_progress.json",rec);print(rec,flush=True);run(*x,12)
    rec.update(completed=len(jobs),elapsed=time.monotonic()-clock,eta_remaining=0);rec["eta_total"]=rec["elapsed"]
    write(OUT/"extend_progress.json",rec)

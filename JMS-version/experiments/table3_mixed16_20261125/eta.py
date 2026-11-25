"""Monitor a final fixed-structure queue using completed same-instance measurements."""
import statistics
import time
from campaign import OUT,GAPS,read,save


if __name__=="__main__":
    while True:
        status=read(OUT/"progress.json")
        results=[p for p in (OUT/"grid").glob("*/*/result.json")]
        sample=[read(p)["record"]["wall_seconds"] for p in results]
        pending=9-len(results)
        median=statistics.median(sample) if sample else None
        if pending and len(status["gates"])<3:eta=None
        else:eta=pending*(median or 35)
        report=dict(completed=len(results),expected=9,failed=len(status["failed"]),elapsed_s=status["elapsed_s"],
            estimated_remaining_s=eta,estimated_total_s=status["elapsed_s"]+eta if eta is not None else None,
            basis=f"One serial fixed-structure worker. Median wall time for {len(sample)} completed 16-wafer cells: {median} s.")
        save(OUT/"eta.json",report)
        print(f"Validated {len(results)}/9; elapsed {status['elapsed_s']:.0f}s; "+(f"estimated total {report['estimated_total_s']:.0f}s, ETA {eta:.0f}s" if eta is not None else "grid ETA awaits the primary bound"),flush=True)
        if pending==0 and status["completed"]==9:break
        time.sleep(5)

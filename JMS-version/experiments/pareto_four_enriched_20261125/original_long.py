"""Directly verify that loose deadlines in the original mixed case preserve the proved floor."""
from probe import OUT,R,sweep
import msvcrt
def run():
    sweep.OUT=OUT/"original_mixed_long";sweep.OUT.mkdir(exist_ok=True)
    caps=[450,500,650,800]
    sweep.CASES={f"H{h}":(R/f"pareto_scales_20261125/four_native_H{h}/417_pinned",caps) for h in (3,10)}
    with (sweep.OUT/"run.lock").open("a+b") as lock:
        try:msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
        except OSError:return
        for k in sweep.CASES:sweep.run(k)
if __name__=="__main__":run()

"""Continuous retiming for the split two-product head and singleton tail structure."""
from probe import OUT,sweep
import msvcrt
def run():
    sweep.OUT=OUT/"mid_continuation";sweep.OUT.mkdir(exist_ok=True)
    src=OUT/"alternate/12_4_3_d0.5"
    sweep.CASES={"split":(src,[423,424,425,425.0625,425.125,425.1875,425.25,425.3125,425.375,425.4375,425.5,426,432,490])}
    with (sweep.OUT/"run.lock").open("a+b") as lock:
        try:msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
        except OSError:return
        sweep.run("split")
if __name__=="__main__":run()

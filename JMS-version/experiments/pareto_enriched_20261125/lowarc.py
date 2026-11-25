"""Independently resolve fractional time/quality tradeoffs around a new uniform-residence witness."""
from neighbor import JOBS,neighborhood
from native_caps import OUT,fixed
import msvcrt

if __name__=="__main__":
    parent=OUT/"native/last_refined_859_2/p_856_56_0"
    assert (parent/"result.json").exists()
    # First retain the native order near its shortest schedules, then permit real robot reordering.
    caps=[845,848,850,851,852,853,853.25,853.5,853.75,854,854.25,854.5,854.75,855,855.125,855.25,
          855.375,855.5,855.625,855.75,855.875,856,856.125,856.25,856.375,856.5,856.625,857,858,860,870]
    fixed.sweep.CASES={"lowarc":(parent,caps)};fixed.sweep.OUT=OUT/"fixed"
    fixed.main("lowarc")
    JOBS["lowtrade"]=(parent,27,[854,855,856,857,858,860,865,875,895])
    with (OUT/"neighbors_lowtrade.lock").open("a+b") as lock:
        try:msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
        except OSError:raise SystemExit("Matching worker active")
        neighborhood("lowtrade",7)

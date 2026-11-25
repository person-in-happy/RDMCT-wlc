"""Expand the newly validated reassignment's sequencing neighborhood around its two tradeoffs."""
import msvcrt
from neighbor import OUT,JOBS,neighborhood

if __name__=="__main__":
    source=OUT/"native/last_875_6/p_868_88_0"
    assert (source/"result.json").exists()
    JOBS["reassigned"]=(source,43,[865,855,845,850,860,863,864,866,867,868,869,870,872,875,880,885,895,910,930,950])
    with (OUT/"neighbors_reassigned.lock").open("a+b") as lock:
        try:msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
        except OSError:raise SystemExit("Matching worker active")
        neighborhood("reassigned",9)

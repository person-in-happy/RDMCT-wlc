"""Run additional epsilon budgets against independent handoff structures."""
import argparse
import msvcrt
from sweep import CASES, MIX, OUT, run

EXTRA={
    "sixteen_37":(OUT/"cap810/p0020_native",[810,811,812,814,817,821,826,834,850,870,910,1100]),
    "sixteen_23":(OUT/"cap812/p0026_native",[812,817,826,834,850,870,910]),
    "sixteen_821":(MIX/"witnesses/proposals__projection809__candidate_821",[810,817,821,826,834,850,870,910,970,1100]),
    "sixteen_init":(MIX/"prepared",[810,850,910,970,1100,1200,1300,1450,1600,1694]),
    "sixteen_long":(OUT/"two_blocks",[810,870,920,970,1020,1060,1100,1160,1220]),
}

if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("case",choices=list(EXTRA));a=p.parse_args()
    CASES.update(EXTRA)
    dest=OUT/a.case;dest.mkdir(exist_ok=True,parents=True)
    with (dest/"worker.lock").open("a+b") as lock:
        lock.seek(0)
        try:msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
        except OSError:print("Worker already running.",flush=True)
        else:run(a.case)

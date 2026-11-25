"""Quadratic epsilon-constraint cells on original event orders, reusing the native sweep runner."""
import argparse
import msvcrt
from pathlib import Path
import sys
import time

HERE=Path(__file__).resolve().parent
EX=HERE.parent
JMS=EX.parent
R=JMS/"results"
OUT=R/HERE.name
OLD=R/"pareto_scales_20261125"
HUB=R/"huber_residence_20261125"
sys.path.insert(0,str(EX/"square_residence_20261125"))
from solver import objective_terms
from score import metrics, OBJECTIVE
sys.path.insert(0,str(EX/"pareto_scales_20261125"))
import sweep
sweep.OUT=OUT/"fixed"
sweep.CASES={
    "long8":(HUB/"witnesses_grid_middle/D_n8_H10_mixed_dual",[554,563,570,574,575.75,576,576.125,576.25,576.375,576.5,576.5625,576.625]),
    "short16":(OLD/"continuous16/endpoint810",[810,810.125,810.375,810.625,810.875,811,811.25,811.5,811.75,812,813,815,820,830]),
    "jump16":(OLD/"cap812/p0026_native",[812,812.25,812.5,813,814,815,817,821,830,855,890,950]),
}
assert sweep.objective_terms is objective_terms and sweep.metrics is metrics


def main(name,stop=None):
    assert OBJECTIVE
    dest=sweep.OUT/name
    dest.mkdir(exist_ok=True,parents=True)
    sig={str(p.relative_to(JMS)):sweep.sha(p) for p in (Path(__file__),EX/"pareto_scales_20261125/sweep.py",
          EX/"square_residence_20261125/score.py",EX/"square_residence_20261125/solver.py")}
    tag=dest/"identity.json"
    if tag.exists():assert sweep.read(tag)==sig
    else:sweep.atomic(tag,sig)
    with (dest/"worker.lock").open("a+b") as lock:
        try:msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
        except OSError:print("Matching worker already active.",flush=True);return
        sweep.run(name,stop)


if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("case",choices=[*sweep.CASES,"all"]);p.add_argument("--stop-after",type=int)
    args=p.parse_args()
    for name in sweep.CASES if args.case=="all" else [args.case]:main(name,args.stop_after)

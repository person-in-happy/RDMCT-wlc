"""Tighten three branch transitions at the 1/8-second controller scale using continuous native timing."""
from probe import OUT,R,JMS,sweep,fixed
from pathlib import Path
import msvcrt

def main():
    root=OUT/"continuation";root.mkdir(exist_ok=True,parents=True)
    source=OUT/"partitions/1_34_2_d0.25"
    cases={"low":(source,[404,405,406,407,408,408.125,408.25,408.375,408.5,408.625,408.75,409,410]),
           "middle":(OUT/"partitions/12_34_d0.5",[426,429,430,431,431.5,432,432.125,432.25,432.375,432.5,433,440,465]),
           "long":(OUT/"long/121/floor_525",[460,475,485,489,490,490.5,490.75,491,491.0625,491.125,491.1875,491.25,492,500,550,650,800])}
    sweep.CASES=cases;sweep.OUT=root
    with (root/"run.lock").open("a+b") as lock:
        try:msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
        except OSError:return
        for case in cases:sweep.run(case)

if __name__=="__main__":main()

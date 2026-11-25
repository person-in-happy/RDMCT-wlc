"""Resolve the native squared-objective subproblem at new caps inside the proven 16-wafer arc."""
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
JMS = HERE.parents[1]
sys.path.insert(0, str(HERE.parent / "pareto_square_20261125"))
import fixed

case = "sixteen_inside"
grid = [810 + k / 16 for k in (1, 3, 4, 5, 7, 8, 9, 11, 12, 13, 15)]
fixed.sweep.OUT = JMS / "results" / HERE.name
fixed.sweep.CASES = {case: (fixed.OLD / "continuous16/endpoint810", grid)}

if __name__ == "__main__":
    optional_stop = int(sys.argv[1]) if len(sys.argv) == 2 else None
    fixed.main(case, stop=optional_stop)

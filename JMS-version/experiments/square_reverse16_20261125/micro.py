"""Native quadratic epsilon-constraint solves with all discrete choices fixed to a verified route."""
import sys
from pathlib import Path
HERE=Path(__file__).resolve().parent;JMS=HERE.parents[1]
sys.path.insert(0,str(HERE.parent/'pareto_square_20261125'))
import fixed
root=JMS/'results/square_reverse16_20261125'
fixed.sweep.OUT=root/'micro'
fixed.sweep.CASES={
    'near_global':(root/'steps_narrowD8/native',[987+i/64 for i in range(9)]),
    'left':(root/'last_tight_d16/native',[981.,983.,985.,985.75]+[986+i/8 for i in range(9)])}
if __name__=='__main__':fixed.main(sys.argv[1])

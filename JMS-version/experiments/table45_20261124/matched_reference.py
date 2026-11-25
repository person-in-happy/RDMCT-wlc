"""Complete the missing full-method reference with the original one-percent driver."""
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"four_gap_ablation_20261123"))
import one_percent

if __name__=="__main__":
    one_percent.OUT=one_percent.solve.JMS/"results/table5_matched_target_20261124/references"
    one_percent.run(int(sys.argv[1]),"full")

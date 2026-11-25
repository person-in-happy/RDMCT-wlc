"""Reoptimize previously unscanned event orders under targeted makespan ceilings."""
import argparse
import sys
import time
from pathlib import Path

HERE=Path(__file__).resolve().parent
JMS=HERE.parents[1]
R=JMS/"results"
OUT=R/HERE.name
sys.path.insert(0,str(HERE.parent/"pareto_square_20261125"))
import fixed
from support import write

SQ=R/"pareto_square_20261125"
OLD=R/"pareto_scales_20261125"
CASES={
    "node20":(OLD/"cap812/p0020_native",[811.125,811.25,811.375,811.5,811.625,811.75,811.875,812]),
    "return981":(SQ/"native/bridge_dual_first_992_3/p_981_88_0",[960,970,975,977,978,979,979.25,979.5,979.75,980,980.25,980.5,980.75,981,982,984,992,1008,1050]),
    "blocks":(OLD/"two_blocks",[980,1000,1020,1040,1060,1080,1100,1110,1120,1130,1140,1148,1152,1155,1156.25]),
    "p823":(SQ/"native/p26_842/p_823_86_12",[812,813,814,815,817,819,820,821,822,822.5,823,824,826,830,840,860,885,910,950]),
}
if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("case",choices=[*CASES,"all"])
    parser.add_argument("--stop-after",type=int);args=parser.parse_args()
    fixed.sweep.CASES=CASES;fixed.sweep.OUT=OUT/"fixed"
    cases=list(CASES) if args.case=="all" else [args.case]
    start=time.monotonic()
    for index,name in enumerate(cases):
        elapsed=time.monotonic()-start
        eta=(len(cases)-index)*(elapsed/index if index else 32)
        q=dict(stage=name,total=len(cases),completed=index,failed=0,elapsed=elapsed,eta_total=elapsed+eta,eta_remaining=eta,
               estimate="native SCIP model per event order, then measured completed-case wall time")
        OUT.mkdir(parents=True,exist_ok=True);write(OUT/"fixed_progress.json",q);print(q,flush=True)
        fixed.main(name,args.stop_after)
    q.update(completed=len(cases),elapsed=time.monotonic()-start,eta_remaining=0);q["eta_total"]=q["elapsed"]
    write(OUT/"fixed_progress.json",q)

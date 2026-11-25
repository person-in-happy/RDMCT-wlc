"""Use the validated 16-wafer pure 2×2 memory setting for the archived large formulation."""
import runpy
import sys
from pathlib import Path

solvers=Path(__file__).resolve().parent.parent/"square_residence_20261125"
sys.path.insert(0,str(solvers))
import solver

ordinary=solver.cell.scip_settings
def settings(model,task,folder):
    ordinary(model,task,folder)
    assert task["n"]==16
    model.setRealParam("limits/memory",11500.)
solver.cell.scip_settings=settings
runpy.run_path(str(solvers/"solver.py"),run_name="__main__")

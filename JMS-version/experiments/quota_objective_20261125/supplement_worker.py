"""Use the shared resumable fixed-structure worker with the quota solver on sys.path."""
import importlib.util
from pathlib import Path
import sys
from supplement import PREVIOUS

spec = importlib.util.spec_from_file_location("threshold_checkpoint", PREVIOUS / "supplement_checkpoint.py")
worker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(worker)
common_install, common_exhausted = worker.install, worker.exhausted


def install(checkpoint):
    import solver
    common_install(checkpoint)
    attach = solver.cell.attach
    previous = checkpoint.native_state()

    def add_incumbent(model, values):
        original = attach(model, values)
        if (previous is not None and not checkpoint.state["resumed_incumbent_checked"]
                and len(model.model.getObjective().terms) > 1):
            warm = attach(model, previous)
            checkpoint.state["resumed_incumbent_checked"] = True
            if model.model.getSolObjVal(warm) < model.model.getSolObjVal(original)-1e-8:
                checkpoint.state["resumed_incumbent_submitted"] = model.model.addSol(warm)
            else:
                model.model.freeSol(warm)
            checkpoint.pulse()
        return original
    solver.cell.attach = add_incumbent


def exhausted(checkpoint):
    import score
    lower = score.physical_lower
    try:
        score.physical_lower = lambda cfg, _: lower(cfg, checkpoint.settings["clean_weight"])
        common_exhausted(checkpoint)
    finally:
        score.physical_lower = lower


if __name__ == "__main__":
    worker.install, worker.exhausted = install, exhausted
    worker.worker(Path(sys.argv[1]).resolve(), sys.argv[2])

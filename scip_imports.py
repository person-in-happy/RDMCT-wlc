"""Shared PySCIPOpt imports with a clearer installation error."""

try:
    import pyscipopt as scip
    import pyscipopt.scip as scip_core
    from pyscipopt import SCIP_RESULT
except ModuleNotFoundError as exc:
    if exc.name != "pyscipopt":
        raise
    raise ModuleNotFoundError(
        "PySCIPOpt is required but not installed for this Python interpreter.\n"
        "Install SCIP first, then install PySCIPOpt with one of:\n"
        "  python -m pip install pyscipopt\n"
        "  conda install -c conda-forge pyscipopt\n"
        "After installation, rerun the command with the same `python` executable."
    ) from exc

"""Share the frozen-input runner while binding paths and objective imports to this variant."""
from pathlib import Path


def load(module_globals):
    local=Path(module_globals["__file__"]).resolve()
    source=local.parents[1]/"residence_objective_20261125"/local.name
    exec(compile(source.read_bytes(),str(source),"exec"),module_globals)

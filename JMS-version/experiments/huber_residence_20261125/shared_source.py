from pathlib import Path


def load_shared(scope):
    caller=Path(scope["__file__"]).resolve()
    source=caller.parents[1]/"residence_objective_20261125"/caller.name
    original=scope["__name__"]
    scope["__name__"]="shared_"+caller.stem
    exec(compile(source.read_bytes(),str(source),"exec"),scope)
    scope["__name__"]=original

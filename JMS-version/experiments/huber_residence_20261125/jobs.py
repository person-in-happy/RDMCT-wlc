from shared_source import load_shared
load_shared(globals())

if __name__=="__main__":
    sys.modules["jobs"]=sys.modules[__name__]
from reuse_fixed import full_reference, four, stage_a


if __name__=="__main__":
    key=sys.argv[1]
    assert key in tasks()
    execute(key)

"""Test split-chain layouts with a distinct, immediately available companion on chamber 3."""
from pathlib import Path
from unittest.mock import patch
import time
from orders import OUT,JMS,sweep,blk,designs,trial

def run():
    source=OUT/"sources/double_only/A404/schedule.json"
    cfg=sweep.Config(**sweep.read(source)["config"])
    out=OUT/"alternate";out.mkdir(exist_ok=True)
    identity={f.relative_to(JMS).as_posix():sweep.sha(f) for f in (Path(__file__),Path(__file__).with_name("orders.py"),source)}
    identity_file=out/"identity.json"
    if identity_file.exists():assert sweep.read(identity_file)==identity
    else:sweep.atomic(identity_file,identity)
    selected=[(k,v) for k,v in designs().items() if len(v[0])==2 and len(v[1])==len(v[2])==1]
    original=blk.block
    def disjoint(cfg,mode,c,groups):
        if c==3:groups=[[w if w!="D2" else "D3" for w in g] for g in groups]
        return original(cfg,mode,c,groups)
    begin=time.monotonic()
    with patch.object(blk,"block",disjoint):
        for i,(k,v) in enumerate(selected):
            elapsed=time.monotonic()-begin;rem=(len(selected)-i)*(elapsed/i if i else 2.0)
            sweep.atomic(out/"progress.json",dict(done=i,total=len(selected),failed=0,elapsed_s=elapsed,remaining_s=rem,estimated_total_s=elapsed+rem))
            print(f"{i}/{len(selected)}, elapsed={elapsed:.1f}s, remaining ~{rem:.1f}s",flush=True)
            trial(cfg,k,v,.5,2,out)
    elapsed=time.monotonic()-begin
    sweep.atomic(out/"progress.json",dict(done=len(selected),total=len(selected),failed=0,elapsed_s=elapsed,remaining_s=0,estimated_total_s=elapsed))

if __name__=="__main__":run()

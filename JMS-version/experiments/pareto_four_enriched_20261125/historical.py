"""Collect and independently recertify archived four-double-wafer schedules with identical physical settings."""
import hashlib
import json
import os
import time
from probe import EX,JMS,R,OUT,sweep,fixed,sparse_witness
from pathlib import Path

def run():
    target=OUT/"archive_catalogue.json"
    if target.exists():return
    base=sweep.read(OUT/"sources/double_only/A404/schedule.json")["config"]
    cfg=sweep.Config(**base)
    seen={};scanned=0;candidates=0;begin=time.monotonic()
    for folder,dirs,files in os.walk(R):
        if Path(folder)==OUT:dirs.clear();continue
        for name in files:
            if not name.endswith(".json"):continue
            p=Path(folder)/name
            size=p.stat().st_size
            if size<10000 or size>300000:continue
            scanned+=1
            with p.open("rb") as f:
                head=f.read(2048)
                if b'"load_ports"' not in head:continue
                data=json.loads(head+f.read())
            if not isinstance(data,dict) or not all(data.get(k) for k in ("config","jobs","events","cycles","pairs")):continue
            config=data["config"]
            if any(config.get(k)!=v for k,v in base.items() if k not in ("horizon","max_pairs","max_cycles")):continue
            key=hashlib.sha256(json.dumps([data[k] for k in ("events","jobs","cycles","pairs")],sort_keys=True).encode()).hexdigest()
            if key not in seen:seen[key]=(p,data)
            candidates+=1
        if scanned and scanned%2000<15:print(f"archived JSON files inspected {scanned}, candidate witnesses {candidates}, elapsed {time.monotonic()-begin:.1f}s",flush=True)
    results=[]
    for k,(p,d) in sorted(seen.items()):
        dest=OUT/"historical"/k[:18];dest.mkdir(parents=True,exist_ok=True)
        fp=dest/"result.json"
        if not fp.exists():
            try:
                checked=sweep.cell.lift(cfg,sparse_witness(cfg,d),None,rebuild=True)
            except (ValueError,KeyError):checked=None
            if checked:
                doc,a,_,rep,n=checked
                assert rep["valid"]
                sweep.save(dest/"schedule.json",doc);sweep.save(dest/"assignment.json.gz",a)
                v=dict(source=str(p.relative_to(JMS)),source_sha256=sweep.sha(p),metrics=fixed.metrics(doc),
                    original_rows=n,replay=rep,files={n:sweep.sha(dest/n) for n in ("schedule.json","assignment.json.gz")})
            else:v=dict(source=str(p.relative_to(JMS)),source_sha256=sweep.sha(p),rejected=True)
            sweep.atomic(fp,v)
        results.append(str(fp.relative_to(JMS)))
    sweep.atomic(target,dict(files_screened=scanned,matching=candidates,distinct=len(seen),native_records=results,wall_seconds=time.monotonic()-begin,
        settings="4x2x2/one wafer per port, H10, 8 dummies, unrestricted witness check at horizon 10000; compact or different-horizon files independently lifted."))
    print(scanned,candidates,len(seen),"finished in",time.monotonic()-begin,flush=True)

if __name__=="__main__":run()

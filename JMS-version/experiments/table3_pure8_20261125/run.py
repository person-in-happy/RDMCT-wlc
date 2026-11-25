"""Pure eight-wafer threshold study; separate recoverable preparation, A and B endpoints."""
from pathlib import Path
import csv
import hashlib
import json
import os
import sys
import time
import subprocess
import msvcrt
import psutil

HERE = Path(__file__).resolve().parent
JMS = HERE.parents[1]
OUT = JMS/"results/table3_pure8_20261125"
LEVELS = {"10pct": .10, "1pct": .01, "0p01pct": .0001}
MODES = ("4x1","2x2")

def load(p):
    return json.loads(p.read_bytes())

def atomic(p,data):
    p.parent.mkdir(parents=True,exist_ok=True)
    tmp=p.with_suffix(f".{os.getpid()}.tmp")
    tmp.write_text(json.dumps(data,indent=2),encoding="utf8")
    os.replace(tmp,p)

def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

def directory(key):
    return OUT.joinpath(*key.split("__"))

def checked(key):
    folder=directory(key)
    path=folder/"result.json"
    if not path.is_file(): return False
    entry=load(path)
    return entry.get("identity")==identity(key) and all(sha(folder/name)==s for name,s in entry["hashes"].items())

def identity(key):
    return dict(key=key,inputs=sha(JMS/"results/table4_one_percent_20261124/inputs/D_n8_H10_mixed_dual/input.json"),
                objective=sha(HERE.parent/"huber_residence_20261125/score.py"),script=sha(Path(__file__)),seed=1)

def execute(key):
    folder=directory(key)
    folder.mkdir(parents=True,exist_ok=True)
    parts=key.split("__")
    mode=parts[0]
    if checked(key):return
    if len(parts)<3:
        sys.path.insert(0,str(HERE.parent/"mixed_controls_20261122"))
        from scale import Config,prepare,first
    if len(parts)==1:
        from decoder import Decoder,Retiming
        ports={f"LP{i}":{"4x1":2 if mode=="4x1" else 0,"2x2":2 if mode=="2x2" else 0} for i in range(1,5)}
        cfg=Config(load_ports=ports,cleaning_interval=10,dummy_count=8,horizon=100000)
        dec=Decoder(cfg)
        genes=tuple(v for i in range(dec.n) for v in (0,i//2%2,0,0,0))
        data=Retiming(dec.build(genes,dec.pairing(genes)),25).solve("A",None,5)
        prepare(folder,cfg,data,1)
        files=["prepared/"+n for n in ("schedule.json","assignment.json.gz","primary.json")]
    elif len(parts)==2:
        src=OUT/mode/"prepared"
        record=first(src,folder/"A",8,1,"default","cp",None,LEVELS[parts[1]],True)
        assert record["gate"] and record["gap"]<=LEVELS[parts[1]]+1e-8
        files=["A/"+n for n in ("schedule.json","assignment.json.gz","primary.json")]
    else:
        sys.path.insert(0,str(HERE.parent/"huber_residence_20261125"))
        from solver import run
        r=run("fixed",OUT/mode/parts[1]/"A",folder/"B",seed=1,gap=LEVELS[parts[2]])
        assert r["eligible"] and r["replay"]["valid"]
        files=["B/"+n for n in ("schedule.json","assignment.json.gz","result.json")]
    atomic(folder/"result.json",dict(identity=identity(key),hashes={n:sha(folder/n) for n in files}))

def controller():
    keys=[(m,) for m in MODES]+[(m,a) for m in MODES for a in LEVELS]+[(m,a,b) for m in MODES for a in LEVELS for b in LEVELS]
    keys=["__".join(k) for k in keys]
    OUT.mkdir(parents=True,exist_ok=True)
    with (OUT/"controller.lock").open("a+b") as lock:
        lock.seek(0)
        try:msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
        except OSError:return
        active={}
        for p in psutil.process_iter(["cmdline"]):
            cmd=p.info["cmdline"] or []
            if len(cmd)>=3 and os.path.normcase(cmd[-2])==os.path.normcase(str(Path(__file__).resolve())) and cmd[-1] in keys:
                active[cmd[-1]]=p
        prior=load(OUT/"progress.json") if (OUT/"progress.json").exists() else {}
        elapsed=prior.get("elapsed_s",0)
        begin=time.monotonic()
        failed={}
        durations=prior.get("completed_seconds",{})
        while True:
            done={k for k in keys if checked(k)}
            for k,p in list(active.items()):
                if not p.is_running():
                    if k not in done:failed[k]="See console.log"
                    else:durations[k]=max(0,time.time()-p._create_time)
                    del active[k]
            for k in keys:
                if len(active)>=4:break
                if k in done or k in failed or k in active:continue
                parent=k.rsplit("__",1)[0]
                if parent!=k and parent not in done:continue
                folder=directory(k)
                folder.mkdir(parents=True,exist_ok=True)
                with (folder/"console.log").open("a",encoding="utf8") as log:
                    p=subprocess.Popen([sys.executable,"-B","-u","-X","utf8",str(Path(__file__).resolve()),k],stdout=log,stderr=subprocess.STDOUT)
                active[k]=psutil.Process(p.pid)
            wall=elapsed+time.monotonic()-begin
            pending=[k for k in keys if k not in done and k not in failed]
            import statistics
            def estimate(k):
                observed=[v for kk,v in durations.items() if kk.count("__")==k.count("__")]
                return statistics.median(observed) if observed else [100,1200,12][k.count("__")]
            eta=sum(max(3,estimate(k)-(time.time()-active[k].create_time() if k in active else 0)) for k in pending)/4
            atomic(OUT/"progress.json",dict(validated=len(done),expected=len(keys),failed=failed,
                active={k:p.pid for k,p in active.items()},elapsed_s=wall,remaining_s=eta,total_estimated_s=wall+eta,
                completed_seconds=durations,basis="Median per stage after completed runs. Initial planning values: SPBS 100s, A 1200s, fixed B 12s. The tight full CP projection can exceed this estimate. Four single-core workers.",
                recovery="Adopt surviving workers; reuse hash-verified endpoints. A reuses saved global lower bounds with original feasible SPBS start. Unbounded native searches restart their tree; preparing SPBS restarts from its constructive seed."))
            print(f"Verified {len(done)}/{len(keys)} | failed {len(failed)} | elapsed {wall:.0f}s | ETA {eta:.0f}s | total {wall+eta:.0f}s | {list(active)}",flush=True)
            if not active:break
            time.sleep(4)
        if failed or len(done)!=len(keys):raise SystemExit(1)
        rows=[]
        for m in MODES:
            for a in LEVELS:
                ar=load(OUT/m/a/"A/primary.json")["record"]
                for b in LEVELS:
                    folder=OUT/m/a/b/"B"
                    br=load(folder/"result.json")
                    sc=br["measured"]
                    rows.append(dict(case="D_n8_pure_"+m,recipe=m,gA=a,gB=b,f_A=sc["cmax"],f_B=sc["secondary"],mean=sc["mean_residence"],spread=sc["residence_range"],E=sc["clean_deficit"],A_lower=ar["lower"],A_upper=ar["upper"],A_gap=ar["gap"],B_lower=br["record"]["lower"],B_gap=br["record"]["gap"],source=folder.relative_to(JMS).as_posix()))
        with (OUT/"threshold_cells.csv").open("w",encoding="utf8",newline="") as f:
            w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)

if __name__=="__main__":
    if len(sys.argv)>1:execute(sys.argv[1])
    else:controller()

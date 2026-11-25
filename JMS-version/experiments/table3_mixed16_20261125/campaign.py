"""Keep one ordered incumbent/bound stream and start fixed Huber cells after each gate."""
import csv
import hashlib
import json
import msvcrt
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import psutil

HERE=Path(__file__).resolve().parent
JMS=HERE.parents[1]
OUT=JMS/"results/table3_mixed16_20261125"
BOUND=JMS/"results/table3_grid16_20261125/batch_bound_mixed.json"
GAPS={"10pct":.1,"1pct":.01,"0p01pct":.0001}
LAYOUTS=("chain22","chain31","mixedlead")


def read(p):return json.loads(p.read_bytes())


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def save(p,data):
    tmp=p.with_name(p.name+f".{os.getpid()}.tmp")
    tmp.write_text(json.dumps(data,indent=2),encoding="utf8")
    os.replace(tmp,p)


def cli(kind,key):
    if kind=="proposal":
        from candidate import main
        main(key)
    elif kind=="native":
        from prepare import configuration,cell,sparse_witness,store_primary
        src=OUT/key
        folder=OUT/"witnesses"/key.replace("/","__").removesuffix(".json")
        folder.mkdir(exist_ok=True,parents=True)
        dataset=read(src)
        cfg=configuration()
        verified=cell.lift(cfg,sparse_witness(cfg,dataset),None,rebuild=True)
        if not verified:raise ValueError("Full native model rejected candidate")
        store_primary(folder,verified,dict(source=key,source_sha256=sha(src),global_case_sha256=sha(OUT/"input.json")))
    elif kind=="B":
        a,b=key.split("__")
        sys.path.insert(0,str(HERE.parent/"huber_residence_20261125"))
        from solver import run
        parent=OUT/read(OUT/"stream.json")["gates"][a]["path"]
        run("fixed",parent,OUT/"grid"/a/b,seed=1,gap=GAPS[b])
    else:raise ValueError(kind)


def controller():
    with (OUT/"controller.lock").open("a+b") as lock:
        lock.seek(0)
        try:msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
        except OSError:return
        identity=dict(config=sha(OUT/"input.json"),source=sha(OUT/"prepared/primary.json"),batch_bound=sha(BOUND),
           solver=sha(HERE.parent/"huber_residence_20261125/solver.py"),objective=sha(HERE.parent/"huber_residence_20261125/score.py"),
           levels=GAPS,seed=1)
        ledger=OUT/"stream.json"
        state=read(ledger) if ledger.exists() else dict(identity=identity,events=[],gates={})
        assert state["identity"]==identity
        progress=OUT/"progress.json"
        prior=read(progress).get("elapsed_s",0) if progress.exists() else 0
        start=time.monotonic()
        bounds=read(BOUND)["lower"]
        active={}
        for p in psutil.process_iter(["cmdline"]):
            c=p.info["cmdline"] or []
            if len(c)>=3 and os.path.normcase(c[-3])==os.path.normcase(str(Path(__file__))):
                active[c[-2],c[-1]]=p
        def launch(k):
            kind,key=k
            filename=(kind+"_"+key.replace("/","_").replace("__","_")+".log")
            with (OUT/filename).open("a",encoding="utf8") as log:
                p=subprocess.Popen([sys.executable,"-B","-u","-X","utf8",str(Path(__file__)),kind,key],stdout=log,stderr=subprocess.STDOUT)
            active[k]=psutil.Process(p.pid)
        jobs=set()
        failures={}
        while True:
            for k,p in list(active.items()):
                if not p.is_running():
                    del active[k]
                    kind,key=k
                    marker=(OUT/"proposals"/key/"result.json" if kind=="proposal" else OUT/"witnesses"/key.replace("/","__").removesuffix(".json")/"primary.json" if kind=="native" else OUT/"grid"/Path(*key.split("__"))/"result.json")
                    if not marker.exists():failures["/".join(k)]="Worker exited before writing a validated endpoint"
            for folder in [OUT/"prepared"]+sorted((OUT/"witnesses").glob("*"),key=lambda p:p.stat().st_mtime):
                record=folder/"primary.json"
                if not record.exists():continue
                if any(row["record_sha256"]==sha(record) for row in state["events"]):continue
                data=read(record)
                assert data["rows"]==1109436 and data["replay"]["valid"] and sha(folder/"schedule.json")==data["schedule_sha256"] and sha(folder/"assignment.json.gz")==data["assignment_sha256"]
                upper=data["metrics"]["cmax"]
                if state["events"] and upper>=state["events"][-1]["upper"]:continue
                event=dict(path=folder.relative_to(OUT).as_posix(),record_sha256=sha(record),upper=upper,lower=bounds,gap=(upper-bounds)/bounds,
                           lower_source=BOUND.relative_to(JMS).as_posix(),lower_sha256=sha(BOUND))
                state["events"].append(event)
                for a,tau in GAPS.items():
                    if a not in state["gates"] and event["gap"]<=tau+1e-10:state["gates"][a]=event
                save(ledger,state)
            rows=[]
            for a,e in state["gates"].items():
                for b,tau in GAPS.items():
                    folder=OUT/"grid"/a/b
                    marker=folder/"result.json"
                    if marker.exists():
                        z=read(marker)
                        assert z["replay"]["valid"] and z["eligible"] and z["record"]["gap"]<=tau+1e-8
                        assert all(sha(folder/k)==v for k,v in z["files"].items())
                        m=z["measured"]
                        rows.append(dict(case="D_n16_H10_mixed_dual",recipe="mixed",gA=a,gB=b,f_A=m["cmax"],f_B=m["secondary"],mean=m["mean_residence"],spread=m["residence_range"],E=m["clean_deficit"],A_lower=e["lower"],A_upper=e["upper"],A_gap=e["gap"],B_lower=z["record"]["lower"],B_upper=z["record"]["upper"],B_gap=z["record"]["gap"],source=folder.relative_to(JMS).as_posix(),schedule_sha256=sha(folder/"schedule.json")))
                    elif not any(k[0] in ("B","native") for k in active):
                        key=("B",a+"__"+b)
                        if "/".join(key) not in failures:launch(key)
            if rows:
                tmp=OUT/"threshold_cells.tmp"
                with tmp.open("w",encoding="utf8",newline="") as f:
                    w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
                os.replace(tmp,OUT/"threshold_cells.csv")
            for p in sorted((OUT/"proposals").glob("*/candidate_*.json"),key=lambda f:f.stat().st_mtime):
                if p.stem.endswith("_values"):continue
                key=p.relative_to(OUT).as_posix()
                dest=OUT/"witnesses"/key.replace("/","__").removesuffix(".json")/"primary.json"
                k=("native",key)
                if not dest.exists() and not any(k1[0] in ("native","B") for k1 in active) and "/".join(k) not in failures:
                    launch(k)
            for layout in LAYOUTS:
                k=("proposal",layout)
                if (OUT/"proposals"/layout/"result.json").exists() or k in active or "/".join(k) in failures:continue
                if len(active)<3 and sum(k1[0]=="proposal" for k1 in active)<2:launch(k)
            elapsed=prior+time.monotonic()-start
            eta=max([360-read(p)["elapsed"] for p in (OUT/"proposals").glob("*/checkpoint.json")]+[0])
            row=dict(expected=9,completed=len(rows),failed=failures,elapsed_s=elapsed,planning_remaining_current_s=eta,
                estimated_remaining_s=0 if len(rows)==9 else None,estimated_total_s=elapsed if len(rows)==9 else None,
                active={"/".join(k):p.pid for k,p in active.items()},upper=state["events"][-1]["upper"],lower=bounds,
                gates=list(state["gates"]),basis="360 solver seconds per compact proposal, two workers. Full 16-wafer gate ETA cannot yet be estimated from comparable completions.",
                recovery="Adopt running workers. Resume verified original-model endpoints and the ordered gates. Compact CP restarts its tree with the last incumbent and remaining cumulative search budget.")
            save(progress,row)
            print(f"16-mixed {len(rows)}/9; failures {len(failures)}; C bounds [{bounds},{row['upper']}]; elapsed {elapsed:.0f}s; stage ETA {eta:.0f}s; grid ETA unknown; active {list(active)}",flush=True)
            if len(rows)==9 or not active:break
            time.sleep(3)


if __name__=="__main__":
    if len(sys.argv)==3:cli(*sys.argv[1:])
    else:controller()

"""Resume the mixed eight-wafer grid and verify every fixed-structure secondary result."""
import csv
import gzip
import hashlib
import json
import msvcrt
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import psutil

HERE=Path(__file__).resolve().parent
JMS=HERE.parents[1]
OUT=JMS/"results/table3_mixed8_20261125"
HUB=HERE.parent/"huber_residence_20261125"
LEVELS={"10pct":.1,"1pct":.01,"0p01pct":.0001}
sys.path.insert(0,str(HUB))
from score import metrics

def read(path):
    return json.loads(path.read_bytes())

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def save(path,data):
    path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_name(path.name+f".{os.getpid()}.tmp")
    temp.write_text(json.dumps(data,indent=2),encoding="utf8")
    temp.replace(path)

def signature(a,b):
    e=read(OUT/"primary_search.json")["gates"][a]
    return dict(primary_sha256=e["record_sha256"],target_gap=LEVELS[b],run_sha256=sha(Path(__file__)),
                score_sha256=sha(HUB/"score.py"),solver_sha256=sha(HUB/"solver.py"))

def checked(a,b):
    path=OUT/a/b
    end=path/"cell.json"
    if not end.exists():return False
    rec=read(end)
    return rec["identity"]==signature(a,b) and all(sha(path/"B"/k)==v for k,v in rec["hashes"].items())

def copy_equivalent(parent,target,b):
    old=JMS/"results/huber_residence_20261125/runs"
    for source in (old/"t4_10_8_10_1_fixed/B",old/"t4_1_8_10_1_fixed/B"):
        prior=read(source/"result.json")
        p=prior["parents"][0]
        if sha(parent/"schedule.json")!=p["schedule_sha256"]:continue
        with gzip.open(parent/"assignment.json.gz","rb") as f:
            native=json.load(f)
        with gzip.open(p["assignment"],"rb") as f:
            if native!=json.load(f):continue
        assert prior["replay"]["valid"] and prior["original_rows"]>0 and prior["replayed_rows"]>0
        assert all(sha(source/k)==v for k,v in prior["files"].items())
        assert sha(Path(p["assignment"]))==p["assignment_sha256"]
        if prior["record"]["gap"]>LEVELS[b]+1e-9:continue
        target.mkdir(parents=True,exist_ok=True)
        for name in prior["files"]:shutil.copyfile(source/name,target/name)
        save(target/"result.json",dict(prior,requested_grid_gap=LEVELS[b],grid_parent_sha256=sha(parent/"primary.json"),
               reuse_result=str((source/"result.json").relative_to(JMS)),reuse_result_sha256=sha(source/"result.json")))
        return True
    return False

def worker(a,b):
    if checked(a,b):return
    folder=OUT/a/b
    event=read(OUT/"primary_search.json")["gates"][a]
    parent=OUT/event["path"]
    assert sha(parent/"primary.json")==event["record_sha256"]
    target=folder/"B"
    reused=copy_equivalent(parent,target,b)
    if not reused:
        from solver import run
        run("fixed",parent,target,seed=1,gap=LEVELS[b])
    result=read(target/"result.json")
    phys=metrics(read(target/"schedule.json"))
    assert max(abs(v-result["measured"][k]) for k,v in phys.items())<1e-7
    assert phys["cmax"]<=event["upper"]+2e-5 and result["record"]["gap"]<=LEVELS[b]+1e-8
    assert result["eligible"] and result["replay"]["valid"] and result["replayed_rows"]>0
    assert all(sha(target/k)==v for k,v in result["files"].items())
    save(folder/"cell.json",dict(identity=signature(a,b),hashes=result["files"]|{"result.json":sha(target/"result.json")},
         reuse=reused,first_primary_event=event,physical=phys))

def export():
    rows=[]
    for a in LEVELS:
        for b in LEVELS:
            assert checked(a,b)
            folder=OUT/a/b
            end=read(folder/"cell.json")
            e=end["first_primary_event"]
            raw=read(folder/"B/result.json")
            s=end["physical"]
            rows.append(dict(case="D_n8_H10_mixed_dual",recipe="mixed",gA=a,gB=b,f_A=s["cmax"],f_B=s["secondary"],
                mean=s["mean_residence"],spread=s["residence_range"],E=s["clean_deficit"],
                A_lower=e["lower"],A_upper=e["upper"],A_gap=e["gap"],
                B_lower=raw["record"]["lower"],B_upper=raw["record"]["upper"],B_gap=raw["record"]["gap"],
                reused=end["reuse"],A_source=(OUT/e["path"]).relative_to(JMS).as_posix(),
                A_sha256=e["record_sha256"],source=(folder/"B").relative_to(JMS).as_posix(),
                schedule_sha256=raw["files"]["schedule.json"],assignment_sha256=raw["files"]["assignment.json.gz"]))
    temp=OUT/"threshold_cells.tmp"
    with temp.open("w",encoding="utf8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    temp.replace(OUT/"threshold_cells.csv")

def controller():
    path=OUT/"progress.json"
    past=read(path).get("elapsed_s",0) if path.exists() else 0
    start=time.monotonic()
    active={}
    for p in psutil.process_iter(["cmdline"]):
        cmd=p.info.get("cmdline") or []
        if len(cmd)>=3 and os.path.normcase(cmd[-3])==os.path.normcase(str(Path(__file__).resolve())):
            if cmd[-2] in LEVELS and cmd[-1] in LEVELS:active[tuple(cmd[-2:])]=p
    failed=[]
    while True:
        search=OUT/"primary_search.json"
        gates=read(search)["gates"] if search.exists() else {}
        done={(a,b) for a in gates for b in LEVELS if checked(a,b)}
        for job,p in list(active.items()):
            if not p.is_running():
                del active[job]
                if job not in done:failed.append(job)
        for a in gates:
            for b in LEVELS:
                if len(active)>=2:break
                if (a,b) in active or (a,b) in done or (a,b) in failed:continue
                dest=OUT/a/b
                dest.mkdir(exist_ok=True,parents=True)
                with (dest/"worker.log").open("a",encoding="utf8") as log:
                    p=subprocess.Popen([sys.executable,"-B","-u",str(Path(__file__).resolve()),a,b],
                                       stdout=log,stderr=subprocess.STDOUT)
                active[(a,b)]=psutil.Process(p.pid)
        elapsed=past+time.monotonic()-start
        prim=read(OUT/"primary_progress.json") if (OUT/"primary_progress.json").exists() else {}
        eta=max(0,prim.get("estimated_remaining_s",150))+(9-len(done))*10/2
        save(path,dict(completed=len(done),expected=9,failed=failed,active={a+"/"+b:p.pid for (a,b),p in active.items()},
            elapsed_s=elapsed,estimated_total_s=elapsed+eta,estimated_remaining_s=eta,
            basis="Primary live projection plus historical 10 s per fixed B, two independent workers",
            recovery="Preserve validated native primary incumbents and first handoffs; restart CP from last verified optimum candidate. Reuse hash-checked cells and adopt surviving B workers. Interrupted unbounded B programs restart their individual cell."))
        print(f"Verified {len(done)}/9, failures {len(failed)}, A handoffs {len(gates)}/3, elapsed {elapsed:.0f}s, total est {elapsed+eta:.0f}s, ETA {eta:.0f}s",flush=True)
        if failed:raise RuntimeError(failed)
        if len(done)==9:break
        time.sleep(4)
    export()

if __name__=="__main__":
    if len(sys.argv)==3:worker(*sys.argv[1:])
    else:
        with (OUT/"controller.lock").open("a+b") as l:
            l.seek(0)
            try:msvcrt.locking(l.fileno(),msvcrt.LK_NBLCK,1)
            except OSError:print("A mixed-grid controller is already active.")
            else:controller()

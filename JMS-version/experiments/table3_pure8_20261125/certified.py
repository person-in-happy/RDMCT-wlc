"""Resumable execution of the bound-assisted validated table-3 thresholds, including Huber retiming."""
import csv
import msvcrt
import os
from pathlib import Path
import subprocess
import sys
import time
import psutil
from gates import GATES,done,register
from run import HERE,JMS,OUT,LEVELS,load,sha,atomic

MODE=sys.argv[1]
ROOT=GATES/MODE

def same_output(p):
    try:
        candidate=Path(p.environ().get("TABLE3_PURE8_RECOVERY_ROOT",str(OUT/"certified"))).resolve()
        return candidate==GATES
    except (psutil.NoSuchProcess,psutil.AccessDenied):
        return False

def record_B(a,b):
    d=ROOT/a/b/"B"
    file=d/"result.json"
    if not file.is_file():return None
    r=load(file)
    A=ROOT/a/"A"
    assert r["replay"]["valid"] and r["eligible"] and r["seed"]==1 and r["target_gap"]==LEVELS[b]
    assert r["parents"][0]["assignment_sha256"]==sha(A/"assignment.json.gz")
    assert r["parents"][0]["schedule_sha256"]==sha(A/"schedule.json")
    assert all(sha(d/k)==v for k,v in r["files"].items())
    return r

def export():
    rows=[]
    for a in LEVELS:
        if not done(MODE,a):continue
        ar=load(ROOT/a/"A/primary.json")
        for b in LEVELS:
            br=record_B(a,b)
            if not br:continue
            folder=ROOT/a/b/"B"
            x=br["measured"]
            rows.append(dict(case="D_n8_pure_"+MODE,recipe=MODE,gA=a,gB=b,f_A=x["cmax"],f_B=x["secondary"],mean=x["mean_residence"],
                spread=x["residence_range"],E=x["clean_deficit"],huber=x["huber_penalty"],A_upper=ar["upper"],A_lower=ar["lower"],A_gap=ar["gap"],
                B_upper=br["record"]["upper"],B_lower=br["record"]["lower"],B_gap=br["record"]["gap"],source=folder.relative_to(JMS).as_posix(),
                schedule=(folder/"schedule.json").relative_to(JMS).as_posix(),schedule_sha256=sha(folder/"schedule.json"),
                A_proof=(ROOT/a/"A/primary.json").relative_to(JMS).as_posix(),B_proof=(folder/"result.json").relative_to(JMS).as_posix()))
    if rows:
        tmp=ROOT/"threshold.tmp"
        with tmp.open("w",encoding="utf8",newline="") as f:
            w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
        os.replace(tmp,ROOT/"threshold_cells.csv")
    return len(rows)

def worker(key):
    if key=="A":
        settings=load(ROOT/"protocol.json")
        lower=settings["lower"]
        register(MODE,OUT/MODE/"prepared",lower,"SPBS initial solution")
        for entry in settings["candidates"]:
            if all(done(MODE,a) for a in LEVELS):break
            p=JMS/entry["source"]
            if p.is_dir():
                assert sha(p/"primary.json")==entry["sha256"]
                register(MODE,p,lower,"archived native witness (ordered input stream)")
            else:
                assert sha(p)==entry["sha256"]
                out=ROOT/"search"/p.stem/"result.json"
                if not out.is_file():
                    cmd=[sys.executable,"-B","-u","-X","utf8",str(HERE/"candidate.py"),MODE,str(p),str(entry["cap"]),str(lower)]
                    for proc in psutil.process_iter(["cmdline"]):
                        args=proc.info["cmdline"] or []
                        if args[-5:]==cmd[-5:] and same_output(proc):
                            proc.wait()
                    if not out.is_file() and not all(done(MODE,a) for a in LEVELS):
                        subprocess.run(cmd,check=True)
        if not all(done(MODE,a) for a in LEVELS):
            raise RuntimeError("Input stream exhausted before every handoff")
    else:
        a,b=key.split("__")
        if record_B(a,b):return
        sys.path.insert(0,str(HERE.parent/"huber_residence_20261125"))
        from solver import run
        run("fixed",ROOT/a/"A",ROOT/a/b/"B",seed=1,gap=LEVELS[b])
        assert record_B(a,b)

def main():
    ROOT.mkdir(parents=True,exist_ok=True)
    protocol=ROOT/"protocol.json"
    if not protocol.is_file():
        if MODE!="2x2":raise RuntimeError("Provide the common lower bound and frozen input stream for 4x1")
        folder=OUT/"projection"/MODE/"565"
        proof=folder/"proof.json"
        candidates=[dict(source=p.relative_to(JMS).as_posix(),sha256=sha(p),cap=int(p.stem.split("_")[1]))
            for p in sorted(folder.glob("projected_*.json"),key=lambda f:-int(f.stem.split("_")[1]))]
        assert candidates and load(proof)["status"]=="OPTIMAL"
        atomic(protocol,dict(lower=int(load(proof)["lower"]),lower_source=proof.relative_to(JMS).as_posix(),lower_sha256=sha(proof),
            initial_sha256=sha(OUT/MODE/"prepared/assignment.json.gz"),initial_record_sha256=sha(OUT/MODE/"prepared/primary.json"),
            started=time.time(),candidates=candidates,order="SPBS then the actual discovery order of strictly improving product-projection incumbents. For each projected assignment solve the original physical skeleton with seed one and register the first validated incumbent crossing each threshold."))
    with (ROOT/"controller.lock").open("a+b") as lock:
        lock.seek(0)
        try:msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
        except OSError:return
        keys=["A"]+[f"{a}__{b}" for a in LEVELS for b in LEVELS]
        live={}
        for p in psutil.process_iter(["cmdline"]):
            cmd=p.info["cmdline"] or []
            if len(cmd)>3 and os.path.normcase(cmd[-3])==os.path.normcase(str(Path(__file__).resolve())) and cmd[-2]==MODE and cmd[-1] in keys and same_output(p):live[cmd[-1]]=p
        if live:print("Adopted active",list(live),flush=True)
        failed={}
        while True:
            complete={k for k in keys if (all(done(MODE,a) for a in LEVELS) if k=="A" else record_B(*k.split("__")))}
            for key,p in list(live.items()):
                if not p.is_running():
                    if key not in complete:failed[key]="See "+key+".log"
                    del live[key]
            for key in keys:
                if key in complete or key in failed or key in live or len(live)>=3:continue
                if key!="A" and not done(MODE,key.split("__")[0]):continue
                with (ROOT/(key+".log")).open("a",encoding="utf8") as log:
                    process=subprocess.Popen([sys.executable,"-B","-u","-X","utf8",str(Path(__file__).resolve()),MODE,key],stdout=log,stderr=subprocess.STDOUT)
                live[key]=psutil.Process(process.pid)
            elapsed=time.time()-load(protocol)["started"]
            n=export()
            eta=(len(keys)-len(complete))*12/3
            if "A" not in complete:eta+=max(8,90-elapsed)
            atomic(ROOT/"progress.json",dict(expected=9,completed=n,failed=failed,active={k:p.pid for k,p in live.items()},
                elapsed_s=elapsed,estimated_remaining_s=eta,total_estimated_s=elapsed+eta,
                basis="Native Huber retiming on eight wafers, historical 8–12 seconds per setting, up to three parallel slots. Add 90s for each native proposal attempt until observed first handoffs.",
                recovery="One lock per supervisor, adopt surviving workers, reuse checksum-verified handoffs and retiming endpoints. Restart unfinished unlimited B search; native proposal attempts restart their tree."))
            print(f"{MODE} verified {n}/9, failed {len(failed)}, elapsed {elapsed:.0f}s, estimated total {elapsed+eta:.0f}s, ETA {eta:.0f}s",flush=True)
            if not live:
                if n!=9:raise SystemExit(1)
                break
            time.sleep(2)

if __name__=="__main__":
    if len(sys.argv)>2:worker(sys.argv[2])
    else:main()

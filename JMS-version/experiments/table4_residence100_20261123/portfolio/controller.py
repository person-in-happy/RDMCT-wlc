"""Adopt live native/projection searches and collect the first verified physical endpoint."""
from datetime import datetime
import msvcrt
import os
from pathlib import Path
import subprocess
import sys
import time

import psutil
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent))
from inputs import CASES, CP, OUT, ROOT, SCIP, case_id, read, save, sha, validate, product
sys.path.insert(0,str(HERE.parent))
from campaign import refresh

ACTIVE_CASES=tuple((n,h) for n,h in CASES if n in (4,8))


def identify(process):
    argv=process.cmdline()
    for script,length in ((HERE.parent/"worker.py",4),(HERE/"joint.py",3),(HERE/"window.py",3)):
        for i,value in enumerate(argv):
            if not value.lower().endswith(script.name) or Path(value).resolve()!=script:
                continue
            rest=argv[i+1:]
            if len(rest)<length:
                return
            n,h,seed=map(int,rest[:3])
            mode=rest[3] if script.name=="worker.py" else ("window" if script.name=="window.py" else ("decision" if "--decision" in rest else "joint"))
            if (n,h) in ACTIVE_CASES and seed in (1,2,3) and mode in ("A","B","J","decision","joint","window"):
                return (n,h,seed,mode)


def main():
    area=OUT/"portfolio"
    area.mkdir(exist_ok=True)
    lock=(OUT/"controller.lock").open("a+b")
    lock.seek(0)
    msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
    active={}
    for p in psutil.process_iter(["name"]):
        if (p.info["name"] or "").lower()=="python.exe":
            try:
                key=identify(p)
            except (psutil.NoSuchProcess,psutil.AccessDenied):
                continue
            if key:
                assert key not in active
                active[key]=p
    total=len(ACTIVE_CASES)*3*4
    save(area/"protocol_4_8.json",dict(base=sha(OUT/"protocol.json"),cases=ACTIVE_CASES,expected=total,target=.10,adopted={str(k):p.pid for k,p in active.items()},
         files={p.name:sha(p) for p in HERE.glob("*.py")},rule="first available verified original-model incumbent and objective-specific bound",
         decision="Test an outward relaxation at the feasible joint incumbent divided by 1.10. An infeasible sublevel supplies a lower bound.",
         pure_B="For a zero-cost feasible D assignment the lower and upper bounds both equal zero. Respect original candidate limits."))
    completed_attempts=set()
    previous=OUT/"progress.json"
    failed=read(previous).get("failures",{}) if previous.exists() else {}
    start=time.monotonic()
    count=-1
    def group(k):
        return f"{case_id(k[0],k[1])}__s{k[2]}"
    keys=[(n,h,s,mode) for s in (1,2,3) for n,h in ACTIVE_CASES for mode in ("decision","window","A","B","J","joint")]
    for k in keys:
        if k in active:
            continue
        if str(k) in failed or any((OUT/"logs").glob(f"portfolio-{group(k)}-{k[-1]}-*.log")):
            completed_attempts.add(k)
        elif k[-1]=="joint" and (area/"runs"/group(k)/"J/best/primary.json").is_file():
            completed_attempts.add(k)
    def endpoint(k):
        arm="A" if k[-1]=="window" else ("J" if k[-1] in ("joint","decision") else k[-1])
        return OUT/"runs"/group(k)/arm/"endpoint.json"
    def is_done(k):
        return endpoint(k).is_file() and (k[-1] not in ("A","window") or endpoint(k[:-1]+("AB",)).is_file())
    def ram(k):
        n=k[0]
        return (5.8 if n==16 else 2.6 if n==8 else 1.3) if k[-1] in ("decision","joint","A","window") else (6.8 if n==16 else 2.8)
    def available():
        free=psutil.virtual_memory().available/1024**3
        for k,p in active.items():
            try:
                free-=max(0.,ram(k)-p.memory_info().rss/1024**3)
            except psutil.NoSuchProcess:
                continue
        return free
    while True:
        for base in (area/"windows").glob("*"):
            afinal,bfinal=base/"A/endpoint.json",base/"AB/endpoint.json"
            if not bfinal.is_file():
                continue
            rec=read(afinal)
            spec=read(OUT/"inputs"/rec["case"]/"input.json")
            k=(spec["n"],spec["H"],rec["seed"],"A")
            if k[:2] not in ACTIVE_CASES:
                continue
            dst=endpoint(k)
            if dst.exists() and sha(dst)!=sha(afinal):
                continue
            assert read(bfinal)["parent"]==sha(afinal)
            if not dst.exists():
                for other,p in list(active.items()):
                    if other==k and p.is_running() and identify(p)==k:
                        p.terminate()
                        p.wait(timeout=20)
                        del active[other]
                if dst.exists() and sha(dst)!=sha(afinal):
                    continue
                save(dst,rec)
            if not endpoint(k[:3]+("AB",)).exists():
                save(endpoint(k[:3]+("AB",)),read(bfinal))
        for k,p in list(active.items()):
            if not p.is_running():
                del active[k]
                completed_attempts.add(k)
                if not is_done(k) and not (area/("decision" if k[-1]=="decision" else "runs")/group(k)/"J/best/primary.json").is_file():
                    if k[-1] in ("A","B","J"):
                        failed[str(k)]="worker exited before a verified endpoint"
        for sub in ("runs","decision"):
            for file in (area/sub).glob("*/*/endpoint.json"):
                r=read(file)
                k=(int(r["case"].split("_")[1][1:]),int(r["case"].split("_")[2][1:]),r["seed"],r["arm"])
                if k[:2] not in ACTIVE_CASES:
                    continue
                dst=endpoint(k)
                if dst.exists():
                    continue
                data=OUT/r["path"]
                spec=read(OUT/"inputs"/r["case"]/"input.json")
                assert sha(data/"schedule.json")==r["schedule_sha256"] and sha(data/"assignment.json.gz")==r["assignment_sha256"]
                d=read(data/"schedule.json")
                assert r["start"]==spec["assignment_sha256"] and d["config"]==spec["config"] and validate(d)["valid"]
                assert product.product_metrics(d)==r["metrics"] and r["actual_gap"]<=.1+1e-9
                # Retire only duplicate searches for this already certified cell.
                for other,p in list(active.items()):
                    if other[:3]==k[:3] and endpoint(other)==dst:
                        if identify(p)==other:
                            p.terminate()
                            p.wait(timeout=20)
                        del active[other]
                save(dst,r)
        # A projection can finish after a native solver reaches its gap first.
        for k,p in list(active.items()):
            if k[-1] in ("decision","joint","window") and is_done(k):
                if identify(p)==k:
                    p.terminate()
                    p.wait(timeout=20)
                del active[k]
        # Give pending small decision proofs capacity alongside longer searches.
        keys.sort(key=lambda k:(0 if k[-1]=="decision" and k[0]==4 else 1,k[2],k[0]))
        for k in keys:
            if len(active)>=8:
                break
            if is_done(k) or k in active or k in completed_attempts:
                continue
            n,h,s,mode=k
            if mode=="window" and (n==4 or sum(t[-1]=="window" for t in active)>=1):
                continue
            if mode=="B" and n<16:
                continue
            if mode=="J" and k[:3]+("decision",) not in completed_attempts:
                continue
            if mode=="joint" and str(k[:3]+("J",)) not in failed:
                continue
            if mode=="A" and sum(t[-1]=="A" for t in active)>=3:
                continue
            if mode=="decision" and sum(t[-1]=="decision" for t in active)>=3:
                continue
            if available()<ram(k)+2.:
                continue
            args=[CP,"-B","-u","-X","utf8",str(HERE/"joint.py"),str(n),str(h),str(s),"--decision"] if mode=="decision" else [
                  CP if mode=="A" else SCIP,"-B","-u","-X","utf8",str(HERE.parent/"worker.py"),str(n),str(h),str(s),mode]
            if mode=="window":
                args=[CP,"-B","-u","-X","utf8",str(HERE/"window.py"),str(n),str(h),str(s)]
            elif mode=="joint":
                args=[CP,"-B","-u","-X","utf8",str(HERE/"joint.py"),str(n),str(h),str(s)]
            with (OUT/"logs"/f"portfolio-{group(k)}-{mode}-{time.time_ns()}.log").open("w",encoding="utf8") as stream:
                active[k]=psutil.Popen(args,cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT)
        num=sum(1 for n,h in ACTIVE_CASES for _ in (OUT/"runs").glob(f"{case_id(n,h)}__s*/*/endpoint.json"))
        if num!=count:
            count=refresh(ACTIVE_CASES)
        state=dict(at=datetime.now().astimezone().isoformat(timespec="seconds"),pid=os.getpid(),verified=count,
                   expected=total,active={str(k):p.pid for k,p in active.items()},failures=failed,
                   dedicated_ablation16=False,elapsed_seconds=time.monotonic()-start,
                   state="completed" if count==total else ("running" if active else "incomplete"))
        save(OUT/"progress.json",state)
        print(state["at"],f"{count}/{total} verified | {len(active)} active | {len(failed)} failed attempts | ETA pending remaining bounds",flush=True)
        if count==total or not active:
            break
        time.sleep(8)


if __name__=="__main__":
    main()

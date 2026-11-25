"""Resume the mixed-grid controller. Register verified lower bounds and prioritize gate candidates."""
import csv
import json
import math
import msvcrt
import os
from pathlib import Path
import sys
import subprocess
import time
import psutil

from campaign import HERE,JMS,OUT,BOUND,GAPS,read,save,sha


def evidence():
    bound=[(read(BOUND)["lower"],BOUND)]
    package=JMS/"results/table3_grid16_20261125"
    for ref in sorted((OUT/"bounds").glob("*.json")):
        acceptance=read(ref)
        path=JMS/acceptance["path"]
        assert path.is_relative_to(package) and sha(path)==acceptance["sha256"]
        report=read(path)
        assert report["lower"]==acceptance["lower"]
        if path.name=="summary.json":
            assert report["full_inventory"] and report["failed"]==0 and report["count"]==report["completed"]
            proofs=sorted(path.parent.glob("p*/result.json"))
            assert len(proofs)==report["count"]==len(acceptance["partitions"])
            assert all(sha(p)==acceptance["partitions"][p.parent.name] for p in proofs)
            assert all(read(p)["lower"]>=acceptance["lower"] for p in proofs)
        else:
            assert report["status"] in ("OPTIMAL","INFEASIBLE","FEASIBLE","UNKNOWN")
        bound.append((acceptance["lower"],path))
    return max(bound,key=lambda v:v[0])


def main():
    with (OUT/"controller.lock").open("a+b") as lock:
        lock.seek(0)
        try:msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
        except OSError:
            print("Another mixed-grid supervisor owns the controller lock",flush=True)
            return
        ledger=OUT/"stream.json"
        if ledger.exists():
            state=read(ledger)
        else:
            prepared=OUT/"prepared"
            u=read(prepared/"primary.json")["metrics"]["cmax"]
            lb0=read(BOUND)["lower"]
            e=dict(path="prepared",record_sha256=sha(prepared/"primary.json"),upper=u,lower=lb0,gap=(u-lb0)/lb0,
                   lower_source=BOUND.relative_to(JMS).as_posix(),lower_sha256=sha(BOUND),trigger="SPBS initializer")
            state=dict(identity=dict(config=sha(OUT/"input.json"),source=sha(prepared/"primary.json"),seed=1,levels=GAPS),
                       events=[e],gates={a:e for a,tau in GAPS.items() if e["gap"]<=tau})
            save(ledger,state)
        assert state["identity"]["config"]==sha(OUT/"input.json")
        progress=OUT/"progress.json"
        previous=read(progress).get("elapsed_s",0) if progress.exists() else 0
        clock=time.monotonic()
        active={}
        campaign=HERE/"campaign.py"
        for p in psutil.process_iter(["cmdline"]):
            argv=p.info["cmdline"] or []
            if len(argv)>=3 and os.path.normcase(argv[-3])==os.path.normcase(str(campaign)):
                active[argv[-2],argv[-1]]=p
        failed={}
        def launch(job):
            kind,key=job
            log=OUT/(kind+"_"+key.replace("/","_")+".log")
            with log.open("a",encoding="utf8") as f:
                p=subprocess.Popen([sys.executable,"-B","-u","-X","utf8",str(campaign),kind,key],stdout=f,stderr=subprocess.STDOUT)
            active[job]=psutil.Process(p.pid)
        def register(upper,lb,path,proof,trigger):
            record=path/"primary.json"
            data=read(record)
            assert data["rows"]==1109436 and data["replay"]["valid"] and abs(data["metrics"]["cmax"]-upper)<1e-6
            assert data["assignment_sha256"]==sha(path/"assignment.json.gz") and data["schedule_sha256"]==sha(path/"schedule.json")
            e=dict(path=path.relative_to(OUT).as_posix(),record_sha256=sha(record),upper=upper,lower=lb,
                   gap=(upper-lb)/lb,lower_source=proof.relative_to(JMS).as_posix(),lower_sha256=sha(proof),trigger=trigger)
            assert upper+1e-6>=lb
            state["events"].append(e)
            for a,tau in GAPS.items():
                if a not in state["gates"] and e["gap"]<=tau+1e-10:state["gates"][a]=e
            save(ledger,state)
        while True:
            for job,p in list(active.items()):
                if p.is_running():continue
                del active[job]
                cat,key=job
                if cat=="native":endpoint=OUT/"witnesses"/key.replace("/","__").removesuffix(".json")/"primary.json"
                elif cat=="B":endpoint=OUT/"grid"/Path(*key.split("__"))/"result.json"
                else:continue
                if not endpoint.exists():failed["/".join(job)]="Worker exited without validated endpoint"
            lb,proof=evidence()
            best=state["events"][-1]
            if lb>best["lower"]:register(best["upper"],lb,OUT/best["path"],proof,"improved global lower bound")
            native=sorted((OUT/"witnesses").glob("*/primary.json"),key=lambda p:p.stat().st_mtime_ns)
            for record in native:
                data=read(record)
                upper=data["metrics"]["cmax"]
                if upper<state["events"][-1]["upper"]-1e-6:register(upper,lb,record.parent,proof,"new native feasible upper bound")
            best=state["events"][-1]
            unfilled=[a for a in GAPS if a not in state["gates"]]
            candidates=sorted((p for p in (OUT/"proposals").glob("*/candidate_*.json") if not p.stem.endswith("_values")),key=lambda p:p.stat().st_mtime_ns)
            pending=[]
            if unfilled:
                ceiling=lb*(1+max(GAPS[a] for a in unfilled))
                eligible=[p for p in candidates if float(p.stem[10:])<=ceiling+1e-8]
                if eligible:pending.append(eligible[0])
            if candidates:
                smallest=min(candidates,key=lambda p:float(p.stem[10:]))
                if float(smallest.stem[10:])<best["upper"]:pending.append(smallest)
            for src in pending:
                key=src.relative_to(OUT).as_posix()
                endpoint=OUT/"witnesses"/key.replace("/","__").removesuffix(".json")/"primary.json"
                if not endpoint.exists() and not any(k[0] in ("native","B") for k in active) and ("native/"+key) not in failed:
                    launch(("native",key))
            rows=[]
            for a,event in state["gates"].items():
                for b,tau in GAPS.items():
                    work=OUT/"grid"/a/b
                    endpoint=work/"result.json"
                    key=a+"__"+b
                    if not endpoint.exists():
                        if not any(k[0] in ("B","native") for k in active) and "B/"+key not in failed:launch(("B",key))
                        continue
                    r=read(endpoint)
                    assert r["eligible"] and r["replay"]["valid"] and r["target_gap"]==tau and r["record"]["gap"]<=tau+1e-8
                    assert all(sha(work/f)==v for f,v in r["files"].items())
                    assert r["parents"][0]["assignment_sha256"]==sha(OUT/event["path"]/"assignment.json.gz")
                    m=r["measured"]
                    rows.append(dict(case="D_n16_H10_mixed_dual",recipe="mixed",gA=a,gB=b,f_A=m["cmax"],f_B=m["secondary"],mean=m["mean_residence"],spread=m["residence_range"],E=m["clean_deficit"],A_lower=event["lower"],A_upper=event["upper"],A_gap=event["gap"],B_lower=r["record"]["lower"],B_upper=r["record"]["upper"],B_gap=r["record"]["gap"],source=work.relative_to(JMS).as_posix(),schedule_sha256=sha(work/"schedule.json"),assignment_sha256=sha(work/"assignment.json.gz"),A_proof=(OUT/event["path"]/"primary.json").relative_to(JMS).as_posix(),A_bound=event["lower_source"]))
            if rows:
                tmp=OUT/"threshold_cells.tmp"
                with tmp.open("w",newline="",encoding="utf8") as f:
                    writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
                os.replace(tmp,OUT/"threshold_cells.csv")
            elapsed=previous+time.monotonic()-clock
            stop=len(rows)==9
            row=dict(expected=9,completed=len(rows),failed=failed,elapsed_s=elapsed,upper=best["upper"],lower=lb,
                gates=list(state["gates"]),active={"/".join(k):p.pid for k,p in active.items()},
                estimated_remaining_s=0 if stop else None,estimated_total_s=elapsed if stop else None,
                basis="The remaining global primary certificate has no comparable solved 16-wafer case. Native gate cells are resumed in a one-worker queue. Checked unbounded primary progress is retained while awaiting a stronger certificate or schedule.",
                recovery="Adopt working native/proposal processes, retain every verified event and earliest handoff, and check parent and final file hashes. Periodically recheck newly published physical witnesses and trusted bounds.")
            save(progress,row)
            print(f"16-mixed {len(rows)}/9; failures {len(failed)}; bounds [{lb},{best['upper']}]; elapsed {elapsed:.0f}s; grid ETA {'0s' if stop else 'unknown until a tighter global bound or incumbent'}",flush=True)
            if stop:break
            time.sleep(5)

if __name__=="__main__":main()

"""Process each newly attained A gate then run or reuse fixed-structure B endpoints."""
import csv
import msvcrt
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import psutil
from common16 import HERE,JMS,OUT,LEVELS,save,load,sha

def main(mode):
    root=OUT/mode
    folder=root/"retiming"
    folder.mkdir(parents=True,exist_ok=True)
    lock=(folder/"controller.lock").open("a+b")
    lock.seek(0)
    try:msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
    except OSError:return
    first=folder/"start.json"
    if not first.exists():save(first,dict(stamp=time.time()))
    started=load(first)["stamp"]
    while True:
        # One native model rebuild at a time within this instance.
        gating=[sys.executable,"-B","-u","-X","utf8",str(HERE/"gate16.py"),mode]
        for proc in psutil.process_iter(["cmdline"]):
            cmd=proc.info["cmdline"] or []
            if cmd[-2:]==gating[-2:]:proc.wait()
        subprocess.run(gating,check=True)
        total=[];pending=[]
        for a in LEVELS:
            parent=root/a/"A/primary.json"
            if not parent.exists():continue
            pr=load(parent)
            for b in LEVELS:
                endpoint=root/a/b/"B"
                result=endpoint/"result.json"
                if not result.exists():
                    for old in total:
                        if old["gB"]!=b:continue
                        older=root/old["gA"]/b/"B"
                        olderpr=load(root/old["gA"]/"A/primary.json")
                        if olderpr["schedule_sha256"]!=pr["schedule_sha256"] or olderpr["assignment_sha256"]!=pr["assignment_sha256"]:continue
                        endpoint.mkdir(parents=True,exist_ok=True)
                        for name in ["schedule.json","assignment.json.gz"]:shutil.copyfile(older/name,endpoint/name)
                        save(endpoint/"reuse.json",dict(reason="Identical seed, target gap, assignment, schedule and native solver",source=(older/"result.json").relative_to(JMS).as_posix(),source_sha256=sha(older/"result.json")))
                        shutil.copyfile(older/"result.json",result)
                        break
                if not result.exists():pending.append((a,b));continue
                r=load(result)
                assert r["eligible"] and r["replay"]["valid"] and r["target_gap"]==LEVELS[b] and r["seed"]==1
                assert r["parents"][0]["assignment_sha256"]==pr["assignment_sha256"] and r["parents"][0]["schedule_sha256"]==pr["schedule_sha256"]
                assert all(sha(endpoint/k)==h for k,h in r["files"].items())
                doc=load(endpoint/"schedule.json")
                assert abs(r["measured"]["cmax"]-max(w["loan_end"] for w in doc["jobs"] if w["product"]))<1e-6
                total.append(dict(case=f"D_n16_pure_{mode}",recipe=mode,gA=a,gB=b,f_A=r["measured"]["cmax"],f_B=r["measured"]["secondary"],
                    mean=r["measured"]["mean_residence"],spread=r["measured"]["residence_range"],E=r["measured"]["clean_deficit"],
                    A_upper=pr["upper"],A_lower=pr["lower"],A_gap=pr["gap"],B_upper=r["record"]["upper"],B_lower=r["record"]["lower"],B_gap=r["record"]["gap"],
                    A_proof=parent.relative_to(JMS).as_posix(),B_proof=result.relative_to(JMS).as_posix(),schedule=(endpoint/"schedule.json").relative_to(JMS).as_posix(),schedule_sha256=sha(endpoint/"schedule.json")))
        if total:
            tmp=root/"threshold_cells.tmp"
            with tmp.open("w",newline="",encoding="utf8") as handle:
                writer=csv.DictWriter(handle,fieldnames=list(total[0]));writer.writeheader();writer.writerows(total)
            os.replace(tmp,root/"threshold_cells.csv")
        elapsed=time.time()-started
        eta=(9-len(total))*50
        status=dict(completed=len(total),total=9,failed=0,elapsed_s=elapsed,estimated_remaining_s=eta,
            estimated_total_s=elapsed+eta,qualified_handoffs=load(root/"gates_progress.json"),basis="One native B at a time; 8-wafer observations and 16-wafer row count; identical-source cells skip.")
        save(folder/"progress.json",status)
        print(f"{mode} fixed B {len(total)}/9, elapsed {elapsed:.0f}s, estimated total {elapsed+eta:.0f}s, ETA {eta}s",flush=True)
        if len(total)==9:return
        if not pending:
            time.sleep(6)
            continue
        a,b=pending[0]
        cmd=[sys.executable,"-B","-u","-X","utf8",str(HERE/"retime16.py"),mode,a,b]
        for proc in psutil.process_iter(["cmdline"]):
            args=proc.info["cmdline"] or []
            if args[-4:]==cmd[-4:]:
                proc.wait()
        if not (root/a/b/"B/result.json").exists():
            with (folder/f"{a}_{b}.log").open("a",encoding="utf8") as log:
                p=subprocess.Popen(cmd,stdout=log,stderr=subprocess.STDOUT)
            while p.poll() is None:
                status["active"]=dict(a=a,b=b,pid=p.pid)
                status["elapsed_s"]=time.time()-started
                spent=status["elapsed_s"]-elapsed
                status["estimated_remaining_s"]=max(0,eta-spent)
                status["estimated_total_s"]=status["elapsed_s"]+status["estimated_remaining_s"]
                save(folder/"progress.json",status)
                print(f"{mode} {a}/{b} | {len(total)}/9, elapsed {status['elapsed_s']:.0f}s, estimated total {status['estimated_total_s']:.0f}s, ETA {status['estimated_remaining_s']:.0f}s",flush=True)
                time.sleep(4)
            if p.returncode:raise RuntimeError(str(folder/f"{a}_{b}.log"))

if __name__=="__main__":main(sys.argv[1])

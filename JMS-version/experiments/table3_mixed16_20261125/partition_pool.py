"""Consume complete archive partitions and reserve one CPU slot for native grid certification."""
import msvcrt
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import psutil
from campaign import OUT,HERE,JMS,read,save,sha
sys.path.insert(0,str(HERE.parent/"table3_grid16_20261125"))
from decode_projection import decode


def main():
    base=OUT/"partition_pool"
    base.mkdir(exist_ok=True)
    source=JMS/"results/table3_grid16_20261125/partitions/mixed_810"
    localpy=HERE/"lift_projection.py"
    with (base/"controller.lock").open("a+b") as lock:
        lock.seek(0)
        try:msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
        except OSError:return
        status_path=base/"progress.json"
        previous=read(status_path).get("elapsed_s",0) if status_path.exists() else 0
        start=time.monotonic()
        while True:
            jobs=[]
            for path in sorted(source.glob("p*/projection.json")):
                label=path.parent.name
                certificate=path.with_name("result.json")
                if not certificate.exists() or read(certificate)["upper"] is None:continue
                folder=base/label
                folder.mkdir(exist_ok=True)
                frozen=folder/"projection.json"
                if not frozen.exists():shutil.copyfile(path,frozen)
                hint=folder/"hint.json"
                if not hint.exists():
                    save(hint,decode(frozen,OUT/"prepared/schedule.json"))
                    save(folder/"source.json",dict(archive=path.relative_to(JMS).as_posix(),sha256=sha(frozen),
                         certificate_sha256=sha(certificate),native_seed_sha256=sha(OUT/"prepared/schedule.json")))
                jobs.append((f"part810_{label}",hint,"ordered"))
            # Expose more flexible ingress timing on all sufficiently good native skeletons.
            for key,hint,policy in list(jobs):
                best=OUT/"proposals"/key/"best.json"
                if best.exists() and read(best)["upper"]<845:jobs.append((key+"_al",hint,"al"))
            active=set()
            occupied=0
            for p in psutil.process_iter(["cmdline"]):
                argv=p.info["cmdline"] or []
                if len(argv)>=4 and os.path.normcase(argv[-4])==os.path.normcase(str(localpy)):
                    occupied+=1;active.add(argv[-2])
                elif any(os.path.normcase(str(HERE/f)) in map(os.path.normcase,argv) for f in ("guided.py","local.py")):occupied+=1
            done=0;remaining=0
            for key,hint,policy in jobs:
                folder=OUT/"proposals"/key
                if (folder/"result.json").exists():done+=1;continue
                used=read(folder/"checkpoint.json")["elapsed"] if (folder/"checkpoint.json").exists() else 0
                remaining+=max(0,180-used)
                if key in active or occupied>=3:continue
                with (base/(key+".log")).open("a",encoding="utf8") as log:
                    subprocess.Popen([sys.executable,"-B","-u","-X","utf8",str(localpy),str(hint),key,policy],stdout=log,stderr=subprocess.STDOUT)
                active.add(key);occupied+=1
            wall=previous+time.monotonic()-start
            save(status_path,dict(expected=len(jobs),completed=done,failed=0,elapsed_s=wall,
                estimated_remaining_s=remaining/3,estimated_total_s=wall+remaining/3,active=sorted(active),
                basis="Each frozen skeleton has up to 180 cumulative native CP seconds. Three search slots share capacity and a fourth slot is reserved for native verification or B."))
            print(f"Frozen projection candidates {done}/{len(jobs)}, failed 0; elapsed {wall:.0f}s; remaining search budget ETA {remaining/3:.0f}s",flush=True)
            if (len(jobs)>0 and done==len(jobs)) or len(read(OUT/"stream.json")["gates"])==3:return
            time.sleep(5)

if __name__=="__main__":main()

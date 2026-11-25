"""Park only quota-exclusive comparisons after preserving their cumulative checkpoints."""
from datetime import datetime
import shutil
import time

import psutil

from jobs import HERE, OUT, folder, read, sha, write


def park(key):
    worker=str(HERE/"jobs.py")
    processes=[p for p in psutil.process_iter(["cmdline"]) if (args:=p.info["cmdline"])
               and worker in args and args[-1]==key]
    if not processes:
        return
    assert len(processes)==1
    p=processes[0]
    dest=folder(key)
    for attempt in range(150):
        p.suspend()
        try:
            progress=read(dest/"progress.json")
            pulse=read(dest/"clock.json")
            newest=max((dest/f).stat().st_mtime for f in ("progress.json","clock.json"))
            recent=time.time()-newest<1.4 and abs(progress["charged_s"]-pulse["charged_s"])<3.5
            if not recent and attempt<149:
                continue
            assert pulse["attempt"]==progress["attempt"] and progress["stage"]=="A"
            folder_out=OUT/"paused"/key
            folder_out.mkdir(parents=True,exist_ok=True)
            files=[]
            for name in ("progress.json","clock.json","A_objectives.jsonl","A_cut_times.jsonl"):
                if (dest/name).exists():
                    shutil.copy2(dest/name,folder_out/name)
                    files.append(name)
            write(folder_out/"checkpoint.json",dict(job=key,pid=p.pid,argv=p.cmdline(),
                  at=datetime.now().astimezone().isoformat(),charged_s=max(pulse["charged_s"],progress["charged_s"]),
                  last_reported_cuts=progress["calls"],source=progress["key"],incumbent_sha256=progress["best"]["digest"],
                  files={f:sha(folder_out/f) for f in files},recovery="resume the saved elapsed budget and incumbent with a new native search tree"))
            p.terminate()
            p.wait(timeout=10)
            return
        finally:
            if p.is_running():
                p.resume()
                time.sleep(.05)


if __name__=="__main__":
    scope=read(OUT/"run_scope.json")
    for key in ("t5_1_no_spbs","t5_2_no_spbs"):
        assert key not in scope["allow"]
        park(key)

"""Recover H=3 stage-A witnesses with fixed chamber batches and shared-resource time windows."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import functools
from hashlib import sha256
import inspect
import msvcrt
from pathlib import Path
import threading
import time
from types import SimpleNamespace
from unittest.mock import patch

import primary3
import blocks as base
from grippers import attach_hands

OUT=base.OUT/"H3"/"window_search"
TASKS=[("full",1243,1),("core",1243,2),("full",1260,3),("full",1230,4)]
BUDGET=100
CONCURRENCY=2


def windows(mode,seed,cap,model,variables,pieces,end):
    all_align=[]
    all_routes={}
    for index,(p,off) in enumerate(pieces):
        for route_i,route in p.routes.items():
            i,j=divmod(route_i,2)
            home=p.members[i][j]
            if not home.startswith("LP"):continue
            mapped={r:variables[off+x] for r,x in route.items()}
            all_routes[home]=mapped
            all_align.append((index,i,j,mapped["al_put"]))
        # Augment gross chemistry windows with the residence and handling constraints in the physical model.
        for q,(x,_,_) in enumerate(p.cycles):
            if index==0:lo,hi=104+94*q,136+100*q
            elif index==1:lo,hi=382,cap-811
            elif index==2:lo,hi=890+94*q,cap-318+94*q
            else:lo,hi=(270,585) if index==3 else (510,830)
            model.add_linear_constraint(variables[off+x],lo,hi)
        for i,group in enumerate(p.members):
            if not all(s.startswith("LP") for s in group):continue
            wa,wb=[all_routes[x] for x in group]
            model.add(wa["al_put"]<=wb["al_put"])
            if index in (0,2):
                for activity in ("origin_pick","destination_put","lower_pick","origin_put"):
                    model.add(wa[activity]==wb[activity])
    # The first four dual-exposure wafers reserve the first four aligner services.
    # The last four are prepared before the second exposure chain starts.
    def priority(row):
        k,i,j,_=row
        if k==0:return 0,i,j
        if k==2:return 3,i,j
        return k-2,i,j
    seq=[r[-1] for r in sorted(all_align,key=priority)]
    for i,j in zip(seq,seq[1:]):model.add(j>=i+28)


def decode(cfg,blocks,times):
    pieces=[];cursor=0
    for p in blocks:
        pieces.append((p,cursor));cursor+=len(p.actions)
    # The second three-pass dual chain reaches H again after all production.
    # Its trailing cleaning changes equipment release only. Reuse an audited
    # empty-tool cleaning and release all preceding slots before it starts.
    cleaning=base.read(base.OUT/"H3/free/block_6.json")
    assert cleaning["signature"][1:4]==[3,"clean",2]
    terminal=base.block(cfg,"clean",2,cleaning["signature"][4])
    last=max(times[off+k]+a.duration for p,off in pieces for k,a in enumerate(p.actions))
    times=list(times)+[last+100+t for t in cleaning["times"]]
    pieces.append((terminal,cursor))
    def normalize(c,data):
        doc=base.normalize_schedule(c,data)
        if not attach_hands(doc):raise ValueError("Invalid hand witness")
        return doc
    with patch("timing.normalize_schedule",normalize):
        return base.BatchTiming.schedule(SimpleNamespace(cfg=cfg,blocks=pieces),times)


def run_one(cfg,task):
    mode,cap,seed=task
    folder=OUT/f"{mode}_{cap}_{seed}"
    folder.mkdir(parents=True,exist_ok=True)
    state_path=folder/"progress.json"
    formulation=sha256(inspect.getsource(windows).encode()).hexdigest()
    ident=[mode,cap,seed,formulation,base.sha(Path(base.__file__))]
    state=base.read(state_path) if state_path.exists() else dict(identity=ident,elapsed_s=0,best=None)
    earlier="03a4b31521882ed767a656eb1c084ddb0ec0570fba2dab6bfc20a852d2a22b5c"
    if state["identity"][3]==earlier and formulation=="5b8f6b890a7069565db99c210b23d87f7aed8d35bee30b60f9b7e7eb8da8443d":
        state["identity"][3]=formulation
    assert state["identity"]==ident
    if (folder/"done.json").exists():return
    start=time.monotonic();old=state["elapsed_s"]
    def record():
        state["elapsed_s"]=old+time.monotonic()-start
        primary3.write(state_path,state)
    stop=threading.Event()
    def update():
        while not stop.wait(3):record()
    th=threading.Thread(target=update,daemon=True);th.start()
    best=folder/"candidate.json"
    def track(ts,score):
        if state["best"] is None or score<state["best"]:
            state["best"]=score
            primary3.write(best,dict(times=ts,score=score))
            record();print(f"{folder.name} candidate: {score:g}s",flush=True)
    pats=primary3.plans(cfg,0)
    if mode=="core":pats=pats[:3]
    try:
        base.time_blocks(cfg,pats,scale=1,ideal=False,seed=seed,budget=max(.01,BUDGET-old),
                         incumbent=min(cap,state["best"]) if state["best"] else cap,
                         hint_times=base.read(best)["times"] if best.exists() else None,
                         specialize=functools.partial(windows,mode,seed,cap),workers=3,progress=track)
        state["status"]="feasible"
    except RuntimeError as exc:
        state["status"]=str(exc).split(" for ")[0]
    finally:
        stop.set();th.join();record()
    primary3.write(folder/"done.json",state)


def run():
    OUT.mkdir(parents=True,exist_ok=True)
    with (OUT/"run.lock").open("a+b") as file:
        try:msvcrt.locking(file.fileno(),msvcrt.LK_NBLCK,1)
        except OSError:
            print("Run already active");return
        cfg=replace(base.configuration(),cleaning_interval=3)
        start=time.monotonic()
        with ThreadPoolExecutor(max_workers=CONCURRENCY) as ex:
            work=[ex.submit(run_one,cfg,task) for task in TASKS]
            while True:
                done=[f for f in work if f.done()]
                secs=0
                for mode,cap,seed in TASKS:
                    folder=OUT/f"{mode}_{cap}_{seed}"
                    if (folder/"done.json").exists():continue
                    elapsed=base.read(folder/"progress.json")["elapsed_s"] if (folder/"progress.json").exists() else 0
                    secs+=max(0,BUDGET-elapsed)
                remaining=secs/CONCURRENCY
                current=dict(done=len(done),expected=len(work),failed=sum(bool(f.exception()) for f in done),
                             elapsed_s=time.monotonic()-start,remaining_s=remaining,
                             estimated_total_s=time.monotonic()-start+remaining,concurrency=CONCURRENCY,threads_per_worker=3,
                             basis="remaining cumulative CP search budgets divided by worker concurrency")
                primary3.write(OUT/"status.json",current)
                print(f"{len(done)}/{len(work)}, failed {current['failed']}, elapsed {current['elapsed_s']:.0f}s, "
                      f"estimated total {current['estimated_total_s']:.0f}s, remaining {remaining:.0f}s",flush=True)
                for mode,cap,seed in TASKS:
                    folder=OUT/f"{mode}_{cap}_{seed}"
                    if mode!="full" or not (folder/"candidate.json").exists():continue
                    r=base.read(folder/"candidate.json");native=folder/f"native_{r['score']:g}"
                    if (native/"primary.json").exists():continue
                    doc=decode(cfg,primary3.plans(cfg,0),r["times"])
                    base.validate_native(cfg,doc,native,dict(search=folder.name,script_sha256=base.sha(Path(__file__))))
                    print("Full-model validated:",doc["cmax"],native,flush=True)
                if len(done)==len(work):break
                time.sleep(4)
            for f in work:f.result()


if __name__=="__main__":run()

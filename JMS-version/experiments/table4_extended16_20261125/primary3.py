"""Find a native H=3 stage-A handoff with the full paired experiment configuration."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import json
import msvcrt
import os
from pathlib import Path
import threading
import time
from types import SimpleNamespace

import blocks as base

OUT = base.OUT / "H3" / "primary_search"
LOCK = threading.Lock()
WALL_BUDGET = 100
THREADS = 2


def write(path, data):
    with LOCK:
        base.write(path, data)


def plans(cfg, variant):
    full, double = [job["wafers"] for job in cfg.pjobs]
    ds = [f"D{i}" for i in range(1, 9)]
    def chain(group, head, tail):
        return base.block(cfg, "2x2", 2, [head, group[:2], group[2:], tail])
    single = [base.block(cfg, "4x1", 3, [full[i:i+2], full[i+2:i+4]]) for i in (0, 4)]
    if variant & 2:
        single = [base.block(cfg, "4x1", 3, [full[i+2:i+4], full[i:i+2]]) for i in (0, 4)]
    clean = base.block(cfg, "clean", 2, [ds[4:6], ds[6:8]])
    early = chain(double[:4], ds[:2], ds[2:4])
    late = chain(double[4:], ds[:2], ds[2:4])
    return [early, clean, late, *single]


def attempt(cfg, task, target):
    seed, variant, cap = task
    folder = OUT / f"s{seed}_v{variant}_c{cap}"
    folder.mkdir(parents=True, exist_ok=True)
    identity = dict(seed=seed, variant=variant, cap=cap,
                    source=base.sha(Path(__file__)), timing_source=base.sha(Path(base.__file__)))
    if (folder/"done.json").exists():
        assert base.read(folder/"done.json")["identity"] == identity
        return
    clock = folder/"progress.json"
    state = base.read(clock) if clock.exists() else dict(identity=identity, wall=0, best=None)
    assert state["identity"] == identity
    if state["best"] is not None and state["best"] <= target:
        write(folder/"done.json", state)
        return
    start = time.monotonic()
    previous = state["wall"]
    result = folder/"candidate.json"
    old = base.read(result) if result.exists() else None
    def note():
        state["wall"] = previous + time.monotonic() - start
        write(clock,state)
    stop = threading.Event()
    def beat():
        while not stop.wait(3):
            note()
    def capture(times, score):
        if state["best"] is None or score < state["best"]:
            state["best"] = score
            write(result, dict(times=times, score=score))
            note()
            print(f"{folder.name}: candidate {score:g} s", flush=True)
    keeper=threading.Thread(target=beat,daemon=True)
    keeper.start()
    try:
        base.time_blocks(cfg, plans(cfg,variant), scale=1, ideal=False, seed=seed,
                         budget=max(.01, WALL_BUDGET - previous),
                         hint_times=old["times"] if old else None,
                         incumbent=min(cap, old["score"]) if old else cap, progress=capture)
    except RuntimeError as error:
        state["solver_termination"]=str(error).split(" for ")[0]
    finally:
        stop.set()
        keeper.join()
        note()
    write(folder/"done.json",state)


def export(cfg, folder, variant):
    row=base.read(folder/"candidate.json")
    times=row["times"]
    pieces=[];offset=0
    for p in plans(cfg,variant):
        pieces.append((p,offset));offset += len(p.actions)
    doc=base.BatchTiming.schedule(SimpleNamespace(cfg=cfg,blocks=pieces),times)
    assert abs(doc["cmax"] - row["score"])<1e-6
    return base.validate_native(cfg,doc,OUT/"native",dict(candidate_source=str(folder),budget_s=WALL_BUDGET))


def run():
    OUT.mkdir(parents=True,exist_ok=True)
    with (OUT/"run.lock").open("a+b") as file:
        try:
            msvcrt.locking(file.fileno(),msvcrt.LK_NBLCK,1)
        except OSError:
            print("An existing foreground controller owns this run.");return
        cfg=replace(base.configuration(),cleaning_interval=3)
        bound=base.read(base.OUT/"H3_clean_bound.json")["lower"]
        tasks=[(1,0,1230),(2,2,1230),(3,0,1270),(4,2,1270)]
        start=time.monotonic()
        with ThreadPoolExecutor(max_workers=THREADS) as ex:
            work={ex.submit(attempt,cfg,task,1.01*bound):task for task in tasks}
            while True:
                dones=[f for f in work if f.done()]
                fail=sum(bool(f.exception()) for f in dones)
                used=sum(base.read(p)["wall"] for p in OUT.glob("s*/progress.json"))
                remaining=max(0,(WALL_BUDGET*len(tasks)-used)/THREADS)
                current=dict(done=len(dones),expected=len(tasks),failed=fail,elapsed_s=time.monotonic()-start,
                             solver_elapsed_cumulative_s=used,remaining_s=remaining,
                             estimated_total_s=time.monotonic()-start+remaining,
                             estimate_basis="Remaining fixed 100s CP searches divided by two one-thread workers")
                write(OUT/"status.json",current)
                print(f"{len(dones)}/{len(tasks)}, failed {fail}, elapsed {current['elapsed_s']:.0f}s, "
                      f"estimated total {current['estimated_total_s']:.0f}s, remaining {remaining:.0f}s",flush=True)
                if len(dones)==len(work):break
                time.sleep(5)
            for f in work:f.result()
        scores=[]
        for seed,v,cap in tasks:
            folder=OUT/f"s{seed}_v{v}_c{cap}"
            if (folder/"candidate.json").exists():
                scores.append((base.read(folder/"candidate.json")["score"],folder,v))
        if scores:
            score,folder,v=min(scores)
            if not (OUT/"native/primary.json").exists():
                f,_=export(cfg,folder,v)
                print(f,flush=True)
            print(f"A: {score} vs {bound}; relative gap {(score-bound)/bound:.4%}",flush=True)


if __name__ == "__main__":
    run()

"""Validate each physical B cell once its frozen, certified A handoff exists."""
import argparse
import csv
import itertools
import msvcrt
import os
from pathlib import Path
import subprocess
import sys
import time
import traceback

from secondary import HERE, OUT, PRIMARY, worker
from design import EXTENSIONS, LEVELS, ROOT, TUNING, pick, read, rel, save, sha
import psutil


def location(c,arm,a,b):
    return OUT/'runs'/c/arm/('B_'+a+'_'+b)


def inventory():
    files=[HERE/'certify.py',HERE/'secondary.py',PRIMARY/'protocol.json',PRIMARY/'contract.json']
    return {rel(p):sha(p) for p in files}


def summary():
    grid={}
    tasks=[(c,'full',a,b) for c,a,b in itertools.product(TUNING,LEVELS,LEVELS)]
    for c,arm,a,b in tasks:
        path=location(c,arm,a,b)/'evidence.json'
        if path.is_file(): grid[c,a,b]=read(path)
    choice=pick(grid)
    if choice:
        tasks += [(c,arm,*choice) for c in TUNING for arm in ('no_spbs','no_rerank')]
        tasks += [(c,'full',*choice) for c in EXTENSIONS]
    rows=[]
    links=[]
    pending=[]
    for task in tasks:
        c,arm,a,b=task
        p=location(*task)/'evidence.json'
        pa=PRIMARY/'runs'/c/arm/('A_'+a)/'evidence.json'
        if not p.exists():
            if pa.exists(): pending.append(task)
            continue
        eb,ea=read(p),read(pa)
        if not(eb['valid'] and ea['valid'] and eb['gate']['accepted'] and ea['gate']['accepted'] and eb['primary_evidence_sha256']==sha(pa)):
            raise ValueError('Unverified or changed handoff')
        rows.append(dict(case=c,arm=arm,target_A_pct=100*LEVELS[a],target_B_pct=100*LEVELS[b],
             achieved_A_pct=100*ea['gate']['recomputed_gap'],achieved_B_pct=100*eb['gate']['recomputed_gap'],
             lower_A=ea['record']['dual_bound'],upper_A=ea['record']['primal_bound'],
             lower_B=eb['record']['dual_bound'],upper_B=eb['record']['primal_bound'],**eb['metrics'],
             primary_seconds=ea['record']['seconds'],secondary_seconds=eb['record']['seconds'],
             primary_evidence=rel(pa),evidence=rel(p)))
        if c in TUNING and arm=='full' and (a,b)==choice:
            links.append(dict(case=c,sections=['SPBS','cut_selection'],evidence=rel(p),sha256=sha(p)))
    doc=dict(completed_cells=len(rows),planned_cells=26,grid_cells_completed=len(grid),grid_cells_planned=18,
             selected=dict(A=choice[0],B=choice[1]) if choice else None,reused_full=links,rows=rows)
    save(OUT/'report.json',doc)
    if rows:
        tmp=OUT/'results.csv.tmp'
        with tmp.open('w',encoding='utf-8-sig',newline='') as stream:
            w=csv.DictWriter(stream,fieldnames=rows[0].keys())
            w.writeheader()
            w.writerows(rows)
        try: tmp.replace(OUT/'results.csv')
        except PermissionError: pass  # JSON remains current while Excel holds an older CSV open.
    return pending,doc


def run():
    OUT.mkdir(exist_ok=True)
    with (OUT/'controller.lock').open('a+b') as lock:
        lock.seek(0)
        msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
        marker=OUT/'protocol.json'
        hashes=inventory()
        if not marker.exists():
            save(marker,dict(assets=hashes,primary_campaign=rel(PRIMARY),time_limits={'A':None,'B':None},levels=LEVELS,
                 objective='All original model rows; positive weight on timing deviations only for physically active centers of the fixed structure',
                 selection=read(PRIMARY/'protocol.json')['selection']))
        elif read(marker)['assets']!=hashes: raise ValueError('Changed physical B protocol')
        failed=set()
        while True:
            pending,doc=summary()
            if doc['completed_cells']==26: return
            print(f"Verified {doc['completed_cells']}/26 | grid {doc['grid_cells_completed']}/18 | failed {len(failed)}",flush=True)
            available=psutil.virtual_memory().available/2**30
            for task in pending:
                if task in failed: continue
                n=read(PRIMARY/'protocol.json')['cases'][task[0]]['n']
                if available<{2:3,4:5,8:7,16:10}[n]: continue
                folder=location(*task)
                attempt=folder/'attempts'/str(time.time_ns())
                attempt.mkdir(parents=True)
                cmd=[sys.executable,'-B','-X','utf8','-u',str(Path(__file__).resolve()),'--job',*task,'--attempt',str(attempt)]
                print('START',task,flush=True)
                with (attempt/'worker.log').open('wb') as stream:
                    proc=subprocess.Popen(cmd,stdout=stream,stderr=subprocess.STDOUT)
                    try: code=proc.wait()
                    finally:
                        if proc.poll() is None: proc.terminate(); proc.wait()
                if code: failed.add(task)
                break
            else:
                if failed and all(t in failed for t in pending): raise RuntimeError('See failure.json in the recorded B attempts')
                print('Waiting for a certified stage A or memory. Overall ETA unknown.',flush=True)
                time.sleep(20)


if __name__=='__main__':
    ap=argparse.ArgumentParser()
    ap.add_argument('--job',nargs=4)
    ap.add_argument('--attempt',type=Path)
    args=ap.parse_args()
    if args.job:
        try: worker(*args.job,location(*args.job),args.attempt)
        except BaseException as exc:
            save(args.attempt/'failure.json',dict(reason=str(exc),trace=traceback.format_exc()))
            raise
    else: run()

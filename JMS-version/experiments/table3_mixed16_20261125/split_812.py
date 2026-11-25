"""Cover both chamber-side assignments for three 812-s mixed partitions with the corrected four-hand outer model."""
import itertools
import json
import msvcrt
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
import psutil
from campaign import HERE,JMS,OUT,read,sha,save
sys.path.insert(0,str(HERE.parent/"table3_grid16_20261125"))
import tool_partition as tool
from ortools.sat.python import cp_model

ROOT=OUT/"tool_split_812"
KINDS=(9,17,31)
BUDGET=240


def input_for(index):
    pattern,cycles=tool.prepare("mixed",812)[index]
    first=next(k for k,mode in pattern if mode==1)
    ids=[i for i,(g,mode) in enumerate(pattern) if g==first]
    masks=["".join(map(str,bits)) for bits in itertools.product((0,1),repeat=len(ids))
           if sum(bits)<=2 and len(bits)-sum(bits)<=2]
    return pattern,cycles,ids,masks


def run(index,mask):
    d=ROOT/f"p{index:04}"/mask
    d.mkdir(exist_ok=True,parents=True)
    ptn,cycles,ids,masks=input_for(index)
    assert mask in masks
    signatures={p:sha(HERE.parent/"table3_grid16_20261125"/p) for p in
        ("tool_partition.py","partition.py","port_projection.py","ordered_projection.py","batch_lower.py")}
    signature=dict(index=index,cap=812,pattern=list(map(list,ptn)),ids=ids,mask=mask,code=sha(Path(__file__)),
        parent_code=signatures,lower809=sha(JMS/"results/table3_grid16_20261125/ports/mixed_814/result.json"))
    checkpoint=d/"state.json"
    old=read(checkpoint) if checkpoint.exists() else dict(identity=signature,elapsed=0,lower=809)
    assert old["identity"]==signature
    if (d/"result.json").exists():return
    tool.order.patterns=lambda nf,nd,cap,ready:{ptn:cycles}
    m,c=tool.add_ports("mixed",812)
    vs={z.name:m.get_int_var_from_proto_index(i) for i,z in enumerate(m.proto.variables) if z.name}
    tool.exact_sides(m,vs,ptn,812,True)
    vs={z.name:m.get_int_var_from_proto_index(i) for i,z in enumerate(m.proto.variables) if z.name}
    for i,side in zip(ids,mask):m.add(vs[f"front_{i}"]==int(side))
    m.add(c>=max(809,old["lower"]))
    m.clear_objective()
    engine=cp_model.CpSolver()
    engine.parameters.num_workers=1;engine.parameters.random_seed=1
    engine.parameters.log_search_progress=True;engine.parameters.log_to_stdout=False
    engine.parameters.max_time_in_seconds=max(0,BUDGET-old["elapsed"])
    started=time.monotonic();stop=threading.Event()
    def used():return min(BUDGET,old["elapsed"]+time.monotonic()-started)
    def heartbeat():
        while not stop.wait(3):save(checkpoint,dict(identity=signature,elapsed=min(BUDGET,used()+3),lower=809))
    clock=threading.Thread(target=heartbeat,daemon=True);clock.start()
    with (d/"cp.log").open("a",encoding="utf8",buffering=1) as f:
        engine.log_callback=lambda message:f.write(message.rstrip()+"\n")
        status=engine.solve(m)
    stop.set();clock.join()
    result=engine.status_name(status)
    if status in (cp_model.OPTIMAL,cp_model.FEASIBLE):
        values={k:engine.value(v) for k,v in vs.items()};values["C"]=engine.value(c)
        save(d/"projection.json",values)
    elapsed=used()
    save(checkpoint,dict(identity=signature,elapsed=elapsed,lower=813 if status==cp_model.INFEASIBLE else 809))
    save(d/"result.json",dict(identity=signature,elapsed=elapsed,status=result,
        lower=813 if status==cp_model.INFEASIBLE else 809,upper=engine.value(c) if status in (cp_model.OPTIMAL,cp_model.FEASIBLE) else None))
    print(index,mask,result,elapsed,flush=True)


def main():
    ROOT.mkdir(exist_ok=True)
    with (ROOT/"controller.lock").open("a+b") as lock:
        lock.seek(0)
        try:msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
        except OSError:return
        alljobs=[]
        # Interleave cases so early completions and difficult patterns each receive a worker.
        masks=[input_for(index)[-1] for index in KINDS]
        for n in range(max(map(len,masks))):
            alljobs.extend((index,case[n]) for index,case in zip(KINDS,masks) if n<len(case))
        signature={k:input_for(k)[-1] for k in KINDS}
        active={}
        for p in psutil.process_iter(["cmdline"]):
            c=p.info["cmdline"] or []
            if len(c)>2 and os.path.normcase(c[-3])==os.path.normcase(str(Path(__file__))):
                active[int(c[-2]),c[-1]]=p
        previous=read(ROOT/"progress.json")["elapsed_s"] if (ROOT/"progress.json").exists() else 0
        start=time.monotonic()
        donefiles={}
        while True:
            for k,p in list(active.items()):
                if not p.is_running():
                    if not (ROOT/f"p{k[0]:04}"/k[1]/"result.json").exists():raise RuntimeError(k)
                    del active[k]
            done=0;remain=0
            for index,mask in alljobs:
                k=index,mask
                where=ROOT/f"p{index:04}"/mask
                if (where/"result.json").exists():
                    done+=1;donefiles[k]=where/"result.json";continue
                # A finished unrestricted parent proof covers every side subset.
                root=JMS/f"results/table3_grid16_20261125/tool_capacity/mixed_812/p{index:04}/result.json"
                if root.exists():
                    r=read(root)
                    if r.get("lower",0)>=813 and r.get("status")=="INFEASIBLE":
                        done+=1;donefiles[k]=root;continue
                used=read(where/"state.json")["elapsed"] if (where/"state.json").exists() else 0
                remain+=max(0,BUDGET-used)
                if k in active or len(active)>=3:continue
                where.mkdir(exist_ok=True,parents=True)
                with (where/"console.log").open("a",encoding="utf8") as f:
                    p=subprocess.Popen([sys.executable,"-B","-u","-X","utf8",str(Path(__file__)),str(index),mask],stdout=f,stderr=subprocess.STDOUT)
                active[k]=psutil.Process(p.pid)
            for i,all_masks in signature.items():
                if all((i,s) in donefiles for s in all_masks):
                    refs={s:dict(path=donefiles[i,s].relative_to(JMS).as_posix(),sha256=sha(donefiles[i,s])) for s in all_masks}
                    lower=min(read(donefiles[i,s])["lower"] for s in all_masks)
                    save(ROOT/f"p{i:04}"/"certificate.json",dict(index=i,lower=lower,masks=all_masks,proofs=refs,
                         scope="Every possible front/back allocation in the first single-exposure batch; at most two products per side."))
            elapsed=previous+time.monotonic()-start
            save(ROOT/"progress.json",dict(expected=len(alljobs),completed=done,failed=0,elapsed_s=elapsed,estimated_remaining_s=remain/3,
                estimated_total_s=elapsed+remain/3,active={f"{i}_{s}":p.pid for (i,s),p in active.items()},
                basis="Up to 240 cumulative CP seconds per unresolved subcase, 3 threads, or early stop on independently proven parent."))
            print(f"Mixed 812 four-hand subcases {done}/{len(alljobs)}, failed 0, elapsed {elapsed:.0f}s, remaining search budget ETA {remain/3:.0f}s",flush=True)
            if done==len(alljobs):break
            time.sleep(3)

if __name__=="__main__":
    if len(sys.argv)==3:run(int(sys.argv[1]),sys.argv[2])
    else:main()

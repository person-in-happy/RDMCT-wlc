"""Repeat the 16-wafer weight study on its original handoffs and recover over-budget controls."""
import subprocess
import sys
import time
from pathlib import Path

import run
from run import HERE, MATCH, R, ROOT, cell, read, save, sha

BASE=run.OUT
OUT=BASE/"original_controls"
CASE="E_n4_H10_mixed_dual"


def prepare():
    tasks={}
    for seed in (1,2,3):
        for w in (0,5,25,100):
            legacy=R/"nondecreasing_review_rhythm_20261103_135933/runs"/f"n16_H10_2x2_dual__s{seed}__w{w}"
            e=read(legacy/"evidence.json")
            source,assignment=Path(e["cell"]["source"]),Path(e["cell"]["values"])
            assert e["valid"] and (sha(source),sha(assignment))==(e["source_sha256"],e["input_values_sha256"])
            key=f"original_rhythm__s{seed}__{w}"
            tasks[key]=dict(case="E_n16_2x2",seed=seed,kind="fixed",seconds=60,gap=None,weight=w,
                            rho=None,schedule=source.relative_to(ROOT).as_posix(),assignment=assignment.relative_to(ROOT).as_posix(),
                            schedule_sha256=sha(source),assignment_sha256=sha(assignment),parent_eligible=True,backend="E",n=16)
    original=read(BASE/"protocol.json")["jobs"]
    for key,t in original.items():
        if t["kind"]=="B":
            e=read(BASE/"runs"/key/"result.json")
            if not e["eligible"]: tasks[key]=t
    return tasks


def redo_a():
    key=f"{CASE}__s2__AB"
    old=read(MATCH/key/"result.json")
    assert old["stages"][0]["record"]["seconds"]>271 and not old["eligible"]
    sys.path.insert(0,str(HERE.parent/"matched_controls_20261122"))
    import importlib.util
    spec=importlib.util.spec_from_file_location("old_matched_controls",HERE.parent/"matched_controls_20261122/run.py")
    matched=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(matched)
    case=matched.CASES[CASE]
    sys.path.insert(0,str(cell.BACKENDS["E"]))
    import model
    folder=OUT/"runs"/(key+"__primary")
    folder.mkdir(parents=True,exist_ok=True)
    data,vals=read(ROOT/case["source"]),cell.values(ROOT/case["assignment"])
    assert sha(ROOT/case["assignment"])==old["input_sha256"]
    cfg=model.Config(**data["config"])
    checked=cell.certify_start(cfg,data,vals)
    result,record=matched.objective_stage(cfg,checked[2],vals,"AB",270,dict(n=4,seed=2),folder)
    eligible=record["seconds"]<=271 and record["status"] not in ("memlimit","userinterrupt","unknown")
    s,v=folder/"schedule.json",folder/"assignment.json.gz"
    save(s,result[0]); save(v,result[1])
    save(folder/"primary.json",dict(record=record,input_sha256=old["input_sha256"],eligible=eligible,
                                    schedule_sha256=sha(s),assignment_sha256=sha(v),replay=result[3]))
    return dict(case=CASE,seed=2,kind="fixed",seconds=30,gap=None,rho=None,weight=25,
                schedule=s.relative_to(ROOT).as_posix(),assignment=v.relative_to(ROOT).as_posix(),
                schedule_sha256=sha(s),assignment_sha256=sha(v),parent_eligible=eligible,backend="E",n=4)


if __name__=="__main__":
    import psutil
    run.OUT=OUT
    if len(sys.argv)>1:
        run.worker(sys.argv[1])
    else:
        tasks=prepare()
        print(f"0 completed | 0 failed | restoring original sources and time budgets",flush=True)
        key=f"matched__{CASE}__s2__AB"
        tasks[key]=redo_a()
        save(OUT/"protocol.json",dict(jobs=tasks,primary_budget=270,secondary_budget=30,threads=1,parallel=1,
             rule="one independent retry for each time-overrun matched small arm, regardless of solution values"))
        failed=[]
        ordered=sorted(tasks,key=lambda k:(not k.startswith("matched"),k))
        start=time.monotonic()
        for i,name in enumerate(ordered,1):
            while psutil.virtual_memory().available<6*1024**3:time.sleep(3)
            log=OUT/"runs"/name/"worker.log"
            log.parent.mkdir(parents=True,exist_ok=True)
            with log.open("w",encoding="utf8") as stream:
                status=subprocess.run([sys.executable,"-B","-X","utf8",__file__,name],stdout=stream,stderr=subprocess.STDOUT).returncode
            if status: failed.append(name)
            print(f"{i-len(failed)}/{len(tasks)} complete | {len(failed)} failed | ETA {(time.monotonic()-start)/i*(len(tasks)-i)/60:.1f} min",flush=True)
            save(OUT/"progress.json",dict(total=len(tasks),completed=i-len(failed),failed=failed,remaining=len(tasks)-i))
        sys.exit(int(bool(failed)))

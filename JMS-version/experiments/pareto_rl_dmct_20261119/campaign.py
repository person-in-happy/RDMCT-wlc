"""Foreground, resumable supervisor for the isolated Pareto experiments."""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time
import traceback

from common import BACKEND, HERE, JMS, PATTERNS, ROOT, digest, save


def loads(p):
    return json.loads(p.read_text(encoding="utf-8"))


def cells(smoke):
    items = []
    def add(case,method,seed,budget,suite,**kw):
        options = "_".join(f"{k}{v}" for k,v in sorted(kw.items()))
        ident = f"{suite}_{case}_{method}_s{seed}"+("_"+options if options else "")
        items.append(dict(id=ident,case=case,method=method,seed=seed,budget=budget,suite=suite,**kw))
    if smoke:
        for c,m in (("S1","domain"),("S1","generic"),("M4","nsga2"),("R8","moead"),("S1","epsilon"),("S1","rl_domain")):
            add(c,m,1,12,"smoke")
        return items
    for case,budget in (("S1",40),("M4",45),("H4",45),("H8",55),("H16",80)):
        for seed in (1,2,3):
            for method in ("domain","epsilon","nsga2","moead","rl_domain","legacy"):
                add(case,method,seed,budget,"main")
            if case in ("S1","M4"):
                for method in ("generic","generic_bound","domain_no_bound","no_order","adaptive"):
                    add(case,method,seed,budget,"ablation",**({"adaptive":True} if method=="adaptive" else {}))
    for seed in (1,2,3):
        for method in ("generic","domain"):
            add("S1",method,seed,18,"paired",paired=True)
    for seed in (1,2):
        for width in (.15,.5):
            add("M4","domain",seed,45,"algorithm",width=width)
        for share in (.12,.32):
            add("M4","domain",seed,45,"algorithm",repair=share)
        for case in ("M4-D4","M4-H3"):
            for method in ("domain","nsga2"):
                add(case,method,seed,45,"machine")
        for weight in (0,12.5,25,50):
            for method in ("domain","nsga2"):
                add("R8",method,seed,46,"weight",weight=weight)
    for method in ("domain","epsilon","nsga2","moead","rl_domain","legacy"):
        add("S1",method,1,300,"long")
    return items


def fingerprints():
    files = list(BACKEND.glob("*.py")) + [PATTERNS/n for n in ("patterns.py","packing.py","timing.py")]
    files += [JMS/"experiments/finite_budget_20261116/finite_budget.py",ROOT/"scip_imports.py",ROOT/"runtime_compat.py",
              ROOT/"cie/code/run_cie_benchmarks.py",ROOT/"cutsel_agent_parallel.py",ROOT/"cie/configs/cie_proposed_inference.json"]
    files += [HERE/n for n in ("campaign.py","search.py","native.py","witness.py","neighborhood.py","decoder.py","common.py","evolution.py","initials.py")]
    return {p.relative_to(ROOT).as_posix():digest(p) for p in sorted(files)}


def prepare(out,smoke,workers):
    import platform
    import psutil
    from importlib.metadata import version
    from joint_algorithms import policy_record
    if out.exists():
        raise FileExistsError(out)
    out.mkdir(parents=True)
    policy = policy_record("proposed",1)
    baseline = Path("G:/work/PlatEMO-master/PlatEMO/Algorithms/Multi-objective optimization")
    source = [baseline/"NSGA-II/NSGAII.m",baseline/"NSGA-II/EnvironmentalSelection.m",baseline/"MOEA-D/MOEAD.m"]
    save(out/"protocol.json",dict(cells=cells(smoke),code=fingerprints(),policy=policy,workers=workers,
        comparable_budget="Seconds from case setup through independent physical replay and full original objective witness admission; final duplicate replay and serialization timed separately.",
        common_input="Neutral LP construction and a charged, serial, shared original SPBS preparation per instance and seed; no previous schedules or target vectors.",
        caps="Fixed endpoint and physical lower-bound to common seed fractions, or adaptive for named ablation.",
        holdouts=["H4","H8","H16"],physical_tolerance=2e-5,cpu_threads_per_worker=1,max_concurrent_gpu_workers=1,
        machine=dict(platform=platform.platform(),logical_cpu=psutil.cpu_count(),physical_gib=round(psutil.virtual_memory().total/2**30,2)),
        python=sys.executable,versions={k:version(k) for k in ("numpy","scipy","pyscipopt","matplotlib","torch","psutil")},
        reference_implementations={str(p):digest(p) for p in source if p.is_file()},
        seed_policy="Seeds 1,2,3; same instance, initial schedule, cap policy and budget for paired algorithm groups.",
        evaluation="S1 reference only after all search. Other cases A_min=B_min=0, A_scale=1.5*A_initial, B_scale=2*B_initial, reference=(1.1,1.1).",
        local_search="Equal integer-gene release counts in the two local policies; dedicated paired operator experiment fixes parents and upper limits."))


def worker(out,cellid,dest):
    from search import Search
    spec = next(s for s in loads(out/"protocol.json")["cells"] if s["id"]==cellid)
    try:
        result = Search(spec,dest,out/"shared_initials").run()
        print(f"DONE {cellid} | frontier {len(result['front'])} | admission cutoff {spec['budget']}s",flush=True)
    except BaseException:
        save(dest/"error.json",{"error":traceback.format_exc()})
        raise


def run(out,workers=None):
    import psutil
    protocol = loads(out/"protocol.json")
    if protocol["code"]!=fingerprints():
        raise RuntimeError("Campaign source differs from its frozen manifest. Use a new campaign for changed solver code.")
    checkpoint = protocol["policy"]
    if digest(checkpoint["checkpoint"])!=checkpoint["sha256"]:
        raise RuntimeError("Changed learned checkpoint")
    items = protocol["cells"]
    from initials import prepare_all
    prepare_all(out,items)
    workers = min(workers or protocol["workers"],protocol["workers"])
    # GPU work is serialized. Interleave instance sizes so memory-intensive native models do not start together.
    queue = sorted(items,key=lambda s:(s["seed"],s["suite"]!="main",s["method"]!="rl_domain",s["budget"],s["id"]))
    done,failed,running = {},{},{}
    for spec in list(queue):
        root = out/"cells"/spec["id"]
        for file in sorted(root.glob("attempt_*/result.json")):
            if loads(file)["spec"]==spec:
                done[spec["id"]] = file.relative_to(out).as_posix()
                queue.remove(spec)
                break
    begin = time.monotonic()
    def progress():
        remaining = (sum(s["budget"] for s in queue)+sum(max(0,v[0]["budget"]-(time.monotonic()-v[4])) for v in running.values()))/workers
        state = dict(total=len(items),completed=len(done),failed=len(failed),running=list(running),pending=len(queue),
                     elapsed_s=round(time.monotonic()-begin),nominal_eta_s=math.ceil(remaining),available_gib=round(psutil.virtual_memory().available/2**30,1))
        save(out/"progress.json",state)
        print(f"完成 {len(done)}/{len(items)} | 失败 {len(failed)} | 运行 {len(running)} | 待运行 {len(queue)} | 预计剩余 {remaining/60:.1f} 分钟 | 可用内存 {state['available_gib']} GiB",flush=True)
    last = -100
    while queue or running:
        for key,(spec,p,log,folder,started) in list(running.items()):
            status = p.poll()
            if status is None:
                continue
            log.close()
            if status==0 and (folder/"result.json").is_file():
                done[key] = (folder/"result.json").relative_to(out).as_posix()
            else:
                failed[key] = dict(path=folder.relative_to(out).as_posix(),exit_code=status)
            del running[key]
            print(f"{key} | {('完成' if key in done else '失败')} | {time.monotonic()-started:.1f}s",flush=True)
            last = -100
        for s in list(queue):
            if len(running)>=workers or psutil.virtual_memory().available<5.5*2**30:
                break
            if s["method"] in ("rl_domain","legacy") and any(r[0]["method"] in ("rl_domain","legacy") for r in running.values()):
                continue
            if s["case"]=="H16" and sum(r[0]["case"]=="H16" for r in running.values())>=1:
                continue
            folder = out/"cells"/s["id"]
            folder.mkdir(parents=True,exist_ok=True)
            attempt = folder/f"attempt_{1+len(list(folder.glob('attempt_*'))):02d}"
            attempt.mkdir()
            log = (attempt/"stdout.log").open("w",encoding="utf-8")
            p = subprocess.Popen([sys.executable,"-B","-X","utf8","-u",str(HERE/"campaign.py"),"worker",
                                  str(out),"--cell",s["id"],"--dest",str(attempt)],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
            running[s["id"]] = (s,p,log,attempt,time.monotonic())
            queue.remove(s)
        if time.monotonic()-last>=8:
            progress()
            last=time.monotonic()
        if running or queue:
            time.sleep(.6)
    progress()
    save(out/"finished.json",dict(done=done,failed=failed,total=len(items),sources_match=(fingerprints()==protocol["code"])))
    if failed:
        raise SystemExit(2)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action",choices=("prepare","run","worker"))
    parser.add_argument("out",type=Path)
    parser.add_argument("--workers",type=int,default=5)
    parser.add_argument("--smoke",action="store_true")
    parser.add_argument("--cell")
    parser.add_argument("--dest",type=Path)
    args = parser.parse_args()
    path = args.out.resolve()
    if args.action=="prepare":
        prepare(path,args.smoke,args.workers)
    elif args.action=="run":
        # Exclusive OS file lock releases automatically if the supervisor is interrupted.
        import msvcrt
        with (path/"supervisor.lock").open("a+b") as lock:
            lock.seek(0)
            msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
            try:
                run(path,args.workers)
            finally:
                lock.seek(0)
                msvcrt.locking(lock.fileno(),msvcrt.LK_UNLCK,1)
    else:
        worker(path,args.cell,args.dest)


if __name__=="__main__":
    main()

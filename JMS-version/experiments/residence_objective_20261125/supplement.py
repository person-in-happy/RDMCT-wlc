"""Resume the manuscript threshold and 16-wafer post-handoff experiments."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import statistics
import subprocess
import sys
import time
import psutil

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
ARCHIVE = ROOT / "JMS-version/results/mixed_controls_20261122"
OUT = ROOT / "JMS-version/results/residence_objective_20261125/supplement"
LEVELS = {"10pct": .1, "1pct": .01, "0p01pct": .0001}


def load(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def save(path, value):
    part = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    part.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf8")
    for i in range(20):
        try:
            os.replace(part, path)
            return
        except PermissionError:
            if i == 19:
                raise
            time.sleep(.01)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def cases():
    jobs = {}
    for grid in ("grid2", "grid4", "grid_2x2"):
        for record in sorted((ARCHIVE / grid).glob("*/result.json")):
            row = load(record)
            assert row["primary"]["gap"] <= LEVELS[row["a"]] + 1e-8
            for b, gap in LEVELS.items():
                previous = record.parent / b / "runs/endpoint/result.json"
                jobs[f"grid_{row['case']}__{row['a']}__{b}"] = (
                    previous, gap, None, 1, row["primary"])
    for record in sorted((ARCHIVE / "ablations_verified").glob("*/result.json")):
        row = load(record)
        if row["arm"] in ("fixed", "full", "fixed_free"):
            previous = record.parent / "B/runs/endpoint/result.json"
            jobs[f"structure_{row['arm']}__s{row['seed']}"] = (
                previous, 0, 30, 1, row["stages"][-1][0])
    for seed in (1, 2, 3):
        # The chosen handoffs are the same full-method A records in all four arms.
        previous = ARCHIVE / "ablations_verified" / f"s{seed}__full/B/runs/endpoint/result.json"
        for weight in (0, .5, 1, 2):
            jobs[f"range_{weight:g}__s{seed}"] = (previous, 0, 30, weight, {})
    return jobs


def target(name, row):
    path, gap, limit, weight, primary = row
    parent = load(path)["job"]
    src = ROOT / parent["schedule"]
    assign = ROOT / parent["assignment"]
    assert src.parent == assign.parent
    assert (digest(src), digest(assign)) == (parent["schedule_sha256"], parent["assignment_sha256"])
    identity = dict(schedule=parent["schedule_sha256"], assignment=parent["assignment_sha256"],
                    seed=parent["seed"], backend=parent["backend"], gap=gap, seconds=limit,
                    range_weight=weight, clean_weight=1, objective="product_mean+mode_range+closed_clean_deficit_v1")
    key = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:24]
    return key, dict(name=name, key=key, source=str(src.parent.relative_to(ROOT)), schedule=src.name,
                     assignment=assign.name, reference=str(path.relative_to(ROOT)), primary=primary, settings=identity)


def checked(path, job):
    result = path / "result.json"
    if not result.exists():
        return False
    d = load(result)
    a = job["settings"]
    return (d["replay"]["valid"] and (a["seconds"] is not None or d["eligible"])
            and d["seed"] == a["seed"] and d["target_gap"] == a["gap"]
            and d["parents"][0]["assignment_sha256"] == a["assignment"]
            and d["parents"][0]["schedule_sha256"] == a["schedule"]
            and d["weights"] == {"range": a["range_weight"], "clean": 1}
            and all(digest(path / k) == v for k, v in d["files"].items()))


def active_workers(out, keys, worker):
    """Match the whole worker entry point and resolved destination before adoption."""
    active = {}
    expected = os.path.normcase(str(worker.resolve()))
    for proc in psutil.process_iter(["cmdline"]):
        try:
            command = proc.info["cmdline"] or []
            if len(command)>3 and os.path.normcase(command[-3])==expected and Path(command[-2]).resolve()==out:
                key=command[-1]
            elif "--output" in command and str(HERE/"solver.py").lower() in [s.lower() for s in command]:
                dest=Path(command[command.index("--output")+1]).resolve()
                if dest.parent!=out:
                    continue
                key=dest.name
            else:
                continue
            if key in keys and proc.is_running():
                active[key]=proc
        except (psutil.NoSuchProcess, psutil.AccessDenied, ValueError, IndexError):
            continue
    return active


def controller(out, manifest, concurrency=2, worker=HERE/"supplement_checkpoint.py", interval=2):
    import msvcrt
    if concurrency < 1:
        raise ValueError("Concurrency must be positive")
    out=Path(out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    with (out / "controller.lock").open("a+b") as lock:
        lock.seek(0)
        try:
            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            print("Existing supplement controller is active.", flush=True)
            return
        manifest_path=out/"manifest.json"
        if manifest_path.exists():
            if load(manifest_path)!=manifest:
                raise ValueError("The archived manifest differs. Choose a separate output directory.")
        else:
            save(manifest_path,manifest)
        jobs={j["key"]:j for j in manifest.values()}
        todo=dict(jobs)
        done, failed, running, retries = {}, {}, {}, {}
        status=out/"progress.json"
        prev=load(status) if status.exists() else {}
        past_elapsed=prev.get("elapsed_s",0.)
        clock = time.monotonic()
        def accept(key):
            p=out/key
            if not checked(p,jobs[key]):
                return False
            record=load(p/"result.json")["record"]
            done[key]=record.get("cumulative_wall_s",record["wall_seconds"])
            return True
        for key in list(todo):
            if accept(key): del todo[key]
        if not todo and prev.get("status")=="complete":
            print(f"Validated {len(done)} unique endpoints / {len(manifest)} logical trials; ETA 0s.",flush=True)
            return
        for key,proc in active_workers(out,todo,worker).items():
            running[key]=(proc,None,True)
            del todo[key]
        while True:
            for key in list(running):
                proc, stream, adopted = running[key]
                if (adopted and proc.is_running()) or (not adopted and proc.poll() is None):
                    continue
                if stream: stream.close()
                if not accept(key):
                    retries[key]=retries.get(key,0)+1
                    if retries[key]<=1:
                        todo[key]=jobs[key]
                    else:
                        failed[key]=dict(exit=None if adopted else proc.returncode,name=jobs[key]["name"])
                del running[key]
            for key in list(todo):
                if len(running) >= concurrency:
                    break
                del todo[key]
                p = out / key
                p.mkdir(exist_ok=True)
                cmd = [sys.executable, "-B", "-u", str(worker.resolve()), str(out), key]
                stream = (p / "console.log").open("a", encoding="utf8")
                proc = subprocess.Popen(cmd, stdout=stream, stderr=subprocess.STDOUT)
                running[key] = (proc, stream, False)
            active={}
            observed=set()
            historical=set()
            def estimate(key):
                a=jobs[key]["settings"]
                group=(a["backend"],a["seconds"])
                samples=[cost for k,cost in done.items() if (jobs[k]["settings"]["backend"],jobs[k]["settings"]["seconds"])==group]
                if samples:
                    observed.add(group)
                    return statistics.median(samples)
                historical.add(group)
                return (a["seconds"]+10) if a["seconds"] is not None else 4
            lanes=[]
            for key,(proc,_,adopted) in running.items():
                cp=out/key/"checkpoint.json"
                ck=load(cp) if cp.exists() else {}
                limit=jobs[key]["settings"]["seconds"]
                charged=ck.get("charged_s",0.)
                active[key]=dict(pid=proc.pid,adopted=adopted,phase=ck.get("phase","starting"),attempt=ck.get("attempt"),
                                 charged_solver_s=charged,remaining_solver_s=None if limit is None else max(0.,limit-charged))
                lanes.append(max(interval,estimate(key)-ck.get("wall_s",0.)))
            lanes.extend([0.]*(concurrency-len(lanes)))
            for key in todo:
                lane=min(range(len(lanes)),key=lanes.__getitem__)
                lanes[lane]+=estimate(key)
            eta=max(lanes)
            elapsed = past_elapsed+time.monotonic()-clock
            state=dict(validated=len(done),failed=failed,total=len(jobs),logical_total=len(manifest),active=active,
                       elapsed_s=round(elapsed,2),estimated_remaining_s=round(eta,2),estimated_total_s=round(elapsed+eta,2),
                       basis=dict(observed_groups=len(observed),historical_groups=len(historical),observed_endpoints=len(done),
                                  method="Median completed wall time by backend and budget; otherwise grid 4s or budget + 10s. Active costs subtract worked time; queued estimates use available worker lanes."),
                       recovery="Verified endpoints persist. Surviving workers are adopted. Interrupted searches restart with a checked incumbent and remaining cumulative solver clock; SCIP tree is discarded.",
                       concurrent=concurrency,status="active" if todo or running else ("failed" if failed else "complete"))
            save(status,state)
            print(f"Validated {len(done)}/{len(jobs)} | failed {len(failed)} | elapsed {elapsed:.1f}s | estimated total {elapsed+eta:.1f}s | ETA {eta:.1f}s",flush=True)
            if not todo and not running:break
            time.sleep(interval)
        if failed:
            raise SystemExit(1)


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--jobs",type=int,default=2)
    ap.add_argument("--out",type=Path,default=OUT)
    ap.add_argument("--only",action="append",help="Selected logical trial(s), in a separate output directory")
    args=ap.parse_args()
    rows=cases()
    if args.only:
        if args.out.resolve()==OUT:
            ap.error("--only requires a separate --out directory")
        rows={name:rows[name] for name in args.only}
    manifest={name:target(name,row)[1] for name,row in rows.items()}
    controller(args.out,manifest,args.jobs)


if __name__ == "__main__":
    main()

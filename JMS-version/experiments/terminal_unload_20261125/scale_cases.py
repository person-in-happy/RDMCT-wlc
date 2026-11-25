"""Construct, retime and independently replay finite-batch benchmarks.

One solver thread. Repeat the command after interruption. Completed cases are
hashed and replayed; an interrupted deterministic case restarts from its input.
"""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import sys
import time
import msvcrt

HERE = Path(__file__).resolve().parent
JMS = HERE.parents[1]
OUT = JMS / "results/terminal_unload_20261125/scale"
sys.path.insert(0,str(JMS/"experiments/pareto75_thesis_20261119"))
from large75 import Config, Packing, Retiming, single_thread_lp, validate
from patterns import Pattern
from timing import BatchTiming
sys.path.insert(0,str(JMS/"experiments/square_residence_20261125"))
from score import metrics

CASES = [(25,12,3,4),(25,12,3,8),(25,12,6,4),(50,17,6,6),(75,37,3,8)]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, data):
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(data,indent=2,allow_nan=False),encoding="utf8")
    temp.replace(path)


class SharedPattern(Pattern):
    def make_pairs(self, products):
        groups = super().make_pairs(products)
        return [[f"D{1+(int(w[1:])-1)%self.cfg.dummy_count}" if w.startswith("D") else w
                 for w in group] for group in groups]


def run_case(n, full, threshold, inventory):
    start = time.perf_counter()
    ports = {f"LP{i+1}": {"4x1":full//4+int(i<full%4),
                           "2x2":(n-full)//4+int(i<(n-full)%4)} for i in range(4)}
    cfg = Config(load_ports=ports,cleaning_interval=threshold,dummy_count=inventory,horizon=100000)
    packing = Packing(cfg)
    packing.patterns = {(k,ch): SharedPattern(cfg,mode,ch,wafers)
                        for k,(mode,wafers) in enumerate(packing.groups+[("clean",[])]) for ch in cfg.chambers}
    beam = [()]
    for _ in range(packing.n):
        beam = packing.advance(beam,4)
    batch = BatchTiming(packing,beam[0])
    lp = Retiming(batch,0)
    built = time.perf_counter()-start
    # Only the makespan objective is solved. Report the physical residence
    # score of this returned point independently of the LP auxiliary fields.
    ans = single_thread_lp(lp.primary,A_ub=lp.matrix,b_ub=lp.rhs,bounds=lp.limits,method="highs")
    if not ans.success:
        raise RuntimeError(ans.message)
    solved = time.perf_counter()-start-built
    schedule = batch.schedule(ans.x[:lp.n].round(8).tolist())
    score = metrics(schedule)
    if abs(score["cmax"]-ans.fun)>1e-5 or not validate(schedule)["valid"]:
        raise ValueError("Fixed-order optimum differs from the replay")
    return schedule,dict(n=n,full=full,H=threshold,D=inventory,selected_pairs=len(schedule["pairs"]),
                         cycles=len(schedule["cycles"]),cleanings=sum(v["mode"]=="clean" for v in schedule["cycles"]),
                         actions=len(batch.actions),lp_cols=lp.matrix.shape[1],lp_rows=lp.matrix.shape[0],
                         build_s=built,lp_s=solved,total_s=time.perf_counter()-start,
                         fixed_order_makespan_lower=ans.fun,global_al_lower=268+28*n,
                         lp_status=ans.message,replay_checks=schedule["validation"]["checks"],**score)


def main(stop_after=None):
    OUT.mkdir(parents=True,exist_ok=True)
    lock = (OUT/"active.lock").open("a+b")
    try:
        msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
    except OSError:
        print("A foreground run already owns the queue.",flush=True)
        return
    sources = [Path(__file__),Path(sys.modules["timing"].__file__),Path(sys.modules["packing"].__file__),
               Path(sys.modules["patterns"].__file__),Path(sys.modules["decoder"].__file__),
               Path(sys.modules["score"].__file__),Path(sys.modules["validate"].__file__)]
    signature = {p.relative_to(JMS).as_posix():digest(p) for p in sources}
    records = []
    try:
        for case in CASES:
            folder = OUT/("_".join(map(str,case)))
            folder.mkdir(exist_ok=True)
            marker, archive = folder/"record.json",folder/"schedule.json.gz"
            estimate = sum(v["total_s"] for v in records)/len(records) if records else 8
            elapsed = sum(v["total_s"] for v in records)
            left = estimate*(len(CASES)-len(records))
            state = dict(completed=len(records),failed=0,elapsed_s=elapsed,remaining_s=left,
                         estimated_total_s=elapsed+left,active=case,concurrency=1,
                         basis="completed case mean; startup estimate 8s per structure construction and LP")
            write(OUT/"status.json",state)
            print(state,flush=True)
            if marker.exists():
                rec = json.loads(marker.read_text())
                if rec["signature"]!=signature or digest(archive)!=rec["schedule_sha256"]:
                    raise ValueError("Checkpoint signature mismatch")
                saved = json.loads(gzip.decompress(archive.read_bytes()))
                if not validate(saved)["valid"] or abs(metrics(saved)["secondary"]-rec["secondary"])>1e-5:
                    raise ValueError("Invalid checkpoint")
            else:
                schedule,rec = run_case(*case)
                data = gzip.compress(json.dumps(schedule,allow_nan=False).encode(),mtime=0)
                temp = archive.with_suffix(".tmp")
                temp.write_bytes(data)
                temp.replace(archive)
                rec.update(signature=signature,schedule_sha256=digest(archive))
                write(marker,rec)
            records.append(rec)
            if stop_after==len(records):
                write(OUT/"status.json",dict(state,completed=len(records),active=None,paused=True))
                return
        elapsed = sum(row["total_s"] for row in records)
        write(OUT/"summary.json",records)
        state = dict(completed=len(records),failed=0,remaining_s=0,estimated_total_s=elapsed,elapsed_s=elapsed)
        write(OUT/"status.json",state)
        print(state,flush=True)
    except Exception as exc:
        write(OUT/"status.json",dict(state,failed=1,error=str(exc)))
        raise
    finally:
        lock.close()


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stop-after",type=int)
    main(parser.parse_args().stop_after)

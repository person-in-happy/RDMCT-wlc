"""Resume the one Table 5 seed whose archived pool does not resolve quadratic ties."""
from pathlib import Path
import hashlib
import json
import msvcrt
import os
import sys
import threading
import time

HERE = Path(__file__).resolve().parent
JMS = HERE.parents[1]
OUT = JMS / "results" / HERE.name / "table5"
sys.path.insert(0, str(HERE))
from score import metrics, OBJECTIVE
from solver import objective_terms
sys.path.insert(0, str(HERE.parent / "residence_objective_20261125"))
import paired

def read(p):
    return json.loads(p.read_text(encoding="utf-8-sig"))

def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

def store(p, doc):
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(f".{os.getpid()}.tmp")
    tmp.write_text(json.dumps(doc, indent=2), encoding="utf8")
    os.replace(tmp, p)

def reference(path):
    timing = read(path / "timing.json")
    assert timing["objective"] == OBJECTIVE
    old = JMS / timing["parent"]
    assert sha(old) == timing["parent_sha256"]
    return timing

class Trial(paired.original.Trial):
    phase_b = paired.ResidenceTrial.phase_b

    def observe(self, x, sol, at):
        if at > self.limit or self.s["hit"]:
            return
        f = metrics(x.result(solution=sol))
        coordinate = tuple(round(f[k], 6) for k in ("cmax","mean_residence","residence_range","clean_deficit"))
        if coordinate not in self.observed:
            w = self.witness(x, sol, at, f)
            with (self.dest/"events.jsonl").open("a", encoding="utf8") as stream:
                stream.write(json.dumps(dict(w, physical=f))+"\n")
            self.observed.add(coordinate)
        super().observe(x, sol, at)

def run():
    OUT.mkdir(exist_ok=True, parents=True)
    ref = OUT/"reference2"
    source = JMS/"results/huber_residence_20261125/runs/ref5_2"
    t = read(source/"timing.json")
    now = metrics(read(source/"B/schedule.json"))
    assert now["residence_range"] < 1e-6 and abs(now["secondary"]-t["f_B"])<1e-5
    refdoc = dict(t, objective=OBJECTIVE, parent=str((source/"timing.json").relative_to(JMS)),parent_sha256=sha(source/"timing.json"))
    store(ref/"timing.json", refdoc)
    dest=OUT/"s2_no_spbs"
    paired.original.solve=paired.Method()
    paired.original.load_reference=reference
    paired.metrics=metrics
    paired.objective_terms=objective_terms
    if (dest/"result.json").is_file():
        report=read(dest/"result.json")
        assert report["schedule_sha256"]==sha(dest/"endpoint/schedule.json")
        print("1/1 verified; ETA 0 s",flush=True)
        return
    trial=Trial(2,"no_spbs",dest,ref)
    trial.observed=set()
    stop=threading.Event()
    def report(done=0,failed=0):
        used=min(trial.limit,trial.elapsed())
        status=dict(objective=OBJECTIVE,completed=done,failed=failed,total=1,stage=trial.s["stage"],
                    elapsed_charged_s=used,estimated_remaining_s=0 if done else round(trial.limit-used,1),
                    estimated_total_s=round(trial.limit,1),cut_calls=trial.s["calls"],pid=os.getpid(),threads=1,
                    basis="Paired seed 2 actual full-method budget; initialisation included. Ends early on simultaneous target.",
                    recovery="Retains verified incumbent, dual lower bound, cut count and charged wall time at 3s heartbeats; restarts search tree.")
        store(OUT/"progress.json",status)
        print(f"Table 5 seed 2, no layered improvement: {done}/1; failed {failed}; stage {status['stage']}; elapsed {used:.1f}s; total {trial.limit:.1f}s; remaining {status['estimated_remaining_s']}s",flush=True)
    def updates():
        while not stop.wait(15):
            report()
    report(); monitor=threading.Thread(target=updates,daemon=True);monitor.start()
    try:
        trial.run()
    except BaseException:
        stop.set();monitor.join();report(failed=1);raise
    stop.set();monitor.join();report(done=1)

if __name__=="__main__":
    OUT.mkdir(parents=True,exist_ok=True)
    with (OUT/"runner.lock").open("a+b") as lock:
        lock.seek(0)
        try: msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
        except OSError: print("An existing foreground worker owns this seed.");sys.exit(0)
        run()

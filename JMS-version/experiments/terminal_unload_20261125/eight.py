"""Check the six-second dwell target at the archived eight-wafer return cap.

Run in a foreground terminal. Each H value is a resumable endpoint. A failed
native search reports its status only for the fixed upstream assignment.
"""
from dataclasses import replace
from hashlib import sha256
import json
import msvcrt
from pathlib import Path
import sys
import time

from extended_model import Config, Integrated, JMS
from replay_events import audit
from seed import constrain_seed, normalize_schedule
from validate import validate
sys.path.insert(0, str(JMS / "experiments/square_residence_20261125"))
from score import metrics

OUT = JMS / "results/terminal_unload_20261125/eight"
BUDGET = 45


def write(path, data):
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, allow_nan=False) + "\n", encoding="utf8")
    tmp.replace(path)


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def run(path, folder, available):
    source = json.loads(path.read_bytes())
    before = metrics(source)
    assert validate(source)["valid"] and before["cmax"] == 553 and before["secondary"] == 3.75
    base = Config(**source["config"])
    data = normalize_schedule(base, source)
    cfg = replace(base, max_pairs=max(p["id"] for p in data["pairs"]) + 1,
                  max_cycles=max(c["index"] for c in data["cycles"]) + 1)
    x = Integrated(cfg)
    m = x.model
    m.setIntParam("parallel/maxnthreads", 1)
    m.setRealParam("numerics/feastol", 1e-8)
    m.setRealParam("limits/time", max(0.01, available))
    m.setIntParam("limits/solutions", 1)
    constrain_seed(x, data, times=False)
    m.addCons(x.cmax <= 553)
    product_pairs = {w["pair"] for w in data["jobs"] if w["product"]}
    active = {p["id"]: p for p in data["pairs"]}
    for p in product_pairs:
        double = active[p]["mode"] == "2x2"
        exposure = 2 * cfg.mix_time if double else cfg.full_time
        m.addCons(x.unload[p]["s"] - x.load[p]["e"] == exposure + (6 if double else 0))
    for c in data["cycles"]:
        chamber, q = c["chamber"], c["index"]
        front, = [p for p in c["pairs"] if p == c["front"]]
        rear, = [p for p in c["pairs"] if p != front]
        is_tail = not any(d["chamber"] == chamber and d["index"] == q + 1 and
                          set(c["pairs"]).intersection(d["pairs"]) for d in data["cycles"])
        rev = int(is_tail and c["mode"] == "2x2" and front not in product_pairs and rear in product_pairs)
        m.addCons(x.product_first[chamber,q] == rev)
    # Keep upstream product handling and exposure times from the witnessed cap.
    byname = {e["name"]: e for e in data["events"]}
    for e in x.events:
        known = byname.get(e["name"])
        if known and (known["kind"] in ("origin_pick", "al_put", "al_pick", "upper_put")
                      or (known["kind"] == "pair_load" and known["pair"] in product_pairs)):
            m.addCons(e["s"] == round(known["start"], 5))
    for c in data["cycles"]:
        if c["mode"] != "clean":
            m.addCons(x.cy.start[c["chamber"],c["index"]] == round(c["start"], 5))
    m.optimize()
    record = dict(status=str(m.getStatus()), solver_s=m.getSolvingTime(), budget_s=BUDGET,
                  source_sha256=digest(path), rows=m.getNConss(transformed=False), before=before)
    if m.getNSols():
        sol = m.getBestSol()
        assert m.checkSol(sol, original=True, completely=True)
        result = x.result(solution=sol)
        assert validate(result)["valid"]
        after = metrics(result)
        assert after["cmax"] <= 553.00001 and abs(after["secondary"] - 3.0) < 1e-5
        write(folder/"schedule.json",result)
        record.update(after=after, replay=audit(folder/"schedule.json"))
    m.freeProb()
    return record


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    lock = (OUT/"active.lock").open("a+b")
    try:
        msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError:
        print("The eight-wafer check is already running.", flush=True)
        return
    begin = time.monotonic()
    results = []
    for H in (3, 10):
        path = JMS / f"results/huber_residence_20261125/reuse/epsilon/H{H}_short_cap553/schedule.json"
        folder = OUT / f"H{H}"
        folder.mkdir(exist_ok=True)
        final, attempt = folder/"record.json", folder/"attempt.json"
        sig = [digest(p) for p in (path, Path(__file__), Path(__file__).with_name("extended_model.py"))]
        elapsed = time.monotonic() - begin
        remaining = (2-len(results))*BUDGET
        state = dict(active=H, completed=len(results), failed=0, elapsed_s=elapsed,
                     remaining_s=remaining, estimated_total_s=elapsed+remaining,
                     basis="sequential solver budgets, excluding model construction")
        write(OUT/"status.json", state)
        print(state, flush=True)
        if final.exists():
            row = json.loads(final.read_bytes())
            if row["signature"] != sig:
                raise ValueError("Endpoint source changed")
            if "after" in row:
                assert row["replay"] == audit(folder/"schedule.json")
        else:
            spent = 0
            if attempt.exists():
                last = json.loads(attempt.read_bytes())
                assert last["signature"] == sig
                spent = min(BUDGET, last["charged"] + max(0,time.time()-last["started"]))
            write(attempt, dict(signature=sig, charged=spent, started=time.time()))
            row = run(path, folder, BUDGET-spent)
            row.update(signature=sig, threshold=H)
            write(final, row)
        results.append(row)
    write(OUT/"summary.json", results)
    duration = time.monotonic()-begin
    write(OUT/"status.json", dict(completed=2, failed=0, elapsed_s=duration,
                                  estimated_total_s=duration, remaining_s=0))
    lock.close()


if __name__ == "__main__":
    main()

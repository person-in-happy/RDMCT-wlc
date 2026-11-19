"""Improve the certified stage-B incumbent across several simultaneous robot-order changes."""
import argparse
import os
from pathlib import Path
import sys
import time

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import experiment as first
from idle import ChamberIdle, GAP
from patterns import travel
from resources import limit_process, peers, sample, wait_for_headroom

old = first.old
OUT = old.JMS/"results/scale75_idle_gap0p01pct_D_20261119_r2"


class OrderMix(ChamberIdle):
    alternative = None

    def add_order(self, model, times, ref, window):
        if self.alternative is None:
            return super().add_order(model, times, ref, window)
        for a, b, lag in sorted(self.edges):
            model.add(times[b] >= times[a]+lag)
        choices = 0
        for resource, items in self.resources.items():
            robot = resource in ("ATR", "VTR")
            main = sorted(items, key=lambda x:(ref[x[0]], x[0]))
            alt = sorted(items, key=lambda x:(self.alternative[x[0]], x[0]))
            rank = {item:i for i,item in enumerate(alt)}

            def lag(left, right):
                if not robot:
                    return left[2]
                a, b = self.actions[left[0]], self.actions[right[0]]
                return left[2]+int(travel(self.cfg, resource, a.location, b.location, b.kind))

            for j, right in enumerate(main):
                frontier = {}
                for left in reversed(main[:j]):
                    loc = self.actions[left[0]].location if robot else resource
                    if rank[left] < rank[right]:
                        # A later common predecessor at the same location dominates this arc.
                        if rank[left] > frontier.get(loc, -1):
                            model.add(times[right[0]] >= times[left[1]]+lag(left,right))
                            frontier[loc] = rank[left]
                    else:
                        direction = model.new_bool_var("")
                        model.add(times[right[0]] >= times[left[1]]+lag(left,right)).only_enforce_if(direction)
                        model.add(times[left[0]] >= times[right[1]]+lag(right,left)).only_enforce_if(~direction)
                        model.add_hint(direction, 1)
                        choices += 1
        return choices


def steps():
    # Proposals explore equipment orders. They enter the result only through a guarded idle solve.
    work = [("head", 0, 900, 340, 8), ("head_peak", 0, 710, 420, 8), ("tail", 640, 0, 400, 8)]
    for sweep in range(3):
        width = (820, 980, 1060)[sweep]
        anchors = list(range((0, 240, 50)[sweep], 6200, width-150))
        if sweep%2:
            anchors.reverse()
        for index, anchor in enumerate(anchors):
            work.append(("proposal", anchor, width, (170, 230, 280)[sweep], 3.5))
            if (index+1)%3 == 0 or index+1 == len(anchors):
                work.append(("combine", 0, 0, 0, 9))
        work.extend([("head_peak", 0, 820, 370, 8), ("tail", 620, 0, 750, 8)])
    work.extend([("certify",0,0,0,50), ("longest",0,0,0,16), ("waiting",0,0,0,22)])
    return work


def protocol():
    prior_record = old.read(first.OUT/"summary.json")
    for name, digest in prior_record["artifact_sha256"].items():
        if old.digest(first.OUT/name) != digest:
            raise ValueError(f"Changed first stage-B pass: {name}")
    source = first.protocol()
    if old.fingerprint(source) != prior_record["protocol_sha256"]:
        raise ValueError("First pass protocol mismatch")
    return dict(upstream_protocol=source, first_pass_summary=old.digest(first.OUT/"summary.json"),
                source_sha256=old.digest(Path(__file__)), steps=steps(), stage_B_relative_gap=GAP,
                method="CP-SAT on resource orders shared by two proposals; physical replay for accepted schedules")


def search(out, token, engine, blocks, baseline, lower, pause_after):
    file = out/"checkpoint.json"
    if file.exists():
        state = old.restore(file, token)
    else:
        base = old.read(first.OUT/"summary.json")
        seed = old.restore(first.OUT/"checkpoint.json",base["protocol_sha256"])["starts"]
        state = dict(starts=seed, explore=seed, records=[])
        old.checkpoint(file, token, state)
    _, metrics, _, _ = first.check_schedule(engine, blocks, state["starts"])
    work = steps()
    for index in range(len(state["records"]),len(work)):
        wait_for_headroom()
        label, a, width, band, budget = work[index]
        ref = state["starts"]
        current = engine.measure(ref)
        accepted = False
        if label == "proposal":
            parent = state["explore"]
            end = engine.finish(parent)
            lo = min(a, max(0, end-width//2))
            proposed, row = engine.solve(parent, lo, min(end+1,lo+width), band, budget)
            state["explore"] = proposed
        else:
            window = first.FIXED
            purpose = "idle"
            if label.startswith("head"):
                window = (a, a+width, band)
            elif label == "tail":
                window = (current["cmax"]-a, current["equipment_end"]+1, band)
            if label == "combine":
                engine.alternative = state["explore"]
            if label in ("head_peak","longest"):
                purpose = "longest"
            elif label == "waiting":
                purpose = "waiting"
            try:
                candidate, row = engine.solve_idle(ref, baseline, lower, window, budget, purpose)
            finally:
                engine.alternative = None
            if candidate != ref:
                _, candidate_metrics, _, _ = first.check_schedule(engine, blocks, candidate)
                accepted = first.ranking(row["metrics"], candidate_metrics) < first.ranking(current, metrics)
                if accepted:
                    state["starts"], metrics = candidate, candidate_metrics
            if label != "combine" or accepted:
                state["explore"] = state["starts"]
        best = engine.measure(state["starts"])
        state["records"].append(dict(step=label, accepted=accepted, incumbent=best, solve=row))
        old.checkpoint(file, token, state)
        remaining = sum(s[-1] for s in work[index+1:])
        first.prior.report(out, "secondary", completed=index+1, total=len(work), failed=0,
                           budget_remaining_s=remaining, metrics=best)
        print(f"{index+1}/{len(work)} {label} {row['status']} failed=0 | idle={best['idle']}s "
              f"Cmax={best['cmax']}s | search budget remaining {remaining:.0f}s", flush=True)
        if pause_after == index+1:
            raise KeyboardInterrupt
    return state


def verify(out):
    saved = old.read(out/"summary.json")
    token = old.fingerprint(protocol())
    if token != saved["protocol_sha256"] or token != old.fingerprint(old.read(out/"campaign.json")):
        raise ValueError("Extended protocol mismatch")
    for name, digest in saved["artifact_sha256"].items():
        if old.digest(out/name) != digest:
            raise ValueError(f"Changed output: {name}")
    cfg, blocks, seed = first.restore_seed()
    engine = OrderMix(cfg, blocks)
    state = old.restore(out/"checkpoint.json", token)
    data, metrics, replay, lanes = first.check_schedule(engine, blocks, state["starts"])
    certificate = old.read(out/"original_row_audit/certificate.json")
    if (saved["baseline"] != engine.measure(seed) or saved["new"] != engine.measure(state["starts"])
            or saved["recipe_metrics"] != metrics or saved["replay"] != replay or data != old.read(out/"result.json")
            or old.fingerprint(lanes) != old.fingerprint(saved["utilization"])
            or certificate["status"] != "all_original_rows_satisfied"
            or certificate["result_sha256"] != old.digest(out/"result.json")):
        raise ValueError("Extended schedule verification failed")
    print(f"Verified {replay['checks']:,} replay checks, certificate for {certificate['original_rows']:,} rows, "
          "and the frozen 0.1% and stage-B artifacts.", flush=True)


def run(out, pause_after):
    with old.output_lock(out):
        spec = protocol()
        token = old.fingerprint(spec)
        if (out/"campaign.json").exists():
            if old.fingerprint(old.read(out/"campaign.json")) != token:
                raise ValueError("Output belongs to a different experiment")
        elif any(p.name not in (".run.lock","campaign.json.tmp") for p in out.iterdir()):
            raise ValueError("Choose an isolated output directory")
        else:
            old.dump(out/"campaign.json", spec)
        if (out/"summary.json").exists():
            verify(out)
            return
        attempt = dict(started_utc=old.stamp(), pid=os.getpid(), parallel_experiments=peers())
        ledger = out/f"attempt_{time.time_ns()}.json"
        old.dump(ledger, attempt)
        try:
            wait_for_headroom()
            cfg, blocks, seed = first.restore_seed()
            engine = OrderMix(cfg, blocks)
            base = old.read(first.OUT/"summary.json")
            baseline = engine.measure(seed)
            lower = base["global_primary_lower_bound"]
            print(f"75 products | 1 worker | 1 GiB process | stage-B gap={100*GAP:g}% | "
                  f"continuing at {base['new']['idle']} idle seconds", flush=True)
            state = search(out,token,engine,blocks,baseline,lower,pause_after)
            search_resource = sample()
            current = engine.measure(state["starts"])
            data, metrics, replay, lanes = first.check_schedule(engine, blocks, state["starts"])
            old.dump(out/"result.json", data)
            first.prior.report(out,"original_model_audit",metrics=current)
            print("Auditing full original model and rendering", flush=True)
            wait_for_headroom()
            cert = first.prior.audit_result(out,token,data)
            from figures import draw
            figures = draw(data,lanes,out/"figures")
            proof = next(r["solve"] for r in state["records"] if r["step"] == "certify")
            bound = proof["conditional_lower_bound"]
            gap = (current["idle"]-bound)/max(1,current["idle"])
            if gap < -1e-9:
                raise ValueError("Final incumbent below its conditional bound")
            names = ["campaign.json","result.json","checkpoint.json","original_row_audit/certificate.json",
                     "original_row_audit/assignment.json.gz"]+["figures/"+f for f in figures["files"]]
            if old.fingerprint(protocol()) != token:
                raise ValueError("Frozen evidence changed during extension")
            result = dict(state="completed", protocol_sha256=token, objective=base["objective"],
                          stage_B_relative_gap=GAP, baseline=baseline, new=current, first_pass=base["new"],
                          baseline_recipe_metrics=base["baseline_recipe_metrics"], recipe_metrics=metrics,
                          utilization=lanes, replay=replay, global_primary_lower_bound=lower,
                          fixed_order_report=dict(integer_seconds=True, lower_bound=bound, upper_bound=current["idle"],
                                                  relative_gap=gap, target_met=gap <= GAP+1e-12, status=proof["status"]),
                          unrestricted_idle_lower_bound=base["unrestricted_idle_lower_bound"],
                          unrestricted_secondary_gap_certified=False, full_model_rows_checked=cert["original_rows"],
                          search_resources=search_resource, resources=sample(), figures=figures,
                          artifact_sha256={n:old.digest(out/n) for n in names}, ended_utc=old.stamp())
            old.dump(out/"summary.json", result)
            first.prior.report(out,"completed",completed=1,failed=0,metrics=current)
            attempt["outcome"] = "completed"
            print(f"Complete 1/1 failed=0 ETA=0 | {current}", flush=True)
        except KeyboardInterrupt:
            attempt["outcome"] = "paused"
            first.prior.report(out,"paused")
        except Exception as exc:
            attempt["outcome"] = "failed"
            first.prior.report(out,"failed",error=repr(exc))
            raise
        finally:
            attempt.update(ended_utc=old.stamp(), resources=sample())
            old.dump(ledger,attempt)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action",choices=("run","resume","verify","status"))
    parser.add_argument("--out",type=Path,default=OUT)
    parser.add_argument("--pause-after",type=int)
    args = parser.parse_args()
    out = args.out.resolve()
    if args.action == "status":
        import json
        print(json.dumps(old.read(out/"progress.json") if (out/"progress.json").exists() else {"stage":"new"},indent=2))
    elif args.action == "verify":
        verify(out)
    elif out.parent == old.JMS/"results" and out not in (old.DEFAULT, first.BASE, first.OUT):
        handle = limit_process()
        run(out,args.pause_after)
    else:
        parser.error("Use a separate output directory directly under JMS-version/results")

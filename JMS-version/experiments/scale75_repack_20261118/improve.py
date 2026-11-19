"""Repack the frozen 75-product instance, then certify and plot the accepted schedule."""
import argparse
import gzip
import json
from importlib.metadata import version
from pathlib import Path
import sys
import time

HERE = Path(__file__).resolve().parent
OLD = HERE.parent/"scale75_20261118"
sys.path.insert(0, str(OLD))
import run as old
from resources import limit_process, peers, sample, wait_for_headroom
from search import Search, fixed_timing, flexible_blocks, utilization, workload_bound
from neighborhood import WindowSearch, window_sequence

OUT = old.JMS/"results/scale75_repack_D_20261118_r1"
TARGET = .001
# Each tuple gives sweep window width, robot reorder band, seconds per window, direction.
SWEEPS = [(560, 100, 2.5, False), (760, 140, 4., True), (660, 130, 3., False),
          (940, 160, 5., True)]
STRATUM_WIDTH = 14


def protocol():
    base = old.DEFAULT
    summary = old.read(base/"summary.json")
    original = old.read(base/"campaign.json")
    for key, digest in summary["sha256"].items():
        if old.digest(base/key) != digest:
            raise ValueError(f"Changed baseline output {key}")
    for key, digest in original["source_sha256"].items():
        if old.digest(old.JMS.parent/key) != digest:
            raise ValueError(f"Changed baseline implementation {key}")
    cert = old.read(base/"original_row_audit/certificate.json")
    if cert["input_sha256"]["result.json"] != summary["sha256"]["result.json"] or cert["status"] != "all_original_rows_satisfied":
        raise ValueError("Baseline audit and result disagree")
    assets = [HERE/n for n in ("improve.py","neighborhood.py","search.py")]
    assets += [OLD/"audit/check_model.py", old.TOOLS/"incumbent_sublevel.py"]
    return dict(config=original["config"], baseline_case=base.name, baseline_sha256=summary["sha256"]["result.json"],
                baseline_summary_sha256=old.digest(base/"summary.json"), baseline_certificate_sha256=old.digest(base/"original_row_audit/certificate.json"),
                original_protocol_sha256=old.fingerprint(original), paired_within_same_instance=True, sweeps=SWEEPS,
                stratum_width=STRATUM_WIDTH, global_certificate_target=TARGET, restricted_cp_relative_gap=TARGET,
                workers=1, cpu_threads=1, memory_limit_mib=1024, gpu=False, python=sys.version,
                versions={k:version(k) for k in ("ortools","pyscipopt","numpy","matplotlib","psutil")},
                source_sha256={p.relative_to(old.JMS.parent).as_posix():old.digest(p) for p in assets})


def report(out, stage, **fields):
    old.dump(out/"progress.json", dict(stage=stage, utc=old.stamp(), resources=sample(), **fields))


def group_search(out, token, packing):
    path = out/"groups.json"
    beam, depth = [()], 0
    if path.exists():
        state = old.restore(path, token)
        beam = [tuple(map(tuple,plan)) for plan in state["beam"]]
        depth = state["depth"]
    begin, first = time.monotonic(), depth
    while depth < packing.n:
        wait_for_headroom()
        beam = packing.next_layer(beam, STRATUM_WIDTH)
        depth += 1
        old.checkpoint(path, token, dict(depth=depth,beam=beam))
        eta = (time.monotonic()-begin)*(packing.n-depth)/(depth-first)
        print(f"Group search {depth}/{packing.n} failed=0 ETA={eta:.1f}s",flush=True)
        report(out, "group_search", completed=depth, total=packing.n)
    return beam


def seed_state(out, token, packing, reference):
    beam = group_search(out,token,packing)
    source = old.read(old.DEFAULT/"search.json")["payload"]["beam"][0]
    old_plan = tuple(map(tuple,source))
    best = (reference["cmax"], old_plan, old.read(old.DEFAULT/"timing_B.json")["payload"]["starts"])
    for plan in beam:
        if packing.extent(plan) > packing.cfg.horizon:
            continue
        blocks = flexible_blocks(packing, plan)
        starts = [at+t for (_,_,at),p in zip(plan,blocks) for t in p.times]
        model = fixed_timing(packing.cfg,blocks,starts)
        row = model.solve("A",starts)
        if row["objective"] < best[0]:
            best = (row["objective"],plan,row["starts"])
    obj, plan, starts = best
    if any(abs(t-round(t))>1e-8 for t in starts):
        raise ValueError("The initial fixed-order optimum needs an integer event witness")
    starts = [round(t) for t in starts]
    timing = fixed_timing(packing.cfg,flexible_blocks(packing,plan),starts)
    old.tested_metrics(timing.schedule(starts))
    print(f"Best feasible starting structure {obj:g}s | baseline {reference['cmax']:g}s",flush=True)
    return dict(plan=plan, starts=starts, initial_cmax=obj, sweep=0, index=0, windows=[], records=[])


def optimize(out, token, packing, reference, bound, pause_after):
    path = out/"windows.json"
    if path.exists():
        state = old.restore(path,token)
    else:
        state = seed_state(out,token,packing,reference)
        old.checkpoint(path,token,state)
    blocks = flexible_blocks(packing,state["plan"])
    search = WindowSearch(packing.cfg,blocks)
    print(f"Resuming at {len(state['records'])} completed windows | Cmax={search.finish(state['starts'])}s",flush=True)
    while state["sweep"] < len(SWEEPS) and search.finish(state["starts"]) > bound*(1+TARGET):
        s = state["sweep"]
        width, band, seconds, reverse = SWEEPS[s]
        if not state["windows"]:
            state["windows"] = window_sequence(search.finish(state["starts"]),width,reverse)
        windows = state["windows"]
        for index in range(state["index"],len(windows)):
            wait_for_headroom()
            lo,hi = windows[index]
            proposed,row = search.solve(state["starts"],lo,hi,band,seconds)
            if row["upper_after"] < row["upper_before"]:
                witness = fixed_timing(packing.cfg,blocks,proposed).schedule(proposed)
                old.tested_metrics(witness)
                state["starts"] = proposed
            state["records"].append(dict(sweep=s+1, **row))
            state["index"] = index+1
            old.checkpoint(path,token,state)
            upper = search.finish(state["starts"])
            remaining = seconds*(len(windows)-index-1)
            print(f"Sweep {s+1}/{len(SWEEPS)} window {index+1}/{len(windows)} failed=0 | "
                  f"Cmax={upper}s | sweep budget remaining ~{remaining:.0f}s",flush=True)
            report(out,"window_search",sweep=s+1,window=index+1,windows=len(windows),
                   completed_windows=len(state["records"]),cmax=upper)
            if len(state["records"]) == pause_after:
                raise KeyboardInterrupt
            if upper <= bound*(1+TARGET):
                break
        state.update(sweep=s+1,index=0,windows=[])
        old.checkpoint(path,token,state)
    return state,blocks


def refine(cfg,blocks,starts):
    # For fixed resource orders all event times are jointly optimized. Retain
    # the best integer witness if the continuous B minimum uses fractional times.
    model = fixed_timing(cfg,blocks,starts)
    a = model.solve("A",starts)
    b = model.solve("B",a["starts"],a["objective"])
    choices = []
    for name,times in (("window",starts),("A",a["starts"]),("B",b["starts"])):
        if max(abs(t-round(t)) for t in times)>1e-8:
            continue
        schedule = model.schedule([round(t) for t in times])
        metrics,_ = old.tested_metrics(schedule)
        choices.append((metrics["cmax"],metrics["secondary"],name,schedule))
    if not choices:
        raise ValueError("No validated integer-second incumbent")
    _,_,chosen,data = min(choices, key=lambda x:(x[0],x[1], x[2]!="B"))
    phases = {stage:{k:v for k,v in row.items() if k!="starts"} for stage,row in (("A",a),("B",b))}
    return data,dict(chosen=chosen, phases=phases)


def verify(out):
    summary = old.read(out/"summary.json")
    if old.fingerprint(protocol()) != summary["protocol_sha256"]:
        raise ValueError("Frozen protocol mismatch")
    for key,digest in summary["artifact_sha256"].items():
        if old.digest(out/key) != digest:
            raise ValueError(f"Changed artifact {key}")
    result = old.read(out/"result.json")
    metrics, replay = old.tested_metrics(result)
    audit = old.read(out/"original_row_audit/certificate.json")
    cfg=old.Config(**old.read(old.DEFAULT/"campaign.json")["config"])
    if (metrics != summary["new_metrics"] or replay != summary["replay"]
            or result["config"] != old.read(old.DEFAULT/"result.json")["config"]
            or old.fingerprint(utilization(result)) != old.fingerprint(summary["new_utilization"])
            or workload_bound(cfg) != summary["global_workload_lower_bound"]
            or audit["result_sha256"] != old.digest(out/"result.json") or audit["status"] != "all_original_rows_satisfied"):
        raise ValueError("Independent result verification failed")
    print(f"Verified {replay['checks']:,} replay checks and stored certificate for {audit['original_rows']:,} original rows.",flush=True)


def audit_result(out,token,data):
    from audit.check_model import evaluate,native_crosscheck
    dest = out/"original_row_audit"
    dest.mkdir(exist_ok=True)
    cert_path = dest/"certificate.json"
    result_sha = old.digest(out/"result.json")
    if cert_path.exists():
        cert = old.read(cert_path)
        if (cert["protocol_sha256"]!=token or cert["result_sha256"]!=result_sha
                or cert["assignment_sha256"]!=old.digest(dest/"assignment.json.gz")):
            raise ValueError("Certificate mismatch")
        return cert
    native = native_crosscheck()
    rows,delta = evaluate(data,verbose=True)
    tmp, archive = dest/"assignment.json.gz.tmp",dest/"assignment.json.gz"
    with gzip.open(tmp,"wt",encoding="utf-8",compresslevel=4) as f:
        json.dump(dict(default=0,nonzero_values=rows.nonzero),f,separators=(",",":"),sort_keys=True)
    tmp.replace(archive)
    cert = dict(status="all_original_rows_satisfied",full_candidate_space=True,products=75,cmax=data["cmax"],
                variables=sum(rows.types.values()), nonzero_variables=len(rows.nonzero), original_rows=rows.rows,
                variable_types=dict(rows.types), max_variable_rounding_s=delta, native_scip_crosscheck=native,
                native_75_scip_checkSol=False, global_optimality_claim=False, protocol_sha256=token,
                result_sha256=result_sha, assignment_sha256=old.digest(archive), resources=sample(),utc=old.stamp())
    old.dump(cert_path,cert)
    return cert


def execute(out,pause_after):
    spec = protocol()
    token = old.fingerprint(spec)
    with old.output_lock(out):
        if (out/"campaign.json").exists():
            if old.fingerprint(old.read(out/"campaign.json")) != token:
                raise ValueError("Protocol changed. Use a new output directory.")
        elif any(p.name not in (".run.lock","campaign.json.tmp") for p in out.iterdir()):
            raise ValueError("Use an isolated result directory")
        else:
            old.dump(out/"campaign.json",spec)
        if (out/"summary.json").exists():
            verify(out)
            return
        started = time.monotonic()
        attempt = dict(started_utc=old.stamp(),peers=peers(),resources_at_start=sample())
        ledger = out/f"attempt_{time.time_ns()}.json"
        old.dump(ledger,attempt)
        try:
            cfg = old.Config(**spec["config"])
            lower = workload_bound(cfg)
            reference = old.read(old.DEFAULT/"result.json")
            baseline,_ = old.tested_metrics(reference)
            wait_for_headroom()
            solution_file = out/"accepted.json"
            if solution_file.exists():
                accepted = old.restore(solution_file,token)
                if old.digest(out/"result.json") != accepted["result_sha256"]:
                    raise ValueError("Changed accepted schedule")
                data = old.read(out/"result.json")
            else:
                state,blocks = optimize(out, token, Search(cfg), baseline, lower["seconds"], pause_after)
                data,phases = refine(cfg,blocks,state["starts"])
                if data["cmax"] > baseline["cmax"]:
                    raise ValueError("Increased primary objective")
                old.dump(out/"result.json",data)
                accepted = dict(refine=phases, initial_cmax=state["initial_cmax"], windows=len(state["records"]),
                                result_sha256=old.digest(out/"result.json"), search_resources=sample())
                old.checkpoint(solution_file,token,accepted)
            metrics,replay = old.tested_metrics(data)
            wait_for_headroom()
            report(out,"original_model_audit",cmax=data["cmax"])
            print("Checking the full original model at the saved feasible assignment",flush=True)
            cert = audit_result(out,token,data)
            report(out,"gantt",cmax=data["cmax"])
            from plot import draw
            staging = out/".rendering"
            figmeta = draw(data,staging)
            figdir = out/"figures"
            figdir.mkdir(exist_ok=True)
            names = ["gantt_resources.png","gantt_resources.pdf","gantt_resources.svg","gantt_details.pdf"]
            for name in names:
                (staging/name).replace(figdir/name)
            staging.rmdir()
            files = ["campaign.json","result.json","accepted.json","groups.json","windows.json",
                     "original_row_audit/certificate.json","original_row_audit/assignment.json.gz"]+["figures/"+n for n in names]
            upper = metrics["cmax"]
            gap = (upper-lower["seconds"])/lower["seconds"]
            record = dict(state="completed",scope="single-instance makespan improvement; restricted CP-SAT neighborhoods",
                          baseline_metrics=baseline,new_metrics=metrics,baseline_utilization=utilization(reference),
                          new_utilization=utilization(data), global_workload_lower_bound=lower,
                          target_global_relative_gap=TARGET, certified_relative_gap_upper_bound=gap,
                          global_target_certified=gap<=TARGET, unrestricted_solver_gap=None,
                          global_optimality_claim=False,learned_cut_selection=False, replay=replay,
                          full_model_rows_checked=cert["original_rows"],figures=figmeta,search=accepted,
                          process_resources=sample(), protocol_sha256=token,
                          artifact_sha256={n:old.digest(out/n) for n in files}, ended_utc=old.stamp())
            old.dump(out/"summary.json",record)
            report(out,"completed",completed=1,failed=0,cmax=upper)
            attempt["outcome"]="completed"
            print(f"Complete=1/1 failed=0 ETA=0 | Cmax {baseline['cmax']:g} -> {upper:g}s",flush=True)
        except KeyboardInterrupt:
            attempt["outcome"]="paused"
            report(out,"paused")
            print("Paused; Resume checks the last complete search layer or window.",flush=True)
        except Exception as exc:
            attempt["outcome"]="failed"
            report(out,"failed",error=repr(exc))
            raise
        finally:
            attempt.update(elapsed_s=time.monotonic()-started, ended_utc=old.stamp(),resources_at_end=sample())
            old.dump(ledger,attempt)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action",choices=("run","resume","verify","status"))
    parser.add_argument("--out",type=Path,default=OUT)
    parser.add_argument("--pause-after-windows",type=int)
    args=parser.parse_args()
    out=args.out.resolve()
    if args.action=="status":
        print(json.dumps(old.read(out/"progress.json") if (out/"progress.json").exists() else {"stage":"new"},indent=2))
        return
    if args.action=="verify":
        verify(out)
        return
    results=old.JMS/"results"
    if out==results or not out.is_relative_to(results) or out.is_relative_to(old.DEFAULT):
        parser.error("Use a separate directory under JMS-version/results")
    job_handle=limit_process()
    execute(out,args.pause_after_windows)


if __name__=="__main__":
    main()

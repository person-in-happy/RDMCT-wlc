"""Per-seed experiments using the frozen Table 4 and paired Table 5 inputs."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import time

HERE = Path(__file__).resolve().parent
JMS = HERE.parents[1]
RES = JMS / "results"
OUT = RES / HERE.name
ONE = RES / "table4_one_percent_20261124"
TEN = RES / "table4_three_arms_20261124"
LEGACY = RES / "table4_residence100_20261123"
MATCHED = RES / "table5_matched_target_20261124"
OLD5 = RES / "table5_one_percent_20261124"
SEEDS = (1, 2, 3)
CELLS = ((2, 3), (4, 3), (4, 10), (8, 3), (8, 10))
METHODS = ("no_rerank", "no_spbs", "hem", "scip_default")
EPS = 0.0002


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf8")
    publish_file(tmp,path)


def publish_file(temporary,target):
    for attempt in range(12):
        try:
            temporary.replace(target)
            return
        except PermissionError:
            if attempt==11:
                raise
            time.sleep(.03*(attempt+1))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def folder(key):
    return OUT / "runs" / key


def reference(seed):
    root = OLD5 if seed in (1, 2) else MATCHED / "references"
    return root / f"runs/s{seed}_full/1pct"


def case(n, h):
    return f"D_n{n}_H{h}_mixed_dual"


def primary_source(n, h, seed, level):
    rel = Path("runs") / f"{case(n,h)}__s{seed}/A/endpoint.json"
    if level == 1:
        file = ONE / rel
        if not file.exists():
            dest = folder(f"primary_{n}_{h}_{seed}")
            return (dest, dest / "primary.json")
    else:
        file = LEGACY / rel
        if not file.exists():
            file = TEN / rel
    record = read(file)
    loc = next(r for r in [ONE, LEGACY, TEN] if file.is_relative_to(r)) / record["path"]
    assert sha(loc/"schedule.json") == record["schedule_sha256"]
    assert sha(loc/"assignment.json.gz") == record["assignment_sha256"]
    assert record["actual_gap"] <= level / 100 + 1e-8
    return loc, file


def stage_a(n, h, seed, dest):
    if HERE.name=="quota_objective_20261125":
        previous=RES/"residence_objective_20261125/runs"/f"primary_{n}_{h}_{seed}"
        source=read(previous/"primary.json")
        assert source["replay"]["valid"] and source["rows"]>0
        assert source["schedule_sha256"]==sha(previous/"schedule.json")
        assert source["assignment_sha256"]==sha(previous/"assignment.json.gz")
        assert read(previous/"schedule.json")["config"]==read(ONE/"inputs"/case(n,h)/"input.json")["config"]
        assert source["record"]["upper"]<=1.01*source["record"]["lower"]+EPS
        for name in ("schedule.json","assignment.json.gz","primary.json"):
            shutil.copy2(previous/name,dest/name)
        return dict(record=source["record"],schedule_sha256=source["schedule_sha256"],
                    assignment_sha256=source["assignment_sha256"],reused_source=str(previous.relative_to(JMS)))
    # Restore the old CP projection in this campaign's own directory. Raw old records remain frozen.
    sys.path.insert(0, str(HERE.parent / "table4_one_percent_20261124"))
    from bench import read as old_read, Config, store, import_pair
    from primary import search
    src = ONE / "inputs" / case(n, h)
    spec = old_read(src / "input.json")
    previous = ONE / f"runs/{case(n,h)}__s{seed}/A"
    old_state = previous / "search.json"
    proof_file = OUT/"primary_relaxation/result.json"
    if n==8 and proof_file.is_file():
        proof=read(proof_file)
        engine=HERE/"primary_relaxation.py"
        relaxation_parent=ONE/"runs/D_n8_H3_mixed_dual__s3/A/witness_1795511516834780600/schedule.json"
        assert proof["status"]=="INFEASIBLE" and proof["lower"]==proof["cap"]+1
        assert proof["code_sha256"]==sha(engine) and proof["source_sha256"]==sha(relaxation_parent)
        model_config=read(relaxation_parent)["config"]
        assert {k:v for k,v in model_config.items() if k!="cleaning_interval"}=={
                k:v for k,v in spec["config"].items() if k!="cleaning_interval"}
        assert model_config["cleaning_interval"]==3 and h in (3,10)
        # The validated product-only lower-bound relaxation omits both cleaning thresholds.
        # A missing H10 trajectory uses the same-seed H3 witness through full H10 replay.
        for candidate_root in [previous, ONE/f"runs/{case(n,3)}__s{seed}/A"]:
            for artifact in sorted(candidate_root.glob("witness*/primary.json")):
                parent=read(artifact)
                if not parent["replay"]["valid"] or parent["metrics"]["cmax"]>1.01*proof["lower"]+EPS:
                    continue
                original=artifact.parent
                source_hashes={name:parent[key] for name,key in [
                    ("schedule.json","schedule_sha256"),("assignment.json.gz","assignment_sha256")]}
                checked=import_pair(Config(**spec["config"]),original,source_hashes)
                rec=dict(status="verified_gap", scope="global_product_Cmax",upper=checked[2]["cmax"],
                         lower=proof["lower"],seconds=0.,proof_seconds=proof["wall_seconds"],
                         projection=str(proof_file.relative_to(JMS)),proof_sha256=sha(proof_file),
                         config_sha256=sha(src/"input.json"),witness=str(artifact.relative_to(JMS)),
                         witness_sha256=sha(artifact),same_seed=True,cross_threshold=candidate_root!=previous)
                assert rec["upper"]<=rec["lower"]*1.01+EPS
                store(dest,checked,rec)
                return dict(record=rec,schedule_sha256=sha(dest/"schedule.json"),
                            assignment_sha256=sha(dest/"assignment.json.gz"))
        raise ValueError(f"Missing target-compatible 1% primary witness for {n}/{h}/{seed}")
    if old_state.exists() and not (dest / "search.json").exists():
        state = read(old_state)
        if state.get("witness"):
            old_w = previous / state["witness"]
            shutil.copytree(old_w, dest / state["witness"], dirs_exist_ok=True)
        write(dest / "search.json", state)
    checked, record = search(Config(**spec["config"]), src, dest, seed, spec)
    store(dest, checked, record)
    return dict(reused_checkpoint=str(old_state) if old_state.exists() else None, record=record,
                schedule_sha256=sha(dest/"schedule.json"),assignment_sha256=sha(dest/"assignment.json.gz"))


def full_reference(seed, dest):
    from solver import run
    original = reference(seed)
    earlier = read(original / "result.json")
    assert earlier["verified"] and earlier["seed"] == seed and earlier["arm"] == "full"
    start = time.perf_counter()
    run("fixed", original/"A", dest/"B", seed=seed, gap=.01)
    elapsed = time.perf_counter()-start
    b = read(dest / "B/result.json")
    assert b["eligible"] and b["replay"]["valid"]
    a_seconds = earlier["gate"]["seconds"]
    total = earlier["prep_seconds"] + a_seconds + elapsed
    doc = dict(seed=seed, arm="full", f_A=b["measured"]["cmax"], f_B=b["measured"]["secondary"],
               f_B_handoff=b["initial"]["secondary"], total_s=total, calls=earlier["gate"]["calls"],
               prep_seconds=earlier["prep_seconds"], A_seconds=a_seconds, B_wall_seconds=elapsed,
               parent_A_sha256=sha(original/"A/primary.json"), parent_result_sha256=sha(original/"result.json"),
               new_B_sha256=sha(dest/"B/result.json"), scope="paired new-objective reference")
    write(dest/"timing.json",doc)
    return doc


def four(n, h, seed, level, arm, dest):
    from solver import run
    from score import metrics
    if arm == "fixed":
        src, source_proof = primary_source(n,h,seed,level)
    else:
        src = ONE / "inputs" / case(n,h) / "A"
        source_proof = src/"primary.json"
        if level == 10:
            old_input = LEGACY/"inputs"/case(n,h)
            # The 10% controls share the archived original input with the A arm.
            manifest = read(old_input/"input.json")
            candidates = [p.parent for p in old_input.rglob("schedule.json")
                          if sha(p)==manifest["schedule_sha256"]]
            if not candidates:
                physical = old_input/"schedule.json"
                if physical.exists() and sha(physical)==manifest["schedule_sha256"]:
                    candidates = [old_input]
            if not candidates:
                raw = Path(manifest.get("source",""))
                if raw.is_dir() and (raw/"schedule.json").is_file():
                    candidates=[raw]
            if not candidates:
                raise ValueError(f"Missing common 10% start for {n}, {h}: {manifest.keys()}")
            src = candidates[0]
            source_proof = old_input/"input.json"
    measured = metrics(read(src/"schedule.json"))
    # Share only completed global certificates with an identical configuration. Each A/B handoff
    # retains its own seed, structure and makespan bound. No timings are attributed to reused solutions.
    warm = []
    if arm == "free":
        pool = OUT/"warm_pool.json"
        if pool.exists():
            for path in read(pool).get(case(n,h), []):
                candidate = Path(path)
                if (candidate/"assignment.json.gz").exists():
                    warm.append(candidate)
    run(arm, src, dest/"B", seed=seed, gap=level/100, warm=warm)
    b = read(dest/"B/result.json")
    if not b["replay"]["valid"]:
        raise ValueError("Missing physical replay")
    if not b["eligible"]:
        raise ValueError(f"New objective gap {b['record']['gap']} exceeds {level}%")
    return dict(n=n, H=h, seed=seed, gap_percent=level, arm=arm, source=str(src.relative_to(JMS)),
                parent=sha(source_proof), initial=measured, measured=b["measured"], record=b["record"],
                result_sha256=sha(dest/"B/result.json"))


def tasks():
    result = [f"ref5_{s}" for s in SEEDS]
    # Start restored short B solves promptly. After an optimum their waiting
    # windows can overlap with other methods using the released CPU slots.
    result.extend(f"t5_3_{a}" for a in ("hem","no_spbs","no_rerank","scip_default"))
    for s in SEEDS:
        if s!=3:
            result.extend(f"t5_{s}_{a}" for a in METHODS)
    if HERE.name=="quota_objective_20261125":
        fast_or_shared=["t5_1_hem","t5_1_no_rerank","t5_1_scip_default","t5_2_scip_default"]
        result=[j for j in result if not j.startswith("t5_")]+fast_or_shared+[
            j for j in result if j.startswith("t5_") and j not in fast_or_shared]
    for level in (10,1):
        for arm in ("fixed","free"):
            for n,h in CELLS:
                if level == 10 and n == 2:
                    continue
                result.extend(f"t4_{level}_{n}_{h}_{s}_{arm}" for s in SEEDS)
    result.extend(f"primary_8_{h}_{s}" for h in (3,10) for s in SEEDS)
    return result


def ready(key):
    w = key.split("_")
    if w[0] == "primary":
        return True
    if not (HERE/"solver.py").is_file() or not (HERE/"score.py").is_file():
        return False
    if w[0] == "t5":
        return (folder("ref5_"+w[1])/"complete.json").is_file() and (HERE/"paired.py").is_file()
    if w[0] == "t4" and w[1] == "1" and w[2] == "8" and w[-1] == "fixed":
        return (folder("_".join(["primary",*w[2:5]]))/"complete.json").is_file()
    return True


def passive_reuse(key):
    current=folder(key)/"progress.json"
    if key.startswith("t5_") and current.is_file() and read(current).get("exhausted"):
        return True
    if HERE.name!="quota_objective_20261125" or key not in {"t5_3_hem","t5_3_no_rerank","t5_3_no_spbs"}:
        return False
    source=RES/"residence_objective_20261125/runs"/key/"progress.json"
    return source.exists() and read(source).get("exhausted",False)


def execute(key):
    dest = folder(key)
    dest.mkdir(parents=True, exist_ok=True)
    w = key.split("_")
    start = time.time()
    if w[0] == "primary":
        report = stage_a(*map(int,w[1:4]),dest)
    elif w[0] == "ref5":
        report = full_reference(int(w[1]),dest)
    elif w[0] == "t5":
        from paired import compare
        report = compare(int(w[1]),"_".join(w[2:]),dest)
    else:
        level,n,h,s = map(int,w[1:5])
        report = four(n,h,s,level,w[-1],dest)
    write(dest/"complete.json",dict(key=key, wall_seconds=time.time()-start, report=report))


if __name__ == "__main__":
    if sys.argv[1] not in tasks():
        raise ValueError(sys.argv[1])
    execute(sys.argv[1])

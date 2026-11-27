"""Independently replay the physical events of this five-case campaign."""
import argparse
import gzip
import hashlib
import json
import math
import msvcrt
from pathlib import Path
import sys
import time
import uuid

HERE = Path(__file__).resolve().parent
JMS = HERE.parents[1]
sys.path.insert(0, str(HERE.parent / "terminal_unload_20261125"))
from replay_events import raw_objectives, validate

CASES = {"n2_h3": (2, 3, 324), "n4_h3": (4, 3, 397),
         "n8_h3": (8, 3, 552), "n16_h3": (16, 3, 716), "n16_h10": (16, 10, 716)}
TOL = 2e-4
PROOF_TOL = 1e-6 + 1e-9


def read(path):
    raw = path.read_bytes()
    return json.loads(gzip.decompress(raw) if path.suffix == ".gz" else raw)


def audit_schedule(data, case):
    n, threshold, primary_lower = CASES[case]
    replay = validate(data)
    if not replay["valid"]:
        raise ValueError((case, replay["errors"][:5]))
    cfg = data["config"]
    products = {j["identity"] for j in data["jobs"] if j["product"]}
    counts = cfg["load_ports"].values()
    if (len(products) != n or cfg["cleaning_interval"] != threshold
            or sum(x.get("2x2", 0) for x in counts) != n // 2 or cfg["dummy_count"] != 8):
        raise ValueError(f"Input dimensions differ for {case}")
    measured = raw_objectives(data)
    if (not all(math.isfinite(x) for x in measured.values())
            or measured["cmax"] < primary_lower - TOL or measured["secondary"] < 3 - TOL
            or abs(measured["cmax"] - replay["product_return_cmax"]) > TOL):
        raise ValueError(f"Physical event metrics or physical lower bound disagree for {case}")
    cycles = {(x["chamber"], x["index"]): x for x in data["cycles"]}
    unloads = {e["pair"]: e for e in data["events"] if e["kind"] == "pair_unload"}
    events = {e["name"]: e for e in data["events"]}
    pairs = {p["id"]: set(p["members"]) for p in data["pairs"]}
    turns = [e for e in data["events"] if e["name"].startswith("rot_priority_")]
    for turn in turns:
        c, q = turn["chamber"], turn["cycle"]
        cycle = cycles[c, q]
        front = cycle["front"]
        rear, = (p for p in cycle["pairs"] if p != front)
        if pairs[front] & products or not pairs[rear] & products:
            raise ValueError(f"Product-first unload used on an ineligible pair in {case}")
        chain = [cycle, turn, unloads[rear], events[f"rot_after_{c}_{q}"], unloads[front]]
        if any(a["end"] > b["start"] + TOL for a, b in zip(chain, chain[1:])):
            raise ValueError(f"Invalid product-first unload timing for {case}")
    return dict(**measured, physical_checks=replay["checks"], priority_turns=len(turns))


def audit_endpoint(folder, name, case):
    path = folder / name
    metadata = read(path)
    sched = path.with_name("schedule.json.gz")
    digest = hashlib.sha256(sched.read_bytes()).hexdigest()
    if digest != metadata["hashes"]["schedule.json.gz"] or metadata["key"] != case:
        raise ValueError(f"Schedule hash mismatch at {path}")
    schedule = read(sched)
    source = read(folder / "spec.json")["config"]
    for field in set(source) | set(schedule["config"]):
        if field not in {"max_pairs", "max_cycles"} and source.get(field) != schedule["config"].get(field):
            raise ValueError(f"Equipment or Pjob configuration changed at {path}: {field}")
    measured = audit_schedule(schedule, case)
    for key in ("cmax", "secondary"):
        if abs(measured[key] - metadata["record"]["metrics"][key]) > TOL:
            raise ValueError(f"Solver and independent event objectives disagree at {path}")
    return dict(path=name, schedule_sha256=digest,
                stage_global_lower=metadata["record"]["global_lower"], **measured)


def run(root):
    reports = {}
    pending = []
    for case in CASES:
        folder = root / case
        path = folder / "case.json"
        if not path.exists():
            pending.append(case)
            continue
        record = read(path)
        if not record.get("final_endpoint") or record.get("state") != "completed":
            pending.append(case)
            continue
        stages = {}
        for name, stage in record["stages"].items():
            if not stage.get("endpoint"):
                continue
            item = audit_endpoint(folder, stage["endpoint"], case)
            cap = record.get("primary_cap")
            if name.startswith("B") and cap is not None and item["cmax"] > cap + TOL:
                raise ValueError(f"{case} {name} exceeded the handoff makespan")
            if name in ("B1", "B2") and stage.get("certified_global") and item["secondary"] > 3 + TOL:
                raise ValueError(f"{case} {name} does not meet its global physical floor")
            stages[name] = dict(item, stop_reason=stage["stop_reason"],
                                certified_global=bool(stage.get("certified_global")),
                                elapsed_seconds=stage["elapsed_seconds"])
        best = audit_endpoint(folder, record["final_endpoint"], case)
        for name, item in stages.items():
            if (best["cmax"] > item["cmax"] + TOL
                    or (abs(best["cmax"] - item["cmax"]) <= 1e-6
                        and best["secondary"] > item["secondary"] + TOL)):
                raise ValueError(f"{case} final archive misses a better endpoint at {name}")
        if record["elapsed_seconds"] > record["budgets"]["case_wall_s"] + .02:
            raise ValueError(f"{case} exceeded its charged wall budget")
        primary_lower = max(CASES[case][2], stages.get("A", {}).get("stage_global_lower", 0))
        process_lower = max([3] + [s["stage_global_lower"] for key, s in stages.items()
                                    if key.startswith("B")])
        primary_proof = abs(best["cmax"] - primary_lower) <= PROOF_TOL
        process_proof = abs(best["secondary"] - process_lower) <= PROOF_TOL
        exact = None
        if primary_proof and process_proof and CASES[case][0] <= 8:
            from exact_witness import build_witness
            exact = build_witness(folder, case, record["final_endpoint"])
        reports[case] = dict(final=best, stages=stages,
                             elapsed_seconds=record["elapsed_seconds"],
                             primary_proven=primary_proof,
                             exact_witness=(exact or {}).get("path"),
                             lexicographic_optimum_proven=primary_proof and process_proof)
    return dict(cases=reports, pending=pending, complete=len(reports) == len(CASES))


def report(root, results):
    lines = ["# 五个等量混合实例的字典序补跑", "",
             "第一目标是最后一片产品回到供片端口的时刻。第二目标按产品平均非加工驻留、同配方驻留极差的平方项及实际清洁欠额合计。表中目标值从最终排程的动作与加工周期重新计算。", "",
             "| 产品数 | 清洁阈值 | 初始工期 / 秒 | 最终工期 / 秒 | 工期全局下界 / 秒 | 最终工艺分 / 等效秒 | 本次证明情况 | 累计用时 / 分钟 |",
             "|---:|---:|---:|---:|---:|---:|---|---:|"]
    for key, row in results["cases"].items():
        spec = read(root / key / "spec.json")
        best, stages = row["final"], row["stages"]
        primary_lb = max(CASES[key][2], stages.get("A", {}).get("stage_global_lower", 0))
        certification = (f"[精确字典序最优]({key}/{row['exact_witness']})" if row["exact_witness"]
                         else "求解容差内达到两目标全局下界" if row["lexicographic_optimum_proven"]
                         else "工期最优，工艺分待证" if row["primary_proven"] else "可行，工期最优性待证")
        lines.append(f"| {spec['n']} | {spec['h']} | {spec['start_score']['cmax']:.6g} | "
                     f"{best['cmax']:.10g} | {primary_lb:.8g} | {best['secondary']:.8g} | "
                     f"{certification} | {row['elapsed_seconds']/60:.2f} |")
    lines.extend(["", "每例使用一次独立解码初解、求解种子 1 和训练种子 1。该组以较长预算检验小规模实例能否达到字典序最优。求解器目标间隙设为零，关闭节点停滞截断。A 为首目标搜索。B1 固定交接时的离散决策并优化动作时刻与同步，B2 进一步开放资源次序，B3 搜索交接工期上限内的完整候选域。各例已执行的阶段和停止原因列于下表。",
                  "", "| 实例 | 阶段 | 停止原因 | 累计秒数 | 已验证工期 / 秒 | 已验证工艺分 / 等效秒 |",
                  "|---|---|---|---:|---:|---:|"])
    for key, row in results["cases"].items():
        for name, s in row["stages"].items():
            lines.append(f"| {key} | {name} | {s['stop_reason']} | {s['elapsed_seconds']:.1f} | "
                         f"{s['cmax']:.8g} | {s['secondary']:.8g} |")
    if any(row["exact_witness"] for row in results["cases"].values()):
        lines.extend(["", "表中保留原生排程的回片时刻。“精确字典序最优”链接列出由同次运行端点统一整秒化得到的精确目标、物理动作与原生约束回填结果。这一步的耗时单列在见证文件中。"])
    if results["pending"]:
        lines.extend(["", "尚待核验的实例为 " + "、".join(results["pending"]) + "。"])
    bound_file = root / "external_count_bound.json"
    if bound_file.exists():
        from check_count_bound import calculate
        independent = read(bound_file)
        for row in independent["cases"]:
            cfg = read(root / f"n16_h{row['h']}" / "spec.json")["config"]
            if calculate(cfg, row["h"]) != row:
                raise ValueError("Independent 16-wafer chamber enumeration does not reproduce")
        lines.extend(["", "两组 16 片正式运行的初始工期下界均为 716 秒。另按实际清洁要求枚举两腔的 81 种产品分配，获得独立工期下界：H=3 为 1066 秒，H=10 与对准器下界合并后为 716 秒。该复核单独报告，未参与运行中的停机判定。[计数记录](external_count_bound.json)"])
    lines.extend(["", "排程文件、SHA-256、复核次数和分项得分见 [independent_audit.json](independent_audit.json)。每个实例目录的 case.json 记录各阶段的预算及端点。"])
    return "\n".join(lines) + "\n"


def publish(root):
    root.mkdir(parents=True, exist_ok=True)
    with (root / "audit.lock").open("a+b") as lock:
        if not lock.seek(0, 2):
            lock.write(b"0")
            lock.flush()
        lock.seek(0)
        while True:
            try:
                msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
                break
            except OSError:
                time.sleep(.5)
        return publish_locked(root)


def publish_locked(root):
    result = run(root)
    for name, content in [("independent_audit.json", json.dumps(result, indent=2, allow_nan=False) + "\n"),
                          ("补跑结果.md", report(root, result))]:
        target = root / name
        temp = target.with_name(f"{target.name}.{uuid.uuid4().hex}.tmp")
        temp.write_text(content, encoding="utf8")
        temp.replace(target)
    print(json.dumps({k: [v["final"]["cmax"], v["final"]["secondary"]]
                      for k, v in result["cases"].items()}), "pending", result["pending"], flush=True)
    return result


def follow(root):
    # The supervisor owns all experiments and the final full audit. This window
    # replays each newly completed subset while other workers keep solving.
    last = None
    last_print = 0.
    while True:
        status = read(root / "status.json")
        counts = status["counts"]
        if counts["completed"] == len(CASES) or status["mode"] != "running":
            if counts["completed"] != len(CASES):
                publish(root)
            return
        completed = tuple(k for k, item in status["summary"].items() if item["state"] == "completed")
        if completed != last:
            publish(root)
            last = completed
            last_print = 0.
        if time.monotonic() - last_print > 60.:
            print(status["updated"], "replayed", len(completed), "of", len(CASES),
                  "failed", counts["failed"], "budget ETA", status["projected_finish"], flush=True)
            last_print = time.monotonic()
        time.sleep(15)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=JMS / "results/lex_campaign_20261127")
    parser.add_argument("--require-complete", action="store_true")
    parser.add_argument("--follow", action="store_true")
    args = parser.parse_args()
    if args.follow:
        follow(args.output)
    elif not publish(args.output)["complete"] and args.require_complete:
        raise SystemExit(2)

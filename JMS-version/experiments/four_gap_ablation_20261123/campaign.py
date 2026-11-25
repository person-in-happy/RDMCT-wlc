"""Run the four-wafer switch study in a visible console and publish paired results."""
from datetime import datetime
import csv
import io
import itertools
import json
import msvcrt
import os
from pathlib import Path
from statistics import mean
import subprocess
import sys
import time

import psutil
from solve import OUT, ROOT, HERE, ARMS, LEVELS, directory, manifest, read, save
from controls import CP, SCIP

SEEDS = (1, 2, 3)
CELLS = tuple(itertools.product(SEEDS, ARMS, LEVELS))


def publish(rows):
    if rows:
        table = io.StringIO()
        writer = csv.writer(table)
        writer.writerow(["seed","arm","g_A","initial_fA","A_fA","A_fB","B_fA","B_fB","init_s","A_s","B_s","calls","lower_A","lower_B"])
        for (s, arm, k), r in rows.items():
            writer.writerow([s,arm,LEVELS[k],r["start_cmax"],r["before"]["cmax"],r["before"]["secondary"],
                r["after"]["cmax"],r["after"]["secondary"],r["prep_seconds"],r["gate"]["seconds"],
                r["secondary"]["seconds"],r["gate"]["calls"],r["gate"]["lower"],r["secondary"]["lower"]])
        tmp = OUT/"runs.tmp"
        tmp.write_text(table.getvalue(), encoding="utf-8-sig")
        os.replace(tmp, OUT/"verified_runs.csv")
    lines = ["# 4片双源混合实例的切换阈值消融","",
        f"已验算 {len(rows)}/{len(CELLS)} 个结果。第二阶段停机阈值为0.01%。下表仅列三个求解种子均完成的组。","",
        "|切换阈值|方法|初始工期|交接工期|交接工艺目标|最终工期|最终工艺目标|初始化用时|工期搜索用时|工艺搜索用时|选割调用|",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    labels = dict(full="完整策略", no_rerank="关闭重排", no_spbs="省略SPBS", projection="投影参照")
    for k in LEVELS:
        for arm in ARMS:
            group = [rows[s,arm,k] for s in SEEDS if (s,arm,k) in rows]
            if len(group) != len(SEEDS):
                continue
            vals = [[r["start_cmax"],r["before"]["cmax"],r["before"]["secondary"],r["after"]["cmax"],
                r["after"]["secondary"],r["prep_seconds"],r["gate"]["seconds"],r["secondary"]["seconds"],
                r["gate"]["calls"]] for r in group]
            lines.append(f"|{LEVELS[k]:g}（{100*LEVELS[k]:g}%）|{labels[arm]}|"+"|".join(f"{mean(col):.2f}" for col in zip(*vals))+"|")
    lines += ["","时间以秒计。初始化用时为五层策略实际墙钟；两阶段用时为求解器记录。工艺目标仅计产品等待与有效节拍。","",
        "## 三种阈值的配对结果","",
        "每项次序均为种子1、2、3。正差表示启用对应组件后数值降低。重排达标用时仅在两种方法均实际触发选割后比较。",""]
    for k in LEVELS:
        if all((s,"full",k) in rows for s in SEEDS):
            f = [rows[s,"full",k] for s in SEEDS]
            def fmt(numbers):
                return "、".join(f"{n:.2f}" for n in numbers)
            lines.append(f"- {100*LEVELS[k]:g}% 切换时，第二阶段使产品工艺目标分别降低 {fmt(r['before']['secondary']-r['after']['secondary'] for r in f)} s。")
            if all((s,"no_spbs",k) in rows for s in SEEDS):
                plain = [rows[s,"no_spbs",k] for s in SEEDS]
                lines.append(f"- {100*LEVELS[k]:g}% 下初始化的起点工期改善为 {fmt(a['start_cmax']-b['start_cmax'] for a,b in zip(plain,f))} s；最终工期改善为 {fmt(a['after']['cmax']-b['after']['cmax'] for a,b in zip(plain,f))} s。")
            if all((s,"no_rerank",k) in rows for s in SEEDS):
                off = [rows[s,"no_rerank",k] for s in SEEDS]
                assert all(a["start_sha256"]==b["start_sha256"] for a,b in zip(off,f))
                if all(a["gate"]["calls"] and b["gate"]["calls"] for a,b in zip(off,f)):
                    lines.append(f"- {100*LEVELS[k]:g}% 下启用重排的达标用时改善为 {fmt(a['gate']['seconds']-b['gate']['seconds'] for a,b in zip(off,f))} s；最终工艺目标改善为 {fmt(a['after']['secondary']-b['after']['secondary'] for a,b in zip(off,f))} s。")
                else:
                    lines.append(f"- {100*LEVELS[k]:g}% 下至少一侧在某种子上未调用选割，已完成的目标值与调用数见表。")
    tmp = OUT/"review.tmp"
    tmp.write_text("\n".join(lines)+"\n",encoding="utf-8")
    os.replace(tmp, OUT/"REVIEW_CN.md")


def run():
    design = json.loads(json.dumps(manifest()))
    spec = OUT/"protocol.json"
    if spec.exists():
        assert read(spec)==design, "Protocol differs from the recorded design"
    else:
        save(spec, design)
    start = time.monotonic()
    active, failed, rows = {}, {}, {}
    published = -1
    while True:
        for job, process in list(active.items()):
            code = process.poll()
            if code is not None:
                del active[job]
                if code:
                    failed[job] = code
        for s, arm, level in CELLS:
            path = directory(s,arm,level)/"result.json"
            if (s,arm,level) not in rows and path.exists():
                r = read(path)
                assert r["verified"] and (r["seed"],r["arm"],r["level"])==(s,arm,level)
                rows[s,arm,level]=r
        if len(rows)!=published:
            publish(rows)
            published=len(rows)
        jobs=[]
        for s in SEEDS:
            if not (OUT/"inputs"/f"s{s}"/"ready.json").exists():
                jobs.append(("prepare",s))
        for s,arm,k in CELLS:
            if (s,arm,k) not in rows and (directory(s,arm,k)/"handoff.json").is_file():
                jobs.append(("finish",s,arm,k))
        for s in SEEDS:
            if not (OUT/"inputs"/f"s{s}"/"ready.json").is_file():
                continue
            for k in LEVELS:
                if not (directory(s,"projection",k)/"handoff.json").is_file():
                    jobs.append(("projection",s,k))
            for arm in ARMS[:3]:
                if not all((directory(s,arm,k)/"handoff.json").is_file() for k in LEVELS):
                    jobs.append(("native",s,arm))
        for job in jobs:
            if job in active or job in failed or len(active)>=6:
                continue
            kind = job[0]
            if sum(j[0]==kind for j in active)>={"prepare":1,"finish":2,"native":3,"projection":2}[kind]:
                continue
            if psutil.virtual_memory().available < 4 * 2**30:
                break
            exe = CP if kind=="projection" else SCIP
            logfile = OUT/"logs"/("_".join(map(str,job))+f"_{time.time_ns()}.log")
            logfile.parent.mkdir(exist_ok=True)
            with logfile.open("w",encoding="utf8") as log:
                active[job]=subprocess.Popen([exe,"-B","-u","-X","utf8",str(HERE/"solve.py"),*map(str,job)],cwd=ROOT,
                                             stdout=log,stderr=subprocess.STDOUT)
        info = {"/".join(map(str,j)):p.pid for j,p in active.items()}
        count=len(rows)
        elapsed=time.monotonic()-start
        # The tight native gates have a different runtime distribution to the analytic gates.
        timed = [r["gate"]["seconds"] for r in rows.values() if r["arm"]!="projection" and r["level"]=="0p01pct" and r["gate"]["seconds"]>0]
        missing = sum((s,a,"0p01pct") not in rows for s in SEEDS for a in ARMS[:3])
        eta = mean(timed)*missing/3 if timed else None
        errors={"/".join(map(str,j)):v for j,v in failed.items()}
        status=dict(updated=datetime.now().isoformat(timespec="seconds"),verified=count,total=len(CELLS),
            failed=errors,active=info,elapsed_seconds=elapsed,eta_seconds=eta)
        save(OUT/"progress.json",status)
        print(f"{status['updated']} | verified {count}/{len(CELLS)} | failed {len(errors)} | ETA " +
              (f"{eta/3600:.2f} h" if eta is not None else "awaiting tight SCIP gates") + " | "+", ".join(info),flush=True)
        if not active and (count==len(CELLS) or not any(j not in failed for j in jobs)):
            return int(bool(failed) or count!=len(CELLS))
        time.sleep(4)


if __name__=="__main__":
    OUT.mkdir(parents=True,exist_ok=True)
    with (OUT/"controller.lock").open("a+b") as lock:
        lock.seek(0)
        msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
        sys.exit(run())

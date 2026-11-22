"""Independent event-based review, written as complete matched cohorts become available."""
import argparse
from datetime import datetime
import math
import os
from statistics import mean
import time

from inputs import BASE, SCENARIOS, TAU, cell, read, save, sha, validate
from controls import product


def check_bounds(record, value):
    u, l = record["upper"], record["lower"]
    assert record["status"] in ("optimal", "gaplimit", "analytic_gap")
    assert math.isfinite(l) and math.isfinite(u) and l <= u+1e-7 and abs(u-value)<cell.EPS
    delta = 0. if value == l == 0 else abs(value-l)/min(abs(value),abs(l)) if value*l>0 else math.inf
    assert delta <= TAU+1e-9


def verify_one(key, spec):
    folder=BASE/"runs"/key
    terminal=read(folder/"result.json")
    src=BASE/"inputs"/spec["case"]/f"s{spec['seed']}"
    prep=read(src/"input.json")
    assert sha(src/"input.json")==terminal["input_manifest_sha256"]
    v=spec["initialization"]
    assert sha(src/v/"assignment.json.gz")==terminal["initial"]==prep["sources"][v]["assignment"]
    assert sha(src/v/"schedule.json")==prep["sources"][v]["schedule"]
    assert all(spec[k]==terminal[k] for k in spec)
    a=folder/"A"
    b=folder/"B/runs/endpoint"
    apr=read(a/"primary.json")
    bpr=read(b/"result.json")
    assert apr["replay"]["valid"] and bpr["replay"]["valid"] and terminal["verified"]
    assert sha(a/"primary.json")==terminal["primary_sha256"] and sha(b/"result.json")==terminal["secondary_sha256"]
    assert apr["record"]==terminal["A"] and bpr["record"]==terminal["B"]
    assert sha(a/"assignment.json.gz")==bpr["job"]["assignment_sha256"]==apr["assignment_sha256"]
    assert sha(a/"schedule.json")==apr["schedule_sha256"]==bpr["job"]["schedule_sha256"]
    assert sha(b/"assignment.json.gz")==bpr["files"]["assignment.json.gz"]
    assert sha(b/"schedule.json")==bpr["files"]["schedule.json"]
    assert bpr["job"]["gap"]==TAU and bpr["job"]["seconds"] is None
    for f in (a/"limits.json",b/"limits.json"):
        if f==a/"limits.json" and apr["record"]["status"]=="analytic_gap":
            continue
        limit=read(f)
        assert limit["relative"]==TAU and limit["time"]>=1e19 and limit["threads"]==1
    schedules=[read(stage/"schedule.json") for stage in (a,b)]
    values=[]
    for data in schedules:
        data["config"]=prep["unrestricted"]
        assert validate(data)["valid"]
        values.append(product.product_metrics(data))
    ma,mb=values
    check_bounds(terminal["A"],ma["cmax"])
    check_bounds(terminal["B"],mb["secondary"])
    assert mb["cmax"] <= ma["cmax"]+cell.EPS
    assert all(abs(mb[k]-terminal["metrics"][k])<cell.EPS for k in mb)
    rec=terminal["A"]
    if spec["method"]!="default" and rec["status"]!="analytic_gap":
        assert spec["checkpoint_sha256"]==rec["policy"]["sha256"]
    return dict(**spec, raw=prep["sources"]["raw"]["assignment"], start=terminal["initial"],
         f_A=ma["cmax"], f_B=mb["secondary"], A_seconds=rec["seconds"], B_seconds=terminal["B"]["seconds"],
         calls=rec.get("policy_calls") or 0, nodes=rec.get("search",{}).get("nodes",0))


def contrasts(rows, jobs):
    methods=("default","hem_spbs","feature_only","no_rerank","greedy")
    results=[]
    for case in SCENARIOS:
        comparisons=[("初始化",("full","raw"),("full","prepared"))]
        comparisons.extend((method,(method,"prepared"),("full","prepared")) for method in methods)
        for label,before,after in comparisons:
            pairs=[]
            for k,j in jobs.items():
                if j["case"]!=case or (j["method"],j["initialization"])!=after:
                    continue
                train=1 if before[0]=="default" else j["training_seed"]
                base=f"{case}__s{j['seed']}__t{train}__{before[1]}__{before[0]}"
                assert base in jobs
                if base not in rows or k not in rows:
                    break
                x,y=rows[base],rows[k]
                assert x["raw"]==y["raw"]
                if before[1]==after[1]:
                    assert x["start"]==y["start"]
                pairs.append((x,y))
            else:
                if not pairs:
                    continue
                effect={}
                for metric in ("f_A","f_B","A_seconds","B_seconds","calls","nodes"):
                    changes=[y[metric]-x[metric] for x,y in pairs]
                    eps=cell.EPS if metric in ("f_A","f_B") else 0
                    effect[metric]=dict(before=mean(x[metric] for x,y in pairs),after=mean(y[metric] for x,y in pairs),
                            lower=sum(d < -eps for d in changes),equal=sum(abs(d)<=eps for d in changes),
                            higher=sum(d > eps for d in changes))
                results.append(dict(case=case, comparison=label, pairs=len(pairs), metrics=effect))
    return results


def review(jobs, rows):
    finished=contrasts(rows,jobs)
    inputs={}
    for case in SCENARIOS:
        paths=[BASE/"inputs"/case/f"s{s}"/"input.json" for s in (1,2,3)]
        if not all(p.exists() for p in paths):
            continue
        cohort=[]
        for path in paths:
            inp=read(path)
            scores=[]
            for arm in ("raw","prepared"):
                loc=path.parent/arm
                assert sha(loc/"assignment.json.gz")==inp["sources"][arm]["assignment"]
                assert sha(loc/"schedule.json")==inp["sources"][arm]["schedule"]
                sc=read(loc/"schedule.json")
                sc["config"]=inp["unrestricted"]
                assert validate(sc)["valid"]
                scores.append(product.product_metrics(sc)["cmax"])
            cohort.append(scores)
        inputs[case]=cohort
    save(BASE/"review.json",dict(expected=len(jobs),verified=len(rows),initialization=inputs,comparisons=finished))
    lines=["# 16片混合实例双阈值消融复核","",
        f"已逐事件复核 {len(rows)}/{len(jobs)} 项，两阶段的相对间隙阈值均为 0.01%。","",
        "## 进入工期搜索前的排程","",
        "| 场景 | 构造工期（s） | SPBS后工期（s） |","|---|---:|---:|"]
    for case,group in inputs.items():
        lines.append(f"| {case} | {mean(x for x,y in group):.2f} | {mean(y for x,y in group):.2f} |")
    lines+=["","这里的工期由进入第一阶段前的物理排程取得。","","## 达到两个阈值后的配对",""]
    if finished:
        lines+=["各列为完整策略减对照策略的配对均值。初始化对照为启用减省略SPBS。第一阶段用时单列，不含构造和初始化。","",
                "| 场景 | 对照 | 配对数 | 工期差（s） | 工艺目标差（s） | 第一阶段用时差（s） | 选割调用差 |",
                "|---|---|---:|---:|---:|---:|---:|"]
        for r in finished:
            delta=lambda k:r["metrics"][k]["after"]-r["metrics"][k]["before"]
            lines.append(f"| {r['case']} | {r['comparison']} | {r['pairs']} | {delta('f_A'):.2f} | "
                         f"{delta('f_B'):.2f} | {delta('A_seconds'):.2f} | {delta('calls'):.2f} |")
        lines+=["","逐指标改善、持平、变差的配对数及节点数见 [review.json](review.json)。"]
    else:
        lines.append("尚无覆盖所需全部种子的完整对照。")
    lines+=["","## 结论依据",""]
    for r in finished:
        a,b=r["metrics"]["f_A"],r["metrics"]["f_B"]
        t,c=r["metrics"]["A_seconds"],r["metrics"]["calls"]
        if a["equal"]==r["pairs"] and b["equal"]==r["pairs"]:
            why="两个目标逐对持平。"
            if c["after"]==0:
                why+="完整策略在这些工期搜索中没有触发学习选割。"
            else:
                why+=f"完整策略触发了学习选割，达到工期阈值的平均用时由 {t['before']:.2f} s 变为 {t['after']:.2f} s。"
        else:
            why=f"完整策略的工期较对照改善/持平/变差 {a['lower']}/{a['equal']}/{a['higher']} 对；工艺目标相应为 {b['lower']}/{b['equal']}/{b['higher']} 对。"
        lines.append(f"- {r['case']}，{r['comparison']}。{why}")
    if not finished:
        lines.append("当前可复核初始化后的可行工期。最终工艺目标及达到同一间隙的搜索效率，等待配对排程。")
    target=BASE/"REVIEW_CN.md"
    tmp=target.with_suffix(".tmp")
    tmp.write_text("\n".join(lines)+"\n",encoding="utf8")
    os.replace(tmp,target)


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--watch",action="store_true")
    args=parser.parse_args()
    design=read(BASE/"protocol.json")["jobs"]
    rows={}
    previous=None
    while True:
        for f in (BASE/"runs").glob("*/result.json"):
            k=f.parent.name
            if k not in rows:
                rows[k]=verify_one(k,design[k])
        state=(len(rows),len(list((BASE/"inputs").glob("*/*/input.json"))))
        if state!=previous:
            review(design,rows)
            print(datetime.now().isoformat(timespec="seconds"),f"reviewed {len(rows)}/{len(design)}",flush=True)
            previous=state
        if not args.watch or len(rows)==len(design):
            break
        time.sleep(40)

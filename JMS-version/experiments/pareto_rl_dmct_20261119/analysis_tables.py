"""Secondary summaries of the independent replay. Only called after the campaign."""
from collections import defaultdict
import statistics as st

from common import TOL


def grouped_results(rows, points, operators, exact, unsupported, target, write_csv, names):
    by_id = defaultdict(list)
    for p in points:
        by_id[p["id"]].append(p)

    def quantiles(values):
        if len(values) == 1:
            return values[0], values[0]
        q1, _, q3 = st.quantiles(values, n=4, method="inclusive")
        return q1, q3

    groups = defaultdict(list)
    for row in rows:
        key = tuple(row[k] for k in ("suite", "case", "method", "weight", "width", "repair"))
        groups[key].append(row)
    averaged = []
    for (suite, case, method, weight, width, repair), rs in sorted(groups.items()):
        info = dict(suite=suite, case=case, method=method, weight=weight, width=width, repair=repair,
                    runs=len(rs), feasible_at_operating=sum(r["A_at_operating"] is not None for r in rs))
        for k in ("HV", "IGD_plus", "hit7", "hit3", "front_count", "A_min", "B_min", "A_at_floor",
                  "A_at_operating", "bound_skips", "lp_calls", "callbacks"):
            values = [r[k] for r in rs if r[k] is not None]
            if values:
                q1, q3 = quantiles(values)
                info.update({k+"_median":st.median(values), k+"_q1":q1, k+"_q3":q3})
        averaged.append(info)
    write_csv(target/"method_summary.csv", averaged)

    # Count only points in the algorithm's individual returned archives, never the scoring oracle.
    coverage = []
    for (suite, case, method, _, _, _), rs in sorted(groups.items()):
        if suite != "main" or case != "S1":
            continue
        for a, b in exact:
            seeds = [r["seed"] for r in rs
                     if any(abs(p["A"]-a)<=TOL and abs(p["B"]-b)<=TOL for p in by_id[r["id"]])]
            coverage.append(dict(method=method, A=a, B=b, unsupported=(a,b) in unsupported,
                                 hit_runs=len(seeds), trials=len(rs), seeds=",".join(map(str, sorted(seeds)))))
    write_csv(target/"s1_point_hits.csv", coverage)

    # Keep the delivery deadline common over all rhythm weights and both algorithms.
    weights = []
    for row in rows:
        if row["suite"] != "weight":
            continue
        a0 = row["scale_A_max"]/1.5
        eligible = [p for p in by_id[row["id"]] if p["A"]<=a0+TOL]
        chosen = min(eligible, key=lambda p:(round(p["B"],5), p["A"]))
        weights.append({k:chosen[k] for k in ("id","case","method","weight","seed","A","B","L_sum","L_max","R",
                                                "rhythm_centers","PP","PD","schedule")}
                       | dict(common_A_deadline=a0))
    write_csv(target/"weight_tradeoffs.csv", weights)

    calls = defaultdict(dict)
    for q in operators:
        if q["suite"] == "paired":
            calls[(q["case"], q["seed"], q["call"])][q["method"]] = q
    paired = []
    for (case, seed, call), parts in sorted(calls.items()):
        if set(parts)!={"generic","domain"}:
            continue
        g, d = parts["generic"], parts["domain"]
        same = (g["parent_ab"] == d["parent_ab"] and g["other_ab"] == d["other_ab"]
                and g["goal"] == d["goal"] and g["cap"] == d["cap"]
                and g["released_orders"] == d["released_orders"])
        paired.append(dict(case=case, seed=seed, call=call, goal=d["goal"], cap=d["cap"],
                           same_parents_cap_and_size=same, generic_released=g["released_orders"],
                           domain_released=d["released_orders"], generic_status=g["status"],
                           domain_status=d["status"], generic_nodes=g["nodes"], domain_nodes=d["nodes"]))
    write_csv(target/"paired_controls.csv", paired)
    return averaged, coverage, weights, paired


def interpretation(rows, points, averaged, cover, weights, paired, names):
    def main(case, method):
        return next(r for r in averaged if (r["suite"],r["case"],r["method"])==("main",case,method))

    def ff(x):
        return f"{x:.3f}".rstrip("0").rstrip(".")

    text = ["", "## 实验结果如何解释", ""]
    for case in (c for c in ("S1","M4","H4","H8","H16") if any(r["case"]==c for r in rows)):
        d = main(case, "domain")
        competitors = sorted((main(case, m) for m in ("epsilon","nsga2","moead","legacy")),
                             key=lambda r:-r["HV_median"])
        best = competitors[0]
        text.append(f"- {case} 的领域搜索 HV 中位数为 {d['HV_median']:.5f}，四分位区间为 "
                    f"[{d['HV_q1']:.5f}, {d['HV_q3']:.5f}]。四种外部或原算法对照中，"
                    f"{names[best['method']]} 的中位数最高，为 {best['HV_median']:.5f}。")
    s1 = [c for c in cover if c["method"]=="domain" and c["hit_runs"]]
    unsup = [c for c in cover if c["unsupported"] and c["hit_runs"]]
    text += ["", f"三个种子的领域搜索合计命中 S1 的 {len(s1)}/7 个不同认证点。六种主方法中，"
             f"至少被一种方法找回的非支持点共 {len({(c['A'],c['B']) for c in unsup})}/3 个。"
             "前沿图中的黑色空心圆给出全部认证点。逐点表保留每个方法的命中种子，可以区分跨种子合并与单次运行。[逐点命中记录](s1_point_hits.csv)"]
    mixed = [p for p in points if p["case"]=="M4" and p["suite"]=="main"]
    fast = min(mixed, key=lambda p:(p["A"],p["B"]))
    floor = [p for p in mixed if p["B"]<=54+TOL]
    if floor:
        short = min(floor,key=lambda p:p["A"])
        text += ["", f"四片标称实例在本次主比较中最快交付为 {ff(fast['A'])} 秒，"
                 f"达到 B=54 的排程中最快为 {ff(short['A'])} 秒。已有证书给出 B=54 时最短工期的下界 476 秒和可行上界 497 秒。"
                 f"合并两批证据，最短工期位于 [476, {ff(min(497,short['A']))}] 秒。"
                 f"相比本次找到的最快交付，达到 B=54 的工期代价至少为 {ff(476-fast['A'])} 秒。"
                 "四片图只画单次运行的样本前沿。[既有端点证书](../../../../../review/pareto_objectives_20261118/certificate_CN.md)"]
    groups = defaultdict(list)
    for row in weights:
        groups[row["weight"]].append(row)
    text += ["", "在八片纯 2×2 工况上，以共同构造排程的工期作为交付上限，再从每个单次档案中挑出满足上限且加权 B 最小的排程。该规则始终有一个可行候选，便于比较同一交付条件下节拍权重的影响。","",
             "| 节拍权重 | 共同交付上限 / s | 入选排程数 | 节拍偏差范围 / s | 总等待范围 / s | 最大单项等待范围 / s |",
             "|---:|---:|---:|---:|---:|---:|"]
    for w, rs in sorted(groups.items()):
        def spread(k):
            vals=[r[k] for r in rs]
            return f"{ff(min(vals))}–{ff(max(vals))}"
        text.append(f"| {w} | {spread('common_A_deadline')} | {len(rs)} | {spread('R')} | {spread('L_sum')} | {spread('L_max')} |")
    text += ["", "[同一交付期限下的逐种子决策](weight_tradeoffs.csv) · [含四分位数的分组指标](method_summary.csv)",""]
    if paired:
        text.append(f"配对邻域对照完成 {len(paired)} 对子问题，其中 "
                    f"{sum(p['same_parents_cap_and_size'] for p in paired)} 对具有相同父排程目标、上限和整数顺序变量释放数。"
                    "各子问题的状态和节点数单独保留。[配对核对表](paired_controls.csv)")
    learned = [r for r in rows if r["suite"]=="main" and r["method"]=="rl_domain"]
    text += ["", f"冻结策略的 {len(learned)} 次主比较中，有 {sum(r['callbacks']>0 for r in learned)} 次实际触发选割回调。"
             "第二轮比较统一了学习版和默认选割的目标上限序列。对内次序消融仅关闭局部解码时的取放次序变异，两组保留相同的 SCIP 修复预算。"
             "主比较每个算法只有三个种子，扰动比较每个设置两个种子，四分位数采用样本分位点间的线性插值。"]
    return text

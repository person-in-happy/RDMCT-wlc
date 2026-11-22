"""Write a short reader-facing results page from the independently verified outputs."""
import csv
import statistics as st
from evaluate import NAMES, fmt, read


def summary(target):
    def table(filename):
        with (target/filename).open(encoding="utf-8-sig",newline="") as f:
            return list(csv.DictReader(f))
    runs=table("runs.csv")
    pts=table("points.csv")
    effects=table("matched_effects.csv")
    pooled=table("weight_common_pool.csv")
    matched=table("paired_controls.csv")
    validation=read(target/"validation.json")
    projection=read(target/"m4_slices/projection.json")
    small=read(target.parents[1]/"s1_refine01/independent_score.json") if (target.parents[1]/"s1_refine01/independent_score.json").exists() else None

    def rs(case,method,suite="main"):
        return [r for r in runs if (r["case"],r["method"],r["suite"])==(case,method,suite)]
    def median(group,key):
        vals=[float(r[key]) for r in group if r[key]!=""]
        return st.median(vals) if vals else None
    cases=("S1","M4","H4","H8","H16")
    methods=("domain","rl_domain","epsilon","nsga2","moead","legacy")
    text=["# 晶圆双目标调度的实验结果","",
          f"正式比较完成 {len(runs)} 组。{validation['archived_witnesses']} 份最终排程全部通过设备事件回放和原模型约束检查。六种方法在五个工况各运行三个种子，另有消融、设备与算法参数扰动及两片单种子长预算实验。",""]
    if small:
        text += [f"**两片工况完成了完整前沿重算。** 使用实际排程确定目标上限，再调用该工况专用的配对与双腔室时序子模型，"
                 f"两个阶段共耗时 {small['elapsed_two_stages']:.2f} 秒。重新获得 {small['certified_hits']}/7 个认证点及其中 "
                 f"{small['unsupported_hits']}/3 个非支持点，HV 为 {small['HV']:.6f}，IGD+ 为 {small['IGD_plus']:.3g}。"
                 "B≤100 时选到的最短工期是 514 秒。完整性来自此前独立证书，本次重算给出了对应的新排程。"
                 "[七点前沿图](../../s1_refine01/s1_complete_CN.png) · [逐点复验](../../s1_refine01/front_checked.csv)",""]
    text+=["## 通用算法在相同时间内找到了什么","",
           "表中为三个种子的 HV 中位数，数值越大越好。S1 用认证前沿极值归一化。其他工况统一按各自共同构造排程定标，参考点为 (1.1, 1.1)。",
           "","| 工况 | 领域搜索 | 领域搜索加学习选割 | ε-SCIP | NSGA-II | MOEA/D | 原两阶段 |",
           "|---|---:|---:|---:|---:|---:|---:|"]
    for c in cases:
        vals=[median(rs(c,m),"HV") for m in methods]
        text.append("| "+c+" | "+" | ".join(f"{x:.5f}" for x in vals)+" |")
    text+=["","[代表种子前沿图](fronts_CN.png) · [HV 随时间的变化](hv_time_CN.png) · [中位数与四分位数](method_summary.csv)",""]
    long=rs("S1","domain","long")
    if long:
        hit=rs("S1","domain")
        text += [f"S1 的通用领域搜索在 40 秒主比较中，三个种子分别命中 "
                 f"{'、'.join(str(int(float(r['hit7']))) for r in sorted(hit,key=lambda r:int(r['seed'])))} 个认证点。"
                 f"种子 1 延长到 300 秒后命中 {int(float(long[0]['hit7']))}/7 个，其中非支持点 {int(float(long[0]['hit3']))}/3。"
                 f"同一长预算运行的 IGD+ 为 {float(long[0]['IGD_plus']):.5f}。"
                 "[逐点、逐种子命中记录](s1_point_hits.csv) · [全部单次结果](runs.csv)",""]
    mixed=[p for p in pts if (p["suite"],p["case"])==("main","M4")]
    fast=min(float(p["A"]) for p in mixed)
    floor=[float(p["A"]) for p in mixed if float(p["B"])<=54+2e-5]
    tight=min([497.]+floor+[a for g in projection["slices"] for a,b in g["vertices"] if b<=54+2e-5])
    visible_pieces=projection["envelope_segments"]
    span=""
    if len(visible_pieces)==1:
        seg=visible_pieces[0]
        left_bracket="[" if seg.get("left_included",True) else "("
        right_bracket="]" if seg.get("right_included",True) else ")"
        span=f"本次结构合并后，这一段的工期区间为 {left_bracket}{fmt(seg['A_left'])}, {fmt(seg['A_right'])}{right_bracket} 秒。"
    text += [f"四片标称实例找到 {fmt(fast)} 秒交付的可行排程。由已知 B=54 的工期下界 476 秒，达到最低 B 至少比这份排程晚 {fmt(476-fast)} 秒。"
             f"综合原证书和本次可行解，B=54 的最短工期位于 [476, {fmt(tight)}] 秒。"
             f"另外，对本次访问的 {projection['structures']} 套不同整数决策开放连续时刻，查得 {projection['segments']} 条结构内有效线段，"
             f"其中 {len(visible_pieces)} 段出现在这些结构合并后的边界上。{span}"
             "[四片连续边界与既有三条已验证线段](m4_slices/m4_conditional_front_CN.png)","",
             "## 哪些算法改动得到了数据支持",""]
    for term in ("配对下界，领域邻域","领域邻域，开启配对下界","开放对内取放次序变异","自适应等待上限","冻结学习选割"):
        selected=[r for r in effects if r["case"]=="M4" and r["experiment"]==term]
        vals=[float(r["delta_HV"]) for r in selected]
        if vals:
            text.append(f"- {term}，四片同种子 HV 差值中位数为 {st.median(vals):+.5f}，{sum(x>1e-7 for x in vals)}/{len(vals)} 次提高。")
    domain=rs("M4","domain")
    screened=sum(int(r["bound_skips"]) for r in domain)
    total_callbacks=sum(int(r["callbacks"]) for r in runs if r["suite"]=="main" and r["method"]=="rl_domain")
    text+=["",f"四片领域搜索三个种子累计按下界跳过 {screened} 次候选评估，重复提出相同配对也计数。"
           f"同父排程与同释放数的算子对照记录了 {len(matched)} 对子问题。学习版主比较共触发 {total_callbacks} 次选割回调。"
           "这些计数分别说明规则被调用以及节省了哪些候选检查，实际前沿质量用上表和逐种子差值判断。"
           "[配对核对表](paired_controls.csv) · [消融与参数配对差值图](m4_ablation_parameters_CN.png)",""]
    weights=[p for p in pts if p["suite"]=="weight"]
    changes=[]
    for key in {(r["seed"],r["deadline_ratio"]) for r in pooled}:
        elig=[r for r in pooled if (r["seed"],r["deadline_ratio"])==key and r.get("R","")!=""]
        if elig:
            changes.append(len({round(float(r["R"]),5) for r in elig})>1)
    text += [f"八片节拍扰动实验中，{len(weights)} 份归档排程有 {sum(float(p['R'])>2e-5 for p in weights)} 份的节拍偏差大于零。"
             f"在相同候选和交付期限下重新计算四种权重，有 {sum(changes)}/{len(changes)} 个种子与期限组合改变了所选方案的节拍偏差。"
             "算法参数另比较邻域比例 0.15/0.30/0.50、修复预算比例 0.12/0.22/0.32，设备参数分别改变辅助片库存和清洁阈值。"
             "[同期限代表排程](weight_tradeoffs.csv) · [同一批排程的权重重算](weight_common_pool.csv)","",
             "本次同预算结果适用于列出的输入、种子和时限。四片以上的数值前沿来自实际可行排程，完整性仍取决于能否排除其他整数结构。"
             "若将本文作为第三个创新点，可论证设备配对等待下界、据此筛选结构，以及按实际资源关系释放邻域的求解方法。"
             "各机制是否改善前沿，应逐工况、逐指标陈述。"
             "[详细实验与停止状态](report_CN.md) · [原始约束与哈希核验](validation.json)"]
    cutpath=target.parents[1]/"cut_pairs01/summary.json"
    if cutpath.is_file():
        cut=read(cutpath)
        text+=["",f"另在原始 ε-SCIP 上进行了 {cut['matched_pairs']} 对直接开关试验，配对使用相同目标上限、初始排程、种子和 4 秒子问题预算。"
               f"{cut['cut_excluded_a_count']} 对的上限能排除至少一种配对数量。加下界后，条件工期改善的有 "
               f"{cut['pairs_improved_conditional_makespan']} 对、变差的有 {cut['pairs_worse_conditional_makespan']} 对。"
               "[直接下界消融、节点数与求解状态](../../cut_pairs01/paired.csv)"]
    (target/"overview_CN.md").write_text("\n".join(text)+"\n",encoding="utf-8")

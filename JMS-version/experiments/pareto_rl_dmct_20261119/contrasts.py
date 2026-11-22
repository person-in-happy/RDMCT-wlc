"""Matched-seed contrasts, operating limits and device objective components."""
from collections import defaultdict
import statistics as st

from common import TOL


def contrast_tables(rows, points, target, write_csv):
    comparisons = []
    def matched(case, name, reference, variant, comparable_hv=True):
        left={r["seed"]:r for r in reference}
        right={r["seed"]:r for r in variant}
        for seed in sorted(left.keys() & right.keys()):
            a,b=left[seed],right[seed]
            entry=dict(experiment=name,case=case,seed=seed,reference=a["id"],variant=b["id"],
                       HV_reference=a["HV"],HV_variant=b["HV"],delta_HV=b["HV"]-a["HV"] if comparable_hv else None,
                       delta_A_min=b["A_min"]-a["A_min"],delta_B_min=b["B_min"]-a["B_min"],
                       delta_at_operating=(b["A_at_operating"]-a["A_at_operating"])
                            if b["A_at_operating"] is not None and a["A_at_operating"] is not None else None,
                       reference_at_operating=a["A_at_operating"],variant_at_operating=b["A_at_operating"],
                       reference_bound_skips=a["bound_skips"],variant_bound_skips=b["bound_skips"],
                       reference_callbacks=a["callbacks"],variant_callbacks=b["callbacks"])
            comparisons.append(entry)
    def select(case, suite, method):
        return [r for r in rows if (r["case"],r["suite"],r["method"])==(case,suite,method)]
    for c in ("S1","M4"):
        domain=select(c,"main","domain")
        generic=select(c,"ablation","generic")
        bounded=select(c,"ablation","generic_bound")
        raw=select(c,"ablation","domain_no_bound")
        matched(c,"配对下界，普通邻域",generic,bounded)
        matched(c,"配对下界，领域邻域",raw,domain)
        matched(c,"领域邻域，关闭配对下界",generic,raw)
        matched(c,"领域邻域，开启配对下界",bounded,domain)
        matched(c,"开放对内取放次序变异",select(c,"ablation","no_order"),domain)
        matched(c,"自适应等待上限",domain,select(c,"ablation","adaptive"))
    for c in ("S1","M4","H4","H8","H16"):
        matched(c,"冻结学习选割",select(c,"main","domain"),select(c,"main","rl_domain"))
    alg=select("M4","algorithm","domain")
    for k, values in (("width",(.15,.5)),("repair",(.12,.32))):
        for v in values:
            matched("M4",f"{k}={v:g}",select("M4","main","domain"),[r for r in alg if r[k]==v])
    for c in ("M4-D4","M4-H3"):
        for method in ("domain","nsga2"):
            matched(c,f"设备参数 {method}",select("M4","main",method),select(c,"machine",method),False)
    write_csv(target/"matched_effects.csv",comparisons)

    pooled=[]
    for seed in sorted({r["seed"] for r in rows if r["suite"]=="weight"}):
        group=[p for p in points if p["suite"]=="weight" and p["seed"]==seed]
        baselines={round(r["scale_A_max"]/1.5,7) for r in rows if r["suite"]=="weight" and r["seed"]==seed}
        if len(baselines)!=1:
            raise ValueError("Weight runs did not have the same neutral makespan")
        baseline=baselines.pop()
        for fraction in (.85,1.,1.15):
            cap=fraction*baseline
            eligible=[p for p in group if p["A"]<=cap+TOL]
            for weight in (0,12.5,25,50):
                if not eligible:
                    pooled.append(dict(seed=seed,deadline_ratio=fraction,A_deadline=cap,weight=weight,candidates=0))
                    continue
                def score(p):
                    return p["L_sum"]+10*p["L_max"]+weight*p["R"]
                pick=min(eligible,key=lambda p:(round(score(p),6),p["A"],p["R"],p["sha256"]))
                pooled.append(dict(seed=seed,deadline_ratio=fraction,A_deadline=cap,weight=weight,
                                   candidates=len(eligible),A=pick["A"],rescored_B=score(pick),
                                   L_sum=pick["L_sum"],L_max=pick["L_max"],R=pick["R"],
                                   rhythm_centers=pick["rhythm_centers"],source_cell=pick["id"],schedule=pick["schedule"]))
    write_csv(target/"weight_common_pool.csv",pooled)
    return comparisons,pooled


def contrast_text(comparisons,pool):
    lines=["","## 同种子消融与参数变化","",
           "下面的 HV 差值逐种子计算，正值表示在列出的改动后超体积上升。设备参数变化同时改变实例和归一化，因此另按秒比较工期和等待。相同方案的不同随机种子共享各自的初始解。","",
           "| 工况 | 改动 | 种子数 | HV 差值中位数 | 提高 / 持平 / 降低 |","|---|---|---:|---:|---:|"]
    keyed=defaultdict(list)
    for r in comparisons:
        if r["delta_HV"] is not None:
            keyed[r["case"],r["experiment"]].append(r["delta_HV"])
    for (c,label),vals in sorted(keyed.items()):
        gain=sum(x>1.e-7 for x in vals)
        loss=sum(x< -1.e-7 for x in vals)
        lines.append(f"| {c} | {label} | {len(vals)} | {st.median(vals):+.5f} | {gain} / {len(vals)-gain-loss} / {loss} |")
    changes=0
    eligible_groups=0
    for seed,fraction in {(r["seed"],r["deadline_ratio"]) for r in pool}:
        subgroup=[r for r in pool if r["seed"]==seed and r["deadline_ratio"]==fraction and r["candidates"]]
        if subgroup:
            eligible_groups+=1
            changes+=len({round(r["R"],5) for r in subgroup})>1
    lines += ["",f"把同一工况、同一随机种子下的排程合并，保留同一交付期限，再对每份排程重算四种节拍权重。"
              f"一共检查 {eligible_groups} 个有可行排程的种子与交付期限组合，其中 {changes} 个组合的最低综合指标方案改变了节拍偏差 R。"
              "这项固定候选集分析补充了分别重新求解四种权重的实验。[逐种子消融和设备扰动](matched_effects.csv) · [固定候选集的跨权重重算](weight_common_pool.csv)"]
    return lines


def plot_contrasts(comparisons, target):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    plt.rcParams.update({"font.family":["Microsoft YaHei","DejaVu Sans"],"axes.spines.top":False,
                         "axes.spines.right":False,"axes.unicode_minus":False,"savefig.dpi":185})
    groups=[
        [("配对下界，普通邻域","普通邻域内加下界"),("配对下界，领域邻域","领域邻域内加下界"),
         ("领域邻域，关闭配对下界","无下界时启用领域邻域"),("领域邻域，开启配对下界","有下界时启用领域邻域"),
         ("开放对内取放次序变异","开放对内取放次序"),("自适应等待上限","自适应等待上限"),("冻结学习选割","冻结学习选割")],
        [("width=0.15","变量比例 0.15"),("width=0.5","变量比例 0.50"),
         ("repair=0.12","修复预算比例 0.12"),("repair=0.32","修复预算比例 0.32")]]
    fig,axes=plt.subplots(1,2,figsize=(11.5,4.65),layout="constrained")
    for ax,labels,title in zip(axes,groups,("消融，每种改动三个配对种子","参数扰动，每种改动两个配对种子")):
        for i,(field,label) in enumerate(labels):
            vals=[r["delta_HV"] for r in comparisons if r["case"]=="M4" and r["experiment"]==field]
            if vals:
                for j,value in enumerate(vals):
                    ax.plot(value,i+.11*(j-(len(vals)-1)/2),"o",markersize=5,color="#60849d",alpha=.8)
                ax.plot(st.median(vals),i,"|",markersize=16,markeredgewidth=2.5,color="#00786c")
        ax.axvline(0,color="#939ca3",linestyle="--",linewidth=.9)
        ax.set_yticks(range(len(labels)),[label for _,label in labels])
        ax.set_ylim(len(labels)-.5,-.5)
        ax.set_xlabel("相同种子的 HV 差值（改动后减改动前）")
        ax.set_title(title,loc="left")
        ax.grid(axis="x",alpha=.15)
    fig.legend(handles=[Line2D([0],[0],marker="o",ls="none",color="#60849d",label="单个种子"),
                        Line2D([0],[0],marker="|",ls="none",color="#00786c",markersize=13,
                               markeredgewidth=2,label="配对差值中位数")],loc="outside lower center",ncol=2,frameon=False)
    fig.savefig(target/"m4_ablation_parameters_CN.png")
    plt.close(fig)

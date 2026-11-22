"""Independently replay returned schedules and score the final and anytime fronts."""
import argparse
import csv
import gzip
import hashlib
import json
import math
import statistics as st
import time
from collections import defaultdict
from fractions import Fraction
from pathlib import Path

from common import JMS, TOL, config, digest, dominates, lower_bound, metrics, save
from native import Native
from validate import validate
from analysis_tables import grouped_results, interpretation
from contrasts import contrast_tables, contrast_text, plot_contrasts

REFERENCE = JMS/"review/pareto_objectives_20261118/certified_s1_frontier.csv"
NAMES = {"domain":"领域邻域 + 下界","rl_domain":"领域邻域 + 下界 + 学习选割","epsilon":"ε 约束 SCIP",
         "legacy":"工期优先两阶段","nsga2":"NSGA-II","moead":"MOEA/D","generic":"普通邻域",
         "generic_bound":"普通邻域 + 下界","domain_no_bound":"领域邻域","no_order":"关闭对内次序搜索",
         "adaptive":"自适应上限"}
MAIN = ("domain","rl_domain","epsilon","nsga2","moead","legacy")
COLORS = {"domain":"#007473","rl_domain":"#bb4134","epsilon":"#6d7783","legacy":"#4c4053",
          "nsga2":"#3468b2","moead":"#a66d14"}
MARKERS = {"domain":"o","rl_domain":"x","epsilon":"^","legacy":"P","nsga2":"s","moead":"d"}


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_csv(path,rows):
    if not rows:
        return
    keys = list(dict.fromkeys(k for r in rows for k in r))
    with path.open("w",newline="",encoding="utf-8-sig") as f:
        w = csv.DictWriter(f,fieldnames=keys)
        w.writeheader()
        w.writerows(rows)


def reference():
    with REFERENCE.open(encoding="utf-8-sig",newline="") as f:
        exact = sorted((float(r["Cmax_s"]),float(Fraction(r["B_fraction"]))) for r in csv.DictReader(f))
    unsupported = []
    for a,b in exact:
        low = max([0.]+[(b-y)/(x-a) for x,y in exact if x>a])
        high = min([math.inf]+[(y-b)/(a-x) for x,y in exact if x<a])
        if low>high or high<=0:
            unsupported.append((a,b))
    return exact,unsupported


def normalized(point,bounds):
    return tuple((p-a)/(b-a) for p,(a,b) in zip(point,bounds))


def hv(points,bounds):
    total,best_y = 0.,1.1
    for x,y in sorted(normalized(p,bounds) for p in points):
        if x<1.1 and y<best_y:
            total += (1.1-x)*(best_y-y)
            best_y = y
    return total


def igdplus(points,exact,bounds):
    normalized_set = [normalized(p,bounds) for p in points]
    return st.mean(min(math.hypot(max(0,x-a),max(0,y-b)) for x,y in normalized_set)
                   for a,b in (normalized(p,bounds) for p in exact))


def hits(points,reference_points):
    return sum(any(max(abs(a-x),abs(b-y))<=TOL for x,y in points) for a,b in reference_points)


def fmt(x,prec=3):
    if x is None:
        return "—"
    return f"{x:.{prec}f}".rstrip("0").rstrip(".") if prec else str(round(x))


def nondominated(points):
    result = []
    for x,y in sorted(points):
        if not result or y<result[-1][1]-TOL:
            if result and abs(x-result[-1][0])<=TOL:
                result.pop()
            result.append((x,y))
    return result


def audit_and_score(out):
    perf = time.monotonic()
    completed = out/"completed_for_audit.json"
    state = read(completed if completed.exists() else out/"finished.json")
    if state["failed"] or len(state["done"])!=state["total"] or not state["sources_match"]:
        raise RuntimeError("An incomplete or changed campaign cannot be scored")
    target = out/"evaluation"
    target.mkdir(exist_ok=True)
    protocol=read(out/"protocol.json")
    from campaign import fingerprints
    if fingerprints()!=protocol["code"] or digest(protocol["policy"]["checkpoint"])!=protocol["policy"]["sha256"]:
        raise RuntimeError("Model, solver, or frozen checkpoint changed after the campaign")
    shared=out/"shared_initials"
    for entry in read(shared/"manifest.json").values():
        if digest(shared/entry["file"])!=entry["sha256"]:
            raise RuntimeError("A shared initial schedule changed after the campaign")
    exact,unsupported = reference()
    bycase = defaultdict(list)
    for key,rel in state["done"].items():
        file = out/rel
        run = read(file)
        bycase[run["spec"]["case"]].append((file,run))
    summary,points,curves,audits,operators,allruns = [],[],[],[],[],{}
    replay_count=0
    auc_times=(0,.1,.25,.5,.75,1.)
    for case in sorted(bycase,key=lambda c:(len(bycase[c]),c)):
        cfg = config(case)
        full = Native(cfg,1,25)
        seen = {}
        try:
            for file,run in bycase[case]:
                s = run["spec"]
                key = s["id"]
                weight=s.get("weight",25)
                pset=[]
                for v in run["front"]:
                    path = file.parent/v["schedule"]
                    with gzip.open(path,"rt",encoding="utf-8") as f:
                        d=json.load(f)
                    if json.dumps(d["config"],sort_keys=True)!=json.dumps(run["config"],sort_keys=True):
                        raise ValueError(f"{path}: config")
                    # Full original-row certification uses a sparse floating-point assignment
                    # reconstructed from equipment events, independently of the search LP.
                    sig = hashlib.sha256(json.dumps([d["events"],d["jobs"],d["cycles"],d["pairs"],d["cmax"]],
                                        sort_keys=True,separators=(",",":")).encode()).hexdigest()
                    if sig not in seen:
                        validation=validate(d)
                        original = full.warm(d)
                        seen[sig] = (validation["valid"],original,validation["checks"])
                    physical,original,checks=seen[sig]
                    m=metrics(d,weight)
                    ab=m["cmax"],m["secondary"]
                    if not physical or not original or max(abs(ab[0]-v["a"]),abs(ab[1]-v["b"]))>TOL or v["t"]>s["budget"]:
                        save(target/"audit_failure.json",dict(cell=key,schedule=str(path),physical=physical,
                             original=original,event_scores=ab,archive_scores=[v["a"],v["b"]],runtime=v["t"]))
                        raise ValueError(f"Revalidation failed: {key} {path.name}, original={original}")
                    pp=sum(sum(w.startswith("LP") for w in pair["members"])==2 for pair in d["pairs"])
                    n=sum(j["product"] for j in d["jobs"])
                    bound=lower_bound(cfg,n,pp)
                    if ab[1]+TOL<bound:
                        raise ValueError("Pair bound violated")
                    common=dict(id=key,suite=s["suite"],case=case,method=s["method"],seed=s["seed"],weight=weight)
                    points.append(common|dict(A=ab[0],B=ab[1],L_sum=m["wait_sum"],L_max=m["wait_max"],R=m["rhythm"],
                                rhythm_centers=m["rhythm_centers"],PP=pp,PD=n-2*pp,bound=bound,admitted_s=v["t"],
                                physical_checks=checks,original_rows=full.x.original_dimensions["constraints"],
                                original_check=True,sha256=digest(path),schedule=path.relative_to(out).as_posix()))
                    pset.append(ab)
                    replay_count+=1
                for i,ab in enumerate(pset):
                    for other in pset[i+1:]:
                        duplicate=max(abs(a-b) for a,b in zip(ab,other))<=TOL
                        if duplicate or dominates(ab,other) or dominates(other,ab):
                            raise ValueError(f"{key}: returned archive contains a dominated or duplicate point")
                    if case=="S1" and weight==25 and not any(a<=ab[0]+TOL and b<=ab[1]+TOL for a,b in exact):
                        raise ValueError(f"{key}: physical point is outside the certified S1 attainable boundary")
                bounds=((331.,519.),(42.,424/3)) if case=="S1" and weight==25 else (
                        (0.,1.5*run["initial"][0]),(0.,2*run["initial"][1]))
                caps=(lower_bound(cfg,n,0),50*n,lower_bound(cfg,n,0)+.25*(run["initial"][1]-lower_bound(cfg,n,0)))
                capvals=[min((a for a,b in pset if b<=cap+TOL),default=None) for cap in caps]
                matched=case=="S1" and weight==25
                rec=common|dict(budget_s=s["budget"],search_wall_s=run["search_wall_s"],shared_spbs_s=run["shared_spbs_seconds"],
                     rejected_original_rows=run["stats"].get("rejected_original_rows",0),
                     last_admitted_s=run["last_eligible_s"],front_count=len(pset),HV=hv(pset,bounds),
                     IGD_plus=igdplus(pset,exact,bounds) if matched else None,
                     hit7=hits(pset,exact) if matched else None,hit3=hits(pset,unsupported) if matched else None,
                     A_min=min(a for a,b in pset),B_min=min(b for a,b in pset),
                     B_floor=caps[0],A_at_floor=capvals[0],B_operating=caps[1],A_at_operating=capvals[1],
                     B_intermediate=caps[2],A_at_intermediate=capvals[2],scale_A_min=bounds[0][0],scale_A_max=bounds[0][1],
                     scale_B_min=bounds[1][0],scale_B_max=bounds[1][1],ref_x=1.1,ref_y=1.1,
                     bound_skips=run["stats"].get("screened",0),lp_calls=run["stats"].get("timing_lp_calls",0),
                     candidate_events=run["stats"].get("validated",0),late_excluded=run["stats"].get("late_excluded",0),
                     global_nodes=sum(q["nodes"] for q in run["subproblems"] if q["scope"]=="unrestricted"),
                     callbacks=(run["policy"] or {}).get("callback_calls",0),width=s.get("width",.3),repair=s.get("repair",.22))
                summary.append(rec)
                allruns[key]=(rec,pset)
                for fraction in auc_times:
                    available=[(a,b) for t,a,b in run["history"] if t<=fraction*s["budget"]]
                    if s["method"]=="legacy" and available:
                        available=[min(available,key=lambda p:(round(p[0],5),p[1]))]
                    curves.append(common|dict(fraction=fraction,wall_s=fraction*s["budget"],HV=hv(available,bounds)))
                for k,q in enumerate(run["subproblems"]):
                    operators.append(common|dict(call=k+1)|q)
            audits.append(dict(case=case,unique_witnesses=len(seen),variables=full.x.original_dimensions["variables"],
                               rows=full.x.original_dimensions["constraints"],all_original_and_physical=True))
            print(f"全模型复验 {case} | 去重排程 {len(seen)} | 累计归档点 {replay_count} | {'、'.join(bycase)}",flush=True)
        finally:
            full.close()
    write_csv(target/"runs.csv",summary)
    write_csv(target/"points.csv",points)
    write_csv(target/"hv_time.csv",curves)
    write_csv(target/"subproblems.csv",operators)
    extra=grouped_results(summary,points,operators,exact,unsupported,target,write_csv,NAMES)
    contrasts=contrast_tables(summary,points,target,write_csv)
    save(target/"validation.json",dict(cells=len(summary),archived_witnesses=replay_count,by_case=audits,
         recovered=state.get("recovered",{}),released_after_row_failure=sum(q.get("status")=="candidate_rejected_original_rows" for q in operators),
         rejected_before_archive=sum(r["rejected_original_rows"] for r in summary),
         late_excluded=sum(r["late_excluded"] for r in summary),
         max_search_wall_over_budget_s=max(0,max(r["search_wall_s"]-r["budget_s"] for r in summary)),
         median_search_wall_over_budget_s=st.median(max(0,r["search_wall_s"]-r["budget_s"]) for r in summary),
         frozen_source_files=len(protocol["code"]),source_hashes_unchanged=True,
         checked_checkpoint_sha256=protocol["policy"]["sha256"],shared_initials_verified=len(read(shared/"manifest.json")),
         new_schedules_with_mixed_PP_PD=sum(p["PP"]>0 and p["PD"]>0 for p in points),
         new_schedules_with_positive_R=sum(p["R"]>TOL for p in points),reference_sha256=digest(REFERENCE),
         archived_inputs_have_original_rows=True,nondominance_checked_within_each_run=True,
         S1_certificate_dominates_or_matches_every_return=True,elapsed_s=time.monotonic()-perf))
    figures(target,summary,points,curves,exact)
    plot_contrasts(contrasts[0],target)
    report(target,summary,points,operators,exact,unsupported,extra,contrasts)
    return summary


def figures(target,rows,points,curves,exact):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({"font.family":["Microsoft YaHei","DejaVu Sans"],"axes.unicode_minus":False,
                         "figure.dpi":120,"savefig.dpi":190,"axes.spines.top":False,"axes.spines.right":False})
    cases=tuple(c for c in ("S1","M4","H4","H8","H16") if any(r["case"]==c for r in rows))
    representative={}
    for c in cases:
        for method in MAIN:
            group=sorted((r for r in rows if r["suite"]=="main" and r["method"]==method and r["case"]==c),
                         key=lambda r:(r["HV"],r["seed"]))
            if group:
                representative[c,method]=group[len(group)//2]["id"]
    save(target/"representative_runs.json",{f"{c}_{m}":v for (c,m),v in representative.items()})
    column_count=3 if len(cases)>4 else 2
    fig,axes=plt.subplots(2,column_count,figsize=(5.4*column_count,8.1),layout="constrained")
    for unused in list(axes.flat)[len(cases):]:
        unused.set_visible(False)
    for ax,case in zip(axes.flat,cases):
        if case=="S1":
            ax.scatter(*zip(*exact),s=110,facecolors="none",edgecolors="black",linewidths=1.2,label="认证前沿",zorder=1)
        for m in MAIN:
            selected=representative.get((case,m))
            pp=[(r["A"],r["B"]) for r in points if r["id"]==selected]
            if pp:
                ax.scatter(*zip(*pp),s=36,alpha=.83,marker=MARKERS[m],c=COLORS[m],label=NAMES[m])
        ax.set_title({"S1":"两片 S1","M4":"四片混合","H4":"留出四片，配方 3+1","H8":"留出八片混合","H16":"留出十六片混合"}[case],loc="left")
        ax.set_xlabel("产品完工时间 A（秒）")
        ax.set_ylabel("等待与节拍指标 B（加权秒）")
        ax.grid(alpha=.17)
    handles,labels=axes.flat[0].get_legend_handles_labels()
    fig.legend(handles,labels,loc="outside lower center",ncol=4,frameon=False)
    fig.savefig(target/"fronts_CN.png")
    plt.close(fig)
    fig,axes=plt.subplots(2,column_count,figsize=(5.0*column_count,7.8),layout="constrained")
    for unused in list(axes.flat)[len(cases):]:
        unused.set_visible(False)
    for ax,c in zip(axes.flat,cases):
        for m in MAIN:
            rs=[r for r in curves if r["suite"]=="main" and r["case"]==c and r["method"]==m]
            times=sorted({r["wall_s"] for r in rs})
            if times:
                ax.plot(times,[st.median(r["HV"] for r in rs if r["wall_s"]==t) for t in times],
                        marker=MARKERS[m],linewidth=1.4,markersize=4,color=COLORS[m],label=NAMES[m])
        ax.set_title(c,loc="left")
        ax.set_xlabel("整例预算时间（秒）")
        ax.set_ylabel("归一化超体积")
        ax.grid(alpha=.18)
    handles,labels=axes.flat[0].get_legend_handles_labels()
    fig.legend(handles,labels,loc="outside lower center",ncol=3,frameon=False)
    fig.savefig(target/"hv_time_CN.png")
    plt.close(fig)
    # The representative full-range S1 panel includes some high-wait incumbents.
    # Separate windows expose every certified isolated point without connecting gaps.
    fig,axes=plt.subplots(1,2,figsize=(10.5,4.4),layout="constrained")
    for ax,window in zip(axes,((327,345,117,149),(510,523,33,99))):
        ax.scatter(*zip(*exact),marker="o",facecolors="none",edgecolors="black",s=105,label="认证前沿")
        for method in MAIN:
            pts=[(p["A"],p["B"]) for p in points if p["id"]==representative["S1",method]]
            if pts:
                ax.scatter(*zip(*pts),color=COLORS[method],marker=MARKERS[method],s=40,label=NAMES[method])
        lo,hi,blo,bhi=window
        for a,b in exact:
            if lo<=a<=hi:
                ax.annotate(f"({fmt(a)}, {fmt(b,2)})",(a,b),xytext=(4,7),textcoords="offset points",fontsize=8)
        ax.set(xlim=(lo,hi),ylim=(blo,bhi),xlabel="产品完工时间 A（秒）",ylabel="等待与节拍指标 B（加权秒）")
        ax.grid(alpha=.18)
    axes[0].set_title("同一对产品",loc="left")
    axes[1].set_title("两组产品与辅助片配对",loc="left")
    handles,labels=axes[0].get_legend_handles_labels()
    fig.legend(handles,labels,loc="outside lower center",ncol=4,frameon=False)
    fig.savefig(target/"s1_certified_windows_CN.png")
    plt.close(fig)

    empirical=[]
    for case in cases:
        ps=[p for p in points if p["case"]==case and p["suite"]=="main"]
        unique=[]
        for p in sorted(ps,key=lambda p:(p["A"],p["B"],p["id"])):
            ab=p["A"],p["B"]
            if any(dominates((q["A"],q["B"]),ab) for q in ps):
                continue
            if any(max(abs(a-b) for a,b in zip(ab,q))<=TOL for q in unique):
                continue
            unique.append(ab)
            empirical.append(dict(case=case,A=p["A"],B=p["B"],cell=p["id"],schedule=p["schedule"]))
    write_csv(target/"empirical_fronts.csv",empirical)


def report(target,rows,points,operators,exact,unsupported,extra,contrasts):
    result=read(target/"validation.json")
    txt=["# RL-DMCT 双目标调度实验","",
         f"共完成 {len(rows)} 组。{result['archived_witnesses']} 份最终排程逐一通过独立设备事件校验和未缩减模型 D 的原始 SCIP 约束检查，覆盖不同算法、种子与权重的重复排程也计入。","","## 主比较","",
         "各单元格给出三个种子的中位数。HV 取大，IGD+ 取小。S1 采用认证前沿的两目标极值归一化。其余实例按共同初始排程预设尺度，所有算法使用同一个归一化参考点 (1.1, 1.1)。跨实例的 HV 使用不同尺度。工期与质量上限来自各自排程的事件时间。","",
         "| 实例 | 方法 | HV | IGD+ | 7点命中 | 非支持点命中 | B≤50N 有解次数 | 上限内工期中位数 / s |",
         "|---|---|---:|---:|---:|---:|---:|---:|"]
    for c in ("S1","M4","H4","H8","H16"):
        for m in MAIN:
            rs=[r for r in rows if (r["suite"],r["case"],r["method"])==("main",c,m)]
            if not rs:
                continue
            med=lambda field:st.median(vals) if (vals:=[r[field] for r in rs if r[field] is not None]) else None
            txt.append(f"| {c} | {NAMES[m]} | {fmt(med('HV'),5)} | {fmt(med('IGD_plus'),5)} | {fmt(med('hit7'))} | {fmt(med('hit3'))} | {sum(r['A_at_operating'] is not None for r in rs)}/{len(rs)} | {fmt(med('A_at_operating'))} |")
    txt+=["","[逐例前沿](fronts_CN.png) · [超体积随时间变化](hv_time_CN.png) · [全部单次结果](runs.csv) · [各点的实际目标与排程文件路径](points.csv)","","## 消融与扰动","",
          "| 实验 | 算例 | 方法或参数 | 次数 | HV 中位数 | 工期最小值的中位数 / s | B 最小值的中位数 |",
          "|---|---|---|---:|---:|---:|---:|"]
    groups=defaultdict(list)
    for r in rows:
        suite=r["suite"]
        if suite=="main" and r["method"]=="domain" and r["case"] in ("S1","M4"):
            groups["ablation",r["case"],NAMES["domain"]].append(r)
        if suite in ("ablation","paired","algorithm","machine","weight","long"):
            label=NAMES[r["method"]]
            if suite=="algorithm":
                label+=f" 邻域比例 {r['width']}，修复预算比例 {r['repair']}"
            if suite=="weight":
                label+=f" 节拍权重 {r['weight']}"
            groups[suite,r["case"],label].append(r)
    for (suite,c,label),rs in sorted(groups.items()):
        txt.append(f"| {suite} | {c} | {label} | {len(rs)} | {fmt(st.median(r['HV'] for r in rs),5)} | {fmt(st.median(r['A_min'] for r in rs))} | {fmt(st.median(r['B_min'] for r in rs))} |")
    txt+=["","不同节拍权重定义了不同的 B。同权重下比较算法。不同权重间比较总等待、最大单项等待、节拍偏差与选中的排程。独立对内次序消融保留跨配对搜索和全模型求解。六组配对算子实验共享同一父排程和相同释放数量，以识别设备资源选择方式的作用。[逐子问题结果与停止状态](subproblems.csv)","","## 证据范围","",
          f"归档中有 {result['new_schedules_with_mixed_PP_PD']} 份排程同时包含产品对和产品–辅助片对，有 {result['new_schedules_with_positive_R']} 份的节拍偏差大于零。每份排程均按实际配对数核验等待下界。S1 的 7 个全局点和其中 3 个非支持点仅用于评分。四片和留出实例展示的是各算法实际找到并通过原模型校验的样本非支配点。图中每个方法取该实例 HV 中位数对应的单次运行。原两阶段对照只交付一份排程。","",
          "NSGA-II 和 MOEA/D 是按本机 PlatEMO 的选择与分解规则实现的 Python 版本。两者共用设备解码、线性规划精修和可行性校验。冻结学习选割使用原检查点，实际回调次数按组保存在 runs.csv。工况扰动为有确定参数的重新排程。各阶段超时保留为求解状态，超出上限时间才返回的候选不参与评分。[原约束核验记录](validation.json)"]
    txt+=["","[两片认证前沿局部放大图](s1_certified_windows_CN.png) · [各算法三种子合并的经验非支配点及排程](empirical_fronts.csv)"]
    txt.extend(interpretation(rows,points,*extra,NAMES))
    txt.extend(contrast_text(*contrasts))
    txt+=["","[四片实例消融和算法参数的配对差值图](m4_ablation_parameters_CN.png)"]
    txt+=["",f"在规定时间内通过全模型目标与原始约束核对后才入档。入档前拦下 {result['rejected_before_archive']} 次原模型见证不一致，超时返回的 {result['late_excluded']} 个候选也未计分。"
          f"子求解器退出和释放模型可晚于记分截止，实测整例超出标称预算的时长中位数为 {result['median_search_wall_over_budget_s']:.2f} 秒，最大为 {result['max_search_wall_over_budget_s']:.2f} 秒。"
          f"启动和收尾核对了 {result['frozen_source_files']} 份冻结源码、学习策略文件和 {result['shared_initials_verified']} 份共同初始排程。[冻结清单](../protocol.json)"]
    recovered=result["recovered"]
    if recovered:
        txt+=["",f"原始运行有 {len(recovered)} 组在 SCIP 候选未通过原约束时中止。已保留失败日志，并用相同种子、预算及初始排程重做这几组，遇到这类候选即舍弃。补跑的结果用于这些组的评分。[补跑与原始记录的对应表](../completed_for_audit.json)"]
    (target/"report_CN.md").write_text("\n".join(txt)+"\n",encoding="utf-8")


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("out",type=Path)
    args=parser.parse_args()
    out=args.out.resolve()
    audit_and_score(out)
    from m4_slices import project
    project(out)
    projected=read(out/"evaluation/m4_slices/projection.json")
    floor_times=[a for g in projected["slices"] for a,b in g["vertices"] if b<=54+TOL]
    with (out/"evaluation/report_CN.md").open("a",encoding="utf-8") as f:
        f.write("\n## 四片实例的连续前沿区间\n\n")
        f.write(f"以四片主比较返回的 {projected['input_schedules']} 份排程为起点，"
                f"对 {projected['structures']} 套不同的整数决策开放全部连续时刻，"
                f"计算出 {projected['segments']} 条结构内有效线段，逐条检查端点和中点。"
                f"其中 {len(projected['envelope_segments'])} 段留在已访问结构合并后的非支配边界上。")
        if floor_times:
            f.write(f"在这些结构内，B=54 时最早可交付于 {min(floor_times):g} 秒。")
        f.write("图中的连线均来自同一整数决策下的连续可行区间。"
                "其他整数结构仍可能改善边界。投影计算的耗时独立于主比较预算。"
                "[四片连续前沿图](m4_slices/m4_conditional_front_CN.png) · [整数赋值、端点与中点](m4_slices/projection.json)\n")
        special=out.parent/"s1_refine01/independent_score.json"
        if special.is_file():
            small=read(special)
            f.write("\n## 两片实例的专用精修\n\n")
            f.write(f"精修复用了既有两片时序子模型，目标上限取自本次生成的排程。"
                    f"两个阶段共用 {small['elapsed_two_stages']:.2f} 秒，重新获得 {small['certified_hits']}/7 个认证点和 "
                    f"{small['unsupported_hits']}/3 个非支持点，HV 为 {small['HV']:.6f}，"
                    f"IGD+ 为 {small['IGD_plus']:.3g}。在 B≤100 时最早交付于 {small['A_at_B100']:.0f} 秒。"
                    "该结果单独记录于实例专用实验。[完整前沿图](../../s1_refine01/s1_complete_CN.png) · "
                    "[七份新排程的独立核验](../../s1_refine01/front_checked.csv)\n")
    from overview import summary
    summary(out/"evaluation")

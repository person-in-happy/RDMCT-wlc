"""Perform the evidence review before applying a supported result to the current local manuscript."""
from collections import defaultdict
from pathlib import Path
import shutil
from statistics import mean
import sys
import time

from inputs import BASE, JMS, SCENARIOS, read, save, sha
from review import contrasts, verify_one

LABELS=dict(default="SCIP默认", hem_spbs="HEM", feature_only="仅扩展特征",
            no_rerank="关闭重排", greedy="贪心解码", full="完整策略")


def score(value):
    return f"{value:.2f}".rstrip("0").rstrip(".")


def describe(effects):
    quality=[]
    efficiency=[]
    for r in effects:
        a,b,t=(r["metrics"][k] for k in ("f_A","f_B","A_seconds"))
        paired=r["pairs"]
        # A lower makespan, or lower process cost at like makespan, identifies
        # which objective improved. Time is compared separately at like outcomes.
        improves_a=a["higher"]==0 and a["lower"]>0
        improves_b=a["equal"]==paired and b["higher"]==0 and b["lower"]>0
        if improves_a or improves_b:
            quality.append(r)
        elif (a["equal"]==paired and b["equal"]==paired and t["higher"]==0 and t["lower"]>0
              and (r["comparison"]=="初始化" or r["metrics"]["calls"]["after"]>0)):
            efficiency.append(r)
    return quality,efficiency


def manuscript_text(rows,effects,quality,efficiency):
    means=defaultdict(list)
    for r in rows.values():
        means[r["case"],r["initialization"],r["method"]].append(r)
    def metrics(key):
        return [score(mean(v[k] for v in means[key])) for k in ("f_A","f_B","A_seconds")]
    table=[r"\paragraph{相同工期切换与工艺停机阈值下的消融}",
           r"在16片混合实例上取$\bar g_A=\bar g_B=0.01\%$。各配置从同一构造排程或相应的SPBS排程开始，达到工期阈值后切换，达到工艺目标的子问题阈值后结束。工期搜索的候选容量由共同构造工期上界和设备容量确定。表~\ref{tab:mixed-gap-paired-cn}中的$t_A$从工期搜索开始计时，初始化用时另计。",
           r"\begin{table}[!htbp]\centering\small",
           r"\caption{16片混合实例在相同双阈值下的目标及工期搜索用时（s）}",
           r"\label{tab:mixed-gap-paired-cn}\resizebox{\columnwidth}{!}{%",
           r"\begin{tabular}{@{}lrrrrrr@{}}\toprule",
           r"& \multicolumn{3}{c}{构造排程} & \multicolumn{3}{c}{SPBS排程}\\",
           r"\cmidrule(lr){2-4}\cmidrule(l){5-7}",
           r"选割策略 & $f_A$ & $f_B$ & $t_A$ & $f_A$ & $f_B$ & $t_A$\\\midrule"]
    for k,label in LABELS.items():
        table.append(" & ".join([label,*metrics(("H6","raw",k)),*metrics(("H6","prepared",k))])+r"\\")
    table+= [r"\bottomrule\end{tabular}}\end{table}",""]
    h6=next(r for r in effects if r["case"]=="H6" and r["comparison"]=="初始化")
    a,b,t=(h6["metrics"][k] for k in ("f_A","f_B","A_seconds"))
    table.append(f"在$H=6$的完整策略对照中，直接求解和启用SPBS的平均工期分别为{score(a['before'])}和{score(a['after'])}~s，工艺目标分别为{score(b['before'])}和{score(b['after'])}~s，达到第一阶段阈值的用时分别为{score(t['before'])}和{score(t['after'])}~s。")
    table+=["",r"另将两种配方各8片产品分别集中在LP1、均分至四个LP、均分至LP1和LP2，对应的清洁阈值依次为2、3、5，辅助片库存为4、6、8片。各学习配置采用三个训练种子，与三个求解种子交叉配对。"]
    for case in ("S1","S2","S3"):
        row=next(r for r in effects if r["case"]==case and r["comparison"]=="hem_spbs")
        a,b,t=(row["metrics"][k] for k in ("f_A","f_B","A_seconds"))
        table.append(f"在$H={SCENARIOS[case][1]}$的场景中，共用SPBS排程的HEM与完整策略分别得到工期{score(a['before'])}和{score(a['after'])}~s，工艺目标{score(b['before'])}和{score(b['after'])}~s，工期搜索用时{score(t['before'])}和{score(t['after'])}~s。")
    # Expose both improvements and adverse directions in the selected component comparison.
    component=next((r for r in quality+efficiency if r["comparison"] in ("no_rerank","greedy","feature_only")),None)
    if component:
        r=component
        a,b,t=(r["metrics"][k] for k in ("f_A","f_B","A_seconds"))
        table+=["",f"在$H={SCENARIOS[r['case']][1]}$的{LABELS[r['comparison']]}与完整策略对照中，工期分别为{score(a['before'])}和{score(a['after'])}~s，工艺目标分别为{score(b['before'])}和{score(b['after'])}~s，工期搜索用时分别为{score(t['before'])}和{score(t['after'])}~s。"]
    return "\n".join(table)+"\n\n"


def finish():
    from tempfile import TemporaryDirectory
    from importlib.util import module_from_spec, spec_from_file_location
    jobs=read(BASE/"protocol.json")["jobs"]
    rows={k:verify_one(k,j) for k,j in jobs.items()}
    effects=contrasts(rows,jobs)
    assert len(effects)==len(SCENARIOS)*6
    quality,efficiency=describe(effects)
    stats=dict(verified=len(rows), objective_comparisons=quality, time_comparisons=efficiency)
    save(BASE/"final_review.json",stats)
    if not quality and not efficiency:
        save(BASE/"disposition.json",dict(status="reviewed",manuscript_change=False,
             reason="No consistent paired advantage in the predefined comparisons; directions, ties and callbacks in REVIEW_CN.md."))
        return
    manuscript=JMS/"JMS_Review_CN.tex"
    before=manuscript.read_bytes()
    current=before.decode("utf8")
    marker=r"\paragraph{固定和放开配对、分腔与周期}"
    revised=manuscript_text(rows,effects,quality,efficiency)
    if r"\label{tab:mixed-gap-paired-cn}" in current:
        if revised.replace("\n","") not in current.replace("\r","").replace("\n",""):
            raise ValueError("An existing gap section differs. The verified review is preserved.")
        return
    if current.count(marker)!=1:
        (BASE/"verified_section.tex").write_text(revised,encoding="utf8")
        raise ValueError("The section anchor has changed; the reviewed draft is saved.")
    candidate=current.replace(marker,revised+marker)
    spec=spec_from_file_location("paper_build",JMS/"tools/build_model4_cn.py")
    builder=module_from_spec(spec)
    spec.loader.exec_module(builder)
    with TemporaryDirectory(prefix="jms-gap-review-", dir=BASE) as folder:
        d=Path(folder)
        paper=d/"paper"
        scratch=d/"build"
        paper.mkdir()
        scratch.mkdir()
        for f in builder.flat_figures(candidate):
            shutil.copy2(f,paper/f.name)
        builder.PAPER=paper
        builder.MAIN=paper/manuscript.name
        builder.BUILD=paper/"output/model4_cn_build"
        builder.MAIN.write_bytes(candidate.encode("utf8"))
        builder.build(scratch)
        assert manuscript.read_bytes()==before, "The user edited the manuscript while it was being checked"
        # Keep the entire former source and the new rendered proof before local publication.
        rev=JMS/"revisions"/"mixed_gap_ablation_20261122"
        rev.mkdir(parents=True,exist_ok=True)
        (rev/"before.tex").write_bytes(before)
        shutil.copy2(builder.BUILD/"build_report.json",rev/"build_report.json")
        pdfname=manuscript.with_suffix(".pdf").name
        for src,dst in ((builder.MAIN,manuscript),(paper/pdfname,manuscript.with_suffix(".pdf")),
                        (paper/pdfname,JMS/"output/pdf"/pdfname)):
            tmp=dst.with_suffix(dst.suffix+".gap.tmp")
            shutil.copy2(src,tmp)
            tmp.replace(dst)
    save(BASE/"disposition.json",dict(status="reviewed",manuscript_change=True,source_sha256=sha(manuscript),
         pdf_sha256=sha(manuscript.with_suffix(".pdf"))))


if __name__=="__main__":
    while True:
        review=BASE/"review.json"
        if review.exists():
            result=read(review)
            if result["verified"]==result["expected"]:
                finish()
                break
        progress=BASE/"progress.json"
        if progress.exists():
            status=read(progress)
            if not status["queued"] and not status["active"] and status["failed"]:
                failures={}
                for key,exit_info in status["failed"].items():
                    folder=BASE/"runs"/key
                    logs=sorted(folder.glob("console-*.log"))
                    failure=logs[-1].read_text(encoding="utf8",errors="replace").splitlines()[-8:] if logs else []
                    live=read(folder/"live.json") if (folder/"live.json").is_file() else {}
                    failures[key]=dict(reason=failure, last_observation=live, **exit_info)
                save(BASE/"unreached.json",dict(completed=status["completed"],expected=status["total"],failures=failures))
                break
        if "--watch" not in sys.argv:
            print("Waiting for independently verified two-stage results.",flush=True)
            break
        time.sleep(40)

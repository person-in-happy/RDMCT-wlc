"""Revise a checked working copy of the actual master's thesis and verify the installed PDF."""
from pathlib import Path
import re
import shutil
import sys

from case_setup import HERE, digest, read, save
from analysis_fronts import REPORT, csvrows
import manuscript as thesis

STAGE = HERE / "manuscript_build"
BACKUP = HERE / "manuscript_backup"
MANIFEST = REPORT / "manuscript_manifest.json"
thesis.STAGE, thesis.PRIOR, thesis.REPORT, thesis.MANIFEST = STAGE, BACKUP, REPORT, MANIFEST
FIGURES = ("pareto_s1", "pareto_75", "paired75_lines", "engineering75")


def section():
    data = read(REPORT / "verified.json")
    mech = read(REPORT / "mechanism_verified.json")
    assert (data["paired_cells"], mech["ablation_cells"], mech["combined_unique"]) == (96, 72, 698)
    assert mech["combined_points"] == {"mix37": 35, "mix50": 10}
    med = {(r["case"], r["method"]): r["HV"] for r in data["summaries"]}
    cases = [("mix37", "37+38"), ("mix50", "50+25")]
    med_rows = []
    effect_rows = []
    for case, name in cases:
        values = [f"{med[case,m]:.5f}" for m in ("domain", "uniform", "nsga2", "moead")]
        med_rows.append(" & ".join([name, *values]) + r" \\")
        for test in (r for r in mech["effects"] if r["case"] == case):
            edits = test["opponent"] == "no_blocks"
            assert (test["wins"] == test["full_HV_wins"] == 12) == edits
            title = "关闭局部块调整" if edits else "改用随机初始结构"
            counts = f"{test['wins']} & {test['ties']}"
            p = f"{test['p_holm']:.5f}" if edits else "1.00000"
            effect_rows.append(f"{name} & {title} & {counts} & \u0024{test['median_delta']:+.5f}\u0024 & {p}" + r" \\")
    front = csvrows(REPORT / "engineering_fronts.csv")
    assert [(min((float(r["A"]), float(r["B"])) for r in front
                 if r["case"] == c and float(r["B"]) <= 2000)) for c, _ in cases] == [(7639, 1951), (7720, 1979)]
    body = (thesis.get(HERE / "paired_section.tex")
            .replace("%%MEDIANS%%", "\n".join(med_rows))
            .replace("%%EFFECTS%%", "\n".join(effect_rows)))
    for row in data["comparisons"]:
        case = {"mix37": "M37", "mix50": "M50"}[row["case"]]
        token = f"%%{case}_{row['opponent'].upper()}%%"
        body = thesis.once(body, token, f"{row['wins']}胜、{row['ties']}平")
    assert "%%" not in body
    return body


def replace_tail(text, start, new):
    selected = [line for line in text.splitlines() if start in line]
    assert len(selected) == 1, start
    line = selected[0]
    return thesis.once(text, line, line.split(start)[0] + new)


def manuscript_changes():
    content = STAGE / "contents"
    text = thesis.get(content / "chap5.tex")
    text = thesis.once(text, "两片算例S1在两种配对方式下的完整前沿。两图分别标注原始坐标，三枚菱形为线性加权和无法取得的非支持点。",
                       "两片算例S1的七个认证点及线性加权和的四个支持点。阶梯给出交期内可达的最低指标，右图放大含三个非支持点（菱形）的区间。")
    text = thesis.once(text, "75片混合批次的经验前沿。左图叠加各方法提交点、共同起点与全部发现记录的合并非支配点，右图放大最短工期端。每个非支配点均有独立核验的完整可行排程。",
                       "37+38片限时实验的经验前沿。左图按方法合并三个种子的提交点，右图放大较早交付的区间，黑色点线纳入所有方法未截断的内部档案。")
    text = thesis.once(text, r"图~\ref{fig:pareto75}汇集全部12次运行在限时内发现的非支配解，含单次提交时被七点上限省略的内部点。",
                       r"图~\ref{fig:pareto75}的黑色点线汇集原90~s实验各方法发现的非支配解，含单次提交时被七点上限省略的内部点。")
    text = thesis.once(text, "75片的12次运行共提交78份排程。", "该90~s实验提交了78份排程。")
    text = thesis.once(text, '新六实例对照的414次主求解均未超过各自预算', '新增实例对照的主求解均在各自预算内完成')
    text = thesis.once(text, '正常分离初轮72次和补充96次合计168次，全部赋值通过完整D模型检查及物理重放。', '正常分离实验的全部赋值均通过完整D模型检查及物理重放。')
    text = thesis.once(text, '四实例上RL-DMCT相对HEM+SPBS的平均相对改善约0.0600\\%，胜/平/负为1/3/0', 'RL-DMCT相对HEM+SPBS的平均相对改善约0.0600\\%，1胜、3平')
    text = thesis.once(text, '根分离的九臂覆盖108次，训练种子固定为1，三个求解种子。', '根分离组件对照将训练种子固定为1，使用三个求解种子。')
    text = thesis.once(text, '正常分离六臂首轮72次包含在前述168次中。', '')
    text = thesis.once(text, '，共36次，均经完整D验证。', '，所得排程均经完整D验证。')
    text = thesis.once(text, '三种策略，共36次运行。', '三种策略。')
    text = thesis.once(text, '；各比较提前清洁与原触发规则、三个求解种子，共144次。', '。各配置使用三个求解种子比较提前清洁与原触发规则。')
    text = thesis.once(text, '，共414次算法运行，加上18次共享准备形成432个队列单元；432份赋值均通过完整模型约束检查和独立物理重放。', '。算法和共享准备生成的赋值均通过完整模型约束检查和独立物理重放。')
    text = thesis.once(text, '再对六个实例等权汇总，平均改善为0.0776\\%，中位数为0，胜/平/负为2/4/0；按实例重采样', '再对各实例等权汇总，平均改善为0.0776\\%，中位数为0，2胜、4平。按实例重采样')
    text = thesis.once(text, '此前小规模主比较连同消融、参数扰动和长预算实验共164组，699份最终排程均已核对。', '小规模主比较、消融、参数扰动和长预算实验提交的699份最终排程均已核对。')
    thesis.put(content / "chap5.tex", text.rstrip() + "\n\n" + section().strip() + "\n")

    text = thesis.get(content / "chap4.tex")
    anchor = "领域搜索从已有非支配解中选择父排程，提高在设备内停留较久的产品被调整的概率。"
    text = thesis.once(text, anchor,
        "每个候选结构记录一类整体取放次序和至多三项局部块调整。六类预设结构覆盖不同的整体取放次序，各自可独立进行重定时。领域搜索从已有非支配解中选取父排程；执行局部修改时，以0.65的概率从驻留时间最长的12片产品中抽取一片，否则从全部产品中抽取，以此定位待改动的生产块。".replace("排程；执行", "排程。执行"))
    thesis.put(content / "chap4.tex", text)

    text = thesis.get(content / "abstract.tex")
    text = replace_tail(text, "75片混合批次获得20个",
        "两种75片配方组合分别得到35和10个经原模型复验的经验非支配点。以超体积比较，保留生产块局部调整在两种组合中均为12胜、0平，领域搜索与NSGA-II和MOEA/D的比较结果则随工况和种子而变。")
    text = replace_tail(text, "For 75 product wafers, 20",
        "Two 75-wafer recipe mixes yield 35 and 10 empirically nondominated points verified against the full model. Allowing local changes to production blocks yields 12 wins and no ties per mix on hypervolume. Comparisons with NSGA-II and MOEA/D vary across mixes and seeds.")
    text = thesis.once(text, '正常分离下的四实例168次对照表明', '正常分离下的实例对照表明')
    text = thesis.once(text, '其414次算法比较中，混合场景S2的平均产品完工时间经初始化由521降至492~s；共享SPBS起点后', '混合场景S2的平均产品完工时间经初始化由521降至492~s。共享SPBS起点后')
    text = thesis.once(text, '胜、平、负为2、4、0', '2胜、4平')
    text = thesis.once(text, 'On four instances, 168 comparisons under standard separation show initialization gains', 'Comparisons under standard separation show initialization gains')
    text = thesis.once(text, 'Across their 414 algorithm runs, initialization reduces the mean makespan from 521 to 492 s in mixed scenario S2.', 'In mixed scenario S2, initialization reduces the mean makespan from 521 to 492 s.')
    text = thesis.once(text, 'two wins, four ties, and no losses', 'two wins and four ties')
    thesis.put(content / "abstract.tex", text)

    text = thesis.get(content / "chap1.tex")
    text = thesis.once(text, "并用75片批次考察排程能否逐片执行。", "并用两种75片配方组合复验逐片排程，检验相同初始结构与评价预算下局部调整生产块的收益。")
    thesis.put(content / "chap1.tex", text)
    text = thesis.get(content / "chap6.tex")
    text = replace_tail(text, "75片混合批次得到20个",
        "两种75片配方组合分别得到35和10个经验非支配点。相同初始结构与160次候选评价下，领域搜索相对两个进化基线的差异未达显著水平。相较关闭局部生产块调整，完整方法在两种工况均为12胜、0平，HV配对差值中位数分别为0.01132和0.02651。大批次实验支持将局部块调整与重定时结合以扩大交付和等待的可选范围。")
    text = thesis.once(text, "并改变配方比例、库存和清洁阈值", "并在更多配方比例、辅助库存和清洁阈值下")
    text = thesis.once(text, "阈值下，检验", "阈值下检验")
    text = thesis.once(text, '四实例168次对照中，', '正常分离实验中，')
    text = thesis.once(text, '六个2片实例共享SPBS起点的414次比较中，', '共享SPBS起点后，')
    text = thesis.once(text, '两胜四平', '2胜、4平')
    thesis.put(content / "chap6.tex", text)
    text = thesis.get(content / "bibliography.tex")
    refs = r"""
\bibitem{fonseca2011eaf}
Fonseca CM, Guerreiro AP, López-Ibáñez M, Paquete L. On the computation of the empirical attainment function.
In: Evolutionary Multi-Criterion Optimization. LNCS 6576. Berlin: Springer, 2011, pp.~106--120.
\url{https://doi.org/10.1007/978-3-642-19893-9_8}.

\bibitem{holm1979}
Holm S. A simple sequentially rejective multiple test procedure.
Scand J Stat 1979;6(2):65--70.
\url{https://www.jstor.org/stable/4615733}.
"""
    thesis.put(content / "bibliography.tex", thesis.once(text, r"\end{thebibliography}",
              refs.strip() + "\n" + r"\end{thebibliography}"))


def stage():
    directory = thesis.THESIS
    STAGE.mkdir(exist_ok=True)
    BACKUP.mkdir(exist_ok=True)
    inputs = thesis.filelist()
    before = {p: digest(directory / p) for p in [*inputs, "main.pdf"]}
    if MANIFEST.exists():
        assert read(MANIFEST)["before"] == before, "The thesis has changed since staging"
    for name in inputs:
        dest = STAGE / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(directory / name, dest)
    manuscript_changes()
    for name in FIGURES:
        shutil.copy2(REPORT / "figures" / (name+".pdf"), STAGE / "figures" / (name+".pdf"))
    thesis.latex(STAGE)
    pages = thesis.page_texts(STAGE)
    reference_count = len(re.findall(r"\\bibitem(?:\[[^\]]*\])?\{", thesis.get(STAGE/"contents/bibliography.tex")))
    assert reference_count == 54
    new_note = "两种75片配方组合分别得到35和10个经原模型复验的经验非支配点。共享初始化后开展算法对照，并用独立种子进行机制消融。保留局部生产块调整在两种工况均为12胜、0平。"
    rd = STAGE / "README.md"
    text = thesis.once(thesis.get(rd), "参考文献52条", f"参考文献{reference_count}条")
    text = replace_tail(text, "当前编译版共 65 页。", f"当前编译版共 {len(pages)} 页。两片算例有完整前沿证书。" + new_note + "默认配置D的100片结果仍待验证。")
    thesis.put(rd, text)
    notes = STAGE / "缺口与实验命令.md"
    text = thesis.get(notes)
    text = replace_tail(text, "2026-11-19 更新。第三个创新点",
        "2026-11-19 更新。第三个创新点为基于配对等待下界的双目标邻域搜索。" + new_note +
        "第四至六章已纳入同预算对照、消融和交期选择。下文保留11月16日方案与运行记录。"
        + "实验数据见[共享起点与消融复核](D:/git/git/RDMCT-A3C/JMS-version/experiments/pareto75_front_comparison_20261119/review/review_CN.md)和[原限时实验](D:/git/git/RDMCT-A3C/JMS-version/experiments/pareto75_thesis_20261119/review/review_CN.md)。")
    thesis.put(notes, text)
    changed = [p for p in inputs if digest(STAGE / p) != before[p]]
    new = ["figures/"+s+".pdf" for s in FIGURES if "figures/"+s+".pdf" not in inputs]
    for p in [*changed, "main.pdf"]:
        backup = BACKUP / p
        backup.parent.mkdir(parents=True, exist_ok=True)
        if not backup.exists():
            shutil.copy2(directory / p, backup)
        assert digest(backup) == before[p]
    staged = {p: digest(STAGE / p) for p in [*changed, *new, "main.pdf"]}
    save(MANIFEST, dict(before=before, changed=changed, new=new, staged=staged, pages=len(pages), references=reference_count))
    print("Staged", len(pages), "pages,", reference_count, "references,", changed, new, flush=True)


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "stage":
        stage()
    elif cmd == "install":
        thesis.install()
    else:
        import layout_review as qa
        {"render": qa.prepare, "accept": qa.accept, "check-installed": qa.installed}[cmd]()

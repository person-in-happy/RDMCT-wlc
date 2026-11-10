"""Insert verified supplement tables and revise the surrounding evidence claims."""
from pathlib import Path
import sys
import json
from statistics import mean

HERE = Path(__file__).resolve().parent
PAPER = HERE.parents[1]
report = json.loads((HERE / 'verified_supplements.json').read_text('utf-8'))
assert report['completed'] == report['original_assignment_replays'] == 114
assert report['raw_results_unchanged'] and report['cleanup_improved'] == 16
src = (PAPER / 'JMS_Review_CN.tex').read_text('utf-8')
original = (HERE / 'original/JMS_Review_CN.tex').read_text('utf-8')
groups = {(g['suite'], g['case'], g['arm'], g['weight']): g for g in report['groups']}


def group(suite, case, arm, weight=None):
    return groups[suite, case, arm, weight]


def part(start, end):
    return original.split(start, 1)[1].split(end, 1)[0]


settings = r'''\section{计算实验与结果分析}
\label{sec:experiments-cn}

实验围绕批次编码的可行性、两阶段目标的作用及规模变化展开。采用初始化、固定结构和节拍项对照分析排程质量，并对最终执行输出进行收尾规范化。

\subsection{实例、计算设置与验证方法}

采用参数化生成的4、8、16、24和32片实例，设备时长、容量及驻留上限见表~\ref{tab:symbol-cn-a}。除腔室资格实验外，同配方产品均允许使用CH2和CH3，按模式组成Pjob；产品在LP1--LP4间均衡分配。混合实例中两种配方各占一半，辅助晶圆共8片。动作时长用于统一比较配方与物料来源，驻留上限及计算时域作为实例参数保存。每个实例与配置使用种子1、2、3；先在同一实例内汇总种子，再比较不同实例。批次内统一出片为给定的供片规则。

计算平台为Windows~11、20逻辑处理器和约32~GB内存，使用Python~3.12.12、PySCIPOpt~6.1.0及PyTorch~2.11.0。每个SCIP任务使用单线程。基础、资格、原节拍和选割实验最多并行两个任务，SCIP内存限额为6000~MiB，进程RSS上限为7000~MiB；同一GPU最多运行一个学习策略任务。阈值与32片实验串行执行，初始SCIP内存限额为18944~MiB，进程上限为14336~MiB。32片纯$2\times2$的三次进程内存中断另以12288~MiB和18432~MiB的对应限额运行，保持实例、种子及初始赋值一致。

基础单阶段预算为300~s，两阶段配置采用270~s主求解和30~s精修，SPBS预算为20~s。定向固定结构对照采用300~s总求解预算；先固定结构再联合搜索的配置分配60~s与240~s。长链节拍实验复用同一第一阶段完整赋值，精修预算60~s；输出收尾预算60~s。三组定向实验均串行执行，固定结构与收尾组的SCIP/进程内存限额为6000/7000~MiB，长链节拍组为10000/14000~MiB。

建模、初始赋值准备和求解时间分别记录。SCIP在算法检查点响应限额，本文同时保留设定预算与实际停止时间。例如，基础初始化对照的主求解实际停止时长为300--389~s，原实验时限停止记录的最大值为619~s。固定结构预求解的时间计入其方法预算。

表~\ref{tab:coverage-cn}区分主实验与定向补充记录。原453次完成运行中441次获得可行排程，12次冷启动在时间限额内未获得可行解；定向补充的114项全部保存可行排程，包括42项对已有输出的收尾处理。每份可行结果均检查原模型约束，独立重放编码覆盖、全Pjob严格出片、资格、满片、连续处理、机械手容量、驻留、回片及辅助片复用，并从实际事件重算指标。运行记录包含同一实例的种子、方法及后处理结果，独立实例按输入配置区分。

\begin{table}[!htbp]
\centering\small
\caption{实验与后处理的完成及可行结果数量}
\label{tab:coverage-cn}
\begin{tabular}{lrrr}\toprule
实验组 & 完成 & 可行 & 执行中断\\\midrule
基础与初始化 & 102 & 90 & 0\\
腔室资格 & 6 & 6 & 0\\
原节拍目标消融 & 48 & 48 & 0\\
学习选割对照 & 72 & 72 & 0\\
清洁阈值与配方 & 216 & 216 & 0\\
32片原资源配置 & 6 & 6 & 3\\
32片资源调整 & 3 & 3 & 0\\\midrule
固定结构与强起点 & 36 & 36 & 0\\
长链节拍与权重 & 36 & 36 & 0\\
输出收尾处理 & 42 & 42 & 0\\\midrule
结果记录合计 & 567 & 555 & 3\\\bottomrule
\end{tabular}
\par\smallskip\footnotesize 收尾处理复用已有两阶段排程；强起点的12次内部预求解计入对应方法，未另计为独立结果。
\end{table}

'''

encoding = r'\subsection{批次编码、腔室资格与排程数量}' + part(
    r'\subsection{批次编码、腔室资格与排程数量}', r'\subsection{时序精修与节拍目标消融}')
refinement = r'\subsection{时序精修与节拍目标消融}' + part(
    r'\subsection{时序精修与节拍目标消融}', '为区分等待与节拍的作用，')
refinement = refinement.replace('最大单项等待均降至65~s', '最大路线等待项均降至65~s')
refinement = refinement.replace('为实际事件计算的总等待', '为实际事件计算的总路线等待')
refinement += r'''分解产品片与辅助片后，八种基础实例的产品路线等待均值下降13.82\%--62.86\%。资格双源实例的产品等待由938~s降至269~s，辅助片等待由20510~s降至84~s，分别下降71.32\%和99.59\%。这两类等待共同构成表中的总量，反映产品供回与辅助库存周转的同步改善。

8片纯$2\times2$的原目标消融包括$H=5,10$和两种来源，各排程有两个节拍评价中心。双源实例在保持1213~s产品完工时间时，仅等待目标得到522~s路线等待和136~s节拍偏差；加入节拍项后分别为542~s和126~s，以20~s路线等待差异换得7.35\%的节拍偏差降幅。两种阈值在该组排程中均未触发清洁。线性与原二次目标得到相同的这些指标。

进一步从阈值实验中选取16片长链、24片含清洁链和24片混合配方，均采用双源配置，分别含6、8、2个节拍评价中心；后两个场景各执行2次清洁。同一实例、同一种子下，四个权重使用同一份第一阶段变量赋值，并固定相同的结构与资源次序。取$\lambda_3=0,5,25,100$，每组精修60~s，共36次运行；其中$\lambda_3=0$为去掉节拍项的消融。

\begin{table*}[t]
\centering\small
\caption{共同第一阶段排程下的长链、清洁与节拍权重实验（时间单位：s）}
\label{tab:rhythm-ablation-cn}
\begin{tabular}{llrrrrl}\toprule
实例 & $\lambda_3$ & $C_{\max}$ & $L_{\rm sum}$ & $L_{\max}$ & 节拍偏差和 & 精修停止状态\\\midrule
'''
for case, label in [('n16_H10_2x2_dual', r'16片，$H=10$，纯$2\times2$'),
                    ('n24_H5_2x2_dual', r'24片，$H=5$，纯$2\times2$'),
                    ('n24_H5_mixed_dual', r'24片，$H=5$，混合')]:
    init = group('rhythm', case, 'refinement', 0)['initial']
    def line(label, weight, m, status):
        return f"{label} & {weight} & {m['product_cmax']:.0f} & {m['route_wait_sum']:.0f} & {m['route_wait_max']:.0f} & {m['rhythm_deviation']:.0f} & {status}" + r'\\' + '\n'
    refinement += line(label, '第一阶段', init, '---')
    if 'n24_H5_2x2' in case:
        for w in (0, 5, 25, 100):
            assert group('rhythm', case, 'refinement', w)['statuses'] == {'memlimit': 3}
        refinement += line('', '0、5、25、100', group('rhythm', case, 'refinement', 0)['metrics'], '内存限额')
    else:
        refinement += line('', '0', group('rhythm', case, 'refinement', 0)['metrics'], '子问题最优')
        refinement += line('', '5、25、100', group('rhythm', case, 'refinement', 25)['metrics'], '子问题最优')
    refinement += r'\midrule' + '\n'
refinement = refinement.rsplit(r'\midrule', 1)[0] + r'''\bottomrule\end{tabular}
\par\smallskip\footnotesize 每个权重运行三个种子，表列均值，各种子在显示精度内一致；合并列示的权重分别运行并得到相同指标。子问题最优指固定主要离散结构的时序精修最优。24片纯$2\times2$的12次运行均在SCIP内存限额处停止并保留初始可行解。
\end{table*}

表~\ref{tab:rhythm-ablation-cn}中，16片长链仅等待目标将路线等待由1766~s降至1000~s；设置正节拍权重后，路线等待为1016~s，节拍偏差由792~s降至784~s，下降1.01\%，产品完工时间保持2537~s。权重5、25、100均实现这一权衡。24片混合配方中，路线等待由3745~s降至1440~s，下降61.55\%，最大路线等待项由437~s降至65~s，同时保持5199~s产品完工时间、20~s节拍偏差及两次清洁安排。该场景四种权重达到相同指标，显示给定结构下等待压缩与既有周期衔接可以兼容。24片纯链式场景保存了4785~s的可行产品完工时间，其各权重结果及内存停止状态一并列于表中。

\subsection{执行输出与完整收尾}

对24份基础精修、6份资格精修及12份原链式精修排程执行式~\eqref{eq:output-completion-cn}，共42次。全部达到固定离散选择下的收尾子问题最优，并保留输入的产品完工时间及完整二阶段目标上界。16份排程的$C_{\mathrm{end}}$缩短，其余26份保持原值；求解器报告的求解时间均不超过3~s，含建模、验解和保存的单项耗时不超过13.94~s。

\begin{table}[!htbp]
\centering\footnotesize
\setlength{\tabcolsep}{3pt}
\caption{单源排程收尾前后的完整完工时间（s）}
\label{tab:completion-cn}
\begin{tabular}{lrrrr}\toprule
实例 & $C_{\max}$ & 原$C_{\mathrm{end}}$ & 新$C_{\mathrm{end}}$ & 降幅(\%)\\\midrule
'''
for case, label, source in [('n4_H3_mixed_single', '4片，$H=3$', '单源'),
    ('n8_H3_mixed_single', '8片，$H=3$', '单源'),
    ('qualification_n8_mixed_single', '8片，资格异构', '单源')]:
    g = group('cleanup', case, 'cleanup', 25)
    a,b = g['initial'],g['metrics']
    reduction = 100*(a['modeled_completion']-b['modeled_completion'])/a['modeled_completion']
    refinement += f"{label} & {b['product_cmax']:.0f} & {a['modeled_completion']:.0f} & {b['modeled_completion']:.0f} & {reduction:.2f}" + r'\\' + '\n'
refinement += r'''\bottomrule\end{tabular}
\par\smallskip\footnotesize 每行三个种子的均值，收尾前后$C_{\max}$相同。$C_{\mathrm{end}}$覆盖全部动作和装载锁复位；各等待与节拍分量由新事件分别计算。
\end{table}

表~\ref{tab:completion-cn}中的4片和8片单源实例分别将全部动作完工时间由100018~s降至2457~s和4899~s，同时保持1491~s和3933~s的产品完工时间；路线等待仍分别为840~s和1680~s。资格单源实例的全部动作完工时间由14985~s降至5725~s。4片、$H=10$双源实例的种子2还将产品完工时间由848.61~s缩短至809~s，三个种子的最终均值为841~s。收尾选择使辅助片归还、末端清洁和压力复位形成明确的完成边界，与产品产出指标共同描述完整执行排程。

'''

initialization = r'\subsection{初始化与固定结构对照}' + part(
    r'\subsection{初始化与可选搜索组件}', '在4片、$H=10$双源实例中，两个固定结构对照')
initialization = initialization.replace('平均完工时间。SPBS组', '主求解结束时的平均完工时间。SPBS组')
initialization = initialization.replace(r'\caption{初始化对照的平均产品完工时间（s）}', r'\caption{不同初始化下主求解结束时的平均产品完工时间（s）}')
initialization = initialization.replace('串行初始解 & SPBS &', '串行起点组 & SPBS起点组 &')
initialization += r'''定向对照进一步选取4片和8片、$H=3,10$的四种双源混合实例，每种运行三个种子。三种方法从相同SPBS完整赋值出发：直接联合求解300~s；固定配对、分腔和周期占位求解300~s；先固定结构求解60~s，再把其完整赋值传递给联合模型求解240~s。共享初始准备单列，预求解包含在第三种方法的总求解预算中。表~\ref{tab:strong-baseline-cn}仅比较第一阶段产品完工时间。

\begin{table}[!htbp]
\centering\footnotesize
\setlength{\tabcolsep}{3pt}
\caption{相同起点与设定总预算下的完工时间（s）}
\label{tab:strong-baseline-cn}
\begin{tabular}{lrrr}\toprule
$N/H$ & 直接联合 & 固定结构 & 固定后联合\\\midrule
'''
for n,h in [(4,3),(4,10),(8,3),(8,10)]:
    key=f'n{n}_H{h}_mixed_dual'
    a,b,c = [group('baseline',key,arm) for arm in ('joint','fixed','fixed_then_joint')]
    av,bv,cv=[g['metrics']['product_cmax'] for g in (a,b,c)]
    initialization += f"{n}/{h} & {av:.2f} & {bv:.2f} & {cv:.2f}" + r'\\'+'\n'
initialization += r'''\bottomrule\end{tabular}
\par\smallskip\footnotesize 每行三个种子的均值；直接联合的完工时间与共同起点相同。4片固定结构的六次运行达到子问题最优，两个阈值的平均用时为56.67和8.33~s，其余30次运行在时间限额处停止。固定后联合的实际总求解均值依次为273.00、294.00、300.33和300.00~s。
\end{table}

固定结构优化在四种实例中均得到更小的平均产品完工时间，降幅为5.20\%--36.76\%。4片两种阈值下均得到542~s；8片、$H=3$与$H=10$的三个种子分别得到1993/2023/1874~s和1203/1268/1348~s。先固定结构再联合搜索的结果也优于直接联合搜索，其改善均由60~s固定结构预求解取得，后续联合搜索保持该可行值。将300~s完整用于固定结构优化在本组实例中得到更好的均值，体现了集中优化给定结构内时序与资源次序的作用；固定结构解同时可作为完整模型的可行起点。

可选学习选割保留八种混合实例、三个种子的72次对照。默认SCIP、HEM和角色感知策略各获得24个可行排程，平均产品完工时间分别为1925.32、1925.63和1925.32~s；角色感知策略与默认SCIP的24组配对值相同。两种学习策略各有17次调用选割，采用最多一轮根节点选割及关闭非根节点选割的共同配置，平均回调耗时为0.22~s和0.32~s。该组件作为求解接口选项记录。

'''

scale = r'\subsection{清洁阈值与规模变化}' + part(r'\subsection{清洁阈值与规模变化}', r'\section{结论}')
scale = scale.replace('三种配方分别使用256、512和256个Pjob库存选择变量，',
    r'三种配方分别使用256、512和256个Pjob库存选择变量；在同样的前32个产品对候选中，逐片选择需2048列，库存选择列数分别减少87.5\%、75.0\%和87.5\%。')
scale = scale.replace('在保留各片产品完整动作与资源约束的同时，以批次库存表示产品归属选择。',
    '模型以批次库存表示产品归属，同时保留各片产品的完整动作与资源约束。')

conclusion = r'''\FloatBarrier
\section{结论}

本文针对满片加工的双源混流旋转腔组合设备，建立两阶段批次任务调度模型。产品按工艺模式与腔室资格分组，编码为Pjob内第$k$片晶圆，全Pjob严格出片约束联结跨LP库存。模型联合描述配对、分腔、周期占位、辅助晶圆复用、清洁和资源时序，并在两阶段优化及输出收尾后恢复具体晶圆动作排程。

原实验获得441份通过原模型约束检查和独立物理重放的可行结果，三类定向补充又形成114份可行结果记录。八种混合实例的24组阶段内精修均保留产品完工时间上界，总路线等待下降15.63\%--63.03\%，最大路线等待项降至65~s。双源8片链式实例的节拍偏差由136~s降至126~s，16片长链由792~s降至784~s；24片含两次清洁的混合实例将路线等待由3745~s降至1440~s，同时保持产品完工时间和节拍偏差。这些结果表明，等待与节拍项能够针对给定生产链形成可量化的时序权衡。

四种小规模实例的固定结构优化较直接联合搜索获得5.20\%--36.76\%的平均完工时间降幅，所得完整赋值可直接用于联合模型热启动。42份两阶段排程经收尾规范化后全部保留产品完工时间及二阶段目标上界，其中16份缩短了全部动作完工时间。批次库存选择、结构化时序优化和收尾输出将产品供回、辅助片周转与设备资源安排连接起来，为满片旋转腔设备提供了可验证的批次调度方法。

'''

new_section = settings + encoding + refinement + initialization + scale + conclusion
(HERE / 'experiment_section.tex').write_text(new_section, 'utf-8')
begin = src.index(r'\section{计算实验与结果分析}')
end = src.index(r'\section*{CRediT作者贡献声明}')
src = src[:begin] + new_section + src[end:]
src = src.replace('两阶段求解结束并选定最终解', '两阶段求解及输出收尾结束并选定最终解')
src = src.replace('并结合结构化初始解方案与学习增强割选择进行限时求解', '并结合结构化初始解方案与可选学习割选择进行限时求解')
if '--check' in sys.argv:
    assert src == (PAPER / 'JMS_Review_CN.tex').read_text('utf-8'), 'Generated content differs from the reviewed manuscript'
    print('Generated results match the reviewed manuscript; manuscript unchanged.')
else:
    (PAPER / 'JMS_Review_CN.tex').write_text(src, 'utf-8')
    print('Updated experiment section, conclusion and end-of-algorithm wording from verified records.')

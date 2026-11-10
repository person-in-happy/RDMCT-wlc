"""Apply verified strengthening results to the current Chinese source snapshot."""
from pathlib import Path
import json
from statistics import mean

HERE = Path(__file__).resolve().parent
PAPER = HERE.parents[1]


def main():
    original = (HERE / 'original/JMS_Review_CN.tex').read_text('utf-8')
    data = json.loads((HERE / 'verified_strengthening.json').read_text('utf-8'))
    assert data['completed'] == data['feasible'] == 48
    assert data['input_assignment_checks'] == 9 and data['wafer_assignment_checks'] == 18
    groups = {(g['case'], g['arm'], g['weight']): g for g in data['groups']}
    cases = [f'n{n}_H5_{mode}_dual' for n in (8, 16) for mode in ('4x1', '2x2', 'mixed')]
    changes = [100 * (1 - groups[c, 'pjob', None]['means']['build_and_start_check_seconds'] /
                          groups[c, 'wafer', None]['means']['build_and_start_check_seconds']) for c in cases]
    assert round(min(changes), 2) == 9.26 and round(max(changes), 2) == 14.98
    for weight in (0, 5, 25, 100):
        g = groups['n24_H5_2x2_dual', 'substituted', weight]
        assert g['statuses'] == {'optimal': 3}
        assert abs(g['actual']['route_wait_sum'] - 1440) < 2e-4
        assert abs(g['actual']['rhythm_deviation'] - 696) < 2e-4
    text = original
    def replace(old, new):
        nonlocal text
        assert text.count(old) == 1, old[:100]
        text = text.replace(old, new)
    def paragraph(prefix, new):
        matches = [p for p in text.split('\n\n') if p.startswith(prefix)]
        if not matches:
            matches = [p for p in text.splitlines() if p.startswith(prefix)]
        assert len(matches) == 1, prefix
        old = matches[0]
        replace(old, new)

    paragraph('在4--32片参数化实例中，', r'''在4--32片参数化实例中，24组基础时序精修均保留产品完工时间上界，总路线等待下降15.63\%--63.03\%。24片含两次清洁的纯链式实例将路线等待由3109~s压缩至1440~s，保持4785~s产品完工时间和696~s节拍偏差；16片长链的节拍偏差由792~s降至784~s。相同严格出片规则下，六种实例的逐片与库存表示获得一致的产品完工时间，库存表示的建模及起点检查耗时降低9.26\%--14.98\%。42份输出收尾中，16份缩短全部动作完工时间，均保持产品完工时间和二阶段加权目标上界。结果表明，批次编码、固定结构时序精修与输出收尾能够连接产品分组、物理资源约束和具体晶圆排程，协调产品产出、工序衔接与周期节拍。''')
    replace(r'''0\le s_o\le Mb_o,\qquad
0\le e_o\le Mb_o,\qquad''', r'''0\le s_o\le\overline T b_o,\qquad
0\le e_o\le\overline T b_o,\qquad''')
    replace('这里比较的两种表示均执行相同的批次出片规则。',
            '这里比较的两种表示均执行相同的批次出片规则；第~\\ref{sec:representation-comparison-cn}节在相同物理约束和初始排程下检验成员表示的计算开销。')
    prefix = '第一阶段按式~\\eqref{eq:primary-objective-cn}搜索批次任务可行域。'
    old = next(p for p in text.split('\n\n') if p.startswith(prefix))
    replace(old, old + '\n\n' + r'''\paragraph{固定结构的代入精修。}
第二阶段已给定的$\widehat\xi_d$可在生成约束时直接代入，保留原子同步选择和全部连续时刻。依据原变量界删除恒真约束，保留其余线性关系和产品完工时间上界，得到与式~\eqref{eq:secondary-domain-cn}相同可行域的精修子问题。求解后将自由变量值与给定离散值合并，恢复完整赋值，在原模型中检查全部约束，再执行后续输出步骤。该代入减少固定结构精修的存储与预处理开销。''')
    replace(r'''\textbf{5. 第二阶段。}固定主要结构和完工时间上界，优化等待及节拍；保留通过原始约束检查的最终批次任务解。\\''',
            r'''\textbf{5. 第二阶段。}固定主要结构和完工时间上界，可直接代入固定离散量后优化等待及节拍；恢复完整赋值并检查原模型约束。\\''')
    paragraph('基础单阶段预算为300~s，', r'''基础单阶段预算为300~s，两阶段配置采用270~s主求解和30~s精修，SPBS预算为20~s。定向固定结构对照采用300~s总求解预算；先固定结构再联合搜索的配置分配60~s与240~s。长链节拍实验复用同一第一阶段完整赋值，精修预算60~s；输出收尾预算60~s。定向实验均串行执行，固定结构与收尾组的SCIP/进程内存限额为6000/7000~MiB，长链节拍组为10000/14000~MiB。固定离散量代入的12组精修沿用原长链组的输入、权重和资源预算；逐片与库存成员表示的36次对照均采用300~s主阶段预算及10000/14000~MiB内存限额，两种表示按种子交替执行顺序。''')
    paragraph('建模、初始赋值准备和求解时间分别记录。', r'''建模、初始赋值准备和求解时间分别记录。成员表示对照另外汇总建模与起点检查的合计耗时，包含模型生成、公共赋值映射与可行性检查；历史SPBS起点构造和求解后完整模型复核分别记录。SCIP在算法检查点响应限额，本文同时保留设定预算与实际停止时间。基础初始化对照的主求解实际停止时长为300--389~s，成员表示对照为300--392~s。固定结构预求解的时间计入其方法预算。''')
    paragraph('表~\\ref{tab:coverage-cn}区分主实验与定向补充记录。', r'''表~\ref{tab:coverage-cn}区分主实验与定向补充记录。原453次完成运行中441次获得可行排程，12次冷启动在时间限额内未获得可行解；定向补充的162项全部保存可行排程，包括42项对已有输出的收尾处理。每份可行结果均检查原模型约束，独立重放编码覆盖、全Pjob严格出片、资格、满片、连续处理、机械手容量、驻留、回片及辅助片复用，并从实际事件重算指标。新增48份赋值及其9份不同输入赋值均重新构建完整模型验解，18份逐片表示赋值另外检查身份选择与库存投影一致性。运行记录包含同一实例的种子、方法及后处理结果，独立实例按输入配置区分。''')
    replace(r'''输出收尾处理 & 42 & 42 & 0\\\midrule
结果记录合计 & 567 & 555 & 3\\\bottomrule''', r'''输出收尾处理 & 42 & 42 & 0\\
固定离散量代入精修 & 12 & 12 & 0\\
逐片与库存成员表示 & 36 & 36 & 0\\\midrule
结果记录合计 & 615 & 603 & 3\\\bottomrule''')
    replace(r'''\par\smallskip\footnotesize 收尾处理复用已有两阶段排程；强起点的12次内部预求解计入对应方法，未另计为独立结果。''',
            r'''\par\smallskip\footnotesize 收尾处理复用已有两阶段排程；强起点的12次内部预求解计入对应方法。长链权重组包含原12次内存停止记录，代入精修采用相同输入并单列；表中计数为运行记录。''')
    table_rows = []
    for case in cases:
        n, _, mode, _ = case.split('_')
        recipe = {'4x1': r'$4\times1$', '2x2': r'$2\times2$', 'mixed': '混合'}[mode]
        for arm in ('wafer', 'pjob'):
            g = groups[case, arm, None]
            d, m = g['dimensions'], g['means']
            label = n[1:] + '/' + recipe if arm == 'wafer' else ''
            name = '逐片' if arm == 'wafer' else '库存'
            table_rows.append(f"{label} & {name} & {g['selectors']} & {d['variables']} & {d['constraints']} & {d['linear_nonzeros']} & {m['build_and_start_check_seconds']:.2f} & {m['build_solve_rss_mb']:.0f} & {g['actual']['product_cmax']:.0f}" + r'\\')
    representation = r'''\subsection{相同出片规则下的成员表示对照}
\label{sec:representation-comparison-cn}

采用8、16片与三种配方的六种双源实例，清洁阈值均为$H=5$，比较逐片成员选择与Pjob库存选择。逐片表示采用0--1变量$y_{wpr}$选择实际产品晶圆$w$及其成员位$(p,r)$，并用非负实数取片时刻绑定该晶圆的取片事件、落实全Pjob严格顺序；库存表示使用$x_{j\ell pr}$。其中$w$为输入实际晶圆编号，$j,\ell,p,r$沿用模型索引。属于同一Pjob及LP的逐片选择量求和即为相应库存选择量，两种表示共用成员位动作路线、物理资源约束、资格和候选容量。

每个实例采用三个种子，形成18组成对比较、36次运行。每对使用同一份SPBS完整物理排程，逐片身份根据该排程的严格取片顺序映射，求解参数与设定预算相同。表~\ref{tab:representation-cn}列出预处理前的完整模型规模与三个种子的平均开销，峰值内存取建模和求解阶段的进程RSS，完整模型回填复核的耗时与内存另计。

\begin{table*}[t]
\centering\footnotesize
\setlength{\tabcolsep}{3pt}
\caption{相同FIFO、候选容量与初始排程下的成员表示比较}
\label{tab:representation-cn}
\begin{tabular}{llrrrrrrr}\toprule
$N$/配方 & 表示 & 选择列 & 总变量 & 约束 & 非零元 & 准备/s & RSS/MiB & $C_{\max}$/s\\\midrule
''' + '\n'.join(table_rows) + r'''
\bottomrule\end{tabular}
\par\smallskip\footnotesize 准备耗时包含建模、起点映射与检查。RSS按2~s间隔采样，并补充建模结束和求解结束读数。36次运行均按时间限额停止，产品完工时间与共同起点相同；设定求解预算为300~s，实际停止时长为300--392~s。
\end{table*}

纯配方8片和16片的选择列分别由128降至64、由512降至128；16片混合配方由512降至256。8片混合配方满足$G=N=8$，两种表示均为128列，其差别来自逐片取片时刻及联结约束。六种实例的总变量数减少0.01\%--0.22\%，约束矩阵非零元减少0.05\%--12.81\%，建模及起点检查耗时减少9.26\%--14.98\%。这些结果量化了库存表示在保持产品动作和资源约束的同时，对身份选择与时刻联结的压缩作用。

18组成对比较均得到一致的产品完工时间，六种实例分别为1178、1213、1720、2400、2943和2525~s。较小的成员选择块与更简洁的联结表达式使相同物理排程的模型准备更快；求解阶段的资源占用按实例列于表中。完整模型验解与逐片身份投影进一步验证了两种表示在这些排程上的对应关系。

'''
    replace(r'\subsection{时序精修与节拍目标消融}', representation + r'\subsection{时序精修与节拍目标消融}')
    paragraph('进一步从阈值实验中选取16片长链、', r'''进一步从阈值实验中选取16片长链、24片含清洁链和24片混合配方，均采用双源配置，分别含6、8、2个节拍评价中心；后两个场景各执行2次清洁。同一实例、同一种子下，四个权重使用同一份第一阶段变量赋值，并固定相同的结构与资源次序。取$\lambda_3=0,5,25,100$，每组精修60~s，形成36组权重配置；其中$\lambda_3=0$为去掉节拍项的消融。24片纯链式的12组采用固定离散量代入实现，各组结果均恢复到完整原模型验解。''')
    replace(r''' & 0、5、25、100 & 4785 & 3109 & 437 & 696 & 内存限额\\''',
            r''' & 0、5、25、100 & 4785 & 1440 & 65 & 696 & 子问题最优\\''')
    replace(r'''\par\smallskip\footnotesize 每个权重运行三个种子，表列均值，各种子在显示精度内一致；合并列示的权重分别运行并得到相同指标。子问题最优指固定主要离散结构的时序精修最优。24片纯$2\times2$的12次运行均在SCIP内存限额处停止并保留初始可行解。''',
            r'''\par\smallskip\footnotesize 每个权重运行三个种子，表列均值，各种子在显示精度内一致；合并列示的权重分别运行并得到相同指标。36组配置均达到固定主要离散结构的时序精修子问题最优，24片纯链式采用代入后的精修结果。''')
    paragraph('表~\\ref{tab:rhythm-ablation-cn}中，16片长链', r'''表~\ref{tab:rhythm-ablation-cn}中，16片长链仅等待目标将路线等待由1766~s降至1000~s；设置正节拍权重后，路线等待为1016~s，节拍偏差由792~s降至784~s，下降1.01\%，产品完工时间保持2537~s。权重5、25、100均实现这一权衡。24片混合配方中，路线等待由3745~s降至1440~s，下降61.55\%；24片纯链式中，由3109~s降至1440~s，下降53.68\%。两者最大路线等待项均由437~s降至65~s，分别保持5199~s、4785~s产品完工时间，以及20~s、696~s节拍偏差和两次清洁。两个含清洁场景的四种权重均达到相同指标，表明给定结构内的等待压缩能够保持既有生产周期衔接。''')
    insert = r'''固定离散量代入后，24片纯链式的精修子问题由完整候选模型的1080365个变量收缩为3645个变量，其中432个为同步选择、3213个为连续变量，并保留34538条约束。12组均达到精修子问题最优，求解器记录的求解时间不超过1~s；包含建模、完整模型复核和保存的单项耗时为54.14--59.24~s。建模与求解阶段的最大记录RSS约504~MiB，包含完整模型复核的进程峰值约4617~MiB，反映了代入精修与完整赋值验解各自的计算成本。'''
    replace(r'\subsection{执行输出与完整收尾}', insert + '\n\n' + r'\subsection{执行输出与完整收尾}')
    paragraph('原实验获得441份通过原模型约束检查', r'''原实验获得441份通过原模型约束检查和独立物理重放的可行结果，定向补充形成162份可行结果记录。八种混合实例的24组阶段内精修均保留产品完工时间上界，总路线等待下降15.63\%--63.03\%，最大路线等待项降至65~s。双源8片链式实例的节拍偏差由136~s降至126~s，16片长链由792~s降至784~s；24片含两次清洁的纯链式和混合实例分别将路线等待由3109~s和3745~s降至1440~s，保持各自产品完工时间与节拍偏差。固定结构内的等待与节拍评价由此形成了可量化的工序衔接改进与时序权衡。''')
    old = next(p for p in text.split('\n\n') if p.startswith('四种小规模实例的固定结构优化较直接联合搜索获得'))
    replace(old, r'''相同严格出片规则、物理约束与初始排程下的六种成员表示对照得到相同的产品完工时间，库存表示的建模及起点检查耗时减少9.26\%--14.98\%，并减少身份选择列与条件时刻联结。固定离散量的等价代入使24片含清洁纯链式的12组精修均获得子问题最优解，完整赋值回填保持原物理约束。

''' + old)
    # Preserve the author's introduction, declarations and reference text.
    assert text.split(r'\section{引言}', 1)[1].split(r'\section{双源混流旋转腔组合设备调度模型}', 1)[0] == original.split(r'\section{引言}', 1)[1].split(r'\section{双源混流旋转腔组合设备调度模型}', 1)[0]
    assert text.split(r'\section*{CRediT', 1)[1] == original.split(r'\section*{CRediT', 1)[1]
    target = PAPER / 'JMS_Review_CN.tex'
    assert target.read_text('utf-8') in (original, text), 'Manuscript changed since snapshot; merge explicitly'
    (HERE / 'applied_manuscript.tex').write_text(text, 'utf-8')
    target.write_text(text, 'utf-8')
    print('Updated Chinese manuscript from 48 verified results; introduction and bibliography preserved.')


if __name__ == '__main__':
    main()

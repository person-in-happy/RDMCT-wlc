from pathlib import Path
from statistics import mean
import difflib
import json
import re

HERE=Path(__file__).resolve().parent
PAPER=HERE.parents[1]
ROOT=PAPER.parent
source=PAPER/'JMS_Review_CN.tex'
old=(HERE/'original/JMS_Review_CN.tex').read_text('utf-8')
assert source.read_text('utf-8')==old, 'Manuscript changed since review snapshot'
audit=json.loads((HERE/'newrule_validation.json').read_text('utf-8'))
derived=json.loads((HERE/'derived_checks.json').read_text('utf-8'))
assert not audit['failures'] and audit['assignments_checked']==180
new=old


def replace(a,b):
    global new
    assert new.count(a)==1,a[:100]
    new=new.replace(a,b)


replace('上述等价关系要求两种表示均采用非递减出片规则，并允许相同的同步取片动作。第~\\ref{sec:representation-comparison-cn}节已有计算对照采用更严格的不可同步取片规则，其结果限于该受限可行域。',
        '上述等价关系要求两种表示采用相同的非递减出片规则与同步取片条件。第~\\ref{sec:representation-comparison-cn}节在统一物理起点和候选容量下对两种表示进行计算对照，并核查同批同步取片排程的身份映射。')
replace(r'节拍权重实验另取$\lambda_3\in\{0,5,25,100\}$，固定前两项权重。',
        r'节拍项对照取$\lambda_3\in\{0,25\}$，固定前两项权重。')
replace('设计结构化可行初始化、时序精修与输出收尾流程，通过固定结构对照及节拍项消融，分析可行起点、资源次序和目标权重对排程的作用。',
        '设计结构化可行初始化、时序精修与输出收尾流程，通过成员表示对照、同步取片见证及节拍项消融，分析批次编码和目标设置对可行排程的作用。')

begin=old.index(r'\section{计算实验与结果分析}')
end=old.index(r'\FloatBarrier'+'\n'+r'\section{结论}',begin)
enum=old[old.index(r'进一步构造8、16、32片',begin):old.index(r'\subsection{相同出片规则',begin)]
enum=enum.replace('库存、资格、严格出片和编码映射','库存、资格、非递减出片和编码映射')
enum=enum.replace('各配置代表性完整排程进行物理重放','36份代表性完整排程按本文非递减出片规则重新进行物理重放')
ablation=old[old.index(r'\subsection{时序精修与节拍目标消融}',begin):old.index(r'进一步从阈值实验中选取16片',begin)]
ablation=ablation.replace('基础时序实验包含','基础时序核验包含').replace('共24组第一阶段--第二阶段排程','共24组输入--精修排程')
ablation=ablation.replace('按同一次运行配对','按同一输入与对应精修结果配对').replace('各运行均满足','各组均满足').replace('单次总等待降幅','各组总等待降幅')
ablation=ablation.replace('4片、$H=10$双源实例的种子2在第二阶段将产品完工时间','4片、$H=10$双源实例的种子2对应排程在第二阶段将产品完工时间')
ablation=ablation.replace('其余基础运行的产品完工时间','其余基础排程的产品完工时间')
ablation=ablation.replace('8片纯$2\\times2$的原目标消融','8片纯$2\\times2$的节拍项对照')
ablation=ablation.replace('线性与原二次目标得到相同的这些指标。','线性与二次参考目标得到相同的这些指标。输入与输出的结构及赋值均通过本文模型复核，比较指标由最终物理事件计算。')
cleanup=old[old.index(r'\begin{table}[!htbp]',old.index(r'\subsection{执行输出与完整收尾}',begin)):old.index(r'\subsection{初始化与固定结构对照}',begin)] if r'\subsection{初始化与固定结构对照}' in old else ''
if not cleanup:
    a=old.index(r'\subsection{执行输出与完整收尾}',begin)
    b=old.index(r'\subsection{',a+15)
    cleanup=old[old.index(r'\begin{table}[!htbp]',a):b]

intro=r'''\section{计算实验与结果分析}
\label{sec:experiments-cn}

实验验证批次编码、同步取片、双腔生产和两阶段时序指标。成员表示比较采用完整候选模型求解；时序与收尾组对给定输入和输出逐项验解，评价具体排程的等待、节拍及完成边界。

\subsection{实例、计算设置与验证方法}

设备时长与资源容量采用表~\ref{tab:symbol-cn-a}的设置，辅助晶圆共8片。完整模型对照包括1、2、4片产品的八种双源配置，覆盖两种纯配方、混合配方、清洁阈值$H=2,3$及同LP和跨LP分布。同模式且腔室资格相同的产品组成Pjob；同一Pjob按输入编号非递减出片，同对同LP产品允许同步取片。资格见证另设置仅CH2、仅CH3和两腔均可三类Pjob。

计算平台为Windows~11、20逻辑处理器和约32~GB内存，采用Python~3.12.12与PySCIPOpt~6.1.0。完整模型比较使用标准SCIP割设置、种子1及单线程，每次主求解预算600~s，SCIP与进程内存限额分别为3000和4500~MiB。每个配置先补全一份公共物理起点，再分别交给逐片和库存表示；正式求解不固定配对、分腔或周期占位，公共起点补全不采用SPBS改善。

八种配置形成16次主求解，全部获得可行排程，其中5次证明最优，其余11次在时间限额处保留可行解；8项公共起点补全单独记录。给定排程的时序核验包含24组基础输入--精修对、6组资格输入--精修对、12组节拍项对照和42组收尾输入--输出对。阶段对照采用种子1、2、3对应的排程，先在同一实例内取均值，再计算指标变化。所有保留的完整赋值均回填本文模型检查，另独立重放工艺、非递减出片、满片、物理手、模块驻留、回片和辅助片复用；指标由事件时刻重算。时序核验组使用保存的配对、周期及资源次序，报告给定排程的阶段内变化。

\subsection{同步取片、跨腔生产与资格验证}

同LP双片$4\times1$实例中，两片产品均属于Pjob1。库存表示得到$C_{\max}=324$~s的最优排程：两片在0~s同时从LP1取出，在CH2的同一PW对内于104--284~s完成生产，并于324~s返回LP1。末端解码将两个成员分别对应到$\mathrm{Pjob}_1[1]$与$\mathrm{Pjob}_1[2]$，恢复实际晶圆1和2。两个取片时刻相等而批次内编号确定，验证了非递减出片与成对搬运的协调。

跨LP双片$4\times1$实例的逐片表示得到324~s的最优排程，完整赋值回填批次模型后仍可行。CH3的生产区间为87--267~s，CH2为104--284~s，两腔同时生产163~s；晶圆1、26分别在0、14~s取出，于310、324~s返回。图~\ref{fig:nondecreasing-witness-cn}展示同步取片与跨腔生产的代表性事件。各生产周期均由产品与辅助片补齐四工位，共享VTR、物理手和辅助片借用区间通过完整排程检查。

\begin{figure*}[t]
\centering
\includegraphics[width=0.92\textwidth]{fig_nondecreasing_witness_cn}
\caption{非递减出片下的代表性排程。（a）同Pjob、同LP的两片产品同时取片；细线表示取片至回片的流经区间，色块表示工艺处理。（b）跨LP产品的两腔生产区间，重叠部分为163~s。}
\label{fig:nondecreasing-witness-cn}
\end{figure*}

资格验证中，每种配方分别设置仅CH2、仅CH3和两腔均可三个Pjob，共六个任务。8片产品分布于LP1与LP2，同一Pjob可跨LP，实际晶圆编号存在间隔。单源与双源各三份给定排程均通过本文模型验解，产品完工时间分别为4707~s和2264~s。另一个仅含两片$4\times1$产品的资格见证将晶圆1限定于CH2、晶圆26限定于CH3，两腔生产区间分别为87--267~s和104--284~s，产品完工时间为324~s。该排程同时验证了专属资格与共享资源下的并行生产。

\subsection{非递减出片下的成员表示对照}
\label{sec:representation-comparison-cn}

逐片表示采用0--1变量$y_{wpr}$指定实际产品晶圆$w$及成员位$(p,r)$，并以非负实数取片时刻联结该晶圆的事件与批次内顺序；库存表示采用$x_{j\ell pr}$。其中$w$为实际晶圆编号，其余下标沿用模型定义。两种表示采用相同的非递减规则、同步取片条件、工艺资格、候选容量及物理资源约束，逐片选择量按Pjob和LP求和后得到库存选择量。

表~\ref{tab:representation-cn}给出八种配置的主问题下界与可行上界。单片$4\times1$与同LP双片$4\times1$的两种表示分别得到296~s、324~s的相同最优值；跨LP双片$4\times1$的逐片表示也证明324~s最优。每份逐片赋值均检查显式身份选择与确定解码的对应关系，并投影回批次模型验解。两个已证等值配置与全部可行赋值的交叉检查支持了编码映射的一致性。

'''
exact=[r for r in audit['rows'] if r['category']=='new_exact' and r['cell']['kind']=='exact']
cases=list(dict.fromkeys(r['cell']['case'] for r in exact))
table=r'''\begin{table*}[t]
\centering\small
\caption{相同非递减出片规则下的完整模型对照（时间单位：s）}
\label{tab:representation-cn}
\begin{tabular}{llrrlrrl}\toprule
 & & \multicolumn{3}{c}{Pjob库存表示} & \multicolumn{3}{c}{逐片表示}\\
 $N$/配方/$H$ & LP分布 & 下界 & 上界 & 状态 & 下界 & 上界 & 状态\\\midrule
'''
for case in cases:
    n,h,recipe=case.split('_')[:3]
    label=f'{n[1:]}/'+({'4x1':r'$4\times1$','2x2':r'$2\times2$','mixed':'混合'}[recipe])+f'/{h[1:]}'
    distribution='同LP' if 'same_lp' in case or n=='n1' else '跨LP'
    vals=[]
    for arm in ('pjob','wafer'):
        e=next(r['evidence'] for r in exact if r['cell']['case']==case and r['cell']['arm']==arm)
        vals.extend([f"{e['lower_bound']:.2f}",f"{e['upper_bound']:.2f}",'最优' if e['state']=='optimal' else '限时可行'])
    table+=' & '.join([label,distribution]+vals)+r'\\'+'\n'
table+=r'''\bottomrule\end{tabular}
\par\smallskip\footnotesize 每个配置使用同一公共起点，两种表示的主求解预算均为600~s。下界和上界保留两位小数；“最优”表示该次完整主求解上下界闭合。公共起点补全与主求解分别计量。
\end{table*}

同LP双片实例仅有一个非空任务--LP组合，即$G=1,N=2$，成员选择列由逐片表示的8列降至库存表示的4列。纯$4\times1$的完整模型变量数由3225降至3219，约束由9854降至9835，非零元由52908降至52450；纯$2\times2$的对应数值为8329降至8323、26350降至26331、144838降至144380。压缩集中于身份选择及取片时刻联结，产品动作与设备资源仍完整保留。

\subsection{批次编码与可行排程数量}
\label{sec:model4-enumeration-cn}

'''
residency=r'''\subsection{驻留上限与执行输出}

表~\ref{tab:residency-witness-cn}列出5份通过本文完整模型验解的4片混合排程，清洁阈值均为$H=10$。各来源采用给定配对、分腔及周期结构，模块驻留与机械手承片上限同时设为表中的$R$；$R$是本表对两类共同上限的简写，单位s。双源三份排程在10000、500和250~s上限下均以542~s完成产品回片，产品流经时间总和分别为1624、1466和1353~s。250~s条件下的完整可行赋值表明，双源供回衔接能够满足该组较紧的驻留要求。

\begin{table}[!htbp]
\centering\footnotesize
\setlength{\tabcolsep}{4pt}
\caption{不同驻留上限下的可行排程（时间单位：s）}
\label{tab:residency-witness-cn}
\begin{tabular}{lrrr}\toprule
来源 & $R$ & $C_{\max}$ & 产品流经时间总和\\\midrule
单源 & 10000 & 1382 & 3044\\
单源 & 500 & 1471 & 2621\\
双源 & 10000 & 542 & 1624\\
双源 & 500 & 542 & 1466\\
双源 & 250 & 542 & 1353\\
\bottomrule\end{tabular}
\par\smallskip\footnotesize 每行对应一份已验证排程；两类上限同时约束产品和辅助晶圆的相应区段。
\end{table}

输出收尾核验采用24份基础精修、6份资格精修及12份链式精修排程，共42组输入--输出对。全部输入和输出均通过本文模型检查，输出保留产品完工时间及完整二阶段目标上界；16份排程的$C_{\mathrm{end}}$缩短，其余26份保持。表~\ref{tab:completion-cn}给出产品回片与设备全部动作完成的不同边界。

'''
experiments=intro+table+enum+ablation+residency+cleanup
new=new[:new.index(r'\section{计算实验与结果分析}')]+experiments+new[new.index(r'\FloatBarrier'+'\n'+r'\section{结论}',new.index(r'\section{计算实验与结果分析}')):]

abstract_start=new.index('\n',new.index(r'\begin{abstract}'))+1
abstract_second=new.index('\n',abstract_start)+1
abstract_end=new.index(r'\end{abstract}',abstract_second)
new=new[:abstract_second]+r'''在八种小规模配置的16次完整主求解中，全部获得可行排程，单片与同LP双片$4\times1$的两种成员表示分别得到296~s和324~s的相同最优值；同批同步取片与双腔重叠163~s的排程验证了编码和资源衔接。经完整模型复核，24组基础输入--精修排程均保持产品完工时间上界，总路线等待下降15.63\%--63.03\%；8片链式双源排程的节拍偏差由136~s降至126~s。42组收尾输入--输出对均保留产品完工时间及二阶段目标上界，其中16组缩短全部动作完工时间。结果表明，批次编码、时序精修与输出收尾能够连接产品分组、物理资源约束和具体晶圆排程，协调产品产出、工序衔接与周期节拍。
'''+new[abstract_end:]
a=new.index(r'\section{结论}')
b=new.index(r'\section*{CRediT',a)
new=new[:a]+r'''\section{结论}

本文针对满片加工的双源混流旋转腔组合设备，建立两阶段批次任务调度模型。产品按工艺模式与腔室资格分组，编码为Pjob内第$k$片晶圆，全Pjob非递减出片约束联结跨LP库存，并允许满足物理条件的同对产品同步取片。模型联合描述配对、分腔、周期占位、辅助晶圆复用、清洁和资源时序，并在两阶段优化及输出收尾后恢复具体晶圆动作排程。

八种配置的16次完整主求解均获得可行解。单片与同LP双片$4\times1$实例的两种成员表示分别证明296~s和324~s最优，库存选择与逐片身份投影保持相同的物理排程含义。同LP双片实例的成员选择列由8降至4，并实现同批两片产品在0~s同步取片。跨LP双片实例的两腔生产区间重叠163~s，产品完工时间为324~s，验证了批次顺序与双腔资源协调。

通过完整模型复核的24组基础输入--精修排程均保持产品完工时间上界，总路线等待下降15.63\%--63.03\%，最大路线等待项降至65~s。8片链式双源实例加入节拍项后，以20~s路线等待差异换得节拍偏差由136~s降至126~s；8片、$H=3$混合实例的单源和双源产品流经时间总和分别减少2.27\%和22.03\%。路线等待、腔内驻留与流经时间的共同评价给出了可量化的工序衔接变化。

4片双源混合排程在250~s模块与机械手驻留上限下以542~s完成产品回片。42组收尾输入--输出对均保持产品完工时间与二阶段目标上界，其中16组缩短全部动作完工时间。批次库存选择、结构化时序精修和收尾输出将产品供回、辅助片周转与设备资源安排连接起来，为满片旋转腔设备提供可验证的批次调度方法。

'''+new[b:]
assert not any(t in new for t in ('匿名','模型4','模型2','9.26','14.98','36.76','12.81'))
assert new.split(r'\begin{abstract}')[1].strip().splitlines()[0]==old.split(r'\begin{abstract}')[1].strip().splitlines()[0]
assert re.findall(r'\\begin\{equation\}(.*?)\\end\{equation\}',new,re.S)==re.findall(r'\\begin\{equation\}(.*?)\\end\{equation\}',old,re.S)
source.write_text(new,'utf-8')
(HERE/'manuscript.patch').write_text(''.join(difflib.unified_diff(old.splitlines(True),new.splitlines(True),fromfile='original/JMS_Review_CN.tex',tofile='JMS-version/JMS_Review_CN.tex')),'utf-8')
print('Updated manuscript with current-rule evidence and verified physical schedules.')

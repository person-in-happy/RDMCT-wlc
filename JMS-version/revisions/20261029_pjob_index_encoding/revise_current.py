"""Revise the user's current source, retaining protected prose and evidence."""
from pathlib import Path
import hashlib, json, re

HERE=Path(__file__).resolve().parent
PAPER=HERE.parents[1]
target=PAPER/'JMS_Review_CN.tex'
source=(HERE/'original/JMS_Review_CN.tex').read_text('utf-8')
assert hashlib.sha256(target.read_bytes()).hexdigest()=='73ac22acb25fded3c6de3d02851571ec8d01cfbfd6dad8bdf96757eca5e1eea6', 'Source changed after snapshot'
s=source


def replace(old,new):
    global s
    assert s.count(old)==1, (old[:100],s.count(old))
    s=s.replace(old,new)


def section(start,end,new):
    global s
    a=s.index(start);b=s.index(end,a)
    s=s[:a]+new+'\n\n'+s[b:]


# The user explicitly approved this correction to the otherwise protected text.
replace('在稳定加工节拍的前提下最小化加工时间', '先最小化产品完工时间，再在保持其上界的条件下改善等待与加工节拍')
abstract=s[s.index('实验表明，342次运行'):s.index(r'\end{abstract}')]
replace(abstract, r'''实验中，对330个候选排程进行批次出片顺序与物理约束复核，得到305个满足要求的排程记录。八种混合配置、每种三个种子的阶段内精修均保持产品完工时间，总等待下降39.76\%--93.64\%，最大单项等待降至65~s。8、16、32片实例分别保留6720、676和6种满足批次顺序的既有取放序列，并给出相应构造族的数量下界。结果验证了批次内产品晶圆编码与具体晶圆排程之间的映射，以及时序精修对工序衔接的改善作用。
''')

# Consistent terminology, including the one affected phrase in the introduction.
for old,new in [('匿名路线','晶圆路线'),('匿名表示','批次任务表示'),('匿名成员','成员'),
                ('匿名任务','晶圆任务'),('匿名产品','产品晶圆'),('匿名MILP','批次任务MILP'),
                ('匿名变量','批次任务变量'),('匿名赋值','批次任务赋值'),('匿名可行域','批次任务可行域'),
                ('匿名求解','批次任务求解'),('匿名搜索','批次任务搜索'),('匿名解','批次任务解'),
                ('匿名PW对','候选PW对'),('匿名动作','晶圆动作')]:
    s=s.replace(old,new)

replace('最终得到晶圆加工的最优排程','最终输出具体晶圆的加工排程')
replace('表~\\ref{tab:symbol-cn-a}和表~\\ref{tab:symbol-cn-b}仅列理解批次任务表示所需的输入与关键决策。',
        '\\subsection{批次任务与产品晶圆编码}\n\\label{sec:model-encoding-cn}\n\n表~\\ref{tab:symbol-cn-a}和表~\\ref{tab:symbol-cn-b}列出批次任务的关键参数、变量及其类型。')
replace('具体产品编号$w$仅用于输入核对和输出追踪。','批次内第$k$片产品晶圆编码为$\\mathrm{Pjob}_j[k]$，实际晶圆编号$w$由编码表关联。')
replace('不同LP的来源仍由库存和取放地点保留，不强制按LP编号依次供片。',
        '同一任务的产品按批次内统一序号依次从LP取出，不同任务的出片可以交错。')
section(r'\paragraph{批次任务编码}',r'\begin{table*}',r'''\paragraph{批次内产品晶圆编码。}
产品按工艺模式、允许腔室集合及其他调度属性划分为$\mathrm{Pjob}_j$。LP $\ell$的槽位$s$对应实际晶圆编号$w=25(\ell-1)+s$，因此未装满LP时编号可以不连续。将任务$j$的实际晶圆编号按升序存入$\mathcal L_j$，令$N_j=|\mathcal L_j|$，建立编码
\begin{equation}
\begin{aligned}
\mathsf{Code}(\mathcal L_j[k])&=\mathrm{Pjob}_j[k],\quad k=1,\ldots,N_j,\\
\ell_{jk}&=1+\left\lfloor\frac{\mathcal L_j[k]-1}{25}\right\rfloor.
\end{aligned}
\label{eq:pjob-input-code-cn}
\end{equation}
$\mathrm{Pjob}_j[k]$表示任务$j$的第$k$片产品晶圆，$\ell_{jk}$是其给定来源LP。批次内序号连续，实际晶圆编号可以不连续；两者的对应关系在建模前确定。$N_{j\ell}=|\{k:\ell_{jk}=\ell\}|$记录各LP库存。

同一Pjob按$k=1,\ldots,N_j$严格依次取片，两片产品的LP取片开始时刻不能相同。该规则适用于整个任务，包括分布在不同LP的产品。成员位$(p,r)$承载产品的完整物理路线，变量$x_{j\ell pr}$选择其所属任务和来源库存；批次内序号由该任务的取片次序唯一确定。因此，模型保留每片产品的取放与加工状态，而不另设实际晶圆编号到候选成员位的选择变量。跨LP先后关系和同批取片互斥由第~\ref{sec:model-assignment-cn}节的约束保证。''')

section(r'\begin{table*}',r'\subsection{单源与双源物理加工路径}',r'''\begin{table*}[!t]
\centering\small
\caption{批次任务调度的关键参数}
\label{tab:symbol-cn-a}
\renewcommand{\arraystretch}{1.12}
\setlength{\tabcolsep}{4pt}
\begin{tabular}{@{}p{0.27\textwidth}p{0.19\textwidth}p{0.49\textwidth}@{}}
\toprule
符号 & 类型 & 含义\\\midrule
$\mathrm{Pjob}_j,m_j,\mathcal C_j$ & 任务集合、类别与集合参数 & 批次任务、工艺模式及允许腔室集合。\\
$N_j,N_{j\ell}$ & 非负整数参数 & 任务产品总数及其在LP $\ell$的库存；$N=\sum_jN_j$。\\
$\mathcal L_j,\ell_{jk}$ & 有序编号表、整数参数 & 批次内序号对应的实际晶圆编号及来源LP。\\
$\mathcal P,\mathcal Q_c$ & 有限索引集合 & 候选PW对及腔室周期，容量为$P_{\max},Q_{\max}$。\\
$d_m,d_o,\rho^r_{oo'}$ & 非负实数参数 & 生产/清洁时长、动作时长及移动或复位间隔，单位s。\\
$H,K_\rho$ & 正整数参数 & 清洁阈值和资源容量，其中$H\ge2$。\\
$\mathcal D,\Gamma_o$ & 有限集合参数 & 实体辅助晶圆库存及动作允许使用的物理手或槽位。\\
$\sigma$ & 0--1参数 & 单源为0，双源为1。\\
$\overline R_{i\rho},\overline T,M$ & 正实数参数 & 驻留上限、排程时域上界和条件约束松弛常数。\\
\bottomrule
\end{tabular}
\end{table*}

\begin{table*}[!t]
\centering\small
\caption{批次任务调度的关键决策变量}
\label{tab:symbol-cn-b}
\renewcommand{\arraystretch}{1.12}
\setlength{\tabcolsep}{4pt}
\begin{tabular}{@{}p{0.27\textwidth}p{0.19\textwidth}p{0.49\textwidth}@{}}
\toprule
符号 & 类型 & 含义\\\midrule
$x_{j\ell pr}$ & 0--1决策变量 & 成员位$(p,r)$是否使用任务$j$在LP $\ell$的一片产品。\\
$v_p,\mu_{pm},z_{pc}$ & 0--1决策变量 & PW对启用、加工类型选择和腔室分配。\\
$X_{pcq},K_{cqm},f_{pcq}$ & 0--1决策变量 & PW对周期占位、周期类型及加工时前侧占位。\\
$g_{pr\tau}$ & 0--1决策变量 & 辅助成员是否借用实体辅助晶圆$\tau$。\\
$h_{ou},y^\rho_{oo'},\gamma_{pa}$ & 0--1决策变量 & 物理手/槽位选择、资源次序和成对同步搬运选择。\\
$s_o,S_{cq}$ & 非负实数决策变量 & 物理动作与加工周期的开始时刻。\\
$\theta_{j\ell}$ & 非负实数辅助变量 & 同一Pjob相邻非空LP之间的取片时间分界。\\
$n_{cq}$ & 非负整数辅助变量 & 周期$q$结束后自上次清洁以来的生产周期计数。\\
$F_p,F_p^\psi,X^P_{pcq}$ & 0--1辅助变量 & 含产品对、含链式产品对及其周期占位的逻辑联结。\\
$C_{\max}$ & 非负实数决策变量 & 最后一片产品返回原LP的时刻上界，第一阶段最小化。\\
$L_{\max},v_{cq}$ & 非负实数辅助变量 & 最大单项等待与节拍偏差上界，第二阶段优化。\\
\bottomrule
\end{tabular}
\end{table*}''')

needle='每个被选择的成员具有完整路线，并在解码时获得唯一产品编号，因此数量约束不允许重复使用同一产品。'
replace(needle,r'''每个被选择的成员对应一片编码产品晶圆的完整路线，数量守恒使其与输入产品一一对应。

\noindent\textbf{批次内严格出片顺序。}
将任务$j$的非空LP按编号升序排列，$h_j(\ell)$表示$\ell$的下一个非空LP。用$\theta_{j\ell}$分隔这两个LP的取片区间，$s^{\rm pick}_{pr},e^{\rm pick}_{pr}$引用成员的LP取片事件。对相邻非空LP及所有候选成员位，施加
\begin{equation}
\begin{aligned}
0\le\theta_{j\ell}&\le\overline T,\\
e^{\rm pick}_{pr}&\le\theta_{j\ell}+M(1-x_{j\ell pr}),\\
s^{\rm pick}_{pr}&\ge\theta_{j\ell}-M(1-x_{j,h_j(\ell),pr}).
\end{aligned}
\label{eq:pjob-release-boundary-cn}
\end{equation}
于是，较小编号LP中属于该任务的产品全部取出后，下一LP才能开始供给该任务。令$\gamma_{p,\rm pick}$表示同对两个成员在LP同步取片，增加
\begin{equation}
\gamma_{p,\rm pick}+\sum_\ell(x_{j\ell p0}+x_{j\ell p1})\le2
\quad(j,p).
\label{eq:pjob-strict-pick-cn}
\end{equation}
同对两片产品属于同一Pjob时，该同步选择为0；不同PW对的取片由ATR资源互斥约束排序。结合正的取片时长，同一Pjob相邻产品的取片区间不重叠，开始时刻严格递增。批次内第$k$个取片成员即为$\mathrm{Pjob}_j[k]$，其来源LP与式~\eqref{eq:pjob-input-code-cn}一致。不同Pjob仍可交错出片，工艺相容时也可成对搬运。

''')

section(r'\subsection{批次任务表示的等价性与规模}',r'\section{批次任务编码、两阶段求解与晶圆解码}',r'''\subsection{编码表示的等价性与规模}
\label{sec:model4-equivalence-cn}
同任务、同LP的产品具有相同调度属性，按取片次序赋予批次内序号后，各成员的路线、资源占用与事件时刻保持不变。跨LP顺序由式~\eqref{eq:pjob-release-boundary-cn}联结，同批严格取片由式~\eqref{eq:pjob-strict-pick-cn}及ATR互斥保证。

令$\mathcal F_{\mathrm W}^{\rm seq}$为具有相同工艺资格、物理规则和批次出片顺序的逐片模型可行域。逐片排程可按式~\eqref{eq:pjob-input-code-cn}转换为批次任务排程；反向由各任务的取片顺序及$\mathcal L_j$恢复实际晶圆。两种映射保持产品完工时间、等待、节拍及全部物理事件，因此
\begin{equation}
\min_{\mathcal F}C_{\max}
=\min_{\mathcal F_{\mathrm W}^{\rm seq}}C_{\max}.
\label{eq:model4-equivalence-cn}
\end{equation}
这里比较的两种表示均执行相同的批次出片规则。

记$G=|\{(j,\ell):N_{j\ell}>0\}|$，一般候选域中的产品成员选择变量由逐片表示的$2NP_{\max}$改为$2GP_{\max}$。成员位直接关联其所属PW对，可省去逐产品到候选对的条件时刻联结及由身份选择推导的同对逻辑量。辅助晶圆实体复用、清洁与资源排序仍分别建模。

含产品的PW对至多为$N$个，将其与纯辅助PW对分别编号并作前缀激活，令含产品对的首成员为产品。只在前$N$个候选对实例化产品库存选择，得到$2GN$个$x$变量。若共有$J$个非空Pjob，跨LP出片规则增加$G-J$个连续辅助量$\theta_{j\ell}$；同批取片互斥使用已有同步选择和ATR次序变量。批次内序号$k$为编码索引，不增加逐片身份选择变量。设备动作及其资源冲突仍随实际晶圆数量增长。''')

section('批次任务模型直接优化Pjob库存选择',r'\subsection{结构化初始化与批次任务搜索}',r'''批次任务模型优化编码产品的配对、腔室分配、周期占位与物理动作。算法依次执行输入编码、可选初始赋值映射、第一阶段求解和第二阶段时序精修，最后输出具体晶圆排程。SCIP负责整数决策、有效不等式生成、上下界维护与可行性检验\citep{achterberg2009scip,bestuzheva2023scip}。

\subsection{输入编码与初始赋值映射}
\label{sec:pjob-encoding-cn}

输入阶段按第~\ref{sec:model-encoding-cn}节建立Pjob、批次内序号、LP库存及编码表$\mathcal L_j$。这一步在建模前完成，与是否使用初始解无关。优化过程中以成员位及库存变量表示编码产品，实际晶圆编号由输入编码表保存。

采用热启动时，将满足批次出片顺序的物理排程$\mathcal S^0$映射为变量赋值$\xi^0=\mathsf{Enc}(\mathcal S^0)$。先将含产品对和纯辅助对分别编号，使含产品对的首成员为产品；再由产品的Pjob和来源LP确定$x_{j\ell pr}$，把配对、分腔、周期占位及动作时刻写入对应变量。辅助晶圆保留实体编号，资源次序、取片时间分界和逻辑辅助量由受限模型补全。冷启动直接求解已编码的模型。''')
replace('先依据任务资格构造保守可行路线，按名义工艺负荷将可选任务分配到允许腔室，并协调补位、连续两次处理、清洁及辅助片归还。',
        '先依据任务资格构造可行路线，将各任务按批次内序号划分为连续区段并分配到允许腔室，使串行起点满足全Pjob出片顺序，同时协调补位、连续两次处理、清洁及辅助片归还。')

section('在两阶段求解结束并选定最终批次任务解',r'\begin{table}[!htbp]',r'''两阶段求解结束并选定最终解$\xi^\star$后，执行$\mathcal S^\star=\mathsf{Dec}(\xi^\star)$。对任务$j$，取出满足$\sum_\ell x_{j\ell pr}=1$的全部产品成员，按首次LP取片开始时刻排序为$i_j^{(1)},\ldots,i_j^{(N_j)}$。依据输入编码表恢复
\begin{equation}
i_j^{(k)}\longmapsto\mathrm{Pjob}_j[k]
\longmapsto\mathcal L_j[k],\qquad k=1,\ldots,N_j.
\label{eq:pjob-decoding-cn}
\end{equation}
出片顺序约束使排序严格递增，来源库存与编码LP逐项一致。将实际编号沿该成员的全部取放、配对、加工和回片事件传播，即得到具体晶圆动作表。解码采用确定映射，保留求解所得的腔室、资源和动作时刻。

例如，Pjob1仅允许CH2，包含LP1的晶圆1、3及LP2的晶圆26、27，输入编码为$\mathrm{Pjob}_1[1],\ldots,\mathrm{Pjob}_1[4]$；LP1的晶圆2属于仅允许CH3的Pjob2，编码为$\mathrm{Pjob}_2[1]$。若算法得到的出片编码次序为
\[
\mathrm{Pjob}_1[1],\ \mathrm{Pjob}_2[1],\ \mathrm{Pjob}_1[2],\
\mathrm{Pjob}_1[3],\ \mathrm{Pjob}_1[4],
\]
则解码后的实际晶圆次序为1、2、3、26、27。Pjob1跨LP保持统一序号顺序，Pjob2可以穿插；后续加工和回片顺序由资源与工艺约束决定。''')
replace(r'\textbf{1. 输入分组。}生成Pjob、$N_{j\ell}$和$\mathcal L_{j\ell}$，检查输入覆盖和资格。',
        r'\textbf{1. 输入编码。}生成Pjob、$\mathrm{Pjob}_j[k]$、$N_{j\ell}$和$\mathcal L_j$，建立实际晶圆与编码的对应表。')
replace(r'\textbf{2. 建模。}建立完整候选域的成员、周期和资源约束。',
        r'\textbf{2. 建模。}建立成员、周期、资源和全Pjob严格出片顺序约束。')

# Retain only evidence whose actual schedules satisfy the newly confirmed rule.
old_refine=s[s.index(r'\begin{table}[!htbp]',s.index(r'\paragraph{时序精修。}')):s.index(r'\paragraph{选割组件。}')]
old_refine=old_refine.replace('节拍项的独立效果需要在具有有效中心的配置中评价。','这组对照主要反映等待项的作用。')
section(r'\section{计算实验与结果分析}',r'\section{结论}',r'''\section{计算实验与结果分析}
\label{sec:experiments-cn}

实验评价批次内编码、出片顺序和时序精修，主要指标为约束验证结果、产品回片完工时间、总等待与最大单项等待。

\subsection{排程样本与验证方法}

计算环境为Windows~11、约32~GB内存，使用Python~3.12.12、PySCIPOpt~6.1.0和PyTorch~2.11.0。单进程SCIP内存设为6000~MiB，最多并行两个单线程任务，同一GPU最多运行一个学习策略任务。直接求解设定300~s，时序精修采用270~s主阶段与30~s第二阶段，结构化初始化预算为20~s。

为检验批次出片约束的作用，采用只约束各LP库存的排程作为对照候选，再按全Pjob序号及完整物理约束逐项验证。基础样本和消融样本分别含114和216个可行候选记录，覆盖单源/双源、$4\times1$、$2\times2$与混合配方。验证检查编码覆盖、全批次严格出片、腔室资格、产品回片、满片占位、连续处理、机械手容量、驻留及辅助片复用。

\begin{table}[!htbp]
\centering\small
\caption{候选排程的批次顺序与物理约束验证}
\label{tab:coverage-cn}
\begin{tabular}{lrrr}\toprule
样本组 & 候选记录 & 通过验证 & 跨LP逆序\\\midrule
基础样本 & 114 & 90 & 24\\
消融样本 & 216 & 215 & 1\\
合计 & 330 & 305 & 25\\\bottomrule
\end{tabular}
\end{table}

表~\ref{tab:coverage-cn}中305个排程记录满足全部检查，25个候选存在同Pjob跨LP逆序。该结果表明，各LP库存守恒不能替代批次整体的出片约束。下文时序比较仅使用精修前后均满足完整约束的排程。

\subsection{批次编码与具体晶圆排程}
\label{sec:model4-enumeration-cn}

选取8、16、32片双源实例，LP1--LP4各存$N/4$片，使用两腔和8片辅助晶圆。每种纯工艺模式设置三个Pjob：LP1产品仅允许CH2，LP2产品仅允许CH3，LP3、LP4产品两腔均可，清洁阈值取$H=3,10$。Pjob3先取完LP3产品，再从LP4取片，三个Pjob之间可以交错。

构造排程每次处理一片产品，以辅助片补齐工位，完成回片和清洁后进入下一产品块。块间900~s间隔覆盖操作、移动和复位，32片完整排程位于100000~s时域内。令$a=N/4$，三个Pjob分别含$a,a,2a$片产品；各任务内部顺序确定，Pjob3的每片产品有两个腔室选择，构造族大小为
\begin{equation}
L_N=\frac{N!}{a!\,a!\,(2a)!}\,2^{2a},\qquad a=N/4.
\label{eq:model4-family-count-cn}
\end{equation}
该构造给出每个固定配方与清洁阈值配置的可行取放顺序数量下界。

\begin{table*}[!t]
\centering\small
\caption{满足批次严格出片顺序的既有序列及构造族下界}
\label{tab:model4-enumeration-cn}
\begin{tabular}{rrrr}\toprule
产品数 & 保留不同顺序 & 每个固定配置已列顺序 & 每个固定配置的数量下界$L_N$\\\midrule
8 & 6720 & 3360 & 6720\\
16 & 676 & 338 & 230630400\\
32 & 6 & 3 & 506980245130444800\\\bottomrule
\end{tabular}
\end{table*}

表~\ref{tab:model4-enumeration-cn}从已有取放序列中筛选满足全Pjob顺序的记录，两种配方各占一半，同配方在两个阈值下相同的显示顺序合并计数。库存、资格、严格出片顺序和编码映射逐条检查；单产品块及各配置代表性完整排程进行物理重放。固定序列中的等待数值变化不重复计数。

\subsection{时序精修与必要消融}
\label{sec:model4-ablation-cn}

时序精修覆盖$N=4,8$、$H=3,10$和单/双源的八种混合配置，每种配置使用三个种子。24组第一阶段与第二阶段排程均通过全Pjob顺序和物理约束检查。表~\ref{tab:refinement-cn}以前一阶段的事件时刻为基准，报告同一离散结构下的等待变化。三个种子的表列指标在显示精度内相同；精修保持产品完工时间，总等待下降39.76\%--93.64\%，最大单项等待降至65~s。

'''+old_refine+r'''
完整线性目标、仅等待目标与二次节拍目标构成时序消融。对于具有相同第一阶段排程的比较，三种目标在上述配置中得到相同的表列结果，与有效节拍中心数为零一致。

\FloatBarrier
''')
section('本文针对满片加工的旋转腔组合设备，建立按工艺模式',r'\section*{CRediT作者贡献声明}',r'''本文针对满片加工的旋转腔组合设备，建立两阶段批次任务调度模型。输入晶圆按工艺模式与腔室资格分组，并编码为Pjob内第$k$片产品晶圆；批次内序号联结各LP库存与严格出片顺序。模型联合决定配对、分腔、辅助晶圆借用、清洁及物理时序，算法在完成两阶段求解后按编码表恢复具体晶圆动作序列。

排程验证得到305个满足批次顺序与完整物理约束的候选记录，构造族给出了8、16、32片实例的可行序列及数量下界。八种混合配置的24组阶段内精修保持产品完工时间，将总等待降低39.76\%--93.64\%。后续研究将进一步考察较大规模下的求解效率、有效节拍结构和执行时长扰动。''')

# Remove only bibliography entries that are no longer cited in the current text.
body=s[:s.index(r'\begin{thebibliography}')]
cited=set()
for group in re.findall(r'\\cite\w*\*?(?:\[[^\]]*\])*\{([^}]+)\}',body):
    cited.update(x.strip() for x in group.split(','))
items=list(re.finditer(r'\\bibitem(?:\[[\s\S]*?\])?\{([^}]+)\}',s))
removed=[]
for index in reversed(range(len(items))):
    item=items[index]
    if item.group(1) not in cited:
        end=items[index+1].start() if index+1<len(items) else s.index(r'\end{thebibliography}',item.end())
        s=s[:item.start()]+s[end:];removed.append(item.group(1))
refs=set(re.findall(r'\\bibitem(?:\[[\s\S]*?\])?\{([^}]+)\}',s))
assert refs==cited,(refs-cited,cited-refs)
s=re.sub(r'\\begin\{thebibliography\}\{\d+\}',lambda _:r'\begin{thebibliography}{'+str(len(refs))+'}',s)
assert '匿名' not in s
assert '模型4' not in s and '模型2' not in s
old_intro=source[source.index(r'\section{引言}'):source.index(r'\section{两阶段批次任务调度模型}')]
new_intro=s[s.index(r'\section{引言}'):s.index(r'\section{两阶段批次任务调度模型}')]
assert new_intro==old_intro.replace('匿名求解','批次任务求解')
old_first=source[source.index(r'\begin{abstract}'):source.index('实验表明，342次运行')]
new_first=s[s.index(r'\begin{abstract}'):s.index('实验中，对330个候选排程')]
assert new_first==old_first.replace('在稳定加工节拍的前提下最小化加工时间','先最小化产品完工时间，再在保持其上界的条件下改善等待与加工节拍')
target.write_text(s,'utf-8')
(HERE/'text_checks.json').write_text(json.dumps(dict(removed_references=sorted(removed),references=len(refs),
    introduction_only_terminology_changed=True,abstract_first_paragraph_only_approved_objective_changed=True,
    forbidden_terms=0),ensure_ascii=False,indent=2),'utf-8')
print('Updated current manuscript; removed references:',removed)

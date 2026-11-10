"""Apply the authorized Model4 revision to the Chinese source only."""
from pathlib import Path
import hashlib, json

ROOT = Path(__file__).resolve().parents[3]
PAPER = ROOT/'JMS-version/JMS_Review_CN.tex'
ORIGINAL = Path(__file__).parent/'original/JMS_Review_CN.tex'
s = ORIGINAL.read_text('utf-8')

def replace(old, new):
    global s
    if old not in s:
        raise ValueError('Missing source fragment: '+old[:100])
    s = s.replace(old, new)

replace(r'\section{问题描述与两阶段调度模型}', r'\section{问题描述与模型4的批次任务调度}')
replace('本文涉及的物料均为晶圆，', r'''本文将逐产品身份的联合表示称为模型2，将本文修订后的匿名批次任务表示称为模型4。模型4按工艺模式、允许腔室集合及其他影响调度的共同属性建立$\mathrm{Pjob}_j$，同一任务在各LP的数量作为库存输入。产品编号只在解码时恢复；同任务、同LP内仅交换产品身份不产生新的物理排程。已有算法与求解实验仍属于各自冻结的模型2或历史固定布局，模型4新增证据在第~\ref{sec:model4-enumeration-cn}节单独报告，不据此宣称求解加速。

本文涉及的物料均为晶圆，''')
start=s.index('表~\\ref{tab:symbol-cn-a}汇总')
end=s.index(r'\subsection{单源与双源物理加工路径}', start)
s=s[:start]+r'''表~\ref{tab:symbol-cn-a}和表~\ref{tab:symbol-cn-b}仅列理解模型4所需的输入与关键决策。其余派生量和线性化辅助量在使用处定义。$j$索引批次任务$\mathrm{Pjob}_j$，$\ell$索引LP，$p$索引候选PW对，$r=0,1$为对内成员位，$c,q$索引腔室及周期。匿名路线任务记为$i=(p,r)$；具体产品编号$w$仅用于输出追踪和历史实验。候选动作$o$的结束时刻由$s_o+d_ob_o$得到，装卸、旋转与周期时刻均引用同一组物理事件。

同模式下，允许集合分别为$\{\mathrm{CH2}\}$、$\{\mathrm{CH3}\}$和$\{\mathrm{CH2},\mathrm{CH3}\}$的产品属于三个不同$\mathrm{Pjob}$。这里的批次任务是一组待处理产品，允许跨多个PW对和周期执行；两腔均可的任务允许拆分到两腔。任务分组不要求整批同时加工，也不额外禁止工艺相容且腔室资格有交集的跨任务组对。不同LP的来源仍由库存和取放地点保留，不强制按LP编号依次供片。

\begin{table*}[!t]
\centering\small
\caption{模型4的关键参数}
\label{tab:symbol-cn-a}
\renewcommand{\arraystretch}{1.13}
\begin{tabular}{@{}p{0.24\textwidth}p{0.70\textwidth}@{}}
\toprule
符号 & 含义\\\midrule
$\mathrm{Pjob}_j,m_j,\mathcal C_j$ & 批次任务、给定工艺模式与允许腔室集合；同任务产品的其他调度属性相同。\\
$N_{j\ell}$ & 任务$j$在LP $\ell$的产品数量；$N=\sum_{j,\ell}N_{j\ell}$。\\
$\mathcal P,\mathcal Q_c$ & 候选PW对与腔室周期集合；容量$P_{\max},Q_{\max}$按实际产品量确定。\\
$d_m,d_o,\rho^r_{oo'}$ & 生产/清洁时长、原子动作时长以及位置相关移动或复位间隔，单位s。\\
$H,\mathcal D,\sigma$ & 清洁阈值、实体辅助片库存以及单源/双源配置。\\
$K_\rho,\Gamma_o,\overline R_{i\rho}$ & 资源容量、允许物理手/槽位以及匿名任务的驻留上限；洁净手与脏手规则保留。\\
$\overline T,M$ & 排程时域上界与有效条件松弛常数；各类物理时长沿用设备输入。\\
$\mathcal L_{j\ell}$ & 该任务在该LP的有序晶圆编号表，仅用于求解后的解码。\\
\bottomrule
\end{tabular}
\end{table*}

\begin{table*}[!t]
\centering\small
\caption{模型4的关键决策变量}
\label{tab:symbol-cn-b}
\renewcommand{\arraystretch}{1.13}
\begin{tabular}{@{}p{0.24\textwidth}p{0.70\textwidth}@{}}
\toprule
符号与类型 & 含义\\\midrule
$x_{j\ell pr}\in\{0,1\}$ & 对$p$的成员位$r$是否使用任务$j$在LP $\ell$的一个匿名产品。\\
$v_p,\mu_{pm},z_{pc}\in\{0,1\}$ & PW对是否启用、采用何种加工类型以及分配到哪个腔室。\\
$X_{pcq},K_{cqm}\in\{0,1\}$ & PW对的周期占位，以及周期选择生产或清洁。\\
$s_o\ge0$ & 物理动作起点，包含装卸、旋转与周期开始；终点由持续时间计算。\\
$g_{pr\tau}\in\{0,1\}$ & 辅助成员借用哪片实体辅助晶圆。\\
$h_{ou},y^\rho_{oo'},\gamma_{pa}\in\{0,1\}$ & 物理手/槽位选择、资源先后次序与允许的成对同步搬运选择。\\
$C_{\max}\ge0$ & 最后一片产品返回原LP的时刻上界，第一阶段最小化。\\
$L_{\max},v_{cq}\ge0$ & 第二阶段的最大等待与节拍偏差上界；总等待由事件时间计算。\\
\bottomrule
\end{tabular}
\end{table*}

''' +s[end:]
replace('产品晶圆集合记为$\\mathcal W$，晶圆路线任务集合记为$\\mathcal I$。每片产品晶圆对应一条完整路线，辅助晶圆每次借用对应一条供回路线；同一实体辅助晶圆可先后承担多个借用任务。',r'匿名路线任务集合为$\mathcal I=\{(p,r):p\in\mathcal P,r=0,1\}$。每个启用成员对应一次完整产品路线或辅助片借用路线；同一实体辅助片归还后可再次借用。定义产品标记$\beta_{pr}=\sum_{j,\ell}x_{j\ell pr}$和辅助标记$d_{pr}=v_p-\beta_{pr}$，二者由成员选择确定。')
replace('来源归属参数满足', '对匿名成员$i=(p,r)$，来源标记由其产品/辅助类型确定：')
replace(r'''\sum_{s\in\mathcal S}\chi_{is}=1,
\qquad i\in\mathcal I.''',r'''\begin{aligned}
\chi_{iA}&=\beta_{pr}+(1-\sigma)d_{pr},\quad
\chi_{iV}=\sigma d_{pr},\\
\chi_{iA}+\chi_{iV}&=v_p,\qquad i=(p,r)\in\mathcal I.
\end{aligned}''')
replace('晶圆的LP归属由输入给定。产品晶圆始终满足$\\chi_{iA}=1$、$\\chi_{iV}=0$；辅助晶圆满足$\\chi_{iA}=1-\\sigma$、$\\chi_{iV}=\\sigma$。',r'任务在各LP的库存$N_{j\ell}$由输入给定，成员的具体LP来源由$x_{j\ell pr}$选择并用于原LP回片。启用产品来自大气区，辅助片的来源区域由$\sigma$确定。')
start=s.index(r'\noindent\textbf{晶圆配对与腔室选择。}')
end=s.index(r'\noindent\textbf{候选容量上界。}',start)
s=s[:start]+r'''\noindent\textbf{批次任务成员与腔室选择。}
PW对由两个成员组成，可以是产品--产品、产品--辅助或辅助--辅助。$x_{j\ell pr}=1$表示选择任务类型与来源库存，不选择具体晶圆编号。仅为$N_{j\ell}>0$的组合建立该变量。数量守恒与满成员位约束为
\begin{equation}
\begin{aligned}
\sum_{p,r}x_{j\ell pr}&=N_{j\ell},\\
\beta_{pr}=\sum_{j,\ell}x_{j\ell pr},\qquad
\beta_{pr}+d_{pr}&=v_p.
\end{aligned}
\label{eq:joint-membership-cn}
\end{equation}
每个被选择的匿名成员具有完整路线，并在解码时获得唯一产品编号，因此数量约束不允许重复使用同一产品。取$\mathcal M=\{\zeta,\psi,\mathrm{cl}\}$分别表示$4\times1$、$2\times2$与清洁，$\mathcal C(m)$为设备对该类型的兼容腔室集合。任务资格与所选PW对共同满足
\begin{equation}
\begin{aligned}
\sum_m\mu_{pm}&=v_p,\qquad \sum_c z_{pc}=v_p,\\
x_{j\ell pr}&\le\mu_{p,m_j},\qquad
x_{j\ell pr}\le\sum_{c\in\mathcal C_j}z_{pc},\\
z_{pc}+\mu_{pm}&\le1\qquad(c\notin\mathcal C(m)).
\end{aligned}
\label{eq:joint-chamber-cn}
\end{equation}
同模式的不同任务可组对，但所选腔室必须属于全部产品成员允许集合的交集。仅CH2与仅CH3的产品不能组成同一对；两腔均可的任务可以与任一专属任务组对，并可把不同执行实例分配至不同腔室。$2\times2$产品仍须在同一腔室完成相邻两次处理。

产品模式$m_j$、任务资格$\mathcal C_j$及来源配置$\sigma$是输入。令$F_p$标记含产品对，$F_p^\psi$标记含$2\times2$产品的对，其联结为
\begin{equation}
\begin{aligned}
F_p&\le\sum_r\beta_{pr}\le2F_p,\qquad F_p+\mu_{p,\mathrm{cl}}\le1,\\
F_p^\psi&\le F_p,\quad F_p^\psi\le\mu_{p\psi},\quad
F_p^\psi\ge F_p+\mu_{p\psi}-1.
\end{aligned}
\label{eq:pair-type-cn}
\end{equation}
成员任务$i=(p,r)$的装卸时刻直接引用对$p$的相应事件；产品动作启用由$\beta_{pr}$确定，辅助路线由$d_{pr}$及$\sigma$确定。同对判断由索引$p$得到。对同类型、同LP、同资格产品，模型不搜索其身份排列；但不同匿名任务的位置、工艺进度和驻留时间仍分别保留。

''' +s[end:]
replace(r'$N=|\mathcal W|=N_{\zeta}+N_{\psi}$',r'$N=\sum_{j,\ell}N_{j\ell}=N_{\zeta}+N_{\psi}$')
s=s.replace('B_p','F_p')
replace('每个辅助晶圆位置对应借用需求$j=(p,r)$', '每个辅助晶圆位置对应借用需求$i=(p,r)$')
replace(r'''\sum_{\tau\in\mathcal T_c}g_{j\tau}=d_{pr},
\qquad j=(p,r)\in\mathcal J_c^D.''',r'''\sum_{\tau\in\mathcal D}g_{pr\tau}=d_{pr},\qquad
\sum_{r=0}^{1}g_{pr\tau}\le1.''')
s=s.replace('g_{j\\tau}', 'g_{pr\\tau}')
replace('各腔室可访问同一物理辅助库存，$\\mathcal T_c$为共享库存对腔室$c$的可用身份集合；相同身份在不同腔室的借用也必须互斥。', '各腔室可访问同一物理辅助库存$\\mathcal D$；相同身份在不同腔室的借用也必须互斥。同一对的两个成员不得使用同一实体辅助片。')
replace('对晶圆$w$进入和离开受限设备区段$r$的事件，有',r'对启用的匿名任务$i=(p,r)$进入和离开受限区段$\rho$的事件，有')
replace(r'''0\le s_{\operatorname{out}(w,r)}-e_{\operatorname{in}(w,r)}
\le\overline R_{wr}.''',r'''0\le s_{\operatorname{out}(i,\rho)}-e_{\operatorname{in}(i,\rho)}
\le\overline R_{i\rho}.''')
replace('直接以回片动作结束时刻$e_{w,\\mathrm{return}}$表示产品晶圆$w$回到原LP的时刻，第一阶段优化目标为',r'以匿名成员的回片动作结束时刻$e_{pr,\mathrm{return}}$表示其返回原LP的时刻，只对产品成员形成主目标下界：')
replace(r'''C_{\max}\ge e_{w,\mathrm{return}}\ (w\in\mathcal W),\qquad
\min_{\xi\in\mathcal F}C_{\max}.''',r'''\begin{gathered}
C_{\max}\ge e_{pr,\mathrm{return}}-M(1-\beta_{pr})\quad(p,r),\\
\min_{\xi\in\mathcal F_4}C_{\max}.
\end{gathered}''')
replace('前述约束共同定义联合可行域$\\mathcal F$，', '前述约束共同定义模型4的联合可行域$\\mathcal F_4$，下文简记为$\\mathcal F$，')
replace('对固定地点的动作，直接使用式~\\eqref{eq:resource-order-cn}。',r'对固定地点的动作，直接使用式~\eqref{eq:resource-order-cn}。产品源端和回片地点由$\chi_{pr\ell}=\sum_jx_{j\ell pr}$选择，其移动间隔同样按地点组合条件启用，且回到所选原LP；不得把不同LP之间的移动省略。')
replace('对于未完成工艺处理的产品晶圆从上装载锁取片至放入腔室的承片任务，',r'允许物理手集合按匿名成员的产品/辅助标记条件联结。对于未完成工艺处理的产品晶圆从上装载锁取片至放入腔室的承片任务，')
replace('区别于第2节产品成员指示量$a_{wpr}$',r'区别于第2节任务成员指示量$x_{j\ell pr}$')
replace(r'\mathrm{WPH}=3600|\mathcal W|/C_{\max}',r'\mathrm{WPH}=3600N/C_{\max}')

insert=r'''\subsection{模型4的解码、等价范围与规模边界}
\label{sec:model4-equivalence-cn}
给定匿名排程后，在每个$(j,\ell)$组内按首次LP取片时刻排序，依次赋予$\mathcal L_{j\ell}$中的升序编号；同时取片按固定成员位顺序赋号。编号沿该匿名任务的全部动作、配对、加工与回片记录传播。同任务产品进入设备后仍保留各自的位置、加工进度和时间状态，因此不是用一个计数器替代全部在制物料。任务中后释放的产品允许先完成；规范化编号不附加全路线FIFO约束，也不固定不同LP的服务顺序。

令$\mathcal F_2^{\rm elig}$为具有同样产品资格、参数和物理规则的逐片模型2可行域。将其中产品身份删除，可得到满足库存与资格的模型4排程；反向按照上述规则分配编号，得到一个逐片可行排程。两种映射保持事件时间、资源占用、产品完工时间及等待/节拍指标。该对应要求同任务同LP内不存在未纳入分组的到达时间、交期或产品专属约束，因而
\begin{equation}
\min_{\mathcal F_4}C_{\max}
=\min_{\mathcal F_2^{\rm elig}}C_{\max}.
\label{eq:model4-equivalence-cn}
\end{equation}
该等价性不把新增资格限制与无限制模型2混同，也不保证两个MILP的连续松弛、分支轨迹和限时求解结果相同。

记$G=|\{(j,\ell):N_{j\ell}>0\}|$，完整候选域中的产品成员选择变量由$2NP_{\max}$改为$2GP_{\max}$。匿名成员直接关联所属PW对，还可省去逐产品到候选PW对的条件时刻联结，以及通过产品身份推导同对关系的逻辑量。参数时长在模型2中已共享，不重复记为减模收益。辅助片实体复用、清洁、机械手排序和实际加工次数仍保留，候选容量不能用任务数替代产品数计算。若给每个匿名候选位机械地展开完整产品路线，条件动作与排序变量也可能增加；总变量与运行时间的净收益需通过稀疏实例化和匹配实验验证，目前不报告模型4求解提速。

'''
replace(r'\section{面向限时可行排程的求解框架}',insert+r'\section{面向限时可行排程的求解框架}')
replace('实验围绕三个制造运行问题展开：',r'除第~\ref{sec:model4-enumeration-cn}节的模型4构造性排程证据外，本节已有求解与算法数据均保留其模型2或历史固定布局归属，不重新标记为模型4实测性能。实验围绕三个制造运行问题展开：')

enumeration=r'''\subsection{模型4的可行排程序列与计数}
\label{sec:model4-enumeration-cn}
本节按模型2既有文件的读取标准列举模型4排程：仅显示全部产品和实际辅助片的ATR/VTR取放与位置，按动作开始时刻排序，同刻动作保留并列组；旋转、曝光、动作终点及数值时间保存在可重建的完整见证中。具体编号按任务和LP规范化，因此同类身份置换不另计数。只改变等待数值而不改变显示动作顺序也不另计数。

每个规模$N\in\{8,16,32\}$包含纯$4\times1$、纯$2\times2$与$H=3,10$的四个固定配置。采用双源、两腔CH2/CH3、8片辅助片及100000~s时域；LP1--LP4各存$N/4$片。每个配置分别建立三个任务：$\mathrm{Pjob}_1$仅允许CH2且来自LP1；$\mathrm{Pjob}_2$仅允许CH3且来自LP2；$\mathrm{Pjob}_3$允许两腔且来自LP3、LP4。其余物理时长沿用模型2配置。任务资格是本节新增输入，不把本节数量与无资格限制的旧文件数量当作同一空间的直接比较。

采用每次处理一个产品、辅助片补齐工位的串行构造；每产品完成完整工艺与回片后执行清洁并归还辅助片，再进入下一个产品块。产品块按900~s间隔启动，该间隔覆盖单块所有动作及复位、移动保护间隔；32片完整终点仍小于100000~s。每块结束时腔室清洁计数为0，故两个阈值均合法，且不会中断$2\times2$的相邻两次处理。该构造用于证明可行性和数量，不是吞吐率最优策略。

四种LP来源构成各出现$N/4$次的多重集序列；其中LP3、LP4的$N/2$个产品分别可选择两腔。每个来源--腔室序列解码为一条规范化取放顺序，来源或所选腔室的变化在输出中可辨，因此此构造族在每个固定配置中的精确大小为
\begin{equation}
L_N=\frac{N!}{[(N/4)!]^4}\,2^{N/2}.
\label{eq:model4-family-count-cn}
\end{equation}
$L_N$同时是模型4全部可行取放顺序数量的下界，不是全空间精确总数。它没有使用同任务同LP产品身份的任意排列；模型2旧导出中的$N!$身份置换下界不直接移用到模型4。

\begin{table*}[!t]
\centering\small
\caption{模型4规范化取放顺序的已列数量与构造性下界}
\label{tab:model4-enumeration-cn}
\begin{tabular}{rrrr}
\toprule
产品数 & 文件内不重复顺序 & 每个固定配置已列顺序 & 每个固定配置至少数量$L_N$\\\midrule
8 & 40320 & 20160 & 40320\\
16 & 50000 & 25000 & 16144128000\\
32 & 60000 & 30000 & 6524835754828824576000\\
\bottomrule
\end{tabular}
\end{table*}

每个规模按构造编号等距选取来源--腔室序列，两种配方各占一半；同一配方在$H=3$与10下显示顺序相同，合并为一条并注明适用配置。表~\ref{tab:model4-enumeration-cn}的文件条数是导出配额，不表示规模覆盖比例；全部空间总数仍未知。

验证分为三层：所有合法LP/腔室/配方/阈值的单产品块执行完整物理重放；每条导出检查库存、资格、规范化编号和显示顺序去重，并由保护间隔证明块间衔接；每个规模、配方和阈值的首、中、末构造编号另执行完整规模物理重放。完整见证检查路线、手爪、移动、驻留、辅助复用、旋转侧位、曝光与清洁，另检查$\mathrm{Pjob}$资格和库存。导出数据保存源码快照、哈希、索引与代表性时间见证。未对每条重新求解MILP，也不宣称已完成模型4的全空间枚举、最优性证明或等预算性能比较。

'''
replace(r'\subsection{阈值前可选清洁的重验证结果}',enumeration+r'\subsection{模型2阈值前可选清洁的重验证结果}')
replace('本文建立两阶段混合整数线性规划模型，',r'本文以匿名批次任务$\mathrm{Pjob}$建立模型4的两阶段混合整数线性规划表示，')
replace('采用结\n构化初始化、限时MILP搜索和时序精修，并评估学习割选择的作用。', '已有模型2及历史固定布局采用结构化初始化、限时MILP搜索和时序精修，并评估学习割选择的作用。')
replace('研究为满片工艺下的旋转腔组合设备调度的模式比较及有限预算内可行排程的获取提供了统一的\n建模与评价方法。', '模型4另列举8、16、32片的规范化可行取放顺序，并给出构造性数量下界；这些记录不构成求解提速或最优性证据。研究为满片工艺下的模式比较及有限预算可行排程提供建模与评价方法。')
replace('本文以满片工艺引入的假片占用为出发点，研究PECVD旋转腔组合设备在不同运行条件下的工艺模式比较与有限预算排程。',r'本文以满片工艺引入的假片占用为出发点，研究PECVD旋转腔组合设备在不同运行条件下的工艺模式比较与有限预算排程。模型4按工艺和腔室资格建立$\mathrm{Pjob}$，通过匿名成员与后验编号删除同任务同LP产品身份的重复选择，保留来源、配对、分腔和完整物理过程。新增8、16、32片导出分别包含40320、50000、60000条规范化取放顺序，构造性下界与验证范围见第~\ref{sec:model4-enumeration-cn}节。以下求解指标仍来自模型2或历史固定布局，不作为模型4性能结果。')

PAPER.write_text(s, 'utf-8')
print('Updated Chinese manuscript:', len(s), 'characters')

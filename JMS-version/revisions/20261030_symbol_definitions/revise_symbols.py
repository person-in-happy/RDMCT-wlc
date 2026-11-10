from pathlib import Path
import hashlib,json,re

HERE=Path(__file__).resolve().parent
PAPER=HERE.parents[1]
path=PAPER/'JMS_Review_CN.tex'
original=(HERE/'original/JMS_Review_CN.tex').read_text('utf-8')
assert hashlib.sha256(path.read_bytes()).hexdigest()=='f11d2b907eaaa49b3e3386a407c61f9445457dec8962dc9bc6a59482b4105030'
s=original

def swap(a,b):
    global s
    assert s.count(a)==1,(a[:85],s.count(a))
    s=s.replace(a,b)

def block(a,b,new):
    global s
    i=s.index(a);j=s.index(b,i)
    s=s[:i]+new+'\n\n'+s[j:]

# Use one meaning for each primary index: r is a pair member; ell is an LP.
s=s.replace(r"\rho^r_{oo'}",r"\delta^\rho_{oo'}").replace(r"\rho^r_{o'o}",r"\delta^\rho_{o'o}")
s=s.replace(r"y^r_{oo'}",r"y^\rho_{oo'}")
s=s.replace(r"\rho^{\rm VTR}_{cc'}",r"\delta^{\rm VTR}_{cc'}")
s=s.replace(r'h_{o\ell}',r'h_{ou}').replace(r"h_{o'\ell}",r"h_{o'u}")
s=s.replace(r'\sum_{\ell\in\Gamma_o}',r'\sum_{u\in\Gamma_o}')
s=s.replace(r'\mathcal A_{is}',r'\mathcal A_{i\varsigma}').replace(r'\chi_{is}',r'\chi_{i\varsigma}')
s=s.replace(r's\in\mathcal S',r'\varsigma\in\mathcal S').replace('在来源$s$',r'在来源区域$\varsigma$')
s=s.replace(r'\mathcal Q^w',r'\mathcal W').replace(r'\mathcal I_h',r'\mathcal I_{\rm rhythm}')

block('表~\\ref{tab:symbol-cn-a}和表~\\ref{tab:symbol-cn-b}', '同模式下，允许集合分别为',r'''表~\ref{tab:symbol-cn-a}和表~\ref{tab:symbol-cn-b}列出关键参数和变量；其余逻辑量与事件引用在相应约束前定义。所有时刻和时长的单位均为s，数量的单位为片、对或周期。

\paragraph{基本索引及取值范围。}
$j\in\mathcal J=\{1,\ldots,J\}$为批次任务索引，$J$为非空Pjob数量；$k\in\{1,\ldots,N_j\}$为任务$j$内的产品序号；$\ell\in\{1,2,3,4\}$为LP编号。$p\in\mathcal P=\{1,\ldots,P_{\max}\}$为候选PW对编号，每个PW对含两个成员，$r\in\{0,1\}$表示对内成员位，$i=(p,r)\in\mathcal I$表示该成员的完整路线任务。$c\in\mathcal C=\{\mathrm{CH2},\mathrm{CH3}\}$为腔室索引，$q\in\mathcal Q_c=\{1,\ldots,Q_{\max}\}$为腔室$c$的候选周期编号；相同$q$在不同腔室对应不同周期。$m\in\mathcal M=\{\zeta,\psi,\mathrm{cl}\}$为加工类型，分别表示$4\times1$生产、$2\times2$生产和清洁。

$o,o'\in\mathcal O$为候选物理动作索引；撇号仅区分两个动作，不表示求导。$\rho\in\mathcal R$为资源类索引，$\mathcal R$包括机械手执行机构、承片手、模块槽位、腔室及辅助晶圆库存等资源类；$u\in\Gamma_o$为动作或占用区间$o$允许使用的物理单元，$\tau\in\mathcal D$为实体辅助晶圆编号。$a$为同地点原子取放段的标签，例如源端取片或入锁放片；$\alpha\in\mathcal W$为等待项索引。资源占用区间的端点引用相应物理动作时刻，具体见第~\ref{sec:model-resource-cn}节。

\begin{table*}[t]
\centering\small
\caption{批次任务调度的关键参数}
\label{tab:symbol-cn-a}
\renewcommand{\arraystretch}{1.05}
\setlength{\tabcolsep}{4pt}
\begin{tabular}{@{}p{0.23\textwidth}p{0.17\textwidth}p{0.55\textwidth}@{}}
\toprule
符号 & 类型 & 定义与下标含义\\\midrule
$\mathrm{Pjob}_j,m_j,\mathcal C_j$ & 产品集合、类别参数、腔室集合 & $\mathrm{Pjob}_j$为第$j$个批次任务的产品集合；$m_j$为该任务给定的生产模式；$\mathcal C_j\subseteq\mathcal C$为该任务产品允许使用的腔室集合。\\
$N_j,N_{j\ell}$ & 非负整数参数 & $N_j$为任务$j$的产品总数；$N_{j\ell}$为其中存放在LP $\ell$的产品数；$N_j=\sum_\ell N_{j\ell}$，全批产品数$N=\sum_jN_j$。\\
$\mathcal L_j$ & 有序编号表 & 任务$j$的实际晶圆编号按升序组成的列表；$\mathcal L_j[k]$为该任务第$k$片产品的实际晶圆编号。\\
$\ell_{jk}$ & 整数参数 & 任务$j$内第$k$片产品晶圆的来源LP编号，$k=1,\ldots,N_j$，$\ell_{jk}\in\{1,2,3,4\}$；其值由$\mathcal L_j[k]$确定。\\
$\mathcal P,\mathcal Q_c$ & 有限索引集合 & $\mathcal P$为候选PW对集合；$\mathcal Q_c$为腔室$c$的候选周期集合；$P_{\max},Q_{\max}$分别为两类集合的容量上界。\\
$d_m,d_o,r_c$ & 正实数参数 & $d_m$为类型$m$的生产或清洁时长；$d_o$为物理动作$o$的持续时间；$r_c$为腔室$c$一次半周旋转的时长。\\
$\delta_{oo'},\delta^\rho_{oo'}$ & 非负实数参数 & $\delta_{oo'}$为技术先后弧$o\to o'$要求的最小间隔；$\delta^\rho_{oo'}$为资源$\rho$完成$o$后执行$o'$所需的换位或复位间隔。\\
$H,K_\rho$ & 正整数参数 & $H$为同一腔室两次清洁之间允许的最多生产周期数，$H\ge2$；$K_\rho$为资源类$\rho$的物理单元数，独占执行机构取1。\\
$\mathcal D,\Gamma_o$ & 有限集合参数 & $\mathcal D$为可复用实体辅助晶圆的编号集合；$\Gamma_o$为占用$o$允许选择的物理单元集合，按给定的材料类型和洁净/脏手规则确定。\\
$\sigma$ & 0--1参数 & 辅助晶圆来源配置：单源取0，双源取1。\\
$\overline R_{i\rho},\overline T,M$ & 正实数参数 & $\overline R_{i\rho}$为成员任务$i$在资源或模块$\rho$上的驻留/承片时长上限；$\overline T$为排程时域上界；$M$为放松未启用条件约束的有效大常数。\\
\bottomrule
\end{tabular}
\end{table*}

\begin{table*}[t]
\centering\small
\caption{批次任务调度的关键决策变量}
\label{tab:symbol-cn-b}
\renewcommand{\arraystretch}{1.05}
\setlength{\tabcolsep}{4pt}
\begin{tabular}{@{}p{0.23\textwidth}p{0.17\textwidth}p{0.55\textwidth}@{}}
\toprule
符号 & 类型 & 定义与取值含义\\\midrule
$x_{j\ell pr}$ & 0--1决策变量 & 取1当且仅当PW对$p$的成员位$r$使用任务$j$在LP $\ell$的一片产品；仅对$N_{j\ell}>0$的组合建立。\\
$v_p,\mu_{pm},z_{pc}$ & 0--1决策变量 & $v_p=1$表示PW对$p$启用；$\mu_{pm}=1$表示该对采用类型$m$；$z_{pc}=1$表示该对分配至腔室$c$。\\
$X_{pcq},K_{cqm},f_{pcq}$ & 0--1决策变量 & $X_{pcq}=1$表示对$p$占用腔室$c$的周期$q$；$K_{cqm}=1$表示该周期采用类型$m$；$f_{pcq}=1$表示该对在此周期位于访问前侧。\\
$g_{pr\tau}$ & 0--1决策变量 & 取1表示成员位$(p,r)$的辅助片借用需求选用实体辅助晶圆$\tau\in\mathcal D$。\\
$h_{ou},y^\rho_{oo'},\gamma_{pa}$ & 0--1决策变量 & $h_{ou}=1$表示占用$o$选择物理单元$u$；$y^\rho_{oo'}=1$表示在竞争同一单元时$o$先于$o'$；$\gamma_{pa}=1$表示对$p$的两成员在原子段$a$同步搬运。\\
$s_o,S_{cq}$ & 非负实数决策变量 & $s_o$为物理动作$o$的开始时刻；$S_{cq}$为腔室$c$第$q$个周期的开始时刻；相应结束时刻由动作时长或周期类型导出。\\
$\theta_{j\ell}$ & 非负实数辅助变量 & 任务$j$由LP $\ell$转至下一非空LP取片的时间分界；仅对存在后继非空LP的$(j,\ell)$定义。\\
$n_{cq}$ & 非负整数辅助变量 & 腔室$c$第$q$个周期结束后，自上次清洁以来累计完成的生产周期数，范围为$0,\ldots,H$。\\
$F_p,F_p^\psi,X^P_{pcq}$ & 0--1辅助变量 & $F_p=1$表示对$p$含产品；$F_p^\psi=1$表示其含$2\times2$产品；$X^P_{pcq}=1$表示该含产品对参加腔室$c$的周期$q$。\\
$C_{\max}$ & 非负实数决策变量 & 所有产品返回原LP时刻的上界，第一阶段将其最小化。\\
$L_{\max},v_{cq}$ & 非负实数辅助变量 & $L_{\max}$为所有等待项的最大值上界；$v_{cq}$为以$(c,q)$为中心的相邻周期开始间隔变化量的绝对值上界。\\
\bottomrule
\end{tabular}
\end{table*}''')

swap('LP $\\ell$的槽位$s$对应实际晶圆编号', 'LP $\\ell$的槽位$s\\in\\{1,\\ldots,25\\}$对应实际晶圆编号')
swap('$\\mathrm{Pjob}_j[k]$表示任务$j$的第$k$片产品晶圆，$\\ell_{jk}$是其给定来源LP。',
     '$\\mathrm{Pjob}_j[k]$表示任务$j$的第$k$片产品晶圆；$k$只在该Pjob内部从1编号至$N_j$。$\\ell_{jk}$中的$j$标识任务、$k$标识该任务内的产品，其值是来源LP编号。例如$\\mathcal L_1=(1,3,26,27)$时，$\\ell_{1,3}=2$，表示Pjob1的第3片产品是实际晶圆26，位于LP2。')
swap('实际晶圆编号可以不连续；两者的对应关系在建模前确定。',
     '实际晶圆编号可以不连续；两者的对应关系在建模前确定。$\\mathsf{Code}$是该确定性编码映射，方括号$[k]$表示取列表的第$k$项，$\\lfloor\\cdot\\rfloor$表示向下取整。')
swap('定义产品标记$\\beta_{pr}=\\sum_{j,\\ell}x_{j\\ell pr}$和辅助标记$d_{pr}=v_p-\\beta_{pr}$，两者均取0或1并由成员选择确定。',
     '定义产品标记$\\beta_{pr}=\\sum_{j,\\ell}x_{j\\ell pr}$和辅助标记$d_{pr}=v_p-\\beta_{pr}$：前者取1表示成员位$(p,r)$为产品，后者取1表示其为辅助片借用。两者是取值为0或1的派生量；$d_{pr}$为成员类型标记，与时长参数$d_o,d_m$通过下标区分。')
swap('来源标记由其产品/辅助类型确定：','来源标记$\\chi_{iA},\\chi_{iV}\\in\\{0,1\\}$分别表示该成员是否由大气区A、真空区V供给，由其产品/辅助类型确定：')
swap('$h_j(\\ell)$表示$\\ell$的下一个非空LP。',
     '$h_j(\\ell)=\\min\\{\\ell\'>\\ell:N_{j\\ell\'}>0\\}$表示该任务在LP $\\ell$之后的首个非空LP；若集合为空，则不为该$(j,\\ell)$建立分界变量。函数$h_j(\\ell)$由输入库存确定，不是决策变量。')
swap('$s^{\\rm pick}_{pr},e^{\\rm pick}_{pr}$引用成员的LP取片事件。',
     '$s^{\\rm pick}_{pr},e^{\\rm pick}_{pr}$分别引用成员$(p,r)$在LP取片动作的开始和结束时刻，上标$\\mathrm{pick}$是动作标签。')
swap('$\\mathcal C(m)$为设备对该类型的兼容腔室集合。',
     '$\\mathcal C(m)\\subseteq\\mathcal C$为设备能够执行类型$m$的腔室集合，由设备能力给定；$\\mathcal C_j$则为任务$j$的产品资格集合，两者分别约束设备能力和产品资格。')
swap('$\\chi_{pr\\ell}=\\sum_jx_{j\\ell pr}$，辅助来源位置标记',
     '$\\chi_{pr\\ell}=\\sum_jx_{j\\ell pr}\\in\\{0,1\\}$，取1表示成员$(p,r)$的来源及回片地点为LP $\\ell$；辅助来源位置标记')
swap('其中，$T$为全设备生产周期总数的上界。','其中，$T,J_{\\max},P_{\\max},Q_{\\max}$均为由产品数量计算的整数上界；$T$为全设备生产周期总数的上界，$J_{\\max}$为清洁总次数上界，与Pjob数量$J$含义不同。')

swap('$b_o$表示启用状态，$s_o,e_o$分别为起止时刻，$d_o$为给定持续时间，$M$为有效大常数。',
     '$b_o\\in\\{0,1\\}$表示动作是否启用，$s_o\\in[0,\\overline T]$为开始时刻，$e_o$为结束时刻表达式，$d_o>0$为给定持续时间，$M$为有效大常数。$b_o$由成员、周期及搬运方式的启用关系确定，不是任意删除必需动作的开关。')
swap('$\\gamma$统称成对搬运与单源随行入片等离散选择。完整先后弧集合为',
     '$\\varsigma\\in\\mathcal S=\\{A,V\\}$为来源区域索引，$\\gamma$统称成对搬运与单源随行入片等0--1选择。弧$(o,o\')$表示动作$o$是$o\'$的前驱，集合$\\mathcal A^{\\rm int}$由腔内工艺规则给定，$\\mathcal A_{i\\varsigma}(\\gamma)$随所选路线启用。完整先后弧集合为')
swap('对必须依次执行的操作先后弧$(o,o\')\\in\\mathcal A$，有',
     '对必须依次执行的操作先后弧$(o,o\')\\in\\mathcal A$，令$\\delta_{oo\'}\\ge0$为前驱结束至后继开始所需的最小技术间隔，有')
swap('若选择量为$x$，对应参考阶段为$[s^{\\rm ref},e^{\\rm ref}]$，则',
     '以$x\\in\\{0,1\\}$统称当前联结所使用的成员、占位或搬运选择量，其具体取值引用对应的既有变量。$s^{\\rm ref},e^{\\rm ref}$分别为被联结的PW对或周期事件起止时刻，上标$\\mathrm{ref}$表示参考事件而非给定常量，则')
swap('$s_{ia},e_{ia}$为成员任务$i$在该段的起止时刻。',
     '$a$标识同地点的原子取片或放片段，$\\gamma_{pa}\\in\\{0,1\\}$；$s_{ia},e_{ia}$分别引用成员$i$在段$a$上的动作起止时刻，不另设独立时钟。')
swap('$\\gamma^{\\rm early}_p,\\gamma^{\\rm late}_p$分别选择',
     '$\\gamma^{\\rm early}_p,\\gamma^{\\rm late}_p,\\gamma_{p,\\mathrm{in}}\\in\\{0,1\\}$均为路线选择变量，其中前两个分别选择')
swap('二元量$A_{pcq}$标识对$p$在腔室$c$的首次参加周期，派生量$Z_{pcq}$标识末次参加周期。',
     '二元辅助量$A_{pcq}$在对$p$首次参加腔室$c$的周期$q$时取1；0--1派生量$Z_{pcq}$在该对最后一次参加此周期时取1。$A^\\psi_{pcq},Z^\\psi_{pcq}$分别标记$2\\times2$含产品对在该周期首次、末次参加处理，均由占位差量导出；上标$\\psi$表示链式生产类型。')
swap('$U_{cq}=\\sum_mK_{cqm}\\in\\{0,1\\}$简记周期启用状态',
     '$U_{cq}=\\sum_mK_{cqm}\\in\\{0,1\\}$为派生周期启用标记，取1表示腔室$c$的周期$q$存在')
swap('分别标记保留上一周期的一个对和本周期后全部退出，取值均为0或1；',
     '分别在周期$q$保留来自$q-1$的一个对、周期$q$结束后两个对全部退出时取1，取值均为0或1；')
swap('分别由$U_{cq}$和$\\upsilon_{cq}$启用，持续$r_c$。',
     '分别由$U_{cq}$和$\\upsilon_{cq}$启用；上标$\\mathrm{rot-}$和$\\mathrm{rot+}$分别表示周期前和周期后的半周旋转，每次持续给定时长$r_c$。上标$\\mathrm{load},\\mathrm{unload}$分别表示PW对装入与卸出。')

# Distinguish the cleaning-segment index h from the end-time symbol e.
start=s.index('清洁区段$e$由');end=s.index('给定解后，',start)
seg=s[start:end]
seg=seg.replace('清洁区段$e$','清洁区段$h$').replace('区段$e$','区段$h$').replace('第$e$区段','第$h$区段')
seg=seg.replace('a_{vce}','a_{vch}').replace('q^{\\rm cl}_{ce}','q^{\\rm cl}_{ch}')
seg=seg.replace('_{c,e-1}','_{c,h-1}').replace('_{ce}','_{ch}').replace('(e>1)','(h>1)')
seg=seg.replace('由周期类型序列中的清洁边界导出。','由周期类型序列中的清洁边界导出，$h=1,2,\\ldots$按腔室$c$内的生产段顺序编号。')
seg=seg.replace('$a_{vch}=1$表示任务$v$属于区段$h$，', '$v\\in\\mathcal V_c$为生产任务索引；0--1派生标记$a_{vch}=1$表示该任务属于腔室$c$的第$h$段，')
seg=seg.replace('$q^{\\rm cl}_{ch}=1$表示该区段后有清洁；','$q^{\\rm cl}_{ch}\\in\\{0,1\\}$取1表示该段后执行清洁，其上标$\\mathrm{cl}$为清洁标签，与周期编号$q$不是同一量；')
seg=seg.replace('所有符号均引用相应物理事件，','上标$\\nu$是五个清洁阶段的标签；$s_v,e_v$和各清洁阶段起止时刻均为既有物理事件的引用，不增加独立时间变量。')
s=s[:start]+seg+s[end:]

swap('每个有效需求必须选择一片库存中的物理辅助晶圆：',
     '对实体编号$\\tau\\in\\mathcal D$，$g_{pr\\tau}=1$表示辅助需求$(p,r)$借用晶圆$\\tau$，否则为0；每个有效需求必须选择一片库存中的物理辅助晶圆：')
swap('以$o$表示该资源占用任务，有',
     '将这些占用区间组成集合$\\mathcal O^{\\rm occ}$，在本节用$o\\in\\mathcal O^{\\rm occ}$表示一项占用，其$s_o,e_o$引用对应物理动作的开始或结束端点，$b_o$引用该占用的启用标记。可选单元编号为$u\\in\\Gamma_o$，有')
swap('是否选择单元$\\ell$','是否选择单元$u$')
swap('若操作$o$和$o\'$可能竞争资源$r$的同一槽位$\\ell$，则',
     '若占用$o,o\'$可能竞争资源类$\\rho$的同一物理单元$u$，令$y^\\rho_{oo\'}=1$表示$o$先于$o\'$、取0表示反向。$\\delta^\\rho_{oo\'}$为该方向的换位或复位间隔，对承片手或辅助晶圆实体的连续占用取0，则')
swap('$\\delta^{\\rm VTR}_{cc\'}$是两个腔室间的给定移动时间；',
     '$p\',c\'$分别为另一个PW对及其腔室索引，$\\delta^{\\rm VTR}_{cc\'}\\ge0$是VTR从腔室$c$移动至$c\'$的给定时长；')
swap('模块驻留区段$\\rho$从放片完成至取片开始，满足',
     '用$\\rho$标识其访问的AL、装载锁或工艺腔室模块。$\\operatorname{in}(i,\\rho)$为将成员$i$放入模块$\\rho$的动作索引，$\\operatorname{out}(i,\\rho)$为从该模块取出的动作索引；模块驻留从放片结束$e_{\\operatorname{in}(i,\\rho)}$计至取片开始$s_{\\operatorname{out}(i,\\rho)}$，满足')
swap('WPH仅以产品回片的$C_{\\max}$为分母。',
     '单位小时产品产出率记为$\\mathrm{WPH}=3600N/C_{\\max}$，由产品数与回片完工时间计算，不是额外决策变量。')
swap('$\\xi_d$为向量的第$d$个分量，带帽量在第二阶段作为常量。',
     '$d$为决策向量的分量索引，$\\xi_d$为其第$d$个分量；$\\widehat\\xi_d$为第一阶段所得对应值，$\\widehat C$及带帽分量在第二阶段作为给定常量。')
swap('给定完工时间容差$\\varepsilon_C$，','给定非负实数完工时间容差$\\varepsilon_C$（单位s），')
swap('令$\\mathcal W$为纳入评价的等待项索引集合，',
     '令$\\mathcal W$为纳入评价的等待项索引集合，$\\alpha\\in\\mathcal W$标识一对前后衔接事件，')
swap('若启用等待软上限$\\bar\\omega_\\alpha$，以非负辅助量$\\eta_\\alpha$表示超额等待的上界：',
     '若启用等待软上限，$\\bar\\omega_\\alpha\\ge0$为等待项$\\alpha$的给定实数上限，$\\eta_\\alpha\\ge0$为其超额等待的实数辅助变量，两者单位均为s：')
swap('将上述指标按非负权重$\\lambda_1,\\ldots,\\lambda_4$组合，',
     '给定非负实数权重$\\lambda_1,\\ldots,\\lambda_4$，下标1至4依次对应总等待、最大单项等待、节拍变化和软等待超额；将上述指标组合，')

block('机器人前缀载片计数也可进行条件代入。','公共初始解的辅助变量补全',r'''机器人前缀载片计数也可进行条件代入。对同一机械手资源$\rho$的动作$o,o'$，沿用二元次序量$y^\rho_{oo'}$；$\Delta_{o'}$为动作$o'$引起的载片数增量，是已知整数，单片取/放取$+1/-1$，成对取/放取$+2/-2$。保留$2y^\rho_{oo'}\le b_o+b_{o'}$后，动作$o$之前由$o'$产生的计数贡献可由$\Delta_{o'}(b_ob_{o'}-y^\rho_{oo'})$改写为$\Delta_{o'}(b_{o'}-y^\rho_{oo'})$。该代入在$b_o=1$时恒等；$b_o=0$时前缀容量条件不启用。实现仅在$M\ge\sum_{o'}|\Delta_{o'}|+4$、未启用前缀的松弛行冗余时采用此改写，其中求和遍历该机械手的全部候选动作。

对于资源类$\rho$的承片、槽位或辅助身份占用，以$\iota,\iota'$索引两项占用区间；$s_\iota,e_\iota$为区间端点，$b_\iota\in\{0,1\}$为启用标记，均引用对应物理事件或成员状态。将该资源的$K_\rho$个单元编号为$u=1,\ldots,K_\rho$，以$a_{\iota u}$简记对应的物理单元分配量$h_{ou}$或辅助片分配量$g_{pr\tau}$，不新增另一套选择变量。定义由分配唯一确定的整数辅助编号$u_\iota=\sum_{u=1}^{K_\rho}u a_{\iota u}\in\{0,\ldots,K_\rho\}$，未启用时为0。令$B=\overline T+\max\{0,d^{\rm reset}_{U},d^{\rm reset}_{L}\}$，其中$d^{\rm reset}_{U},d^{\rm reset}_{L}\ge0$是上、下装载锁的给定复位时长，$B$为派生时间上界；含复位尾部的区间均满足$s_\iota\ge0,e_\iota\le B$。

将区间平移$Bu_\iota$，令$\epsilon_{\iota\iota'}=2-b_\iota-b_{\iota'}\in\{0,1,2\}$为未启用区间数，并以$\vartheta_{\iota\iota'}\in\{0,1\}$选择平移后的先后次序，互斥可写为
\begin{equation*}
\begin{aligned}
s_{\iota'}+B(u_{\iota'}-u_\iota)&\ge e_\iota-B(K_\rho+1)(1-\vartheta_{\iota\iota'}+\epsilon_{\iota\iota'}),\\
s_\iota-B(u_{\iota'}-u_\iota)&\ge e_{\iota'}-B(K_\rho+1)(\vartheta_{\iota\iota'}+\epsilon_{\iota\iota'}).
\end{aligned}
\end{equation*}
两项占用启用且单元编号相同时，$\vartheta_{\iota\iota'}=1$表示$\iota$先于$\iota'$，取0表示反向。编号不同时，按编号大小选择平移后的次序，原时间区间可以重叠；未启用项由$\epsilon_{\iota\iota'}$放松。该二元量用于同资源单元互斥，与跨LP取片分界$\theta_{j\ell}$不同。允许单元集合互不相交的占用对不需要互斥行。机械手动作的次序与换位约束仍单独保留；两腔间移动时间相同时，可用腔室编号差的正、负两条线性下界表示移动条件。''')

swap('记$G=|\\{(j,\\ell):N_{j\\ell}>0\\}|$，',
     '记$G=|\\{(j,\\ell):N_{j\\ell}>0\\}|$为非空任务--LP组合的数量，$|\\cdot|$表示集合元素个数，')
swap('令$\\mathcal F_k$为第$k$层固定的离散变量索引集合，',
     '以$t\\in\\{1,\\ldots,5\\}$表示SPBS层号，令$\\mathcal F_t$为该层固定的离散变量分量索引集合，')
s=s.replace(r'd\in\mathcal F_k',r'd\in\mathcal F_t')
# No change to meaning: call out that these symbols denote deterministic maps.
swap('映射为变量赋值$\\xi^0=\\mathsf{Enc}(\\mathcal S^0)$。',
     '映射为变量赋值$\\xi^0=\\mathsf{Enc}(\\mathcal S^0)$，其中上标0表示初始排程和初始赋值，$\\mathsf{Enc}$为物理排程到模型赋值的确定映射。')
swap('执行$\\mathcal S^\\star=\\mathsf{Dec}(\\xi^\\star)$。',
     '执行$\\mathcal S^\\star=\\mathsf{Dec}(\\xi^\\star)$，其中$\\mathsf{Dec}$为最终赋值到具体晶圆排程的确定映射，上标$\\star$表示算法最终保留的结果。')

assert s[:s.index(r'\section{双源混流旋转腔组合设备调度模型}')]==original[:original.index(r'\section{双源混流旋转腔组合设备调度模型}')]
assert s[s.index(r'\section{计算实验与结果分析}'):]==original[original.index(r'\section{计算实验与结果分析}'):]
assert not any(x in s for x in ('匿名','模型4','模型2'))
path.write_text(s,'utf-8')
(HERE/'edit_scope.json').write_text(json.dumps(dict(abstract_and_introduction_unchanged=True,
    experiments_conclusion_references_unchanged=True,solver_files_changed=False,
    primary_index_rules={'j':'Pjob','k':'product index within Pjob','ell':'LP','p':'pair','r':'pair member',
                         'c':'chamber','q':'cycle','rho':'resource class','u':'resource unit','tau':'physical dummy'}),indent=2),'utf-8')
print('Updated definitions and indices; abstract, introduction and experiments preserved.')

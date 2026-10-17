from pathlib import Path
import re,json,shutil,hashlib,difflib

HERE=Path(__file__).resolve().parent
PAPER=HERE.parents[1]
source=PAPER/'JMS_Review_CN.tex'
explanation=PAPER/'MODEL_EXPLANATION_CN.md'
for path in [source,explanation,PAPER/'JMS_Review_CN.pdf',PAPER/'output/pdf/MODEL_EXPLANATION_CN.pdf']:
    backup=HERE/(path.stem+'.before'+path.suffix)
    if not backup.exists(): shutil.copy2(path,backup)
old=(HERE/'JMS_Review_CN.before.tex').read_text(encoding='utf-8')
s=old

inputs=[
r'$\mathcal W$为产品晶圆集合，$w$为产品编号；$\mathcal I$为晶圆路线任务集合，$i$为任务编号，包括产品路线和辅助晶圆每次借用路线。',
r'$\mathcal S=\{A,V\}$为来源区域集合，$s$为区域索引；$A,V$分别为大气区、真空区。$\sigma=0/1$表示单源/双源；$\chi_{is}=1$表示任务$i$来自区域$s$。',
r'$\ell_w$为产品$w$所在LP编号；$m_w\in\{\zeta,\psi\}$为其给定工艺模式；$\mathcal C(m)$为可执行加工类型$m$的腔室集合。',
r'产品晶圆总数，$N=|\mathcal W|=N_{\zeta}+N_{\psi}$，不含辅助晶圆。',
r'$\mathcal P$为候选PW对集合，$p$为对编号；$\mathcal M=\{\zeta,\psi,\mathrm{cl}\}$为加工类型集合，$m$为类型索引；三种标签依次为$4\times1$、$2\times2$生产和清洁。',
r'$\mathcal C=\{\mathrm{CH1,CH2}\}$为工艺腔室集合，$c$为腔室编号；$\mathcal L=\{1,2\}$为腔室两侧的PW对位置集合，$l$为侧位编号。',
r'$\mathcal P^{\zeta}$、$\mathcal P^{\psi}$分别为采用$4\times1$、$2\times2$工艺的含产品PW对集合，由成员与类型选择导出；上标为工艺标签。',
r'$\mathcal B_c$为腔室$c$的$4\times1$生产批次集合（索引$b$）；$\mathcal K_c$为该腔$2\times2$产品对链位置集合（索引$k$）；$\mathcal Q_c$为候选加工周期集合（索引$q$）。',
r'$N_{\zeta},N_{\psi}$分别为两种工艺的产品数量，下标为工艺标签；$T$为全设备生产周期总数上界；$J_{\max}$为全设备清洁总次数上界。',
r'$P_{\max}$为全批次候选PW对容量；$Q_{\max}$为全设备加工周期总数上界，并用作每腔候选容量；下标$\max$表示上界，加工周期含生产与清洁。',
r'单腔自初始洁净状态或上次清洁后累计生产周期数的上限；允许在$H-1$个周期后为紧随清洁的$2\times2$生产提前清洁。',
r'$\mathcal O$为候选物理动作集合，$o,o^{\prime}$为两个动作的编号；$\mathcal A$为动作先后弧集合，$(o,o^{\prime})$表示动作$o$先于$o^{\prime}$。',
r'$\mathcal A^{\rm int}$为共同腔内先后弧集合，上标int表示腔内；$\mathcal A_{is}(\gamma)$为任务$i$从区域$s$供回晶圆时、在搬运选择$\gamma$下启用的路线弧集合。',
r'$d_o$为动作$o$的给定持续时间；$r_c$为腔室$c$半周旋转的给定持续时间，单位均为s。',
r'$\delta_{oo^{\prime}}$为先后动作$o,o^{\prime}$之间的最小间隔；$\rho^r_{oo^{\prime}}$为资源$r$从$o$转至$o^{\prime}$所需换位或复位时间；$\rho^{\rm VTR}_{cc^{\prime}}$为VTR从腔室$c$至$c^{\prime}$的移动时间。',
r'$M$为条件时间约束使用的有效大常数；$\overline R_{wr}$为晶圆$w$在受限设备或路线区段$r$内的最大驻留时间，单位为s。',
r'$\overline T$为排程时刻的有效上界；$d_m$为加工类型$m$的固定持续时间，单位为s；上横线表示上界。',
r'路线事件标签，依次表示源端取片、放至AL、从AL取回、放入上装载锁；在$s_{wa},e_{wa}$中作为动作阶段索引$a$的取值。',
r'$\mathcal E_c$为腔室$c$的清洁区段集合，$e$为区段编号；$\mathcal V_c$为该腔生产任务集合，$v$为任务编号，任务为一个$4\times1$批次或$2\times2$生产周期。',
r'$\nu$为清洁任务的阶段索引，取FL、BL、P、BU、FU，依次表示前装、后装、清洁处理、后卸、前卸；其中P为阶段标签。',
r'$\mathcal J_c^D$为分配至腔室$c$的辅助晶圆借用需求集合，$j=(p,r)$表示对$p$第$r$个成员位的需求，上标D表示辅助需求；$\mathcal T_c$为该腔可访问的实体辅助晶圆集合，$\tau$为实体编号。',
r'共享物理资源集合，$r$为资源编号，涵盖机械手执行机构、承片手、模块槽位、腔室及实体辅助晶圆。',
r'资源占用任务$o$允许选择的物理单元集合，$\ell$为单元编号；VTR的$D_1,D_2$表示两只脏手，$C_1,C_2$表示两只洁净手，数字为同类手编号。',
r'$\operatorname{in}(w,r)$、$\operatorname{out}(w,r)$分别给出晶圆$w$进入、离开受限区段$r$的动作编号，用于引用相应起止时刻。',
r'由配对、分腔、周期、完整晶圆路线及资源约束定义的联合可行域；其元素为完整变量向量$\xi$。',
r'$\mathcal D_{\rm fix}$为第二阶段固定分量的索引集合（索引$d$）；$\mathcal Q^w$为等待项集合（索引$\alpha$，上标$w$为等待标签）；$\mathcal I_h$为节拍差分的有效三元组$(c,e,q)$集合。',
r'$\lambda_1,\lambda_2,\lambda_3,\lambda_4$依次为总等待、最大单项等待、节拍变化、软等待超额的非负权重；数字下标表示目标项类别。',
r'$\bar\omega_\alpha$为等待项$\alpha$的软上限；$\varepsilon_C$为第二阶段产品完工时间上界的非负容差，下标C表示完工时间，单位均为s。'
]
variables=[
r'$a_{wpr}=1$表示产品$w$占PW对$p$的成员位$r$；$d_{pr}=1$表示该位置由辅助晶圆占据；$v_p=1$表示启用对$p$。$r\in\{0,1\}$为对内两个成员位，取0分别表示对应选择未发生。',
r'$\mu_{pm}=1$表示对$p$采用加工类型$m$；$z_{pc}=1$表示对$p$分配至腔室$c$，否则为0；产品自身配方$m_w$为输入。',
r'$B_p=1$表示对$p$至少含一片产品；$B_p^{\psi}=1$表示该对含采用$2\times2$工艺的产品，否则为0；上标$\psi$为工艺标签。',
r'$U_{cq}=1$表示腔室$c$的第$q$个候选加工周期启用；$K_{cqm}=1$表示该周期采用类型$m$；$X_{pcq}=1$表示对$p$参加该周期，否则为0。',
r'$X^P_{pcq}=1$表示含产品对$p$参加腔室$c$的周期$q$，上标P表示产品；$A^{\psi}_{pcq},Z^{\psi}_{pcq}=1$分别表示该周期为$2\times2$含产品对$p$的首次、末次工艺处理，否则为0。',
r'$b_o=1$表示候选动作或资源占用任务$o$启用，$b_o=0$表示不启用；其取值由布局及可选搬运关系联结。',
r'$s_o$、$e_o$分别为动作或占用任务$o$的开始、结束时刻，单位s；动作满足$e_o=s_o+d_ob_o$，未启用动作的两时刻为0。',
r'$x=1$表示选择当前讨论的个体动作与参考阶段的联结，$x=0$表示不选择；$s^{\rm ref},e^{\rm ref}$为该参考阶段的起止时刻，上标ref为参考标签。',
r'$\gamma^{\rm early}_p=1$表示单源产品--辅助对$p$中辅助晶圆先行直接入锁；$\gamma^{\rm late}_p=1$表示产品放至AL后再取辅助晶圆；上标early、late标记两种入片方式，否则为0。',
r'$s_v,e_v$为生产任务$v$的起止时刻；$s_{wa},e_{wa}$为晶圆$w$在路线动作阶段$a$的起止时刻，单位s；此处$w$可指产品或某次借用的辅助晶圆。',
r'$A_{pcq}=1$表示周期$(c,q)$是对$p$在腔室$c$的首个参与周期；$Z_{pcq}=1$表示该周期是其末个参与周期，否则为0。',
r'$S_{cq},E_{cq}$为腔室$c$第$q$个加工周期的开始、结束时刻（s）；$n_{cq}$为该周期结束后自初始洁净状态或最近清洁以来的生产周期数，取$0,\ldots,H$。',
r'$f_{pcq}=1$表示对$p$位于腔室$c$周期$q$的访问前侧；$\kappa_{cq}=1$表示该周期保留上一周期的一个对；$\upsilon_{cq}=1$表示该周期后两对全部退出，否则为0。',
r'$s^{\rm load}_p,e^{\rm load}_p$为对$p$装入所选腔室的起止时刻；$s^{\rm unload}_p,e^{\rm unload}_p$为该对卸出的起止时刻，单位s；上标load、unload为装、卸标签。',
r'腔室$c$周期$q$对应半周旋转的起止时刻（s）；$s$表示开始、$e$表示结束；上标rot$-$、rot$+$分别标记周期前、周期后旋转，正负号不表示数值正负。',
r'$z_{ce}=1$表示腔室$c$的清洁区段$e$启用；$a^{\zeta}_{cbe}=1$表示该腔$4\times1$批次$b$属于区段$e$；$a^{\psi}_{cqe}=1$表示该腔$2\times2$生产周期$q$属于区段$e$，否则为0。',
r'$a_{vce}=1$表示生产任务$v$属于腔室$c$的区段$e$，否则为0；$N_{ce}$为该区段的生产周期数；$q^{\rm cl}_{ce}=1$表示该区段后启用清洁，否则为0，此处$q$为变量名。',
r'$s^{\rm cl}_{ce},e^{\rm cl}_{ce}$为腔室$c$区段$e$后完整清洁任务的起止时刻；$s^{\rm cl,\nu}_{ce},e^{\rm cl,\nu}_{ce}$为其中阶段$\nu$的起止时刻（s）；上标cl表示清洁。',
r'$x^{\zeta}_{pcbl}=1$表示对$p$位于腔室$c$的$4\times1$批次$b$的侧位$l$；$x^{\psi}_{pck}=1$表示该对占该腔$2\times2$链位置$k$，否则为0；二者由周期及侧位导出。',
r'$g_{j\tau}=1$表示借用需求$j=(p,r)$使用实体辅助晶圆$\tau$，否则为0；需求编号与实体编号分别表示一次使用任务和一片可复用晶圆。',
r'$h_{o\ell}=1$表示占用任务$o$选择单元$\ell$，否则为0；$\gamma_{pa}=1$表示对$p$在允许的同地点原子搬运段$a$上同步搬运。特殊下标$a=\mathrm{in}$时表示单源产品--辅助对随行入片选择。',
r'当动作$o,o^{\prime}$争用资源$r$的同一单元时，$y^r_{oo^{\prime}}=1$表示$o$先于$o^{\prime}$，取0表示反向次序；上标$r$标识资源，撇号区分两个动作。',
r'$C_w=e_{w,\mathrm{return}}$为产品$w$返回原LP的结束时刻；$C_{\max}$为所有产品回片时刻的共同上界，第一阶段最小化后取其最大值（s）；return、max为语义标签。',
r'$\xi$为全部决策和辅助变量的向量，$\xi_d$为第$d$个分量；$\widehat\xi$为第一阶段当前最好可行解，$\widehat\xi_d$为其相应分量；$\widehat C$为该解产品完工时间，带帽量在第二阶段作为常量。',
r'$\omega_\alpha$为等待项$\alpha$的非负等待时长；$L_{\rm sum}$为所有纳入评价的等待之和；$L_{\max}$为最大单项等待的上界（s）；sum、max分别为求和、最大值标签。',
r'腔室$c$、清洁区段$e$内生产周期$q$的开始时刻（s），与相应物理动作开始时刻相同；三重下标依次定位腔室、区段、周期。',
r'在腔室$c$、清洁区段$e$中，以生产周期$q$为中心的后一个开始间隔减去前一个开始间隔（s）；仅对$(c,e,q)\in\mathcal I_h$定义，可正可负。',
r'腔室$c$、区段$e$、生产周期$q$对应的$|\Delta_{ceq}|$的非负上界（s）；用于线性表示该三周期组的节拍变化。',
r'等待项$\alpha$超出软上限$\bar\omega_\alpha$的非负超额上界（s），满足$\eta_\alpha\ge\max\{0,\omega_\alpha-\bar\omega_\alpha\}$。',
r'第二阶段目标表达式，由总等待、最大单项等待、节拍变化和可选软等待超额按$\lambda_1,\ldots,\lambda_4$加权构成。'
]
assert len(inputs)==28 and len(variables)==30
tables=re.findall(r'\\begin\{table\*\}.*?\\end\{table\*\}',s,re.S)[:2]
records=[]
for index,(table,definitions) in enumerate(zip(tables,[inputs,variables]),1):
    begin=table.index('\\midrule\n')+len('\\midrule\n')
    end=table.index('\\bottomrule')
    rows=table[begin:end].strip().splitlines()
    assert len(rows)==len(definitions)
    revised=[]
    for row,definition in zip(rows,definitions):
        symbol,kind,_=row.removesuffix(r'\\').split(' & ')
        revised.append(symbol+' & '+kind+' & '+definition+r'\\')
        records.append({'table':index,'symbol':symbol,'kind':kind,'definition':definition})
    new=table[:begin]+'\n'.join(revised)+'\n'+table[end:]
    new=new.replace(r'\begin{table*}[t]',r'\begin{table*}[!t]')
    new=new.replace('C{0.20\\textwidth}C{0.16\\textwidth}C{0.43\\textwidth}',
                    'C{0.23\\textwidth}C{0.10\\textwidth}C{0.61\\textwidth}')
    s=s.replace(table,new)

index_note=r'''下标按所指对象解释：$w$为产品晶圆或明确指定的晶圆使用任务，$i$为完整路线任务，$p$为PW对，$c$为腔室，$q$为该腔候选加工周期，$b$为$4\times1$生产批次，$k$为$2\times2$产品对链位置，$e$为清洁区段，$v$为生产任务，$o$为动作或资源占用任务，$\alpha$为等待项。$r=0,1$在$a_{wpr},d_{pr}$中表示对内成员位，而$r\in\mathcal R$在$y^r_{oo'}$中表示资源；$l\in\mathcal L$为腔室侧位，$\ell\in\Gamma_o$为物理手或槽位，二者不混用。清洁需求$j=(p,r)$与实体身份$\tau$分别描述一次借用和一片可复用辅助晶圆。撇号如$o',c'$仅区分同类对象，不表示求导。

下标或上标中的$\zeta,\psi,\mathrm{cl}$分别标记两种生产工艺与清洁；load、unload、rot$\pm$、ref、return、sum、max分别标记装载、卸载、周期前后旋转、参考阶段、返回、求和和最大值。它们是语义标签。时间变量和时间参数的单位统一为s；二元指示量的1表示定义的事件或选择成立，0表示不成立。表中派生集合$\mathcal P^{\zeta},\mathcal P^{\psi}$及区段、批次、链位置随排程结构确定，不作为独立于配对和周期的输入选择。'''
anchor='\n\n\\begin{table*}[t]'
pos=s.index(anchor,s.index('表~\\ref{tab:symbol-cn-a}'))
s=s[:pos]+'\n\n'+index_note+s[pos:]

def before(label,text):
    global s
    marker='\\label{'+label+'}'
    pos=s.rfind(r'\begin{equation}',0,s.index(marker))
    s=s[:pos]+text+'\n\n'+s[pos:]
def after(label,text):
    global s
    pos=s.index(r'\end{equation}',s.index('\\label{'+label+'}'))+len(r'\end{equation}')
    s=s[:pos]+'\n\n'+text+'\n\n'+s[pos:]

after('eq:spbs-fix-cn',r'此处$j$为MILP标量变量$x_j$的索引，$q\in\{1,\ldots,5\}$为初始化松弛层级；$\ell_j^{(q)},u_j^{(q)}$分别为该层级下变量$x_j$的下界和上界，$\widehat x_j$为骨架给定值。$\mathcal F_q$是固定变量索引集合，区别于第2节的联合可行域$\mathcal F$；此处$q$不表示加工周期。')
after('eq:role-mass-cn',r'在式~\eqref{eq:role-mass-cn}中，$i$索引候选割，$j$索引原MILP的标量变量$x_j$，$a_{ij}$为第$i$条割中$x_j$的系数；$g\in\mathcal G$索引变量角色，$p_{ig}$为割$i$在角色$g$上的绝对系数质量占比，$\varepsilon>0$为分母稳定常数。$\mathcal G$包含二元、一般整数、目标活跃连续、连续辅助和其他五类；$B,I,C_{\rm obj},C_{\rm aux}$为前四类的标签。这里的$a_{ij}$表示线性不等式系数，区别于第2节产品成员指示量$a_{wpr}$。')
after('eq:gated-encoding-cn',r'下标$i$定位候选割；上标$H,R$分别标记HEM通用特征支路与角色特征支路。$\widetilde x_i$为$x_i$经层归一化$\operatorname{LN}$后的向量，$\widetilde x_i^{H},\widetilde x_i^{R}$为其两组分量；$u_i^{H},u_i^{R}$为投影后的128维支路向量，$g_i$为128维门值，$z_i$为融合结果。$W_H,W_R,W_g$分别为两支路投影和门控的权重矩阵，$b_H,b_R,b_g$为相应偏置；下标H、R、g表示网络部件。$\sigma(\cdot)$为sigmoid函数，$\odot$为逐元素乘法。上述权重和偏置在训练中学习、正式推理时固定；此处$\sigma$与第2节来源参数$\sigma$的含义不同。')
after('eq:lstm-encoding-cn',r'$t$为分离轮次，$m_t$为该轮截断后的候选数，$i=1,\ldots,m_t$为编码顺序。$h_i,c_i$分别为处理候选$i$后的隐藏状态和记忆状态；$h_{i-1},c_{i-1}$为前一个编码位置的状态，二者均为128维向量。此处$c_i$为网络状态，不是工艺腔室编号$c$。')
s=s.replace('在低层第$r$个解码步，解码器根据上一时刻状态$d_r$和全部编码状态$h_i$',
    '在低层第$r$个解码步，解码器根据已选前缀形成的状态$d_r$和全部编码状态$h_i$')
after('eq:pointer-decoding-cn',r'下标$r$为解码步，$i$为候选割编号；$a_{ri}$为glimpse注意力分数，$\alpha_{ri}$为对候选维$i$归一化后的注意力权重，$\bar h_r$为该步候选状态的加权摘要，$b_{ri}$为pointer选择分数。$W_e,W_d$分别投影编码状态与解码状态，$U_e,U_g$分别投影编码状态与glimpse摘要，$v_g,v_p$分别为两种评分的可训练向量；下标e、d、g、p标记网络部件。$M_{ri}$为候选掩码，区别于时间大常数$M$；$i_r$为第$r$步选中的割编号，$i_{1:r-1}$为此前有序前缀，$S_t$为第$t$轮编码后的候选状态。$P(\cdot\mid\cdot)$表示条件选择概率。')
after('eq:beam-score-cn',r'$b$为一条父束前缀，$j$为尚未选择的候选割编号，$b\oplus j$表示在前缀末端追加$j$；$L_r$为长度$r$前缀的联合对数概率，初始空前缀满足$L_0=0$。$B$表示束宽，$\mathcal B_r$为第$r$步保留的前缀集合，二者均不表示生产批次。')
after('eq:policy-cn',r'$\theta$为策略网络参数，$k_t$为第$t$轮保留的割数，$i_{1:k_t}$为长度$k_t$的有序割序列；$\pi_\theta^H$为高层数量策略，$\pi_\theta^L$为给定状态与前缀的低层选择策略。上标H、L在此分别表示高层、低层；$\rho_t$为高层输出映射得到的保留比例，下标$t$均表示分离轮次。')
after('eq:submodular-cn',r'式~\eqref{eq:submodular-cn}的$t$表示分离轮次，$S$为扩展池$\mathcal R_t$内已选割集合，$i$为已选割编号，$u$为池内被代表候选的编号，$g$为角色类别。$q_i$为割$i$的即时结构质量，$r_i$为其pointer顺序先验，$d_g$为角色$g$的需求占比，$s_{ui}$为候选$u$与$i$的截断相似度，$F_t(S)$为本轮集合$S$的代理效用。$A_t$为固定策略锚点集合，$U\subseteq\mathcal R_t\setminus A_t$为待补全子集；残余函数$f(U)$度量相对锚点的新增效用。此处$q_i,r_i,d_g$均为选割评价量，不是加工周期、物理资源或动作时长。')
after('eq:reinforce-cn',r'$J$为期望回报目标，$\nabla_\theta J$为其关于参数$\theta$的梯度，帽号表示样本估计。此处$B$为训练轨迹批量大小，$b=1,\ldots,B$为轨迹编号；$R_b$为轨迹$b$的回报，$\tau_b$为该轨迹首次有效候选集上的采样割序列，$\pi_\theta(\tau_b)$为相应策略概率。$\bar R$为本批回报均值，$\bar R_{\rm EMA}$为指数移动平均基线，下标EMA为方法标签。这里的$B,b,\tau_b$分别区别于束宽、父束和实体辅助晶圆身份。')
after('eq:pdi-gap-cn',r'本节$t\in[0,T]$为一次求解内经过的时间，$T$为PDI计时窗长度（s），区别于第2节生产周期容量上界$T$；$P(t),D(t)$分别为该时刻的原始上界、对偶下界，$\Delta(t)$为两界绝对差，$m(t),M(t)$为两界绝对值的较小值、较大值。$G_{\rm end}$为停止时的相对gap，$g_{\rm PDI}(t)$为积分使用的瞬时gap；下标end、PDI是指标标签，PDI的单位为百分数乘秒。')
s=s.replace('预设PDI析因模型的$R^2=0.998$。','预设PDI析因模型的决定系数$R^2=0.998$，其中上标2为平方记号。')
s=s.replace('所选$k_t$条割依次按锚点原顺序和贪心补全顺序加入当前LP。',
    '最终有序割序列记为$S_t^\star$，上标$\star$标记本轮输出；所选$k_t$条割依次按锚点原顺序和贪心补全顺序加入当前LP。')
s=s.replace('并在预设分析族内作Holm校正。限时运行保留在汇总中，',
    '并在预设分析族内作Holm校正；统计检验中的$p$表示$p$值。限时运行保留在汇总中，')

geteq=lambda text:re.findall(r'\\begin\{equation\}.*?\\end\{equation\}',text,re.S)
assert len(geteq(s))==42 and geteq(s)==geteq(old)
assert re.findall(r'\\label\{[^}]+\}',s)==re.findall(r'\\label\{[^}]+\}',old)
source.write_text(s,encoding='utf-8',newline='\n')

md=(HERE/'MODEL_EXPLANATION_CN.before.md').read_text(encoding='utf-8')
# Update each existing appendix entry in place, retaining its individual numerical example.
for table in (1,2):
    subset=[record for record in records if record['table']==table]
    for row,record in enumerate(subset,1):
        pattern=rf'(\*\*表{table}-{row:02d}[^\n]*\*\*\n\n\*\*类型与定义。\*\* )[^\n]+'
        md,count=re.subn(pattern,lambda m:m[1]+record['kind']+'；'+record['definition'],md)
        assert count==1,(table,row)
old_hash=re.search(r'SHA-256前16位为 `([^`]+)`',md)[1]
new_hash=hashlib.sha256(source.read_bytes()).hexdigest()
md=md.replace(old_hash,new_hash[:16])
glossary='## 下标、上标与索引的逐项读法\n\n'+index_note.replace('表中','正文符号表中')+'\n\n'
glossary+=r'''**成员变量的完整读法。** $a_{wpr}$读作“产品晶圆$w$是否位于候选PW对$p$的第$r$个成员位”。例如$a_{W1,p3,0}=1$表示W1进入p3的第0位；0表示这项成员关系未选择。$w$不是工序，$p$不是时刻，$r$不是机械手。

**周期变量的完整读法。** $X_{pcq}=1$表示“PW对$p$参加腔室$c$的第$q$个加工周期”。例如$X_{p4,CH2,2}=1$表示p4参加CH2的周期2；其含义不是p4由第2只手搬运。$S_{cq}$只定位该周期的开始时刻，具体对的成员由$a_{wpr}$另行描述。

**辅助身份的完整读法。** $g_{j\tau}=1$表示需求$j$借用实体辅助晶圆$\tau$；$j=(p,r)$同时定位“哪个对、哪个成员位”。例如$g_{(p3,0),A1}=1$表示p3第0位借用A1，其他需求仍可在归还后借用同一A1。

**不要只按字母猜含义。** 在选割公式中，$a_{ij}$是“候选割$i$中原MILP变量$x_j$的系数”。$i$是割编号、$j$是变量编号，两者都不是晶圆工序。系数可以为负或非整数，不能按二元成员指示量$a_{wpr}$理解。

'''
algo_notes=[]
for label in ['eq:spbs-fix-cn','eq:role-mass-cn','eq:gated-encoding-cn','eq:lstm-encoding-cn',
              'eq:pointer-decoding-cn','eq:beam-score-cn','eq:policy-cn','eq:submodular-cn','eq:reinforce-cn','eq:pdi-gap-cn']:
    pos=s.index(r'\end{equation}',s.index('\\label{'+label+'}'))+len(r'\end{equation}')
    paragraph=s[pos:].strip().split('\n\n')[0]
    number=next(i+1 for i,e in enumerate(geteq(s)) if '\\label{'+label+'}' in e)
    paragraph=re.sub(r'式~\\eqref\{[^}]+\}',f'式（{number}）',paragraph)
    algo_notes.append(f'**式（{number}）的索引与部件标签。** '+paragraph)
glossary+='### 算法与指标公式中的下标\n\n'+'\n\n'.join(algo_notes)+'\n\n'
md=md.replace('## 阅读起点：模型究竟在决定什么',glossary+'## 阅读起点：模型究竟在决定什么')
md=md.replace('本轮更新未改变投稿正文、实验结果或模型代码。','本轮同步补充投稿正文与本说明的符号、下标释义，公式、实验结果与模型代码未改变。')
explanation.write_text(md,encoding='utf-8',newline='\n')
numbers={re.search(r'\\label\{([^}]+)\}',e)[1]:i+1 for i,e in enumerate(geteq(s))}
(HERE/'equation_mapping.json').write_text(json.dumps({'manuscript_sha256':new_hash,'equations':numbers,'symbol_rows':[28,30]},ensure_ascii=False,indent=2),encoding='utf-8')
(HERE/'symbol_definitions.json').write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding='utf-8')
(HERE/'revision.diff').write_text(''.join(difflib.unified_diff(old.splitlines(True),s.splitlines(True),fromfile='before',tofile='after')),encoding='utf-8')
print('Expanded 58 symbol rows and index definitions; all 42 equations unchanged.')

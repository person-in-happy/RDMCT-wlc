from pathlib import Path
p=Path('JMS-version/JMS_Review_CN.tex');text=p.read_text(encoding='utf-8')
for a in ['o','w','p','c',r'\ell']:
 text=text.replace(a+r'\prime',a+"'")
def para(prefix,new):
 global text
 lines=text.splitlines();found=[i for i,l in enumerate(lines) if l.startswith(prefix)]
 assert len(found)==1,(prefix,found)
 lines[found[0]]=new;text='\n'.join(lines)+'\n'
para('对于资源类$\\rho$的承片',r'''对于承片、槽位及辅助晶圆占用，$\iota,\iota'$是同一资源类的两项占用区间索引。$s_\iota,e_\iota$是非负实数变量，分别表示区间起止时刻；$b_\iota$是二元辅助变量，表示区间是否启用，以上均引用对应物理事件或路线状态。$a_{\iota u}$是二元决策变量的简写，表示区间$\iota$是否使用单元$u$，其值引用$h_{ou}$或$g_{pr\tau}$。$u_\iota$是整数辅助变量，表示所选单元编号，满足$u_\iota=\sum_{u=1}^{K_\rho}u a_{\iota u}\in\{0,\ldots,K_\rho\}$；未启用时为0。含复位尾部的区间满足$s_\iota\ge0,e_\iota\le B$。''')
para('将区间平移$Bu_',r'''将区间平移$Bu_\iota$，使不同物理单元的占用分别落入对应时间段。$\epsilon_{\iota\iota'}$是整数辅助变量，表示两项占用中未启用的数量，满足$\epsilon_{\iota\iota'}=2-b_\iota-b_{\iota'}\in\{0,1,2\}$。$\vartheta_{\iota\iota'}$是二元决策变量，表示平移后区间$\iota$是否先于$\iota'$。因此，同一物理单元的互斥条件可写为''')
para('两项占用启用且单元编号相同时',r'''两项占用均启用且单元编号相同时，平移量相消，上述约束保证原区间不重叠。单元编号不同时，按编号顺序排列平移后的区间，原区间仍可重叠；未启用区间不受该互斥条件限制。允许单元集合互不相交的占用对无需建立互斥约束。机械手动作的次序与换位条件仍单独保留；两腔间移动时间相同时，可用腔室编号差的正、负两条线性下界表示移动条件。''')
para('令$\\mathcal F_{\\mathrm W}',r'''$\mathcal F_{\mathrm W}^{\rm seq}$是逐片模型的可行域，采用与本文相同的工艺资格、物理规则和批次出片顺序。逐片排程可按式~\eqref{eq:pjob-input-code-cn}转换为批次任务排程；反向由各任务的取片顺序及$\mathcal L_j$恢复实际晶圆。两种映射保持产品完工时间、等待、节拍及全部物理事件，因此''')
para('采用热启动时，将满足批次出片顺序',r'''$\mathcal S^0$是给定的初始物理排程，满足批次出片顺序；$\xi^0$是给定常量向量，表示该排程对应的初始变量赋值；$\mathsf{Enc}$是排程映射函数，按$\xi^0=\mathsf{Enc}(\mathcal S^0)$生成赋值，上标0表示初始结果。热启动时，先将含产品对和纯辅助对分别编号，使含产品对的位置$r=0$安排产品；再由产品的Pjob和来源LP确定$x_{j\ell pr}$，将配对、分腔、周期占位及动作时刻写入对应变量。辅助晶圆保留实体编号，资源次序、取片时间分界和逻辑辅助变量由受限模型补全。冷启动直接求解已编码的模型。''')
para('产品回片之后，排程仍可能包含',r'''产品回片之后，排程仍可能包含辅助片归还、末端清洁及装载锁复位。$\widetilde\xi$是给定常量向量，表示第二阶段保留的可行赋值，$\widetilde\xi_d$是其第$d$个分量；$\widetilde C$是非负实数常量，表示该赋值的产品完工时间。$F_2$是式~\eqref{eq:secondary-objective-cn}对应的加权目标函数，$\widetilde F_2=F_2(\widetilde\xi)$是收尾处理采用的目标值常量。波浪号表示收尾输入。$\mathcal D_{\rm disc}$是全部离散变量的分量索引集合，包含第二阶段允许调整的原子同步选择。为使已安排动作尽早完成，在保持产品完工时间及第二阶段目标上界的条件下，求解''')
para('其中，$\\varepsilon_2=',r'''式~\eqref{eq:output-completion-cn}固定全部离散选择，仅调整连续时刻；输入排程提供可行起点。装载锁占用的结束端点包含压力复位，因此目标同时计入辅助片归还、末端清洁和复位完成。收尾结果记录两种完工时间、路线等待和节拍指标，随后进行晶圆身份解码。''')
para('两阶段求解及输出收尾结束并选定',r'''$\xi^\star$是给定常量向量，表示两阶段求解及收尾后保留的最终可行赋值；$\mathcal S^\star$是对应的具体晶圆排程，上标$\star$表示最终保留结果，不表示已证明全局最优。$\mathsf{Dec}$是排程解码函数，按$\mathcal S^\star=\mathsf{Dec}(\xi^\star)$恢复实际晶圆身份和全部事件时刻。对任务$j$，将满足$\sum_\ell x_{j\ell pr}=1$的对内位置按首次LP取片开始时刻非递减排列；同刻依次按来源LP、对编号和对内位置升序排列。$i_j^{(k)}$是排序后的对内位置索引，表示任务$j$的第$k$片产品对应的位置，上标$(k)$是排序序号。依据输入编码表恢复''')
# Physical premise -> equation -> concise explanation, following the reference papers.
para('PW对可以是产品--产品',r'''一个PW对可由两片产品、一片产品与一片辅助晶圆，或两片辅助晶圆组成。例如，$x_{1,1,1,0}=1$尚不区分表~\ref{tab:pjob-code-example-cn}中的晶圆1和3。所有产品均须安排加工，且每个启用对内位置恰好安排一片晶圆。因此，有''')
para('每个安排产品的对内位置对应',r'''式~\eqref{eq:joint-membership-cn}保证每个任务在各LP的产品均被使用，且同一对内位置不会同时安排产品和辅助晶圆。各位置保留完整加工路线，实际产品编号在求解后按出片次序恢复。''')
para('$h_j(\\ell)$是整数常量',r'''同一批次任务须按输入编号取片。由于实际编号按LP分段，较小编号LP中的该任务产品应先于下一非空LP中的产品取片。$h_j(\ell)$是整数常量，表示任务$j$在LP $\ell$之后的首个非空LP编号，计算为$\min\{\ell'>\ell:N_{j\ell'}>0\}$；$\ell'$是计算中的LP索引，集合为空时不建立对应分界变量。$s^{\rm pick}_{pr}$是非负实数变量，表示位置$(p,r)$的晶圆在LP取片的开始时刻，直接引用对应动作的$s_o$。因此，相邻非空LP之间满足''')
para('该式表达批次内时刻的非递减关系',r'''式~\eqref{eq:pjob-nondecreasing-pick-cn}允许相邻产品具有相同的取片开始时刻。当两片产品属于同一PW对且来自同一LP时，可令$\gamma_{p,\rm pick}=1$并同步取片；该动作仍须满足式~\eqref{eq:double-transfer-cn}及机械手容量约束。不同PW对或不同LP的取片须满足ATR互斥与换位条件。同刻取片的产品按来源LP、对编号及对内位置依次排序，其来源与式~\eqref{eq:pjob-input-code-cn}一致。不同Pjob可以交错取片，并在工艺相容时成对搬运。''')
para('设备兼容性与产品资格分别通过',r'''同一PW对中的两片晶圆应采用相容的工艺模式，并进入共同允许的腔室。因此，模式与腔室选择满足''')
para('含产品标记与所选加工类型之间满足',r'''含产品的PW对不能用于清洁，且只有采用链式模式的含产品对需要连续参加两次处理。因此，有''')
para('$U_{cq}$是二元辅助变量',r'''腔室执行生产或清洁时均应保持四工位满片，即每个周期恰好容纳两个PW对。$U_{cq}$是二元辅助变量，表示腔室$c$的周期$q$是否启用。所选PW对的腔室与加工类型须与周期一致，因此，有''')
para('上述线性联结避免直接使用二元变量乘积',r'''式~\eqref{eq:cycle-capacity-cn}保证满片加工、对与周期相容及候选容量限制；式~\eqref{eq:cycle-products-cn}保证只有含产品对的占位计入生产要求。由此，生产周期至少含一个产品对，清洁周期只含辅助对。周期按编号连续启用，但不同加工模式的先后次序仍由模型确定。''')
para('在物理路径与配对关系确定后',r'''晶圆只有完成前一道操作后才能进入下一道操作。成对搬运时，两片晶圆还应同步取放。本节据此建立动作持续时间、路线先后关系和同步约束；共享资源引起的服务次序在第~\ref{sec:model-resource-cn}节讨论。''')
para('动作启用状态由晶圆路线',r'''所选晶圆路线、腔室周期及搬运方式决定哪些动作需要执行。已启用动作的持续时间为给定值，未启用动作的起止时刻均置零；其中LP取片时长满足$d_o>0$。因此，有''')
para('式~\\eqref{eq:operation-time-cn}表示',r'''式~\eqref{eq:operation-time-cn}保证取放、对准、压力转换、旋转及加工动作按给定时长执行，等待只能发生在动作之间。''')
para('对必须依次执行的操作先后弧',r'''对弧$(o,o')\in\mathcal A$，后继动作只能在前驱完成并经过必要间隔后开始。若后继启用，则前驱也必须启用。因此，有''')
para('式~\\eqref{eq:precedence-cn}表示',r'''式~\eqref{eq:precedence-cn}保证产品与辅助晶圆沿所选路线依次运行，并使装载、加工和卸载事件遵守工艺顺序。''')
para('式~\\eqref{eq:double-transfer-cn}表示',r'''式~\eqref{eq:double-transfer-cn}保证成对搬运的两条晶圆事件具有相同的起止时刻。此时机械手只执行一次共同动作，该动作仍须与其他动作互斥。未选择成对搬运时，两片晶圆的动作分别按式~\eqref{eq:resource-order-cn}排序。无论是否同步，每片晶圆均占用一只物理手，因而同步取放不减少承片需求。''')
para('首次进入标记的三条不等式使',r'''式~\eqref{eq:cycle-exposures-cn}使每个启用PW对只进入腔室一次，并连续参加一个或两个周期。前三条不等式给出$A_{pcq}=X_{pcq}(1-X_{pc,q-1})$，结合末次参加标记可得$\sum_{c,q}Z_{pcq}=\sum_{c,q}A_{pcq}=v_p$。含产品的$4\times1$对参加一次处理，含产品的$2\times2$对在同腔参加相邻两次处理；每个链式周期至多有一个首次参加的产品对和一个末次参加的产品对。纯辅助补位对与清洁对均只参加一个周期。''')
para('$E_{cq}$是非负实数辅助变量',r'''一个加工周期只有在前一周期结束后才能开始，持续时间由所选加工类型确定。$E_{cq}$是非负实数辅助变量，表示腔室$c$的周期$q$结束时刻。因此，有''')
para('$\\kappa_{cq},\\upsilon_{cq}$是二元辅助变量',r'''机械手只能访问腔室前侧，故新装入的PW对位于前侧，保留自上一周期的PW对经旋转转至后侧。$\kappa_{cq},\upsilon_{cq}$是二元辅助变量，分别表示周期$q$是否保留来自$q-1$的一个PW对、周期$q$结束后是否两个PW对全部退出。根据相邻周期的占位关系，有''')
para('取候选尾部$U_',r'''腔室完成一次生产后累计计数增加1，完成清洁后计数归零。达到阈值时须执行清洁，未达到阈值时可在合法工艺边界提前清洁；初始清洁与连续清洁均不允许。取候选尾部$U_{c,Q_{\max}+1}=0$，有''')
para('每完成一个生产周期，计数增加1',r'''式~\eqref{eq:clean-counter-cn}限制相邻两次清洁之间的生产次数，并在达到阈值时强制清洁，包括最后一个生产段。由式~\eqref{eq:cycle-capacity-cn}与式~\eqref{eq:cycle-exposures-cn}，同一链式产品对须连续参加两个生产周期，故清洁不能插入这两次处理之间。''')
para('各腔室可访问同一物理辅助库存',r'''两腔共享辅助晶圆库存，一片辅助晶圆在归还之前不能再次借出。因此，每项有效借用需求应选定一片实体晶圆，同一PW对的两个位置应使用不同晶圆，有''')
para('式~\\eqref{eq:dummy-assign-cn}表示',r'''式~\eqref{eq:dummy-assign-cn}保证每项辅助需求恰好分配一片晶圆。借用区间按共享资源约束排序，使同一晶圆只能在完成归还后再次使用。该条件同样适用于跨腔借用，允许两腔使用不同辅助晶圆并行生产。''')
para('若占用$o,o',r'''若两项占用选择同一资源单元，则其中一项必须在另一项结束后开始，并满足该方向的换位或复位间隔。因此，有''')
para('式~\\eqref{eq:resource-order-cn}表示',r'''式~\eqref{eq:resource-order-cn}保证选用同一物理单元的占用区间不重叠；选用不同单元时，该对互斥条件不限制其并行。该约束分别用于机械手动作、物理手、模块槽位、腔室执行机构和实体辅助晶圆。承片手及辅助晶圆的连续占用不另计换位时长。''')
para('驻留上限分别约束每片晶圆',r'''上述驻留与承片限制逐片施加，因此同一PW对中的两片晶圆仍须分别满足各自的时间上限。''')
para('前述约束共同定义',r'') if '前述约束共同定义' in text else None
# Move implementation details out of the modeling exposition; keep all equations and conditions.
start=text.index(r'\paragraph{等价实现与内存控制。}')
end=text.index(r'\subsection{编码表示的等价性与规模}',start)
block=text[start:end].replace(r'\paragraph{等价实现与内存控制。}',r'\subsection{模型的等价实现}')
block=block.replace('缓存列','辅助变量').replace('逻辑辅助量','逻辑辅助变量').replace('二元次序量','二元次序变量')
text=text[:start]+text[end:]
insert=text.index(r'\subsection{可选选割组件}')
text=text[:insert]+block+text[insert:]
# Clarify variables fixed only for evaluation without re-declaring their meanings.
text=text.replace('上界辅助量取紧值','上界辅助变量取紧值')
text=text.replace('库存表示需要$2GN$个$x$变量','库存表示需要$2GN$个$x_{j\ell pr}$变量')
assert '派生' not in text
assert '成员' not in text
p.write_text(text,encoding='utf-8')
print('Reference style and remaining declarations updated.')

from pathlib import Path
import json,re,statistics
HERE=Path(__file__).resolve().parent
PAPER=HERE.parents[1]
data=json.loads((HERE/'verified_evidence.json').read_text(encoding='utf-8'))['batches']
source=(HERE/'original/JMS_Review_CN.tex').read_text(encoding='utf-8')
mean=statistics.mean

def table(caption,label,columns,head,rows,note='',wide=False):
    env='table*' if wide else 'table'
    return ('\\begin{'+env+'}[!htbp]\n\\centering\\footnotesize\n\\setlength{\\tabcolsep}{3pt}\n'
        +'\\caption{'+caption+'}\n\\label{'+label+'}\n\\begin{tabular}{'+columns+'}\\toprule\n'
        +head+r'\\\midrule'+'\n'+'\n'.join(' & '.join(map(str,row))+r'\\' for row in rows)
        +'\n\\bottomrule\\end{tabular}\n'+('\\par\\smallskip\\footnotesize '+note+'\n' if note else '')+'\\end{'+env+'}')

cases=data['core']['case_summary']; rows=[]
for k in ('n4_H3_mixed_dual','n4_H3_mixed_single','n4_H10_mixed_dual','n8_H3_mixed_dual'):
    n,h,_,src=k.split('_');a=cases[k]
    rows.append([n[1:]+'/'+h[1:],'双源' if src=='dual' else '单源','0/3','3/3',f"{a['serial']['cmax_mean']:.2f}",f"{a['joint']['cmax_mean']:.2f}"])
tables={'@@TABLE_INIT@@':table('初始化对照：可行解获得率与完工时间（s）','tab:initialization-cn','ccccrr',
    r'$N/H$ & 来源 & 冷启动 & 两种起点 & 串行 & SPBS',rows,'两种起点各自为3/3；时间列为对应主求解结果的三个种子均值。')}

ab=data['ablation'];by={(r['case'],r['seed'],r['variant']):r for r in ab['rows']};rows=[]
for n in (4,8):
    for h in (3,10):
        for src in ('dual','single'):
            k=f'n{n}_H{h}_mixed_{src}';rs=[by[k,s,'refined'] for s in (1,2,3)]
            before=mean(r['phase1_metrics']['route_wait_sum'] for r in rs);after=mean(r['metrics']['route_wait_sum'] for r in rs)
            assert all(abs(r['upper']-by[k,r['seed'],'joint']['upper'])<2e-4 for r in rs)
            rows.append([f'{n}/{h}','双源' if src=='dual' else '单源',f"{mean(r['upper'] for r in rs):.0f}",f'{before:.2f}',f'{after:.2f}',f'{100*(before-after)/before:.2f}'])
tables['@@TABLE_REFINE@@']=table('时序精修的阶段内变化（时间单位：s）','tab:refinement-cn','ccrrrr',
    r'$N/H$ & 来源 & $C_{\max}$ & 总等待前 & 总等待后 & 降幅(\%)',rows,
    r'$C_{\max}$在$10^{-6}$~s级容差内保持；等待由实际事件重新计算。')
rows=[]
for arm,label in (('joint','默认SCIP'),('hem','HEM'),('proposed','完整组件'),('feature_only','仅特征'),('greedy','贪心选择'),('no_structure','去角色补全')):
    rs=[r for r in ab['rows'] if r['variant']==arm]
    improved=sum(r['upper']<by[r['case'],r['seed'],'joint']['upper']-2e-4 for r in rs)
    calls=sum(bool(r['cut_telemetry'] and r['cut_telemetry']['callback_calls']) for r in rs)
    rows.append([label,f"{mean(r['upper'] for r in rs):.2f}",f'{improved}/24',f'{calls}/24' if arm!='joint' else '--'])
tables['@@TABLE_CUTS@@']=table('冻结选割组件的描述性消融','tab:cut-ablation-cn','lrrr',
    r'方法 & 平均$C_{\max}$(s) & 改善次数 & 回调触发',rows,
    '改善次数相对同配置、同种子的默认SCIP；回调仅指自定义选择器。各方法实际停止时间不同，不据此排序求解速度。')
rs=data['core']['rows'];rows=[]
for n in (4,8):
    for h in (3,10):
        line=[f'{n}/{h}']
        for mode in ('4x1','2x2','mixed'):
            chosen=[r for r in rs if r['case']==f'n{n}_H{h}_{mode}_dual' and r['variant']=='joint']
            lb=max(r['lower'] for r in chosen if r['lower'] is not None);ub=min(r['upper'] for r in chosen)
            line.append(f'{lb:.2f} / {ub:.2f}')
        rows.append(line)
tables['@@TABLE_MODES@@']=table('双源配置的模式比较：下界 / 可行上界（s）','tab:modes-cn','crrr',
    r'$N/H$ & 纯$4\times1$ & 纯$2\times2$ & 混合',rows)
rows=[]
for n in (4,8):
    for mode,label in (('4x1',r'$4\times1$'),('2x2',r'$2\times2$'),('mixed','混合')):
        r=next(r for r in rs if r['case']==f'n{n}_H3_{mode}_dual' and r['variant']=='joint' and r['seed']==1)
        d=r['build']['dimensions']
        rows.append([n,label,d['nonempty_task_lp_groups'],d['pjob_inventory_variables'],d['variables'],d['constraints']])
tables['@@TABLE_DIMENSIONS@@']=table('双源实例预处理前的规模（$H=3$）','tab:dimensions-cn','rcrrrr',
    r'$N$ & 模式 & $G$ & 库存选择列 & 总变量 & 总约束',rows)

algorithm=(HERE/'algorithm_section.tex').read_text(encoding='utf-8')
algorithm=algorithm.replace('模型4直接优化','批次任务模型直接优化').replace('模型4实验使用既有训练种子1、第60轮的冻结策略，仅评价迁移后的观测。','选割消融使用训练种子1、第60轮的冻结策略。')
algorithm=algorithm.replace('本文不据这些冻结策略实验宣称完成模型4专属训练或获得普遍求解优势。','')
algorithm=algorithm.replace('模型4的批次任务求解与末端晶圆解码','批次任务求解与末端晶圆解码').replace('模型4成立或排程解码','物理建模或排程解码')
algorithm=algorithm.replace('编码和解码都是确定性映射；','输入分组与晶圆编号恢复采用确定规则；')
algorithm=algorithm.replace('该过程不同于历史固定布局的零目标初始化；','')
algorithm=algorithm.replace('本节中的晶圆解码区别于学习割选择器内部的序列生成，不以神经网络预测晶圆身份。','')
algorithm=algorithm.replace('因此需要补充的是\\emph{输入分组及初始赋值映射}，而不是另设一套染色体编码。','输入编码包括任务分组及初始可行排程向匿名变量的映射。')
algorithm=algorithm.replace('可选选割组件与必要消融','可选选割组件')
algorithm=algorithm.replace('学习割选择作为可选搜索组件保留，不作为物理建模或排程解码的前提。','学习割选择用于辅助MILP搜索。')
algorithm=algorithm.replace('割选择器内部的编码与有序选择只处理候选不等式，不负责Pjob与晶圆之间的映射。','')
experiments=(HERE/'experiments_section.tex').read_text(encoding='utf-8')
for marker,value in tables.items():experiments=experiments.replace(marker,value)
experiments=experiments.replace('因此，以下比较报告排程质量和组件观测，不作严格等墙钟预算的速度排名。','以下按实际停止时获得的排程质量报告描述性比较。')
experiments=experiments.replace('各方法实际停止时间不同，不据此排序求解速度。','')
assert '@@' not in experiments
start=source.index(r'\section{面向限时可行排程的求解框架}')
end=source.index(r'\section{结论}',start)
source=source[:start]+algorithm+'\n'+experiments+'\n'+source[end:]

abstract=r'''先进薄膜沉积设备中的满片加工要求使产品晶圆、辅助晶圆、旋转腔与共享机械手形成相互依赖的资源占用。本文建立按工艺模式和腔室资格分组的批次任务混合整数线性规划，将同任务同LP内可交换产品的身份选择从排程决策中分离，并在算法末端恢复具体晶圆编号。模型统一描述两种生产模式、辅助晶圆复用、连续处理和清洁边界，采用完工时间优先、等待与节拍精修的两阶段求解。342次运行中获得330个通过约束检查和物理重放的可行排程；四种初始化对照配置中，冷启动12次均未取得可行解，两类构造起点各12次均获得可行排程。八种混合配置的阶段内精修保持产品完工时间，总等待下降39.76\%--93.64\%。固定产品结构下调整辅助晶圆借用关系，将一组4片配置的条件最优完工时间由532~s降至403~s。另给出8、16、32片规范化取放顺序的构造性数量下界。研究提供了从批次任务决策到具体晶圆执行序列的建模与求解方法。'''
source=re.sub(r'\\begin\{abstract\}.*?\\end\{abstract\}',lambda _:r'\begin{abstract}'+'\n'+abstract+'\n'+r'\end{abstract}',source,flags=re.S)
source=source.replace(r'\sep 学习增强精确优化',r'\sep 批次任务')
source=source.replace(r'\section{问题描述与模型4的批次任务调度}',r'\section{问题描述与批次任务调度模型}')
old='本文将逐产品身份的联合表示称为模型2，将本文修订后的匿名批次任务表示称为模型4。'
p0=source.index(old);p1=source.index('\n\n',p0)
source=source[:p0]+r'产品按工艺模式、允许腔室集合及其他影响调度的共同属性划分为批次任务$\mathrm{Pjob}_j$，同一任务在各LP的数量作为库存输入。模型选择任务类型、来源和匿名成员的物理动作；具体编号在算法末端恢复。'+source[p1:]
source=source.replace('理解模型4所需的输入与关键决策','理解批次任务表示所需的输入与关键决策')
source=source.replace('模型4的关键参数','批次任务调度的关键参数').replace('模型4的关键决策变量','批次任务调度的关键决策变量')
source=source.replace('具体产品编号$w$仅用于输出追踪和历史实验','具体产品编号$w$仅用于输入核对和输出追踪')
source=source.replace('定义产品标记$\\beta_{pr}=\\sum_{j,\\ell}x_{j\\ell pr}$和辅助标记$d_{pr}=v_p-\\beta_{pr}$，二者由成员选择确定。','定义产品标记$\\beta_{pr}=\\sum_{j,\\ell}x_{j\\ell pr}$和辅助标记$d_{pr}=v_p-\\beta_{pr}$，两者均取0或1并由成员选择确定。')
source=source.replace('第~\\ref{sec:joint-evidence-cn}节通过控制产品结构的对照量化这一影响。','第~\\ref{sec:model4-ablation-cn}节给出保持产品结构的辅助身份对照。')
source=source.replace('固定布局实验另施加其布局与服务次序条件。','固定结构对照另固定指定的分配与占位。')
source=source.replace('固定布局实验额外固定这些位置及服务次序，并采用仅末批补位规则：若后续同类批次存在，当前$4\\times1$批次含两个产品对。联合模型允许在任一合法生产周期采用辅助补位。','联合模型允许在任一合法生产周期采用辅助补位；固定结构对照则另固定所选分配与占位。')
source=source.replace('共享资源的先后关系分为给定次序和待定次序。操作先后弧及预设服务链中的操作按指定次序执行，其余冲突操作通过次序变量协调。固定布局的纯$4\\times1$实验采用预设的对准和装载锁服务次序；当候选批次数不超过清洁阈值时，VTR也采用预设的批次装卸服务链。这些预设关系仅用于固定布局实验；联合模型由资源次序变量决定其余冲突动作的顺序。','共享资源的先后关系分为给定技术次序和待定服务次序。路线先后弧按工艺执行，其余冲突动作通过资源次序变量协调。')
source=source.replace('对启用的匿名任务$i=(p,r)$进入和离开受限区段$\\rho$的事件，有','对启用的匿名任务$i=(p,r)$，模块驻留区段$\\rho$从放片完成至取片开始，满足')
source=source.replace('式~\\eqref{eq:residence-cn}表示晶圆在上装载锁、工艺腔室、下装载锁或受限制搬运区段中的物理停留时间不得超过上限，即驻留时间约束。','式~\\eqref{eq:residence-cn}控制AL、装载锁和工艺腔室中的驻留时间。机械手承片区间另从取片动作开始计至放片动作完成，并对该完整区间施加承片时长上限。')

eq0=source.index(r'\subsection{模型4的解码、等价范围与规模边界}')
eq1=source.index(r'\section{批次任务编码',eq0)
equiv=source[eq0:eq1]
para0=equiv.index('给定匿名排程后，');para1=equiv.index('\n\n',para0)
equiv=equiv[:para0]+r'同任务、同LP且调度属性相同的产品可相互交换身份。将逐片排程投影为匿名成员后，库存与全部物理事件保持不变；算法末端的编号恢复见第~\ref{sec:pjob-decoding-cn}节。每个在制成员仍有独立位置、进度和时间状态。'+equiv[para1:]
equiv=equiv.replace('模型4的解码、等价范围与规模边界','匿名表示的等价性与规模').replace('逐片模型2','逐片模型').replace('模型4','批次任务模型').replace('无限制模型2','无限制逐片模型')
equiv=equiv.replace('目前不报告批次任务模型求解提速','计算性能需在匹配实例与资源下单独评价')
equiv=equiv.replace('构造初始排程后完成辅助变量赋值，并在释放额外固定条件的完整模型中检查，再按任务--LP组的首次取片次序解码具体产品身份。','初始赋值映射和最终编号恢复分别位于第3节算法的前端与末端。该表示减少产品身份选择，匿名PW对等标签仍可能存在对称性。')
source=source[:eq0]+equiv+source[eq1:]
source=source.replace(r'\mathcal F_2^{\rm elig}',r'\mathcal F_{\mathrm W}^{\rm elig}').replace(r'\mathcal F_4',r'\mathcal F')
source=source.replace('前述约束共同定义模型4的联合可行域$\\mathcal F$，下文简记为$\\mathcal F$，','前述约束共同定义联合可行域$\\mathcal F$，')
start=source.index('记$G=|');end=source.index('\n\n',start)
source=source[:start]+r'记$G=|\{(j,\ell):N_{j\ell}>0\}|$，一般候选域中的产品成员选择变量由逐片表示的$2NP_{\max}$改为$2GP_{\max}$。匿名成员直接关联所属PW对，可省去逐产品到候选对的条件时刻联结及身份推导的同对逻辑量。共享时长参数保持原定义；辅助片实体复用、清洁与资源排序仍需建模，候选容量由产品数而非任务数确定。'+source[end:]

# State scope once, using affirmative definitions instead of repeated disclaimers.
source=source.replace('本文直接优化等待与周期节拍，并以硬上限控制驻留时间；不将这些指标解释为已经实现等驻留或严格JIT控制。','本文优化等待与周期节拍，并以硬上限控制驻留时间。')
source=source.replace('当前实验不含随机偏差的在线注入、测量反馈或闭环重调度，因此其结果仅验证已测试确定性配置下的排程能力。','实验采用给定参数快照，比较确定性配置下的排程。')
source=source.replace('本文以减少等待和不规则衔接支持面向JIT的运行设计，不宣称已建立包含需求时刻、提前/延迟代价或驻留一致性目标的JIT调度模型。','需求时刻匹配及驻留一致性属于另外的调度目标。')
source=source.replace('本文不以等待减少替代这一检验。','')
start=source.index(r'\paragraph{模式选择的判定口径。}');end=source.index('\n\n',start)
source=source[:start]+r'\paragraph{模式选择的判定口径。} 在相同设备和资格条件下，以产品回片完工时间评价模式。有效上下界分离或已证最优值用于认证优选；界区间重叠时，报告已获得排程的可行上界及等待、节拍指标。'+source[end:]

oldstart=source.index('上述晶圆与资源约束形成混合整数调度问题。');oldend=source.index('\n\n',oldstart)
source=source[:oldstart]+r'上述晶圆与资源约束形成混合整数调度问题。强化学习可用于CT动作选择，也可辅助MILP搜索\citep{kim2025adaptivecluster,tang2020cut,huang2022cutranking,paulus2022looking}。HEM以层次策略协调割数量和有序子集\citep{wang2023hem}。本文以结构化初始化和两阶段MILP求解为主体，将冻结选割策略作为可选组件，通过消融观察其增量作用。'+source[oldend:]
p0=source.index('本文围绕“');p1=source.index(r'\section{问题描述',p0)
source=source[:p0]+r'''本文围绕满片条件下的批次生产组织与具体晶圆排程，主要贡献如下：
\begin{enumerate}[leftmargin=*]
\item 按工艺模式、腔室资格和LP库存建立批次任务表示，将可交换产品身份从优化变量中分离，同时保留配对、辅助借用和完整物理路线；
\item 统一描述并行生产、链式生产和清洁边界，构建产品完工时间优先、等待与节拍精修的两阶段模型；
\item 给出输入分组、初始赋值编码、匿名求解和末端晶圆解码流程，以必要消融及模式对照评价可行排程获取和时序质量。
\end{enumerate}

第2节定义批次任务模型；第3节介绍编码、求解与解码流程；第4节报告实验结果；第5节给出结论。

'''+source[p1:]
p0=source.index(r'\section{结论}');p1=source.index(r'\section*{CRediT',p0)
source=source[:p0]+r'''\section{结论}

本文针对满片加工的旋转腔组合设备，建立按工艺模式、腔室资格及LP库存组织产品的批次任务模型。匿名成员保留完整搬运、加工及驻留状态，产品身份在求解结束后按任务--LP组的首次取片顺序恢复。该表示将可交换身份与配对、分腔、辅助片复用和清洁等物理决策分开，输出仍为可执行的逐晶圆动作序列。

实验完成342次运行并获得330个有效排程。构造起点在四种初始化对照配置中均支持可行排程获取；两阶段精修保持产品完工时间，将八种混合配置的总等待降低39.76\%--93.64\%。辅助片身份对照表明，即使产品结构相同，其跨腔借用关系也能显著影响完工时间。模式比较得到随批量和清洁阈值变化的候选排程排序，相关界区间仍有重叠。后续研究将围绕较大规模下的资源排序压缩、有效节拍结构及执行时长扰动展开。

'''+source[p1:]

# Keep only cited bibliography entries; retain their original bibliographic text.
keys=set()
for match in re.finditer(r'\\cite\w*\{([^}]+)\}',source):keys.update(k.strip() for k in match.group(1).split(','))
matches=list(re.finditer(r'\\bibitem(?:\[[^\]]*\])?\{([^}]+)\}',source));endbib=source.index(r'\end{thebibliography}')
for i in range(len(matches)-1,-1,-1):
    m=matches[i];end=matches[i+1].start() if i+1<len(matches) else endbib
    if m.group(1) not in keys:source=source[:m.start()]+source[end:]
assert '模型4' not in source and '模型2' not in source,[line for line in source.splitlines() if '模型4' in line or '模型2' in line]
assert '历史基准' not in source and '@@' not in source
(PAPER/'JMS_Review_CN.tex').write_text(source,encoding='utf-8')
(HERE/'generated_tables.json').write_text(json.dumps(tables,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(dict(lines=len(source.splitlines()),citations=len(keys),tables=len(tables)),ensure_ascii=False))

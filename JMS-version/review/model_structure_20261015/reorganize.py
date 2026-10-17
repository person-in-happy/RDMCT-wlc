"""Reorganize Section 2 by model dependencies without changing its feasible set."""
from pathlib import Path
import re
import shutil
import json
import difflib

HERE = Path(__file__).resolve().parent
PAPER = HERE.parents[1]
path = PAPER/'JMS_Review_CN.tex'
backup = HERE/'JMS_Review_CN.before_reorganization.tex'
if backup.exists():
    assert backup.read_bytes() == path.read_bytes(), 'Source already revised.'
else:
    shutil.copy2(path, backup)
s = path.read_text(encoding='utf-8')
start = s.index(r'\section{问题描述与两阶段调度模型}')
end = s.index(r'\section{结构感知MILP求解框架}')
old = s[start:end]

def span(a, b):
    assert old.count(a)==old.count(b)==1, (a,b)
    return old[old.index(a):old.index(b)].strip()

def para(prefix):
    matches=[x for x in old.splitlines() if x.strip().startswith(prefix)]
    assert len(matches)==1, prefix
    return matches[0].strip()

eqs = {}
for m in re.finditer(r'\\begin\{equation\}.*?\\end\{equation\}', old, re.S):
    label = re.search(r'\\label\{([^}]+)\}',m[0])[1]
    assert label not in eqs
    eqs[label]=m[0]
assert len(eqs)==27

def eq(label):
    return eqs[label]

def heading(name):
    return '\\noindent\\textbf{'+name+'。}'

def section(title,label,*parts):
    return '\\subsection{'+title+'}\n\\label{'+label+'}\n\n'+'\n\n'.join(parts)

tables = re.findall(r'\\begin\{table\*\}.*?\\end\{table\*\}', old, re.S)
assert len(tables)==2
# The summary tables follow the same conceptual order as the six subsections.
input_prefixes=[r'$\mathcal W,',r'$\mathcal S,',r'$\ell_w,',r'$N$',
    r'$\mathcal P,',r'$\mathcal C,',r'$\mathcal P^{',r'$\mathcal B_c,',
    r'$N_{\zeta}',r'$P_{\max}',r'$H$',r'$\mathcal O,',r'$\mathcal A^{',
    r'$d_o,',r'$\delta_',r'$M,',r'$\overline T,',r'$\mathrm{pick',
    r'$\mathcal E_c,',r'$\nu;',r'$\mathcal J_c^D,',r'$\mathcal R$',
    r'$\Gamma_o$',r'$\operatorname{in}',r'$\mathcal F$',r'$\mathcal D_',
    r'$\lambda_',r'$\bar\omega_']
variable_prefixes=[r'$a_{wpr}',r'$\mu_{pm}',r'$B_p,',r'$U_{cq}',
    r'$X^P_',r'$b_o$',r'$s_o,',r'$x,s^{',r'$\gamma^{',r'$s_v,',
    r'$A_{pcq}',r'$S_{cq}',r'$f_{pcq}',r'$\begin{gathered}s^{',
    r'$s^{\rm rot',r'$z_{ce}',r'$a_{vce}',r'$s^{\rm cl}',r'$x^{\zeta}',
    r'$g_{j',r'$h_{o',r'$y^r_',r'$C_w,',r'$\xi,',r'$\omega_',
    r'$h_{ceq}',r'$\Delta_',r'$v_{ceq}',r'$\eta_',r'$\Phi$']
def reorder_table(table,prefixes):
    a=table.index('\\midrule\n')+len('\\midrule\n')
    b=table.index('\\bottomrule')
    rows=table[a:b].strip().splitlines()
    chosen=[]
    for prefix in prefixes:
        found=[row for row in rows if row.startswith(prefix)]
        assert len(found)==1,(prefix,found)
        chosen.append(found[0])
    assert len(chosen)==len(rows) and set(chosen)==set(rows)
    return table[:a]+'\n'.join(chosen)+'\n'+table[b:]
tables=[reorder_table(tables[0],input_prefixes),reorder_table(tables[1],variable_prefixes)]
tables[0]=tables[0].replace('共同腔内先后关系及晶圆$i$按来源$s$', '共同腔内先后关系及晶圆任务$i$按来源$s$')

intro = '\n\n'.join([
    r'\section{问题描述与两阶段调度模型}'+'\n'+r'\setcounter{equation}{0}',
    para('本文涉及的物料'),
    r'给定LP1--LP4的产品晶圆数量与工艺模式、辅助晶圆库存和设备初始状态，调度任务是联合确定晶圆配对、腔室分配、加工周期、共享资源次序与动作时刻。模型依次描述物理路径、晶圆与周期的匹配关系、动作时间逻辑、工艺与清洁规则、资源占用，以及两阶段优化目标。',
    para('模型输入包括'),para('清洁阈值$H'),
    r'表~\ref{tab:symbol-cn-a}与表~\ref{tab:symbol-cn-b}分别汇总集合、参数与决策变量，符号按下文建模顺序排列。各物理动作统一使用起止时刻$s_o,e_o$，周期、装卸及清洁阶段的时刻符号对应相应物理事件。',
    *tables])

path_section=section('单源与双源物理加工路径','sec:model-path-cn',
    r'产品晶圆集合记为$\mathcal W$，晶圆路线任务集合记为$\mathcal I$。每片产品晶圆对应一条完整路线，辅助晶圆每次借用对应一条供回路线；同一实体辅助晶圆可先后承担多个借用任务。',
    para(r'设$\mathcal S=').split(r'\begin{equation}')[0].strip(),
    eq('eq:source-membership-cn'),
    para(r'式~\eqref{eq:source-membership-cn}'),
    r'产品晶圆在两种来源配置下均沿“LP--ATR--AL--ATR--上装载锁--VTR--工艺腔室--VTR--下装载锁--ATR--原LP”运行。产品先经AL对准，再由装载锁完成压力转换，进入工艺腔室完成给定配方。',
    r'单源辅助晶圆从LP4旁的大气存储区出发，经ATR、上装载锁和VTR进入工艺腔室，使用后经VTR、下装载锁和ATR返回原存储区。辅助晶圆单独供给时不经过AL；与产品晶圆随行入片时，在产品对准期间保持在ATR上，待产品取回后共同入锁。两种方式均不对辅助晶圆执行AL对准。',
    r'双源辅助晶圆从真空存储区出发，经VTR进入工艺腔室，使用后由VTR返回真空存储区。两种来源配置分别见图~\ref{fig:single-source-cn}与图~\ref{fig:system-zh-new}。上述路径确定晶圆必须经历的物理环节，成对搬运选择及其时间条件在第~\ref{sec:model-time-cn}节给出。')

bounds=span('纯辅助对可用于补位或清洁', '$4\\times1$模式的常规满产品批次')
pairing=span('PW对（wafer pair）', '纯辅助对可用于补位或清洁')
capacity=span(r'令$\mathcal Q_c=', '二元量$A_{pcq}')
capacity=capacity.replace('二元量$U_{cq}$标识周期启用，$K_{cqm}$选择周期类型，$X_{pcq}$选择参加该周期的PW对。',
    '二元量$U_{cq}$标识周期启用，$K_{cqm}$选择周期类型，$X_{pcq}$选择参加该周期的PW对，$X^P_{pcq}$标识该占位是否来自含产品对。')
pair_section=section('晶圆、PW对与腔室周期的匹配关系','sec:model-assignment-cn',
    r'本节将单片晶圆组织为PW对，再将PW对分配到兼容腔室及其加工周期。生产周期与清洁周期共用候选加工周期集合，具体生产次数和清洁触发规则在第~\ref{sec:model-process-cn}节规定。',
    heading('晶圆配对与腔室选择')+'\n'+pairing,
    heading('候选容量上界')+'\n'+bounds,
    heading('PW对与加工周期匹配')+'\n'+capacity)

time_core=span('对任一候选物理操作', r'\subsection{联合周期占位与旋转装卸}')
operation=time_core[:time_core.index('对必须依次执行')].strip()
precedence=time_core[time_core.index('对必须依次执行'):].strip()
operation=operation.replace('对任一候选物理操作$o$，开始、结束和持续时间满足',
    r'令$\mathcal O$为候选动作集合。对动作$o\in\mathcal O$，$b_o$表示启用状态，$s_o,e_o$分别为起止时刻，$d_o$为给定持续时间，$M$为有效大常数。各动作满足')
stages=span('产品晶圆或辅助晶圆的个体阶段', '对于单源产品--辅助对')
stages=stages.replace('当PW对$p$在同地点、同动作的原子搬运段$a$上选择一次成对搬运时，两片晶圆的搬运阶段同步：',
    r'令$w_1,w_2$为PW对$p$中的两片晶圆，$\gamma_{pa}$表示在同地点原子搬运段$a$上选择成对搬运。$s_{wa},e_{wa}$为晶圆$w$在该段的起止时刻。成对搬运要求两片晶圆的对应动作同步：')
single=span('对于单源产品--辅助对', '对晶圆$w$进入和离开受限设备区段')
time_section=section('动作时间与先后逻辑','sec:model-time-cn',
    r'在物理路径与配对关系确定后，以动作启用、持续时间、前后衔接和同步条件描述路线的时间可行性。动作间的技术先后关系由本节规定，共享资源冲突引起的待定次序在第~\ref{sec:model-resource-cn}节处理。',
    heading('动作启用与持续时间')+'\n'+operation,
    heading('路径对应的动作先后关系')+'\n'+r'令$\mathcal A^{\rm int}$为腔内共同先后弧集合，$\mathcal A_{is}(\gamma)$为晶圆任务$i$在来源$s$及搬运选择$\gamma$下的供回片先后弧集合；$\gamma$统称成对搬运与单源随行入片等离散选择。完整先后弧集合为',
    eq('eq:route-union-cn'),
    r'式~\eqref{eq:route-union-cn}按晶圆来源和搬运选择启用对应路径，将产品路线、辅助晶圆供回路线与腔内动作链连接起来。'+ '\n\n'+precedence,
    heading('阶段联结与成对动作同步')+'\n'+stages,
    heading('单源产品--辅助对的入片逻辑')+'\n'+single)

process_story=span('$4\\times1$模式的常规满产品批次',r'\subsection{晶圆来源配置与基本时间关系}')
exposures=span('二元量$A_{pcq}', '加工周期的起止时刻为')
duration=span('加工周期的起止时刻为', '令$f_{pcq}')
rotation=span('令$f_{pcq}', '给定解后，$x^{')
cleaning=span('整数$n_{cq}', '每个辅助晶圆位置对应借用需求')
fixed=para('给定解后，$x^{')
process_section=section('两种工艺模式与清洁处理','sec:model-process-cn',
    r'第~\ref{sec:model-assignment-cn}节确定周期中有哪些PW对，本节进一步规定各对参与生产的次数、相邻周期的保留与退出、旋转装卸次序及清洁边界。所有时刻均沿用第~\ref{sec:model-time-cn}节的动作时间表示。',
    heading('生产模式与连续占位')+'\n'+process_story+'\n\n'+exposures,
    heading('加工时长与周期衔接')+'\n'+duration,
    heading('前后侧占位与旋转装卸')+'\n'+rotation,
    heading('清洁触发与清洁动作链')+'\n'+cleaning,
    fixed)

dummy=span('每个辅助晶圆位置对应借用需求',r'\subsection{机械手、腔室与时间资源占用}')
resource_intro=span('共享资源的先后关系分为', 'ATR为双手机械手')
resource_units=span('ATR为双手机械手', '若操作$o$和$o\'')
resource_order=span('若操作$o$和$o\'', '上述操作先后约束')
deadlock=para('上述操作先后约束')
residency=span('对晶圆$w$进入和离开受限设备区段',r'\subsection{完工时间优先的两阶段优化}')
resource_section=section('辅助晶圆复用与机械手、模块资源','sec:model-resource-cn',
    r'晶圆路线和腔内加工规则还需满足实体资源的可用性。本节先为辅助晶圆借用任务选择实体身份，再分配机械手承片位置和模块槽位，最后通过互斥次序及驻留上限协调资源占用。',
    heading('辅助晶圆身份与循环复用')+'\n'+dummy,
    heading('机械手承片与模块容量')+'\n'+resource_units,
    heading('资源互斥与地点相关换位')+'\n'+resource_intro+'\n\n'+resource_order,
    heading('驻留限制与时序可行性')+'\n'+residency+'\n\n'+deadlock)

primary=span('令$C_w$为产品晶圆', r'令$\mathcal Q^w$')
waiting=para(r'令$\mathcal Q^w$')
rhythm=para('对腔室$c$，清洁区段')
last=para('当对应权重严格为正')
domain=r'''\begin{equation}
\begin{gathered}
\xi_d=\widehat\xi_d\quad(d\in\mathcal D_{\rm fix}),\qquad
C_{\max}\le\widehat C+\varepsilon_C.
\end{gathered}
\label{eq:secondary-domain-cn}
\end{equation}'''
wait_eq=r'''\begin{equation}
\begin{gathered}
L_{\rm sum}=\sum_{\alpha\in\mathcal Q^w}\omega_\alpha,\qquad
L_{\max}\ge\omega_\alpha.
\end{gathered}
\label{eq:secondary-wait-cn}
\end{equation}'''
rhythm_eq=r'''\begin{equation}
\begin{gathered}
\Delta_{ceq}=(h_{ce,q+1}-h_{ceq})-(h_{ceq}-h_{ce,q-1}),\\
v_{ceq}\ge\Delta_{ceq},\qquad v_{ceq}\ge-\Delta_{ceq}.
\end{gathered}
\label{eq:secondary-rhythm-cn}
\end{equation}'''
soft_eq=r'''\begin{equation}
\eta_\alpha\ge\omega_\alpha-\bar\omega_\alpha,\qquad
\eta_\alpha\ge0.
\label{eq:secondary-softwait-cn}
\end{equation}'''
objective=r'''\begin{equation}
\begin{gathered}
\min\Phi=\lambda_1L_{\rm sum}+\lambda_2L_{\max}
+\lambda_3\sum_{(c,e,q)\in\mathcal I_h}v_{ceq}
+\lambda_4\sum_{\alpha\in\mathcal Q^w}\eta_\alpha.
\end{gathered}
\label{eq:secondary-objective-cn}
\end{equation}'''
objective_section=section('完工时间优先的两阶段优化','sec:model-objective-cn',
    r'前述约束共同定义联合可行域$\mathcal F$。第一阶段优化产品回片完工时间，第二阶段在保留第一阶段完工时间上界与主要离散结构的条件下优化等待与生产节拍。',
    heading('第一阶段：最小化产品回片完工时间')+'\n'+primary,
    heading('第二阶段：限定优化范围并精修时序')+'\n'+r'设第一阶段获得当前最好可行解$\widehat\xi$，其产品完工时间为$\widehat C$。集合$\mathcal D_{\rm fix}$包含第二阶段固定的配对、分腔、周期占位、辅助身份、手分配、随行入片选择与资源次序。给定完工时间容差$\varepsilon_C$，第二阶段在原可行域上增加',
    domain,
    r'式~\eqref{eq:secondary-domain-cn}保留主要离散结构及产品完工时间上界，同地点原子取放同步选择与连续时刻继续参与优化。第一阶段即使尚未证明最优，也可用其当前最好可行解启动第二阶段。',
    waiting+'\n'+wait_eq,
    rhythm+'\n'+rhythm_eq,
    r'若启用等待软上限$\bar\omega_\alpha$，以非负辅助量$\eta_\alpha$表示超额等待的上界：'+'\n'+soft_eq,
    r'将上述指标按非负权重$\lambda_1,\ldots,\lambda_4$组合，第二阶段目标为'+'\n'+objective,
    r'式~\eqref{eq:secondary-objective-cn}分别惩罚总等待、最大单项等待、相邻生产周期开始间隔的变化和软等待超额。正式实验采用$(\lambda_1,\lambda_2,\lambda_3)=(1,10,25)$、$\varepsilon_C=10^{-6}$；关闭软等待上限时不生成超额变量，也不计入对应惩罚项。',
    last)

new='\n\n'.join([intro,path_section,pair_section,time_section,process_section,resource_section,objective_section])+'\n\n'
# Formula-by-formula conservation, with the former secondary block split only by purpose.
new_eqs={re.search(r'\\label\{([^}]+)\}',m[0])[1]:m[0]
         for m in re.finditer(r'\\begin\{equation\}.*?\\end\{equation\}',new,re.S)}
for label,formula in eqs.items():
    if label!='eq:secondary-objective-cn':
        assert new_eqs[label]==formula,label
def canonical(formula):
    formula=re.sub(r'\\(?:begin|end)\{[^}]+\}|\\label\{[^}]+\}','',formula)
    formula=re.sub(r'\\qquad|\\quad|\\,|\\\\','',formula)
    return re.sub(r'[\s.,&]','',formula)
split_labels=['eq:secondary-domain-cn','eq:secondary-wait-cn','eq:secondary-rhythm-cn',
              'eq:secondary-softwait-cn','eq:secondary-objective-cn']
assert canonical(eqs['eq:secondary-objective-cn'])==canonical(''.join(new_eqs[k] for k in split_labels))
old_labels=re.findall(r'\\label\{([^}]+)\}',old)
new_labels=re.findall(r'\\label\{([^}]+)\}',new)
assert set(old_labels)<=set(new_labels) and len(new_labels)==len(set(new_labels))
assert len(re.findall(r'\\subsection\{',new))==6
result=s[:start]+new+s[end:]
assert result[:start]==s[:start]
assert result[result.index(r'\section{结构感知MILP求解框架}'):]==s[end:]
path.write_text(result,encoding='utf-8',newline='\n')
(HERE/'revision.diff').write_text(''.join(difflib.unified_diff(s.splitlines(True),result.splitlines(True),fromfile='before',tofile='after')),encoding='utf-8')
(HERE/'structure_audit.json').write_text(json.dumps({
    'old_model_equations':len(eqs),'new_model_equations':len(new_eqs),
    'unchanged_equations':26,'secondary_split_equivalent':True,'outside_model_unchanged':True,
    'formula_order':list(new_eqs)},ensure_ascii=False,indent=2),encoding='utf-8')
print('Reorganized six subsections; 26 model equation blocks unchanged; secondary block split into five equivalent groups.')

"""Expand Table 1 from the complete input contract; retain key-variable Table 2."""
from pathlib import Path
import ast
import json
import re

PAPER = Path(__file__).resolve().parents[2]

# Symbol, type, definition. Sets determined by a solution are explicitly marked.
sets = [
(r'$\mathcal J,\mathrm{Pjob}_j$', '任务索引与产品集合', r'$\mathcal J=\{1,\ldots,J\}$；产品按模式、腔室资格及调度属性分组，每片恰属一个任务。'),
(r'$\ell,s,\mathcal L_j,k,\ell_{jk}$', 'LP、槽位与有序编码', r'四个LP，槽位$s=1,\ldots,25$；$\mathcal L_j$存任务$j$实际编号升序表，$k=1,\ldots,N_j$；来源$\ell_{jk}$由编号表确定。'),
(r'$N_{j\ell},N_j,N_\zeta,N_\psi,N$', '库存及派生整数', r'各任务在各LP的产品库存；$N_j=\sum_\ell N_{j\ell}$，$N=N_\zeta+N_\psi=\sum_jN_j$，不含辅助片。'),
(r'$m_j,\mathcal M,\mathcal C,\mathcal C_j$', '配方与资格集合', r'$\mathcal M=\{\zeta,\psi,\mathrm{cl}\}$；设备腔室为CH2/CH3；任务模式$m_j$与非空资格$\mathcal C_j\subseteq\mathcal C$由输入给定。'),
(r'$\mathcal C(m)$', '设备兼容集合', r'类型$m$可用的设备腔室；本设备两腔均支持两种配方及清洁，产品资格再由$\mathcal C_j$收紧。'),
(r'$\mathcal P,\mathcal Q_c,\mathcal I$', '派生候选集合', r'$\mathcal P=\{1,\ldots,P_{\max}\}$，$\mathcal Q_c=\{1,\ldots,Q_{\max}\}$；成员位$r\in\{0,1\}$，路线任务$\mathcal I=\mathcal P\times\{0,1\}$。'),
(r'$T,J_{\max},P_{\max},Q_{\max}$', '派生容量上界', r'$T=N_\zeta+2N_\psi$，$J_{\max}=T$，$P_{\max}=N+3T$，$Q_{\max}=2T$；用于完整候选域，不是实际执行数量。'),
(r'$\mathcal S,\sigma$', '来源集合与配置', r'$\mathcal S=\{A,V\}$为大气/真空区域；单源$\sigma=0$，双源$\sigma=1$。产品均来自LP；辅助片分别来自AS或VS。'),
(r'$\mathcal D,D$', '辅助身份集合与数量', r'$\mathcal D=\{D_1,\ldots,D_D\}$，$D=|\mathcal D|$；基准按每腔4片配置，共享8片，非按腔独占；实现允许$4\le D\le10$。'),
(r'$\mathcal O,\mathcal O^{\rm occ}$', '派生动作与占用集合', r'由候选成员、周期及路线模板生成物理动作和资源占用区间；占用端点引用取放、旋转与加工事件。'),
(r'$\mathcal R,K_\rho,\Gamma_o$', '资源类、容量与允许单元', r'ATR承2片、VTR承4片，AL容量1，上/下LL各2槽，腔室4工位；机器人及腔室执行机构各为独占资源；$\Gamma_o$为占用允许单元集合。'),
(r'$\mathcal A^{\rm int},\mathcal A_{is}(\gamma),\mathcal A$', '路线模板与启用弧集', r'腔内公共先后弧及按来源、成对搬运/随行选择启用的供回弧；完整弧集由模板和选择确定，并非预先固定的完整动作次序。'),
(r'$\mathcal V_c,e,\nu$', '解后派生区段索引', r'生产任务集$\mathcal V_c$、清洁区段$e$及清洁阶段$\nu\in\{FL,BL,P,BU,FU\}$由周期结构及物理事件恢复，不是独立输入分段。'),
(r'$\mathcal W,\mathcal I_h,\mathcal D_{\rm fix}$', '评价与阶段二派生集合', r'等待项集由路线间隔生成；节拍中心集$\mathcal I_h$由连续保留链确定；固定分量集$\mathcal D_{\rm fix}$包含除原子同步外的非连续变量。'),
]
params = [
(r'$d_\zeta,d_\psi,d_{\mathrm{cl}}$', '正实数时长', r'两种生产及清洁曝光默认180、90、500 s；$2\times2$产品需相邻两次90 s曝光。'),
(r'$d_o^{\rm ATR},d_o^{\rm VTR},r_c$', '正实数时长', r'ATR取放4 s、VTR取放1 s、腔室半周旋转2 s；共同装卸对只执行一次原子动作，LP取片时长为正。'),
(r'$t_{\rm ATR},t_{\rm VTR},t_{\rm empty}$', '移动时间配置', r'通常换位分别3、2 s；ATR从LL空返LP或AS再取片为6 s；同地点及U/L间移动取0，按地点与方向生成换位参数。'),
(r'$t_{\rm AL},t_{\rm pump},t_{\rm vent}$', '必要工艺间隔', r'产品AL对准20 s、上锁抽气30 s、下锁放气25 s；辅助片不执行AL对准。'),
(r'$t_{\rm U}^{\rm reset},t_{\rm L}^{\rm reset}$', '槽位复位时长', r'上/下LL槽位分别30、25 s，从另一侧取片结束后计；可与取片后运输重叠。'),
(r"$d_o,\delta_{oo'},\delta^\rho_{oo'}$", '按模板派生的时长参数', r'物理动作持续时间、技术弧最小间隔及方向相关换位/复位间隔，由上述时长、地点与物理路线生成，不额外任意赋值。'),
(r'$H$', '清洁阈值', r'整数$H\ge2$，默认3；累计1至$H-1$次可在合法边界提前清洁，达到$H$必须清洁，包括末段。'),
(r'$\overline R_{i\rho}$', '硬驻留/承片上限', r'模块驻留与机械手承片上限默认各10000 s；模块按放片结束至取片开始计，手按取片开始至放片结束计。'),
(r'$\overline T,M,B$', '时域与派生松弛量', r'时域默认100000 s；$M=3\overline T+\max(t_{\rm pump},t_{\rm vent},t_{\rm U}^{\rm reset},t_{\rm L}^{\rm reset})$；资源平移带宽$B=\overline T+\max(0,t_{\rm U}^{\rm reset},t_{\rm L}^{\rm reset})$。'),
('辅助片对准策略', '路线配置', '当前为不对准，可单独绕过AL或随产品到AL而留在ATR上；旧全片对准选项仅用于历史规则，不能与当前输入混用。'),
('VTR洁净/脏手策略', '承片资格配置', '当前未加工产品用两只脏手、加工完成产品用两只洁净手，辅助片可用全部四手；旧不区分手的选项属不同物理规则。'),
('Pjob出片与设备容量规则', '固定模型配置', '同Pjob跨LP按输入序号严格取片且不可同步；不同Pjob可交错；每个PW对2片、每个腔室周期2对满片。'),
(r'$\lambda_1,\lambda_2,\lambda_3,\varepsilon_C$', '阶段二配置', r'总等待、最大等待及节拍绝对偏差权重为$(1,10,25)$，产品完工上界容差$10^{-6}$ s；固定第一阶段主要离散结构。'),
(r'$\bar\omega_\alpha,\lambda_4$', '未启用的扩展配置', r'可选软等待上限及超额罚权重；当前默认实现不生成该项。它们不是当前实验必须提供的输入。'),
]

fields = {
'load_ports':'LP库存与实际编号','pjobs':'任务ID、模式、资格、产品ID列表',
'source':'来源集合与单/双源配置','dummy_alignment':'辅助片对准策略','vtr_hand_policy':'VTR洁净/脏手策略',
'dummy_count':'辅助身份集合与数量','cleaning_interval':'清洁阈值',
'full_time':'4x1曝光','mix_time':'2x2曝光','cleaning_time':'清洁曝光',
'handling':'VTR取放','atr_handling':'ATR取放','atr_empty_ll_to_lp':'ATR从LL空返源端',
'rotation':'半周旋转','atr_travel':'ATR通常移动','vtr_travel':'VTR通常移动',
'alignment':'AL对准','pump':'上锁抽气','vent':'下锁放气','upper_reset':'上锁复位','lower_reset':'下锁复位',
'module_residency':'模块驻留上限','robot_residency':'手上承片上限','horizon':'时域',
'max_pairs':'候选对容量','max_cycles':'每腔候选周期容量','chambers':'设备腔室集合'}

def latex_table(rows, continued=False):
    prefix = r'\addtocounter{table}{-1}'+'\n' if continued else ''
    caption = '批次任务调度的参数与集合配置' + ('（续）' if continued else '')
    label = '' if continued else '\\label{tab:symbol-cn-a}\n'
    body = '\n'.join(' & '.join(row)+r'\\' for row in rows)
    return '\n'.join([r'\begin{table*}[!t]', prefix+r'\centering\small',
        r'\caption{'+caption+'}', label+r'\renewcommand{\arraystretch}{1.03}',
        r'\setlength{\tabcolsep}{4pt}',
        r'\begin{tabular}{@{}p{0.23\textwidth}p{0.15\textwidth}p{0.57\textwidth}@{}}',
        r'\toprule',r'符号或配置项 & 类型 & 定义、取值及生成规则\\\midrule',body,
        r'\bottomrule',r'\end{tabular}',r'\end{table*}'])

def main():
    texpath=PAPER/'JMS_Review_CN.tex'
    tex=texpath.read_text('utf-8')
    match=re.search(r'\\begin\{table\*\}.*?\\label\{tab:symbol-cn-a\}.*?\\end\{table\*\}',tex,re.S)
    assert match
    table2=re.search(r'\\begin\{table\*\}[^\n]*\n(?:(?!\\begin\{table\*\}).)*?\\label\{tab:symbol-cn-b\}.*?\\end\{table\*\}',tex,re.S).group()
    tex=tex[:match.start()]+latex_table(sets)+'\n\n'+latex_table(params,True)+tex[match.end():]
    tex=tex.replace('列出关键参数和变量；其余逻辑量与事件引用在相应约束前定义。',
        '分别列出模型所需的完整参数与集合配置、关键决策变量。表1区分实例给定、规则固定和派生配置，并注明未启用的扩展项；其余逻辑量与事件引用在相应约束前定义。')
    tex=tex.replace('\\subsection{单源与双源物理加工路径}',
        '参数与集合属于建模输入或其确定性派生配置，结果文件保留它们用于复核；求解输出的变量值与这些配置分开记录。候选容量未显式指定时按表1的完整上界生成；缩小容量须声明其受限范围。求解时限、种子、内存和并发数属于实验协议，见计算实验设置，不作为物理模型参数。\n\n\\subsection{单源与双源物理加工路径}',1)
    assert table2 in tex,'Table 2 altered'
    texpath.write_text(tex,'utf-8')
    mdpath=PAPER/'MODEL_EXPLANATION_CN.md'
    md=mdpath.read_text('utf-8')
    start=md.index('## 2.1 ');end=md.index('## 2.2 ',start)
    rows=sets+params
    table='\n'.join('| '+' | '.join(row)+' |' for row in rows)
    new='''## 2.1 全部参数与集合配置

表1按建模需要完整列出集合、实例输入、固定物理规则及其派生配置，默认数值以当前 `Config` 为准。输入集合不等于求解结果；解后确定的集合已单独标注，不要求用户提前枚举。表2仍仅列关键变量。

| 符号或配置项 | 类型 | 定义、取值及生成规则 |
|---------------------------|------------------|-------------------------------------------------------|
'''+table+'''

Table: 模型所需的参数与集合配置

表中数学集合基数的竖线与Markdown表格分隔符无关。每腔4片是基准库存总量配置规则，不是按腔专属分配；两腔共享8片，可用片数还取决于归还时刻。实例允许覆盖默认数值，不能把默认值写成全部实验的共同输入。

代码 `self.H` 表示时域 `horizon`，公式中的$H$才表示清洁阈值；两者不可混淆。资源移动参数在本文式(22)简记为$\\rho_{ii'}$，文稿写作$\\delta^\\rho_{oo'}$。等待集合在文稿记为$\\mathcal W$。

**配置字段覆盖。** 当前 `Config` 的全部27个字段及其表1含义如下；`pjobs`嵌套记录必须含任务ID、模式、允许腔室和产品ID列表。未显式提供Pjob时按代码默认组建，不能误用为已经给定专属腔室资格。

'''
    # Ordinary short paragraphs avoid accidentally introducing a third table.
    for names in [list(fields)[i:i+5] for i in range(0,len(fields),5)]:
        new+='；'.join('`'+k+'`：'+fields[k] for k in names)+'。\n\n'
    new+='''`max_pairs=max_cycles=0`表示自动取完整候选上界，不是零候选。可显式放大容量；小于安全上界时会标记受限候选域。阶段二权重与容差当前在实现中固定；软等待上限是未启用扩展，不在 `Config` 中。求解时限、种子、内存、并发、初始化预算是实验协议，另见实验命令文档。

'''
    # Escape literal cardinality bars in the Markdown table.
    new=new.replace(r'$D=|\mathcal D|$',r'$D=\lvert\mathcal D\rvert$')
    new=new.replace('表中数学集合基数的竖线与Markdown表格分隔符无关。','')
    md=md[:start]+new+md[end:]
    md=md.replace('## 2.2 决策与派生量','## 2.2 关键决策变量与辅助量',1)
    pos=md.index('\n注意$v_p$')
    md=md[:pos]+'\nTable: 批次任务调度的关键决策变量\n'+md[pos:]
    mdpath.write_text(md,'utf-8')
    config=next(n for n in ast.parse((PAPER/'model4_pjob_fifo_20261029/model.py').read_text('utf-8')).body if isinstance(n,ast.ClassDef) and n.name=='Config')
    actual=[n.target.id for n in config.body if isinstance(n,ast.AnnAssign)]
    assert set(actual)==set(fields),(set(actual)-set(fields),set(fields)-set(actual))
    out=Path(__file__).parent/'coverage.json'
    out.write_text(json.dumps(dict(config_fields=actual,coverage=fields,missing=[],
        table1_rows=len(rows),table2_manuscript_unchanged=True),ensure_ascii=False,indent=2),'utf-8')
    print(f'Complete Table 1: {len(rows)} rows, {len(actual)} Config fields; Table 2 retained')

if __name__=='__main__':main()

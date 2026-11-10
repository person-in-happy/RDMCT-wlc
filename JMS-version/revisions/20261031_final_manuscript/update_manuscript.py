"""Apply the evidence-based Chinese final revision to the current user source."""
from pathlib import Path
import hashlib
import json
import re

HERE = Path(__file__).resolve().parent
PAPER = HERE.parents[1]
target = PAPER / 'JMS_Review_CN.tex'
original = (HERE/'original/JMS_Review_CN.tex').read_text('utf-8')
assert hashlib.sha256((HERE/'original/JMS_Review_CN.tex').read_bytes()).hexdigest() == '601c7e3e163007e31fb448fa9123374b51647e6a953bddff6445e2ea95b626d3'
assert target.read_text('utf-8') == original, 'Current source changed after backup'
stats = json.loads((HERE/'statistics.json').read_text('utf-8'))
s = original


def replace(old,new):
    global s
    assert s.count(old)==1, (old[:100],s.count(old))
    s=s.replace(old,new)


# Preserve the user's abstract background and the introduction except the
# explicitly authorized corrections to objective and algorithm-effect claims.
start=s.index('实验中，对330个候选排程')
end=s.index(r'\end{abstract}',start)
s=s[:start]+r'''在4--32片实例的453次完成运行中，441次获得通过原模型检查与独立物理重放的可行排程。八种混合实例的24组阶段内精修均保留产品完工时间上界，总等待下降15.63\%--63.03\%，最大单项等待降至65~s。双源链式实例在保持1213~s产品完工时间的同时，节拍偏差由136~s降至126~s；SPBS组相对串行初始解组的平均完工时间下降1.91\%--9.96\%。结果表明，批次任务编码能够连接产品分组、物理资源约束与具体晶圆排程，两阶段优化能够在产品完工时间优先的条件下改善工序衔接和周期节拍。
'''+s[end:]
replace(r'\sep 学习增强精确优化',r'\sep 两阶段优化')
replace('对于PECVD设备，减少无\n效等待、改善重复生产周期的节拍，特别是JIT的限制，有助于在保证生产节奏稳定的前提下形成可预测的供片与取片安排。',
        '对于PECVD设备，减少无\n效等待、协调重复生产周期的开始间隔，有助于形成可预测的供片与取片安排。')
replace('有序子集，利用A3C算法结合SCIP求解器能够得到大规模MILP问题的精确解，为解决双源混流旋转腔组合设备调度问题提供了思路',
        '有序子集，将A3C学习策略嵌入SCIP的割选择过程，为双源混流旋转腔组合设备调度问题的限时求解提供了思路')
replace('确保产品完工时间优先、等待与节拍满足JIT限制；','保持产品完工时间优先，并通过第二阶段协调工序等待与生产节拍；')
replace('将SPBS初始解策略和角色感知层次割选择策略嵌入HEM算法，同时结合束搜索算法得到大规模MILP求解算法，通过消融验证有限时间内算法的求解效率以及求解质量。',
        '设计结构化可行初始化与时序精修流程，并接入角色感知层次割选择和束搜索，通过初始化与节拍目标消融评价各组成部分的作用。')

# Align the expanded parameter table with the symbols already used in the text.
replace(r'\graphicspath{{figures/pjob_sequence_cn/}{figures/terminology_cn/}{figures/}}',
        r'\graphicspath{{figures/final_results_cn/}{figures/pjob_sequence_cn/}{figures/terminology_cn/}{figures/}}')
s=s.replace(r'\mathcal A_{is}(\gamma)',r'\mathcal A_{i\varsigma}(\gamma)')
s=s.replace(r'\mathcal I_h',r'\mathcal I_{\rm rhythm}')
replace(r'$\mathcal V_c,e,\nu$ & 解后派生区段索引 & 生产任务集$\mathcal V_c$、清洁区段$e$及清洁阶段',
        r'$\mathcal V_c,h,\nu$ & 解后派生区段索引 & 生产任务集$\mathcal V_c$、清洁区段$h$及清洁阶段')
replace(r'$\mathcal D=\{D_1,\ldots,D_D\}$，$D=|\mathcal D|$；基准按每腔4片配置，共享8片，非按腔独占；实现允许$4\le D\le10$。',
        r'$\mathcal D=\{1,\ldots,D\}$为实体辅助晶圆编号集，$D=|\mathcal D|$；存储容量为10片，配置满足$4\le D\le10$，基准采用两腔共享8片。')
replace('辅助片分别来自AS或VS。','辅助片分别来自大气存储区（AS）或真空存储区（VS）。')
replace('当前为不对准，可单独绕过AL或随产品到AL而留在ATR上；旧全片对准选项仅用于历史规则，不能与当前输入混用。',
        '辅助片不执行AL对准，可单独绕过AL入锁，或随产品到AL并在其对准期间留在ATR上。')
replace('当前未加工产品用两只脏手、加工完成产品用两只洁净手，辅助片可用全部四手；旧不区分手的选项属不同物理规则。',
        '未加工产品用两只脏手，加工完成产品用两只洁净手，辅助片可使用全部四只手；允许单元集合按成员类型给定。')
replace('可选软等待上限及超额罚权重；当前默认实现不生成该项。它们不是当前实验必须提供的输入。',
        r'可选软等待上限及超额罚权重，分别为非负实数时长和非负实数权重；本实验取$\lambda_4=0$。')
s=s.replace(r'd^{\rm reset}_{U}',r't_{\rm U}^{\rm reset}').replace(r'd^{\rm reset}_{L}',r't_{\rm L}^{\rm reset}')
replace('因此，正文的派生量数量不能直接当作求解器独立变量的数量。','')
replace('正式主求解释放初始化固定关系，保留全部候选对与周期；初始解补全子问题的最优状态不作为完整问题的最优性证据。上述代入、资源互斥改写和初始化实现分别冻结源码与验证记录，不把旧代数表示下的运行时间直接归入新实现的算法性能比较。',
        '正式主求解释放初始化固定关系，保留全部候选对与周期，由完整模型继续搜索。')
replace(r'第~\ref{sec:model4-ablation-cn}节给出保持产品结构的辅助身份对照。',
        '实验中的物理重放逐项检查跨腔辅助片借用与归还关系。')

body=(HERE/'experiment_section.tex').read_text('utf-8')
refrows=[]
for row in sorted(stats['refinement'],key=lambda r:(r['suite']!='paper',r['n'],r['h'],r['source']=='single')):
    label=(f"{row['n']}/{row['h']}" if row['suite']=='paper' else f"{row['n']}/{row['h']}（资格）")
    origin='单源' if row['source']=='single' else '双源'
    refrows.append(f"{label} & {origin} & {row['c1']:.2f} & {row['c2']:.2f} & {row['wait1']:.2f} & {row['wait2']:.2f} & {row['percent']:.2f}"+r'\\')
body=body.replace('@REFINEMENT_ROWS@','\n'.join(refrows))
initrows=[]
for row in stats['initialization']:
    parts=row['case'].split('_');origin='单源' if parts[-1]=='single' else '双源'
    label=parts[0][1:]+'/'+parts[1][1:]
    initrows.append(f"{label} & {origin} & {row['serial']:.2f} & {row['spbs']:.2f} & {row['percent']:.2f}"+r'\\')
body=body.replace('@INITIALIZATION_ROWS@','\n'.join(initrows))
scalerows=[]
for row in stats['scale32']:
    recipe=row['case'].split('_')[2]
    label={'4x1':r'$4\times1$','2x2':r'$2\times2$','mixed':'混合'}[recipe]
    status='内存限额' if row['status']==['memlimit'] else '时间限额'
    scalerows.append(f"{label} & {row['variables']} & {row['constraints']} & {row['x_variables']} & {row['peak_gib']:.2f} & {row['cmax']:.0f} & {status}"+r'\\')
body=body.replace('@SCALE_ROWS@','\n'.join(scalerows))
assert not re.search(r'@[A-Z_]+@',body)
start=s.index(r'\section{计算实验与结果分析}')
end=s.index(r'\section*{CRediT作者贡献声明}',start)
s=s[:start]+body+'\n'+s[end:]

assert s[s.index(r'\section*{CRediT作者贡献声明}'):]==original[original.index(r'\section*{CRediT作者贡献声明}'):]
assert not any(term in s for term in ('匿名','模型4','模型2','330个候选','305个','39.76','93.64'))
assert not any(ord(c)<32 and c not in '\r\n\t' for c in s)
target.write_text(s,'utf-8')
(HERE/'applied_experiment_section.tex').write_text(body,'utf-8')
print('Updated Chinese manuscript; author declarations and references preserved.')

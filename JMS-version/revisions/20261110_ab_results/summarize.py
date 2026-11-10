"""Build the complete audit note; keep diagnostic detail outside the manuscript."""
from pathlib import Path
from collections import defaultdict, Counter
from statistics import mean
import json

OUT = Path(__file__).resolve().parent
JMS = OUT.parents[1]
e = json.loads((OUT / 'evidence.json').read_text(encoding='utf-8'))
a = [r for r in e['rows'] if r['suite'] != 'mechanism']
b = [r for r in e['rows'] if r['suite'] == 'mechanism']
notes = []
for r in e['rows']:
    if not r['valid']:
        continue
    data = json.loads((JMS / 'results' / r['campaign'] / 'runs' / r['id'] / 'result.json').read_text(encoding='utf-8'))
    points = sorted((j[k], delta) for j in data['jobs'] if not j['product']
                    for k, delta in (('loan_start', 1), ('loan_end', -1)))
    # Same 2e-4 s tolerance as independent physical validation. Coalesce nearly
    # identical endpoints; do not change the saved schedule or frozen metrics.
    groups = []
    for t, delta in points:
        if groups and t - groups[-1][0] <= 2e-4:
            groups[-1][1] += delta
        else:
            groups.append([t, delta])
    current = peak = 0
    for t, delta in groups:
        current += delta
        peak = max(peak, current)
    assert current == 0 and peak <= r['config']['dummy_count'], r['id']
    if peak != r['metrics']['peak_auxiliary_loans']:
        notes.append(dict(campaign=r['campaign'], id=r['id'], inventory=r['config']['dummy_count'],
                          raw_peak=r['metrics']['peak_auxiliary_loans'], tolerant_peak=peak))
(OUT / 'inventory_endpoint_checks.json').write_text(json.dumps(dict(tolerance_seconds=2e-4,
    checked_schedules=sum(r['valid'] for r in e['rows']), differences=notes,
    original_results_modified=False), ensure_ascii=False, indent=2), encoding='utf-8')

lines = ['# A/B实验复核与入稿记录（2026-11-10）', '',
    '对象：[当前中文稿](../../JMS_Review_CN.tex)。原稿、PDF和文档备份见[before/](before/)。'
    '本次只更新当前中文稿及其PDF、审查和命令文档；不改动`JMS/`副本、冻结实验或正在运行的C批次。', '',
    '## 已采用的结论', '',
    '1. **跨训练种子的初始化收益。** 正常分离合并168次运行，仍为四个实例。'
    '学习方法包含训练种子1/2/3和求解种子1/2/3，SCIP仅保留三个求解种子。'
    '两个混合实例中，加SPBS的平均产品完工优于对应无SPBS臂，方向在三个训练种子下保持一致。',
    '2. **库存影响已证最优值。** 单产品2×2的4片/8片库存对应309/303 s，改善6 s（1.94%）；'
    '两个清洁阈值和两种规则下成立。纯4×1均为296 s。结论限定该合成场景。',
    '3. **有限库存下的耦合约束。** H=2的单产品2×2获得11份耦合排程；'
    '4片库存的五份排程均为四个辅助身份、9次借用、5次重复借用。', '',
    '正文新增两小节、两张表，更新摘要和结论。完整覆盖、无解与超时明细保留在本记录；'
    '正文没有增加普遍学习优势、严格限时加速或多产品模式最优排序的主张。', '',
    '## 完整审计与覆盖', '',
    f'检查312次记录，重新验证221份有效赋值，核对{len(e["hashes"])}个唯一文件哈希。'
    '验证包括完整原始D约束、独立物理重放、清洁原触发规则、输入一致性、LP哈希、'
    '策略检查点、预算和退出码。未调用优化或训练，未重新生成LP。', '',
    '| 批次 | 完成/计划 | 最优 | 限时可行 | 限时无可行解 | 有效排程 |',
    '|---|---:|---:|---:|---:|---:|',
    '| A复用父批次 | 72/72 | 36 | 36 | 0 | 72 |',
    '| A新增 | 96/96 | 48 | 48 | 0 | 96 |',
    '| B | 144/144 | 44 | 9 | 91 | 53 |', '',
    '以上“最优”为该配置和清洁规则下完整主问题的求解证明。B的8个单产品配置×2规则均至少一次闭合上下界；'
    '并非每个种子都证明最优。全部运行退出码为0，未触发动态内存保护；B保留一次中断尝试的归档。', '',
    '## A：完整配对统计', '',
    '| 实例 | 方法 | 无SPBS均值/s | 有SPBS均值/s | 每格重复数 |',
    '|---|---|---:|---:|---:|']
for case in sorted({r['case'] for r in a}):
    for method in ('scip', 'hem', 'proposed'):
        rr = [[r for r in a if r['case'] == case and r['arm'] == method + '_' + arm] for arm in ('plain', 'spbs')]
        lines.append(f'| {case} | {method} | {mean(r["metrics"]["product_cmax"] for r in rr[0]):.2f} | '
                     f'{mean(r["metrics"]["product_cmax"] for r in rr[1]):.2f} | {len(rr[0])} |')
lines += ['', '预设主比较proposed+SPBS对HEM+SPBS：先对实例内的成对种子求相对差，再对四实例取平均。'
          '平均增益0.0600%，中位数0，胜/平/负为1/3/0；描述性实例bootstrap 95%区间[0, 0.1801]%。'
          '按训练种子分组为0.1801%、0、0。无SPBS的proposed对HEM平均为−0.0148%，胜/平/负0/3/1。'
          '这支持初始化收益，但没有建立稳定的学习扩展优势。', '',
          'SPBS起点在2片混合上为511/505/511 s，4片混合为541 s。'
          '共同输入不含原始离线构造成本；60+240与300 s是名义分段预算，非统一端到端墙钟比较。', '',
          '## B：全部配置的上下界与覆盖', '',
          '每个配置的每规则运行三次；下表LB取三次中的最大有效下界，UB取最小有效上界，单位s。'
          '这是同一冻结MILP的证书汇总，不是将三个600 s运行合并为单次预算成绩。'
          '“—”表示未找到上界，不能据此判为不可行。', '',
          '| 配置 | 可选规则有效/3 | 可选[LB,UB] | 原规则有效/3 | 原规则[LB,UB] |',
          '|---|---:|---:|---:|---:|']
bt = {(r['case'], r['arm']): r for r in e['b_table']}
fmt = lambda v: '—' if v is None else f'{v:.2f}'
for case in sorted({r['case'] for r in b}):
    x, y = bt[case, 'optional'], bt[case, 'legacy']
    lines.append(f'| {case} | {x["valid"]}/3 | [{fmt(x["best_bound"])},{fmt(x["best_upper"])}] | '
                 f'{y["valid"]}/3 | [{fmt(y["best_bound"])},{fmt(y["best_upper"])}] |')
lines += ['', 'B共9/24配置取得排程：8个单产品配置和2片混合/H3/8片辅助配置。'
          '后三者中的“两片混合”三种子：可选规则514/518/511 s，原规则518/514.26/514 s，未闭合上下界，'
          '故未据此宣称提前清洁提高最优质量。三个配置共同复用旧输入：1片4×1/H3/D8、1片2×2/H2/D8、'
          '2片混合/H3/D8；其他配置共同冷启动。', '',
          '11份连续加工/清洁/复用见证均为单产品；53份有效排程的节拍中心均为0。'
          '3份纯4×1可选规则结果含提前清洁，但产品最优值与原规则相同。'
          '这些证据未补齐多产品长链、当前D节拍权重消融或100片当前D排程。', '',
          '## 预算、计数与保留记录', '',
          '| 批次 | 单元 | 主求解/s | 名义预算/s |', '|---|---|---:|---:|']
for r in e['budget_overruns']:
    lines.append(f'| {"A" if "backfill" in r["campaign"] else "B"} | {r["id"]} | {r["seconds"]:g} | {r["allotted"]:g} |')
lines += ['', 'A两次主阶段超限3/5 s，B九次超限2–123 s。原记录完整保留，本次未查明其系统或计时根因。'
          '这些运行不被用作严格等墙钟效率证据。B九次超限均无可行解，不影响单产品最优证书。', '',
          '借还峰值另做容差复核：[inventory_endpoint_checks.json](inventory_endpoint_checks.json)。'
          '两份排程的原始逐端点峰值受浮点误差影响。例如D4/H2/可选规则/种子3中，同一D2的归还172.0000000000109 s、再借172.00000000000995 s'
          '仅差约9.4×10⁻¹³ s；原始逐端点排序给出峰值5，按物理验解2×10⁻⁴ s容差合并端点为4。'
          '全部221份有效排程的容差峰值均未超过库存。原始统计和正在使用的冻结入口不变；正文未引用该原始峰值。', '',
          '## 修改、复现及尚待完成', '',
          '- [audit.py](audit.py)：仅审计三批已完成记录；[evidence.json](evidence.json)保留逐次检查、哈希和全量数据。',
          '- [tables.json](tables.json)：按模型配置、方法、训练种子聚合的完整表。',
          '- [before/](before/)：修改前原稿、PDF和命令/审查文档。',
          '- [final_checks.json](final_checks.json)：编译、数值对应、原始数据保存和版面检查。',
          '- C资格搜索及后续transfer/chain/rhythm不属于本次结论，完成后另行审计。',
          '- 代表性实例、端到端预算、多产品连续链、当前D大规模排程与第三创新点算法实现仍需后续研究。', '',
          '本轮未新增外部文献事实或重新评估期刊要求；仅将本地已验证实验与当前稿件对齐。']
text = '\n'.join(lines) + '\n'
text = text.replace('后三者中的“两片混合”三种子', '其中两片混合的三个求解种子')
(OUT / 'REVIEW_AB_CN.md').write_text(text, encoding='utf-8')
print(json.dumps(dict(report='REVIEW_AB_CN.md', verified_rows=312, fresh_assignments=221,
                      endpoint_metric_differences=notes), ensure_ascii=False))

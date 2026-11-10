"""Finish manuscript provenance checks and package validated deliverables.

Read-only with respect to solver code, campaigns, and raw experiment outputs.
No optimization or experiment launcher is called.
"""
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
import difflib
import hashlib
import json
import re
import zipfile

import pymupdf

HERE = Path(__file__).resolve().parent
PAPER = HERE.parents[1]
ROOT = PAPER.parent


def read(path):
    return json.loads(path.read_text('utf-8'))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', 'utf-8')


source = PAPER / 'JMS_Review_CN.tex'
pdf = PAPER / 'JMS_Review_CN.pdf'
text = source.read_text('utf-8')
original = (HERE / 'original/JMS_Review_CN.tex').read_text('utf-8')
audit = read(HERE / 'newrule_validation.json')
derived = read(HERE / 'derived_checks.json')
build = read(PAPER / 'output/model4_cn_build/build_report.json')
assert sha(source) == build['source_sha256']
assert sha(pdf) == build['pdf_sha256']
assert sha(PAPER / 'output/pdf/JMS_Review_CN.pdf') == sha(pdf)
assert build['pages'] == 16
assert all(build[k] == 0 for k in ('undefined_references', 'overfull_boxes', 'duplicate_labels'))
assert len(pymupdf.open(pdf)) == 16

equations = lambda s: re.findall(r'\\begin\{equation\}.*?\\end\{equation\}', s, re.S)
assert equations(text) == equations(original)
assert len(equations(text)) == 39
assert text.split('\\begin{abstract}')[0] == original.split('\\begin{abstract}')[0]
abstract_opening = lambda s: s.split('\\begin{abstract}\n', 1)[1].split('\n', 1)[0]
assert abstract_opening(text) == abstract_opening(original)
intro = lambda s: s.split('\\section{引言}', 1)[1].split('\\section{双源混流旋转腔组合设备调度模型}', 1)[0]
intro_lines = lambda s: [line for line in intro(s).splitlines() if not line.startswith('\\item 设计结构化')]
assert intro_lines(text) == intro_lines(original), 'Unexpected introduction changes'
assert text.split('\\section*{CRediT作者贡献声明}', 1)[1] == original.split('\\section*{CRediT作者贡献声明}', 1)[1]
citations = set(k.strip() for group in re.findall(r'\\cite\w*(?:\[[^\]]*\])*\{([^}]+)\}', text) for k in group.split(','))
bibliography = re.findall(r'\\bibitem\{([^}]+)\}', text)
assert len(bibliography) == 31 and citations == set(bibliography)
assert all(term not in text for term in ('匿名', '模型4', '模型2'))
assert '非递减' in text and '同一PW对内同步取片' in text

assert not audit['failures'] and audit['assignments_checked'] == 180
assert audit['original_models_built'] == 25 and audit['optimization_calls'] == 0
assert sha(PAPER / 'model4_pjob_nondecreasing_20261102/model.py') == audit['model_sha256']
assert sha(PAPER / 'model4_pjob_nondecreasing_20261102/pjob_order.py') == audit['release_code_sha256']
for relative, expected in audit['hashes'].items():
    assert sha(ROOT / relative) == expected, relative
old_audit = read(HERE / 'audit_results.json')
for relative, expected in old_audit['raw_file_hashes'].items():
    path = Path(relative)
    assert sha(path if path.is_absolute() else ROOT / path) == expected, relative
for relative, expected in derived['sequence_hashes'].items():
    assert sha(ROOT / relative) == expected, relative
for example in derived['sequence_examples']:
    assert sha(ROOT / example['file']) == example['sha256'], example['file']
assert len(derived['phase_pairs']) == 30
assert len(derived['ablation']) == 12
assert len(derived['cleanup']) == 42 and derived['cleanup_improved'] == 16
assert len(derived['sequence_examples']) == 36

campaign = PAPER / 'results/nondecreasing_followup_exact_20261102_205212'
spec = read(campaign / 'campaign.json')
assert sha(campaign / 'campaign.json') == read(campaign / 'contract.json')['campaign_sha256']
assert read(campaign / 'finished.json')['complete'] == 24
for relative, expected in spec['assets'].items():
    assert sha(ROOT / relative) == expected, relative
    assert sha(campaign / 'frozen_code' / relative) == expected, relative
primary = [r for r in audit['rows'] if r['category'] == 'new_exact' and r['cell']['kind'] == 'exact']
assert len(primary) == 16 and all(r['valid'] for r in primary)
states = Counter(r['evidence']['state'] for r in primary)
assert states['optimal'] == 5
by_case = {}
for row in primary:
    by_case.setdefault(row['cell']['case'], {})[row['cell']['arm']] = row
equal_optimal = []
for case, arms in by_case.items():
    assert set(arms) == {'pjob', 'wafer'}
    if all(r['evidence']['state'] == 'optimal' for r in arms.values()):
        assert abs(arms['pjob']['evidence']['upper_bound'] - arms['wafer']['evidence']['upper_bound']) < 1e-5
        equal_optimal.append(case)
assert len(equal_optimal) == 2
table = text.split('\\label{tab:representation-cn}', 1)[1].split('\\end{table*}', 1)[0]
case_order = ('n1_H3_4x1_dual', 'n1_H2_2x2_dual', 'n2_H3_4x1_dual',
              'n2_H2_2x2_dual', 'n2_H3_mixed_dual', 'n4_H3_mixed_dual',
              'n2_H3_4x1_dual_same_lp', 'n2_H2_2x2_dual_same_lp')
table_lines = [line for line in table.splitlines() if re.match(r'^[124]/', line)]
assert len(table_lines) == 8
for case, line in zip(case_order, table_lines):
    cols = [s.strip() for s in line.rstrip('\\').split('&')]
    for arm, offset in (('pjob', 2), ('wafer', 5)):
        ev = by_case[case][arm]['evidence']
        assert cols[offset] == f"{ev['lower_bound']:.2f}"
        assert cols[offset + 1] == f"{ev['upper_bound']:.2f}"
        assert cols[offset + 2] == ('最优' if ev['state'] == 'optimal' else '限时可行')

# Snapshot only; do not invoke commands that regenerate running-campaign summaries.
active = PAPER / 'results/pjob_nondecreasing_paper_all_20261102_231102'
coverage = read(active / 'summary/coverage.json')
progress = read(active / 'progress.json')
now = datetime.now(timezone.utc).isoformat()
active_states = Counter(x['state'] for x in progress['cells'].values())
snapshot = dict(captured_utc=now, campaign=str(active.relative_to(ROOT)),
                coverage=coverage, scheduler_states=dict(active_states),
                included_in_manuscript=False)
save(HERE / 'active_campaign_snapshot.json', snapshot)

report = f'''# 中文稿结果更新与复核记录

核验时间（UTC）：{now}

## 本轮采用的规则和筛选依据

当前稿采用全Pjob取片开始时刻非递减规则；同Pjob、同LP、同PW对的两片产品允许同步取片。依据为独立非递减实现及其冻结实验配置。本轮保留这一版本的模型、编码、解码与39个编号公式。

“满足新版”按模型约束、物理重放和指标口径判断，不按结果是否有利判断。新版成员表示对照完整保留八种配置的16次主求解，包括限时可行结果。历史排程经过新版完整赋值验解后，仅用于具体排程的物理指标；历史求解时间、下界、最优性、不可行性和方法排名不转移为新版结论。

## 已写入正文的证据

| 证据 | 覆盖与检查 | 正文采用的结论 |
|---|---|---|
| 新规则完整模型对照 | 8个公共起点补全、16次主求解，24项完成；16次主求解全部可行、5次最优 | 两种成员表示在单片及同LP双片4×1配置分别证明296 s、324 s最优；完整列出全部上下界和停止状态 |
| 同Pjob同步取片 | 同LP双片Pjob排程，完整模型和物理重放均通过 | 两片在0 s同时取片、104–284 s加工、324 s回片 |
| 双腔生产 | 新规则跨LP双片逐片排程回填Pjob模型；另验证专属腔室资格见证 | 两腔生产区间87–267 s及104–284 s，重叠163 s |
| 时序精修 | 24组基础、6组资格输入与输出；核对完工时间上界和产品流经时间分解 | 基础实例均值总路线等待下降15.63%–63.03%；产品与辅助片等待分开解释 |
| 节拍项消融 | 12组相同实例、种子和初始结构的三目标对照 | 双源链式实例等待522→542 s、节拍偏差136→126 s；写明权衡和评价中心数 |
| 驻留见证 | 5份有完整赋值且在新模型中验解通过的排程 | 4片双源在250 s共同驻留上限下以542 s完成产品回片 |
| 输出收尾 | 42组输入输出；检查产品完工时间、完整二阶段目标及全部动作完工边界 | 16组缩短全部动作完工时间，26组保持 |
| 可行序列构造 | 7402条导出顺序检查；36份代表性完整排程按新规则重放 | 明确区分导出数量与构造族下界，未作为大规模优化性能结果 |

本轮构建25个新规则原模型，检查180份完整赋值，失败数0；另独立核对8份逐片表示的显式身份与解码映射。180为赋值检查数，并非180个独立实验。36份序列例子另作物理重放。核验脚本禁止调用优化器，未启动正式实验。

## 已修正的审稿风险

1. 规则版本混用：新完整对照替代旧严格顺序的最优性表，删除旧计时、内存、初始化排名和学习性能结论。
2. 将可行排程写成最优：对照表分别列明下界、上界及最优/限时可行；驻留与资格排程表述为经验证的具体排程。
3. 同步与并行只有概念图：新增由实际事件生成的同步取片与双腔加工图，核对产品、辅助片和共享资源。
4. 缩减身份变量被解释为整体变量成比例缩减：同时报告8→4的成员选择列及完整模型3225→3219等维数，说明压缩位置。
5. 总等待降幅被误认为产品流经时间降幅：拆分产品与辅助片，并单列产品腔内驻留和流经时间。
6. 节拍改善被误认为所有指标同时下降：正文直接给出20 s等待差异与10 s节拍偏差下降。
7. 收尾极大降幅受时间域松弛影响：删除以松弛时刻为基准的夸大百分比，报告完成边界和保留目标上界的42组检查。
8. 将序列样本数写成全部可行解数：使用“导出总数”和“构造族下界”，不计连续时刻扰动。

## 仍可能被审稿人追问的点

- **更大规模、端到端方法效果。** 当前正文不据历史计时推出新版提速或算法优势。若要加入这类结论，需要完成相同新规则、相同起点与预算的对照。正在运行的102项主实验尚未完整，不能用部分单元代替整组结论。
- **同步取片是否总能缩短产品完工时间。** 当前实例证明同步操作可实现；同LP双片逐片表示采用0和14 s取片也达到324 s最优，因此不宣称同步必然带来完工时间优势。
- **成员表示对照是否证明一般计算优势。** 八种配置各一个求解种子主要验证表示和可行映射；5次最优、11次限时可行不支持普遍提速或统计显著性结论。正文完整保留较差上界，未按表现筛除。
- **历史精修结果是否等同于新版算法重新运行。** 本轮将输入和输出完整回填新模型，证明其可行性及报告指标；这支持给定结构下的时序比较，不等同于对新版搜索过程、运行时间或整个可行域重新求最优。
- **驻留表是否确定可行边界。** 五份排程证明列示条件可行。旧严格顺序单源250 s的固定结构不可行结果未在新规则下重证，未纳入表，也未据此判定新规则单源不可行；该表不承担完整参数扫描或模式优越性比较。
- **可选学习割是否有效。** 当前稿仅保留接口描述，无学习性能优势结论；没有此类结论就不需要为本轮正文增设学习性能实验。

这些事项记录于独立审查文件；正文保持由数据直接得出结论的写法。本轮没有检查外部期刊投稿系统，也没有重新在线逐条核验文献元数据；完成的是当前稿的引用完整性、结果可追溯性、模型一致性及页面检查。

## 正在运行实验的只读快照

- 路径：`{active.relative_to(ROOT)}`。
- 当前覆盖记录：期望{coverage['expected']}项，完成观察{coverage['complete_observations']}项；状态为`{json.dumps(coverage['states'], ensure_ascii=False)}`。
- 调度器状态：`{json.dumps(dict(active_states), ensure_ascii=False)}`。
- 快照时间见本文件首部；状态可能继续变化。未修改控制器、输入、启动脚本、共享路径或原始结果，未将部分结果计入正文。
- 当前正文不需要另开重复主实验。已有命令入口见`JMS-version/NONDECREASING_RERUN_COMMANDS_CN.md`；其中列出的全套实验范围不表示本轮均须补跑。待当前主实验结束后，先核对完整覆盖和新规则验解，再决定是否扩展正文结论。

## 文件与复核方法

- `newrule_validation.json`：180份赋值的新模型验解、物理重放、模型哈希与360份原始结果/变量文件哈希。
- `derived_checks.json`：阶段配对、目标上界、节拍对照、序列计数及例子重放。
- `audit_results.json`：历史四批补强实验的冻结记录；只作来源追溯，非本轮全部纳入正文的结果。
- `completion_review.json`：最终源稿/PDF、引用、公式、数据哈希及编译检查。
- `manuscript.patch`：对本轮修改前备份的完整差异。
- `active_campaign_snapshot.json`：在跑实验只读快照。

中文稿16页，XeLaTeX连续编译3遍；未解析引用、重复标签和越界盒均为0。31项参考文献均在正文引用，无需删除条目。逐页总览及重点页面放大检查完成，包括摘要、结果表、事件图和参考文献。保留已写摘要开头、引言主体及作者声明；另一份中文稿与英文稿均未同步。
'''
(HERE / 'REVIEW_CN.md').write_text(report, 'utf-8')
(HERE / 'CHANGES_CN.md').write_text('''# 本轮修改清单

- 采用现行非递减取片规则，保留建模、输入编码及末端解码的已修订定义。
- 摘要实验证明、引言第三项贡献、实验部分和结论更新为新版有效证据；保留摘要开头和引言主体。
- 完整纳入新版8种配置、16次主求解的上下界与状态，增加同Pjob同步取片和双腔重叠事件图。
- 保留通过新版完整验解的时序、驻留及收尾排程；不沿用旧规则的求解计时、最优性和不可行性结论。
- 删除旧方法排名、学习性能、阈值曲线和大规模优化性能的未匹配论述，压缩可选选割说明。
- 拆分产品路线等待、腔内驻留及流经时间；报告节拍权衡和收尾目标上界检查。
- 保留全部39个编号公式和31项仍被引用的参考文献；未修改另一份中文稿、英文稿、求解源码、启动器或原始结果。
- 生成16页PDF、审查记录、结果核验记录及可复现源文件包。本轮不启动新的优化实验。

历史排程的保留依据为新版完整可行性检查，不能据此把历史求解过程称为新版算法重跑。详情见同目录REVIEW_CN.md。
''', 'utf-8')
(HERE / 'manuscript.patch').write_text(''.join(difflib.unified_diff(
    original.splitlines(True), text.splitlines(True),
    fromfile='original/JMS_Review_CN.tex', tofile='JMS-version/JMS_Review_CN.tex')), 'utf-8')
completion = dict(completed_utc=now, source_sha256=sha(source), pdf_sha256=sha(pdf),
    pages=16, equations_preserved=39, references=31, missing_citations=0,
    unused_references=0, abstract_opening_preserved=True, introduction_only_contribution_updated=True,
    declarations_preserved=True, raw_assignment_files_unchanged=len(audit['hashes']),
    historical_files_unchanged=len(old_audit['raw_file_hashes']),
    new_rule_assignments_checked=180, new_rule_assignment_failures=0, original_models_built=25,
    explicit_wafer_identity_checks=8, representative_sequence_replays=36,
    primary_runs=16, primary_states=dict(states), paired_equal_optima=equal_optimal,
    build=build, active_campaign=snapshot, formal_experiments_started=0,
    optimization_calls=0, visual_review=dict(contact_pages=list(range(1,17)),
    enlarged_pages=[1,13,14,15,16], witness_figure_reviewed=True),
    report_sha256=sha(HERE/'REVIEW_CN.md'), derived_checks_sha256=sha(HERE/'derived_checks.json'),
    full_assignment_audit_sha256=sha(HERE/'newrule_validation.json'))
save(HERE / 'completion_review.json', completion)

files = {source: 'JMS_Review_CN.tex', pdf: 'JMS_Review_CN.pdf'}
for name in re.findall(r'\\includegraphics(?:\[[^\]]*\])?\{([^}]+)\}', text):
    candidates = list((PAPER/'figures').rglob(name+'.pdf'))
    assert candidates, name
    for path in candidates:
        files[path] = path.relative_to(PAPER).as_posix()
for name in ('REVIEW_CN.md','CHANGES_CN.md','completion_review.json','newrule_validation.json',
             'derived_checks.json','active_campaign_snapshot.json','manuscript.patch',
             'audit_newrule.py','derive_checks.py','plot_witness.py','finalize_review.py'):
    files[HERE/name] = 'review/'+name
readme = '''# 中文稿与本轮核验材料

JMS_Review_CN.tex及PDF为本轮中文结果更新版。保留非递减取片规则，仅采用新版正式结果或通过新版完整验解的物理排程指标。

编译：在本目录运行三遍 `xelatex -interaction=nonstopmode -halt-on-error JMS_Review_CN.tex`。需要elsarticle、ctex及Fandol字体等标准TeX发行版组件。五幅PDF图随包提供。

review目录包含差异、审查报告及核验记录。审查脚本依赖原项目及其完整原始结果，压缩包不包含求解环境、全部原始实验或在跑实验。通过记录中的路径、冻结配置和SHA-256可定位原始证据。

正在运行的102项主实验未纳入本轮正文；详见review/REVIEW_CN.md的带时间快照。该状态不影响本包内已完成对照和已验证排程的核验记录。
'''
manifest = {archive:sha(path) for path,archive in files.items()}
manifest['README_CN.md'] = hashlib.sha256(readme.encode('utf-8')).hexdigest()
output = PAPER / 'output/JMS_CN_newrule_results_20261102.zip'
with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_DEFLATED) as z:
    for path, archive in files.items():
        z.write(path, archive)
    z.writestr('README_CN.md', readme)
    z.writestr('manifest_sha256.json', json.dumps(manifest, ensure_ascii=False, indent=2)+'\n')
with zipfile.ZipFile(output) as z:
    assert z.testzip() is None
    for name, expected in manifest.items():
        assert hashlib.sha256(z.read(name)).hexdigest() == expected
save(HERE / 'package_receipt.json', dict(path=str(output.relative_to(ROOT)),
     sha256=sha(output), files=len(manifest)+1, bytes=output.stat().st_size,
     source_sha256=sha(source),pdf_sha256=sha(pdf),created_utc=now))
print(json.dumps(dict(pages=16, assignments=180, primary_states=dict(states),
    references=31, active_complete=coverage['complete_observations'],
    package=str(output), package_bytes=output.stat().st_size), ensure_ascii=False, indent=2))

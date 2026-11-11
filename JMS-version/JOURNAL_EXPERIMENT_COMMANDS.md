# 期刊补充实验状态与后续缺口（更新：2026-11-11）

**100片目标另行执行：** 当前transfer冻结为6个合格实例、432个单元，实际全为2片，不会生成100片混合加工与清洁排程；原清单A—E也未覆盖100片。新增[100片持续求解与甘特图自动更新命令](LARGE_SCHEDULE_COMMANDS.md)使用隔离输出，可与现有批次并行并调用GPU策略，不设置固定内存配额。--until-optimal不设时间或节点上限，资源不足会提示；找到通过验证的可行解即自动出图，改善后更新原路径，完整主问题证明结束后再改为“全局最优”标注。本次仅预检，未启动100片优化，不能保证现有硬件必能完成证明。

文稿的2片资源排程图已换为当前模型完整复验通过的16片、920 s可行排程，未证最优，未计入A—E算法对照。

**A、B已完成并复核入稿。** A新增96/96完成，合并原72次后为168份有效排程；B为144/144完成、53份有效排程。新增正文聚焦跨训练种子的初始化收益和库存/模式配对结论，见[本轮审查](revisions/20261110_ab_results/REVIEW_AB_CN.md)。A、B无需再运行start或resume。C及后续批次不计入本次入稿证据。

五个补充批次237/237已完成，228份可行排程全部重新通过原始完整模型赋值检查及物理重放。结论已补入 [JMS_Review_CN.tex](JMS_Review_CN.tex)，全文审查见 [JOURNAL_REVIEW_CN.md](JOURNAL_REVIEW_CN.md)。

| 实验 | 完成/计划 | 有效排程 | 后续处理 |
|---|---:|---:|---|
| 根分离算法/组件 | 108/108 | 108 | 已入稿，不重跑 |
| 正常分离设置 | 72/72 | 72 | 已入稿，不重跑 |
| 固定/联合结构 | 36/36 | 36 | 已入稿，不重跑 |
| 收尾对照 | 12/12 | 12 | 无额外改善，已如实入稿 |
| 节拍见证搜索 | 9/9 | 0 | 未取得见证，不能启动后续权重消融 |

**2026-11-09第二轮补充：** 已复用旧D的1片2×2/H=2排程补入清洁、连续加工与辅助复用见证，见新图及表。新入口 [journal_support_experiments.py](tools/journal_support_experiments.py) 已实现，以下命令补第2、3项证据，**本轮没有启动正式实验**。既有237次结果及冻结入口不变。详细设计和解释边界见 [补充协议](revisions/20261109_coupling_transfer/SUPPLEMENT_PROTOCOL_CN.md)。

两次超限已披露：根分离4片混合SCIP种子1实际428 s，设置300 s；节拍搜索4片纯2×2种子3实际802 s，设置600 s。保留原记录，先查明预算执行/记账问题，不能仅用命令参数宣称实际等时。

E机制与旧100片结果继续按原模型归属复用。后续新实验仍应使用可见前台、隔离输出、动态系统内存余量保护，不采用固定SCIP/RSS内存配额。没有必要为填表重跑旧固定内存批次。

如需复核最新A/B审计，在可见PowerShell中执行以下命令；它检查312次记录（含复用的72次）、重建221份有效赋值、重算指标与哈希，**不调用优化、不生成共享LP**，只读取这三个已完成批次：

```powershell
Set-Location D:\git\git\RDMCT-A3C
& 'G:\conda\envs\a3cenv\python.exe' -X utf8 -u JMS-version/revisions/20261110_ab_results/audit.py
```

该命令更新审计目录，不改实验原始数据。旧`20261109_journal_results/audit.py`会扫描全部journal批次，现有未完成批次时不应再使用它作全目录审计；旧`revise.py`也不应覆盖后续修订稿。

## 新实验的公共设置

以下命令在**可见PowerShell前台**运行。每10 s显示完成/失败数、当前耗时、RSS与预计剩余时间；同一时刻一个工作进程、SCIP单线程，避免学习策略争用同一GPU。`limits/memory`保持SCIP原生无限哨兵值，**没有固定SCIP内存或进程RSS配额**；仅在系统可用RAM低于10%时停止当前单元并保留记录。输出隔离、模型/输入/检查点哈希冻结，所有有效输出须通过完整原始D赋值检查和物理重放。

`--time-limit`是求解器预算；`--wall-limit`是含建模/验证的异常保护上限，**不是等墙钟算法预算**。本轮未解决上次第1项端到端预算缺口。超限照实记入`budget_overrun_seconds`，不能把它们当作严格限时证据。`prepare`、`plan`、`check`均不求解；`start`建立新批次并开始运行，`resume`只能使用原冻结设置。不要把下列`start`作用于已经存在的目录。

```powershell
Set-Location D:\git\git\RDMCT-A3C
$py = 'G:\conda\envs\a3cenv\python.exe'
$entry = 'JMS-version/tools/journal_support_experiments.py'
```

## A. 先补训练重复：只新增96次，复用原72次

**当前状态（2026-11-10核对）：本批96/96完成、0失败；合并原72次后168份赋值全部重新通过完整D模型与物理重放。已入稿，无需重跑。** 下列命令仅重建汇总报告。

沿用四个旧实例、正常分离、300 s名义预算和原输入。仅补HEM/proposed、有/无SPBS的训练种子2、3，求解种子1、2、3；SCIP与训练种子1不重跑。报告自动合并为168行、仍只有**4个实例**。这只能检查检查点敏感性，不能替代新测试集；不能据结果选择最好训练种子再投稿。

```powershell
& $py -X utf8 -u $entry report --campaign JMS-version/results/journal_d_backfill_standard_20261109_r1
```

原冻结设置为300 s名义求解预算、1800 s墙钟保护；没有固定内存配额。初始化收益及跨训练种子汇总已写入文稿。

## B. 清洁规则、加工模式场景与辅助库存对照：144次

**当前状态（2026-11-10核对）：144/144完成，0失败、0待运行；44次最优、9次限时可行、91次限时无可行解。53份有效赋值全部重新通过完整D模型与物理重放。** 单产品库存敏感性、两工艺场景的已证最优值及11份耦合见证已用于正文；完整覆盖和异常另存审查记录。原中断单元已重跑完成，旧尝试保留在`interrupted_attempts/`，无需再resume。

六个工作负载：1片纯4×1、1片纯2×2、2片混合、4片纯4×1、4片纯2×2、4片混合；每个交叉`H={2,3}`、辅助片数`{4,8}`，得24配置。每配置比较可选提前清洁与原H/H−1触发规则，三个求解种子。两规则使用同一完整候选空间；若有完全同配置且两规则均接受的旧输入，则共同复用，否则共同冷启动。阶段二关闭以隔离主目标。

```powershell
& $py -X utf8 -u $entry report --campaign JMS-version/results/journal_d_mechanism_20261109_r1
```

该命令仅重建已完成批次的报告。原冻结设置为600 s求解预算、2400 s墙钟保护和动态系统内存保护，无固定内存配额。其他批次如发生中断，按文末“状态、恢复与预检”检查，不照搬已完成B批次的历史恢复步骤。

名义求解预算总和24 h。报告清洁次数/提前清洁次数、连续产品PW对数、辅助借用/复用/并发峰值、产品完工和全部占用结束，以及上下界。纯4×1与纯2×2是**累计加工时长均为180 s的两种合成工艺场景**；尚无工程依据认定现实产品可任意切换两种工艺，不写成实际产线工艺优劣结论。只有有效上下界足以分离时才作最优排序。不得将“8片库存时只用7片”解释为库存瓶颈。

## C. 预设27个新实例的资格搜索

规模`N={2,4,8}` × 配方`{纯4×1,纯2×2,半数混合}` × 三场景。场景依次为：集中LP/H2/4辅助片、四LP轮转/H3/6辅助片、偏斜两LP/H5/8辅助片。参数组合在方法结果出现前固定；这是覆盖设计，场景因子相关，不能从场景差异单独估计H或库存效应。

```powershell
& $py -X utf8 -u $entry plan --suite qualification
& $py -X utf8 -u $entry start --suite qualification --campaign JMS-version/results/journal_d_qualification_20261109_r1 --time-limit 1200 --wall-limit 3600
& $py -X utf8 -u $entry report --campaign JMS-version/results/journal_d_qualification_20261109_r1
```

27次，固定SCIP求解种子17、正常分离、不加载策略、无构造输入，名义预算9 h。其输出只用于生成**共同可行输入**，1200 s资格搜索不能冒充后续300 s算法成绩。所有27个结果必须完成；超时无解正常记录，进程失败须先排查。若全无可行输入，入口拒绝下一步；若只有K个合格实例，必须同时报告K/27及失败分布，不得称完整27例算法验证。

## D. 在合格的新实例上隔离学习增量及组件消融

```powershell
& $py -X utf8 -u $entry plan --suite transfer --source-campaign JMS-version/results/journal_d_qualification_20261109_r1
& $py -X utf8 -u $entry start --suite transfer --source-campaign JMS-version/results/journal_d_qualification_20261109_r1 --campaign JMS-version/results/journal_d_transfer_20261109_r1 --time-limit 300 --wall-limit 1800
& $py -X utf8 -u $entry report --campaign JMS-version/results/journal_d_transfer_20261109_r1
```

每合格实例69次算法运行+3次共享SPBS准备，最多1944个队列单元。对照为SCIP/HEM/proposed各有/无SPBS，另有仅扩展特征、去结构重排、贪心替代束搜索三个**同SPBS输入**消融；学习臂训练种子1/2/3、求解种子1/2/3，SCIP只做三个求解种子，不复制成训练样本。

**每实例/求解种子的SPBS只计算一次，所有学习臂使用完全相同的赋值哈希。** 各SPBS臂仍按60 s准备+240 s主问题记账，共享只减少执行开销；无SPBS为300 s主问题。未用满的60 s不转给主问题。主比较为proposed+SPBS对HEM+SPBS，同时对照SCIP+SPBS；分开报告SPBS从原输入得到的改善与随后学习阶段的改善。

按全部预算耗尽估算，每个合格实例约5 h求解预算，K=27约135 h，另加建模/载入/验证；先查看资格覆盖再决定是否执行整批。每次恢复继续同一批次，不能根据中途有利结果截断并声称完成。输出`summary/analysis.json`和`analysis_rows.json`，先在每实例内平均成对种子差异，再报告实例级平均/中位增益、胜平负、描述性95% bootstrap区间及分训练种子增益。四个旧实例与新实例单独报告，不能把重复运行当独立样本。

## E. 只有保留节拍主张时再补长连续链：24次搜索及条件消融

旧9次要求至少两个节拍中心的搜索全部无解。本批另行预设4/6片纯2×2、H3/5、4/8辅助片，三个种子；要求**至少一个**节拍中心、一次实际清洁和同一辅助身份至少两次借用。降低中心数门槛是新的诊断设计，不能与旧9次合并计算成功率。搜索仍使用完整候选容量，但增加了见证约束，因此其最优/不可行状态均仅属于受限搜索域。

```powershell
& $py -X utf8 -u $entry start --suite chain --campaign JMS-version/results/journal_d_chain_20261109_r1 --time-limit 1200 --wall-limit 3600
& $py -X utf8 -u $entry report --campaign JMS-version/results/journal_d_chain_20261109_r1
```

24次名义预算8 h。全部完成后，每配置取**最低成功求解种子**，不按完工时间或权重收益挑选。若没有合格见证，下列命令会拒绝启动，应继续保留节拍验证缺口，而不是延长预算直至出现有利结果。

```powershell
& $py -X utf8 -u $entry plan --suite rhythm --source-campaign JMS-version/results/journal_d_chain_20261109_r1
& $py -X utf8 -u $entry start --suite rhythm --source-campaign JMS-version/results/journal_d_chain_20261109_r1 --campaign JMS-version/results/journal_d_rhythm_20261109_r1 --time-limit 120 --wall-limit 1800
& $py -X utf8 -u $entry report --campaign JMS-version/results/journal_d_rhythm_20261109_r1
```

每合格见证12次：权重0/5/25/100 × 三种子，固定同一主要离散结构、保持产品完工上界，比较等待和节拍偏差。该子问题最优不代表完整调度全局最优；没有指标变化也必须报告。

## 状态、恢复与预检

以下以A批次为例；对其他批次只替换路径。已完成单元会跳过。若Ctrl+C被控制器正常捕获，并写入`failure.json`且原因为`foreground_interrupted`，普通`resume`会归档旧尝试后重跑该单元。若终端关闭、进程被强制结束等使结束记录来不及写入，已有目录可能仍被status列为pending，即使failed为0，普通resume也会报`Incomplete/failed attempt preserved`。此时先确认没有残留实验进程、检查`runs/<单元>/solve/solver.log`和`logs/`，再显式追加`--retry-failed`。其他已记录失败也需检查原因后才能重试；旧尝试另行归档，不能把失败当作无解。

```powershell
& $py -X utf8 -u $entry status --campaign JMS-version/results/journal_d_backfill_standard_20261109_r1
& $py -X utf8 -u $entry resume --campaign JMS-version/results/journal_d_backfill_standard_20261109_r1
```

若只想预检，将对应`start`改为`prepare`，再对`campaign.json`中的单元执行：

```powershell
& $py -X utf8 -u $entry check --campaign JMS-version/results/journal_d_backfill_standard_20261109_r1 --cell n2_H3_4x1_dual__s1__t2__hem_plain
```

本轮创建的`journal_support_preflight_20261109_*`仅用于入口和模型/策略载入检查，**不是正式实验，请勿当作完成结果或恢复为正式批次**。新的方法执行分支尚未完成真实优化运行；本轮验证为协议测试、构模/载入和已有赋值重放，实验结论仍待正式运行与全量审计。

# 学位论文待补实验命令（更新：2026-11-11）

**新增100片入口：** 见[100片持续求解与甘特图自动更新命令](LARGE_SCHEDULE_COMMANDS.md)。支持与当前批次并行、GPU策略推理及动态整机内存余量保护，不设置固定内存配额。--until-optimal不设时间或节点上限，完整主问题已证最优才记为成功；资源不足会提示。未证最优也自动生成已验证可行解的甘特图，后续改善更新同一路径，历史解独立保留。本次只做预检，未启动100片优化；不能保证现有硬件必能完成证明。

当前文稿甘特图已换为完整复验通过的16片纯4×1、920 s可行排程，未证全局最优；旧100片图仍不能作为当前D模型结果。

仅整理第一、第二创新点的期刊稿，请另见 [期刊稿独立审查](JOURNAL_REVIEW_CN.md)和[期刊缺失实验命令](JOURNAL_EXPERIMENT_COMMANDS.md)。两份清单的同协议实验应复用，不要重复运行。

对应[项目审查与六章整理方案](THESIS_REVIEW_AND_PLAN_CN.md)。本次只整理和检查入口，**未启动正式实验**。

## 1. 已有结果先用

- D编码对照 `gap_d_encoding_20261108_r2` 已24/24完成，不重跑。
- CIE正式七阶段6273条记录、E下30组阶段内精修和24次权重消融，保留原模型与预算归属直接使用，不为换章节重跑。
- 100片混合排程及全流程/腔室/资源图已存在于旧固定结构模型，Cmax约9998秒；异质时长模型有28658秒构造排程。两者均不是当前D的100片最优结果。
- 原结构批次 `gap_d_structure_20261108_r1` 为1/36，属于旧固定内存协议。原文件和已完成结果保留；本清单不再推荐其固定内存等待/续跑命令。新协议完整36次单列，旧1次仅作旧协议观察，不能拼作统一资源条件的比较。
- 原命令全文已备份到 [EXPERIMENT_COMMANDS.before.md](review/thesis_workspace_20261108/EXPERIMENT_COMMANDS.before.md)。

## 2. 新入口：不设置固定内存配额

`tools/thesis_gap_experiments.py` 是隔离的新入口，复用当前D后端，不修改旧驱动、冻结协议、LP或结果。

- 不设固定SCIP内存或进程RSS上限；使用SCIP原生默认的无限内存标记。协议中的 `memory_mb` 巨大数值是该标记，不是预留这么多物理内存。
- 每秒监测系统可用内存，默认低于物理总内存10%时停止当前单元并保留失败记录；下一单元启动前也检查该比例。此为整机可用内存保护，不是固定给每个实验若干GiB，也不会因启动时的空闲量冻结一个RSS配额。
- 前台、单线程、一次一个单元；每10秒显示完成/失败数、当前耗时、RSS与预计剩余时间。暂按完整模型的资源开销选择串行。新批次保存机器、输入、代码哈希、求解预算和实际峰值RSS。
- 不同资源协议分别报告。取消内存配额不能保证32/100片模型可构建或可求解。
- 入口已通过20项已有赋值的建模/检查，未做正式优化；这只验证入口和输入，不承诺算法产生改善。

在可见PowerShell终端执行：

```powershell
Set-Location D:\git\git\RDMCT-A3C
$ThesisPython = 'G:\conda\envs\a3cenv\python.exe'
$ThesisDriver = 'JMS-version/tools/thesis_gap_experiments.py'
```

## 3. P1：结构对照与SPBS后续流程

先检查矩阵，不求解、不创建正式批次：

```powershell
& $ThesisPython -X utf8 -u $ThesisDriver plan --suite structure
& $ThesisPython -X utf8 -u $ThesisDriver plan --suite spbs
```

四个已有D可行输入；结构为4实例×3种子×3臂=36次，三臂分别联合300秒、固定300秒、先固定60秒后联合240秒：

```powershell
& $ThesisPython -X utf8 -u $ThesisDriver start --suite structure --campaign JMS-version/results/thesis_d_structure_20261108_unlimited_r1 --time-limit 300 --stage2-limit 60 --wall-limit 1800
```

SPBS为4实例×3种子×2臂=24次；无SPBS主问题300秒，有SPBS为60秒结构改进＋240秒主问题，两臂均追加60秒精修与60秒收尾：

```powershell
& $ThesisPython -X utf8 -u $ThesisDriver start --suite spbs --campaign JMS-version/results/thesis_d_spbs_20261108_unlimited_r1 --time-limit 300 --stage2-limit 60 --wall-limit 1800
```

这两组从共同已验证赋值开始，仅检验已有起点后的搜索/改善；不是冷启动构造成功率，也不是HEM网络独立贡献实验。原输入构造成本需另报。

## 4. P2：收尾与节拍机制

收尾12次，保持产品完工时间和二阶段目标上界，仅改善全部占用结束时间：

```powershell
& $ThesisPython -X utf8 -u $ThesisDriver start --suite cleanup --campaign JMS-version/results/thesis_d_cleanup_20261108_unlimited_r1 --stage2-limit 60 --wall-limit 1800
```

节拍见证搜索9次：4片纯2×2、6片纯2×2、6片混合，H=10，每例三种子；要求至少2个有效节拍中心：

```powershell
& $ThesisPython -X utf8 -u $ThesisDriver start --suite rhythm_search --campaign JMS-version/results/thesis_d_rhythm_search_20261108_unlimited_r1 --time-limit 600 --wall-limit 1800
```

只有上一步全部结束且至少有一个合格输入，才执行权重消融。每实例按预定最小成功种子选择输入，三个求解种子、四权重共享赋值，每臂60秒，条件性12—36次：

```powershell
& $ThesisPython -X utf8 -u $ThesisDriver start --suite rhythm --source-campaign JMS-version/results/thesis_d_rhythm_search_20261108_unlimited_r1 --campaign JMS-version/results/thesis_d_rhythm_20261108_unlimited_r1 --stage2-limit 60 --wall-limit 1800
```

见证搜索额外限制了可行域，其最优/不可行不推广到完整原问题；无合格输入时入口拒绝消融。E的既有有效节拍结果仍可使用，不因D搜索失败而丢弃。

## 5. 状态与恢复

只对已创建的新批次使用；其他批次替换目录，不要重复start：

```powershell
& $ThesisPython -X utf8 -u $ThesisDriver status --campaign JMS-version/results/thesis_d_structure_20261108_unlimited_r1
& $ThesisPython -X utf8 -u $ThesisDriver resume --campaign JMS-version/results/thesis_d_structure_20261108_unlimited_r1
```

启动前内存比例不足时，没有创建新运行单元，释放内存后直接resume。若工作单元因系统可用内存保护、worker错误或墙钟保护停止，先检查 `runs/单元/failure.json` 和日志；解决原因后可显式恢复，旧尝试会归档：

```powershell
& $ThesisPython -X utf8 -u $ThesisDriver resume --campaign JMS-version/results/thesis_d_structure_20261108_unlimited_r1 --retry-failed
```

Ctrl+C的 `foreground_interrupted` 尝试可直接resume；未知半成品必须先诊断。恢复以单元为单位，不恢复SCIP搜索树。不并行启动这份清单的多个队列。

## 6. 尚缺实现或成功证据的事项

| 必补事项 | 为什么不能仅给一条现成命令 | 先完成什么 |
|---|---|---|
| 第三创新点算法及消融 | 尚无完整瓶颈识别、解池共识/分歧、联合邻域、质量引导MILP修复入口 | 实现方法与通用LNS/SPBS基线、固定总预算及结果验收；不能把现有SPBS重新命名当新方法 |
| 当前D的完整100片三模式×清洁矩阵 | 已新增100片混合单例完整主问题入口，尚未运行；完整表示仍有内存障碍 | 先按[100片命令](LARGE_SCHEDULE_COMMANDS.md)核验混合实例的可行性与界，再扩展可比矩阵；不能承诺必得全局最优 |
| 当前D下HEM增强端到端比较 | 当前选割结果只保留共同起点、回调有限；旧模型checkpoint迁移不能等同于重新训练 | 当前模型训练/验证/测试协议、构造成本入账、训练种子独立重复及回调诊断 |

第三创新点和端到端训练评价仍有实现或设计前置条件。新增100片命令对应已实现的入口，但尚无成功求解证据。审查索引可随时只读重建：

```powershell
& $ThesisPython -X utf8 JMS-version/review/thesis_workspace_20261108/catalog.py
& $ThesisPython -X utf8 JMS-version/review/thesis_workspace_20261108/check_evidence.py
```

所有结果都要保留optimal、限时有解、限时无解、memlimit、外部保护和失败的区别。命令执行完成不等于模型可行、最优或算法优于基线。

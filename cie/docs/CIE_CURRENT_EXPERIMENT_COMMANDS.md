# C&IE 当前PW模型补强实验命令（2026-11-09）

模型、参数、目标和实验结论一律以新版 `JMS-version` 为准。当前稿为 [rdmct_cie_analysis_focused_zh.tex](../products/rdmct_cie_analysis_focused_zh.tex)。旧CIE的固定配对、固定槽位生成MILP及6273次历史实验保留归档，不能合入当前联合模型D的主比较。**本轮没有启动新求解或训练。**

已有180次算法比较、36次结构比较、12次收尾及9次节拍搜索直接复用；同模型1片2×2/H2的303 s最优见证已经展示连续加工、清洁和辅助片复用，不能再称完全没有这类见证。其库存峰值5/8、有效节拍中心0，仍不足以证明库存瓶颈或长链节拍效果。

## 1. 公共设置与优先级

在可见PowerShell前台运行。动态显示完成/失败数和ETA；单线程、一次一个工作进程，学习任务不争用同一GPU。新入口没有固定SCIP内存或进程RSS配额，只监测系统可用RAM比例（默认10%）。这是系统余量保护，不是固定内存方案。原批次、检查点、共享LP和旧启动器不改。

```powershell
Set-Location D:\git\git\RDMCT-A3C
$py = 'G:\conda\envs\a3cenv\python.exe'
$endToEnd = 'cie/code/run_current_jms_experiments.py'
$support = 'JMS-version/tools/journal_support_experiments.py'
```

推荐顺序：A端到端小批次 → B已有输入检查点补齐 → C机制对照 → D新实例资格及条件消融 → E端到端27例 → F必要时长链节拍。不要一次把全部命令贴入终端。C、D、F直接复用新版[JMS命令及解释](../../JMS-version/JOURNAL_EXPERIMENT_COMMANDS.md)，不另造冲突协议。

## A. 新入口：端到端小批次，先验证运行链

此前所有新增SPBS算法比较从现成赋值开始；本批不读取任何预计算可行排程。四个预设配置，七臂，三个求解种子，共84次。七臂是冷启动SCIP/HEM/proposed、构造+SCIP、构造+SPBS+SCIP/HEM/proposed。学习检查点训练种子先固定1。

第四例限定单腔，是显式的设备配置诊断，不冒充正文双腔默认实例；所有配置仍使用新版D的约束实现、100 s非加工驻留/承片和10000 s含复位时域、完整候选容量。

```powershell
& $py -X utf8 -u $endToEnd plan --suite pilot --budget 600
& $py -X utf8 -u $endToEnd prepare --suite pilot --campaign cie/results/current_jms/cie_d_e2e_pilot_20261109_r1 --budget 600
& $py -X utf8 -u $endToEnd check --campaign cie/results/current_jms/cie_d_e2e_pilot_20261109_r1
& $py -X utf8 -u $endToEnd start --campaign cie/results/current_jms/cie_d_e2e_pilot_20261109_r1
& $py -X utf8 -u $endToEnd audit --campaign cie/results/current_jms/cie_d_e2e_pilot_20261109_r1
```

总名义墙钟上限约14 h，另有启动检查、记录和独立审计；不是完成时间承诺。先检查实际运行错误、构造失败原因和有效覆盖，再扩展到E。

**端到端口径：** 每单元从阶段子进程启动前开始计时，包含Python导入、构造、模型建立、赋值补齐、SPBS、策略加载、主求解以及在线检查点的模型/物理验证和序列化。初始化至多分配总时间20%，提前结束的剩余时间交给主求解；构造或映射失败也计时，并回退到剩余预算的冷启动。第二阶段及收尾关闭，以隔离原始完工目标。

父进程每0.1 s检查时间和可用RAM，初始化与主求解分别受截止时刻约束，默认另容许0.5 s进程退出缓冲。**只把完整写出时间和验证时刻都不晚于科学截止时刻的检查点算作限时成绩。** 退出缓冲内或之后才写出的更好解不计入。记录实际墙钟和超出量；进程结束并非精确发生在第600.000 s。完整重建模型的独立最终审计在求解后单列计时，不伪装成600 s内完成。

每次改善保存包含完整变量赋值的原子检查点。在线保存也有成本，计入各臂；主阶段被超时终止时仍可使用此前合法保存的解。完整原始模型赋值验证和物理重放均通过后才可入稿；构造失败、无可行解、进程错误、内存余量停止全部保留。失败不等于不可行。保存的上界轨迹采用全过程时间，不拿旧240/300 s主阶段PDI做端到端排名。本入口暂不自动计算跨阶段PDI或显著性。

这是**新增工程入口**，本轮验证包括非优化协议检查、测试和已有赋值重放；没有运行真实优化，首次实际执行仍需检查回调、截止处理和日志。它不意味着端到端性能证据已经存在。

## B. 只补缺失检查点重复，不重跑旧72次

直接采用新版JMS的 `backfill_standard`：新增96次，合并原72次，仍只有四个独立实例。HEM/proposed有无SPBS，补训练种子2、3；求解种子1、2、3。不得选择最好训练种子作为最终报告。

```powershell
& $py -X utf8 -u $support plan --suite backfill_standard
& $py -X utf8 -u $support start --suite backfill_standard --campaign JMS-version/results/cie_d_backfill_standard_20261109_r1 --time-limit 300 --wall-limit 1800
& $py -X utf8 -u $support report --campaign JMS-version/results/cie_d_backfill_standard_20261109_r1
```

该入口的 `--time-limit` 是求解预算，`--wall-limit` 是异常保护，不是A的统一墙钟。名义求解预算约8 h。若新版JMS同协议批次已经完成或正在运行，直接复用该批次，不再运行CIE同名重复批次。

## C. 清洁规则与库存的匹配对照：144次

六种工作负载交叉H={2,3}、辅助片={4,8}，24配置；每配置可选提前清洁/原触发规则 × 三求解种子。两规则共享同配置合法输入，否则共同冷启动。完整候选空间不变，精修关闭。

```powershell
& $py -X utf8 -u $support plan --suite mechanism
& $py -X utf8 -u $support start --suite mechanism --campaign JMS-version/results/cie_d_mechanism_20261109_r1 --time-limit 600 --wall-limit 2400
& $py -X utf8 -u $support report --campaign JMS-version/results/cie_d_mechanism_20261109_r1
```

名义求解预算24 h。报告有效上/下界、实际清洁/提前清洁、连续产品PW对、辅助借用/复用/并发峰值、产品与设备完成边界。模式比较只是累计处理时长均为180 s的合成工艺场景；没有工程依据时不声称现实配方可替代。只有界足以分离时才给出最优模式排序。

## D. 新测试集与同输入学习增量

27个预设配置：N={2,4,8} × 三配方 × 三种LP/H/库存场景，具体构型见新版JMS协议。先按固定种子17、1200 s资格搜索取得共同输入，完整报告27例的成功/失败，不删除无解配置。

```powershell
& $py -X utf8 -u $support plan --suite qualification
& $py -X utf8 -u $support start --suite qualification --campaign JMS-version/results/cie_d_qualification_20261109_r1 --time-limit 1200 --wall-limit 3600
& $py -X utf8 -u $support report --campaign JMS-version/results/cie_d_qualification_20261109_r1
```

资格阶段27次，名义求解预算9 h。全部完成后，K个合格实例进入后续比较；K=0时入口拒绝执行，不能把资格搜索成本隐藏为算法能力。

```powershell
& $py -X utf8 -u $support plan --suite transfer --source-campaign JMS-version/results/cie_d_qualification_20261109_r1
& $py -X utf8 -u $support start --suite transfer --source-campaign JMS-version/results/cie_d_qualification_20261109_r1 --campaign JMS-version/results/cie_d_transfer_20261109_r1 --time-limit 300 --wall-limit 1800
& $py -X utf8 -u $support report --campaign JMS-version/results/cie_d_transfer_20261109_r1
```

每例69算法单元+3共享SPBS准备，最多1944队列单元，K=27约135 h名义求解预算。每例/求解种子仅计算一次SPBS，所有学习臂共享其赋值哈希；学习检查点训练种子1/2/3，求解种子1/2/3。主比较为proposed+SPBS对HEM+SPBS，SCIP+SPBS为参照；同SPBS的特征、去重排、贪心解码为次要消融。按实例汇总成对差异，报告胜平负及区间；K/27和资格失败分布必须同时给出。

## E. 27例的无条件端到端比较

与D的资格设计使用**完全相同配置**，但每个算法从零开始，不读取D的资格解，也不筛除D失败实例。单训练种子为27×7×3=567次，600 s墙钟名义上限94.5 h；三个训练种子为27×(3个SCIP臂+4个学习臂×3)×3=1215次，上限202.5 h。SCIP不复制成“训练重复”。

以下采用三个冻结训练种子，回答跨检查点的端到端稳定性；这是冻结旧策略在D上的迁移，不是D上重新训练。

```powershell
& $py -X utf8 -u $endToEnd plan --suite generalization --training-seeds 1 2 3 --budget 600
& $py -X utf8 -u $endToEnd prepare --suite generalization --training-seeds 1 2 3 --campaign cie/results/current_jms/cie_d_e2e_27_20261109_r1 --budget 600
& $py -X utf8 -u $endToEnd check --campaign cie/results/current_jms/cie_d_e2e_27_20261109_r1
& $py -X utf8 -u $endToEnd start --campaign cie/results/current_jms/cie_d_e2e_27_20261109_r1
& $py -X utf8 -u $endToEnd audit --campaign cie/results/current_jms/cie_d_e2e_27_20261109_r1
```

先做A和非优化check，再决定是否完整启动E。不得中途看到有利结果便停批并当作完整矩阵。若暂不需要跨训练重复，在**prepare前**改成 `--training-seeds 1` 并使用不同新批次名，不能修改已冻结协议。

## F. 保留D长链节拍主张时的条件实验

现有1片清洁见证没有有效节拍中心；旧9次节拍搜索也没有输入。新版JMS预设24次带见证约束搜索，再按最低成功种子选择固定输入，权重0/5/25/100 × 三种子。受限搜索最优不是完整调度全局最优。

```powershell
& $py -X utf8 -u $support start --suite chain --campaign JMS-version/results/cie_d_chain_20261109_r1 --time-limit 1200 --wall-limit 3600
& $py -X utf8 -u $support report --campaign JMS-version/results/cie_d_chain_20261109_r1
& $py -X utf8 -u $support plan --suite rhythm --source-campaign JMS-version/results/cie_d_chain_20261109_r1
& $py -X utf8 -u $support start --suite rhythm --source-campaign JMS-version/results/cie_d_chain_20261109_r1 --campaign JMS-version/results/cie_d_rhythm_20261109_r1 --time-limit 120 --wall-limit 1800
& $py -X utf8 -u $support report --campaign JMS-version/results/cie_d_rhythm_20261109_r1
```

链搜索名义预算8 h；无合格见证时不执行rhythm，保留未验证边界。不能延长直到有利为止。

## 状态与恢复

```powershell
& $py -X utf8 -u $endToEnd status --campaign cie/results/current_jms/cie_d_e2e_pilot_20261109_r1
& $py -X utf8 -u $endToEnd resume --campaign cie/results/current_jms/cie_d_e2e_pilot_20261109_r1
```

新端到端入口只续跑尚未创建的单元，已完成/失败结果不覆盖；Ctrl+C留下的不完整单元会阻止自动恢复，须先诊断并用新批次安排显式重试，原尝试保留。JMS support入口沿用其自身恢复/归档规则，不混用参数。

`cie/results/current_jms/preflight_*_not_experiment` 是本轮非优化预检，不能作为实验结果或正式恢复入口。所有新性能结论均待实验完成、独立审计和实例级分析后再入稿。100片排程是学位论文的目标；尚无依据把它列为C&IE统一硬性门槛，也不能用旧模型100片结果证明D模型规模能力。

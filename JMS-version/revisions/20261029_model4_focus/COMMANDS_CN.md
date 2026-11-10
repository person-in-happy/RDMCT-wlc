# 当前投稿稿件的补充实验命令

核对日期：2026-10-29。本清单对应精简后的中文稿；旧的完整实验目录保存在本次修订的`original/MODEL4_EXPERIMENT_COMMANDS.md`。

## 已完成或正在运行，不重复启动

| 实验 | 状态 | 处理 |
|---|---|---|
| `core`，`model4_core_all_20261028_fix1` | 126/126记录完整，114个有效排程 | 已更新正文；12次无解超时保留 |
| `ablation`，`model4_ablation_all_20261028_164314` | 216/216有效排程 | 已更新必要消融与精修结果 |
| `crossover`，`model4_crossover_all_20261029_080528` | 正在运行，计划216次 | 自然完成后审计，补入8/16/24片模式结果 |

上述342个已完成观测已核对冻结协议、结果与LP哈希，并重新执行可行结果的独立物理验解。初次预检失败的`model4_core_all_20261028_091756`保留为故障记录，不计入运行样本。

## 优先补充：资格与解码，6次

现有正式求解批次均为`Qualification all`。新增两份8片混合配置，在同一LP内同时包含“仅CH2、仅CH3、两腔均可”，分别采用单源和双源，每种配方各有三个Pjob，总计六个Pjob；每配置运行种子1、2、3。

输入已经准备在`JMS-version/experiments/model4_focus_20261029/`，编号为1--6、26--27。该补充检验带资格限制的MILP、库存和末端晶圆解码，不进行算法排名。

从仓库根目录在可见PowerShell执行：

```powershell
Set-Location 'D:\git\git\RDMCT-A3C'
powershell -ExecutionPolicy Bypass -File .\JMS-version\experiments\model4_focus_20261029\run_qualification.ps1
```

该入口串行运行6次，显示完成/失败数、内存及ETA；冻结输入与运行源码，保存独立输出目录。每次270+30秒、SPBS 20秒、SCIP 6000 MiB、RSS保护7000 MiB、单元墙钟保护1800秒；无学习GPU任务。可先用`-PlanOnly`核对清单而不求解。

## 优先补充：有效节拍配置，48次

现有混合消融实例没有有效节拍中心。保留节拍项时，需要补充8片纯2×2、单/双源、H=5/10的4种配置，比较直接求解、完整线性精修、仅等待精修及二次节拍目标，每种3个种子。

```powershell
$r = '.\JMS-version\model4_pjob_20261027\run_experiments.ps1'
powershell -ExecutionPolicy Bypass -File $r -Suite rhythm
```

48次用于评价有效节拍结构下的结果。该现有入口分别运行各方法的第一阶段；只有审计中`controlled_comparison=true`的配对才同时具有相同第一阶段赋值和有效节拍中心。其余结果可描述协议差异，但不能单独归因于节拍惩罚项。若没有受控配对，保留描述性结论即可，不因结果不显著而反复重跑。

## 可选规模扩展：只补32片，9次

正在运行的模式扫描已经覆盖8/16/24片；若继续扩展正式求解规模，仅运行32片子集，无需再次执行完整`scale`。

```powershell
powershell -ExecutionPolicy Bypass -File $r -Suite scale32 -Jobs 1 -MemoryMB 18944 -ProcessMemoryMB 14336
```

三种配方、H=3、种子1/2/3，共9次。该资源协议与正在运行的模式扫描一致。当前正文中的32片构造性序列与数量下界无需等待这组实验；它们不属于32片MILP性能结果。

优先补充合计54次；若加入32片扩展，共63次。

## 本稿不要求新增的实验

- 不再重复`core`、`ablation`、`crossover`或其`mode24`子集。
- 不额外运行`fixed`：现有基础组已有固定结构和辅助身份对照。
- 不要求完整`doe`、`ood`、`sensitivity`、独立`diagnostic`或大规模训练比较：相关主张已移出正文。
- 不要求额外`cleaning`：保留清洁约束，不宣称提前清洁的独立性能收益。
- 不要求`gantt16`长预算重跑：模式扫描完成后的有效见证可直接绘图；延长预算不作为等预算样本替换。
- 若今后要主张相对逐片模型的总变量下降或求解加速，再另设同资格、同实例、同资源的逐片对照；当前稿只陈述成员选择块和表示方式。

## 启动顺序、审计与计时

等当前模式扫描自然结束，再逐组运行上述补充。两个入口均检查已有实验进程；不需要停止活动队列。

对现有统一入口生成的批次，使用实际目录审计：

```powershell
$campaign = 'JMS-version/results/替换为实际批次目录'
powershell -ExecutionPolicy Bypass -File $r -Action status -Campaign $campaign
powershell -ExecutionPolicy Bypass -File $r -Action audit -Campaign $campaign
```

资格补充入口的`progress.json`逐项记录完成、失败、进程退出码、实际墙钟和采样峰值RSS，具体排程及原始检查位于各单元`result.json`。其批次不是统一入口的campaign格式，不能对它调用统一入口的`audit/resume`。

已完成批次存在实际停止时间超过300秒设定值的情况；正文已经改为报告设定预算和实际时间，不再把原始PDI均值作为严格等墙钟预算排名。以后若要恢复速度比较，需要另行冻结统一时间口径，不能修改当前活动批次。

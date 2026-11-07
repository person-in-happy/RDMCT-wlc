# 本轮补充实验命令

在项目根目录、已激活的`a3cenv`终端中运行。入口使用现有`G:\conda\envs\a3cenv\python.exe`，在当前可见终端显示完成数、失败数、运行项及预计剩余时间。每组串行、每个SCIP任务单线程，输出目录独立。

```powershell
$r = Join-Path $PWD 'JMS-version\experiments\review_followup_20261102\run_followup.ps1'
```

## 1. 公平计时：优先执行

```powershell
powershell -ExecutionPolicy Bypass -File $r -Suite timing -Campaign '.\JMS-version\results\review_followup_timing_20261102_01'
```

六种既有8/16片实例、两种成员表示、各6次重复，共72项。每种实例两种先后执行顺序各出现3次。只测模型生成和起点映射/约束检查，不调用`optimize()`，不重跑原36次300 s求解。

两种表示使用同一份历史完整起点。保留构造器内两臂共同的一遍规模统计，取消原逐片臂独有的额外扫描；最终规模报告在计时外统一生成。输出分别记录`build_seconds`、`mapping_and_check_seconds`和两者之和`preparation_seconds`。汇总中给出每次观测、均值和样本标准差。

默认进程上限8000 MiB，启动前要求可用内存至少9024 MiB。

## 2. 双腔并行可行见证：优先执行

```powershell
powershell -ExecutionPolicy Bypass -File $r -Suite parallel -TimeLimit 600 -Campaign '.\JMS-version\results\review_followup_parallel_20261102_01'
```

三个2片双源场景：180 s的4×1、600 s的4×1、90 s的2×2。两片产品分别只允许CH2、CH3，辅助片库存仍为8片；2×2场景取H=2，覆盖连续处理后的清洁。

在完整候选模型上要求两腔首个生产周期重叠至少1 s，寻找可行见证。每项主求解600 s；这是并行能力的定向验证，不与原性能实验混算。得到的事件表、周期表、晶圆表和完整赋值保存在各`runs`子目录；最终赋值再回填原模型验解。

`summary/cells.json`中的`valid=true`且`target_met=true`表示得到并行见证。未找到可行解时保留停止状态；若求解器证明不可行，该证书针对所加首周期重叠条件，不表示原调度问题不可行。

## 3. 小规模完整模型的精确对照

```powershell
powershell -ExecutionPolicy Bypass -File $r -Suite exact -TimeLimit 600 -Campaign '.\JMS-version\results\review_followup_exact_20261102_01'
```

六种实例：1片4×1/H3、1片2×2/H2、2片4×1/H3、2片2×2/H2、2片混合/H3、4片混合/H3。各用Pjob和逐片成员表示求解一次，共12次主求解，使用种子1、标准SCIP割设置和同一公共物理起点。

队列另含6项公共起点补全，逐实例生成后供两种表示共用，因此进度总数为18。补全不采用SPBS改进；每个主求解预算600 s，配对两臂预算一致。完整主问题不固定配对、分腔或周期占位。

检查`summary/exact_pairs.json`：只有`both_optimal=true`且`equal_proven_values=true`才构成该实例的等值最优性证据。时间停止的上下界单独保存，`±1e20`等哨兵值转换为null。该对照使用同一设备模型的两种身份表示，并辅以独立物理重放，不冒称独立穷举全部设备排程。

## 4. 驻留上限验证

```powershell
powershell -ExecutionPolicy Bypass -File $r -Suite residency -TimeLimit 300 -Stage2Limit 60 -Campaign '.\JMS-version\results\review_followup_residency_20261102_01'
```

4片混合、H=10、单/双源，各取模块驻留和机械手承片上限10000、500、250 s，共6项。各组固定同一历史配对、分腔和周期结构，主阶段300 s，时序精修60 s。H=10用于研究生产驻留压力，避免把250 s上限与500 s清洁处理时长直接冲突混为调度改善效果。

原起点若满足新上限则接纳，否则记录拒绝并在相同固定结构内搜索。结果给出产品流经时间、腔内驻留、路线等待、节拍和原模型验解。上述上限是参数化实验水平，不作为真实设备工艺限值。

第2–4组默认SCIP内存3000 MiB、进程上限4500 MiB，启动前要求可用内存至少5524 MiB。

## 计划、状态与恢复

只查看数量和设置，不建模求解：

```powershell
powershell -ExecutionPolicy Bypass -File $r -Suite exact -Action plan
```

查看状态：

```powershell
powershell -ExecutionPolicy Bypass -File $r -Action status -Campaign '.\JMS-version\results\review_followup_exact_20261102_01'
```

内存预检停止、关闭终端或中断后，使用原冻结设置恢复：

```powershell
powershell -ExecutionPolicy Bypass -File $r -Action resume -Campaign '.\JMS-version\results\review_followup_exact_20261102_01'
```

恢复时不再传`-Suite`、预算或内存参数。需要修改设置时新建`_02`目录。已经记录为执行失败的单元在诊断原因后，通过上述恢复命令追加`-RetryFailed`显式重试；旧尝试保存在`interrupted_attempts`。

`finished.json`表示队列执行结束。科学验证是否达到目标，分别查看`validated_records`、`targets_met`、并行单元的`target_met`以及精确对照的配对最优状态。运行结束后将新结果与文稿逐项对齐，不自动替换正文或历史结果。

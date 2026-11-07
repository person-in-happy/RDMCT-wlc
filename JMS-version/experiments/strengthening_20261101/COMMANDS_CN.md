# 本轮补强命令

在 `D:\git\git\RDMCT-A3C` 的 PowerShell 中运行。使用新入口，原求解器、已完成实验及其冻结配置保持原样。本轮只准备和验证入口，没有启动优化实验。

## 1. 含清洗的24片纯链式精修：12组

对应此前全部因内存限制保留起点的 `n24_H5_2x2_dual`：种子1、2、3，节拍权重0、5、25、100，共12组。每组保持原产品完工时间上界，同一种子的四个权重使用同一份完整起点。每组精修预算60秒，与原实验一致。

```powershell
Set-Location D:\git\git\RDMCT-A3C
$r = (Resolve-Path .\JMS-version\experiments\strengthening_20261101\run_strengthen.ps1).Path
powershell -NoProfile -ExecutionPolicy Bypass -File $r -Suite rhythm_memory -Stage2Limit 60
```

新实现先代入已固定的离散变量，保留时刻与同步选择，再求解同一精修目标。每份输出均恢复为完整赋值，并在未经修改的完整原模型中重新检查约束和物理排程。已有另外24组有效精修、36组初始化对照和42组收尾实验无需重复。

## 2. 相同FIFO规则的逐片/Pjob成员表示对照：36组

8、16片，4×1、2×2及混合配方，均采用双源、清洗阈值5；两种表示、三个随机种子，共36组。两种表示使用相同的候选容量、工艺资格、严格FIFO规则、初始物理排程、SCIP参数和300秒主阶段预算。

在上一项结束后运行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File $r -Suite representation -TimeLimit 300
```

本实验隔离“逐片成员选择”和“Pjob库存选择”的差异，两种表示共享产品对位置的动作路线。它回答成员编码对完整模型规模、资源消耗和固定预算解质量的影响；不将规则不同的历史逐片求解器当作匹配基线。8片混合配方中非空Pjob–LP组数等于产品数，可作为选择列数不变的对照。

记录内容包括变量、约束、非零元、成员选择列、建模及起点检查耗时、求解耗时、节点、界、gap、实际产品完工时间，以及内存。完整原模型回填验解单独计时，建模/求解阶段与验解阶段的内存分开记录。内存峰值每2秒采样，并补充建模结束和求解结束处读数。

## 资源、输出与继续执行

- 两项命令均在前台串行执行，显示完成数、失败数、当前任务和ETA。无需另开后台任务。
- 默认SCIP内存预算10000 MiB，进程RSS上限14000 MiB，额外保留2048 MiB；每个任务启动前要求系统可用内存至少16048 MiB（约15.7 GiB）。代入实现减少精修模型规模，完整原模型验解仍需内存。
- 输出目录自动建立为 `JMS-version/results/strengthen_rhythm_memory_时间戳` 和 `strengthen_representation_时间戳`，启动时显示实际路径。不要复用旧实验目录。
- 12组精修的优化预算合计最多12分钟，36组表示对照合计最多3小时；建模、验解及保存时间另计，以前台ETA为准。
- `summary/cells.csv` 和 `summary/coverage.json` 保存汇总；各任务的 `result.json`、`variables.json`、`full_model_audit.json`、`evidence.json`、`resources.json` 和日志保留完整记录。`complete` 表示结果已通过验解，最优性和是否受内存限制须读取 `solver_status`。

如果运行因可用内存不足而暂停，释放内存后，用启动时显示的**实际目录**继续。假设它保存于变量 `$c`：

```powershell
# 将右侧替换为启动时显示的实际目录。
$c = 'JMS-version/results/strengthen_rhythm_memory_实际时间戳'
powershell -NoProfile -ExecutionPolicy Bypass -File $r -Action status -Campaign $c
powershell -NoProfile -ExecutionPolicy Bypass -File $r -Action resume -Campaign $c
```

`resume` 使用冻结设置，不追加 `-Suite` 或预算参数。已有失败任务只有在原因处理后加 `-RetryFailed` 才重试，原失败记录会归档保留。需要改预算时新建批次，并对两种表示、所有权重统一使用新预算。

仅查看计划、不优化：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File $r -Action plan -Suite rhythm_memory
powershell -NoProfile -ExecutionPolicy Bypass -File $r -Action plan -Suite representation
```

实现与验解说明见 [PROTOCOL_CN.md](PROTOCOL_CN.md)。

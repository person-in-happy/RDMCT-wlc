# 当前默认参数补跑与甘特图命令（2026-11-03）

本次确认：表1保持100 s、B=10000 s；工艺腔100 s约束扣除必要工艺处理后的非加工驻留，生产与清洁处理均扣除。AL/装载锁仍按放片结束至取片开始，机械手仍按取片开始至放片结束。模型正文式(28)已明确。引言与表1、表2不改。

独立代码：`model4_pjob_nonprocessing_20261103`。旧的 `model4_pjob_nondecreasing_20261102`、冻结批次和结果均未修改。本轮只做准备、模型赋值检查和绘图，正式优化调用为0。

## 现有补跑结果如何使用

- 学习选割72/72完成，均为限额可行，0份完整主问题最优证书。它们使用总驻留10000 s、时域100000 s，不能充当当前参数的算法对照。
- `crossover` 的216单元与 `scale32` 的9单元都在预检查退出，未完成正式运行。16048 MiB=14000 MiB进程预算+2048 MiB余量；20480 MiB=18432+2048。不能删除保护或将该错误解释为模型不可行。
- 已保存的858份含解输出（包含不同阶段文件，不是858个独立实例）中，21份通过当前参数的物理重放与完整模型赋值检查。正文保留六份代表性排程，不能将筛选后的见证作为成功率或算法性能样本。
- 同Pjob同LP双片4×1排程以324 s达到旧宽松模型的有效下界；完整新模型检查通过，因此当前参数下仍可证明产品完工时间最优。辅助片294 s归还，产品324 s回片，装载锁复位342 s完成。
- 旧稿16片甘特图的同质手、固定布局或旧参数条件不同，不能直接插入当前文稿。已按新验解证书重绘324 s完整排程。

详见 `revisions/20261103_results_default_residency/REVIEW_CN.md` 和机器可读审计文件。

## 新补跑入口与预算

在可见PowerShell窗口逐组运行，勿同时启动多个控制队列。入口固定为1个CPU任务、每个SCIP单线程；打印进行中单元、完成/失败数、RSS和预计剩余时间。学习选割最多只有一个推理任务，不重新训练。

```powershell
Set-Location 'D:\git\git\RDMCT-A3C'
$py = 'G:\conda\envs\a3cenv\python.exe'
$runner = '.\JMS-version\model4_pjob_nonprocessing_20261103\paper_defaults.py'
```

下列是新的统一参数协议，并非对旧实验补上几个缺项。新模型有完整候选容量，主求解不固定配对、分腔或周期。小规模已有重验合格赋值时，使用共同可行起点；其余配置冷启动，不调用可能违反100 s约束的旧串行构造器。同一实例各方法/种子使用同一份起点，保存在新批次的 `warm` 目录。主求解与精修分别计时，不与旧SPBS预算混合排名。

### 先跑已准备的小规模8个实例

该批次尚未执行任何求解，已冻结参数和起点。每例主求解600 s，精修60 s，SCIP/进程内存6000/8000 MiB，要求可用内存至少10048 MiB。它是8次库存表示主求解，不冒称完成原来的16次双表示对照。

```powershell
$small = 'JMS-version/results/current_defaults_small_prepared_20261103'
& $py -X utf8 -u $runner run --campaign $small
if ($LASTEXITCODE -ne 0) { throw '小规模批次停止，请查看保存的日志。' }
& $py -X utf8 $runner status --campaign $small
```

正常单元间中断后可用 `resume`；已有部分输出或失败单元不会被覆盖，需先诊断，再安排独立重试。内存预检查失败尚未建立运行目录时，可释放内存后直接恢复：

```powershell
& $py -X utf8 -u $runner resume --campaign $small
```

### 重建16片甘特图所需的完整主问题

四种配置：16片，4×1/2×2，H=3/10，双源；种子1。主求解7200 s、精修60 s，内存10000/14000 MiB，要求至少16048 MiB可用内存。该预算不保证证明最优；无闭合上下界时只能绘制“可行排程”图。

```powershell
$gantt = 'JMS-version/results/current_defaults_gantt_' + (Get-Date -Format 'yyyyMMdd_HHmmss')
& $py -X utf8 $runner prepare --suite gantt --campaign $gantt --time-limit 7200 --stage2-limit 60 --memory-mb 10000 --process-memory-mb 14000 --wall-limit 14400
if ($LASTEXITCODE -ne 0) { throw '甘特图批次准备失败。' }
& $py -X utf8 -u $runner run --campaign $gantt
```

### 主排程、选割、清洁阈值与32片规模

每个命令块创建独立新批次，不修改旧参数批次。先通过小规模检查，再逐块运行。`prepare`只准备，不求解；`run`才正式启动。

```powershell
$paper = 'JMS-version/results/current_defaults_paper_' + (Get-Date -Format 'yyyyMMdd_HHmmss')
& $py -X utf8 $runner prepare --suite paper --campaign $paper --time-limit 300 --stage2-limit 60 --memory-mb 6000 --process-memory-mb 8000 --wall-limit 1800
if ($LASTEXITCODE -ne 0) { throw '准备失败。' }
& $py -X utf8 -u $runner run --campaign $paper
```

上述主排程为8种混合配置×3种子，共24个单元。保留主阶段及精修输出；只有输入和输出都满足当前模型时才组成阶段对照。

```powershell
$cuts = 'JMS-version/results/current_defaults_cuts_' + (Get-Date -Format 'yyyyMMdd_HHmmss')
& $py -X utf8 $runner prepare --suite paper_cuts --campaign $cuts --time-limit 300 --stage2-limit 0 --memory-mb 6000 --process-memory-mb 8000 --wall-limit 1800
if ($LASTEXITCODE -ne 0) { throw '准备失败。' }
& $py -X utf8 -u $runner run --campaign $cuts
```

学习选割仍为8实例×3种子×3方法=72个单元；冻结策略、根节点割配置，各方法相同主预算。必须检查实际回调次数，未触发选割不能作为策略效果证据。

```powershell
$crossover = 'JMS-version/results/current_defaults_crossover_' + (Get-Date -Format 'yyyyMMdd_HHmmss')
& $py -X utf8 $runner prepare --suite crossover --campaign $crossover --time-limit 300 --stage2-limit 0 --memory-mb 10000 --process-memory-mb 14000 --wall-limit 1800
if ($LASTEXITCODE -ne 0) { throw '准备失败。' }
& $py -X utf8 -u $runner run --campaign $crossover
```

阈值组为72实例×3种子=216个单元，要求可用内存至少16048 MiB。

```powershell
$scale32 = 'JMS-version/results/current_defaults_scale32_' + (Get-Date -Format 'yyyyMMdd_HHmmss')
& $py -X utf8 $runner prepare --suite scale32 --campaign $scale32 --time-limit 300 --stage2-limit 0 --memory-mb 12288 --process-memory-mb 18432 --wall-limit 3600
if ($LASTEXITCODE -ne 0) { throw '准备失败。' }
& $py -X utf8 -u $runner run --campaign $scale32
```

32片组为3实例×3种子=9个单元，要求可用内存至少20480 MiB。若内存不足，先关闭自己不需要的工作负载，或改用资源足够的主机；不要在冻结批次内降低预算。需要另设较低预算时创建新协议批次，完整记录并与本协议分开报告。

## 只重绘当前已证最优排程，不求解

当前绘图输出采用资源泳道：统一横向时间轴，模块动作色块标注晶圆编号，不添加路径连线或箭头。搬运、对准和压力变化按图注说明补全可行时间段，原取放、旋转、加工时刻不变。绘图器同时保存 `swimlane_actions.json`，可追溯每个色块和路径端点。

```powershell
$proof = 'JMS-version/revisions/20261103_results_default_residency/optimality_certificate.json'
$certificate = Get-Content -Raw -Encoding UTF8 -LiteralPath $proof | ConvertFrom-Json
& $py -X utf8 '.\JMS-version\tools\render_current_defaults_gantt.py' --result $certificate.result --variables $certificate.variables --proof $proof --output 'JMS-version/figures/current_defaults_20261103' --require-optimal
```

绘图器会重新检查参数、完整原模型赋值、独立物理重放以及最优性证书哈希；旧的“optimal”文件名或固定结构最优状态不能通过该门槛。

## 新16片结果完成后的绘图命令

沿用上面实际运行的 `$gantt`。只有主问题上下界闭合且完整验解通过，`--require-optimal`才输出最优图：

```powershell
$cell = Join-Path $gantt 'runs/n16_H3_4x1_dual__s1__scip'
& $py -X utf8 '.\JMS-version\tools\render_current_defaults_gantt.py' --result (Join-Path $cell 'result.json') --variables (Join-Path $cell 'variables.json') --output 'JMS-version/figures/current_defaults_n16_H3_4x1' --require-optimal
```

其他三种配置对应 `n16_H3_2x2_dual__s1__scip`、`n16_H10_4x1_dual__s1__scip`、`n16_H10_2x2_dual__s1__scip`，每图使用不同输出目录。若只获得可行解，可以去掉 `--require-optimal` 绘制明确标注“未证明最优”的图，不能在文稿中改称最优。

## 尚未具备当前参数证据的比较

逐片/库存表示、资格异构、长链节拍权重、固定结构/联合搜索、构造族数量及42份收尾配对，均需基于新的合格输入重新组织。上述入口不冒称已经实现这些对照，也不使用失配的历史输入代替新起点。应先完成小规模和主排程组，再按相同起点、候选容量、预算与目标设置准备这些专门比较；在此之前，相关旧结论仅保留在审计档案。

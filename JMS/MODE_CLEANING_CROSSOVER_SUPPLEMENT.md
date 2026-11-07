# JMS 4.2 工艺模式／清洁周期补充实验

## 实验问题与口径

旧图 4 实验采用的是单次曝光等时：4×1 一次加工 180 s，2×2 的两次加工各 180 s。它能回答单次曝光等时时的模式差异，但不能回答总配方时间相同的问题，因此不能直接用旧表得出本补充实验的结论。

本补充实验固定以下参数：

| 参数 | 数值／解释 |
| --- | --- |
| 4×1 工艺时间 | 一次 180 s |
| 2×2 工艺时间 | 第一次 90 s、第二次 90 s，总计 180 s |
| 无冲突的 2×2 工艺桥接 | VTR 四夹爪连续交换一次，精确 4 s |
| 拆分桥接 | 仅当来片未就绪或资源冲突时允许；卸片和装片各 4 s，中间还必须有空载复位 |
| 腔室清洁时间 | 500 s |
| 清洁周期 K | 每个腔室完成 K 个满腔工艺 cycle 后触发；不是 K 片产品晶圆 |
| 尾批不足 | 使用辅助 PEC 晶圆闭合 2×2 头／尾边界，不把辅助晶圆计入产品产量 |

每个 N 比较三种构型：纯 4×1、纯 2×2、1:1 混跑。混跑在奇数片时按项目既定口径令 4×1 多一片，因此 16／17／20 片分别为 `8+8`、`9+8`、`10+10`。

清洁周期 1 不进入扫描。2×2 的产品对需要相邻的两次曝光，而 K=1 会在每次曝光后强制清洁，改变被比较的工艺语义。扫描从 K=2 开始。

转换点没有脱离批量 N 的唯一常数：尾批、辅助 PEC 和两个腔室的分配都会改变清洁次数。因此必须分别报告每个 N 的转换区间，而且不能预先假定胜者随 K 单调变化。分析器会列出所有相邻 K 上的胜者变化。

## 一次完整发现扫描：16／17／20 片，K=2..10

这是回答 clean3、clean10 以及寻找转换区间的主命令。先用一个训练种子和一个 SCIP 种子发现候选转换点；每个单元只有在 `status=optimal`、`gap<=1e-8` 且独立物理验证通过时才进入比较。

```powershell
conda activate a3cenv
Set-Location D:\git\git\RDMCT-A3C

& .\JMS\run_mode_cleaning_crossover.ps1 `
    -WaferCounts '16,17,20' `
    -CleaningIntervals '2-10' `
    -TrainingSeeds '1' `
    -SolverSeeds '1' `
    -TimeLimit 14400 `
    -WarmStartTimeLimit 600 `
    -MemoryLimitMB 4096 `
    -ScipVerbosity 2 `
    -RunLabel 'jms_mode_cleaning_discovery_n16_n17_n20_20260831'
if ($LASTEXITCODE -ne 0) { throw 'Mode/cleaning discovery failed.' }
```

若只想先得到 clean3 与 clean10 的成对结论，可把 `-CleaningIntervals` 改为 `'3,10'`。这条缩减命令不能确定中间的转换点。

## 投稿确认：clean3、clean10 和实际转换边界，5×5 种子

先打开发现扫描输出的 `summary/mode_cleaning_transitions.csv`。把下面示例中的 `5,6` 替换为该文件报告的全部相邻转换端点；如果 16、17、20 片的端点不同，取并集。不要只挑有利于某种模式的 K。

```powershell
conda activate a3cenv
Set-Location D:\git\git\RDMCT-A3C

$transitionEndpoints = '5,6'  # 必须替换为发现扫描实际报告的端点并集
$confirmIntervals = '3,10,' + $transitionEndpoints

& .\JMS\run_mode_cleaning_crossover.ps1 `
    -WaferCounts '16,17,20' `
    -CleaningIntervals $confirmIntervals `
    -TrainingSeeds '1-5' `
    -SolverSeeds '1-5' `
    -TimeLimit 14400 `
    -WarmStartTimeLimit 600 `
    -MemoryLimitMB 4096 `
    -ScipVerbosity 2 `
    -RunLabel 'jms_mode_cleaning_confirmation_5x5_20260831'
if ($LASTEXITCODE -ne 0) { throw 'Mode/cleaning 5x5 confirmation failed.' }
```

这里的 5×5 是五个冻结训练检查点与五个 SCIP 种子的完整交叉。脚本从 `cie/results/repro_manifest/selected_checkpoint_manifest.csv` 逐个取 Proposed 检查点并校验 SHA-256；不重新训练，也不使用本轮临时训练。

## 输出与判定

每个运行标签的输出在：

```text
JMS/results/mode_cleaning_crossover/<RunLabel>/
  runs/
  solutions/
  validation/cie_manufacturing_metrics.json
  summary/mode_cleaning_comparison.csv
  summary/mode_cleaning_transitions.csv
  summary/mode_cleaning_crossover.json
  summary/mode_cleaning_crossover.md
```

`mode_cleaning_comparison.csv` 给出每个 N、K 下纯 4×1、纯 2×2、1:1 混跑的 Cmax、WPH 和三模式最优者。`mode_cleaning_transitions.csv` 单独给出纯 4×1／纯 2×2 在所有相邻 K 上的胜者切换；混跑不用于定义这两个纯工艺的转换点。

分析器还会逐个读取纯 2×2 和混跑的 `.sol`：联合桥接必须满足 `load_start=start` 且 `end-start=4 s`；拆分桥接的两个载片动作必须各为 4 s，并包含至少 4 s 的空载复位。任一单元超时、gap 非零、物理验证失败、桥接不符、种子单元缺失／重复或不同种子的已证最优 Cmax 不一致，脚本都会失败并禁止形成投稿结论。

本实验只比较主目标 Cmax，因此使用 `stage2_off`，避免把甘特图等待压缩的第二阶段预算混入吞吐率比较。若需要为某个已确认单元导出投稿甘特图，应另行对该单元运行 `stability_profile=full` 并同时证明主目标与等待压缩阶段最优；不能把本扫描的 stage2-off 解直接作为最终甘特图证据。

## 混跑切换间隔诊断

不能只凭泳道中的空白认定模式切换存在额外 setup。现有 `16` 片、clean10、2×2 为 `90+90 s` 的混跑解显示：

| 边界事件 | 时间 | 结论 |
| --- | ---: | --- |
| CH2 最后一次 4×1 前侧卸载结束 → 2×2 head 开始 | `422 → 426` | 4 s，等于 VTR 必需动作／复位下界 |
| CH3 最后一次 4×1 前侧卸载结束 → 2×2 head 开始 | `590.999992 → 594.999992` | 4 s，腔室模式边界已紧接 |
| 最后一对 4×1 的 AL 完成 → 第一片 2×2 的 AL 开始 | `302 → 330` | 28 s，由 ATR `AL→LLupper` 11 s、空载回 LP 6 s、`LP→AL` 11 s 组成 |
| 最后一对 4×1 离开 LLupper → 第一对 2×2 进入 LLupper | `343 → 389` | 46 s；LLupper 先完成 30 s 复位，混跑对还需完成单槽 AL 串行服务并由 ATR 搬入 |

因此，最新 clean10 解中最显眼的 AL／LL 空白主要是共享 ATR、单槽 AL 和有状态 LL 的管线衔接，不是显式的工艺模式切换时间。第一对 2×2 已在最后一批 4×1 尚未完成时提前做 AL／LL 准备，模型并未把两种模式的全部上游路径串行化。

但旧的 clean3 半时长结果不能据此证明所有可见空档都必需：例如 16 片混跑虽然主目标 `optimal/gap=0`，稳定性阶段是 `not_run`，独立重建的最大物理等待达到 `553 s`。clean3 还可能恰在 4×1→2×2 边界触发 500 s 腔室清洁。前者是同一 Cmax 下未压缩的任意等待，后者才是清洁规则要求；绘图时必须分别标识。

现有证据不支持删除 4×1→2×2 的顺序约束或强行让 AL／LL 泳道无缝。若业务上要求 AL／LL 也连续，需要增加中间缓存、允许不同腔室交错模式，或改变 ATR／LL 资源结构，这些都会改变被投稿模型而不是单纯改善求解器。当前正确处理是：吞吐率扫描使用主目标精确证书；投稿甘特图另用 `full` 二阶段，并且只有二阶段也 `optimal/gap<=1e-8` 才导出。

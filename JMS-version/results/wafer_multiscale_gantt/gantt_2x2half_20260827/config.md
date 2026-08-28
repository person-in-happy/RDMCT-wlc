# JMS 甘特图实验配置：10 次加工后清洁（2x2 工艺时间修正版）

本配置用于 8、16 片 wafer。所有时间单位均为秒。

> 2026-08-27 配方更正：2x2 应为两次各 90 s，总计 180 s；旧的两次各 180 s（总计 360 s）是错误配方。本次只重建纯 2x2 和 1:1 混跑；纯 4x1 始终为一次 180 s，不受本次修改影响。

## 1. 工艺与清洁参数

| 参数 | 值 | 含义 |
| --- | ---: | --- |
| 工艺腔室 | CH2、CH3 | 两个共享旋转工艺腔室 |
| 4x1 工艺时间 | 180 | 一次满腔工艺；本次未修改 |
| 2x2 第一次工艺时间 | **90** | `--mix_boundary_process_time=90` |
| 2x2 第二次工艺时间 | **90** | `--mix_internal_process_time=90` |
| 2x2 工艺总时间 | **180** | 90 + 90，与 4x1 相同；不含搬运和旋转 |
| 清洁间隔 | 每腔室 10 个满腔工艺周期 | CH2、CH3 分别累计 |
| 清洁加工时间 | 500 | 不含 PEC 搬运和旋转 |
| 腔室 180° 旋转 | 2 | 每次旋转时间 |
| 腔室转运动作最小间隔 | 1 | `pm_transfer_gap` |

2x2 的两次工艺分别计为一个满腔工艺周期。清洁批次为 `PEC+PEC / PEC+PEC`；尾片不足时也使用 PEC/dummy 辅助晶圆填满物理槽位。

## 2. 机器人、模块和模型参数

| 参数 | 值 |
| --- | ---: |
| ATR 物理机器人 / wafer 容量 | 1 / 2 |
| VTR 物理机器人 / wafer 容量 | 1 / 4 |
| ATR 装载或卸载时间 | 4 |
| ATR 路径移动时间 | 3 |
| ATR 完整带片搬运 | 11（4 + 3 + 4） |
| ATR 空载 LL-LP 返回 | 6 |
| ATR AL 双片交换 | 8 |
| VTR 带片搬运 / 空载复位 | 4 / 4 |
| AL 最小标定占用 | 20 / wafer |
| LLupper / LLlower 转换 | 30 / 25 per slot |
| AL、LLupper、LLlower 容量 | 1、2、2 slots |
| 产品 batch size | 4 |
| PM 数量 / 建模步数 | 2 / 13 |
| 每个 PM 最大 4x1 batch slots | 15 |
| 可复用 PEC / PEC storage | 8 / 10 slots |
| Big-M | 10000 |
| 模块 / 机器人最大驻留 | 10000 / 10000 |
| `max_schedule_wait_time` | 0（禁用硬上限） |
| 生成稳定化目标 / 工艺策略 | `compact_resource_idle` / `auto` |

产品路径：

`LP -> ATR -> AL -> ATR -> LLupper -> VTR -> CH -> VTR -> LLlower -> ATR -> LP`

## 3. 本次重新生成的四个实例

| 规模 | 纯 2x2 | 1:1 混跑 |
| --- | --- | --- |
| 8 wafer | 0×4x1 + 8×2x2 | 4×4x1 + 4×2x2 |
| 16 wafer | 0×4x1 + 16×2x2 | 8×4x1 + 8×2x2 |

`run_wafer8_16_clean10_gantt_evidence.ps1` 默认只处理以上四个实例。若确需把未修改的 8/16 片纯 4x1 一起重算，可显式加 `-IncludeUnchanged4x1`；本次投稿证据更新不需要该参数。

脚本会检查 `model.md` 中 4x1=180 s、含 2x2 的实例每次曝光=90 s、cleaning interval=10，并且只在 `status=optimal`、`gap <= 1e-8`、独立 `checkSol` 通过时导出甘特图。

修正版实例与结果使用独立路径，不覆盖旧配方：

- 实例：`generated_instances/jms_clean10_small_2x2half/`
- manifest：`JMS/wafer8_16_clean10_half2x2_gantt_suites.json`
- 甘特图：`JMS/results/wafer_multiscale_gantt/gantt_2x2half_20260827/`

旧 `gantt/` 中的纯 2x2 和混跑图基于 180+180 配方，不能继续使用；其中纯 4x1 图的工艺时间定义未改变。

## 4. 从 LP/SPBS 生成到最优甘特图的完整命令

第一次执行修正版时不要加 `-SkipGeneration`。

```powershell
conda activate a3cenv
Set-Location 'D:\git\git\RDMCT-A3C'

powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File '.\JMS\run_wafer8_16_clean10_gantt_evidence.ps1' `
  -TimeLimit 7200 `
  -WarmStartTimeLimit 1200 `
  -MemoryLimitMB 4096 `
  -ScipVerbosity 4 `
  -RunLabel 'jms_clean10_half2x2_opt_20260827' `
  -Python 'G:\conda\envs\a3cenv\python.exe'
```

该命令仅重新生成并求解 8/16 片的纯 2x2 和混跑四个实例，再完成独立验证及 JSON/SVG/HTML 导出。7200 s 为每个实例的求解上限。
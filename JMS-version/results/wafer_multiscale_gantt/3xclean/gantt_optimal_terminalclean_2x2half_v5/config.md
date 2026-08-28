# JMS 3xclean 甘特图实验配置（2x2 工艺时间修正版）

本配置用于 8、16、17、20 片 wafer 的纯 2x2、纯 4x1 和 1:1 混跑实验。所有时间单位均为秒。

> 2026-08-27 配方更正：旧配置把 2x2 的两次工艺都设成了 180 s，即总工艺时间 360 s；这是错误配方。正确值是每次 90 s、两次合计 180 s，与一次 4x1 的 180 s 相同。基于旧配方得到的最优值、warm start 和甘特图不能作为新配方的证据。

## 1. 工艺与清洁参数

| 参数 | 值 | 含义 |
| --- | ---: | --- |
| 工艺腔室 | CH2、CH3 | 两个共享旋转工艺腔室 |
| 4x1 工艺时间 | 180 | 一次满腔 4x1 工艺 |
| 2x2 第一次工艺时间 | **90** | `--mix_boundary_process_time=90` |
| 2x2 第二次工艺时间 | **90** | `--mix_internal_process_time=90` |
| 2x2 工艺总时间 | **180** | 90 + 90，与 4x1 相同；不含搬运和旋转 |
| 清洁间隔 | **每腔室 3 个满腔工艺周期** | CH2、CH3 分别累计；达到第 3 次即触发 |
| 清洁加工时间 | 500 | 纯清洁加工，不含 PEC 装卸和旋转 |
| 腔室 180° 旋转 | 2 | 每次旋转时间 |
| 腔室转运动作最小间隔 | 1 | `pm_transfer_gap` |

2x2 的第一次、第二次工艺各自占用一个满腔工艺周期，因此都会参与“每 3 次满片加工触发清洁”的计数。被触发的终端清洁也计入 `c_max`，不能延迟到 Big-M 上界。

每次清洁使用 `PEC+PEC / PEC+PEC` 四片辅助晶圆，执行正常 VTR 装卸、旋转和 500 s 清洁加工。尾片不能填满物理槽位时同样由 PEC/dummy 辅助晶圆补齐；辅助晶圆不是产品 wafer。

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
| VTR 带片搬运 | 4 |
| VTR 不同端点间空载复位 | 4 |
| AL 最小标定占用 | 20 / wafer |
| LLupper 泵送/复位 | 30 / slot |
| LLlower 放气/复位 | 25 / slot |
| AL 容量 | 1 slot |
| LLupper / LLlower 容量 | 各 2 个独立 slot |
| 产品 batch size | 4 |
| PM 数量 | 2 |
| 建模步数 | 13 |
| 每个 PM 最大 4x1 batch slots | 15 |
| 可复用 PEC | 8；每腔固定 4 片 |
| PEC storage 容量 | 10 slots |
| Big-M | 10000 |
| 模块 / 机器人最大驻留 | 10000 / 10000 |
| `max_schedule_wait_time` | 0（禁用该硬上限，不表示零等待） |
| 生成稳定化目标 | `compact_resource_idle` |
| 工艺模式策略 | `auto` |

产品路径：

`LP -> ATR -> AL -> ATR -> LLupper -> VTR -> CH -> VTR -> LLlower -> ATR -> LP`

PEC 路径：

`PEC storage -> VTR -> CH -> VTR -> PEC storage`

每个 wafer 规模包含纯 2x2、纯 4x1、1:1 混跑三种模式。17 片混跑按奇数规则使用 9 片 4x1 和 8 片 2x2。

## 3. 求解与投稿证据门槛

- Python：`G:\conda\envs\a3cenv\python.exe`，运行前必须 `conda activate a3cenv`。
- 冻结模型：Proposed，training seed 1，epoch 60。
- checkpoint SHA-256：`23961d2d9f09473982a79271642fca1d6e76cd0bf3837240d5e38a2361d824ce`。
- 2x2/混跑实例由生成器重新构造 SPBS warm start；旧 `180+180` 配方的认证 warm start 已从执行脚本中移除，不能复用。
- 脚本强制检查生成的 `model.md`：4x1 必须为 180 s，2x2 每次必须为 90 s，cleaning interval 必须为 3。
- 求解使用 `--no_resume`、SCIP optimality emphasis 和 aggressive heuristics。
- 只有 `status=optimal`、`gap <= 1e-8` 且独立 SCIP `checkSol` 通过的结果才会导出甘特图。
- 清洁使用青绿色 `#2A9D8F`；清洁窗口内其他模块等待不绘制；PEC/dummy 等待不绘制。这只是渲染过滤，物理解仍完整参与验证。

修正版实例与结果使用独立路径，不覆盖旧配方：

- 实例：`generated_instances/jms_3xclean_2x2half/`
- manifest：`JMS/wafer_3xclean_half2x2_gantt_suites.json`
- 甘特图：`JMS/results/wafer_multiscale_gantt/3xclean/gantt_optimal_terminalclean_2x2half_v5/`

旧目录 `gantt_optimal_terminalclean_makespan_v4/` 使用 180+180 配方，已失效。当前文档不列新最优值，因为修正配方尚未重新完成求解；不得沿用旧 `c_max`。

## 4. 从 LP/SPBS 生成到最优甘特图的完整命令

第一次执行修正版时不要加 `-SkipGeneration`，否则脚本会检测到旧 `model.md` 的 180 s 并停止。

```powershell
conda activate a3cenv
Set-Location 'D:\git\git\RDMCT-A3C'

powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File '.\JMS\run_wafer_3xclean_gantt_evidence.ps1' `
  -TimeLimit 7200 `
  -WarmStartTimeLimit 1200 `
  -MemoryLimitMB 4096 `
  -ScipVerbosity 4 `
  -StabilityProfile stage2_off `
  -RunLabel 'jms3clean_half2x2_opt_20260827' `
  -Python 'G:\conda\envs\a3cenv\python.exe'
```

该命令生成 12 个新 LP/SPBS，运行 Proposed+SCIP，执行独立物理可行性与最优性门槛检查，再导出 JSON、SVG 和 HTML。7200 s 是每个实例的求解上限，不是整个批次的总时长；若任一实例未证明 optimal，脚本会停止且不会把该批次包装成投稿证据。
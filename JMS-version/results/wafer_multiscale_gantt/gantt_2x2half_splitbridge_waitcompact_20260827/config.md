# JMS 甘特图配置：每 10 次满腔加工后清洁

本配置用于 8、16 片 wafer 的纯 2×2 和 4×1/2×2=1:1 混跑。时间单位均为秒。纯 4×1 配方没有变化，默认不重复生成；如需一起运行，向脚本添加 `-IncludeUnchanged4x1`。

## 工艺与设备参数

| 参数 | 值 | 命令/说明 |
| --- | ---: | --- |
| 工艺腔室 | CH2、CH3 | 两个共享旋转腔室 |
| 4×1 加工 | 180 | `--full_process_time=180` |
| 2×2 第一次加工 | 90 | `--mix_boundary_process_time=90` |
| 2×2 第二次加工 | 90 | `--mix_internal_process_time=90` |
| 2×2 总加工 | 180 | 90+90，与 4×1 相同；不含搬运和旋转 |
| 清洁触发 | 每腔累计 10 个满腔工艺周期 | 两次 2×2 曝光各计一次 |
| 清洁加工 | 500 | 纯 PEC 清洁，不含装卸/旋转 |
| 腔室 180° 旋转 | 2 | `--pm_rotation_time_180=2` |
| PM 搬运动作间隔 | 1 | `--pm_transfer_gap=1` |
| ATR 容量 / 路径移动 | 2 / 3 | 装片或卸片各 4；一条带片路径共 11 |
| ATR 空载 LL→LP | 6 | 两段 3 s |
| AL 标定 / 双片交换 | 20 / 8 | AL 容量 1 |
| VTR 容量 / 带片动作 / 空载复位 | 4 / 4 / 4 | 一个物理 VTR |
| LLupper / LLlower | 30 / 25 | 各 2 个独立 slot |
| PEC | 8 | 每腔固定 4 个可复用 token；storage 10 slots |
| Big-M | 10000 | `--big_m=10000` |
| 模块 / 机器人最大驻留 | 10000 / 10000 | 仅为安全上界 |
| 硬等待上限 | 0 | 禁用，不表示零等待 |

产品路径：`LP -> ATR -> AL -> ATR -> LLupper -> VTR -> CH -> VTR -> LLlower -> ATR -> LP`。

尾片不足时使用 PEC/dummy 补满物理槽位。清洁批次为 `PEC+PEC / PEC+PEC`。

## 2×2 bridge 修正

旧模型把每个中间 bridge 强制成一次原子 `LLupper -> CH -> LLlower` 交换。因此，即使产品已加工完成且 VTR 空闲，只要下一对产品尚未到达 LLupper，旧模型也不允许先卸出产品；旧解的 `optimal` 只是在这个受限动作集合内成立。

当前模型允许二选一：

- 来片已就绪：一次 4 s combined bridge，同时卸出旧 pair、装入新 pair；
- 来片未就绪：先用 4 s 执行 `CH -> LLlower` 提前卸片，VTR 空载复位，之后再用 4 s 执行 `LLupper -> CH` 装片。

腔室图分别绘制 `2x2 early unload`、`chamber vacant / waiting for incoming pair` 和 `2x2 later load`。空腔等待不再误画成已完成产品的腔内等待。

## 求解、旧训练与发布门槛

- Python：`G:\conda\envs\a3cenv\python.exe`；运行前必须 `conda activate a3cenv`。
- 使用可审计的旧 50-epoch 训练 checkpoint：
  `data\mip_20260710\_mix_wafer18_20260710.lp_mix_wafer18\_mix_wafer18_20260710.lp_mix_wafer18_2026_07_10_10_19_40_0000--s-1\params.pkl`
- checkpoint SHA-256：`0895a8ad74c745591bc1bbc21bafa77b4df1d7b83c3a4f07494e35118005fdec`。
- 说明：历史 2026-07-11 配置曾指向 `data/mip_20260710/params.pkl`，该根文件现在不存在；上述 checkpoint 是该历史目录下最后一个完整 50-epoch、23D、with-token 训练，是当前能逐字节审计的旧训练代理，不能宣称与已丢失根文件完全相同。
- 第一阶段严格最小化 `c_max`。
- 第二阶段固定第一阶段 `c_max` 和产品工艺路由身份，但释放 ATR/VTR 资源顺序、AL/LL/PEC token 时隙分配和 combined/split bridge 选择；启用 `--schedule_linear_physical_route_only` 后，目标严格对应独立校验器的六段产品路线等待：ATR→AL、AL→LLupper、LLupper→VTR、VTR→PM、PM→VTR、LLlower→ATR，最小化 `总物理路线等待 + 10×最大单段等待`，cadence 权重为 0。
- 第二阶段只在第一阶段已经证明 `optimal` 后启动；主阶段若超时，会保留 incumbent 并记录 `stability_status=skipped_primary_not_optimal`，不会用未证最优的 `c_max` 生成投稿图。
- 旧 checkpoint 只在根节点执行 learned inference。曾测试的非根候选顺序实验既不属于旧训练策略，也没有形成可复现的统一优势，相关实验代码已撤销；正式命令固定 `ScipNonrootSeparationRounds=0`。16 片纯 2×2 的 180 s root-only 诊断仅得到 `c_max≈914`、gap `22.85%`，因此不是最优证书，脚本会拒绝导出该结果。
- 只有同时满足以下条件才导出投稿甘特图：物理等待目标和排程决策释放开关均为 `true`、`primary_status=optimal`、主阶段 `gap<=1e-8`、`stability_status=optimal`、二阶段 `gap<=1e-8`、独立 SCIP `checkSol` 通过。

2026-08-27 的 8 片纯 2×2 端到端诊断已通过：`c_max=578`、总物理路径等待 `224`、最大单段等待 `28`；主阶段与物理等待阶段均为 `optimal/gap=0`，独立物理校验通过。48 个路线间隙中只有 8 个非零：每对晶圆的第一片在 `AL→LLupper` 等待 28 s，第二片在 `ATR→AL` 等待 28 s，其余 40 个间隙为 0；这是单槽 AL 串行标定与成对搬运在同一最优 `c_max` 下的等待，不是 PM/VTR 卸片拖延。旧图对应值为 450 和 50。该单例仅验证链路，不替代完整 8/16 批次。

## 路径

- 实例：`generated_instances/jms_clean10_small_2x2half/`
- manifest：`JMS/wafer8_16_clean10_half2x2_gantt_suites.json`
- 脚本：`JMS/run_wafer8_16_clean10_gantt_evidence.ps1`
- 新甘特图：`JMS/results/wafer_multiscale_gantt/gantt_2x2half_splitbridge_waitcompact_20260827/`
- 运行记录：`JMS/results/wafer_multiscale_gantt/runs/wafer8_16_clean10/<run_label>/`
- 独立验证：`JMS/results/wafer_multiscale_gantt/validation/wafer8_16_clean10/<run_label>/`

旧目录 `gantt_2x2half_20260827/` 使用原子 bridge，不作为最终等待紧致性证据。

## 完整命令（8/16 片，纯 2×2 + 1:1 混跑）

首次执行且冻结 LP 不存在时不要加 `-SkipGeneration`；当前恢复命令的 LP 已存在，所以使用该开关。`9000=5400+3600`：主阶段预算仍为原来的 5400 s，只把等待压缩预算从 1800 s 增加到 3600 s。第二阶段节点上限使用 `-1`（不限节点），避免像 `wafer16_mixed11_clean10` 一样在 794 s、尚未用完时间预算时被 500000 节点提前终止。脚本会对同一确定性路径下已有 `.sol` 做完整 `checkSol` 后作为 incumbent 复用，但 SCIP 仍重新证明主阶段和等待阶段；分析器按 `started_at` 选择同一路径的最新重跑元数据，不会继续误读旧 `nodelimit` 行。

```powershell
conda activate a3cenv
Set-Location 'D:\git\git\RDMCT-A3C'

powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File '.\JMS\run_wafer8_16_clean10_gantt_evidence.ps1' `
  -SkipGeneration `
  -TimeLimit 9000 `
  -StabilityTimeLimit 3600 `
  -StabilityNodeLimit -1 `
  -WarmStartTimeLimit 1200 `
  -MemoryLimitMB 4096 `
  -ScipVerbosity 4 `
  -ScipHeuristicsProfile aggressive `
  -ScipNonrootSeparationRounds 0 `
  -RunLabel 'jms_clean10_half2x2_splitbridge_physicalwait_rootonly_legacy50_20260827' `
  -Checkpoint 'data\mip_20260710\_mix_wafer18_20260710.lp_mix_wafer18\_mix_wafer18_20260710.lp_mix_wafer18_2026_07_10_10_19_40_0000--s-1\params.pkl' `
  -Python 'G:\conda\envs\a3cenv\python.exe'
```

若也要重跑未改变的纯 4×1，追加 `-IncludeUnchanged4x1`。仅做 8 片纯 2×2 诊断时可追加 `-OnlyWafer8Pure22`，但该命令不构成完整批次证据。
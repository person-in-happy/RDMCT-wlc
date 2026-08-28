# JMS 3xclean 甘特图配置：每 3 次满腔加工后清洁

本配置用于 8、16、17、20 片 wafer 的纯 2×2、纯 4×1 和 4×1/2×2=1:1 混跑。17 片混跑按奇数规则使用 9 片 4×1、8 片 2×2。时间单位均为秒。

## 工艺与设备参数

| 参数 | 值 | 命令/说明 |
| --- | ---: | --- |
| 工艺腔室 | CH2、CH3 | 两个共享旋转腔室 |
| 4×1 加工 | 180 | `--full_process_time=180` |
| 2×2 两次加工 | 90 + 90 | 总计 180，与 4×1 相同 |
| 清洁触发 | 每腔累计 3 个满腔工艺周期 | 两次 2×2 曝光各计一次 |
| 清洁加工 | 500 | 不含 PEC 装卸/旋转 |
| 腔室旋转 / PM 动作间隔 | 2 / 1 | 秒 |
| ATR 容量 / 路径移动 / 装卸 | 2 / 3 / 4 | LL→LP 空载复位 6；AL 交换 8 |
| VTR 容量 / 带片动作 / 空载复位 | 4 / 4 / 4 | 一个物理 VTR |
| AL / LLupper / LLlower | 20 / 30 / 25 | 容量分别为 1 / 2 / 2 |
| PEC | 8 | 每腔固定 4 个可复用 token；storage 10 slots |
| Big-M | 10000 | `--big_m=10000` |
| 模块 / 机器人最大驻留 | 10000 / 10000 | 安全上界 |
| 硬等待上限 | 0 | 禁用 |

达到第 3 次工艺即触发清洁，包括终端触发；终端清洁完成时间计入 `c_max`。每次清洁使用四片 PEC。尾片不足时同样用 PEC/dummy 补满。

## 2×2 bridge 与甘特图语义

中间 bridge 既可在来片就绪时执行一次 4 s combined 交换，也可先提前卸出已完成 pair、VTR 复位、稍后再装入下一 pair。这样，VTR 空闲时不会因模型动作缺失而强迫已完成产品滞留腔室。

清洁使用青绿色 `#2A9D8F`；清洁窗口内其他模块等待不绘制；PEC/dummy 等待不绘制。该过滤只影响渲染，完整解仍参与独立物理验证。

## 求解、旧训练与证书

- Python：`G:\conda\envs\a3cenv\python.exe`，运行前必须 `conda activate a3cenv`。
- 使用旧 50-epoch checkpoint：
  `data\mip_20260710\_mix_wafer18_20260710.lp_mix_wafer18\_mix_wafer18_20260710.lp_mix_wafer18_2026_07_10_10_19_40_0000--s-1\params.pkl`
- SHA-256：`0895a8ad74c745591bc1bbc21bafa77b4df1d7b83c3a4f07494e35118005fdec`。
- 该文件是历史 `data/mip_20260710` 目录下可审计的最后一个完整旧训练；已丢失的 `data/mip_20260710/params.pkl` 无法证明与它逐字节相同。
- 第一阶段最小化 `c_max`；第二阶段在同一 `c_max` 下释放 ATR/VTR 资源顺序、AL/LL/PEC token 时隙分配和 combined/split bridge。启用 `--schedule_linear_physical_route_only` 后，目标与独立校验器一致，最小化六段产品路线的 `总等待 + 10×最大单段等待`，cadence 权重为 0。
- 旧 checkpoint 只在根节点执行 learned inference。曾测试的非根候选顺序实验在 3xclean 的 90 s 同预算诊断中没有改善证明进度，且不属于旧训练策略，相关实验代码已撤销；正式命令固定 `ScipNonrootSeparationRounds=0`。
- 只有第一阶段已经证明 `optimal` 才启动第二阶段；若主阶段超时，则保留 incumbent 并记录 `stability_status=skipped_primary_not_optimal`，绝不把未证最优的 `c_max` 当作词典序基准。
- 发布门槛要求物理等待目标和排程决策释放开关均为 `true`，主阶段和等待压缩阶段均为 `optimal`、各自 gap 均不超过 `1e-8`，且独立 SCIP `checkSol` 通过。
- wafer20 纯 2×2 的 2125.999897 s 旧解已按 `combined=1` 补齐新变量并通过新 LP 的独立 `checkSol`；它只作为可行上界，SCIP 仍须独立证明全局最优。

## 路径

- 实例：`generated_instances/jms_3xclean_2x2half/`
- manifest：`JMS/wafer_3xclean_half2x2_gantt_suites.json`
- 脚本：`JMS/run_wafer_3xclean_gantt_evidence.ps1`
- 新甘特图：`JMS/results/wafer_multiscale_gantt/3xclean/gantt_optimal_terminalclean_2x2half_splitbridge_waitcompact_v6/`
- 新 incumbent：`JMS/warm_starts/wafer20_22_clean3_2x2half_splitbridge_cmax2126.sol`

旧 `gantt_optimal_terminalclean_2x2half_v5/` 使用原子 bridge 或没有等待压缩双证书，不作为最终投稿证据。

## 完整命令（8/16/17/20 片 × 三种模式）

首次执行且冻结 LP 不存在时不要加 `-SkipGeneration`。当前冻结 LP 已存在，因此下面使用 `-SkipGeneration`。`16200=12600+3600`：主阶段仍保留原来的 12600 s，只扩大等待压缩阶段并取消独立节点上限（`-1`）；不是整批总时长。脚本按实例写哈希短名 checkpoint 和 `<run_label>/solve.log`；相同命令重跑时，会先复用当前 RunLabel 的已验解 `.sol`，没有时再回退到 `-ReuseSolutionRunLabel` 指定的旧解，但仍重新证明两个最优阶段。汇总文件名会在 Windows 路径过长时自动缩短，完整 `RunLabel` 仍保存在内容中。

旧批次 `jms3clean_half2x2_opt_20260827` 明确使用了 `stage2_off`，因此 12 个实例的 `stability_status=not_run` 是协议配置的必然结果，不是导出器误判。其 12 个 incumbent 均通过独立物理可行性检查，但 `wafer20_pure22_clean3` 的主阶段仅为 `timelimit`、gap `0.005200896926719607`；旧解只能加速新求解，不能作为完整投稿证书。

```powershell
conda activate a3cenv
Set-Location 'D:\git\git\RDMCT-A3C'

powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File '.\JMS\run_wafer_3xclean_gantt_evidence.ps1' `
  -SkipGeneration `
  -TimeLimit 16200 `
  -StabilityTimeLimit 3600 `
  -StabilityNodeLimit -1 `
  -WarmStartTimeLimit 1200 `
  -MemoryLimitMB 4096 `
  -ScipVerbosity 4 `
  -StabilityProfile full `
  -ScipHeuristicsProfile off `
  -ScipNonrootSeparationRounds 0 `
  -ReuseSolutionRunLabel 'jms3clean_half2x2_opt_20260827' `
  -RunLabel 'jms3clean_half2x2_full_reproof_20260828' `
  -Checkpoint 'data\mip_20260710\_mix_wafer18_20260710.lp_mix_wafer18\_mix_wafer18_20260710.lp_mix_wafer18_2026_07_10_10_19_40_0000--s-1\params.pkl' `
  -Python 'G:\conda\envs\a3cenv\python.exe'
```

若只重新证明最困难的 20 片纯 2×2，可在上述命令末尾追加 `-OnlyWafer20Pure22` 并换一个独立 `RunLabel`。单例结果只能作为该单例证据，不能替代 12 实例完整批次。
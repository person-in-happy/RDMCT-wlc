# 消融实验与证据解释指南

## 主实验矩阵

主消融采用结构模块开/关与 greedy/beam 的 2x2 设计，并增加 SCIP 外部基线：

| 方法 | 特征/结构模块 | 解码 | 权重共享目的 |
| --- | --- | --- | --- |
| SCIP | SCIP 原生 | 原生 | 非学习基线 |
| HEM | 13 维，无结构重排 | greedy | 基础学习方法 |
| HEM + Beam | 13 维，无结构重排 | beam | 与 HEM 共用 checkpoint，只检验 beam |
| HEM + Structure | 23 维，role-submodular | greedy | 与 Proposed 共用 checkpoint |
| Proposed | 23 维，role-submodular | beam | 完整方法 |

因此可以计算四个受控效应：HEM 到 HEM+Beam、HEM 到 HEM+Structure、
HEM+Beam 到 Proposed、HEM+Structure 到 Proposed。最后一组直接检验结构模块开启后
beam 是否缓解清洁大规模实例上的退化。

## 四个主指标

当前问题是最小化模型，以下四个指标均为越小越好，但证据含义不同：

1. **Mean Solving Time**：平均墙钟时间。只有在最优率、可行解率和解质量可比时，
   更小才表示更快。大量 timeout 时应以 PAR-2 辅助，不能把几秒 watchdog 差异写成加速。
2. **Mean Best Objective**：有可行解运行中的平均 incumbent 目标值。本项目中主要是
   makespan，越小表示调度质量/WPH 越好。必须同时报告 incumbent rate，防止仅对少数有解
   样本取均值造成选择偏差。
3. **Mean Primal-Dual Gap**：当前最好可行解与可证明界之间的相对差距。越小表示最优性
   证明更强，0 表示已证明最优；它同时受 primal incumbent 和 dual bound 影响。
4. **Mean Primal-Dual Integral (PDI)**：求解全程 primal-dual gap 对时间的积分。越小表示
   更早找到好解并更快收紧界，是 timeout 较多时最适合评价 cut selection 的主指标。

Mean Nodes 不是单调优劣指标。节点少可能表示搜索树高效，也可能表示根节点停滞；旧结果中
`a3c_only` 只有 1 个节点但 objective、gap 和 PDI 都更差，正好说明不能用节点数单独证明优势。

## 旧 ablation_results 的正确解读

`ablation_petri_transfer_20260708_234743` 只有 1 个实例、1 个种子，且所有方法均 timeout，
只能作为案例，不能作为统计结论。

- 完整方法 objective 为 1756.00，低于 SCIP 的 1915.01，单次相对改善约 8.30%。
- 完整方法 gap 为 0.6199，低于 SCIP 的 0.7764，绝对减少约 0.1565，相对减少约 20.2%。
- 完整方法 PDI 为 78111.88，低于 SCIP 的 81156.96，单次改善约 3.75%；尚未达到预设 5% 效应门槛。
- 完整方法时间为 1848s，SCIP 为 1832s。由于两者均达到 1800s time limit，不能声称加速。
- 旧 `beam_only` 实际是启发式结构重排，不是 HEM+Beam；旧四方法命名不能用于最终论文表格。

这组结果最多支持“完整方法在该实例上得到更好的 incumbent、gap 和 PDI”，不能支持
“总体显著优于 SCIP/HEM”。

## 论文结论门槛

正式报告以相同 instance-seed-training-seed 配对，主指标采用单侧 Wilcoxon signed-rank，
并对多个基线执行 Holm 校正。只有每个基线同时满足以下条件才标记 claim-ready：

- 至少 10 个有效 PDI 配对；
- Proposed 平均 PDI 改善不低于 5%；
- Proposed 胜率不低于 60%；
- Proposed 可行解率不低于对应基线；
- Holm 校正后 `p < 0.05`。

正式表格还应报告 objective、gap、PAR-2、incumbent rate 和 optimal rate。若 PDI 显著但
objective 没有改善，应把结论限定为“更好的 anytime 求解效率”；只有 objective/gap 也一致
改善时，才可以进一步声称“得到更高质量解并收紧最优性界”。

## 正式命令

```powershell
.\aaai\run_aaai.ps1 -Stage train-hem -Seeds '1,2,3,4,5'
.\aaai\run_aaai.ps1 -Stage train-proposed -Seeds '1,2,3,4,5'
.\aaai\run_aaai.ps1 -Stage benchmark-all -Seeds '1,2,3,4,5' -TimeLimit 600 `
  -Suites 'petri_large,petri_wafer100_stress'
```

若论文要把贡献进一步归因到“10 个结构特征本身”，再运行机制实验：

```powershell
.\aaai\run_aaai.ps1 -Stage train-feature-only -Seeds '1'
.\aaai\run_aaai.ps1 -Stage benchmark-mechanism -Seeds '1,2,3,4,5' `
  -TimeLimit 600 -Suites 'petri_large'
```

该实验依次比较 HEM、23D feature-only、结构重排 greedy 和完整 beam。主五组用于整体
优势结论，机制实验用于支持“结构表示”和“结构重排”各自的贡献。

`petri_large` 包含 4 个留出清洁实例并使用 5 个 SCIP seed，形成 20 个统计单元；100 片
实例固定 seed 1 作为 stress case。跨 MILP 族泛化实验另行使用 `-Suites all`，不要与主 Petri
消融混成一个均值。

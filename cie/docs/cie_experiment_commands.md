# C&IE 实验命令索引

> 完整且唯一的正式协议是 [`../README.md`](../README.md)。当前暂停/恢复、最多三路的单行命令、投稿包清单和时间估算见 [`cie_submission_runbook_zh.md`](cie_submission_runbook_zh.md)。本文只作快速索引，不单独定义实例、seed、预算或统计口径。

所有命令从仓库根目录的 PowerShell 执行。

## 阶段顺序

| 顺序 | Stage | 作用 |
| ---: | --- | --- |
| 1 | `check` | 检查 Python 依赖和 CLI |
| 2 | `smoke` | CPU 端到端小测试；必须在冻结 validation 前 |
| 3 | `generate-all` | 生成并冻结 validation/core/sensitivity/OOD |
| 4 | `train-all` | HEM、feature-only、Proposed 各训练 5 seeds |
| 5 | `gpu-smoke` | 检查新 checkpoint 的 GPU 推理 |
| 6 | `tune-acs` | 只在 validation 上调 ACS |
| 7 | `warmstarts-*` | 生成 core/sensitivity/OOD 的 SPBS |
| 8 | `benchmark-*` | Validation/Main/Stability/DOE/SPBS/Sensitivity/OOD |
| 9 | `run_cie_postprocess.ps1` | 合并、独立验解、精确审计、投稿统计和DOE图 |

## 最小命令

```powershell
.\cie\run_cie_single.ps1 -Stage check -LogId cie_check
```

```powershell
.\cie\run_cie_single.ps1 -Stage smoke -LogId cie_smoke
```

正式模型：

```powershell
.\cie\run_cie_single.ps1 -Stage train-all -Seeds '1,2,3,4,5' -GpuDevice cuda:0 -LogId cie_train_all_repro_v1
```

正式 Main/OOD 必须传冻结参数 `-AcsWeightsFile cie\results\repro_manifest\selected_acs.json`；完整命令只从投稿执行手册复制。

runner 默认拒绝训练来源或 seed 不可审计的旧 checkpoint。`-AllowLegacyCheckpoints` 只用于非论文 `gpu-smoke`，不得用于正式 campaign。

算法优势实验固定使用 `full`（阶段 2 开启、`linear`）。两个排程因素只
通过 `benchmark-stability` 的 `full/stage2_off/linear_off` 三组进行
单因素对比，命令见正式协议。

## 精确行数

| Validation | Main | Stability | DOE | SPBS | Sensitivity | OOD |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 4 | 2700 | 1500 | 300 | 960 | 80 | 729 |

协议定义见 [`../README.md`](../README.md)；实际执行命令、恢复、合并、统计和投稿门槛见 [`cie_submission_runbook_zh.md`](cie_submission_runbook_zh.md)。

## 历史清单

以下文件仅记录旧机器或旧 campaign，不是当前协议：

- `cie_single_way_commands.md`
- `cie_two_way_parallel_commands.md`
- `cie_current_parallel_commands.md`

不要从历史清单复制硬编码盘符、硬件版本、campaign ID、ACS latest 或旧 seed 集合。

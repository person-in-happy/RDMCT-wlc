# PDI与最优性补充实验命令

## 口径

- PDI是求解窗口内归一化原始--对偶gap的时间积分，越低越好；它不是终点最优性指示量。
- 证明最优必须同时满足`status=optimal`和终止`gap=0`。
- 不能预设或保证“只有Proposed达到0”。只有在预先固定实例、预算、seed和分析规则后，结果实际满足该条件时才能报告。
- 当前冻结Main矩阵已经完成2700次运行，足以支持“Proposed取得最低观察平均PDI”，但不支持“只有Proposed证明最优”或“显著优于所有方法”。

## 从零独立复现Main矩阵

在已激活项目Python环境、CUDA可用且冻结checkpoint/ACS文件保持不变的PowerShell中执行：

```powershell
Set-Location D:\git\git\RDMCT-A3C
$env:CUDA_MODULE_LOADING='LAZY'
$env:RDMCT_COMPACT_TEXT_LOG='1'
$env:RDMCT_TEXT_LOG_MAX_MB='2'
$env:RDMCT_TEXT_LOG_BACKUP_COUNT='1'

.\cie\run_cie_single.ps1 `
  -Stage benchmark-main `
  -CampaignId jms_proof_status_600s_v1 `
  -ShardTag all `
  -LogId jms_proof_status_600s_v1_all `
  -Seeds '1,2,3,4,5' `
  -TrainingSeeds '1,2,3,4,5' `
  -TimeLimit 600 `
  -MemoryLimitMB 2048 `
  -GpuDevice cuda:0 `
  -AcsWeightsFile cie\results\repro_manifest\selected_acs.json

.\cie\run_cie_postprocess.ps1 `
  -Stage main `
  -CampaignId jms_proof_status_600s_v1 `
  -SolverSeeds '1,2,3,4,5' `
  -TrainingSeeds '1,2,3,4,5' `
  -Reference proposed
```

运行可中断后原命令恢复；不要更换`CampaignId`或删除超时行。投稿判断应同时读取：

```text
cie/results/main/jms_proof_status_600s_v1/submission_analysis/
  cie_submission_method_summary.csv
  cie_submission_pairwise_tests.csv
  submission_audit.json
```

只有`submission_audit.json`为`PASS`，且预先固定的实例级检验支持相应结论时，才更新正文。若目标是比较“何时证明最优”，应分析达到`gap=0`的时间及删失的限时运行，而不是等待累计PDI“下降到0”；PDI作为累计量不会在求解过程中向0下降。

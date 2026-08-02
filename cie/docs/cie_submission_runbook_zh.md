# Computers & Industrial Engineering 投稿执行手册

> 审计时间：2026-08-01 23:42（Asia/Shanghai）。本文给出当前机器上的暂停/恢复方法和从现状走到可投稿状态的唯一执行顺序。实验协议定义仍以 [`../README.md`](../README.md) 为准。本文中的 PowerShell 命令均为单行命令，不使用续行符。

官方依据：[C&IE Guide for Authors](https://www.sciencedirect.com/journal/computers-and-industrial-engineering/publish/guide-for-authors)；[Elsevier LaTeX instructions](https://www.elsevier.com/en-gb/researcher/author/policies-and-guidelines/latex-instructions)。投稿要求可能变化，正式上传当天再次核对。

## 1. 先区分两条路线

### 1.1 当前 `cie_ood_1200s_mem4096_final_v1` 只是工程活动

当前三路 OOD 使用旧 AAAI provenance checkpoint，并且 `run_cie_benchmarks.py` 于 2026-07-31 23:04 修改、`environments.py` 于 2026-08-01 11:36 修改。training seed 1--4 的部分结果早于修改，training seed 5 晚于修改。逐项检查点只保证单个 training seed 内部一致，不能证明跨 training seed 使用同一代码。

截至审计时，旧活动共有 674/729 个无 runner error 的唯一观测：solver seed 1 为 222/243，seed 2 为 222/243，seed 3 为 230/243；剩余55项。把它补到729行只能完成工程记录，不能填入最终投稿结果表。

### 1.2 投稿级路线必须从冻结点重新开始

严格按当前协议，投稿级 `*_repro_v1` 正式 benchmark 为 0/6273 行，15个可审计训练模型为0/15。旧 Main、OOD、SPBS 和 smoke 不得并入新 campaign。投稿级路线禁止使用 `-AllowLegacyCheckpoints`。

## 2. 今晚如何暂停，明天如何恢复当前旧 OOD

当前三路均在 training seed 5 正常运行，错误日志为空：

| 分片 | 已同步写盘 | 正在运行 | 中断后恢复点 |
| --- | ---: | ---: | ---: |
| solver seed 1 | 24/45 | 25/45 | 重跑25/45 |
| solver seed 2 | 24/45 | 25/45 | 重跑25/45 |
| solver seed 3 | 32/45 | 33/45 | 重跑33/45 |

在三个原始终端中分别按一次 `Ctrl+C`，等待返回 PowerShell 提示符。不要使用 `Suspend-Process`，也不要只关闭编辑器窗口。已完成单项已执行 flush/fsync；最多损失当时正在求解的一项。

关机前检查，必须无输出：

```powershell
Get-CimInstance Win32_Process | Where-Object { ($_.Name -eq 'python.exe' -and $_.CommandLine -match 'run_cie_benchmarks.py' -and $_.CommandLine -match 'cie_ood_1200s_mem4096_final_v1') -or ($_.Name -eq 'powershell.exe' -and $_.CommandLine -match 'run_cie.ps1' -and $_.CommandLine -match 'cie_ood_1200s_mem4096_final_v1') } | Select-Object ProcessId,ParentProcessId,Name,CommandLine
```

若仍有残留 Python，先列出PID，再逐个执行 `Stop-Process -Id <PID> -Force`，然后重新运行上面的检查。不要用模糊进程名终止其他 Python 工作。

当前 runner 已加入旧模型 provenance 门禁，因此明天恢复旧活动必须显式使用 `-AllowLegacyCheckpoints`。这只授权旧活动收尾，不改变其“不可用于投稿”的性质。

solver seed 1：

```powershell
Set-Location D:\git\git\RDMCT-A3C; $env:CUDA_MODULE_LOADING='LAZY'; $env:RDMCT_COMPACT_TEXT_LOG='1'; $env:RDMCT_TEXT_LOG_MAX_MB='2'; $env:RDMCT_TEXT_LOG_BACKUP_COUNT='1'; .\cie\run_cie_single.ps1 -Stage benchmark-ood -CampaignId cie_ood_1200s_mem4096_final_v1 -ShardTag seed1 -LogId cie_ood_1200s_mem4096_final_v1_seed1 -Seeds '1' -TrainingSeeds '5' -TimeLimit 1200 -MemoryLimitMB 4096 -GpuDevice cuda:0 -AllowLegacyCheckpoints
```

solver seed 2：

```powershell
Set-Location D:\git\git\RDMCT-A3C; $env:CUDA_MODULE_LOADING='LAZY'; $env:RDMCT_COMPACT_TEXT_LOG='1'; $env:RDMCT_TEXT_LOG_MAX_MB='2'; $env:RDMCT_TEXT_LOG_BACKUP_COUNT='1'; .\cie\run_cie_single.ps1 -Stage benchmark-ood -CampaignId cie_ood_1200s_mem4096_final_v1 -ShardTag seed2 -LogId cie_ood_1200s_mem4096_final_v1_seed2 -Seeds '2' -TrainingSeeds '5' -TimeLimit 1200 -MemoryLimitMB 4096 -GpuDevice cuda:0 -AllowLegacyCheckpoints
```

solver seed 3：

```powershell
Set-Location D:\git\git\RDMCT-A3C; $env:CUDA_MODULE_LOADING='LAZY'; $env:RDMCT_COMPACT_TEXT_LOG='1'; $env:RDMCT_TEXT_LOG_MAX_MB='2'; $env:RDMCT_TEXT_LOG_BACKUP_COUNT='1'; .\cie\run_cie_single.ps1 -Stage benchmark-ood -CampaignId cie_ood_1200s_mem4096_final_v1 -ShardTag shardB -LogId cie_ood_1200s_mem4096_final_v1_seed3_resume -Seeds '3' -TrainingSeeds '5' -TimeLimit 1200 -MemoryLimitMB 4096 -GpuDevice cuda:0 -AllowLegacyCheckpoints
```

按近期约19分钟/项计算，三路并行临界路径约6小时39分，连同启动和汇总约7小时。运行期间不得修改签名代码、数据、模型或ACS。

## 3. 投稿前必须补齐的证据

| 项目 | 投稿目标 | 当前正式有效 | 目的 |
| --- | ---: | ---: | --- |
| 可审计模型 | 15 | 0 | HEM、feature-only、Proposed各5个独立training seeds |
| ACS validation网格 | 720 solves | 0 | 只在validation选择并冻结ACS参数 |
| Warm starts | 65 | 0 | core 48、sensitivity 8、OOD 9 |
| Validation | 4行 | 0 | 求解、写解和独立验解sanity |
| Main | 2700行 | 0 | 标称实例主比较与算法消融 |
| Stability | 1500行 | 0 | `full/stage2_off/linear_off`控制变量实验 |
| DOE | 300行 | 0 | 制造因素主效应和预设交互 |
| SPBS | 960行 | 0 | auto warm start与none组件对比 |
| Sensitivity | 80行 | 0 | 工艺和资源参数稳健性 |
| OOD | 729行 | 0 | 大规模分布外泛化 |

正式 benchmark 合计6273行。还必须完成全部 incumbent 解文件的独立可行性验证、制造指标、实例级聚合、效应量、置信区间、双侧配对Wilcoxon和Holm校正。

在冻结前必须先解决两项方法学缺口：

1. 论文机制表要求 cut-pool size、角色覆盖、冗余、callback开销和root-bound证据；当前runner只有部分callback时间，没有完整cut count、dual bound、root gap、LP iterations、首次/最佳解/证明时间。应先增加并测试遥测，或删除论文中对应声明。冻结后再改遥测会迫使正式实验全部重跑。
2. 论文写“按validation PDI选checkpoint”，但三个训练配置当前 `evaluate_freq=0`，协议又固定使用 `itr_60.pkl`。必须在“预先固定最后一轮”与“启用独立validation选择”之间二选一，并同步修改论文和协议，不能事后择优。

## 4. 正式冻结门槛

完成代码/指标修改后，建立干净、可追溯的冻结提交。当前工作区若不干净，不得开始正式campaign。

```powershell
python -m pip install matplotlib
```

```powershell
python -c "import numpy,scipy,matplotlib; print('numpy',numpy.__version__,'scipy',scipy.__version__,'matplotlib',matplotlib.__version__)"
```

```powershell
Set-Location D:\git\git\RDMCT-A3C; git status --short
```

```powershell
python -m pytest tests/test_training_and_cie_contract.py tests/test_cie_combine_runs.py tests/test_analyze_cie_solutions.py tests/test_audit_cie_submission.py tests/test_analyze_cie_submission.py tests/test_cie_runbook_schedule.py tests/test_cie_postprocess_contract.py -q
```

```powershell
$preStatus=@(git status --porcelain=v1 --untracked-files=all); if ($preStatus.Count -ne 0) { $preStatus; throw 'Worktree must be clean before creating the reproduction manifest.' }; New-Item -ItemType Directory -Force cie\results\repro_manifest | Out-Null; 'CLEAN_BEFORE_MANIFEST' | Set-Content cie\results\repro_manifest\git_status_before_manifest.txt; git rev-parse HEAD | Set-Content cie\results\repro_manifest\git_commit.txt; python -m pip freeze | Set-Content cie\results\repro_manifest\pip_freeze.txt; nvidia-smi | Set-Content cie\results\repro_manifest\nvidia_smi.txt
```

必须先在写任何manifest文件之前检查工作区；`git_status_before_manifest.txt` 只记录该门禁通过，不能用“创建manifest之后的git status”冒充运行前干净状态。

生成并冻结数据后保存hash：

```powershell
.\cie\run_cie_single.ps1 -Stage generate-all -LogId cie_generate_all_repro_v1
```

```powershell
Get-ChildItem cie\data -Recurse -File -Filter *.lp | Get-FileHash -Algorithm SHA256 | Export-Csv cie\results\repro_manifest\cie_lp_sha256.csv -NoTypeInformation
```

此后禁止修改 `run_cie_benchmarks.py`、`environments.py`、cut selector、pointer networks、beam search、常量、数据生成器、LP、训练配置、模型或ACS。仅修改说明文档不会改变实验签名，但正式提交仍应记录最终commit。

## 5. 训练、ACS与warm start

8GB GPU建议一次只训练一路。三类模型依次执行，每条命令内部运行seeds 1--5：

```powershell
.\cie\run_cie_single.ps1 -Stage train-hem -Seeds '1,2,3,4,5' -GpuDevice cuda:0 -LogId cie_train_hem_repro_v1
```

```powershell
.\cie\run_cie_single.ps1 -Stage train-feature-only -Seeds '1,2,3,4,5' -GpuDevice cuda:0 -LogId cie_train_feature_only_repro_v1
```

```powershell
.\cie\run_cie_single.ps1 -Stage train-proposed -Seeds '1,2,3,4,5' -GpuDevice cuda:0 -LogId cie_train_proposed_repro_v1
```

检查15个新 `variant.json` 中 CLI seed、SCIP seed、experiment seed相同，训练路径为当前 `cie/data/policy_training/train`，并只保存runner实际选择的15个 `itr_60.pkl` 路径与hash；禁止递归混入旧模型：

```powershell
$rows=foreach($family in @('hem','feature_only','proposed')){foreach($seed in 1..5){$dir="cie\models\$family\seed_$seed";$variant=Join-Path $dir 'variant.json';$checkpoint=Join-Path $dir 'itr_60.pkl';if(-not(Test-Path -LiteralPath $variant -PathType Leaf)-or-not(Test-Path -LiteralPath $checkpoint -PathType Leaf)){throw "Missing formal model: $family seed $seed"};$meta=Get-Content -LiteralPath $variant -Raw|ConvertFrom-Json;$trainingPath=[string]$meta.env.instance_file_path;$validPath=$trainingPath.Replace('/','\').ToLowerInvariant().EndsWith('cie\data\policy_training\train');if([int]$meta.parser_args.seed-ne$seed-or[int]$meta.parser_args.scip_seed-ne$seed-or[int]$meta.experiment.seed-ne$seed-or-not$validPath){throw "Non-auditable metadata: $variant"};[pscustomobject]@{family=$family;training_seed=$seed;checkpoint=(Resolve-Path -LiteralPath $checkpoint).Path;checkpoint_sha256=(Get-FileHash -LiteralPath $checkpoint -Algorithm SHA256).Hash;variant=(Resolve-Path -LiteralPath $variant).Path;variant_sha256=(Get-FileHash -LiteralPath $variant -Algorithm SHA256).Hash;training_path=$trainingPath}}};$rows|Export-Csv cie\results\repro_manifest\selected_checkpoint_manifest.csv -NoTypeInformation; .\cie\run_cie_single.ps1 -Stage gpu-smoke -GpuDevice cuda:0 -LogId cie_gpu_smoke_repro_v1
```

ACS只允许在validation上调，随后复制为固定文件：

```powershell
.\cie\run_cie_single.ps1 -Stage tune-acs -MemoryLimitMB 4096 -LogId cie_tune_acs_repro_v1
```

```powershell
$src=(Get-ChildItem cie\results\acs_tuning -Filter 'acs_grid_*.json' | Sort-Object LastWriteTime | Select-Object -Last 1).FullName; Copy-Item -LiteralPath $src -Destination cie\results\repro_manifest\selected_acs.json -Force; Get-FileHash cie\results\repro_manifest\selected_acs.json -Algorithm SHA256 | Export-Csv cie\results\repro_manifest\selected_acs_sha256.csv -NoTypeInformation
```

以下三条可在三个终端并行运行：

```powershell
.\cie\run_cie_single.ps1 -Stage warmstarts-core -WarmStartTimeLimit 180 -MemoryLimitMB 2048 -LogId warm_core_repro_v1
```

```powershell
.\cie\run_cie_single.ps1 -Stage warmstarts-sensitivity -WarmStartTimeLimit 600 -MemoryLimitMB 2048 -LogId warm_sensitivity_repro_v1
```

```powershell
.\cie\run_cie_single.ps1 -Stage warmstarts-ood -WarmStartTimeLimit 600 -MemoryLimitMB 4096 -LogId warm_ood_repro_v1
```

验收：core为48个generated和12个pure-4x1 not-applicable，sensitivity为8，OOD为9；`failures=0`且LP hash匹配。

## 6. 正式benchmark：最多三路

三个终端分别执行标记为A/B/C的队列，同一终端中的命令按出现顺序逐条执行，任意时刻最多三条。矩阵按solver seed和training seed拆开以均衡负载；一个阶段全部完成并验收后再进入下一阶段。所有Main/OOD命令显式使用冻结ACS。每天中断后只需原样重跑当时尚未完成的那条命令。

每次新开三个终端，先分别执行一次以下单行设置，避免SCIP文本日志膨胀：

```powershell
Set-Location D:\git\git\RDMCT-A3C; $env:CUDA_MODULE_LOADING='LAZY'; $env:RDMCT_COMPACT_TEXT_LOG='1'; $env:RDMCT_TEXT_LOG_MAX_MB='2'; $env:RDMCT_TEXT_LOG_BACKUP_COUNT='1'
```

### 6.1 Validation

```powershell
.\cie\run_cie_single.ps1 -Stage benchmark-validation -CampaignId cie_validation_600s_repro_v1 -ShardTag seed1 -LogId cie_validation_600s_repro_v1_seed1 -Seeds '1' -TimeLimit 600 -MemoryLimitMB 2048
```

### 6.2 Main（目标2700行）

终端A依次执行A1、A2，共900行：

```powershell
.\cie\run_cie_single.ps1 -Stage benchmark-main -CampaignId cie_main_600s_mem2048_repro_v1 -ShardTag s1to5_t1 -LogId cie_main_600s_mem2048_repro_v1_s1to5_t1 -Seeds '1,2,3,4,5' -TrainingSeeds '1' -TimeLimit 600 -MemoryLimitMB 2048 -GpuDevice cuda:0 -AcsWeightsFile cie\results\repro_manifest\selected_acs.json
```

```powershell
.\cie\run_cie_single.ps1 -Stage benchmark-main -CampaignId cie_main_600s_mem2048_repro_v1 -ShardTag s1to2_t2 -LogId cie_main_600s_mem2048_repro_v1_s1to2_t2 -Seeds '1,2' -TrainingSeeds '2' -TimeLimit 600 -MemoryLimitMB 2048 -GpuDevice cuda:0 -AcsWeightsFile cie\results\repro_manifest\selected_acs.json
```

终端B依次执行B1、B2，共900行：

```powershell
.\cie\run_cie_single.ps1 -Stage benchmark-main -CampaignId cie_main_600s_mem2048_repro_v1 -ShardTag s1to5_t3 -LogId cie_main_600s_mem2048_repro_v1_s1to5_t3 -Seeds '1,2,3,4,5' -TrainingSeeds '3' -TimeLimit 600 -MemoryLimitMB 2048 -GpuDevice cuda:0 -AcsWeightsFile cie\results\repro_manifest\selected_acs.json
```

```powershell
.\cie\run_cie_single.ps1 -Stage benchmark-main -CampaignId cie_main_600s_mem2048_repro_v1 -ShardTag s1to4_t4 -LogId cie_main_600s_mem2048_repro_v1_s1to4_t4 -Seeds '1,2,3,4' -TrainingSeeds '4' -TimeLimit 600 -MemoryLimitMB 2048 -GpuDevice cuda:0 -AcsWeightsFile cie\results\repro_manifest\selected_acs.json
```

终端C依次执行C1、C2、C3，共900行：

```powershell
.\cie\run_cie_single.ps1 -Stage benchmark-main -CampaignId cie_main_600s_mem2048_repro_v1 -ShardTag s3to5_t2 -LogId cie_main_600s_mem2048_repro_v1_s3to5_t2 -Seeds '3,4,5' -TrainingSeeds '2' -TimeLimit 600 -MemoryLimitMB 2048 -GpuDevice cuda:0 -AcsWeightsFile cie\results\repro_manifest\selected_acs.json
```

```powershell
.\cie\run_cie_single.ps1 -Stage benchmark-main -CampaignId cie_main_600s_mem2048_repro_v1 -ShardTag s5_t4 -LogId cie_main_600s_mem2048_repro_v1_s5_t4 -Seeds '5' -TrainingSeeds '4' -TimeLimit 600 -MemoryLimitMB 2048 -GpuDevice cuda:0 -AcsWeightsFile cie\results\repro_manifest\selected_acs.json
```

```powershell
.\cie\run_cie_single.ps1 -Stage benchmark-main -CampaignId cie_main_600s_mem2048_repro_v1 -ShardTag s1to5_t5 -LogId cie_main_600s_mem2048_repro_v1_s1to5_t5 -Seeds '1,2,3,4,5' -TrainingSeeds '5' -TimeLimit 600 -MemoryLimitMB 2048 -GpuDevice cuda:0 -AcsWeightsFile cie\results\repro_manifest\selected_acs.json
```

### 6.3 Stability（目标1500行）

终端A依次执行A1、A2，共540行：

```powershell
.\cie\run_cie_single.ps1 -Stage benchmark-stability -CampaignId cie_stability_600s_mem2048_repro_v1 -ShardTag s1_t1to5 -LogId cie_stability_600s_mem2048_repro_v1_s1_t1to5 -Seeds '1' -TrainingSeeds '1,2,3,4,5' -TimeLimit 600 -MemoryLimitMB 2048 -GpuDevice cuda:0
```

```powershell
.\cie\run_cie_single.ps1 -Stage benchmark-stability -CampaignId cie_stability_600s_mem2048_repro_v1 -ShardTag s4_t1to4 -LogId cie_stability_600s_mem2048_repro_v1_s4_t1to4 -Seeds '4' -TrainingSeeds '1,2,3,4' -TimeLimit 600 -MemoryLimitMB 2048 -GpuDevice cuda:0
```

终端B依次执行B1、B2，共480行：

```powershell
.\cie\run_cie_single.ps1 -Stage benchmark-stability -CampaignId cie_stability_600s_mem2048_repro_v1 -ShardTag s2_t1to5 -LogId cie_stability_600s_mem2048_repro_v1_s2_t1to5 -Seeds '2' -TrainingSeeds '1,2,3,4,5' -TimeLimit 600 -MemoryLimitMB 2048 -GpuDevice cuda:0
```

```powershell
.\cie\run_cie_single.ps1 -Stage benchmark-stability -CampaignId cie_stability_600s_mem2048_repro_v1 -ShardTag s5_t1to3 -LogId cie_stability_600s_mem2048_repro_v1_s5_t1to3 -Seeds '5' -TrainingSeeds '1,2,3' -TimeLimit 600 -MemoryLimitMB 2048 -GpuDevice cuda:0
```

终端C依次执行C1、C2、C3，共480行：

```powershell
.\cie\run_cie_single.ps1 -Stage benchmark-stability -CampaignId cie_stability_600s_mem2048_repro_v1 -ShardTag s3_t1to5 -LogId cie_stability_600s_mem2048_repro_v1_s3_t1to5 -Seeds '3' -TrainingSeeds '1,2,3,4,5' -TimeLimit 600 -MemoryLimitMB 2048 -GpuDevice cuda:0
```

```powershell
.\cie\run_cie_single.ps1 -Stage benchmark-stability -CampaignId cie_stability_600s_mem2048_repro_v1 -ShardTag s4_t5 -LogId cie_stability_600s_mem2048_repro_v1_s4_t5 -Seeds '4' -TrainingSeeds '5' -TimeLimit 600 -MemoryLimitMB 2048 -GpuDevice cuda:0
```

```powershell
.\cie\run_cie_single.ps1 -Stage benchmark-stability -CampaignId cie_stability_600s_mem2048_repro_v1 -ShardTag s5_t4to5 -LogId cie_stability_600s_mem2048_repro_v1_s5_t4to5 -Seeds '5' -TrainingSeeds '4,5' -TimeLimit 600 -MemoryLimitMB 2048 -GpuDevice cuda:0
```

### 6.4 DOE（目标300行）

```powershell
.\cie\run_cie_single.ps1 -Stage benchmark-doe -CampaignId cie_doe_600s_mem2048_repro_v1 -ShardTag seeds1to2 -LogId cie_doe_600s_mem2048_repro_v1_seeds1to2 -Seeds '1,2' -TimeLimit 600 -MemoryLimitMB 2048
```

```powershell
.\cie\run_cie_single.ps1 -Stage benchmark-doe -CampaignId cie_doe_600s_mem2048_repro_v1 -ShardTag seeds3to4 -LogId cie_doe_600s_mem2048_repro_v1_seeds3to4 -Seeds '3,4' -TimeLimit 600 -MemoryLimitMB 2048
```

```powershell
.\cie\run_cie_single.ps1 -Stage benchmark-doe -CampaignId cie_doe_600s_mem2048_repro_v1 -ShardTag seed5 -LogId cie_doe_600s_mem2048_repro_v1_seed5 -Seeds '5' -TimeLimit 600 -MemoryLimitMB 2048
```

### 6.5 SPBS（目标960行）

终端A依次执行A1、A2，共336行：

```powershell
.\cie\run_cie_single.ps1 -Stage benchmark-spbs -CampaignId cie_spbs_600s_mem2048_repro_v1 -ShardTag s1to3_both -LogId cie_spbs_600s_mem2048_repro_v1_s1to3_both -Seeds '1,2,3' -SpbsWarmStarts both -TimeLimit 600 -MemoryLimitMB 2048
```

```powershell
.\cie\run_cie_single.ps1 -Stage benchmark-spbs -CampaignId cie_spbs_600s_mem2048_repro_v1 -ShardTag s10_none -LogId cie_spbs_600s_mem2048_repro_v1_s10_none -Seeds '10' -SpbsWarmStarts none -TimeLimit 600 -MemoryLimitMB 2048
```

终端B依次执行B1、B2，共336行：

```powershell
.\cie\run_cie_single.ps1 -Stage benchmark-spbs -CampaignId cie_spbs_600s_mem2048_repro_v1 -ShardTag s4to6_both -LogId cie_spbs_600s_mem2048_repro_v1_s4to6_both -Seeds '4,5,6' -SpbsWarmStarts both -TimeLimit 600 -MemoryLimitMB 2048
```

```powershell
.\cie\run_cie_single.ps1 -Stage benchmark-spbs -CampaignId cie_spbs_600s_mem2048_repro_v1 -ShardTag s10_auto -LogId cie_spbs_600s_mem2048_repro_v1_s10_auto -Seeds '10' -SpbsWarmStarts auto -TimeLimit 600 -MemoryLimitMB 2048
```

终端C执行C1，共288行：

```powershell
.\cie\run_cie_single.ps1 -Stage benchmark-spbs -CampaignId cie_spbs_600s_mem2048_repro_v1 -ShardTag s7to9_both -LogId cie_spbs_600s_mem2048_repro_v1_s7to9_both -Seeds '7,8,9' -SpbsWarmStarts both -TimeLimit 600 -MemoryLimitMB 2048
```

### 6.6 Sensitivity（目标80行）

```powershell
.\cie\run_cie_single.ps1 -Stage benchmark-sensitivity -CampaignId cie_sensitivity_600s_mem2048_repro_v1 -ShardTag seeds1to4 -LogId cie_sensitivity_600s_mem2048_repro_v1_seeds1to4 -Seeds '1,2,3,4' -TimeLimit 600 -MemoryLimitMB 2048
```

```powershell
.\cie\run_cie_single.ps1 -Stage benchmark-sensitivity -CampaignId cie_sensitivity_600s_mem2048_repro_v1 -ShardTag seeds5to7 -LogId cie_sensitivity_600s_mem2048_repro_v1_seeds5to7 -Seeds '5,6,7' -TimeLimit 600 -MemoryLimitMB 2048
```

```powershell
.\cie\run_cie_single.ps1 -Stage benchmark-sensitivity -CampaignId cie_sensitivity_600s_mem2048_repro_v1 -ShardTag seeds8to10 -LogId cie_sensitivity_600s_mem2048_repro_v1_seeds8to10 -Seeds '8,9,10' -TimeLimit 600 -MemoryLimitMB 2048
```

### 6.7 OOD（目标729行）

```powershell
.\cie\run_cie_single.ps1 -Stage benchmark-ood -CampaignId cie_ood_1200s_mem4096_repro_v1 -ShardTag seed1 -LogId cie_ood_1200s_mem4096_repro_v1_seed1 -Seeds '1' -TrainingSeeds '1,2,3,4,5' -TimeLimit 1200 -MemoryLimitMB 4096 -GpuDevice cuda:0 -AcsWeightsFile cie\results\repro_manifest\selected_acs.json
```

```powershell
.\cie\run_cie_single.ps1 -Stage benchmark-ood -CampaignId cie_ood_1200s_mem4096_repro_v1 -ShardTag seed2 -LogId cie_ood_1200s_mem4096_repro_v1_seed2 -Seeds '2' -TrainingSeeds '1,2,3,4,5' -TimeLimit 1200 -MemoryLimitMB 4096 -GpuDevice cuda:0 -AcsWeightsFile cie\results\repro_manifest\selected_acs.json
```

```powershell
.\cie\run_cie_single.ps1 -Stage benchmark-ood -CampaignId cie_ood_1200s_mem4096_repro_v1 -ShardTag seed3 -LogId cie_ood_1200s_mem4096_repro_v1_seed3 -Seeds '3' -TrainingSeeds '1,2,3,4,5' -TimeLimit 1200 -MemoryLimitMB 4096 -GpuDevice cuda:0 -AcsWeightsFile cie\results\repro_manifest\selected_acs.json
```

## 7. 合并、验解和统计

每个正式campaign完成后运行一次对应命令。run_cie_postprocess.ps1 按失败即停止的顺序完成：递归合并、SCIP独立验解、精确矩阵/主键/错误/solution审计、制造实例优先聚合、bootstrap 95%区间、配对效应量、双侧Wilcoxon与全局Holm。DOE另外输出预设主效应、两两交互、OLS置信区间、诊断数据和两张程序生成的非AI图。

```powershell
.\cie\run_cie_postprocess.ps1 -Stage validation -CampaignId cie_validation_600s_repro_v1
```

```powershell
.\cie\run_cie_postprocess.ps1 -Stage main -CampaignId cie_main_600s_mem2048_repro_v1
```

```powershell
.\cie\run_cie_postprocess.ps1 -Stage stability -CampaignId cie_stability_600s_mem2048_repro_v1
```

```powershell
.\cie\run_cie_postprocess.ps1 -Stage doe -CampaignId cie_doe_600s_mem2048_repro_v1
```

```powershell
.\cie\run_cie_postprocess.ps1 -Stage spbs -CampaignId cie_spbs_600s_mem2048_repro_v1
```

```powershell
.\cie\run_cie_postprocess.ps1 -Stage sensitivity -CampaignId cie_sensitivity_600s_mem2048_repro_v1
```

```powershell
.\cie\run_cie_postprocess.ps1 -Stage ood -CampaignId cie_ood_1200s_mem4096_repro_v1
```

正式DOE不得使用 `-NoPlots`；若缺少matplotlib或图未生成，后处理会失败，必须在正式冻结前安装更新后的 `requirements.txt`。固定reference依次为 `scip_default`、`proposed`、`proposed[full]`、`scip_default[manufacturing_doe]`、`scip_default[spbs_auto]`、`scip_default`、`proposed`。机器可读结果在各campaign的 `analysis/` 和 `submission_analysis/`；至少保存 `submission_audit.json`、`cie_submission_analysis.json` 和CSV产物，终端审计必须显示 `PASS`。

验收必须同时满足：精确行数4/2700/1500/300/960/80/729；无重复键；`error`和`solution_write_error`为空；timeout、memlimit和无incumbent行保留；每个incumbent有唯一 `.sol`；所有制造分析 `invalid_count=0`；统计先在制造实例内聚合training/solver重复，再做双侧配对检验和Holm校正。DOE还必须输出主效应、预设交互、置信区间和诊断图。

上述工具不会虚构当前runner尚未采集的机制遥测。若保留cut-pool、角色覆盖、冗余、callback/fallback开销或root-bound声明，必须在第3节所述冻结前补字段、测试和对应机制分析；否则从论文中删除这些不可验证声明。

## 8. 论文和Editorial Manager投稿包

现有英文稿使用官方 `elsarticle` class，基础模板正确，但尚不是可上传包。当前还有27个 `TBD`、6张未完成表、0张图，本机也未安装LaTeX工具链。

最终按“官方要求 + 本项目论文完整性门槛”准备：

- 匿名正文 `manuscript_anonymous.tex/pdf`：无作者、单位、致谢、基金号、身份化仓库链接或文件元数据。
- 单独title page：题名、与Editorial Manager顺序一致的所有作者、每个单位的完整标准名称/邮寄地址/国家、致谢、利益冲突、通信作者邮寄地址、邮箱和电话。
- 可编辑 `highlights.txt`：3--5条，每条含空格不超过85字符；当前5条长度合规，最终应替换为有证据的结果。
- Elsevier declarations tool生成的利益冲突 `.doc/.docx`；无冲突也必须提交声明。
- CRediT、Funding、Data statement和数据/代码链接：匿名评审稿删除或匿名化逐作者CRediT、完整基金号和身份化链接；完整作者贡献与Funding放在不发审稿人的title-page/author-details文件或Editorial Manager字段，接受后的最终稿恢复。初投使用匿名评审链接；最终归档使用永久标识符（优先DOI）。若数据不能共享，Data statement必须说明原因。
- 生成式AI声明：本稿使用过Codex/ChatGPT辅助，必须在参考文献前披露工具、用途、人工复核和作者责任。不得用生成式AI制作或修改投稿图片或graphical abstract。
- 投稿型supplement：完整模型、算法和超参数、实例生成、全部结果与失败行、统计细节、环境与复现清单。它是本项目因正文承诺补充材料而设的内部必需项，不是C&IE对所有论文的通用硬性项。
- LaTeX平铺源包：tex、bib/bbl、必要bst/sty和图片处于同一目录；PDF不是源文件。每幅图按正文顺序单独保存为 `Figure_*.pdf/png/tiff`，另备可编辑 `figure_captions.txt`。
- APA 7参考文献、术语表、图表交叉引用、拼写检查、版权许可、作者一致批准和非一稿多投确认。
- Cover letter建议准备，但当前公开Guide未把它列为通用硬性项；以正式上传当天Editorial Manager字段为准。

官方数值门槛：摘要不超过250个英文词；关键词1--7个；highlights 3--5条且每条不超过85字符。摘要还应独立、事实性地给出目的、主要结果和结论，不含参考文献，非常用缩写首次定义；关键词必须为英文，避免含 `and/of` 的冗长短语，仅使用公认缩写。Graphical abstract为鼓励项而非硬性项。投稿当天以官方Guide为准。

方法命名必须统一：仓库 `RDMCT-A3C` 与稿件 `SA-RLCS` 要么统一名称，要么在摘要、方法、代码和数据元数据中明确二者关系。

## 9. 剩余时间估算

| 工作 | 三并发或单路现实估算 | 硬上限/保守估算 |
| --- | ---: | ---: |
| 当前旧OOD收尾 | 7小时 | 7小时 |
| 机制遥测、checkpoint规则与冻结 | 1--3天 | 若保留未实现的机制声明则可能更长 |
| 15模型训练（单GPU） | 30--45小时 | 约2--3天 |
| ACS + warm start | 约6--18小时 | ACS单路60小时 + warm start约6小时 |
| 6273行benchmark（下述均衡三终端队列） | 约208--220小时 | 约403小时 |
| 验解、统计、图表、论文与投稿包 | 4--7天 | 若返工则更长 |

若机器24小时连续运行，现实乐观约2.5--3.5周；每天只运行约12小时，约4--5周；按所有求解触顶、ACS触顶并预留返工，保守约5--8周。这里的403小时是当前Stage接口下的均衡固定队列硬上限，不是完全动态调度的理论下界。若机制遥测或选模规则尚未定稿，先完成它们再开始正式计时；任何正式运行后的代码/协议修改都会使该估算重新开始。

## 10. “可以投稿”的最终定义

- [ ] 所有机制指标和checkpoint选择规则在运行前冻结。
- [ ] 工作区对应一个可复现commit，环境、LP、模型、ACS均有hash。
- [ ] 15个模型provenance通过默认门禁，正式命令没有 `-AllowLegacyCheckpoints`。
- [ ] 6273行完整、无重复、错误处理和censoring规则可审计。
- [ ] 全部incumbent独立验解通过，`invalid_count=0`。
- [ ] 实例级统计、DOE、机制分析、OOD和失败分析全部完成。
- [ ] 英文稿没有 `TBD` 或无来源的 `--`，每个数字可追溯到冻结分析产物。
- [ ] 双匿名稿、title page、highlights、利益冲突、AI声明、CRediT、Funding、Data statement和LaTeX源包齐全；本项目内部要求的supplement齐全，cover letter按Editorial Manager字段准备。
- [ ] 摘要、关键词、highlights、APA 7、术语表和匿名化检查通过。

满足这些门槛表示“材料达到可投稿状态”，不代表期刊必然录用。

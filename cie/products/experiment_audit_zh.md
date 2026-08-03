# C&IE 实验完成度与续跑审计

> **当前结论更新于2026-08-02。** 本文下半部保留的2026-07-28命令仅为故障历史，严禁再次执行。当前正式顺序和单行命令只以[`../docs/cie_submission_runbook_zh.md`](../docs/cie_submission_runbook_zh.md)为准，协议定义以[`../README.md`](../README.md)为准。

## 2026-08-02 当前快照

- 旧`cie_ood_1200s_mem4096_final_v1`已完成729/729，三分片各243条，无重复、无runner/solution-write error，但729条全部`timelimit`。SCIP与ACS各27/27有incumbent；每个学习方法族只有27/135，且旧training seeds 2--5均无incumbent。
- 旧15个checkpoint的`experiment.seed`均为1，且活动跨代码修改；旧OOD只能作为工程诊断，不能进正式性能表。`timelimit`本身并非无效，排除根因是checkpoint provenance。
- 旧Main为880/2700且claim-ready门禁未通过；旧SPBS只有none组336条并含一条SCIP phase error；它们均不能通过挑选有利行支持算法优势。
- 正式冻结准备已建立：commit`08f3d5959ca49dc836c0ad9d3b957bdbed7ab181`、运行前clean记录、90个LP hash，数据生成81/81成功。
- 新HEM、feature-only与Proposed检查点均为5/5，共15/15；冻结清单已逐项记录路径、checkpoint/variant hash和三处seed，runner已强制消费。ACS validation 720/720已完成并冻结。core 48、sensitivity 8和OOD 9个warm starts均完成；OOD最终9/9、failures=0，最后一个修复解已在当前完整LP上独立验解通过。正式benchmark当前为0/6273。
- 2026-08-02续跑协议已补强：新训练检查点保存完整训练状态并按epoch恢复；ACS逐求解写入带资产签名的JSONL；benchmark沿用逐评估JSONL；warm start按LP哈希复用。统一通过`run_cie_single.ps1`中断和原命令恢复，最多重做当前未提交的原子单元。
- 四个归档零gap单例及一个四方法旧单例只作为“非验证性模型健全性检查”写入初稿；完整归档状态清单仍需生成，不能只引用89秒的有利行。

model-evidence已完成81/81个LP，模型规模raw/summary/manifest均已生成，CIE相关测试59/59通过。最终评估代码与可移植15模型manifest已提交并推送；Validation 4/4、独立验解和投稿审计PASS。benchmark前门槛已全部通过，当前下一步是按执行手册第6.2节启动Main三队列。

---

## 以下为2026-07-28故障历史（命令已禁用）

审计时间：2026-07-28（Asia/Shanghai）。以下内容不代表当前完成度，也不作为论文最终结果表。

## 1. 当前结论

现有结果仍不足以支持C&IE最终性能结论。论文中的PDI、gap、时间、节点数、最优率和显著性表应继续留空。原因是主实验只有880/2700行，统一4096 MB的OOD活动只有63/729行，SPBS只有336/960行，DOE和敏感性尚未产生正式结果。

新增且可确认的结果只有一项工程预检：OOD solver seed 3、training seed 1在4096 MB上完成63行，错误数为0。它只能说明当前内存配置通过该分片，不能用于估计方法性能。

## 2. 完成度

| 实验 | 冻结目标 | 当前可用结果 | 明确缺口 | 最终表是否可填 |
|---|---:|---:|---:|---|
| Main | 2700行 | 880行 | 1820行 | 否 |
| OOD 4096 MB | 729行 | 63行、0错误 | 666行，正在运行 | 否 |
| SPBS | 960行 | 336行，含1个非内存错误 | 624行及1个错误替换 | 否 |
| DOE | 300行 | 0行 | 300行 | 否 |
| Sensitivity | 80行 | 0行 | 80行 | 否 |
| Validation sanity | 4行 | 0行 | 4行 | 非主表，但应完成 |

Main的880行由solver seed 3完整540行和solver seed 1的training seeds 1--3共340行组成。缺少solver seed 1的training seeds 4--5共200行，以及solver seeds 2、4、5各540行。

旧2048 MB OOD数据不得与新活动合并：solver seed 2有243行且无错误；solver seed 3有243行但含39个错误；solver seed 1没有raw CSV。它们只用于故障分析。

SPBS已有spbs_none seeds 1--7共336行，其中seed 3、实例cie_core_n032_f024_m008_proc090出现一次“SCIP method cannot be called at this time in solution process”错误；这不是内存错误，需要单独复跑并在最终合并时只替换该行。

## 3. 当前正在运行的三路OOD

三路均于2026-07-27 18:54启动，SCIP内存上限为每进程4096 MB，时间上限1200秒：

1. solver seed 1，training seeds 1--5，目标243行。
2. solver seed 2，training seeds 1--5，目标243行。
3. solver seed 3，续跑training seeds 2--5，目标180行；与已完成的training seed 1合并后为243行。

启动前三路需要的保守内存预算为3×4096+4096=16384 MB；启动前可用物理内存约23 GB，启动后约19.4 GB，可用虚拟内存约34.4 GB。核验时三个run_cie_benchmarks.py进程均已进入第一个实例，错误日志为空。当前运行期间不得再启动第四个正式实验。

对应日志目录：

- cie/results/logs/cie_ood_1200s_mem4096_final_v1_seed1
- cie/results/logs/cie_ood_1200s_mem4096_final_v1_seed2
- cie/results/logs/cie_ood_1200s_mem4096_final_v1_seed3_resume

若任务被外部终止，以下为精确续跑命令；当前进程存活时不要重复执行。2026-07-28起runner默认逐项写入 `runs/.checkpoints/*.jsonl`，所以第二天应原样重跑同一命令，不能更改campaign、分片、seeds、training seeds、时间/内存上限、数据或模型。已成功完成的单项会显示 `resumed` 并跳过，异常项及中断瞬间的活动项会重试。

    Set-Location D:\git\git\RDMCT-A3C; $env:CUDA_MODULE_LOADING='LAZY'; $env:RDMCT_COMPACT_TEXT_LOG='1'; $env:RDMCT_TEXT_LOG_MAX_MB='2'; $env:RDMCT_TEXT_LOG_BACKUP_COUNT='1'; .\cie\run_cie_single.ps1 -Stage benchmark-ood -CampaignId cie_ood_1200s_mem4096_final_v1 -ShardTag seed1 -LogId cie_ood_1200s_mem4096_final_v1_seed1 -Seeds '1' -TrainingSeeds '2,3,4,5' -TimeLimit 1200 -MemoryLimitMB 4096 -GpuDevice cuda:0

    Set-Location D:\git\git\RDMCT-A3C; $env:CUDA_MODULE_LOADING='LAZY'; $env:RDMCT_COMPACT_TEXT_LOG='1'; $env:RDMCT_TEXT_LOG_MAX_MB='2'; $env:RDMCT_TEXT_LOG_BACKUP_COUNT='1'; .\cie\run_cie_single.ps1 -Stage benchmark-ood -CampaignId cie_ood_1200s_mem4096_final_v1 -ShardTag seed2 -LogId cie_ood_1200s_mem4096_final_v1_seed2 -Seeds '2' -TrainingSeeds '2,3,4,5' -TimeLimit 1200 -MemoryLimitMB 4096 -GpuDevice cuda:0

    Set-Location D:\git\git\RDMCT-A3C; $env:CUDA_MODULE_LOADING='LAZY'; $env:RDMCT_COMPACT_TEXT_LOG='1'; $env:RDMCT_TEXT_LOG_MAX_MB='2'; $env:RDMCT_TEXT_LOG_BACKUP_COUNT='1'; .\cie\run_cie_single.ps1 -Stage benchmark-ood -CampaignId cie_ood_1200s_mem4096_final_v1 -ShardTag shardB -LogId cie_ood_1200s_mem4096_final_v1_seed3_resume -Seeds '3' -TrainingSeeds '2,3,4,5' -TimeLimit 1200 -MemoryLimitMB 4096 -GpuDevice cuda:0

## 4. 防止内存不足和白跑的改动

1. 单任务包装器默认内存从2048 MB提高到4096 MB；主实验等需要延续旧2048 MB协议的活动必须显式写出2048。
2. 新增TrainingSeeds参数，可从指定训练种子继续，不重复固定基线。
3. 新增SpbsWarmStarts参数，可只跑none、auto或两者，避免重复336项SPBS。
4. 进度读取使用FileShare.ReadWrite，不再因日志正在写入而长期显示0%。
5. raw CSV在显著性分析前写盘；SciPy导入若遇到MemoryError，只跳过显著性分析。
6. 紧凑日志关闭每次割选择的计数和推理计时；内部文本日志限制为2 MB并保留1个备份。
7. runner默认在每个“实例×方法×solver seed”成功后执行flush和fsync；完整批次写完成标记。每天可用 `Ctrl+C` 停止，最多损失一个正在运行的单项。错误项不会写成完成，避免把失败结果永久跳过。

日志文件主要消耗磁盘而不是物理内存，但减少高频输出可以降低管道缓冲、格式化和磁盘I/O。机器可读raw、summary、JSON、解文件、进度行及错误日志必须保留。

注意：此前中断的seed 1/seed 2日志停在15/63，但当时版本只在整批结束时写raw，因而这15项没有完整机器可读指标，无法从紧凑日志可靠恢复，必须一次性重算。补丁后的首次启动开始逐项保留，此后不再发生整批白跑。不要删除campaign中的 `.checkpoints` 目录。

## 5. OOD完成后的实验顺序、目的和命令

所有阶段最多同时三个run_cie_benchmarks.py进程。启动三路4096 MB任务前，要求可用物理内存和虚拟内存均不低于16384 MB；三路2048 MB任务要求均不低于10240 MB。低于阈值时不要强制启动。

### 5.1 Main主比较

目的：在20个标称实例上比较SCIP、ACS、HEM、HEM+beam、23D feature-only、structure+greedy和Proposed；隔离角色特征、结构补全与束搜索贡献。继续沿用旧活动的600秒和2048 MB，不能与4096 MB主实验混合。

第一波最多三路：

    .\cie\run_cie_single.ps1 -Stage benchmark-main -CampaignId cie_main_600s_compact_final_v1 -ShardTag seed1 -LogId cie_main_600s_compact_final_v1_seed1_resume -Seeds '1' -TrainingSeeds '4,5' -TimeLimit 600 -MemoryLimitMB 2048 -GpuDevice cuda:0

    .\cie\run_cie_single.ps1 -Stage benchmark-main -CampaignId cie_main_600s_compact_final_v1 -ShardTag seed2 -LogId cie_main_600s_compact_final_v1_seed2 -Seeds '2' -TrainingSeeds '1,2,3,4,5' -TimeLimit 600 -MemoryLimitMB 2048 -GpuDevice cuda:0

    .\cie\run_cie_single.ps1 -Stage benchmark-main -CampaignId cie_main_600s_compact_final_v1 -ShardTag seed4 -LogId cie_main_600s_compact_final_v1_seed4 -Seeds '4' -TrainingSeeds '1,2,3,4,5' -TimeLimit 600 -MemoryLimitMB 2048 -GpuDevice cuda:0

任一路结束后再启动seed 5：

    .\cie\run_cie_single.ps1 -Stage benchmark-main -CampaignId cie_main_600s_compact_final_v1 -ShardTag seed5 -LogId cie_main_600s_compact_final_v1_seed5 -Seeds '5' -TrainingSeeds '1,2,3,4,5' -TimeLimit 600 -MemoryLimitMB 2048 -GpuDevice cuda:0

### 5.2 DOE制造因素实验

目的：估计晶圆数、配方比例和加工时间系数对吞吐率、周期时间、资源利用率、PEC占用和清洗开销的主效应及预设交互。

    .\cie\run_cie_single.ps1 -Stage benchmark-doe -CampaignId cie_doe_600s_compact_final_v1 -ShardTag seeds1to2 -LogId cie_doe_600s_compact_final_v1_seeds1to2 -Seeds '1,2' -TimeLimit 600 -MemoryLimitMB 2048

    .\cie\run_cie_single.ps1 -Stage benchmark-doe -CampaignId cie_doe_600s_compact_final_v1 -ShardTag seeds3to4 -LogId cie_doe_600s_compact_final_v1_seeds3to4 -Seeds '3,4' -TimeLimit 600 -MemoryLimitMB 2048

    .\cie\run_cie_single.ps1 -Stage benchmark-doe -CampaignId cie_doe_600s_compact_final_v1 -ShardTag seed5 -LogId cie_doe_600s_compact_final_v1_seed5 -Seeds '5' -TimeLimit 600 -MemoryLimitMB 2048

### 5.3 SPBS初解组件实验

目的：固定SCIP设置，只比较无初解与自动SPBS初解，衡量对incumbent rate、PDI、gap和求解时间的作用。

    .\cie\run_cie_single.ps1 -Stage benchmark-spbs -CampaignId cie_spbs_600s_compact_final_v1 -ShardTag auto_seeds1to4 -LogId cie_spbs_600s_compact_final_v1_auto_seeds1to4 -Seeds '1,2,3,4' -SpbsWarmStarts auto -TimeLimit 600 -MemoryLimitMB 2048

    .\cie\run_cie_single.ps1 -Stage benchmark-spbs -CampaignId cie_spbs_600s_compact_final_v1 -ShardTag auto_seeds5to7 -LogId cie_spbs_600s_compact_final_v1_auto_seeds5to7 -Seeds '5,6,7' -SpbsWarmStarts auto -TimeLimit 600 -MemoryLimitMB 2048

    .\cie\run_cie_single.ps1 -Stage benchmark-spbs -CampaignId cie_spbs_600s_compact_final_v1 -ShardTag both_seeds8to10 -LogId cie_spbs_600s_compact_final_v1_both_seeds8to10 -Seeds '8,9,10' -SpbsWarmStarts both -TimeLimit 600 -MemoryLimitMB 2048

补齐后单独复跑seed 3的none组并只替换错误实例，不覆盖其余47个原始观测：

    .\cie\run_cie_single.ps1 -Stage benchmark-spbs -CampaignId cie_spbs_600s_compact_final_v1 -ShardTag retry_seed3_none -LogId cie_spbs_600s_compact_final_v1_retry_seed3_none -Seeds '3' -SpbsWarmStarts none -TimeLimit 600 -MemoryLimitMB 2048

### 5.4 参数敏感性

目的：检验运动时间、加工时间、PEC容量和清洗间隔变化下结论是否稳定。

    .\cie\run_cie_single.ps1 -Stage benchmark-sensitivity -CampaignId cie_sensitivity_600s_compact_final_v1 -ShardTag seeds1to4 -LogId cie_sensitivity_600s_compact_final_v1_seeds1to4 -Seeds '1,2,3,4' -TimeLimit 600 -MemoryLimitMB 2048

    .\cie\run_cie_single.ps1 -Stage benchmark-sensitivity -CampaignId cie_sensitivity_600s_compact_final_v1 -ShardTag seeds5to7 -LogId cie_sensitivity_600s_compact_final_v1_seeds5to7 -Seeds '5,6,7' -TimeLimit 600 -MemoryLimitMB 2048

    .\cie\run_cie_single.ps1 -Stage benchmark-sensitivity -CampaignId cie_sensitivity_600s_compact_final_v1 -ShardTag seeds8to10 -LogId cie_sensitivity_600s_compact_final_v1_seeds8to10 -Seeds '8,9,10' -TimeLimit 600 -MemoryLimitMB 2048

### 5.5 Validation sanity

目的：在四个冻结小实例上验证基础SCIP链路、解文件和可行性检查，不用于测试集调参。

    .\cie\run_cie_single.ps1 -Stage benchmark-validation -CampaignId cie_validation_600s_final_v1 -ShardTag seed1 -LogId cie_validation_600s_final_v1_seed1 -Seeds '1' -TimeLimit 600 -MemoryLimitMB 2048

## 6. 最终接收标准

1. 行数达到2700、729、960、300和80，且种子/方法/训练种子覆盖与冻结设计一致。
2. 所有错误和超时保留；工程错误单独复跑并记录替换规则。
3. 不混合不同时间上限、内存上限、模型检查点或候选预算。
4. 解文件重新载入SCIP验证，invalid_count必须为0。
5. 按制造实例配对，Wilcoxon检验和Holm校正以实例为统计单元。
6. 只有满足以上条件后，才把数值写入中英文论文结果表。

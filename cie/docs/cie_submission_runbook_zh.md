# Computers & Industrial Engineering 投稿执行手册

> 审计时间：2026-08-17 14:58:02（Asia/Shanghai）。本文记录已闭合的投稿证据、复现入口和上传前作者事项。实验协议定义仍以 [`../README.md`](../README.md) 为准。本文中的 PowerShell 命令均为单行命令，不使用续行符。

官方依据：[C&IE Guide for Authors](https://www.sciencedirect.com/journal/computers-and-industrial-engineering/publish/guide-for-authors)；[Elsevier LaTeX instructions](https://www.elsevier.com/en-gb/researcher/author/policies-and-guidelines/latex-instructions)。投稿要求可能变化，正式上传当天再次核对。

## 1. 当前证据状态与论文主张边界

### 1.1 旧 OOD 已完成，但只属于工程诊断

`cie_ood_1200s_mem4096_final_v1` 已于2026-08-02完成729/729条唯一记录（三个solver-seed分片各243条），无重复键、无runner error、无solution-write error。729条全部为`timelimit`。SCIP与ACS各自27/27条产生incumbent；每个学习方法族只有27/135条产生incumbent，且只有旧training seed 1有效。15个旧`variant.json`均记录`experiment.seed=1`，代码还跨批次修改。因此，该活动只能说明运行器、内存设置和大实例困难度，不能进入正式主表或OOD性能表，也不能通过挑选其中效果好的行证明算法优势。

`timelimit`不等于“结果无效”，而是共同预算到期时尚未完成证明；有incumbent的行仍可用于PDI、最终gap、上下界、首次可行解和incumbent rate分析。由于旧活动的检查点来源不合格，它被排除的根因是provenance，而不是`timelimit`本身。

### 1.2 投稿级路线的当前状态

正式`*_repro_v1`活动中，Main 2700/2700、Stability 1500/1500和DOE 300/300均已完成，并于2026-08-12重新执行独立SCIP验解、精确矩阵审计和正式统计，三阶段的`submission_audit.json`均为`PASS`。Main原有7条边界失败已确认来自`.sol`文本序列化：连续残差只比SCIP默认$10^{-6}$容差高$1.11\times10^{-13}$。验解器现保留SCIP容差并只增加$10^{-12}$绝对序列化裕量；该策略有单元测试，2700/2700个保存解现全部通过，并未删除或挑选任何行。Stability的物理路径总等待、最大等待、节拍CV和节拍偏差均由保存解的事件时间独立重构，并按`solution_file`与正式结果严格1:1联接；完整性联接和后处理审计均已`PASS`，无需重跑求解器。DOE已生成预设主效应、交互、置信区间及两张程序图。

截至2026-08-17 14:58:02，SPBS已完成960/960，Sensitivity已完成80/80，正式OOD已完成729/729；三阶段均通过独立验解、精确矩阵审计和正式统计。OOD的729行全部为`timelimit`，但每行均有经独立验解的有效incumbent，runner error和solution-write error均为0，`invalid_count=0`，投稿审计`PASS`。其warm starts 9/9通过完整验解和LP哈希核对。旧`cie/models/<family>/seed_N`目录、旧Main、旧OOD、旧SPBS和smoke不得并入新campaign；正式复现命令禁止使用`-AllowLegacyCheckpoints`。

正式训练输出位于带时间戳的递归目录，而不是固定的`cie/models/<family>/seed_N`。必须按`variant.json`中的parser seed、SCIP seed、experiment seed和训练数据路径递归解析，并强制存在`itr_60.pkl`；不能把中断训练的`params.pkl`当作epoch 60正式模型。第5节给出门禁。

### 1.3 两篇直接参考文献限定的创新边界

- Gu等（2024）《Scheduling of Multi-finger-robotic Cluster Tools with Multi-space Process Modules》研究四指机械手、四空间工艺模块、单产品稳态运行，并在预先固定的BS/HTS序列下分别建立以周期时间为目标的LP；腔室清洗和多晶圆类型同时处理留作未来研究。本文可主张的是有限时域产品晶圆/真空区假片双源混流、混合$4\times1$/$2\times2$模式、旋转腔室、清洗、真空区假片循环、灵活分配/排序的精确MIP，以及保持incumbent最大完工时间的条件式第二阶段。两个模型不等价，不能直接比较原始运行时间。
- Wang等（2023）《Learning Cut Selection for Mixed-Integer Linear Programming via Hierarchical Sequence Model》已经包含13维通用割特征、层次选择数量、有序指针子集和与A3C密切相关的并行策略梯度。本文不能把这些元素再次作为创新。可检验的新组合是SPBS原始热启动、HEM式策略、有限宽束搜索、变量类型/角色特征与次模补全及SCIP的集成，并必须逐组件消融。
- 当前正式训练配置使用移动平均REINFORCE基线，不是学习评论家的严格A3C。稿件保留`RDMCT-A3C`作为项目名，但算法正文称“并行层次策略梯度”。若要把严格A3C作为算法创新，必须另行实现、冻结并与HEM式策略梯度配对比较。
- RL-SAT当前只证明候选专用CP-SAT抽象，不证明完整Petri MIP或全部腔室分配的全局最优，故不进入主比较。

## 2. 中断、恢复与TimeLimit规则

旧OOD已经完成，无需再运行任何`cie_ood_1200s_mem4096_final_v1`恢复命令。此后所有耗时命令都必须通过`run_cie_single.ps1`启动。按一次`Ctrl+C`并等待返回PowerShell提示符；启动器会终止且只终止该命令的PowerShell/Python子进程树，已原子保存的工作不会丢失。不要直接关闭窗口或强制关机；若发生异常断电，恢复规则相同，但当前尚未提交的最小原子单元需要重做。

| 阶段 | 恢复粒度 | 中断后的操作 | 不会重复的内容 |
| --- | --- | --- | --- |
| `train-*` | 完成的epoch | 原样重跑同一family、同一seed命令 | 新格式`params.pkl`之前的全部完整epoch；epoch 60完成后整条跳过 |
| `tune-acs` | 单次实例×seed×权重求解 | 原样重跑同一命令 | `.checkpoints/acs_grid_<signature>.jsonl`中的全部完成求解 |
| `warmstarts-*` | 单个实例的兼容SPBS文件 | 原样重跑同一profile命令 | LP哈希一致且元数据完整的`.sol`/`.meta.json` |
| `benchmark-*` | 单个实例×方法×solver seed×training seed | 原样重跑同一命令 | 对应campaign分片`.checkpoints/*.jsonl`中的无错误完成行 |
| `generate-*` | 无跨文件checkpoint | 原样重跑；生成器按确定性文件名重建 | 该阶段较短；不要在生成期间启动benchmark |
| 后处理 | 整个分析步骤 | 原样重跑 | 原始结果不变，分析文件以确定性方式重建 |

恢复时必须保持Stage、CampaignId、ShardTag、Seeds、TrainingSeeds、时间/内存上限、warm-start模式、数据、训练配置、代码、模型和ACS文件不变。benchmark和ACS的签名会拒绝或隔离参数/资产变化；训练续跑还会核对训练代码、配置、训练LP、family和三处seed。不得删除或编辑`.checkpoints`、`params.pkl`、`variant.json`，也不得把较早`itr_*.pkl`手工改名。运行benchmark前仍须确认15个正式模型均为`itr_60.pkl`。

### 2.1 已完成的旧中断恢复记录

2026-08-08 Stability中断的最后可观测终端输出为00:16:43.335（中国标准时间），当时原子进度885/1500。原样恢复后，该阶段于2026-08-11 08:42:46完成1500/1500，2026-08-12通过独立验解与投稿审计，因此不再执行旧恢复命令。正式OOD的三个分片也已完成并审计，不再存在需要恢复的正式benchmark进程；第6节命令仅作为从零复现入口保留。

## 3. 投稿证据矩阵（已闭合）

| 项目 | 投稿目标 | 当前正式有效 | 目的 |
| --- | ---: | ---: | --- |
| 冻结清单与数据 | 1套 | 已建立 | 运行前commit、环境和90个LP hash；数据生成81/81成功 |
| 可审计模型 | 15 | 15 | HEM、feature-only、Proposed各5/5，全部epoch 60 |
| 选定检查点清单 | 1 | 已完成 | 15/15路径、variant/hash和三处seed已冻结，runner强制消费 |
| ACS validation网格 | 720 solves | 720 | 调参完整并已冻结`selected_acs.json`及hash |
| Warm starts | 65 | 已完成 | core 48、sensitivity 8、OOD 9均通过；OOD报告 failures=0 |
| Validation | 4行 | 4 | 4/4均有incumbent，独立验解、精确矩阵和投稿审计全部PASS |
| 建模证据 | 1套 | 已完成 | compact测试通过；81/81个LP的变量、约束、文件大小和解析时间表已生成 |
| Main | 2700行 | 2700，审计PASS | 七方法公平比较；PDI与时间均值第一，全部保存解独立验解通过 |
| Stability | 1500行 | 1500，独立验解与审计PASS | 完整/关闭二阶段/替代目标控制实验；物理等待与节拍由事件时间独立重构并严格联接 |
| DOE | 300行 | 300，审计PASS | 60单元析因、主效应/交互/诊断图已完成 |
| SPBS | 960行 | 960，独立验解与审计PASS | auto warm start与none组件对比；PDI与incumbent率主效应显著 |
| 学习策略×SPBS交互 | 可选 | 0 | 仅在正文主张SPBS与学习策略存在协同/交互时必做 |
| Sensitivity | 80行 | 80，独立验解与审计PASS | 工艺、搬运、清洗和真空区假片库存OFAT |
| OOD | 729行 | 729，独立验解与审计PASS | 大规模分布外可行性与性能边界 |

核心矩阵（不含Validation）已完成6269/6269行；加Validation为6273/6273。七阶段投稿审计均为`PASS`，共6041个incumbent全部通过独立验解，`invalid_count=0`。Main中Proposed平均PDI为16585.70，低于HEM的16823.18和SCIP的16919.01，平均求解时间218.32~s亦为七方法最低；相对HEM和SCIP的区间跨零且Holm校正$p=1.0$，因此只主张标称矩阵中的最低观测均值，不声称总体显著领先。Stability中，相对stage2_off，完整配置使物理路径总等待、最大等待、节拍CV和节拍偏差和分别降低51.91\%、68.89\%、39.70\%和94.05\%，四项Holm校正后均显著。SPBS自动初始解相对none使incumbent率由51.67\%提高至100\%，PDI降低26.19\%，Holm $p$分别为$2.55\times10^{-5}$和$3.46\times10^{-8}$。Sensitivity 80/80均有有效incumbent，但仅为单方法OFAT。OOD 729/729均在1200~s触顶但均有有效incumbent；ACS取得最低平均OOD PDI，所有全局Holm校正方法差异均不显著，故OOD只支持分布外可行性，不支持RDMCT-HBS领先主张。当前主张范围内无需继续运行benchmark。

最终证据解释与归档边界如下：

1. 正式runner没有完整采集cut count、dual bound、root gap、LP iterations、首次/最佳解/证明时间，因此稿件不得新增依赖这些未采集遥测的机制性量化主张；否则必须另行冻结协议并重跑受影响矩阵。
2. checkpoint门禁已经实现并冻结15/15；最终源包应保留清单、路径/hash、variant hash和三处seed的追溯记录。
3. 当前`benchmark-main`让全部方法统一使用auto warm start，`benchmark-spbs`比较SCIP的none/auto。因此核心矩阵能分别估计“学习方法在共同初解条件下的差异”和“SPBS对SCIP的主效应”，不能估计二者的交互。最短路线删除协同声明；若保留协同声明，再补A2交互实验。
4. `model-evidence` Stage现已覆盖compact模型单元验证与变量/约束/LP大小/解析时间规模表。Gu（2024）的固定BS/HTS稳态LP与本文有限时域双源混流两阶段MIP并不等价，不能作为等价性硬门槛；正文应做逐项建模差异表。独立incumbent验解由validation和正式后处理完成。
5. 当前训练命令固定`baseline_type=simple`，没有严格演员--评论家A3C对照。默认做法是把算法准确命名为“并行层次策略梯度”；只有在增加严格A3C实现及公平配对实验后，才把A3C训练本身写成创新。RL-SAT不用于替代该缺口。

### 3.1 两项创新所需实验、目的和当前命令状态

| 编号 | 实验 | 目的 | 当前可执行入口 |
| --- | --- | --- | --- |
| M1 | compact小例单元等价 | 验证$4\times1$、$2\times2$、mixed主目标一致、别名积分性、变量减少和SPBS可行性 | 下方单元测试；只能作代码验证 |
| M2 | 独立解验证 | 重载每个incumbent并检查原MIP可行性 | 第6.1节+第7节validation |
| M3 | Gu BS/HTS约化特例 | 可选外部边界验证；两个模型不等价，不作为核心实验前置 | 无Stage；最短路线以文献差异表代替，不声称约化等价 |
| M4 | 模型规模表 | 报告变量数、整数变量数、约束数、LP大小和解析时间随晶圆数增长 | `model-evidence` Stage，见下方命令 |
| M5 | 两阶段稳定性 | 比较`full/stage2_off/linear_off`并按primary status区分最优证明与incumbent抛光 | 第6.3节+第7节stability |
| A1 | SCIP none vs SPBS | 隔离原始热启动对incumbent率、PDI和gap的主效应 | 第6.5节+第7节spbs |
| A2 | HEM/Proposed none vs SPBS | 仅用于估计热启动与学习策略的difference-in-differences交互 | 可选；只有保留“协同/交互”主张时才实现并补跑 |
| A3 | HEM greedy vs beam | 隔离有限宽束搜索 | 第6.2节Main中的HEM-13D/HEM-13D+beam |
| A4 | 13D/23D/structure消融 | 隔离变量角色比例与次模补全 | 第6.2节Main；角色特征比较必须使用双方greedy |
| A5 | strict A3C vs policy gradient | 仅在算法名坚持A3C时验证评论家、价值损失和更新时序 | **无支持Stage；默认不主张strict A3C** |
| A6 | RL-SAT | 可选附录验证CP-SAT抽象边界 | 不进入主实验，无命令 |

M1与M4统一执行命令如下；该命令生成可审计的模型规模原始表与按profile/晶圆数聚合表：

```powershell
Set-Location D:\git\git\RDMCT-A3C; .\cie\run_cie_single.ps1 -Stage model-evidence -LogId cie_model_evidence_repro_v1
```

M3和A2不是当前主张的硬阻塞项：M3因问题设定不等价而改为文献边界比较；A2通过不作协同/交互声明而保持可选。`model-evidence`、冻结清单、warm starts、训练、Validation以及Main、Stability、DOE、SPBS、Sensitivity和OOD均已完成并审计。

## 4. 正式冻结门槛

已在commit`08f3d5959ca49dc836c0ad9d3b957bdbed7ab181`建立clean训练快照并重新生成数据。随后新增了checkpoint manifest强制门禁、可恢复训练/ACS/benchmark以及`model-evidence` Stage，因此仍需在这些修改验收后建立最终评估commit；训练模型无需重做。正式benchmark的冻结点必须记录训练commit与最终评估commit。

若修改仅涉及评估resolver、审计器或新增实验Stage，而训练代码、配置、训练LP及其hash均未改变，已完成模型可以保留，但最终清单必须同时记录训练commit与评估commit。若训练代码、特征、奖励、数据或配置发生变化，则受影响模型必须重训。完成所有代码/指标修改后，再建立干净、可追溯的评估冻结提交。

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
python -m pytest tests/test_cie_resume.py tests/test_compact_petri_model.py tests/test_training_and_cie_contract.py tests/test_cie_combine_runs.py tests/test_analyze_cie_solutions.py tests/test_audit_cie_submission.py tests/test_analyze_cie_submission.py tests/test_cie_runbook_schedule.py tests/test_cie_postprocess_contract.py -q
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

8GB GPU一次只训练一路，仍按family×seed拆开。`train-*`入口现已默认传入`--auto_resume`：每个epoch结束后，`params.pkl`以原子替换方式保存模型、高/低层策略优化器、学习率调度器、移动平均基线、归一化器、随机数状态、已完成epoch，以及代码/配置/训练LP签名。中断后原样重跑命令，会在同一日志目录从最后完整epoch继续；若已存在严格匹配的epoch-60检查点则整条跳过。中断发生在一个epoch内部时，仅重做该epoch。旧的weights-only中间模型缺少完整训练状态，脚本会拒绝把它作为精确恢复点并从epoch 0建立新运行。训练配置当前固定使用`cuda:0`，`-GpuDevice`参数尚未透传到训练程序。HEM、feature-only和Proposed均已5/5完成，不要重跑本节训练命令；这些命令只保留为来源审计和缺失时恢复参考。

先检查是否仍有训练进程；有输出时不要启动第二路训练：

```powershell
Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'python.exe' -and $_.CommandLine -match 'parallel_reinforce_algorithm.py' } | Select-Object ProcessId,ParentProcessId,CommandLine
```

feature-only已5/5完成。仅当manifest审计明确指出某个seed缺失时，才按对应seed原样恢复；不要手工添加`--resume_model`或`--start_epoch`：

```powershell
Set-Location D:\git\git\RDMCT-A3C; .\cie\run_cie_single.ps1 -Stage train-feature-only -Seeds '1' -LogId cie_train_feature_only_seed1_repro_v1
Set-Location D:\git\git\RDMCT-A3C; .\cie\run_cie_single.ps1 -Stage train-feature-only -Seeds '2' -LogId cie_train_feature_only_seed2_repro_v1
Set-Location D:\git\git\RDMCT-A3C; .\cie\run_cie_single.ps1 -Stage train-feature-only -Seeds '3' -LogId cie_train_feature_only_seed3_repro_v1
Set-Location D:\git\git\RDMCT-A3C; .\cie\run_cie_single.ps1 -Stage train-feature-only -Seeds '4' -LogId cie_train_feature_only_seed4_repro_v1
Set-Location D:\git\git\RDMCT-A3C; .\cie\run_cie_single.ps1 -Stage train-feature-only -Seeds '5' -LogId cie_train_feature_only_seed5_repro_v1
```

Proposed 5/5已经完成，不要重跑。只有后续来源审计明确发现某个seed缺失时，才使用以下对应恢复命令：

```powershell
Set-Location D:\git\git\RDMCT-A3C; .\cie\run_cie_single.ps1 -Stage train-proposed -Seeds '1' -LogId cie_train_proposed_seed1_repro_v1
Set-Location D:\git\git\RDMCT-A3C; .\cie\run_cie_single.ps1 -Stage train-proposed -Seeds '2' -LogId cie_train_proposed_seed2_repro_v1
Set-Location D:\git\git\RDMCT-A3C; .\cie\run_cie_single.ps1 -Stage train-proposed -Seeds '3' -LogId cie_train_proposed_seed3_repro_v1
Set-Location D:\git\git\RDMCT-A3C; .\cie\run_cie_single.ps1 -Stage train-proposed -Seeds '4' -LogId cie_train_proposed_seed4_repro_v1
Set-Location D:\git\git\RDMCT-A3C; .\cie\run_cie_single.ps1 -Stage train-proposed -Seeds '5' -LogId cie_train_proposed_seed5_repro_v1
```

下面的长命令是历史禁用示例，保留仅用于解释旧结果为什么不合格，仍严禁执行。它后面的`freeze-checkpoints`才是当前正式命令：

```powershell
throw 'DISABLED: checkpoint manifest is not consumed by the runner and fixed seed_N paths select legacy models.';$rows=foreach($family in @('hem','feature_only','proposed')){foreach($seed in 1..5){$dir="cie\models\$family\seed_$seed";$variant=Join-Path $dir 'variant.json';$checkpoint=Join-Path $dir 'itr_60.pkl';if(-not(Test-Path -LiteralPath $variant -PathType Leaf)-or-not(Test-Path -LiteralPath $checkpoint -PathType Leaf)){throw "Missing formal model: $family seed $seed"};$meta=Get-Content -LiteralPath $variant -Raw|ConvertFrom-Json;$trainingPath=[string]$meta.env.instance_file_path;$validPath=$trainingPath.Replace('/','\').ToLowerInvariant().EndsWith('cie\data\policy_training\train');if([int]$meta.parser_args.seed-ne$seed-or[int]$meta.parser_args.scip_seed-ne$seed-or[int]$meta.experiment.seed-ne$seed-or-not$validPath){throw "Non-auditable metadata: $variant"};[pscustomobject]@{family=$family;training_seed=$seed;checkpoint=(Resolve-Path -LiteralPath $checkpoint).Path;checkpoint_sha256=(Get-FileHash -LiteralPath $checkpoint -Algorithm SHA256).Hash;variant=(Resolve-Path -LiteralPath $variant).Path;variant_sha256=(Get-FileHash -LiteralPath $variant -Algorithm SHA256).Hash;training_path=$trainingPath}}};$rows|Export-Csv cie\results\repro_manifest\selected_checkpoint_manifest.csv -NoTypeInformation; .\cie\run_cie_single.ps1 -Stage gpu-smoke -GpuDevice cuda:0 -LogId cie_gpu_smoke_repro_v1
```

训练后可用下列只读命令列出递归目录中的完整epoch-60候选及元数据；它只是诊断，不是最终门禁：

```powershell
Set-Location D:\git\git\RDMCT-A3C; Get-ChildItem cie\models -Recurse -File -Filter itr_60.pkl | ForEach-Object { $v=Join-Path $_.DirectoryName 'variant.json'; if(Test-Path -LiteralPath $v){$m=Get-Content -LiteralPath $v -Raw|ConvertFrom-Json; [pscustomobject]@{checkpoint=$_.FullName; parser_seed=$m.parser_args.seed; scip_seed=$m.parser_args.scip_seed; experiment_seed=$m.experiment.seed; training_path=$m.env.instance_file_path; modified=$_.LastWriteTime}} } | Sort-Object checkpoint | Format-Table -AutoSize
```

当前正式命令（已执行并得到15/15；最终冻结前再执行一次）：

```powershell
Set-Location D:\git\git\RDMCT-A3C; .\cie\run_cie_single.ps1 -Stage freeze-checkpoints -CheckpointManifest cie\results\repro_manifest\selected_checkpoint_manifest.csv -LogId cie_freeze_checkpoints_repro_v1
```

**正式checkpoint门禁已实现。** Main、Stability和OOD只从冻结清单读取15个明确`itr_60.pkl`，逐一校验路径/hash/variant hash/三处seed/训练路径，并禁止`params.pkl`回退。任何校验失败都会在求解前停止，避免昂贵实验白跑。

ACS只允许在validation上调，随后复制为固定文件。当前720/720已完成并已冻结；不要重跑，除非审计发现hash或文件损坏：

```powershell
.\cie\run_cie_single.ps1 -Stage tune-acs -MemoryLimitMB 4096 -LogId cie_tune_acs_repro_v1
```

ACS调参执行4个validation实例×5个seeds×（1个default+35个simplex profile）=720次求解。现在每次求解结束都会立即追加并`fsync`到`cie/results/acs_tuning/.checkpoints/acs_grid_<signature>.jsonl`；签名覆盖参数、manifest、validation LP及关键求解代码。中断后原样重跑上面的命令，已完成项显示`source=resume`并跳过，最多重做中断时正在运行的一个求解；全部完成后以原子替换生成稳定命名的`acs_grid_<signature>.json`。不要使用`--no_resume`进行正式调参。ACS仍属于冻结前调参而不是确认性性能样本，但其720次选择过程已经可以审计和恢复。

```powershell
$src=(Get-ChildItem cie\results\acs_tuning -Filter 'acs_grid_*.json' | Sort-Object LastWriteTime | Select-Object -Last 1).FullName; Copy-Item -LiteralPath $src -Destination cie\results\repro_manifest\selected_acs.json -Force; Get-FileHash cie\results\repro_manifest\selected_acs.json -Algorithm SHA256 | Export-Csv cie\results\repro_manifest\selected_acs_sha256.csv -NoTypeInformation
```

以下是三类warm-start的完整命令。core 48/48、sensitivity 8/8和OOD 9/9均已完成，不要重跑。OOD最后一个48片1:1旧SPBS文件具有当前LP hash，但仅覆盖主排程而缺少完整二阶段作用域；修复器在当前模型上重新验证主排程、补全13个二阶段变量并再次完整验解，最终报告 failures=0。

```powershell
.\cie\run_cie_single.ps1 -Stage warmstarts-core -WarmStartTimeLimit 180 -MemoryLimitMB 2048 -LogId warm_core_repro_v1
```

```powershell
.\cie\run_cie_single.ps1 -Stage warmstarts-sensitivity -WarmStartTimeLimit 600 -MemoryLimitMB 2048 -LogId warm_sensitivity_repro_v1
```

```powershell
.\cie\run_cie_single.ps1 -Stage warmstarts-ood -WarmStartTimeLimit 600 -MemoryLimitMB 4096 -LogId warm_ood_repro_v1
```

任一warm-start命令中断后原样重跑。生成器只复用同时具备完整`.sol`、完整`.meta.json`、`solution_scope=full_quadratic_model`且`instance_sha256`与当前LP一致的实例；半写文件或旧LP对应文件不会被接受。因此已完成实例直接跳过，最多重做当前实例。恢复时不得改变profile、时间/内存限制或LP。

验收：core为48个generated和12个pure-4x1 not-applicable，sensitivity为8，OOD为9；`failures=0`且LP hash匹配。

以下1800秒命令现在只作为未来hash变化或文件损坏后的恢复参考，不要在当前状态重跑：

```powershell
Set-Location D:\git\git\RDMCT-A3C; .\cie\run_cie_single.ps1 -Stage warmstarts-ood -WarmStartTimeLimit 1800 -MemoryLimitMB 4096 -LogId warm_ood_repro_v1
```

model-evidence已完成81/81个LP并生成raw、summary与manifest；Validation 4/4及独立验解/投稿审计PASS。Main、Stability、DOE、SPBS、Sensitivity和OOD均已完成并审计。当前主张所需实验已经闭合，无继续运行命令。

## 6. 正式benchmark：已全部完成（从零复现时最多三路）

**benchmark前置门槛和七阶段验收均已通过。** OOD warm-start 9/9、model-evidence 81/81、15模型可移植manifest、Validation 4/4及六组正式benchmark 6269/6269均已完成。M3不是等价模型的强制实验，A2仅在新增SPBS与学习策略协同/交互主张时必需。第6.1--6.7节命令均仅作为可恢复复现记录保留，当前不要重跑。

若将来从零复现，三个终端分别执行标记为A/B/C的队列，同一终端中的命令按出现顺序逐条执行，任意时刻最多三条。矩阵按solver seed和training seed拆开以均衡负载；一个阶段全部完成并验收后再进入下一阶段。Main/OOD显式使用冻结ACS；Main/OOD/Stability还通过默认参数`cie\results\repro_manifest\selected_checkpoint_manifest.csv`强制使用冻结模型。复现中需要停机时，在各终端各按一次`Ctrl+C`并等待提示符返回；再次原样运行同一命令即可读取`.checkpoints/*.jsonl`中的完整原子项。不得更换CampaignId或ShardTag冒充续跑。

每次新开三个终端，先分别执行一次以下单行设置，避免SCIP文本日志膨胀：

```powershell
Set-Location D:\git\git\RDMCT-A3C; $env:CUDA_MODULE_LOADING='LAZY'; $env:RDMCT_COMPACT_TEXT_LOG='1'; $env:RDMCT_TEXT_LOG_MAX_MB='2'; $env:RDMCT_TEXT_LOG_BACKUP_COUNT='1'
```

### 6.1 Validation

目的：用4个冻结小实例验证求解、写解、独立验解、manifest和ACS链路；它是Main的最小故障隔离门槛，不用于调参或形成性能结论。

```powershell
.\cie\run_cie_single.ps1 -Stage benchmark-validation -CampaignId cie_validation_600s_repro_v1 -ShardTag seed1 -LogId cie_validation_600s_repro_v1_seed1 -Seeds '1' -TimeLimit 600 -MemoryLimitMB 2048
```

### 6.2 Main（目标2700行）

目的：在共同auto-SPBS、共同预算和5×5随机种子设计下比较SCIP、ACS、HEM-13D、HEM-13D+beam、23D feature-only、structure策略与Proposed；检验总体算法优势，并隔离束搜索、角色特征和结构补全的贡献。

当前进度：已完成2700/2700，运行错误0、解写出错误0、incumbent 2700/2700；全部保存解独立验解通过，精确矩阵审计`PASS`，正式统计已回填论文。平均PDI为16585.70、平均求解时间218.32~s，二者均为七方法最低；相对HEM和SCIP的PDI分别降低1.41\%和1.97\%。本节命令仅作复现来源保留，当前不要重跑。

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

目的：比较`full/stage2_off/linear_off`，验证条件式第二阶段目标是否在不改变主目标最优性的前提下改善排程稳定性，并区分已证明最优与仅有incumbent的结果。

当前进度：已完成1500/1500，运行错误0、全部incumbent独立验解通过，严格`solution_file` 1:1联接和后处理审计均为`PASS`。full、linear_off、stage2_off的平均物理路径总等待分别为2596.012、2469.472、5398.597，最大等待分别为296.326、293.271、952.570，节拍CV分别为0.130049、0.134292、0.215676，节拍偏差和分别为22.040、60.180、370.408。相对stage2_off，full的四项降幅依次为51.91\%、68.89\%、39.70\%、94.05\%，Holm校正$p$依次为$3.81\times10^{-5}$、0.00224、0.02137、0.01838；相对linear_off仅节拍偏差和降低63.38\%且显著（Holm $p=0.0377$），其余不显著。full第一阶段预算为540~s，而关闭阶段的配置为600~s，所以PDI和求解时间不作因果加速证据。本节命令仅作复现来源保留，当前不要重跑。

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

目的：估计晶圆数、双源比例、模块构型与处理时间等制造因素对模型表现的主效应及预设交互，证明结论不是由单一实例结构偶然驱动。

当前进度：已完成300/300，运行错误0、全部保存解独立验解通过，审计`PASS`；60个析因单元、预设交互、置信区间和两张程序图均已生成并回填论文。本节命令仅作复现来源保留，当前不要重跑。

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

目的：固定SCIP和预算，仅比较none与auto-SPBS，识别warm initial solution对incumbent率、PDI和最终gap的独立主效应；本阶段不证明它与学习策略存在协同。

本阶段已完成960/960：none与auto各480行；728个incumbent独立验解有效，投稿审计PASS。下列命令仅作同一campaign的可恢复复现记录，当前不要重跑。

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

目的：检验运动/加工时间、真空区假片容量和清洗参数变化时结论方向是否稳定，回答参数扰动下的鲁棒性问题。

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

目的：在更大规模和分布外构型上检验可行解交付能力与性能边界；全部方法统一触顶时以PDI、最终gap、incumbent率和上下界为主，不把原始运行时间作为速度证据。

最终状态：729/729完成，三个分片各243行；重复键0，runner error与solution-write error均为0。729行全部为`timelimit`且全部有incumbent，所有保存解均通过独立验解，`invalid_count=0`，投稿审计`PASS`。ACS取得最低平均OOD PDI；RDMCT-HBS的OOD均值不占优，所有全局Holm校正方法差异均不显著。因此，本阶段证明共同求解链在九个更大构型上均能交付有效可行排程，不证明RDMCT-HBS在分布外显著领先。以下三条命令仅用于从零复现，当前不要执行。

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

七个正式campaign的后处理均已执行并通过。run_cie_postprocess.ps1 按失败即停止的顺序完成：递归合并、SCIP独立验解、精确矩阵/主键/错误/solution审计、制造实例优先聚合、bootstrap 95%区间、配对效应量、双侧Wilcoxon与全局Holm。DOE另外输出预设主效应、两两交互、OLS置信区间、诊断数据和两张程序生成的非AI图。以下命令仅作为确定性复现入口保留。

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

### 7.1 跑完后如何判断能否反映算法优势

主结论预先以PDI为主要指标，最终gap、incumbent rate和可行解质量为次要指标；只有部分方法提前结束时才比较求解时间。所有方法都到达600/1200秒时，不能把相同的截尾时间当作速度证据。

- Proposed对HEM-13D与SCIP：回答完整方法是否整体占优，但不能把差异归因于单一组件。
- HEM-13D+beam对HEM-13D：隔离束搜索贡献。
- feature-only-23D-greedy对HEM-13D-greedy：隔离角色/扩展特征贡献。
- Proposed对structure-greedy：在相同结构策略下检验束搜索增益。
- SCIP-auto对SCIP-none：只检验SPBS warm start的独立贡献，不解释学习策略交互。

“评测样本内的平均优势”和“总体统计显著优越”必须分开判断。完整2700次Main矩阵显示：RDMCT-HBS在七种配置中取得最低观测平均PDI与最短观测平均求解时间，平均PDI相对HEM和SCIP分别降低1.41\%和1.97\%。正文可明确陈述这一标称矩阵样本事实。相对HEM和SCIP的实例级区间仍跨零且Holm校正$p=1.0$，所以不得扩大为“总体统计显著优于所有基线”“对所有实例普遍优越”或无条件的实际领先。

模型贡献已有独立的确认性证据：1500次Stability实验全部通过独立验解，严格物理指标由事件时间重构后按`solution_file` 1:1联接，后处理审计`PASS`。相对stage2_off，完整两阶段配置使物理路径总等待、最大等待、节拍CV和节拍偏差和分别降低51.91\%、68.89\%、39.70\%和94.05\%，Holm校正$p$分别为$3.81\times10^{-5}$、0.00224、0.02137和0.01838；相对linear_off仅节拍偏差和降低63.38\%且显著。SPBS 960行也已形成确认性算法证据：自动初始解使incumbent率提高48.33个百分点、PDI降低26.19\%，两项Holm校正后均显著。Sensitivity 80行证明预设OFAT场景均能产生经验证incumbent，但不证明跨方法排序稳健。OOD 729行全部触顶但均产生经验证incumbent；ACS平均OOD PDI最低且全局Holm校正差异均不显著，因此只主张分布外可行解交付，不主张RDMCT-HBS的OOD排序优势。

`timelimit`行必须保留。存在incumbent时使用PDI、gap、上下界与解质量；无incumbent时进入incumbent-rate及预设惩罚/截尾分析，不能删行。归档检查先核对每个campaign的`submission_audit.json`为`PASS`，再从`cie_submission_analysis.json`和配套CSV追溯中英文稿数值；任何手工挑选行或跨campaign混合都不允许。

## 8. 论文和Editorial Manager投稿包

现有分析导向英文稿使用官方`elsarticle` class，并有同步中文审查稿、独立匿名入口、title page、cover letter、highlights、figure captions和supplement。Main、Stability、DOE、SPBS、Sensitivity及OOD正式结果均已回填，MiKTeX工具链可生成英文和中文PDF。计算证据已经闭合；最终上传仍取决于作者补齐基金/致谢、逐作者CRediT、ORCID、全体作者原创性与投稿同意、通信作者完整邮寄地址和电话，以及匿名数据/代码评审链接，并完成最终匿名化与源包冻结。

最终按“官方要求 + 本项目论文完整性门槛”准备：

- 匿名正文 `manuscript_anonymous.tex/pdf`：无作者、单位、致谢、基金号、身份化仓库链接或文件元数据。
- 单独title page：题名、与Editorial Manager顺序一致的所有作者、每个单位的完整标准名称/邮寄地址/国家、致谢、利益冲突、通信作者邮寄地址、邮箱和电话。
- 可编辑 `highlights.txt`：3--5条，每条含空格不超过85字符；当前5条长度合规，最终应替换为有证据的结果。
- Elsevier declarations tool生成的利益冲突 `.doc/.docx`；无冲突也必须提交声明。
- CRediT、Funding、Data statement和数据/代码链接：匿名评审稿删除或匿名化逐作者CRediT、完整基金号和身份化链接；完整作者贡献与Funding放在不发审稿人的title-page/author-details文件或Editorial Manager字段，接受后的最终稿恢复。初投使用匿名评审链接；最终归档使用永久标识符（优先DOI）。若数据不能共享，Data statement必须说明原因。
- 生成式AI声明：本稿已在参考文献前披露Codex辅助的工具用途、人工复核和作者责任；最终提交前再次核对措辞。不得用生成式AI制作或修改投稿图片或graphical abstract。
- 投稿型supplement：完整模型、算法和超参数、实例生成、全部结果与失败行、统计细节、环境与复现清单。它是本项目因正文承诺补充材料而设的内部必需项，不是C&IE对所有论文的通用硬性项。
- LaTeX平铺源包：tex、bib/bbl、必要bst/sty和图片处于同一目录；PDF不是源文件。每幅图按正文顺序单独保存为 `Figure_*.pdf/png/tiff`，另备可编辑 `figure_captions.txt`。
- APA 7参考文献、术语表、图表交叉引用、拼写检查、版权许可、作者一致批准和非一稿多投确认。
- Cover letter建议准备，但当前公开Guide未把它列为通用硬性项；以正式上传当天Editorial Manager字段为准。

官方数值门槛：摘要不超过250个英文词；关键词1--7个；highlights 3--5条且每条不超过85字符。摘要还应独立、事实性地给出目的、主要结果和结论，不含参考文献，非常用缩写首次定义；关键词必须为英文，避免含 `and/of` 的冗长短语，仅使用公认缩写。Graphical abstract为鼓励项而非硬性项。投稿当天以官方Guide为准。

方法命名已统一为`RDMCT-HBS`。正文准确表述其学习组件为“A3C启发的并行层次策略梯度”，并说明使用共享策略网络与指数移动平均基线；这与当前实现一致，不冒充含独立学习评论家的strict A3C。算法贡献由SPBS热启动、23维角色特征重构、层次策略与有限宽束搜索共同构成，SCIP负责可行性与证明。

## 9. 实验闭合与上传前作者事项

| 项目 | 最终状态 |
| --- | --- |
| Validation | 4/4，独立验解与投稿审计`PASS` |
| 六组正式benchmark | 6269/6269；Main 2700、Stability 1500、DOE 300、SPBS 960、Sensitivity 80、OOD 729 |
| 全部核心矩阵 | 含Validation为6273/6273，无重复键，七阶段审计均为`PASS` |
| Incumbent验解 | 6041个incumbent全部独立验解通过，`invalid_count=0` |
| 追加计算 | 当前论文主张不需要新增实验；A2只有在新增SPBS与学习策略协同/交互主张时才需要 |

当前没有待续跑的正式实验或后处理命令。上传前必须由作者确认或补齐：基金与基金号、致谢、逐作者CRediT、ORCID、全体作者原创性/独家投稿/最终版本同意、通信作者完整邮寄地址和电话，以及匿名数据/代码评审链接。上述项目依赖作者信息或外部归档服务，不以实验运行时长估算。

## 10. “可以投稿”的最终定义

- [x] `model-evidence`、checkpoint选择规则和当前正文所需机制边界已冻结；M3/A2仅在增加对应主张时补充。
- [ ] 工作区对应一个可复现commit，环境、LP、模型、ACS均有hash。
- [x] 求解入口强制消费冻结checkpoint manifest；15个模型路径/hash与每行结果一致，正式命令没有`-AllowLegacyCheckpoints`。
- [x] 6273行核心矩阵完整、无重复，建模证据单独验收，错误处理和censoring规则可审计；当前不声称SPBS×策略协同。
- [x] 七阶段共6041个incumbent全部独立验解通过，`invalid_count=0`。
- [x] Main、Stability、DOE、SPBS、Sensitivity与OOD实例级统计均已完成；七阶段投稿审计均为`PASS`。
- [x] 算法名统一为RDMCT-HBS，A3C启发的并行层次策略梯度表述与实现一致。
- [x] 中英文分析导向稿无`TBD`或无来源结果；SPBS、Sensitivity与OOD均已回填并可追溯到正式分析产物。
- [ ] 双匿名稿、title page、highlights、利益冲突、AI声明、CRediT、Funding、Data statement和LaTeX源包齐全；本项目内部要求的supplement齐全，cover letter按Editorial Manager字段准备。
- [ ] 摘要、关键词、highlights、APA 7、术语表和匿名化检查通过。

满足这些门槛表示“材料达到可投稿状态”，不代表期刊必然录用。

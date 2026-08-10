# Computers & Industrial Engineering 投稿执行手册

> 审计时间：2026-08-09（Asia/Shanghai）。本文给出从当前证据状态走到可投稿状态的执行顺序。实验协议定义仍以 [`../README.md`](../README.md) 为准。本文中的 PowerShell 命令均为单行命令，不使用续行符。

官方依据：[C&IE Guide for Authors](https://www.sciencedirect.com/journal/computers-and-industrial-engineering/publish/guide-for-authors)；[Elsevier LaTeX instructions](https://www.elsevier.com/en-gb/researcher/author/policies-and-guidelines/latex-instructions)。投稿要求可能变化，正式上传当天再次核对。

## 1. 当前证据状态与论文主张边界

### 1.1 旧 OOD 已完成，但只属于工程诊断

`cie_ood_1200s_mem4096_final_v1` 已于2026-08-02完成729/729条唯一记录（三个solver-seed分片各243条），无重复键、无runner error、无solution-write error。729条全部为`timelimit`。SCIP与ACS各自27/27条产生incumbent；每个学习方法族只有27/135条产生incumbent，且只有旧training seed 1有效。15个旧`variant.json`均记录`experiment.seed=1`，代码还跨批次修改。因此，该活动只能说明运行器、内存设置和大实例困难度，不能进入正式主表或OOD性能表，也不能通过挑选其中效果好的行证明算法优势。

`timelimit`不等于“结果无效”，而是共同预算到期时尚未完成证明；有incumbent的行仍可用于PDI、最终gap、上下界、首次可行解和incumbent rate分析。由于旧活动的检查点来源不合格，它被排除的根因是provenance，而不是`timelimit`本身。

### 1.2 投稿级路线的真实起点

正式`*_repro_v1` benchmark已采集Main 2700/2700行和Stability原子检查点885/1500行。三类新模型均已完成：HEM、feature-only与Proposed各5/5，共15/15个epoch-60检查点。`selected_checkpoint_manifest.csv`冻结了15/15个明确路径及checkpoint/variant SHA-256；Main、Stability和OOD的runner强制读取并逐项校验该manifest，不回退`params.pkl`。Main精确矩阵、主键、错误和解文件数量完整，但2026-08-09独立SCIP `checkSol`发现7/2700个文本保存解未通过，故投稿审计当前为FAIL。逐条打印违反原因后确认，7条均只涉及连续时间先后约束，违反量统一为$1.00000011116208\times10^{-6}$，即仅比默认$10^{-6}$可行性容差多约$1.11\times10^{-13}$；这是解文本往返精度边界，不是离散路由或资源冲突。仍须预先声明并测试统一的round-trip验解容差、重跑全部独立验解并取得PASS，才能冻结正式统计。旧`cie/models/<family>/seed_N`目录、旧Main、旧OOD、旧SPBS和smoke不得并入新campaign。正式命令禁止使用`-AllowLegacyCheckpoints`。

正式训练输出位于带时间戳的递归目录，而不是固定的`cie/models/<family>/seed_N`。必须按`variant.json`中的parser seed、SCIP seed、experiment seed和训练数据路径递归解析，并强制存在`itr_60.pkl`；不能把中断训练的`params.pkl`当作epoch 60正式模型。第5节给出门禁。

### 1.3 两篇直接参考文献限定的创新边界

- Gu等（2024）《Scheduling of Multi-finger-robotic Cluster Tools with Multi-space Process Modules》研究四指机械手、四空间工艺模块、单产品稳态运行，并在预先固定的BS/HTS序列下分别建立以周期时间为目标的LP；腔室清洗和多晶圆类型同时处理留作未来研究。本文可主张的是有限时域双源产品/PEC混流、混合$4\times1$/$2\times2$模式、旋转腔室、清洗、载具令牌、灵活分配/排序的精确MIP，以及保持incumbent最大完工时间的条件式第二阶段。两个模型不等价，不能直接比较原始运行时间。
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

### 2.1 2026-08-08中断点与恢复位置

当前没有Python/SCIP评测进程。三路Stability均为外部中断而非程序异常，`run.err.log`均为空。可直接审计到的最后终端输出时间分别为：solver seed 1在2026-08-08 00:15:49.391、seed 2在00:16:43.335、seed 3在00:16:18.076（中国标准时间）；因此本次中断的最后可观测时间为2026-08-08 00:16:43.335。日志没有单独记录操作系统杀进程时刻，不能把最后输出时间伪称为精确终止时刻。

原子保存进度为885/900（当前三路子矩阵），总Stability目标进度为885/1500：seed 1保存293/300，停在`linear_off`、training seed 5，最后完成实例`cie_core_n024_f000_m024_proc100.lp`，恢复后从第14/20个实例`cie_core_n024_f006_m018_proc100.lp`开始；seed 2与seed 3各保存296/300，最后完成`cie_core_n024_f018_m006_proc100.lp`，恢复后均从第17/20个实例`cie_core_n032_f000_m032_proc100.lp`开始。重新执行第6.3节A1、B1、C1三条原命令即可，签名相同的已完成行自动跳过；这不是继续训练，15个训练模型早已完成，而是继续稳定性benchmark。三路只剩7/4/4、合计15个未原子保存的任务，各路首个任务就是中断时正在计算的实例，按600秒上限并行恢复约需1--1.5小时。

## 3. 投稿前必须补齐的证据

| 项目 | 投稿目标 | 当前正式有效 | 目的 |
| --- | ---: | ---: | --- |
| 冻结清单与数据 | 1套 | 已建立 | 运行前commit、环境和90个LP hash；数据生成81/81成功 |
| 可审计模型 | 15 | 15 | HEM、feature-only、Proposed各5/5，全部epoch 60 |
| 选定检查点清单 | 1 | 已完成 | 15/15路径、variant/hash和三处seed已冻结，runner强制消费 |
| ACS validation网格 | 720 solves | 720 | 调参完整并已冻结`selected_acs.json`及hash |
| Warm starts | 65 | 已完成 | core 48、sensitivity 8、OOD 9均通过；OOD报告 failures=0 |
| Validation | 4行 | 4 | 4/4均有incumbent，独立验解、精确矩阵和投稿审计全部PASS |
| 建模证据 | 1套 | 已完成 | compact测试通过；81/81个LP的变量、约束、文件大小和解析时间表已生成 |
| Main | 2700行 | 2700已采集；审计FAIL | 精确矩阵完整，但7个保存解未通过独立`checkSol`，修复前不得作为最终投稿证据 |
| Stability | 1500行 | 885个原子完成行 | `full/stage2_off/linear_off`控制变量实验；当前三路885/900，总体尚缺615 |
| DOE | 300行 | 0 | 制造因素主效应和预设交互 |
| SPBS | 960行 | 0 | auto warm start与none组件对比 |
| 学习策略×SPBS交互 | 可选 | 0 | 仅在正文主张SPBS与学习策略存在协同/交互时必做 |
| Sensitivity | 80行 | 0 | 工艺和资源参数稳健性 |
| OOD | 729行 | 0 | 大规模分布外泛化 |

当前已实现的正式benchmark核心矩阵合计6273行，其中已采集3585行（Main 2700，Stability 885）。Main阶段性实例级统计中，Proposed平均PDI为16585.70，低于HEM的16823.18和SCIP的16919.01，但相对HEM的bootstrap 95\%区间为$[-446.70,846.26]$（以“对照减Proposed”为正），全局Holm校正$p=1.0$；因此只能写“观察到改善趋势”，不能写“显著优于”。最短可投稿路线不把非等价Gu特例和“学习策略×SPBS协同”设为硬前置；正文必须相应收窄为“新MIP相对文献边界的扩展”“学习策略改进的主效应”和“SPBS初解的独立主效应”，不得写成二者存在正交互。当前最高优先级不是启动新的DOE/OOD，而是诊断Main的7条独立验解失败并使审计达到`invalid_count=0`。

正式benchmark启动前的实际门槛如下：

1. 论文机制表要求 cut-pool size、角色覆盖、冗余、callback开销和root-bound证据；当前runner只有部分callback时间，没有完整cut count、dual bound、root gap、LP iterations、首次/最佳解/证明时间。应先增加并测试遥测，或删除论文中对应声明。冻结后再改遥测会迫使正式实验全部重跑。
2. checkpoint门禁已经实现并冻结15/15；正式启动前再次执行`freeze-checkpoints`，确认清单仍为15/15且hash未漂移。
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

M3和A2不再是最短路线的硬阻塞项：M3因问题设定不等价而改为文献边界比较；A2通过删除协同声明而改为可选。`model-evidence`、冻结清单、OOD warm starts、测试、最终评估commit和validation全部通过后，即可启动6273行正式benchmark。

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

model-evidence已完成81/81个LP并生成raw、summary与manifest；CIE相关测试59/59通过；最终评估commit与可移植manifest已推送；Validation 4/4及独立验解/投稿审计PASS。**现在从这里继续：** 第6.2节Main三队列已获准启动。

## 6. 正式benchmark：最多三路

**benchmark前置门槛已全部通过，Main可以启动。** OOD warm-start 9/9、model-evidence 81/81、CIE测试59/59、15模型可移植manifest、GitHub冻结提交以及Validation 4/4独立验解/投稿审计均已完成。M3不是等价模型的强制实验，A2仅在声称协同时必需。现在按第6.2节A/B/C三终端队列启动Main。

三个终端分别执行标记为A/B/C的队列，同一终端中的命令按出现顺序逐条执行，任意时刻最多三条。矩阵按solver seed和training seed拆开以均衡负载；一个阶段全部完成并验收后再进入下一阶段。Main/OOD显式使用冻结ACS；Main/OOD/Stability还通过默认参数`cie\results\repro_manifest\selected_checkpoint_manifest.csv`强制使用冻结模型。需要停机时在各终端各按一次`Ctrl+C`并等待提示符返回；启动器会清理该实验的子进程树。第二天原样重跑当时尚未完成的同一条命令；完成行从`.checkpoints/*.jsonl`恢复，中断时正在求解且尚未写入的一个原子项会自动重做。不得用新的CampaignId或ShardTag“续跑”，否则会建立另一套断点。

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

当前进度：七个分片均已结束，精确矩阵2700/2700、运行错误0、解写出错误0、incumbent 2700/2700。阶段性统计已写入论文，但独立验解有7行失败，投稿审计为FAIL。失败集中于两个实例：`cie_core_n016_f008_m008_proc100.lp`的HEM、HEM+Beam、Structure+Greedy和Proposed各1行，以及`cie_core_n024_f000_m024_proc100.lp`的Feature-only、Structure+Greedy和Proposed各1行；SCIP与ACS没有失败。7条的最大违反量均为$1.00000011116208\times10^{-6}$，属于文本序列化后刚好越过默认容差的连续先后约束。不要重跑整个Main，也不要删除检查点。下一步应为独立验解器加入明确、保守且有单元测试的round-trip容差策略，同时保留原始残差报告；随后重跑第7节Main后处理。只有在更严格的解再导出仍被要求且无法从现有解可靠完成时，才考虑参数一致的修复分片。审计PASS前不得把Main表称为最终投稿结果。

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

当前进度：原子检查点885/1500。先在三个终端分别原样重跑下面的A1、B1、C1；它们会跳过已保存的885行，只重做中断时尚未落盘的当前实例并完成剩余任务。A1剩7个原子任务，B1和C1各剩4个，三路恢复约1--1.5小时。A1/B1/C1完成后，再按既定队列运行A2、B2、C2和C3以补齐solver seeds 4--5；不得提前运行Stability后处理。

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

目的：检验运动/加工时间、PEC容量和清洗参数变化时结论方向是否稳定，回答参数扰动下的鲁棒性问题。

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

目的：在更大规模和分布外构型上检验泛化；大量`timelimit`时以PDI、最终gap、incumbent率和上下界为主，不比较统一触顶的原始运行时间。

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

### 7.1 跑完后如何判断能否反映算法优势

主结论预先以PDI为主要指标，最终gap、incumbent rate和可行解质量为次要指标；只有部分方法提前结束时才比较求解时间。所有方法都到达600/1200秒时，不能把相同的截尾时间当作速度证据。

- Proposed对HEM-13D与SCIP：回答完整方法是否整体占优，但不能把差异归因于单一组件。
- HEM-13D+beam对HEM-13D：隔离束搜索贡献。
- feature-only-23D-greedy对HEM-13D-greedy：隔离角色/扩展特征贡献。
- Proposed对structure-greedy：在相同结构策略下检验束搜索增益。
- SCIP-auto对SCIP-none：只检验SPBS warm start的独立贡献，不解释学习策略交互。

可以写“算法具有优势”的最低证据标准是：Proposed相对预先指定的HEM和SCIP基线在实例级PDI方向上更好，bootstrap 95%置信区间不跨0，双侧配对Wilcoxon经Holm校正后`p<0.05`，同时没有明显恶化incumbent率、验解有效率、错误率或内存失败率；Sensitivity与OOD至少保持相同方向。若仅均值更好但区间跨0，只能写“观察到改善趋势”。若只在挑选的单例上更好，不能主张优势。若Main不显著或方向相反，建模创新仍可投稿，但必须删除算法优越性结论并如实报告失败分析。

`timelimit`行必须保留。存在incumbent时使用PDI、gap、上下界与解质量；无incumbent时进入incumbent-rate及预设惩罚/截尾分析，不能删行。最终先查看每个campaign的`submission_audit.json`是否`PASS`，再从`cie_submission_analysis.json`和配套CSV逐表回填中英文稿，任何手工挑选行或跨campaign混合都不允许。

## 8. 论文和Editorial Manager投稿包

现有英文稿使用官方`elsarticle` class，基础模板正确，但尚不是可上传包。当前有32个`TBD`、8张表、0张图，本机也未安装LaTeX工具链。

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

方法命名已按证据边界处理：仓库项目名为`RDMCT-A3C`，当前稿件算法名为中性的`RDMCT-HPS`，并在方法和数据可用性中明确当前冻结训练是并行层次策略梯度而非strict A3C。只有补完演员--评论家实验后才重新评估算法名。

## 9. 剩余时间估算

| 工作 | 三并发或单路现实估算 | 硬上限/保守估算 |
| --- | ---: | ---: |
| 新OOD warm-start收尾 | 已完成，报告failures=0 | 0小时，不重跑 |
| checkpoint resolver与15模型冻结 | 已完成 | 最终commit后复核约数分钟 |
| 三类模型训练 | 15/15已完成 | 0小时，不重跑 |
| ACS validation网格 | 720/720已完成并冻结 | 0小时，不重跑 |
| model-evidence、测试、冻结与Validation | 已完成且Validation审计PASS | 0小时，不重跑 |
| Main | 2700/2700已采集；7条为统一的$10^{-6}$文本往返容差边界 | 容差策略、测试和重新验解约1--3小时；预计无需重跑2700行 |
| Stability | 885/1500；当前三路收尾约1--1.5小时 | 余下615行全部触顶约34.2小时三并发 |
| DOE、SPBS、Sensitivity、OOD | 0/2069 | 全部触顶约115小时三并发，另加后处理 |
| 可选A2交互增量 | 约23--30小时 | 约61小时；仅保留协同声明时增加 |
| 验解、统计、模型规模表、图表、论文与投稿包 | 4--7天 | 若返工则更长 |

A2若选择执行，采用最短可识别设计：复用Main中相同20实例的auto行，只新增SCIP、HEM-13D和RDMCT-HPS的none行，共约1100行；不重复auto行。按旧Main约222秒/行估算三并发约23小时，全部触顶约61小时。默认最短投稿路线不执行A2，并在正文删除协同/交互主张。

在Main的统一文本往返容差通过测试且无需重跑2700行的前提下，剩余2684个benchmark原子任务按三并发全部触顶约149小时，24小时连续运行约7--10天，夜间必须中断且每天运行12小时约2--3周，再预留2--4天用于验解、统计和论文回填。若期刊级复核要求重新导出或重算7个解，增量应远小于重跑整个Main；只有求解/写解协议必须整体改变时才需要重新评估Main有效性。若坚持strict A3C，还需演员--评论家实现、5个训练模型和至少一组500行标称配对，另预留约2--4周。任何正式benchmark开始后的签名代码/协议修改都会使受影响结果失效。

## 10. “可以投稿”的最终定义

- [ ] `model-evidence`、必要机制指标或对应删稿、checkpoint选择规则在运行前冻结；M3/A2仅在保留对应主张时补充。
- [ ] 工作区对应一个可复现commit，环境、LP、模型、ACS均有hash。
- [ ] runner强制消费冻结checkpoint manifest；15个模型路径/hash与每行结果一致，正式命令没有`-AllowLegacyCheckpoints`。
- [ ] 6273行核心矩阵完整、无重复，建模证据单独验收，错误处理和censoring规则可审计；若声称SPBS×策略协同，再要求约1100行A2增量。
- [ ] 全部incumbent独立验解通过，`invalid_count=0`。
- [ ] 实例级统计、DOE、机制分析、OOD和失败分析全部完成。
- [ ] 算法名保持RDMCT-HPS，或strict A3C演员--评论家实验已完成并通过公平配对。
- [ ] 英文稿没有 `TBD` 或无来源的 `--`，每个数字可追溯到冻结分析产物。
- [ ] 双匿名稿、title page、highlights、利益冲突、AI声明、CRediT、Funding、Data statement和LaTeX源包齐全；本项目内部要求的supplement齐全，cover letter按Editorial Manager字段准备。
- [ ] 摘要、关键词、highlights、APA 7、术语表和匿名化检查通过。

满足这些门槛表示“材料达到可投稿状态”，不代表期刊必然录用。

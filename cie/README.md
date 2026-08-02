# C&IE 投稿级实验复现入口

> 本文是 `cie/` 正式实验的唯一协议，所有命令均从仓库根目录的 PowerShell 执行。当前暂停/恢复、三路单行命令、投稿包和时间表见 [`docs/cie_submission_runbook_zh.md`](docs/cie_submission_runbook_zh.md)。完成流程可得到可审计的实验包，但不能保证录用。

审计日期：2026-08-01。投稿前再次核对 [C&IE 官方 Guide for Authors](https://www.sciencedirect.com/journal/computers-and-industrial-engineering/publish/guide-for-authors) 和 [Elsevier LaTeX instructions](https://www.elsevier.com/en-gb/researcher/author/policies-and-guidelines/latex-instructions)。当前官方指南采用 double-anonymized review，并要求研究数据存储、引用、链接或解释不能共享的原因，同时在投稿时提供 data statement。

## 0. 当前现场结论

- `cie_ood_1200s_mem4096_final_v1` 截至2026-08-01 23:42为674/729个工程观测，三路均在training seed 5；它可以逐项暂停/恢复，但使用旧checkpoint且跨过代码修改，只能做工程诊断。
- 严格投稿级 `*_repro_v1` benchmark 当前为0/6273行，可审计模型为0/15。旧Main/OOD/SPBS不能填最终论文表。
- 今晚停止、明日恢复旧OOD必须使用的新门禁参数、正式重跑顺序和2.5--8周分情景时间估算见[投稿执行手册](docs/cie_submission_runbook_zh.md)。

## 1. 协议边界

- 新复现统一使用 `*_repro_v1` campaign，不追加到旧 campaign。
- 不混合不同 commit、LP、checkpoint、ACS、时间或内存。
- 正式冻结后不再运行 `smoke`、`generate-*` 或重新调 ACS。
- training seed 是独立训练重复；solver seed 是 SCIP 求解重复。两者都不是独立制造实例。
- 旧 checkpoint 只能做功能 smoke；Main/OOD 默认拒绝来源或种子不可审计的模型。

已有结果的真实完成度见 [`products/README.md`](products/README.md)。

## 2. 环境、自检和 smoke

最低 Python 3.10，环境名可以自定。学习方法需要 CUDA；生成、SCIP、warm start 和分析可使用 CPU。

```powershell
conda create -n rdmct-cie python=3.13
```

```powershell
conda activate rdmct-cie
```

```powershell
Set-Location D:\git\git\RDMCT-A3C
```

```powershell
python -m pip install --upgrade pip
```

```powershell
python -m pip install -r requirements.txt
```

```powershell
.\cie\run_cie_single.ps1 -Stage check -LogId cie_check_repro_v1
```

```powershell
.\cie\run_cie_single.ps1 -Stage smoke -LogId cie_smoke_repro_v1
```

smoke 会重建 validation 小实例，因此必须在正式冻结前完成。验收：raw 的 `error`、`solution_write_error` 为空，至少有一个 `.sol`，并且 `cie_manufacturing_metrics.json` 的 `invalid_count=0`。

保存环境：

```powershell
$preStatus=@(git status --porcelain=v1 --untracked-files=all); if ($preStatus.Count -ne 0) { $preStatus; throw 'Worktree must be clean before creating the reproduction manifest.' }; New-Item -ItemType Directory -Force cie\results\repro_manifest | Out-Null; 'CLEAN_BEFORE_MANIFEST' | Set-Content cie\results\repro_manifest\git_status_before_manifest.txt; git rev-parse HEAD | Set-Content cie\results\repro_manifest\git_commit.txt; python -m pip freeze | Set-Content cie\results\repro_manifest\pip_freeze.txt; nvidia-smi | Set-Content cie\results\repro_manifest\nvidia_smi.txt
```

另行记录 OS、CPU、RAM、GPU、Python、Torch/CUDA、SCIP、PySCIPOpt、NumPy、SciPy 和并发方式。正式运行期间不要升级依赖。

## 3. 数据划分与冻结

`generate-all` 不会重建随仓库提供的策略训练划分。先确认 `policy_training/train` 和 `test` 分别有 5、4 个 LP，并保存 hash：

```powershell
@(Get-ChildItem cie\data\policy_training\train -Filter *.lp).Count; @(Get-ChildItem cie\data\policy_training\test -Filter *.lp).Count; Get-ChildItem cie\data\policy_training -Recurse -File | Get-FileHash -Algorithm SHA256 | Export-Csv cie\results\repro_manifest\policy_training_sha256.csv -NoTypeInformation
```

生成 benchmark：

```powershell
.\cie\run_cie_single.ps1 -Stage generate-all -LogId cie_generate_all_repro_v1
```

| 集合 | LP 数 | 用途 |
| --- | ---: | --- |
| validation | 4 | smoke/ACS/完整性检查 |
| core | 60 | DOE；其中 nominal 20 用于 Main |
| core SPBS | 48 | 排除 pure `4x1` |
| sensitivity | 8 | OFAT |
| OOD | 9 | 大规模外部分布 |

```powershell
foreach ($profile in 'validation','core','sensitivity','ood') { "$profile LP=$(@(Get-ChildItem "cie/data/$profile" -Recurse -Filter *.lp).Count)" }; Get-ChildItem cie\data -Recurse -File -Filter *.lp | Get-FileHash -Algorithm SHA256 | Export-Csv cie\results\repro_manifest\cie_lp_sha256.csv -NoTypeInformation
```

预期 4/60/8/9；每个生成报告的 `failures` 必须为空。此后冻结 LP。

## 4. 重训 15 个模型

训练入口已同步 CLI/Python/PyTorch/SCIP seed：

```powershell
.\cie\run_cie_single.ps1 -Stage train-all -Seeds '1,2,3,4,5' -GpuDevice cuda:0 -LogId cie_train_all_repro_v1
```

它依次训练 HEM、feature-only、Proposed，每类 5 seeds。每模型 60 epochs、
每 epoch 8 samples、2 workers、样本 SCIP 上限 30 秒，其中阶段 2 预留
5 秒并使用 `linear`，应按天规划。

```powershell
python -m pytest tests/test_training_and_cie_contract.py -q
```

```powershell
.\cie\run_cie_single.ps1 -Stage gpu-smoke -GpuDevice cuda:0 -LogId cie_gpu_smoke_repro_v1
```

正式模型的 `variant.json` 必须满足 `parser_args.seed == parser_args.scip_seed == experiment.seed`，且训练路径指向当前 `cie/data/policy_training/train`。必须按[执行手册第5节](docs/cie_submission_runbook_zh.md#5-训练acs与warm-start)导出runner实际选中的15个checkpoint路径、variant和各自hash，禁止递归哈希时混入旧模型。若只想检查附带的迁移模型，可在 gpu-smoke 加 `-AllowLegacyCheckpoints`；该结果不得进论文。

仓库附带旧 checkpoint 的 `variant.json` 是不可改写的训练 provenance，其中
可能仍记录第二阶段关闭；不能为“同步配置”而手工改成 true。执行
`train-all` 后生成的新 `variant.json` 才应自然记录当前 `full/linear`
训练配置。`cie_proposed_inference.json` 只描述网络结构，正式求解环境由
runner 的 `stability_profile` 构造，因此该文件没有 `env` 段。

## 5. ACS 与 warm start

ACS 只能在 validation 上调：

```powershell
.\cie\run_cie_single.ps1 -Stage tune-acs -MemoryLimitMB 4096 -LogId cie_tune_acs_repro_v1
```

```powershell
$AcsFile=(Get-ChildItem cie\results\acs_tuning -Filter 'acs_grid_*.json' | Sort-Object LastWriteTime | Select-Object -Last 1).FullName; Get-FileHash $AcsFile -Algorithm SHA256 | Export-Csv cie\results\repro_manifest\selected_acs_sha256.csv -NoTypeInformation
```

该网格为 4 实例 × 5 seeds × 35 profiles，加 default 共 720 次求解，单路最坏约 60 h。实际只生成一个 JSON。Main/OOD 必须显式传 `-AcsWeightsFile $AcsFile`，不要依赖 latest。

```powershell
.\cie\run_cie_single.ps1 -Stage warmstarts-core -WarmStartTimeLimit 180 -MemoryLimitMB 2048 -LogId warm_core_repro_v1
```

```powershell
.\cie\run_cie_single.ps1 -Stage warmstarts-sensitivity -WarmStartTimeLimit 600 -MemoryLimitMB 2048 -LogId warm_sensitivity_repro_v1
```

```powershell
.\cie\run_cie_single.ps1 -Stage warmstarts-ood -WarmStartTimeLimit 600 -MemoryLimitMB 4096 -LogId warm_ood_repro_v1
```

预期 core 48 个 `.sol` 加 12 个 pure-4x1 不适用，sensitivity 8，OOD 9。报告 `failures=0`，status 只能是 `generated` 或 `not_applicable_pure41`，`.meta.json` 的 LP SHA-256 必须匹配。

## 6. 正式 benchmark

Main/稳定化消融/DOE/SPBS/Sensitivity 固定 600 s、2048 MB；OOD 固定
1200 s、4096 MB。所有正常 benchmark 使用 `full` 稳定化 profile：
阶段 2 开启且模式为 `linear`。修改任一协议必须换 campaign 并整组重跑。

### Validation：4 行

实际单行命令见[执行手册第6.1节](docs/cie_submission_runbook_zh.md#61-validation)。

### Main：2700 行

为缩短墙钟时间，必须使用[执行手册第6.2节](docs/cie_submission_runbook_zh.md#62-main目标2700行)的三终端均衡队列；不得再使用单路全矩阵命令。

`20 × [2 个基线 + 5 个学习方法 × 5 training seeds] × 5 solver seeds = 2700`。方法为 SCIP default、validation-tuned ACS、HEM、feature-only、HEM+beam、structure+greedy、Proposed。

### 排程稳定化单因素消融：1500 行

实际单行命令使用[执行手册第6.3节](docs/cie_submission_runbook_zh.md#63-stability目标1500行)的三终端均衡队列。

`20 个实例 × 1 个 Proposed × 5 training seeds × 5 solver seeds × 3
profiles = 1500`。三组严格采用控制变量法：

| profile | `lexicographic_schedule_stability` | `schedule_stability_mode` | 用途 |
| --- | --- | --- | --- |
| `full` | `true` | `linear` | 完整参考组 |
| `stage2_off` | `false` | `linear` | 只关闭阶段 2 |
| `linear_off` | `true` | `quadratic` | 阶段 2 保持开启，只移除 linear 目标 |

脚本固定 Proposed、实例、warm start、training/solver seeds、总预算和停止
条件，并自动以 `proposed[full]` 做实例级分析。Main 的算法优势比较始终为
`full`，不得用这三组替代或混入算法消融。

### DOE：300 行

实际单行命令见[执行手册第6.4节](docs/cie_submission_runbook_zh.md#64-doe目标300行)。

`60 × 5 = 300`；只运行 SCIP default + auto warm start，用于制造因素分析。

### SPBS：960 行

必须使用[执行手册第6.5节](docs/cie_submission_runbook_zh.md#65-spbs目标960行)的none/auto均衡队列；合并器必须通过SPBS条件保留测试，不能把两组折叠为480行。

`48 × 2 × 10 = 960`；只能称为 SPBS auto-vs-none 组件实验。

### Sensitivity：80 行

实际单行命令见[执行手册第6.6节](docs/cie_submission_runbook_zh.md#66-sensitivity目标80行)。

### OOD：729 行

实际单行命令见[执行手册第6.7节](docs/cie_submission_runbook_zh.md#67-ood目标729行)。

`9 × [2 + 5 × 5] × 3 = 729`。保留 timeout、无 incumbent 和非零 gap，不要求全部证明最优。

按每条求解上限估算，单路全矩阵总上限约1166小时；执行手册的均衡三终端固定队列硬上限约403小时，现实benchmark约208--220小时。实际估算与全流程日历时间以[执行手册第9节](docs/cie_submission_runbook_zh.md#9-剩余时间估算)为准。

## 7. 恢复、合并与分析

runner 每完成一个“实例 × 方法 × solver seed”就同步写 `runs/.checkpoints/*.jsonl`。中断后原样重跑即可恢复；不得改 campaign、shard、seed、时限、内存、LP、模型、ACS 或代码。

并行时使用相同 `CampaignId`、不同 `ShardTag/LogId`、互不重叠的 solver seeds；其余协议一致。共享 GPU 会影响 wall-clock，必须记录并发方式。

正式后处理必须使用失败关闭入口；Main 示例：

```powershell
.\cie\run_cie_postprocess.ps1 -Stage main -CampaignId cie_main_600s_mem2048_repro_v1
```

该入口依次完成递归合并、SCIP独立验解、精确矩阵/主键/solution审计、实例级bootstrap/效应量/Wilcoxon/Holm；DOE还生成预设主效应、两两交互、OLS置信区间、诊断数据和非AI程序图。七阶段单行命令及固定reference见[执行手册第7节](docs/cie_submission_runbook_zh.md#7-合并验解和统计)。

最终分析必须先在制造实例内聚合 training/solver 重复，再做双侧配对 Wilcoxon 与 Holm 校正。独立样本数为 Main 20、DOE 60、SPBS 48、Sensitivity 8、OOD 9。runner JSON 的 run-level p 值不用于论文推断。

## 8. 结果与声明边界

raw 重点字段包括 method、solver/training seed、status、time、nodes、gap、PDI、objective、incumbent、solution、错误、checkpoint 和策略设置。制造分析输出 cmax、WPH、cycle time、资源利用率、PEC/cleaning 与 `physically_feasible`。

当前 runner 不完整输出 dual bound、primal integral、首解/最佳解/证明时间、root gap closed、LP iterations、accepted cut count、角色覆盖或冗余。论文若保留这些机制声明，必须先补遥测再冻结正式实验；否则删除对应声明。

- 当前自动投稿统计报告runner failure、incumbent/optimal rate、PDI、gap和求解时间；PAR-2、节点、首解/最佳解/证明时间及工业指标只有在字段和censoring规则于冻结前明确实现后才能加入论文。
- `hem → hem_beam`、`hem_structure → proposed` 是相同 checkpoint 下的 decode 比较。
- `hem → hem_structure`、`feature_only → proposed` 同时改变特征或 checkpoint，不是纯单因素消融。
- 正式算法对比统一采用 `full`（阶段 2 开启、`linear`）；只有独立
  `benchmark-stability` 可以按控制变量法关闭一个因素。
- DOE 的主效应、预设两两交互、置信区间、诊断数据和程序图已由 `analyze_cie_submission.py` 自动生成；正式DOE若缺图或模型不可估计，后处理必须失败。

## 9. 投稿硬门槛

- [ ] Validation/Main/Stability/DOE/SPBS/Sensitivity/OOD 行数为
  4/2700/1500/300/960/80/729。
- [ ] seed 矩阵完整，shard 无交叠。
- [ ] `error`、`solution_write_error` 全为空。
- [ ] timeout、memlimit、无 incumbent 全部保留。
- [ ] 每个 incumbent 行都有实际 `.sol`，solution_count 与唯一 incumbent 行数相等。
- [ ] 所有 `cie_manufacturing_metrics.json` 的 `invalid_count=0`。
- [ ] checkpoint 与 training seed 匹配；同 campaign 的 LP/模型/ACS/预算/代码一致。
- [ ] 显著性以制造实例为单位。
- [ ] 保存环境、commit、机器、LP/checkpoint/ACS hash、全部 raw、solution、日志和分析。
- [ ] 论文不含 `[TBD]`、`--` 或来自未完成 campaign 的数值。

官方当前采用 Research Data Option C。建议归档环境、冻结资产、raw/combined 结果、`.sol`、分析、日志、断点和表图生成代码，并在数据仓库分配持久标识符；不能共享时写明原因和 data statement。双匿名稿与title page必须分开；使用Codex/ChatGPT辅助稿件准备必须加入官方要求的生成式AI声明，且不得使用生成式AI创建或修改投稿图片或graphical abstract。

## 10. 历史材料

`docs/cie_single_way_commands.md`、`cie_two_way_parallel_commands.md` 与 `cie_current_parallel_commands.md` 是历史或高级运维记录；不得覆盖本文协议。简版索引见 [`docs/cie_experiment_commands.md`](docs/cie_experiment_commands.md)。

从当前机器继续执行时，以 [`docs/cie_submission_runbook_zh.md`](docs/cie_submission_runbook_zh.md) 中的单行命令和验收顺序为准。

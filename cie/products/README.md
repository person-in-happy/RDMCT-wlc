# C&IE 论文包与当前证据状态

> 审计时间：2026-08-01 23:42（Asia/Shanghai）。本目录中的稿件、表格和图只能在正式 campaign、独立验解和统计门槛全部通过后填写；空白或 `[TBD]` 不是结果。

完整协议见 [`../README.md`](../README.md)，从暂停、恢复到投稿的唯一执行入口见 [`../docs/cie_submission_runbook_zh.md`](../docs/cie_submission_runbook_zh.md)。

## 1. 投稿有效进度

严格按当前 `*_repro_v1` 协议，旧 `*_final_v1`、smoke 和 legacy checkpoint 结果均不得并入正式结果。

| 项目 | 投稿目标 | 当前正式有效 | 状态 |
| --- | ---: | ---: | --- |
| 可审计训练模型 | 15 | 0 | HEM、feature-only、Proposed 各 5 个独立 training seeds 待重训 |
| Validation | 4 | 0 | 待运行 |
| Main | 2700 | 0 | 待运行 |
| Stability | 1500 | 0 | 待运行 |
| DOE | 300 | 0 | 待运行 |
| SPBS | 960 | 0 | 待运行 |
| Sensitivity | 80 | 0 | 待运行 |
| OOD | 729 | 0 | 待运行 |

正式 benchmark 合计为 **0/6273**。还需要 720 次 ACS validation 网格求解、65 个 warm starts、全部 incumbent 独立验解、制造指标、实例级统计、效应量、置信区间、双侧配对 Wilcoxon 与 Holm 校正。

## 2. 历史工程结果（不得填入最终论文表）

| 实验 | 工程目标 | 审计快照 | 问题 |
| --- | ---: | ---: | --- |
| Main | 2700 | 880 | campaign 不完整且不属于冻结的投稿协议 |
| OOD | 729 | 674 | 旧模型、跨代码版本；正在补齐的仅是工程 campaign |
| SPBS | 960 | 336 | campaign 不完整且含 1 个 runner error |
| Stability | 1500 | 0 | 未运行 |
| DOE | 300 | 0 | 未运行 |
| Sensitivity | 80 | 0 | 未运行 |
| Validation | 4 | 0 | 未运行 |

当前 `cie_ood_1200s_mem4096_final_v1` 即使补到 729/729，也只能证明断点机制和运行链路可用。它混用了旧 AAAI provenance checkpoint，且 training seed 1--4 的部分结果早于 `run_cie_benchmarks.py` 和 `environments.py` 的最近修改，不能作为同一冻结版本的投稿证据。

## 3. 正式运行前必须先解决

1. 补齐或删去机制声明所依赖的遥测：cut-pool size、accepted cut count、角色覆盖、冗余、callback/fallback 开销、dual bound、root gap、LP iterations、首次解/最佳解/证明时间。
2. 固定 checkpoint 规则。稿件写的是按 validation PDI 选模，但当前训练配置为 `evaluate_freq=0`，协议又固定 `itr_60.pkl`；必须在正式重训前选择“预先固定末轮”或“启用独立 validation 选模”，并同步论文与协议。
3. 冻结代码、LP、训练数据、模型、ACS、环境和 commit 的 hash。冻结后不得修改签名代码或数据生成器。
4. 统一 `RDMCT-A3C` 与稿件算法名 `SA-RLCS`，或在摘要、方法、代码和数据元数据中明确二者关系。

## 4. 论文与投稿包缺口

现有英文稿使用 Elsevier 官方 `elsarticle` class，摘要约 202 词、6 个关键词和 5 条 highlights 的数量/长度当前合规，但仍有 27 个 `TBD`、6 张未完成表和 0 张图。本机尚无可用的 LaTeX 编译工具链。

正式上传前按“官方要求 + 本项目内部完整性门槛”准备：

- 双匿名正文 `manuscript_anonymous.tex/pdf`；独立 title page 应列出与 Editorial Manager 顺序一致的作者、每个单位的完整标准名称/地址/国家及通信信息；
- 3--5 条、每条不超过 85 字符的可编辑 highlights；
- Elsevier declarations tool 生成的利益冲突 `.doc/.docx`；
- CRediT、Funding 和 Data statement；匿名评审稿不得泄露逐作者贡献、完整基金号或身份化链接，完整信息放入不发审稿人的作者材料/投稿字段；数据初投使用匿名链接，最终使用永久标识符（优先 DOI），不能共享则说明原因；
- 生成式 AI 使用声明；不得用生成式 AI 生成或修改投稿图片或 graphical abstract；
- 投稿型 supplement、完整 APA 7 参考文献、术语表和可复现清单；supplement 是本项目因正文承诺而设的内部必需项，不是 C&IE 通用硬性项；
- 平铺的 LaTeX 源文件包、编译 PDF、单独图文件与 `figure_captions.txt`、全体作者批准；cover letter 建议准备，并以正式上传当天 Editorial Manager 字段为准。

摘要除不超过 250 个英文词外，还应独立、事实性地包含目的、主要结果和结论，不含引用，非常用缩写首次定义；关键词须为英文。Graphical abstract 是鼓励项而非硬性项。

官方依据：[C&IE Guide for Authors](https://www.sciencedirect.com/journal/computers-and-industrial-engineering/publish/guide-for-authors)；[Elsevier LaTeX instructions](https://www.elsevier.com/en-gb/researcher/author/policies-and-guidelines/latex-instructions)。正式上传当天应再次核对。

## 5. 最终填表门槛

- 所有正式阶段达到 4/2700/1500/300/960/80/729，且无重复主键；
- `error` 和 `solution_write_error` 为空，timeout、memlimit 和无 incumbent 行不得删除；
- 每个 incumbent 有唯一 `.sol`，独立验解 `invalid_count=0`；
- 七个campaign的 `run_cie_postprocess.ps1` 均显示PASS，并保存精确矩阵审计、实例级bootstrap/效应量/Wilcoxon/Holm；DOE还须有主效应、预设交互、置信区间、诊断数据和程序生成图；
- 15 个模型 provenance 通过默认门禁，正式命令不含 `-AllowLegacyCheckpoints`；
- 模型、LP、ACS、commit 和环境 hash 完整，所有数字可追溯到冻结分析产物；
- 正文没有 `[TBD]`、无来源的 `--` 或人工外推结果；
- 双匿名、声明、数据、补充材料和 LaTeX 源包均通过投稿清单。

完整结果未达到这些门槛前，只能报告工程预检进度，不能声称已经形成最终 C&IE 性能证据。

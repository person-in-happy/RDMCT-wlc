# C&IE 论文包与当前证据状态

> 审计时间：2026-08-02（Asia/Shanghai）。本目录中的正式结果表只能在新campaign、独立验解和统计门槛全部通过后填写；归档单例只作非验证性模型健全性检查，空白或`[TBD]`不是结果。

完整协议见 [`../README.md`](../README.md)，从暂停、恢复到投稿的唯一执行入口见 [`../docs/cie_submission_runbook_zh.md`](../docs/cie_submission_runbook_zh.md)。

当前长任务已统一为可恢复入口：训练按完整epoch恢复，ACS与benchmark按单次求解恢复，warm start按实例复用；中断后必须保持参数不变并原样重跑同一条`run_cie_single.ps1`命令。不要直接运行底层Python或删除`.checkpoints`。

## 1. 投稿有效进度

严格按当前 `*_repro_v1` 协议，旧 `*_final_v1`、smoke 和 legacy checkpoint 结果均不得并入正式结果。

| 项目 | 投稿目标 | 当前正式有效 | 状态 |
| --- | ---: | ---: | --- |
| 完整epoch-60训练候选 | 15 | 15 | HEM、feature-only、Proposed各5/5；冻结manifest已完成并由runner强制消费 |
| Validation | 4 | 4 | 4个incumbent均独立验解通过，提交审计PASS |
| Main | 2700 | 0 | 待运行 |
| Stability | 1500 | 0 | 待运行 |
| DOE | 300 | 0 | 待运行 |
| SPBS | 960 | 0 | 待运行 |
| Sensitivity | 80 | 0 | 待运行 |
| OOD | 729 | 0 | 待运行 |

正式确认性性能矩阵仍为**0/6273**，其benchmark前门槛已全部通过：15模型冻结清单、ACS validation 720/720、全部65个warm starts、81/81个LP的model-evidence、CIE测试59/59以及Validation 4/4独立验解/审计均完成。下一步按执行手册启动Main三队列。

## 2. 历史工程结果（不得填入最终论文表）

| 实验 | 工程目标 | 审计快照 | 问题 |
| --- | ---: | ---: | --- |
| Main | 2700 | 880 | campaign 不完整且不属于冻结的投稿协议 |
| OOD | 729 | 729 | 0 runner error、全部timelimit；旧模型seed来源错误且跨代码版本 |
| SPBS | 960 | 336 | campaign 不完整且含 1 个 runner error |
| Stability | 1500 | 0 | 未运行 |
| DOE | 300 | 0 | 未运行 |
| Sensitivity | 80 | 0 | 未运行 |
| Validation | 4 | 0 | 未运行 |

`cie_ood_1200s_mem4096_final_v1`已经729/729完成。SCIP/ACS各27/27有incumbent，每个学习方法族仅27/135；旧15个`variant.json`的`experiment.seed`均为1，且活动跨代码修改。它只能作为运行链路和大实例困难度诊断，不能进入正式性能表。`timelimit`本身不是无效观测；这里被排除的根因是checkpoint provenance。

## 3. 从当前进度继续

1. 补齐或删去机制声明所依赖的遥测：cut-pool size、accepted cut count、变量角色覆盖、冗余、callback/fallback开销、dual bound、root gap、LP iterations、首次解/最佳解/证明时间。
2. 等当前OOD warm-start结束；若不是9/9且`failures=0`，按执行手册用1800秒命令重试。成功实例会复用。
3. 执行`model-evidence`，完成测试和最终评估commit，再运行`freeze-checkpoints`复核15/15，随后先跑Validation。
4. 冻结代码、LP、训练数据、模型、ACS、环境、训练commit和评估commit的hash。冻结后不得修改签名代码或数据生成器。
5. Validation全部PASS后，按执行手册最多三路进入Main、Stability、DOE、SPBS、Sensitivity、OOD；仓库名保留`RDMCT-A3C`，稿件算法暂名`RDMCT-HPS`，只有完成演员--评论家对照后才主张strict A3C。

## 4. 论文与投稿包缺口

现有英文稿使用Elsevier官方`elsarticle` class，有6个关键词和5条highlights，但仍有32个`TBD`、8张表和0张图。本机尚无可用的LaTeX编译工具链；摘要还缺正式结果，最终再验收250词上限。

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

- 核心正式阶段达到4/2700/1500/300/960/80/729，model-evidence通过且无重复主键；只有声称协同时才要求A2约1100条增量；
- `error` 和 `solution_write_error` 为空，timeout、memlimit 和无 incumbent 行不得删除；
- 每个 incumbent 有唯一 `.sol`，独立验解 `invalid_count=0`；
- 七个campaign的 `run_cie_postprocess.ps1` 均显示PASS，并保存精确矩阵审计、实例级bootstrap/效应量/Wilcoxon/Holm；DOE还须有主效应、预设交互、置信区间、诊断数据和程序生成图；
- runner强制消费冻结manifest，15个模型路径/hash与每行结果一致，正式命令不含`-AllowLegacyCheckpoints`；
- 模型、LP、ACS、commit 和环境 hash 完整，所有数字可追溯到冻结分析产物；
- 正文没有 `[TBD]`、无来源的 `--` 或人工外推结果；
- 双匿名、声明、数据、补充材料和 LaTeX 源包均通过投稿清单。

完整结果未达到这些门槛前，只能报告工程预检进度，不能声称已经形成最终 C&IE 性能证据。

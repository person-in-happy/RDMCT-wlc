# C&IE 投稿产品与证据状态

> 审计快照：2026-08-14 11:47:04（Asia/Shanghai）。实验定义以 [C&IE复现协议](../README.md) 为准，运行和恢复命令以 [投稿执行手册](../docs/cie_submission_runbook_zh.md) 为准。

## 1. 已冻结证据

| 阶段 | 目标 | 状态 | 投稿用途 |
| --- | ---: | --- | --- |
| Validation | 4 | 4/4，独立验解与审计PASS | 模型和求解链验证 |
| Main | 2700 | 2700/2700，独立验解与审计PASS | 七方法标称比较 |
| Stability | 1500 | 1500/1500，独立验解与审计PASS | 两阶段排程机制 |
| DOE | 300 | 300/300，独立验解与审计PASS | 规模、配方和工艺因素 |
| SPBS | 960 | 960/960；728个incumbent全部有效，审计PASS | 初始解主效应 |
| Sensitivity | 80 | 80/80，独立验解与审计PASS | 单因素参数扰动 |
| OOD | 729 | 112/729，seed1/2/3三路运行中 | 分布外评估 |

正式六组benchmark当前为5652/6269；加Validation后为5656/6273，尚缺OOD 617行。历史`*_final_v1`、smoke、legacy checkpoint和筛选单例不得并入正式统计。

## 2. 已进入稿件的主要结论

- RDMCT-HBS在完整2700次标称实验中取得七种方法最低平均PDI（16585.70）和最低平均求解时间（218.32 s），平均PDI相对适配HEM和SCIP分别降低1.41%和1.97%，在所评协议下具有最强平均anytime性能。
- SPBS使incumbent获得率从51.67%提高至100%，并使平均PDI降低26.19%；Holm校正`p`分别为`2.55\times10^{-5}`和`3.46\times10^{-8}`。
- 相对关闭第二阶段，完整两阶段配置使事件重构的路线总等待、最大等待、节拍CV和节拍偏差和分别降低51.91%、68.89%、39.70%和94.05%，四项经Holm校正后均显著。
- DOE显示晶圆数与混流配方构成产生强交互；全部预设加工时间尺度主效应和交互效应的置信区间均跨零。
- Sensitivity的80次运行全部获得并验解可行解；该单方法OFAT只支持预设参数扰动下的可运行性，不用于声称跨方法鲁棒性排序。

## 3. 当前投稿文件

- `rdmct_cie_draft.tex/pdf`：英文双匿名正文工作稿，Elsevier `elsarticle` 模板，摘要246词。
- `rdmct_cie_analysis_focused.tex/pdf`：重新撰写的分析导向英文稿，突出模型逻辑、结果机理和明确优势结论，旧稿未覆盖。
- `rdmct_cie_analysis_focused_zh.tex/pdf`：与分析导向英文稿同步的中文审查稿。
- `manuscript_analysis_focused_anonymous.tex/pdf`：分析导向新稿的独立匿名投稿入口及已编译PDF，不覆盖原匿名稿。
- `highlights_analysis_focused.txt`：分析导向新稿专用英文Highlights，原`highlights.txt`保持不变。
- `submission_metadata_analysis_focused.md`：分析导向新稿专用投稿元数据与待作者确认项。
- `manuscript_versions.md`：旧稿冻结哈希、新稿用途及版本关系。
- `manuscript_anonymous.tex/pdf`：单一来源匿名投稿包装文件；当前PDF已编译，OOD回填后重新冻结。
- `rdmct_cie_draft_zh.tex/pdf`：中文审查稿。
- `rdmct_cie_references.bib`：英文参考文献库。
- `highlights.txt`：5条英文Highlights，每条71--79字符。
- `title_page.tex/pdf`：采用作者提供文稿中的姓名、单位、邮箱和通讯作者信息生成的一页独立标题页。
- `cover_letter_draft.tex/pdf`：一页C&IE投稿信草稿，已写入模型、算法和审计通过的量化贡献。
- `rdmct_cie_supplement.tex/pdf`：匿名补充材料，含实验矩阵、验解口径、物理指标定义、SPBS、Sensitivity和DOE补充证据。
- `submission_metadata.md`：投稿系统元数据及必须由作者确认的缺失信息清单。
- `figure_captions.txt`：正文图和补充图的独立英文图注。
- `Figure_DOE_PDI_effects.png`：正文DOE效应图。
- `Figure_S1_DOE_diagnostics.png`：补充材料诊断图。
- `experiment_audit_zh.md`：正式实验和主张边界审计。

## 4. 尚未闭合的投稿门槛

1. OOD达到729/729后运行`run_cie_postprocess.ps1 -Stage ood`，要求矩阵、独立验解和投稿审计PASS，再把正式结果写入中英文稿。
2. 独立title page已写入作者姓名、单位、通信地址和邮箱；作者仍须确认原文未提供的基金、致谢、ORCID和逐作者CRediT分工。
3. 将匿名数据/代码包上传到不暴露作者身份的评审链接；接受后替换为永久公共归档标识符。
4. title page、cover letter、supplement和figure captions已生成；OOD回填后再冻结最终匿名正文`manuscript_anonymous.tex/pdf`和扁平LaTeX源包。
5. 上传前检查PDF元数据、文件名、致谢、基金号、身份化链接和自引措辞，确保不泄露作者身份。

满足上述门槛表示材料达到可提交状态，不代表期刊必然录用。

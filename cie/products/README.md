# C&IE 投稿产品与证据状态

> 审计快照：2026-08-17 14:58:02（Asia/Shanghai）。实验定义以 [C&IE复现协议](../README.md) 为准，复现命令与验收口径以 [投稿执行手册](../docs/cie_submission_runbook_zh.md) 为准。

## 1. 已冻结证据

| 阶段 | 目标 | 状态 | 投稿用途 |
| --- | ---: | --- | --- |
| Validation | 4 | 4/4，独立验解与审计PASS | 模型和求解链验证 |
| Main | 2700 | 2700/2700，独立验解与审计PASS | 七方法标称比较 |
| Stability | 1500 | 1500/1500，独立验解与审计PASS | 两阶段排程机制 |
| DOE | 300 | 300/300，独立验解与审计PASS | 规模、配方和工艺因素 |
| SPBS | 960 | 960/960；728个incumbent全部有效，审计PASS | 初始解主效应 |
| Sensitivity | 80 | 80/80，独立验解与审计PASS | 单因素参数扰动 |
| OOD | 729 | 729/729；全部为timelimit但均有独立验解有效incumbent，审计PASS | 分布外可行性与性能边界 |

正式六组benchmark为6269/6269；加Validation后为6273/6273。共6041个incumbent全部通过独立验解，`invalid_count=0`，七阶段投稿审计均为`PASS`。历史`*_final_v1`、smoke、legacy checkpoint和筛选单例不得并入正式统计。

## 2. 已进入稿件的主要结论

- RDMCT-HBS在完整2700次标称实验中取得七种方法最低观测平均PDI（16585.70）和最低观测平均求解时间（218.32 s），平均PDI相对适配HEM和SCIP分别降低1.41%和1.97%；相应实例级区间跨零且Holm校正`p=1.0`，故不声称总体统计显著领先。
- 向SCIP提供预计算SPBS incumbent后，定时求解阶段的incumbent获得率从51.67%提高至100%，平均PDI降低26.19%；Holm校正`p`分别为`2.55\times10^{-5}`和`3.46\times10^{-8}`。离线SPBS构造成本不计入该预算。
- 在相同600 s总预算下，相对无精修工作流，完整两阶段工作流所得排程的事件重构路线总等待、最大等待、节拍CV和节拍偏差和分别低51.91%、68.89%、39.70%和94.05%，四项经Holm校正后均显著；因第一阶段预算分别为540 s和600 s，该结果不解释为固定同一第一阶段排程后的纯第二阶段因果效应。
- DOE显示晶圆数与混流配方构成产生强交互；全部预设加工时间尺度主效应和交互效应的置信区间均跨零。
- Sensitivity的80次运行全部获得并验解可行解；该单方法OFAT只支持预设参数扰动下的可运行性，不用于声称跨方法鲁棒性排序。
- OOD的729次运行均触及1200 s上限，但七种方法在九个更大构型上均返回经独立验解的有效incumbent。ACS取得最低平均OOD PDI；RDMCT-HBS与各基线的全局Holm校正差异均不显著，因此OOD证据支持共同求解链的分布外可行性，不支持RDMCT-HBS分布外领先的主张。

## 3. 当前投稿文件

- `rdmct_cie_draft.tex/pdf`：英文双匿名正文工作稿，Elsevier `elsarticle` 模板，摘要246词。
- `rdmct_cie_analysis_focused.tex/pdf`：重新撰写的分析导向英文稿，突出模型逻辑、结果机理和明确优势结论；最终摘要244词，旧稿未覆盖。
- `rdmct_cie_analysis_focused_zh.tex/pdf`：与分析导向英文稿同步的中文审查稿。
- `manuscript_analysis_focused_anonymous.tex/pdf`：分析导向新稿的独立匿名投稿入口及已编译PDF，不覆盖原匿名稿。
- `highlights_analysis_focused.txt`：分析导向新稿专用英文Highlights，原`highlights.txt`保持不变。
- `submission_metadata_analysis_focused.md`：分析导向新稿专用投稿元数据与待作者确认项。
- `manuscript_versions.md`：旧稿冻结哈希、新稿用途及版本关系。
- `manuscript_anonymous.tex/pdf`：保留版匿名投稿包装文件；分析导向新稿另有独立匿名入口。
- `rdmct_cie_draft_zh.tex/pdf`：中文审查稿。
- `rdmct_cie_references.bib`：英文参考文献库。
- `highlights.txt`：5条英文Highlights，每条71--79字符。
- `title_page.tex/pdf`：采用作者提供文稿中的姓名、单位、邮箱和通讯作者信息生成的一页独立标题页。
- `cover_letter_draft.tex/pdf`：一页C&IE投稿信草稿，已写入模型、算法和审计通过的量化贡献。
- `rdmct_cie_supplement.tex/pdf`：匿名补充材料，含实验矩阵、验解口径、物理指标定义、SPBS、Sensitivity和DOE补充证据。
- `CIE_RDMCTHBS_anonymous_source_20260817.zip`：平铺匿名正文源包，已在独立临时目录完成LaTeX/BibTeX全流程编译和身份泄漏检查。
- `CIE_RDMCTHBS_anonymous_supplement_source_20260817.zip`：独立匿名补充材料源包，已完成解压重编译和身份泄漏检查。
- `source_bundle_manifest.md`：两个源包的文件白名单、SHA-256、独立编译与上传角色记录。
- `submission_metadata.md`：投稿系统元数据及必须由作者确认的缺失信息清单。
- `figure_captions.txt`：正文图和补充图的独立英文图注。
- `Figure_DOE_PDI_effects.png`：正文DOE效应图。
- `Figure_S1_DOE_diagnostics.png`：补充材料诊断图。
- `experiment_audit_zh.md`：正式实验和主张边界审计。

## 4. 上传前仍需作者确认的事项

1. 确认基金及基金号、致谢、逐作者CRediT分工和ORCID；无相关内容时也需由作者明确确认。
2. 确认已依据USTB官方网站补入的完整校址，补充通信作者电话，并确认作者顺序、单位、邮箱及通信作者指定。
3. 由全体作者确认原创性、独家投稿和最终版本同意。
4. 将数据/代码包上传到不暴露作者身份的评审链接；接受后替换为永久公共归档标识符。
5. 当前技术稿匿名PDF和扁平LaTeX源包已经冻结并独立编译通过；加入匿名数据/代码评审链接后，按同一白名单重建最终包并再次检查PDF元数据、身份化链接和自引措辞。

满足上述门槛表示材料达到可提交状态，不代表期刊必然录用。

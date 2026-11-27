# Computers & Industrial Engineering 稿件

2026-11-27 中英文稿已同步 JMS 正文中的机械手和腔室术语、公式说明、表 3 与表 6。图 1、2 对齐了 AL，图 5 以 90 mm 宽单栏排成三行两列。(a、b) 为 4 片，(c、d) 为 8 片，(e、f) 为 16 片。六幅子图各自标出总加工时间和工艺目标，35 个实心圆表示已求得排程的目标值。图 6 至 8 采用经验证的排程。图 8 已换用缩短两腔首、次并行加工间隔的 75 片排程，其正文数值保留上一排程的结果。两个版本的证据见审查记录。C&IE 稿保留突出两阶段求解方法的摘要、独立标题页、匿名主稿、单栏连续行号及 APA 作者–年份引文。[JMS 中文正文](../../JMS-version/JMS_Review_CN.tex) · [JMS 英文正文](../../JMS-version/submission/manuscript_body_en.tex)

| 用途 | 文件 |
| --- | --- |
| 英文匿名主稿 | [PDF](rdmct_cie_analysis_focused.pdf) · [LaTeX](rdmct_cie_analysis_focused.tex) · [可独立编译的平铺源包](CIE_anonymous_source_20261126.zip) |
| 中文审阅稿 | [PDF](rdmct_cie_analysis_focused_zh.pdf) · [LaTeX](rdmct_cie_analysis_focused_zh.tex) |
| 独立标题页和作者贡献 | [PDF](title_page.pdf) · [LaTeX](title_page.tex) |
| 投稿栏位用文字 | [英文摘要](abstract_current_en.txt) · [英文 Highlights](highlights_analysis_focused.txt) · [英文图题](figure_captions.txt) |
| 正文所引补充数据 | [108 组阈值记录、训练日志及检查点标识](Supplementary_Data.zip) |
| 来源、核查及待确认事项 | [审查记录](CIE_CURRENT_REVIEW_CN.md) |

英文匿名包装入口为 `manuscript_analysis_focused_anonymous.tex`，中文兼容入口为 `rdmct_cie_draft_zh.tex`。两者各自指向上表相应主稿。编译顺序为 XeLaTeX、Biber、XeLaTeX 两遍。在本目录编译时使用 `figures_current/` 和 `rdmct_cie_current_references.bib`。英文平铺源包内的主文件名为 `manuscript.tex`。

## 历史材料

`rdmct_cie_draft.tex`、`manuscript_anonymous.tex`、旧的补充稿与投稿信草稿、日期为 20260817、20261109、20261111 的压缩包分别对应此前版本。追溯入口见[历史版本与哈希](manuscript_versions.md)。既往实验的运行记录见[执行手册](../docs/cie_submission_runbook_zh.md)。

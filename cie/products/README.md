# C&IE 当前材料入口

当前中文审阅稿为 [rdmct_cie_analysis_focused_zh.tex](rdmct_cie_analysis_focused_zh.tex)（[PDF](rdmct_cie_analysis_focused_zh.pdf)），模型与证据来自迁移时的 `JMS-version/JMS_Review_CN.tex`，迁移快照见[修订记录](../revisions/20261109_jms_alignment/migration_manifest.json)。此稿尚不是已完成的英文投稿稿；JMS 后续修改也不会自动同步。

## 当前文件

| 文件 | 用途 |
|---|---|
| [CIE_CURRENT_REVIEW_CN.md](CIE_CURRENT_REVIEW_CN.md) | 迁移审查、研究缺口、作者确认事项与提交边界 |
| [CIE_CURRENT_EXPERIMENT_COMMANDS.md](../docs/CIE_CURRENT_EXPERIMENT_COMMANDS.md) | 当前联合模型 D 的补强实验与端到端预算协议 |
| `rdmct_cie_draft_zh.tex/pdf` | 当前中文稿的兼容入口 |
| `rdmct_cie_current_references.bib` | 当前中文稿文献库 |
| `abstract_current_en.txt`、`highlights_analysis_focused.txt` | 当前英文摘要和 Highlights 草稿 |
| `title_page.tex/pdf`、`cover_letter_draft.tex/pdf` | 标题页与投稿信草稿，仍须作者确认 |
| `CIE_current_CN_review_source_20261109.zip` | 中文审阅源包，稿件改动后需重建 |

新增实验是否完成，以实际批次、冻结配置及完整验解记录为准；共享实验最新状态查看 [JMS 期刊命令](../../JMS-version/JOURNAL_EXPERIMENT_COMMANDS.md)，避免重复启动。

## 历史资产

以下文件保留原模型与日期归属，不与当前中文稿、新 Highlights 或新标题页混合提交：

- `rdmct_cie_draft.tex/pdf`、`rdmct_cie_analysis_focused.tex/pdf`：旧模型英文稿。
- `manuscript_anonymous.tex/pdf`、`manuscript_analysis_focused_anonymous.tex/pdf`：旧英文匿名包装入口。
- `rdmct_cie_supplement.tex/pdf`、`rdmct_cie_references.bib`、`highlights.txt`、`highlights_analysis_focused_zh.txt`、`figure_captions.txt`：旧模型补充材料、文献与配套文字。
- `CIE_RDMCTHBS_anonymous_source_20260817.zip`、`CIE_RDMCTHBS_anonymous_supplement_source_20260817.zip`：历史匿名源包。
- [旧版本与冻结哈希](manuscript_versions.md)、[源包审计清单](source_bundle_manifest.md)、[历史实验审计](experiment_audit_zh.md)：用于追溯旧稿和冻结证据。

正式提交前须完成英文全文和图内标签同步、作者信息与逐作者贡献确认、数据/代码评审链接、官方作者指南复核及新增实验审查。具体缺口集中维护在 [CIE_CURRENT_REVIEW_CN.md](CIE_CURRENT_REVIEW_CN.md)，不再使用旧双作者元数据页。

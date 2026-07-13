# CIRP CMS 2027 投稿包（第二选择）

本目录是与 INCOM 版本隔离的备选投稿工作区。它不修改 `aaai/`、项目主代码或 `incom2027/`。

## 目录

- `official/`：从 CMS 2027 官网下载的官方 Elsevier/Procedia CIRP LaTeX 模板与投稿指南；
- `paper/`：使用官方 `elsarticle + ecrc` 模板编写的英文初稿；
- `docs/official_requirements.md`：官网要求和日期；
- `docs/missing_experiments_and_content.md`：面向 CIRP 制造系统审稿人的实验缺口；
- `docs/abstract_submission.md`：2026-09-11 前可使用的摘要初稿；
- `reused_from_aaai/`：仅复制原论文、参考文献和流程图，不包含模型、数据或结果大目录。

## 当前论文定位

题目为 *Executable Scheduling of a Dual-Source Rotary Cluster Tool*。CMS 版本重点是制造系统，而不是通用割平面学习：

1. 旋转腔、ATR/VTR、AL、LL 与 PEC 周转的设备级模型；
2. $4\times1$ 与 $2\times2$ 混流下的可执行调度；
3. Gantt 物理一致性和生产利用率；
4. SPBS 初解对生产调度求解的作用。

## 编译

```powershell
cd cirp_cms2027\paper
pdflatex -interaction=nonstopmode -halt-on-error cirp_cms2027_draft.tex
bibtex cirp_cms2027_draft
pdflatex -interaction=nonstopmode -halt-on-error cirp_cms2027_draft.tex
pdflatex -interaction=nonstopmode -halt-on-error cirp_cms2027_draft.tex
```

## 重要的投稿伦理提醒

INCOM 普通全文截止为 2026-11-15，CMS 全文截止为 2026-11-18。两篇初稿共享同一设备问题和部分模型，不能把它们作为两篇独立原创成果同时送审。当前设计是“首选/第二选择”：只提交其中一篇；若要两边都投，必须先把贡献、数据和实验拆成实质不同的研究，并在后投论文中引用和说明前一篇。


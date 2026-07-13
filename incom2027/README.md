# IFAC INCOM 2027 投稿包（首选）

本目录是一套独立投稿工作区，不依赖修改 `aaai/`，也不会把实验输出写回项目根目录。

## 目录

- `official/`：2026-07-13 从官网取得的 INCOM 2027 CFP 与 IFAC LaTeX 官方包；
- `paper/`：按 IFAC 官方类文件编写的英文初稿、参考文献和可编译 PDF；
- `docs/official_requirements.md`：官方要求、日期和核对链接；
- `docs/missing_experiments_and_content.md`：距离可投稿还缺的实验和内容，按优先级列出；
- `reused_from_aaai/`：从原 AAAI 工作区复制的可复用材料，原文件未改动。

## 当前论文定位

题目为 *Structure-Aware Optimization for Dual-Source Rotary Cluster-Tool Scheduling*。INCOM 版本的主线是：

1. 双源产品晶圆/PEC 的物理可执行调度模型；
2. 不改变原问题可行域的 SPBS 初解；
3. 面向难解混流实例的角色感知割平面选择；
4. 以 production scheduling、模型可执行性和求解性能为评价中心。

## 编译

在仓库根目录执行：

```powershell
cd incom2027\paper
pdflatex -interaction=nonstopmode -halt-on-error incom2027_draft.tex
bibtex incom2027_draft
pdflatex -interaction=nonstopmode -halt-on-error incom2027_draft.tex
pdflatex -interaction=nonstopmode -halt-on-error incom2027_draft.tex
```

投稿前必须把作者、单位、邮箱、基金信息和实验结果替换完整，并重新核对页数、字体嵌入及 PDF 大小。


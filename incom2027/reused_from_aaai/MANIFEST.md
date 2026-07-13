# 从 AAAI 工作区复制的材料

复制日期：2026-07-13。所有源文件仍保留在 `aaai/`，本目录中的副本可独立修改，不回写源目录。

| 本目录文件 | 原始位置 | 复用理由 |
| --- | --- | --- |
| `rdmct_aaai27.tex` | `aaai/products/rdmct_aaai27.tex` | 提取模型定义、SPBS、特征定义和已记录验证数据 |
| `rdmct_aaai27.bib` | `aaai/products/rdmct_aaai27.bib` | 已整理的 cluster-tool、SCIP、HEM、ACS 和 MIPLIB 文献 |
| `rdmct_pipeline.pdf` | `aaai/products/rdmct_pipeline.pdf` | 方法流程图与 INCOM 论文主线直接相关 |
| `experiment_harness/run_aaai27_benchmarks.py` | `aaai/code/run_aaai27_benchmarks.py` | 统一运行基线与学习策略 |
| `experiment_harness/combine_aaai27_runs.py` | `aaai/code/combine_aaai27_runs.py` | 合并多训练 seed 与 SCIP seed 结果 |
| `experiment_harness/tune_aaai27_acs.py` | `aaai/code/tune_aaai27_acs.py` | 在 validation 上调 ACS 权重 |
| `experiment_harness/aaai27_benchmark_suites.json` | `aaai/configs/aaai27_benchmark_suites.json` | 固定数据划分和跨家族 suite |

未复制 `aaai/models/`、`aaai/data/` 和 `aaai/results/`，避免数 GB 重复文件和把未完成训练误当成投稿证据。

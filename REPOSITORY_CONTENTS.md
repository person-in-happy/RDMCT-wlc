# 版本控制与本地实验产物

本仓库跟踪模型与实验源码、测试、实验命令、当前论文源文件和交付 PDF、图件及审查记录。当前中文稿源文件为 `JMS-version/JMS_Review_CN.tex`；`JMS/` 是另一份稿件，不自动同步。

## 2026-10-17 清理

清理范围为 LaTeX 构建目录与辅助文件、PDF 页面预览，以及 `JMS-version/figures/temp` 下同时存在 PDF/SVG 的可再生 TIFF。逐文件记录见 `JMS-version/review/cleanup_20261017.json`。图件源数据、PDF/SVG、当前论文、审查报告及修改前源文件均保留。

下列目录或文件仍保留在本地，由 `.gitignore` 排除；它们不是可随意删除的缓存：

- `JMS-version/results/optional_cleaning_*/`：新清洁规则实验的原始输出、冻结协议、求解记录、校验记录和进度。清理时 crossover 的调度器仍在运行，未将其拍成“完整结果”提交。
- `JMS-version/results/joint_model*/`：历史联合模型实验与验证记录。
- `JMS-version/results/frozen_models_20260906/`：冻结 LP；路径和哈希映射仍跟踪在 `JMS-version/results/frozen_model_paths.json`。
- `manuscript_archive/`、审查目录中的 `*.before.pdf`：历史文稿和归档。
- 本地重复导出的 ZIP 包：保留文件，仅避免重复纳入 Git。

因此，**GitHub 克隆不是本地原始证据的完整备份**。复现源码不等于已取得历史实验数据；若需迁移或发布结果，应另行保存完整证据包及哈希，并核对所用模型、检查点、预算和验解结果。不要为了缩小仓库删除原始解、冻结 LP 或检查点，也不要在活动实验期间改动其文件。

已被 Git 跟踪的历史证据不因新增忽略规则而自动移除。此次提交仅包括当前 JMS-version 研究文件、已核对的模型/指标/绘图实现与测试，以及明确的编译、浏览器缓存和预览目录删除。其他项目和历史交付包的原有改动、删除仍留在本地工作区，不随此次提交发布。清理清单只记录此次实际删除的可再生产物，不把此前删除归为本次清理。

后续实验顺序和前台并行命令见 `JMS-version/REVALIDATION_COMMANDS_20261016.md`。实验结束必须检查覆盖和验证记录；超时无 incumbent 不是不可行性证明。

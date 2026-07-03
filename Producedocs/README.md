# Producedocs

这个目录用于维护当前项目的论文说明、运行说明、专利交底书，以及 Markdown 到 docx 的导出脚本。

## 当前文档语义

本目录下所有文档都应与当前代码中的**端到端全流程 MIP**保持一致。文档描述必须覆盖：

- 产品 wafer：`LP -> ATR -> AL -> ATR -> LLupper -> VTR -> CH -> VTR -> LLlower -> ATR -> LP`
- PEC wafer：`PEC storage -> VTR -> CH -> VTR -> PEC storage`
- `AL` 单槽位约束
- `LLupper` / `LLlower` 双槽位容量约束
- `ATR` / `VTR` 操作互斥
- `CH2` / `CH3` 的 `4x1` 与 `2x2` 排产语义
- `4x1` 前/后两组可达槽位的先装后卸约束
- PEC wafer 的循环复用约束

## 目录内容

- `docs/`
  作用：存放 Markdown 源文档和导出的 docx

- `docs/sf3_ct_4x1_problem_description.md`
  作用：整理两篇四槽 PM / 四指机械手文献中的设备说明、问题描述、稳态 LP 建模方法，以及可直接交给 AI 生成文献型 MIP/LP 的提示词

- `docs/技术交底书.docx`
  作用：原始技术交底书草稿，保留以便追溯，不再直接编辑。

- `docs/技术交底书_项目逻辑与创新点梳理.md`
  作用：当前可编辑的技术交底书重构底稿；先阐明双源混流全流程调度主发明，再将学习型割平面选择作为可选的求解加速方案。

- `docs/技术交底书_项目逻辑与创新点梳理.docx`
  作用：上述 Markdown 导出的交付版，可供发明人和专利代理人审阅。

## 使用方法

导出专利交底书：

```powershell
pandoc Producedocs\docs\技术交底书_项目逻辑与创新点梳理.md `
  -o Producedocs\docs\技术交底书_项目逻辑与创新点梳理.docx `
  --reference-doc=Producedocs\docs\技术交底书.docx
```

## 维护约定

1. 若修改了 `docs/` 下的 Markdown，请同步重新导出 docx。
2. 若修改了 `petri_mip_generator.py` 的建模语义，请同步检查运行说明、方法章节、创新点与专利交底书。
3. 文档里如果提到“聚合前端时间、未显式调度 ATR/AL/LL/VTR”、或把 `4x1` 继续写成“单一抽象槽位”，说明该文档已经过时，需要更新。
4. 正式递交前应由发明人确认设备动作和工艺事实，并由专利代理人补齐现有技术来源、实施例数据和附图。

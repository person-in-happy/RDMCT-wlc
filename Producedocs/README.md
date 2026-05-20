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

- `template_patent.docx`
  作用：运行说明和专利交底书导出的模板

- `docx_markdown_renderer.py`
  作用：Markdown 渲染为 docx 的公共工具

- `generate_run_guide_docx.py`
  作用：将 `docs/how_to_run_and_get_final_mip_solution.md` 导出为 docx

- `generate_patent_disclosure_docx.py`
  作用：将 `docs/patent_disclosure_dual_source_rotary_a3c_beam_20260329.md` 导出为 docx

## 使用方法

导出运行说明：

```powershell
python Producedocs\generate_run_guide_docx.py
```

导出专利交底书：

```powershell
python Producedocs\generate_patent_disclosure_docx.py
```

## 维护约定

1. 若修改了 `docs/` 下的 Markdown，请同步重新导出 docx。
2. 若修改了 `petri_mip_generator.py` 的建模语义，请同步检查运行说明、方法章节、创新点与专利交底书。
3. 文档里如果提到“聚合前端时间、未显式调度 ATR/AL/LL/VTR”、或把 `4x1` 继续写成“单一抽象槽位”，说明该文档已经过时，需要更新。

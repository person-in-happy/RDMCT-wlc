# Producedocs

这个目录用于集中存放与项目交付产出相关、但不属于核心训练和求解代码的文档材料。

当前保留的内容包括：
- 运行说明文档
- MIP 建模说明文档
- 论文方法与创新点草稿
- 专利交底书
- 文档生成脚本
- 专利附图素材

当前结构：
- `docs/`：Markdown 与导出的 Docx 文档
- `patent_assets/`：专利示意图和引用素材
- `docx_markdown_renderer.py`：公共 Markdown -> Docx 渲染器
- `generate_run_guide_docx.py`：运行说明导出脚本
- `generate_patent_disclosure_docx.py`：专利交底书导出脚本
- `template_patent.docx`：默认文档模板

本目录已经清理掉无对应源文件的旧专利正文脚本和旧版成稿，只保留当前仍在使用的一套文档与导出入口。

项目核心代码仍位于仓库根目录，例如：
- `petri_mip_generator.py`
- `parallel_reinforce_algorithm.py`
- `run_petri_a3c_beam.py`
- `run_ablation_experiments.py`
- `petri_gantt.py`

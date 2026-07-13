# AAAI-27 工作区：从零开始

所有 AAAI-27 相关代码、配置、数据、模型、结果、论文和说明都在本目录内。

第一次使用，只需要在仓库根目录依次运行：

```powershell
.\aaai\run_aaai.ps1 -Stage check
.\aaai\run_aaai.ps1 -Stage quick
```

## GPU execution

After installing CUDA-enabled PyTorch, run `check` before any long experiment. Learning stages run on `cuda:0` and fail fast instead of silently falling back to CPU:

```powershell
.\aaai\run_aaai.ps1 -Stage check
.\aaai\run_aaai.ps1 -Stage train-hem -Seeds "1,2,3" -GpuDevice cuda:0
```

`train-hem`, `train-feature-only`, `train-proposed`, `benchmark`, and `benchmark-all` use GPU. `generate-data`, `quick`, `tune-acs`, SCIP Default, and Adaptive Cut Selection remain CPU workloads because SCIP does not solve MILPs on CUDA.

若这两步成功，再阅读：

[`docs/aaai27_experiment_and_submission_guide.md`](docs/aaai27_experiment_and_submission_guide.md)

目录说明：

- `code/`：实验、数据生成和画图代码；
- `configs/`：训练、测试和数据清单；
- `data/`：本流程生成或放入的全部实验实例；
- `models/`：HEM 和本文方法的训练输出；
- `results/`：快速测试、ACS 调参和正式结果；
- `docs/`：零基础操作手册、修改记录和论文自审；
- `products/`：AAAI 官方模板、LaTeX、PDF、checklist 和投稿压缩包。

不要把 `quick_demo` 的结果写进论文；它只证明软件可以运行。

论文文件：

- 英文 LaTeX：[`products/rdmct_aaai27.tex`](products/rdmct_aaai27.tex)
- 英文编译稿：[`products/rdmct_aaai27.pdf`](products/rdmct_aaai27.pdf)
- 中文阅读版：[`products/rdmct_aaai27_zh.md`](products/rdmct_aaai27_zh.md)
- 中文 Word 版：[`products/rdmct_aaai27_zh.docx`](products/rdmct_aaai27_zh.docx)
- 往届 AAAI 写作分析：[`docs/accepted_aaai_writing_analysis.md`](docs/accepted_aaai_writing_analysis.md)

正式多训练种子汇总使用：

```powershell
.\aaai\run_aaai.ps1 -Stage benchmark-all -Seeds "1,2,3,4,5" -TimeLimit 600 -GpuDevice cuda:0
```

# RDMCT-A3C：双源混流半导体组合设备调度

本项目面向双源、混流半导体组合设备的端到端调度，使用 SCIP 建立和求解 MIP，并研究强化学习割选择、结构感知重排与 SPBS warm start。

当前模型覆盖产品晶圆与 PEC 晶圆的完整流转、ATR/VTR/AL/Load Lock/CH2/CH3 资源约束、`4x1` 与 `2x2` 混合工艺、PEC 循环复用和显式 cleaning 作业。

主优化目标是：

```text
min c_max
```

`c_max` 是最后一片产品晶圆完成全流程并返回 LP 的时间。吞吐量按 `3600 × 产品晶圆数 / c_max` 计算。

## 从这里开始

文档按用途分成三个入口：

- [完整运行指南](Producedocs/docs/how_to_run_and_get_final_mip_solution.md)：术语、安装、参数、单实例训练/测试、消融和故障排查。
- [C&IE 投稿级实验入口](cie/README.md)：冻结协议、全部 campaign、统计口径、精确行数和投稿验收。
- [C&IE 当前证据状态](cie/products/README.md)：仓库中已有结果能否用于论文。

`cie/docs/` 中的单路、两路和并行清单是历史运行记录或高级运维材料；正式实验以 [`cie/README.md`](cie/README.md) 为唯一协议。

## 10 分钟 CPU smoke

该 smoke 只验证：

```text
生成小实例 → SCIP 求解 → 保存 .sol → 独立验解 → 制造指标 → 实例级统计
```

它不训练模型，也不能形成论文结论。首次安装依赖的时间不计入 10 分钟。

### 1. 准备环境

最低 Python 版本为 3.10。当前仓库已在 Python 3.13、PySCIPOpt 6.1 环境完成自检；这只是已验证快照，不是唯一可用组合。

```powershell
Set-Location <你的路径>\RDMCT-A3C
python -m venv .venv
Set-ExecutionPolicy -Scope Process Bypass
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

若 `pyscipopt` 安装失败，需要先安装 SCIP，或使用 conda-forge 提供的 PySCIPOpt：

```powershell
conda install -c conda-forge pyscipopt scipy
```

### 2. 自检

```powershell
.\cie\run_cie_single.ps1 -Stage check -LogId cie_check
```

预期：Python、NumPy、PyTorch、PySCIPOpt、SciPy 均可导入，所有 C&IE 脚本的 `--help` 能解析，命令退出码为 0。日志位于：

```text
cie/results/logs/cie_check/
```

### 3. 运行 smoke

```powershell
.\cie\run_cie_single.ps1 -Stage smoke -LogId cie_smoke
```

结果位于：

```text
cie/results/smoke/<时间戳>/
├── runs/
├── solutions/
└── analysis/
```

验收标准：

- `runs/` 中存在 raw CSV、summary CSV、JSON 和 Markdown；
- `solutions/` 中至少有一个 SCIP `.sol`；
- raw 中 `error`、`solution_write_error` 为空；
- `analysis/cie_manufacturing_metrics.json` 的 `invalid_count` 为 0。

## GPU 何时需要

实例生成、SCIP 默认求解、SPBS warm start 和统计分析可以在 CPU 上运行。训练 HEM/feature-only/Proposed 以及正式评测学习策略时需要 CUDA；配置写为 `cuda:0` 而 CUDA 不可用时会报错，不会自动回退。

先按本机驱动安装兼容的 CUDA PyTorch，再检查：

```powershell
python -c "import torch; print('torch', torch.__version__); print('cuda', torch.cuda.is_available()); print('device', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'CPU')"
```

仓库附带的是迁移 checkpoint，只可用于功能诊断。若尚未重训当前 C&IE 模型，可显式运行非论文 GPU smoke：

```powershell
.\cie\run_cie_single.ps1 -Stage gpu-smoke -GpuDevice cuda:0 -AllowLegacyCheckpoints -LogId cie_gpu_smoke_legacy
```

正式 Main/OOD 默认拒绝来源不可审计或训练种子不一致的旧 checkpoint。先按 [C&IE 入口](cie/README.md) 执行 `train-all`。

## `--chamber_idle_penalty` 的真实含义

当前版本保留该参数只是为了兼容旧命令、旧配置和 checkpoint 元数据。

- 它不进入当前 LP 主目标；
- 它不进入当前默认 `schedule_stability` 表达式；
- 改成 0、`1e-4` 或更大值不会产生旧文档描述的等待加权效果；
- 不应把它作为论文敏感性因素。

真正的排程紧凑化由词典序第二阶段控制，关键配置是：

- `lexicographic_schedule_stability`；
- `lexicographic_stability_time_limit`；
- `schedule_stability_mode`；
- linear 模式下的 `schedule_linear_*_weight` 和等待上限。

当前所有 Petri 训练、评估和在线测试配置都显式采用
`lexicographic_schedule_stability=true` 与
`schedule_stability_mode=linear`，并给第二阶段非零时间预算。正式算法优势
对比也固定使用这一完整配置；两个因素的作用只在独立的
`benchmark-stability` 控制变量实验中考察，不能在算法对比组里随意关闭。

完整公式和配置示例见[完整运行指南](Producedocs/docs/how_to_run_and_get_final_mip_solution.md#chamber_idle_penalty-为什么改了没有效果)。

## quick 不等于投稿实验

根目录的 quick、`latest`、一键生成并求解入口只用于调试。以下结果不能直接用于 C&IE：

- 单实例或单随机种子；
- 用 `latest` 自动选择 checkpoint；
- 训练集、验证集和测试集重叠；
- 不同方法使用不同 LP、时限、内存、warm start 或停止条件；
- 删除 timeout、失败或无 incumbent 的记录；
- 从多次运行中只挑最好值；
- 混合不同 commit、300/600 秒或 2048/4096 MB 的结果。

正式实验必须冻结 LP、配置、ACS、checkpoint 和 campaign，区分 training seed 与 solver seed，并保留全部 raw 行与 `.sol`。

## 主要文件

| 路径 | 用途 |
| --- | --- |
| `petri_mip_generator.py` | 生成端到端 Petri/MIP 实例 |
| `petri_warm_start.py` | 生成和校验 SPBS warm start |
| `parallel_reinforce_algorithm.py` | 训练和测试割选择策略 |
| `run_petri_a3c_beam.py` | 生成新实例并运行单实例学习策略测试 |
| `run_ablation_experiments.py` | 四方法公平消融 |
| `petri_gantt.py` | 全流程、腔体和资源甘特图 |
| `configs/` | quick、训练和结构实验配置 |
| `cie/` | C&IE 冻结实例、模型、runner、结果和论文包 |
| `generated_instances/` | 一般流程生成的 LP、说明和 warm start |
| `data/` | 一般流程训练日志与 checkpoint |

## 背景文档

- [设备与问题描述](Producedocs/docs/sf3_ct_4x1_problem_description.md)
- [逐晶圆端到端 MIP](Producedocs/docs/per_wafer_path_mip.md)
- [结构感知训练与消融协议](Producedocs/docs/a3c_structure_ablation.md)
- [完整运行指南](Producedocs/docs/how_to_run_and_get_final_mip_solution.md)
- [C&IE 投稿级实验入口](cie/README.md)

## 复现底线

- 所有命令默认从仓库根目录执行；
- 正式评测复用冻结 LP，不让 wrapper 临时重建实例；
- 修改工艺时间、驻留上限、PEC 或 cleaning 后，重新生成 LP 和与其 SHA-256 匹配的 warm start；
- 保存 Git commit、环境清单、配置、manifest、LP/checkpoint/ACS hash、raw CSV/JSON、`.sol`、日志和分析报告；
- 仓库已有结果不代表正式 campaign 已完成，以 [C&IE 当前证据状态](cie/products/README.md) 为准。

## License

本项目采用 [MIT License](LICENSE)。

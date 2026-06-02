# 双源混流半导体组合设备调度代码运行说明

本文档根据当前代码版本重新整理，适用于以 `petri_mip_generator.py` 为核心的端到端全流程 MIP、强化学习 cut selection、A3C+Beam 测试、消融实验和甘特图生成流程。

当前代码已经显式建模：

- 产品晶圆路径：`LP -> ATR -> AL -> ATR -> LLupper -> VTR -> CH -> VTR -> LLlower -> ATR -> LP`
- PEC wafer 路径：`PEC storage -> VTR -> CH -> VTR -> PEC storage`
- 两个旋转腔：`CH2`、`CH3`
- 两种工艺模式：`4x1` 和 `2x2`
- `ATR`、`AL`、`LLupper`、`LLlower`、`VTR` 的资源互斥或容量限制
- PEC wafer 的 token 复用约束
- 4x1 前后侧位的真实装卸顺序
- 2x2 的 head、cycle、bridge、tail 链式结构
- 按加工次数触发的纯 PEC cleaning 批次
- 模块驻留时间和机械手动作驻留时间上限

## 1. 运行前准备

### 1.1 进入项目目录

```powershell
cd G:\git\L2O-HEM-Torch
```

### 1.2 安装依赖

建议使用 conda 或 venv 创建独立环境。当前 `requirements.txt` 包含：

```powershell
python -m pip install -r requirements.txt
```

其中 `pyscipopt` 依赖本机可用的 SCIP 环境。如果执行脚本时报错 `PySCIPOpt is required but not installed`，需要先安装 SCIP，再安装 PySCIPOpt，例如：

```powershell
conda install -c conda-forge pyscipopt
```

或：

```powershell
python -m pip install pyscipopt
```

GPU 不是必需项；若没有 CUDA，测试和训练会回退到 CPU，但训练速度会明显变慢。

### 1.3 主要脚本用途

| 脚本 | 用途 | 主要输出 |
| --- | --- | --- |
| `petri_mip_generator.py` | 生成双源混流全流程 MIP 实例 | `.lp`、`_model.md` |
| `parallel_reinforce_algorithm.py` | 训练或测试 cut selection 策略 | `params.pkl`、`progress.csv`、solution json |
| `run_petri_a3c_beam.py` | 生成实例并调用训练好的模型测试 A3C+Beam | runtime config、solution json、甘特图 |
| `run_ablation_experiments.py` | 对比默认 SCIP、A3C、Beam、A3C+Beam | `.json`、`.csv`、`.md`、对比图、甘特图 |
| `petri_gantt.py` | 根据求解结果生成甘特图 | `.svg`、`index.html` |
| `plot_progress_curves.py` | 根据 `progress.csv` 绘制训练收敛曲线 | `convergence_curves.svg` |
| `stitch_progress_runs.py` | 拼接多次续训的 `progress.csv` | stitched csv |

## 2. 推荐目录约定

建议统一使用以下目录，便于训练和测试脚本互相找到文件：

```text
generated_instances/MIP       MIP 实例和模型说明
data                          训练日志、checkpoint、progress.csv
petri_transfer_use_hrl_*      测试输出和 solution json
ablation_results              消融实验结果
Producedocs/docs              说明文档
```

当前 `configs/petri_mip_test_config.json` 中的默认实例目录是：

```json
"instance_file_path": "generated_instances/MIP"
```

因此，除非有特殊需要，建议把新生成的 `.lp` 文件放在 `generated_instances/MIP` 下。

## 3. 生成 MIP 实例

### 3.1 生成一个推荐测试实例

```powershell
python petri_mip_generator.py   --output_dir generated_instances/MIP   --instance_name mip_clean.lp  --num_batches 16  --num_pm 2  --num_steps 13  --process_mode mixed  --mode_4x1_wafers 25  --mode_2x2_wafers 15  --pec_pool_size 8  --pm_rotation_time_180 2  --pair_transfer_time 4  --atr_transfer_time 3  --atr_return_time 3  --aligner_time 20   --llupper_time 30  --lllower_time 25  --full_process_time 80   --mix_boundary_process_time 30  --mix_internal_process_time 30   --cleaning_interval 10  --cleaning_process_time 60  --max_module_residency_time 80  --max_robot_residency_time 80  --pm_balance_penalty 0.01
```

生成文件会自动带日期后缀，例如在 `2026-05-08` 运行时，输出类似：

```text
generated_instances/MIP/mip_batch10_cleaning_20260508.lp
generated_instances/MIP/mip_batch10_cleaning_20260508_model.md
```

训练、测试和画图时应使用实际生成出的带日期文件名。

### 3.2 小规模连通性实例

第一次验证环境时，不建议直接跑大实例。可先生成小规模实例：

```powershell
python petri_mip_generator.py ^
  --output_dir generated_instances/MIP ^
  --instance_name mip_small_check.lp ^
  --process_mode mixed ^
  --mode_4x1_wafers 4 ^
  --mode_2x2_wafers 2 ^
  --pec_pool_size 8 ^
  --cleaning_interval 10
```

### 3.3 配置工艺模式

`--process_mode` 用来选择本次实例的工艺模式策略：

- `4x1`：全部产品晶圆只跑 `4x1`
- `2x2`：全部产品晶圆只跑 `2x2`
- `mixed` / `both`：按 `--mode_4x1_wafers` 和 `--mode_2x2_wafers` 数量混跑
- `custom`：完全按 wafer 级配置生成
- `auto`：默认兼容模式；有 `--mode_sequence` 时按序列，否则按两类数量生成

只跑 `4x1`：

```powershell
python petri_mip_generator.py ^
  --output_dir generated_instances/MIP ^
  --instance_name mip_4x1_only.lp ^
  --process_mode 4x1 ^
  --total_wafers 20 ^
  --pec_pool_size 8
```

只跑 `2x2`：

```powershell
python petri_mip_generator.py ^
  --output_dir generated_instances/MIP ^
  --instance_name mip_2x2_only.lp ^
  --process_mode 2x2 ^
  --total_wafers 20 ^
  --pec_pool_size 8
```

按数量混跑：

```powershell
python petri_mip_generator.py ^
  --output_dir generated_instances/MIP ^
  --instance_name mip_mixed_counts.lp ^
  --process_mode mixed ^
  --mode_4x1_wafers 12 ^
  --mode_2x2_wafers 8 ^
  --pec_pool_size 8
```

如果每片产品晶圆的模式已知，可以用 `--mode_sequence` 指定完整序列。模式支持 `4x1`、`2x2`，也支持简单别名 `full`、`mix`、`4`、`2`。

```powershell
python petri_mip_generator.py ^
  --output_dir generated_instances/MIP ^
  --instance_name mip_sequence_case.lp ^
  --total_wafers 8 ^
  --process_mode custom ^
  --mode_sequence "4x1,4x1,4x1,2x2,2x2,2x2,2x2,2x2" ^
  --pec_pool_size 8
```

也可以用 `--wafer_mode_map` 只覆盖指定编号的晶圆。下面的命令表示共有 8 片产品晶圆，默认跑 `4x1`，其中 `W3` 和 `W7` 改跑 `2x2`：

```powershell
python petri_mip_generator.py ^
  --output_dir generated_instances/MIP ^
  --instance_name mip_wafer_map_case.lp ^
  --process_mode custom ^
  --total_wafers 8 ^
  --default_wafer_mode 4x1 ^
  --wafer_mode_map "W3:2x2,W7=2x2" ^
  --pec_pool_size 8
```

注意：`--mode_sequence` 和 `--wafer_mode_map` 是 wafer 级配置，优先级高于数量参数；若给了 `--total_wafers`，解析出的产品晶圆数量必须与它一致。

### 3.4 当前关键参数说明

| 参数 | 含义 | 当前限制或默认语义 |
| --- | --- | --- |
| `--num_pm` | 旋转腔数量 | 当前设备固定为 `2`，对应 `CH2` 和 `CH3` |
| `--batch_size` | 旋转腔槽位数 | 固定为 `4` |
| `--process_mode` | 工艺模式策略 | `4x1`、`2x2`、`mixed`、`custom` 或 `auto` |
| `--mode_4x1_wafers` | 执行 4x1 的产品晶圆数 | 可为奇数，尾片自动与 PEC 组成 PW 对 |
| `--mode_2x2_wafers` | 执行 2x2 的产品晶圆数 | 可为奇数，尾片自动与 PEC 组成 PW 对 |
| `--mode_sequence` | wafer 级完整模式序列 | 例如 `4x1,2x2,4x1`；优先级高于数量参数 |
| `--wafer_mode_map` | wafer 编号模式覆盖 | 例如 `W3:2x2,W7=4x1`；可配合 `--default_wafer_mode` 使用 |
| `--default_wafer_mode` | 未覆盖 wafer 的默认模式 | 常用于 `--process_mode custom --wafer_mode_map ...` |
| `--pec_pool_size` | 可复用 PEC wafer 数 | 必须不超过 `pec_storage_slots=10`，且至少为 `4*num_pm=8`，并能被 `num_pm` 整除 |
| `--cleaning_interval` | 每个腔体连续加工多少次后插入 cleaning | `0` 表示关闭 cleaning 约束，默认 `10` |
| `--cleaning_process_time` | cleaning 工艺时间 | 若为 `0`，代码使用 `2*full_process_time` |
| `--max_module_residency_time` | 模块驻留时间上限 | 用于 AL、LL、PM 等模块 |
| `--max_robot_residency_time` | 机械手动作驻留时间上限 | 用于 ATR、VTR、PEC 搬运动作 |
| `--num_batches` | 兼容参数 | 当前 4x1 批次数上界由产品 PW 对数量自动推导；该参数仍需为正数 |

## 4. 训练 cut selection 模型

### 4.1 训练前检查配置

训练默认读取：

```text
configs/petri_mip_test_config.json
```

请确认其中的实例目录和训练规模符合本次实验：

```json
"env": {
  "instance_file_path": "generated_instances/MIP",
  "scip_time_limit": 300,
  "single_instance_file": "mip_clean_20260508.lp"
}
```

首次训练时，还建议把 `experiment.base_log_dir` 设为普通输出根目录，例如：

```json
"experiment": {
  "base_log_dir": "data"
},
"start_epoch": 0
```

不要让 `base_log_dir` 指向一个已经不存在的历史实验目录。当前训练代码会尝试在 `base_log_dir` 中查找 `params.pkl`，如果该目录不存在，可能会在正式训练前报错。只有续训时，才把 `base_log_dir` 改为某个真实存在、且包含 `params.pkl` 的旧实验目录。

当前训练中，若使用 `--reward_type solving_time`，求解时限主要由配置文件里的 `env.scip_time_limit` 控制。命令行的 `--time_limit` 保留为兼容参数，不应作为唯一的时限设置来源。

### 4.2 对已生成实例进行训练

把命令中的实例名替换为第 3 节实际生成的 `.lp` 文件名：

```powershell
python parallel_reinforce_algorithm.py  --config_file configs/petri_mip_test_config.json  --train_type train   --single_instance_file mip_clean_20260508.lp  --sel_cuts_percent 0.2  --reward_type solving_time  --baseline_type simple  --policy_type with_token  --use_cutsel_percent_policy True  --seed 1  --scip_seed 1  --time_limit 300  --instance_type petri_transfer
```

训练输出目录形如：

```text
data/petri_mip_rl_beam_mip_batch10_cleaning_20260508.lp_petri_transfer/
  petri_mip_rl_beam_mip_batch10_cleaning_20260508.lp_petri_transfer_<timestamp>--s-<seed>/
    params.pkl
    itr_*.pkl
    progress.csv
    variant.json
```

后续测试时，`--test_model_path` 应指向其中的 `params.pkl`，也可以指向某个 `itr_<epoch>.pkl`。

### 4.3 训练时自动生成实例

`parallel_reinforce_algorithm.py` 也可以在训练开始时自动调用 MIP 生成器。该路径使用 `petri_*` 参数：

```powershell
python parallel_reinforce_algorithm.py ^
  --config_file configs/petri_mip_test_config.json ^
  --train_type train ^
  --generate_petri_instance True ^
  --petri_instance_dir generated_instances/MIP ^
  --petri_instance_name mip_auto_train.lp ^
  --petri_batches 10 ^
  --petri_num_pm 2 ^
  --petri_num_steps 13 ^
  --petri_process_mode mixed ^
  --petri_4x1_wafers 10 ^
  --petri_2x2_wafers 10 ^
  --petri_pec_pool_size 8 ^
  --single_instance_file all ^
  --sel_cuts_percent 0.2 ^
  --reward_type solving_time ^
  --baseline_type simple ^
  --policy_type with_token ^
  --use_cutsel_percent_policy True ^
  --seed 1 ^
  --scip_seed 1 ^
  --instance_type petri_transfer
```

注意：当前训练入口的自动生成参数尚未暴露 `cleaning_process_time`、`max_module_residency_time` 等高级参数，会使用 `PetriMIPConfig` 中的默认值。若要自定义 cleaning 时间或驻留时间，请先用 `petri_mip_generator.py` 手动生成 `.lp`，再按 4.2 训练。

### 4.4 续训

若训练中断，先找到上一次包含 `params.pkl` 的实验目录，然后修改 `configs/petri_mip_test_config.json`：

```json
"experiment": {
  "base_log_dir": "data/.../上一次实验目录"
},
"start_epoch": 8,
"algorithm": {
  "num_epochs": 20
}
```

含义是：从已经保存的 `params.pkl` 载入模型权重，从第 `8` 个 epoch 继续训练，直到总 epoch 数达到 `20`。

续训时建议保持以下命令行参数不变：

```text
--single_instance_file
--instance_type
--seed
--scip_seed
--reward_type
--baseline_type
--policy_type
--use_cutsel_percent_policy
```

当前续训机制主要恢复模型权重和 normalize 统计量，不完整恢复 optimizer 与 lr scheduler 的内部状态，因此属于“加载上次模型继续训练”，不是严格意义上的全状态断点恢复。

## 5. 绘制训练收敛曲线

训练后通常会得到：

```text
data/.../progress.csv
```

若直接绘制最近一次训练记录：

```powershell
python plot_progress_curves.py
```

输出默认保存在对应实验目录：

```text
convergence_curves.svg
```

也可以显式指定输入和输出：

```powershell
python plot_progress_curves.py ^
  --progress_csv data\YOUR_RUN\YOUR_EXP\progress.csv ^
  --output Producedocs\docs\convergence_curves_example.svg ^
  --title "Training Convergence Dashboard" ^
  --subtitle "Petri-transfer training run" ^
  --hide_source_path
```

如果一次实验由多段续训组成，可先拼接：

```powershell
python stitch_progress_runs.py ^
  --runs data\RUN_1\EXP_1 data\RUN_2\EXP_2 ^
  --output data\stitched_progress.csv
```

再绘图：

```powershell
python plot_progress_curves.py ^
  --progress_csv data\stitched_progress.csv ^
  --output data\stitched_convergence.svg
```

## 6. 使用训练好的模型测试 A3C+Beam

### 6.1 一键生成实例并测试

`run_petri_a3c_beam.py` 会先生成新的 MIP 实例和 runtime config，然后调用 `parallel_reinforce_algorithm.py --train_type test`。

```powershell
python run_petri_a3c_beam.py ^
  --config_file configs/petri_mip_test_config.json ^
  --test_model_path data\YOUR_RUN\YOUR_EXP\params.pkl ^
  --instance_dir generated_instances/MIP ^
  --instance_name mip_test_cleaning.lp ^
  --num_batches 10 ^
  --num_pm 2 ^
  --num_steps 13 ^
  --process_mode mixed ^
  --mode_4x1_wafers 10 ^
  --mode_2x2_wafers 10 ^
  --pec_pool_size 8 ^
  --sel_cuts_percent 0.2 ^
  --policy_type with_token ^
  --use_cutsel_percent_policy True ^
  --test_decode_type beam_search ^
  --seed 1 ^
  --scip_seed 1 ^
  --instance_type petri_transfer
```

重要注意事项：

- `--test_model_path` 必须是真实存在的 `params.pkl` 或 `itr_*.pkl`。
- `run_petri_a3c_beam.py` 当前未暴露 cleaning 高级参数，使用 MIP 配置默认值。
- 脚本默认参数中的 `pec_pool_size=40` 不适合当前设备约束，运行时务必显式传入 `--pec_pool_size 8` 或 `10`。

测试结果通常保存到：

```text
petri_transfer_use_hrl_Trueheuristics_cutsel/
  seed_<seed>_model_<model>_RL_max_cuts_root_<ratio>_solutions_<date>.json
```

测试脚本会尝试自动生成甘特图，输出目录通常为同名 `_gantt` 目录。

### 6.2 对已有实例直接测试

若不想重新生成实例，可先确认 `configs/petri_mip_test_config.json` 中：

```json
"test_kwargs": {
  "test_instance_path": "generated_instances/MIP",
  "test_model_path": "data/YOUR_RUN/YOUR_EXP/params.pkl"
}
```

然后运行：

```powershell
python parallel_reinforce_algorithm.py  --config_file configs/petri_mip_test_config.json  --train_type test  --single_instance_file mip_clean_20260508.lp  --sel_cuts_percent 0.2  --policy_type with_token  --use_cutsel_percent_policy True  --test_decode_type beam_search  --seed 1  --scip_seed 1  --instance_type petri_transfer
```

## 7. 运行消融实验

消融实验会对比四类方法：

- `solver_only`：默认 SCIP
- `beam_only`：启发式 Beam
- `a3c_only`：A3C 策略
- `a3c_beam`：A3C + Beam

有训练模型时：

```powershell
python run_ablation_experiments.py   --config_file configs/petri_mip_test_config.json   --test_model_path data\mip_rl_beam_clean_20260508.lp_transfer\mip_rl_beam_clean_20260508.lp_transfer_2026_05_08_11_01_44_0000--s-1\mip_rl_beam_mip_clean_20260508.lp_petri_transfer\mip_rl_beam_mip_clean_20260508.lp_petri_transfer_2026_05_12_10_02_27_0000--s-1\params.pkl   --instance_dir generated_instances/MIP  --instance_name mip_ablation_cleaning.lp  --generate_petri_instance True  --num_batches 10   --num_pm 2   --num_steps 13  --process_mode mixed  --mode_4x1_wafers 51  --mode_2x2_wafers 47  --pec_pool_size 8  --time_limit 3000  --instance_type petri_transfer  --output_dir ablation_results
```

没有训练模型时，也可以不传 `--test_model_path`，此时 `a3c_only` 和 `a3c_beam` 会被标记为 skipped，但 `solver_only` 和 `beam_only` 仍可运行。

消融实验输出包括：

```text
ablation_results/ablation_<instance_type>_<timestamp>.json
ablation_results/ablation_<instance_type>_<timestamp>.csv
ablation_results/ablation_<instance_type>_<timestamp>.md
ablation_results/ablation_<instance_type>_<timestamp>_comparison.svg
ablation_results/ablation_<instance_type>_<timestamp>_gantt/
```

## 8. 根据 solution json 生成甘特图

如果测试或消融已经自动生成了甘特图，可直接查看对应 `_gantt/index.html`。

若要手动生成：

```powershell
python petri_gantt.py ^
  --solution_json petri_transfer_use_hrl_Trueheuristics_cutsel\YOUR_SOLUTIONS.json
```

也可以指定输出目录：

```powershell
python petri_gantt.py ^
  --solution_json petri_transfer_use_hrl_Trueheuristics_cutsel\YOUR_SOLUTIONS.json ^
  --output_dir generated_instances\MIP\manual_gantt
```

默认 `--view full` 会生成全流程甘特图。若只想检查两个四腔加工模块 `CH2/CH3` 的排程，可生成 chamber-only 甘特图：

```powershell
python petri_gantt.py ^
  --solution_json petri_transfer_use_hrl_Trueheuristics_cutsel\YOUR_SOLUTIONS.json ^
  --view chambers
```

若要按设备资源/腔室查看每个动作，可生成 resource 甘特图。该视图会把结果按 `ATR robot`、`AL`、`LLupper slot`、`VTR robot`、`CH2/CH3 PM`、`LLlower slot` 分泳道输出，并在每个动作条中标注参与动作的 `Wxx` 产品晶圆和 `PECxx` 晶圆：

```powershell
python petri_gantt.py ^
  --solution_json petri_transfer_use_hrl_Trueheuristics_cutsel\YOUR_SOLUTIONS.json ^
  --view resources
```

也可以一次生成全流程图、`CH2/CH3` 模块图和资源视角图：

```powershell
python petri_gantt.py ^
  --solution_json petri_transfer_use_hrl_Trueheuristics_cutsel\YOUR_SOLUTIONS.json ^
  --view all
```

全流程甘特图会展示：

- 产品晶圆的 `ATR / AL / LLupper / VTR / PM / LLlower / Return`
- PEC wafer 的 `VTR / PM / Return`
- 4x1 前后侧位装卸
- 2x2 head、cycle、bridge、tail
- cleaning 批次
- 每片产品晶圆的最终回 LP 时间

`--view chambers` 只绘制两条泳道：`CH2 four-pocket module` 和 `CH3 four-pocket module`。图中包含每个 chamber 的 `4x1` batch、`2x2` head/bridge/cycle/tail，以及 cleaning 窗口，适合检查同一时刻每个四腔模块内的 wafer/PEC 组合是否合理。

`--view resources` 生成 `<instance>_resources_gantt.svg`。它面向设备资源占用检查：同一条泳道表示同一个物理资源，动作条文本和鼠标悬停提示都会显示本次动作涉及的晶圆编号，例如 `W1, W2, PEC3, PEC4`。

## 9. 推荐完整运行顺序

第一次完整复现实验时，建议按以下顺序：

1. 生成一个小规模 MIP，确认 PySCIPOpt 和路径无误。
2. 生成目标规模 MIP，记录带日期的 `.lp` 文件名。
3. 修改或确认 `configs/petri_mip_test_config.json` 中的 `instance_file_path` 和 `scip_time_limit`。
4. 运行 `parallel_reinforce_algorithm.py --train_type train` 训练 cut selection 模型。
5. 用 `plot_progress_curves.py` 检查训练曲线。
6. 用 `run_petri_a3c_beam.py` 或 `parallel_reinforce_algorithm.py --train_type test` 测试训练好的模型。
7. 用 `petri_gantt.py` 查看具体调度时间表。
8. 用 `run_ablation_experiments.py` 做对比实验并生成汇总报告。

## 10. 常见问题

### 10.1 `pec_pool_size` 报错

当前设备说明绑定每个旋转腔 4 片 PEC wafer。由于 `num_pm=2`，因此 `pec_pool_size` 至少为 `8`，且不能超过 `pec_storage_slots=10`，并需要能被 `num_pm` 整除。推荐使用：

```text
--pec_pool_size 8
```

### 10.2 生成实例后训练找不到文件

检查三处是否一致：

```text
generated_instances/MIP/实际文件名.lp
configs/petri_mip_test_config.json 中的 env.instance_file_path
训练命令中的 --single_instance_file
```

注意 `.lp` 文件名会自动追加日期，训练时不要继续使用未追加日期的原始 `--instance_name`。

### 10.3 训练很慢

每个训练 sample 都会实际调用一次 SCIP 求解。若配置为：

```text
num_epochs = 20
samples_per_epoch = 4
scip_time_limit = 300
```

仅采样阶段上界就是：

```text
20 * 4 * 300 = 24000 秒
```

初次验证时建议：

- 把实例规模降到 `4x1=4, 2x2=2`
- 把 `configs/petri_mip_test_config.json` 中的 `env.scip_time_limit` 降到 `60` 或 `120`
- 保持 `trainer.samples_per_epoch` 较小
- 确认流程跑通后再扩大规模

### 10.4 cleaning 导致不可行

若 `cleaning_interval` 太小，而 2x2 链本身需要连续占用较多 cycle，模型可能要求将工作拆分到两个 chamber，否则会报告不可行。调试时可先设置：

```text
--cleaning_interval 0
```

确认基础调度可行后，再逐步恢复 cleaning 约束。

### 10.5 测试脚本提示找不到模型

`run_petri_a3c_beam.py` 会检查 `--test_model_path` 是否存在。请确认路径指向真实文件，例如：

```text
data\...\params.pkl
```

而不是只写到实验目录。

### 10.6 只想看默认 SCIP 或 Beam 对比

可以直接运行 `run_ablation_experiments.py` 并省略 `--test_model_path`。此时 A3C 相关方法会跳过，但默认 SCIP 和启发式 Beam 仍会输出结果。

## 11. 参数含义总表

本节按脚本列出当前运行中会用到的参数。多个脚本出现同名参数时，其基础含义相同；差别只在于该脚本是否继续把参数传给 MIP 生成器、训练环境或测试环境。

### 11.1 `petri_mip_generator.py` 参数

| 参数 | 默认值 | 具体含义 |
| --- | --- | --- |
| `--output_dir` | `generated_instances/petri` | MIP 实例输出目录。当前建议使用 `generated_instances/MIP`，与配置文件默认实例目录保持一致。 |
| `--instance_name` | `petri_batch10_fullflow_v7.lp` | 原始实例文件名。程序会自动追加日期后缀，例如 `mip_case_20260508.lp`。 |
| `--num_batches` | `10` | 兼容参数，必须为正数。当前 4x1 每腔批次数上界由产品 PW 对数量自动推导，不直接由该参数决定。 |
| `--num_pm` | `2` | 旋转腔数量。当前设备固定为 2，对应 `CH2` 和 `CH3`。 |
| `--num_steps` | `13` | 兼容旧流程的步骤数参数；当前模型主要按具体阶段和资源约束建模。 |
| `--total_wafers` | `0` | 产品晶圆总数。为 `0` 时由模式数量、`mode_sequence` 或 `wafer_mode_map` 自动确定；单模式或 wafer 级配置时可直接指定总片数。 |
| `--process_mode` | `auto` | 工艺模式策略：`4x1` 只跑 4x1，`2x2` 只跑 2x2，`mixed` / `both` 按两类数量混跑，`custom` 用 wafer 级配置，`auto` 自动推断。 |
| `--mode_4x1_wafers` / `--full_mode_wafers` | `10` | 执行 4x1 工艺的产品晶圆数量。若为奇数，最后一个 4x1 PW 对自动为 `1 product + 1 PEC`。 |
| `--mode_2x2_wafers` / `--mix_mode_wafers` | `10` | 执行 2x2 工艺的产品晶圆数量。若为奇数，最后一个 2x2 PW 对自动为 `1 product + 1 PEC`。 |
| `--pec_pool_size` | `8` | 可复用 PEC wafer 数量。当前要求至少 `4*num_pm=8`，不超过 PEC storage 容量 `10`，且能被 `num_pm` 整除。 |
| `--batch_size` | `4` | 单个旋转腔槽位数。当前四槽旋转腔固定为 `4`。 |
| `--big_m` | `10000.0` | 大 M 线性化常数，用于启用/禁用约束和时间区间绑定。过小可能误删可行解，过大可能带来数值问题。 |
| `--pm_transfer_gap` | `1.0` | 腔体换片间隔兼容参数。当前主要时序由 VTR 搬运、旋转、加工和资源互斥约束确定。 |
| `--pm_rotation_time_180` | `2.0` | 旋转腔 180 度自转时间，用于 4x1 和 cleaning 的前后侧位装卸衔接。 |
| `--pair_transfer_time` | `4.0` | VTR 搬运一个 PW 对的时间，用于 4x1 装卸、2x2 head/bridge/tail 和 cleaning 装卸。 |
| `--atr_transfer_time` | `3.0` | ATR 送片动作时间，例如 `LP -> AL`、`AL -> LLupper`。 |
| `--atr_return_time` | `3.0` | ATR 回片动作时间，即 `LLlower -> LP`。 |
| `--aligner_time` | `20.0` | 产品晶圆占用 AL 校准器的最短时间。 |
| `--llupper_time` | `30.0` | 产品晶圆在 LLupper 中的最短停留时间。 |
| `--lllower_time` | `25.0` | 产品晶圆在 LLlower 中的最短停留时间。 |
| `--full_process_time` | `80.0` | 4x1 满片加工工艺时间。 |
| `--mix_boundary_process_time` | `30.0` | 2x2 边界 cycle 工艺时间，主要对应链首、链尾相关循环。 |
| `--mix_internal_process_time` | `30.0` | 2x2 内部 cycle 工艺时间，主要对应中间产品链循环。 |
| `--cleaning_interval` | `10` | 每个 chamber 连续完成多少个完整腔体加工 cycle 后插入一次 cleaning。设为 `0` 表示关闭 cleaning 约束。 |
| `--cleaning_process_time` | `0.0` | cleaning 工艺时间。若为 `0`，代码采用 `2*full_process_time` 作为有效 cleaning 时间。 |
| `--max_module_residency_time` | `10000.0` | 晶圆在 AL、LL、PM 等模块中的最大驻留时间上限。 |
| `--max_robot_residency_time` | `10000.0` | 晶圆在 ATR/VTR 搬运动作中的最大驻留时间上限。 |
| `--pm_balance_penalty` | `0.01` | 目标函数中的腔体负载均衡惩罚权重。主目标仍为最小化 `c_max`。 |
| `--mode_sequence` | 空字符串 | wafer 级完整模式序列，可写 `4x1,4x1,2x2` 等；优先级高于两类数量参数。 |
| `--wafer_mode_map` / `--wafer_modes` | 空字符串 | 按产品晶圆编号覆盖模式，可写 `W3:2x2,W7=4x1`。 |
| `--default_wafer_mode` | 空字符串 | `wafer_mode_map` 未覆盖晶圆的默认模式；常配合 `--process_mode custom --total_wafers` 使用。 |

### 11.2 `parallel_reinforce_algorithm.py` 参数

| 参数 | 默认值 | 具体含义 |
| --- | --- | --- |
| `--config_file` | `configs/petri_mip_test_config.json` | 训练/测试基础配置文件路径。 |
| `--sel_cuts_percent` | `0.1` | cut 选择比例基础值，用于控制加入求解器的 cuts 数量比例。 |
| `--single_instance_file` | `all` | 指定单个实例文件名；`all` 表示测试阶段读取实例目录下全部 `.lp/.mps/.cip` 文件。 |
| `--reward_type` | `lp_solution_value` | 训练奖励类型。Petri 实验常用 `solving_time`。 |
| `--baseline_type` | `simple` | 强化学习 baseline 类型；`simple` 为简单基线，`net` 会启用价值网络。 |
| `--train_type` | `train` | 运行模式；`train` 为训练，`test` 为加载模型测试。 |
| `--instance_type` | `item_placement` | 实例类型标识，用于日志和结果目录命名。Petri 流程建议用 `petri_transfer`。 |
| `--time_limit` | `10` | 命令行时限兼容参数。使用 `solving_time` 时，主要以配置文件 `env.scip_time_limit` 为准。 |
| `--use_cutsel_percent_policy` | `False` | 是否启用高层 cut 保留比例策略。Petri 实验建议为 `True`。 |
| `--policy_type` | `with_token` | 低层策略网络类型；`with_token` 表示带终止符的指针网络。 |
| `--seed` | `1` | 主随机种子。 |
| `--scip_seed` | `1` | SCIP 求解器随机种子。 |
| `--test_decode_type` | `beam_search` | 测试阶段 cut 序列解码方式，常用 `beam_search` 或 `greedy`。 |
| `--generate_petri_instance` | `False` | 是否在运行前自动生成 Petri MIP 实例。 |
| `--petri_instance_dir` | `generated_instances/petri` | 自动生成 Petri 实例时的输出目录。当前建议传 `generated_instances/MIP`。 |
| `--petri_instance_name` | `petri_batch10_fullflow_v7.lp` | 自动生成实例时的原始文件名，会自动追加日期。 |
| `--petri_batches` | `10` | 自动生成实例时传给 MIP 配置的 `num_batches`。 |
| `--petri_num_pm` | `2` | 自动生成实例时的 chamber 数量，当前必须为 `2`。 |
| `--petri_num_steps` | `13` | 自动生成实例时的兼容 step 参数。 |
| `--petri_total_wafers` | `0` | 自动生成实例时的产品晶圆总数校验值。 |
| `--petri_process_mode` | `auto` | 自动生成实例时的工艺模式策略，取值同 `--process_mode`。 |
| `--petri_4x1_wafers` | `20` | 自动生成实例时的 4x1 产品晶圆数量。 |
| `--petri_2x2_wafers` | `20` | 自动生成实例时的 2x2 产品晶圆数量。 |
| `--petri_pec_pool_size` | `8` | 自动生成实例时的 PEC wafer 数量。 |
| `--petri_mode_sequence` | 空字符串 | 自动生成实例时的 wafer 级完整模式序列。 |
| `--petri_wafer_mode_map` / `--petri_wafer_modes` | 空字符串 | 自动生成实例时按晶圆编号覆盖模式。 |
| `--petri_default_wafer_mode` | 空字符串 | 自动生成实例时未覆盖晶圆的默认模式。 |

### 11.3 `run_petri_a3c_beam.py` 参数

| 参数 | 默认值 | 具体含义 |
| --- | --- | --- |
| `--config_file` | `configs/petri_mip_test_config.json` | 基础配置文件；脚本会基于它写出 runtime config。 |
| `--test_model_path` | 必填 | 训练好的模型文件路径，通常为 `params.pkl` 或 `itr_*.pkl`。 |
| `--instance_dir` | `generated_instances/petri` | 新实例输出目录和测试实例目录。当前建议传 `generated_instances/MIP`。 |
| `--instance_name` | `petri_batch10_fullflow_v7.lp` | 新实例原始文件名，会自动追加日期。 |
| `--sel_cuts_percent` | `0.2` | 测试时 cut 保留比例相关参数。 |
| `--policy_type` | `with_token` | 策略网络类型，应与训练时保持一致。 |
| `--use_cutsel_percent_policy` | `True` | 是否使用高层 cut 比例策略，应与训练时保持一致。 |
| `--test_decode_type` | `beam_search` | 测试解码方式，推荐 `beam_search`。 |
| `--seed` | `1` | 测试主随机种子。 |
| `--scip_seed` | `1` | SCIP 随机种子。 |
| `--instance_type` | `petri_transfer` | 结果输出目录命名标识。 |
| `--num_batches` | `10` | 传给 MIP 生成器的 `num_batches`。 |
| `--num_pm` | `2` | 传给 MIP 生成器的 chamber 数量。当前必须为 `2`。 |
| `--num_steps` | `13` | 传给 MIP 生成器的兼容 step 参数。 |
| `--total_wafers` | `0` | 产品晶圆总数校验值。 |
| `--process_mode` | `auto` | 新实例的工艺模式策略，取值同 `petri_mip_generator.py`。 |
| `--mode_4x1_wafers` | `20` | 新实例中 4x1 产品晶圆数量。 |
| `--mode_2x2_wafers` | `20` | 新实例中 2x2 产品晶圆数量。 |
| `--pec_pool_size` | `8` | 新实例中 PEC wafer 数量。当前设备通常传 `8` 或 `10`。 |
| `--mode_sequence` | 空字符串 | 新实例的 wafer 级完整模式序列。 |
| `--wafer_mode_map` / `--wafer_modes` | 空字符串 | 新实例中按晶圆编号覆盖模式。 |
| `--default_wafer_mode` | 空字符串 | 新实例中未覆盖晶圆的默认模式。 |

### 11.4 `run_ablation_experiments.py` 参数

| 参数 | 默认值 | 具体含义 |
| --- | --- | --- |
| `--config_file` | `configs/petri_mip_test_config.json` | 消融实验基础配置文件。 |
| `--test_model_path` | 空字符串 | 训练好的模型路径；为空时 A3C 相关方法跳过，默认 SCIP 和 Beam 仍可运行。 |
| `--instance_dir` | `generated_instances/petri` | 实例目录。当前建议传 `generated_instances/MIP`。 |
| `--instance_name` | `petri_batch10_fullflow_v7.lp` | 待生成或待读取的实例名。若生成实例，会自动追加日期。 |
| `--generate_petri_instance` | `True` | 是否在消融前生成新 Petri MIP 实例。 |
| `--single_instance_file` | 空字符串 | 指定已有实例文件名。为空时通常使用 `instance_name` 或生成后的实例名。 |
| `--output_dir` | `ablation_results` | 消融实验结果输出目录。 |
| `--instance_type` | `petri_transfer` | 结果文件名前缀中的实例类型标识。 |
| `--seed` | `1` | 消融实验主随机种子。 |
| `--scip_seed` | `1` | SCIP 随机种子。 |
| `--sel_cuts_percent` | `0.2` | A3C/Beam 方法中的 cut 保留比例相关参数。 |
| `--policy_type` | `with_token` | 策略网络类型，应与训练模型一致。 |
| `--use_cutsel_percent_policy` | `True` | 是否使用高层 cut 比例策略。 |
| `--a3c_decode_type` | `greedy` | A3C-only 方法的解码方式。 |
| `--a3c_beam_decode_type` | `beam_search` | A3C+Beam 方法的解码方式。 |
| `--heuristic_beam_size` | `3` | Beam-only 启发式方法的 beam 宽度。 |
| `--heuristic_redundancy_weight` | `0.15` | Beam-only 启发式重排时的冗余惩罚权重。 |
| `--time_limit` | `-1.0` | 消融实验中覆盖配置文件 SCIP 时限的参数，大于 0 时生效。 |
| `--num_batches` | `10` | 生成消融实例时的 `num_batches`。 |
| `--num_pm` | `2` | 生成消融实例时的 chamber 数量，当前必须为 `2`。 |
| `--num_steps` | `13` | 生成消融实例时的兼容 step 参数。 |
| `--total_wafers` | `0` | 生成消融实例时的产品晶圆总数校验值。 |
| `--process_mode` | `auto` | 生成消融实例时的工艺模式策略，取值同 `petri_mip_generator.py`。 |
| `--mode_4x1_wafers` | `20` | 生成消融实例时的 4x1 产品晶圆数量。 |
| `--mode_2x2_wafers` | `20` | 生成消融实例时的 2x2 产品晶圆数量。 |
| `--pec_pool_size` | `40` | 生成消融实例时的 PEC wafer 数量。当前设备不接受默认值 `40`，应显式传 `8` 或 `10`。 |
| `--mode_sequence` | 空字符串 | 生成消融实例时的 wafer 级完整模式序列。 |
| `--wafer_mode_map` / `--wafer_modes` | 空字符串 | 生成消融实例时按晶圆编号覆盖模式。 |
| `--default_wafer_mode` | 空字符串 | 生成消融实例时未覆盖晶圆的默认模式。 |

### 11.5 辅助脚本参数

| 脚本 | 参数 | 默认值 | 具体含义 |
| --- | --- | --- | --- |
| `petri_gantt.py` | `--solution_json` | 必填 | 求解结果 JSON 文件路径，需包含非空 `solution` 字段。 |
| `petri_gantt.py` | `--output_dir` | 空字符串 | 甘特图输出目录；为空时自动创建 `<solution_stem>_gantt`。 |
| `petri_gantt.py` | `--view` | `full` | 甘特图视图：`full` 为全流程，`chambers` 只绘制 `CH2/CH3` 四腔加工模块，`resources` 按 `ATR/AL/LL/VTR/PM` 资源泳道输出并标注晶圆编号，`all` 同时生成全部视图。 |
| `plot_progress_curves.py` | `--progress_csv` | 空字符串 | 指定要绘图的 `progress.csv`；若传目录，则默认使用目录下的 `progress.csv`。 |
| `plot_progress_curves.py` | `--data_dir` | `data` | 未指定 `progress_csv` 时，从该目录递归寻找最新 `progress.csv`。 |
| `plot_progress_curves.py` | `--output` | 空字符串 | SVG 输出路径；为空时写到 `progress.csv` 所在目录。 |
| `plot_progress_curves.py` | `--window` | `3` | 移动平均窗口，用于平滑曲线。 |
| `plot_progress_curves.py` | `--width` | `1600` | SVG 宽度，单位像素。 |
| `plot_progress_curves.py` | `--columns` | `2` | 曲线面板列数。 |
| `plot_progress_curves.py` | `--title` | `Training Convergence Dashboard` | 图表主标题。 |
| `plot_progress_curves.py` | `--subtitle` | 空字符串 | 图表副标题；为空时默认显示源文件路径。 |
| `plot_progress_curves.py` | `--hide_source_path` | `False` | 是否隐藏图表中的源文件路径。 |
| `stitch_progress_runs.py` | `--runs` | 必填 | 多个训练 run 目录或 `progress.csv` 路径，按拼接顺序传入。 |
| `stitch_progress_runs.py` | `--output` | 空字符串 | 拼接后的 CSV 输出路径。为空时写到第一个 run 目录。 |
| `stitch_progress_runs.py` | `--prefer` | `later` | 重复 epoch 行的保留策略；`later` 保留后传入 run，`earlier` 保留先传入 run。 |

### 11.6 `configs/petri_mip_test_config.json` 常用配置项

| 配置路径 | 具体含义 |
| --- | --- |
| `experiment.seed` | 实验随机种子。 |
| `experiment.exp_prefix` | 日志目录名前缀；训练时会追加实例名和 `instance_type`。 |
| `experiment.base_log_dir` | 日志和 checkpoint 根目录。首次训练建议为 `data`；续训时指向包含 `params.pkl` 的旧实验目录。 |
| `experiment.snapshot_mode` | checkpoint 保存方式。 |
| `experiment.snapshot_gap` | checkpoint 保存间隔。 |
| `env.instance_file_path` | 训练环境读取 MIP 实例的目录。 |
| `env.scip_time_limit` | SCIP 单次求解时限，单位秒。 |
| `env.single_instance_file` | 配置文件中的默认实例名，会被命令行 `--single_instance_file` 覆盖。 |
| `env.presolving` | 是否启用 SCIP presolving。 |
| `env.separating` | 是否启用 SCIP separating。 |
| `env.conflict` | 是否启用 SCIP conflict analysis。 |
| `env.heuristics` | 是否启用 SCIP 内置启发式。 |
| `env.max_rounds_root` | root 节点最大 cut 分离轮数。 |
| `algorithm.num_epochs` | 总训练 epoch 数；续训时表示最终训练到的总 epoch。 |
| `algorithm.train_steps_per_epoch` | 每个 epoch 内策略网络更新步数。 |
| `algorithm.batch_size` | 策略更新 batch 大小。 |
| `algorithm.actor_net_lr` | 低层策略网络学习率。 |
| `algorithm.critic_net_lr` | critic/value 网络学习率。 |
| `algorithm.reward_type` | 奖励类型，可被命令行覆盖。 |
| `algorithm.baseline_type` | baseline 类型，可被命令行覆盖。 |
| `algorithm.evaluate_freq` | 每隔多少个 epoch 做一次 evaluate。 |
| `algorithm.evaluate_samples` | 每次 evaluate 使用的样本数。 |
| `algorithm.lr_decay` | 是否启用学习率衰减。 |
| `algorithm.lr_decay_step` | 学习率衰减步长。 |
| `algorithm.lr_decay_rate` | 学习率衰减倍率。 |
| `algorithm.normalize` | 是否对 cut 特征做运行均值方差归一化。 |
| `algorithm.normalize_reward` | 是否对 reward 做归一化。 |
| `trainer.samples_per_epoch` | 每个 epoch 采样多少次 SCIP 求解。 |
| `trainer.n_jobs` | 并行采样 worker 数，需整除 `samples_per_epoch`。 |
| `net_share.embedding_dim` | cut 特征嵌入维度；当前结构感知特征常用 `23`。 |
| `net_share.hidden_dim` | 策略网络隐藏层维度。 |
| `net_share.tanh_exploration` | 策略输出探索强度缩放参数。 |
| `net_share.use_tanh` | 是否对 logits 使用 tanh 限幅。 |
| `policy.n_glimpses` | 指针网络 glimpse 次数。 |
| `policy.beam_size` | beam search 宽度。 |
| `value.n_process_block_iters` | 高层比例策略或 value 网络中的处理块迭代次数。 |
| `cutsel_percent_policy.use_cutsel_percent_policy` | 是否启用高层 cut 比例策略。 |
| `cutsel_percent_policy.train_freq` | 高层策略训练频率。 |
| `cutsel_percent_policy.train_highlevel_batch_size` | 高层策略训练 batch 大小。 |
| `cutsel_percent_policy.highlevel_actor_lr` | 高层策略学习率。 |
| `devices.global_device` | 主进程设备，例如 `cuda:0`。无 CUDA 时会回退 CPU。 |
| `devices.multi_devices` | 多 worker 使用的设备列表，例如 `["0"]`。 |
| `test_kwargs.test_instance_path` | 测试实例目录。 |
| `test_kwargs.test_model_path` | 测试时加载的模型路径。 |
| `test_kwargs.n_jobs` | 测试并行 worker 数。 |
| `evaluate_kwargs` | 训练中 evaluate 使用的实例目录、worker 数和环境参数。 |
| `online_test_kwargs` | 训练中 online test 使用的频率、实例目录、worker 数和环境参数。 |
| `start_epoch` | 训练起始 epoch。首次训练为 `0`；续训时设为下一轮要开始的 epoch。 |
## 12. 最小命令清单

生成实例：

```powershell
python petri_mip_generator.py ^
  --output_dir generated_instances/MIP ^
  --instance_name mip_small_check.lp ^
  --process_mode mixed ^
  --mode_4x1_wafers 4 ^
  --mode_2x2_wafers 2 ^
  --pec_pool_size 8
```

训练：

```powershell
python parallel_reinforce_algorithm.py ^
  --config_file configs/petri_mip_test_config.json ^
  --train_type train ^
  --single_instance_file mip_small_check_20260508.lp ^
  --reward_type solving_time ^
  --baseline_type simple ^
  --policy_type with_token ^
  --use_cutsel_percent_policy True ^
  --instance_type petri_transfer
```

测试：

```powershell
python run_petri_a3c_beam.py ^
  --config_file configs/petri_mip_test_config.json ^
  --test_model_path data\YOUR_RUN\YOUR_EXP\params.pkl ^
  --instance_dir generated_instances/MIP ^
  --instance_name mip_test.lp ^
  --process_mode mixed ^
  --mode_4x1_wafers 4 ^
  --mode_2x2_wafers 2 ^
  --pec_pool_size 8 ^
  --instance_type petri_transfer
```

画甘特图：

```powershell
python petri_gantt.py ^
  --solution_json petri_transfer_use_hrl_Trueheuristics_cutsel\YOUR_SOLUTIONS.json
```

按 AL、机械手、PM 等资源输出并标注晶圆：

```powershell
python petri_gantt.py ^
  --solution_json petri_transfer_use_hrl_Trueheuristics_cutsel\YOUR_SOLUTIONS.json ^
  --view resources
```

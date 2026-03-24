# Dual-Source Mixed-Flow Semiconductor Scheduling with MIP + A3C + Beam Search

本项目围绕“双源混流半导体组合设备调度问题”提供一套完整流程：

1. 生成双源混流半导体组合设备调度问题的 MIP 实例
2. 使用 A3C 风格的分层 cut selection 策略结合束搜索进行求解
3. 执行消融实验，对比默认 SCIP、A3C、Beam Only、A3C + Beam
4. 输出最终解、甘特图以及消融实验效率/求解质量对比图

## 当前 MIP 的真实语义

当前仓库中的 `petri_mip_generator.py` 已切换到修正后的共享旋转腔模型。其关键语义如下：

- 共享旋转腔为 `CH2` 和 `CH3`
- `CH2` 和 `CH3` 都可以执行 `4x1` 与 `2x2`
- 每个产品对的工艺模式是输入参数，而不是模型里的路由决策
- `PEC` 只在 `4x1` 补位或 `2x2` 首尾边界时消耗
- `4x1` 产品对只能与 `4x1` 产品对或 `PEC` 配批
- `2x2` 产品对只能与 `2x2` 产品对或 `PEC` 形成流水周期

如果不传 `--mode_sequence`，生成器默认使用交替模式 `2x2,4x1,2x2,4x1,...` 作为演示实例。真实实验建议显式传入 pair-level 或 wafer-level 的 `mode_sequence`。

## 路径说明

当前版本已经统一了路径解析逻辑：

- 所有相对路径默认都相对于项目根目录解析
- 项目移动到新的磁盘或目录后，不需要再手工改脚本里的旧绝对路径
- 训练日志、生成实例、测试结果、消融结果都会稳定写回当前仓库目录下

默认输出位置如下：

- 实例与模型说明：`generated_instances/petri/`
- 训练日志与模型：`data/`
- RL 测试结果：`<instance_type>_use_hrl_Trueheuristics_cutsel/`
- 消融实验结果：`ablation_results/`

## 环境依赖

- Python 3.7+
- `numpy`
- `tqdm`
- `gtimer`
- `torch`
- `tensorboard`
- `pyscipopt`
- SCIP

安装命令：

```powershell
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

如果 `pyscipopt` 尚未安装：

```powershell
python -m pip install pyscipopt
```

## 目录结构

- `petri_mip_generator.py`：生成双源混流调度 MIP
- `parallel_reinforce_algorithm.py`：训练与测试主入口
- `run_petri_a3c_beam.py`：一键生成实例并用 A3C + Beam 测试
- `run_ablation_experiments.py`：运行消融实验并生成对比结果
- `petri_gantt.py`：从解文件生成甘特图
- `docs/petri_dual_source_rotary_mip.md`：当前 MIP 建模说明
- `docs/how_to_run_and_get_final_mip_solution.md`：运行说明
- `configs/petri_mip_test_config.json`：Petri MIP 测试/训练配置

## 推荐流程

### 1. 生成 MIP 实例

```powershell
python petri_mip_generator.py ^
  --output_dir generated_instances/petri ^
  --instance_name petri_batch10_v2.lp ^
  --num_batches 10 ^
  --num_pm 2 ^
  --num_steps 13 ^
  --total_wafers 40 ^
  --pec_pool_size 40
```

说明：
- `--instance_name` 传入的是基础文件名，生成器会自动在扩展名前追加当天日期
- 例如传入 `petri_batch10_v2.lp`，实际输出会变成 `petri_batch10_v2_<YYYYMMDD>.lp`

如果要显式指定工艺模式，可以传入：

```powershell
python petri_mip_generator.py ^
  --output_dir generated_instances/petri ^
  --instance_name sanity_modes.lp ^
  --num_batches 2 ^
  --num_pm 2 ^
  --total_wafers 8 ^
  --pec_pool_size 8 ^
  --mode_sequence "2x2,4x1,2x2,4x1"
```

生成结果：

- `generated_instances/petri/petri_batch10_v2_<YYYYMMDD>.lp`
- `generated_instances/petri/petri_batch10_v2_<YYYYMMDD>_model.md`

### 2. 训练 A3C 风格策略模型

```powershell
python parallel_reinforce_algorithm.py ^
  --config_file configs/petri_mip_test_config.json ^
  --train_type train ^
  --generate_petri_instance True ^
  --petri_instance_dir generated_instances/petri ^
  --petri_instance_name petri_batch10_v2.lp ^
  --petri_batches 10 ^
  --petri_num_pm 2 ^
  --petri_num_steps 13 ^
  --petri_total_wafers 40 ^
  --petri_pec_pool_size 40 ^
  --single_instance_file petri_batch10_v2.lp ^
  --policy_type with_token ^
  --use_cutsel_percent_policy True ^
  --sel_cuts_percent 0.2 ^
  --reward_type solving_time ^
  --baseline_type simple ^
  --instance_type petri_transfer ^
  --time_limit 300 ^
  --seed 1 ^
  --scip_seed 1
```

如果训练时要生成真实模式序列的实例，可以额外传入：

```powershell
  --petri_mode_sequence "2x2,4x1,2x2,4x1,..."
```

训练输出在 `data/` 下自动创建实验目录，典型文件包括：

- `params.pkl`
- `itr_*.pkl`
- `progress.csv`
- `debug.log`
- `variant.json`

### 3. 使用 A3C + Beam Search 测试并输出最终解

```powershell
python run_petri_a3c_beam.py ^
  --config_file configs/petri_mip_test_config.json ^
  --test_model_path data/petri_mip_rl_beam/YOUR_EXPERIMENT_DIR/params.pkl ^
  --instance_dir generated_instances/petri ^
  --instance_name petri_batch10_v2.lp ^
  --num_batches 10 ^
  --num_pm 2 ^
  --num_steps 13 ^
  --total_wafers 40 ^
  --pec_pool_size 40 ^
  --sel_cuts_percent 0.2 ^
  --policy_type with_token ^
  --use_cutsel_percent_policy True ^
  --test_decode_type beam_search ^
  --seed 1 ^
  --scip_seed 1 ^
  --instance_type petri_transfer
```

其中 `YOUR_EXPERIMENT_DIR` 替换成训练阶段真实产生的目录名。

测试输出会写到项目根目录下的：

- `petri_transfer_use_hrl_Trueheuristics_cutsel/`

典型结果文件：

- `seed_1_model_params.pkl_RL_max_cuts_root_0.2_<YYYYMMDD>.npy`
- `seed_1_model_params.pkl_RL_max_cuts_root_0.2_solutions_<YYYYMMDD>.json`
- `seed_1_model_params.pkl_RL_max_cuts_root_0.2_solutions_<YYYYMMDD>_gantt/`

### 4. 手动从解文件重生成甘特图

```powershell
python petri_gantt.py ^
  --solution_json petri_transfer_use_hrl_Trueheuristics_cutsel/seed_1_model_params.pkl_RL_max_cuts_root_0.2_solutions_<YYYYMMDD>.json
```

指定输出目录：

```powershell
python petri_gantt.py ^
  --solution_json petri_transfer_use_hrl_Trueheuristics_cutsel/seed_1_model_params.pkl_RL_max_cuts_root_0.2_solutions_<YYYYMMDD>.json ^
  --output_dir docs/petri_gantt_demo
```

`petri_gantt.py` 支持两类输入：

- RL 测试输出的 `*_solutions_<YYYYMMDD>.json`
- 消融实验输出的 `ablation_*.json`

### 5. 运行消融实验

```powershell
python run_ablation_experiments.py ^
  --config_file configs/petri_mip_test_config.json ^
  --test_model_path data/petri_mip_rl_beam/YOUR_EXPERIMENT_DIR/params.pkl ^
  --instance_dir generated_instances/petri ^
  --instance_name petri_batch10_v2.lp ^
  --generate_petri_instance True ^
  --num_batches 10 ^
  --num_pm 2 ^
  --num_steps 13 ^
  --total_wafers 40 ^
  --pec_pool_size 40 ^
  --sel_cuts_percent 0.2 ^
  --policy_type with_token ^
  --use_cutsel_percent_policy True ^
  --a3c_decode_type greedy ^
  --a3c_beam_decode_type beam_search ^
  --heuristic_beam_size 3 ^
  --seed 1 ^
  --scip_seed 1 ^
  --instance_type petri_transfer
```

消融实验会比较：

- `solver_only`
- `a3c_only`
- `beam_only`
- `a3c_beam`

默认输出到 `ablation_results/`，典型文件包括：

- `ablation_petri_transfer_<timestamp>.json`
- `ablation_petri_transfer_<timestamp>.csv`
- `ablation_petri_transfer_<timestamp>.md`
- `ablation_petri_transfer_<timestamp>_comparison.svg`
- `ablation_petri_transfer_<timestamp>_gantt/`

## 输出解释

### RL 测试输出

- `status`：SCIP 求解状态
- `best_obj`：当前最优目标值
- `solution`：非零变量取值
- `solving_time`：求解时间
- `ntotal_nodes`：搜索节点数
- `primal_dual_gap`：原始对偶间隙
- `primaldualintegral`：原始对偶积分

### 消融实验输出

- `json`：完整结果，含每个方法每个实例的解与统计量
- `csv`：逐实例结果表
- `md`：摘要与超参数说明
- `comparison.svg`：效率/质量对比图
- `gantt/`：各方法对应的调度甘特图

## 复现实验时的注意事项

- `seed` 控制 Python / NumPy / PyTorch 随机性
- `scip_seed` 控制 SCIP 内部随机性
- 训练产生的是策略参数，不是最终 MIP 解
- 最终解始终由 SCIP 在测试或默认求解阶段给出
- 只有当 `status == optimal` 时，才能说明当前结果已被证明为最优解

## 一句话总结

推荐的最短闭环是：

1. 生成或自动生成 `generated_instances/petri/*.lp`
2. 训练得到 `data/.../params.pkl`
3. 用 `run_petri_a3c_beam.py` 生成 `*_solutions_<YYYYMMDD>.json` 与自动甘特图
4. 用 `run_ablation_experiments.py` 生成四组方法对比、甘特图和 `*_comparison.svg`

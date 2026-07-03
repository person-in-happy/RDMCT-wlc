# 双源混流半导体调度：从实例生成到训练、测试、消融和甘特图前端

本文档给出一套可以直接在 PowerShell 中运行的完整流程，覆盖：

1. 生成 Petri/MIP 调度实例
2. 训练 cut selection 模型
3. 在测试集上验证模型
4. 运行消融实验
5. 打开交互式甘特图前端
6. 查看训练曲线和补充扩展功能

所有命令默认从项目根目录运行：

```powershell
cd G:\git\RDMCT-A3C
```

下面的示例把路径和参数直接写在命令中，不再先用变量赋值命令保存路径。每条命令下方给出必要说明。

## 1. 快速流程

这一节给出小规模可跑通流程。先生成带日期后缀的 Petri/MIP 训练实例，再读取该实例训练 cut selection 模型，并把模型保存到 `data`。

### 2.1 生成训练集

```powershell
python petri_mip_generator.py  --output_dir generated_instances\test  --instance_name mip_fullflow_train.lp  --num_batches 10  --num_pm 2  --process_mode mixed  --mode_4x1_wafers 7  --mode_2x2_wafers 11  --pec_pool_size 8  --chamber_idle_penalty 0.0001
```

说明：
- `--output_dir generated_instances\petri` 是训练集输出目录，与快速配置中的 `env.instance_file_path` 保持一致。
- 生成器会给 `.lp` 文件名自动追加日期后缀，并在终端打印真实文件路径。
- 下一步训练时，把终端输出的真实 `.lp` 文件名填到 `--single_instance_file`。

### 2.2 训练模型

```powershell
python parallel_reinforce_algorithm.py  --config_file configs\petri_mip_test_config.json  --train_type train  --generate_petri_instance False  --single_instance_file mip_wafer11_41_train_20260611.lp --sel_cuts_percent 0.2  --reward_type primaldualintegral  --baseline_type simple  --policy_type with_token  --use_cutsel_percent_policy True  --seed 1  --scip_seed 1  --time_limit 1800  --instance_type petri_transfer
```

说明：
训练路径为single_instance_file
- `--reward_type solving_time` 关心求解速度，`--reward_type primaldualintegral` 关心求解质量。
- `--config_file configs\petri_mip_quick_config.json` 使用快速配置：`num_epochs=5`、`samples_per_epoch=2`、`n_jobs=1`、训练日志根目录为 `data`。
- `--generate_petri_instance False` 表示训练阶段不再自动生成实例，而是读取第 2.1 节已经生成的训练集。
- `--single_instance_file batch10_fullflow_train_<date>.lp` 要替换为第 2.1 节终端输出的真实文件名。
- 正式训练可把 `configs\petri_mip_quick_config.json` 中的 `algorithm.num_epochs`、`trainer.samples_per_epoch` 和 `env.scip_time_limit` 调大。

训练输出目录形如：

```text
data/mip_rl_beam_<instance>_petri_transfer/<run_timestamp>/
  params.pkl
  itr_*.pkl
  progress.csv
  variant.json
```

### 2.3 绘制训练曲线

```powershell
python plot_progress_curves.py  --data_dir data  --output data\latest_convergence_curves.svg  --window 3  --title "Cut Selection Training"
```

说明：该命令从 `data` 中递归寻找最新的 `progress.csv`，并输出到 `data\latest_convergence_curves.svg`。

## 3. 生成测试集并验证模型

### 3.1 单实例封装求解

如果只想快速生成一个实例并立刻用训练好的模型测试，可使用封装脚本：

```powershell
python run_petri_a3c_beam.py   --config_file configs\petri_mip_test_config.json  --test_model_path latest   --instance_dir generated_instances\MIP_pipeline_demo_single_test   --instance_name mip_single_test.lp   --num_batches 10   --num_pm 2   --num_steps 13  --process_mode mixed  --mode_4x1_wafers 17  --mode_2x2_wafers 0  --pec_pool_size 8   --chamber_idle_penalty 0.0001  --test_decode_type beam_search   --time_limit 1800  --seed 1   --scip_seed 1  --instance_type petri_transfer
```

说明：

- `--test_model_path latest` 会自动定位 `data` 目录下最新的 `params.pkl`。
- `--instance_dir generated_instances\MIP_pipeline_demo_single_test` 是新测试实例和 runtime config 的输出目录。
- 该封装脚本会生成实例、写出测试 runtime config、调用 `parallel_reinforce_algorithm.py --train_type test`，并自动尝试生成甘特图前端。

测试输出目录通常形如：

```text
petri_transfer_use_hrl_Trueheuristics_cutsel/
  seed_<seed>_model_params.pkl_RL_max_cuts_root_0.2.npy
  seed_<seed>_model_params.pkl_RL_max_cuts_root_0.2_solutions_<date>.json
  seed_<seed>_model_params.pkl_RL_max_cuts_root_0.2_solutions_<date>_gantt/
```

### 3.2 批量测试多个已有实例

```powershell
python parallel_reinforce_algorithm.py  --config_file configs\petri_mip_quick_config.json   --train_type test   --single_instance_file all  --sel_cuts_percent 0.2   --policy_type with_token   --use_cutsel_percent_policy True   --test_decode_type beam_search   --test_time_limit 1800  --seed 1   --scip_seed 1   --instance_type petri_transfer
```

说明：该命令读取 `configs\petri_mip_quick_config.json` 中的 `test_kwargs.test_instance_path=generated_instances/petri`，并测试该目录下全部 `.lp/.mps/.cip` 实例；配置中的 `test_model_path=latest` 会自动定位最新模型。

## 4. 运行消融实验

消融实验会对比四种方法：

- `solver_only`：默认 SCIP cut selection
- `a3c_only`：只用 A3C 策略
- `beam_only`：只用启发式 Beam
- `a3c_beam`：A3C + Beam

### 4.1 带训练模型的消融实验

```powershell
python run_ablation_experiments.py  --config_file configs\petri_mip_quick_config.json  --test_model_path latest  --instance_dir generated_instances\MIP_pipeline_demo_ablation  --instance_name mip_ablation_demo.lp  --generate_petri_instance True   --num_batches 10   --num_pm 2   --num_steps 13   --process_mode mixed  --mode_4x1_wafers 17   --mode_2x2_wafers 0   --pec_pool_size 8   --chamber_idle_penalty 0.0001   --time_limit 1800  --sel_cuts_percent 0.2   --policy_type with_token  --use_cutsel_percent_policy True   --a3c_decode_type greedy   --a3c_beam_decode_type beam_search   --heuristic_beam_size 3   --heuristic_redundancy_weight 0.15   --heuristic_max_candidates 256   --heuristic_max_selected_cuts 256   --seed 1   --scip_seed 1   --instance_type petri_transfer   --output_dir ablation_results
```

说明：`--test_model_path latest` 会自动使用最新训练模型；结果写入 `ablation_results`，并自动生成 `<结果文件名>_gantt\index.html`。

### 4.2 无训练模型的消融实验

如果没有 `params.pkl`，可以先比较默认 SCIP 和启发式 Beam；A3C 相关方法会被标记为 skipped：

```powershell
python run_ablation_experiments.py   --config_file configs\petri_mip_test_config.json  --instance_dir generated_instances\MIP_pipeline_demo_ablation_nomodel   --instance_name mip_ablation_nomodel.lp   --generate_petri_instance True   --process_mode mixed   --mode_4x1_wafers 8   --mode_2x2_wafers 6   --pec_pool_size 8   --chamber_idle_penalty 0.0001   --time_limit 1800   --seed 1   --scip_seed 1   --instance_type petri_transfer   --output_dir ablation_results
```

说明：不传 `--test_model_path` 时，A3C 相关方法跳过，默认 SCIP 和启发式 Beam 仍会运行。

消融输出包括：

```text
ablation_results/ablation_<instance_type>_<timestamp>.json
ablation_results/ablation_<instance_type>_<timestamp>.csv
ablation_results/ablation_<instance_type>_<timestamp>.md
ablation_results/ablation_<instance_type>_<timestamp>_comparison.svg
ablation_results/ablation_<instance_type>_<timestamp>_gantt/
  index.html
  manifest.json
  *.svg
```

即使没有任何方法得到可行解，`_gantt/index.html` 也会生成，用来展示 `_comparison.svg` 对比图和无甘特图提示。

## 5. 甘特图前端

### 5.1 生成并打开甘特图前端

测试和消融会自动尝试生成甘特图。如果需要手动生成：

```powershell
python petri_gantt.py   --solution_json latest   --output_dir gantt_manual   --view all

Start-Process "gantt_manual\index.html"
```

说明：`--solution_json latest` 会自动读取 `petri_transfer_use_hrl_Trueheuristics_cutsel` 下最新的 `*solutions*.json`；`--output_dir gantt_manual` 是前端输出目录。

### 5.2 前端界面功能

`index.html` 是静态前端，不需要启动服务器。页面包含：

- 视图下拉框：`full`、`chambers`、`resources`
- 算法下拉框：消融实验中不同算法的结果
- 实例下拉框：多实例测试或消融中的不同 LP
- 对比图区域：展示消融 `_comparison.svg`
- SVG 打开按钮：单独打开当前甘特图
- 鼠标悬停提示：条形对应的标签、泳道、开始时间、结束时间、持续时间

三种甘特图视图：

- `full`：按产品晶圆和 PEC job 展示全流程路径
- `chambers`：只展示 `CH2/CH3` 四腔模块内部排程
- `resources`：按 `ATR robot`、`AL`、`LLupper slot`、`VTR robot`、`CH2/CH3 PM`、`LLlower slot` 等物理资源分泳道

## 6. 实例生成扩展功能

### 6.1 工艺模式

`--process_mode` 支持：

| 模式 | 含义 |
| --- | --- |
| `auto` | 默认模式；若传 `mode_sequence` 则按序列，否则按 4x1/2x2 数量 |
| `mixed` / `both` | 按 `--mode_4x1_wafers` 和 `--mode_2x2_wafers` 数量混跑 |
| `4x1` | 所有产品晶圆只走 4x1 |
| `2x2` | 所有产品晶圆只走 2x2 |
| `custom` | 使用 wafer 级模式序列或稀疏覆盖 |

只跑 4x1：

```powershell
python petri_mip_generator.py   --output_dir generated_instances\MIP   --instance_name mip_4x1_only.lp   --process_mode 4x1   --total_wafers 12   --pec_pool_size 8
```

只跑 2x2：

```powershell
python petri_mip_generator.py 
  --output_dir generated_instances\MIP 
  --instance_name mip_2x2_only.lp 
  --process_mode 2x2 
  --total_wafers 12 
  --pec_pool_size 8
```

### 6.2 wafer 级模式序列

完整指定每片产品晶圆的模式：

```powershell
python petri_mip_generator.py 
  --output_dir generated_instances\MIP 
  --instance_name mip_sequence_case.lp 
  --process_mode custom 
  --total_wafers 8 
  --mode_sequence "4x1,4x1,4x1,2x2,2x2,4x1,2x2,2x2" 
  --pec_pool_size 8
```

`--mode_sequence` 支持 `4x1`、`2x2`，也支持简单别名：`4`、`2`、`full`、`mix`。

### 6.3 wafer 级稀疏覆盖

只覆盖部分晶圆，其他晶圆使用默认模式：

```powershell
python petri_mip_generator.py 
  --output_dir generated_instances\MIP 
  --instance_name mip_wafer_map_case.lp 
  --process_mode custom 
  --total_wafers 8 
  --default_wafer_mode 4x1 
  --wafer_mode_map "W3:2x2,W7=2x2" 
  --pec_pool_size 8
```

### 6.4 cleaning 扩展

`--cleaning_interval` 控制每个 chamber 连续加工多少次后插入纯 PEC cleaning：

- `--cleaning_interval 10`：每个清洗 epoch 最多 10 次 chamber process
- `--cleaning_interval 0`：关闭 cleaning 约束
- `--cleaning_process_time 0`：使用默认清洗时间，等于 `2 * full_process_time`
- `--cleaning_process_time 60`：显式指定清洗时间

示例：

```powershell
python petri_mip_generator.py 
  --output_dir generated_instances\MIP 
  --instance_name mip_cleaning_interval_case.lp 
  --process_mode mixed 
  --mode_4x1_wafers 8 
  --mode_2x2_wafers 6 
  --pec_pool_size 8 
  --cleaning_interval 6 
  --cleaning_process_time 60
```

### 6.5 驻留时间扩展

`--max_module_residency_time` 限制晶圆在模块中的驻留窗口；`--max_robot_residency_time` 限制机械手动作相关的驻留窗口。

```powershell
python petri_mip_generator.py 
  --output_dir generated_instances\MIP 
  --instance_name mip_residency_case.lp 
  --process_mode mixed 
  --mode_4x1_wafers 8 
  --mode_2x2_wafers 6 
  --pec_pool_size 8 
  --max_module_residency_time 100 
  --max_robot_residency_time 100
```

如果时限过紧，模型可能变为 infeasible。

### 6.6 PEC token 约束

`--pec_pool_size` 必须满足：

- 不超过 PEC storage 容量，当前为 10
- 至少为 `4 * num_pm`，当前 `num_pm=2` 时至少为 8
- 能被 `num_pm` 整除

当前设备常用值为 `8` 或 `10`。不要使用消融脚本默认的 `40`。

### 6.7 目标函数软惩罚

实例生成器当前目标为：

```text
min c_max
  + pm_balance_penalty * chamber_load_imbalance
  + chamber_idle_penalty * sum(chamber_idle_slack)
  + chamber_nonprocess_wait_square_penalty * sum(chamber_nonprocess_wait_square)
  + post_process_wait_penalty * sum(pair_post_process_wait)
```

相关参数：

- `--pm_balance_penalty`：鼓励 4x1/2x2 工作在两个 chamber 间更均衡
- `--chamber_idle_penalty`：鼓励同一 CH 上相邻加工组更连续，压缩可避免的组间等待
- `--chamber_nonprocess_wait_square_penalty`：按窗口惩罚 CH 内“有晶圆但未加工”的驻留时间平方，优先压缩 2x2 bridge/tail 前后的长等待
- `--post_process_wait_penalty`：惩罚产品晶圆在 PM 加工完成后等待 VTR 卸载的时间

`chamber_idle_slack` 不是硬约束，而是二级目标中的软惩罚，主要覆盖：

- `full_batch_idle_*`：同一 CH 上相邻 `4x1` 批次之间的空闲
- `full_to_mix_idle_*`：尾部 `4x1` 批次到该 CH 后续 `2x2` 链之间的切换空闲
- `mix_cycle_to_bridge_idle_*`、`mix_tail_idle_*`：`2x2` 链内部允许保留的资源等待；head 完成后立即进入第一个 cycle，bridge 完成后立即进入下一个 cycle

`chamber_nonprocess_wait_square_*` 覆盖所有 CH 占腔但非加工窗口：`4x1` 的装入/旋转/卸出窗口，`2x2` 的 head、每次 bridge、tail，以及 cleaning 的装卸窗口；这些窗口按各自时长分别平方后求和。

如果上游资源尚未就绪，例如 `VTR`、`LLupper`、`AL`、PEC token 或 cleaning 约束阻塞，模型仍允许等待；该惩罚只是在可行且不显著影响主目标的情况下，把甘特图上的空白往前压缩。

## 7. 模型训练和测试扩展功能

### 7.1 policy 类型

常用设置：

```powershell
--policy_type with_token
```

`with_token` 使用 end-token 版本 pointer network，适合 cut selection 序列决策。

### 7.2 高层 cut 数量策略

```powershell
--use_cutsel_percent_policy True
--sel_cuts_percent 0.2
```

含义：

- `use_cutsel_percent_policy=True`：启用高层 cut selection percent policy
- `sel_cuts_percent=0.2`：默认选择 cut 池中约 20% 的 cut，具体会和策略输出共同作用

### 7.3 reward 类型

推荐调度实验使用：

```powershell
--reward_type solving_time
```

其他旧设置如 `lp_solution_value` 会把根节点 LP 目标改善作为 reward，且会改变部分环境参数，不建议作为当前 Petri 调度默认实验。

### 7.4 测试解码方式

测试和消融常用：

```powershell
--test_decode_type beam_search
```

消融实验中：

- `--a3c_decode_type greedy`：A3C-only 使用 greedy
- `--a3c_beam_decode_type beam_search`：A3C+Beam 使用 beam search
- `beam_only` 使用 `heuristic_beam_size`、`heuristic_redundancy_weight` 等启发式参数

## 8. 消融实验输出解释

消融 JSON 中主要字段：

| 字段 | 含义 |
| --- | --- |
| `summary` | 四种方法的均值指标 |
| `results` | 每个方法每个实例的详细结果 |
| `diagnostics` | 自动诊断提示，如无 incumbent、实例数量太少等 |
| `artifacts.comparison_svg` | 消融对比图 |
| `artifacts.gantt_outputs` | 甘特图和前端输出文件 |

常用指标：

- `mean_solving_time`：平均求解时间
- `mean_ntotal_nodes`：平均搜索节点数
- `mean_best_obj`：有 incumbent 的平均目标值
- `mean_primal_dual_gap`：有 incumbent 的平均 gap
- `num_with_solution`：有可行解的实例数

当所有方法都没有 incumbent 时，不要用 best objective 或 gap 排名；此时只能比较时间、节点数和诊断信息。

## 9. 续训和训练曲线扩展

### 9.1 续训

续训时把 runtime config 中：

```json
"experiment": {
  "base_log_dir": "上一轮包含 params.pkl 的 run 目录"
},
"start_epoch": <下一轮起始 epoch>
```

然后重新运行训练命令。注意不要把 `base_log_dir` 指向不存在的目录。

### 9.2 拼接多次训练曲线

```powershell
python stitch_progress_runs.py 
  --runs data\RUN_1 data\RUN_2 
  --output data\stitched_progress.csv 
  --prefer later
```

再绘图：

```powershell
python plot_progress_curves.py 
  --progress_csv data\stitched_progress.csv 
  --output data\stitched_convergence_curves.svg 
  --window 3
```

## 10. 推荐正式规模参数

快速流程用于打通链路。正式实验可逐步提高规模：

```powershell
python petri_mip_generator.py 
  --output_dir generated_instances\MIP 
  --instance_name mip_formal_mixed.lp 
  --num_batches 16 
  --num_pm 2 
  --num_steps 13 
  --process_mode mixed 
  --mode_4x1_wafers 25 
  --mode_2x2_wafers 15 
  --pec_pool_size 8 
  --cleaning_interval 10 
  --cleaning_process_time 60 
  --max_module_residency_time 120 
  --max_robot_residency_time 120 
  --pm_balance_penalty 0.01 
  --chamber_idle_penalty 0.0001
```

训练配置建议：

- `env.scip_time_limit`: 800 或更高
- `algorithm.num_epochs`: 20 或更高
- `trainer.samples_per_epoch`: 4 或更高
- `trainer.n_jobs`: 按 CPU/SCIP 资源设置

消融时间预算建议：

```powershell
--time_limit 3000
```

正式消融至少准备 3 个以上测试实例，否则统计结论不稳定。

## 11. 命令参数速查

本节集中解释前文命令中出现的 PowerShell 参数、脚本参数和配置项。若同一个参数在多个脚本中反复出现，其语义保持一致；区别只在于该脚本是直接生成实例、训练/测试策略，还是做封装实验。

### 11.1 PowerShell 命令写法

| 写法或参数 | 含义 |
| --- | --- |
| `` | PowerShell/cmd 风格的换行续行符。复制多行命令时保留它；如果改成一行，可以去掉。 |
| `latest` | 本项目部分入口支持的特殊路径值；`--test_model_path latest` 自动寻找 `data` 下最新 `params.pkl`，`--solution_json latest` 自动寻找最新测试 solution JSON。 |
| `configs\petri_mip_quick_config.json` | 快速流程配置文件，避免在命令行里临时写 JSON 配置。 |
| `Start-Process "gantt_manual\index.html"` | 用系统默认浏览器打开指定静态前端文件，路径直接写在命令中。 |

### 11.2 `petri_mip_generator.py` 参数

这些参数控制 MIP 实例如何生成，适用于直接运行 `petri_mip_generator.py`，也适用于 `run_petri_a3c_beam.py` 和 `run_ablation_experiments.py` 中同名的实例生成参数。

| 参数 | 默认值 | 含义 |
| --- | --- | --- |
| `--output_dir` | `generated_instances/petri` | LP 实例和 `_model.md` 说明文件的输出目录。 |
| `--instance_name` | `petri_batch10_fullflow_v7.lp` | 原始实例文件名；代码会自动追加日期后缀，生成实际 `.lp` 文件。 |
| `--num_batches` | `10` | 兼容参数，表示候选批次数上界。当前 4x1/2x2 结构会结合产品 PW 对数量自动收紧。 |
| `--num_pm` | `2` | 共享旋转腔数量。当前设备语义固定为 `2`，对应 `CH2` 和 `CH3`。 |
| `--num_steps` | `13` | 兼容参数，保留给旧 Petri/MIP 流程；当前全流程路径主要由显式资源和 wafer 路径决定。 |
| `--total_wafers` | `0` | 产品晶圆总数校验值。为 `0` 时由 `--mode_4x1_wafers`、`--mode_2x2_wafers` 或 `--mode_sequence` 推断。 |
| `--process_mode` | `auto` | 工艺模式策略：`mixed/both` 按两类数量混跑，`4x1` 或 `2x2` 表示单一模式，`custom` 使用 wafer 级配置，`auto` 自动推断。 |
| `--mode_4x1_wafers` / `--full_mode_wafers` | `10` | 走 4x1 工艺的产品晶圆数量；奇数尾片会自动与 PEC 组成 PW 对。 |
| `--mode_2x2_wafers` / `--mix_mode_wafers` | `10` | 走 2x2 工艺的产品晶圆数量；奇数尾片会自动与 PEC 组成 PW 对。 |
| `--mode_sequence` | 空字符串 | wafer 级完整模式序列，例如 `4x1,4x1,2x2`；优先级高于数量参数。 |
| `--wafer_mode_map` / `--wafer_modes` | 空字符串 | wafer 级稀疏覆盖，例如 `W3:2x2,W7=4x1`；适合只改少数晶圆模式。 |
| `--default_wafer_mode` | 空字符串 | `wafer_mode_map` 未覆盖晶圆的默认模式，常与 `--process_mode custom --total_wafers` 配合使用。 |
| `--pec_pool_size` | `8` | 可循环复用的 PEC wafer 数。当前应为 `8` 或 `10`，且至少 `4*num_pm`、不超过 PEC storage 容量、能被 `num_pm` 整除。 |
| `--batch_size` | `4` | 单个旋转腔槽位数；当前四槽 PM 固定为 `4`。 |
| `--big_m` | `10000.0` | 大 M 线性化常数，用于条件约束和时间关系绑定。过小会误伤可行解，过大可能带来数值不稳定。 |
| `--pm_transfer_gap` | `1.0` | 腔体换片间隔兼容参数；当前主要时序由 VTR、旋转、加工和资源互斥约束控制。 |
| `--pm_rotation_time_180` | `2.0` | 旋转腔 180 度转动时间，用于 4x1 前后侧位和 cleaning 装卸衔接。 |
| `--pair_transfer_time` | `4.0` | VTR 单次搬运时间；同时作为 ATR 在源模块取片和目标模块放片的单次时长。 |
| `--atr_transfer_time` | `3.0` | ATR 单段路径移动时间，即 `LP -> AL` 或 `AL -> LL` 的移动时长。ATR 载片 `LP -> AL`、`AL -> LLupper` 总时长均为 `2 * pair_transfer_time + atr_transfer_time`。 |
| `--atr_return_time` | `3.0` | ATR 载片 `LLlower -> LP` 的路径移动时间；该载片动作总时长为 `2 * pair_transfer_time + atr_return_time`。相邻 ATR 动作若需从 `LL` 空载回到 `LP`，还会额外插入 `2 * atr_transfer_time` 的回位时间。 |
| `--aligner_time` | `20.0` | 产品晶圆占用 AL 校准器的最短时间。 |
| `--llupper_time` | `30.0` | 产品晶圆在 `LLupper` 中的最短停留时间。 |
| `--lllower_time` | `25.0` | 产品晶圆在 `LLlower` 中的最短停留时间。 |
| `--full_process_time` | `80.0` | 4x1 满片加工工艺时间。 |
| `--mix_boundary_process_time` | `30.0` | 2x2 边界 cycle 工艺时间，主要对应链首、链尾相关循环。 |
| `--mix_internal_process_time` | `30.0` | 2x2 内部 cycle 工艺时间，主要对应中间产品链循环。 |
| `--cleaning_interval` | `10` | 每个 chamber 连续完成多少次加工 cycle 后插入 cleaning；`0` 表示关闭 cleaning 约束。 |
| `--cleaning_process_time` | `0.0` | cleaning 工艺时间；为 `0` 时使用 `2 * full_process_time`。 |
| `--max_module_residency_time` | `10000.0` | 晶圆在 AL、LL、PM 等模块中的最大驻留时间。 |
| `--max_robot_residency_time` | `10000.0` | 晶圆在 ATR/VTR 搬运动作相关阶段的最大驻留时间。 |
| `--pm_balance_penalty` | `0.01` | 目标函数中的腔体负载均衡惩罚权重。主目标仍是最小化 `c_max`。 |
| `--chamber_idle_penalty` | `1e-4` | 目标函数中的 CH 组间空闲软惩罚权重，用于压缩相邻 `4x1` 批次、`4x1 -> 2x2` 切换和 `2x2` 链内部可避免等待。 |
| `--chamber_nonprocess_wait_square_penalty` | `1e-2` | 高优先级二级目标权重，按窗口惩罚 CH 内有晶圆但未加工的驻留时间平方。 |
| `--post_process_wait_penalty` | `0.05` | 目标函数中的 PM 加工完成至 VTR 卸载开始之间的等待惩罚权重。 |

### 11.3 `parallel_reinforce_algorithm.py` 参数

这些参数控制 cut selection 策略的训练和测试。

| 参数 | 默认值 | 含义 |
| --- | --- | --- |
| `--config_file` | `configs/petri_mip_test_config.json` | 训练/测试基础配置文件路径；命令行参数会覆盖其中部分字段。 |
| `--train_type` | `train` | 运行模式：`train` 训练策略，`test` 加载模型并测试。 |
| `--single_instance_file` | `all` | 指定单个实例文件名；`all` 表示读取实例目录下全部支持的 MIP 文件。 |
| `--sel_cuts_percent` | `0.1` | cut 保留比例基础值，例如 `0.2` 表示约 20%。 |
| `--reward_type` | `lp_solution_value` | 奖励类型；当前 Petri 调度实验推荐 `solving_time`。 |
| `--baseline_type` | `simple` | 强化学习 baseline 类型；常用 `simple`，旧实验中也可能使用 value network。 |
| `--policy_type` | `with_token` | 策略网络类型；`with_token` 表示带 end-token 的 pointer network，适合序列决策。 |
| `--use_cutsel_percent_policy` | `False` | 是否启用高层 cut 数量/比例策略；当前 Petri 实验建议传 `True`。 |
| `--test_decode_type` | `beam_search` | 测试阶段 cut 序列解码方式，常用 `beam_search` 或 `greedy`。 |
| `--instance_type` | `item_placement` | 实例类型标识，用于日志和结果目录命名；Petri 流程建议 `petri_transfer`。 |
| `--time_limit` | `10` | 兼容性时限参数。训练时若使用 `solving_time`，主要仍以配置文件 `env.scip_time_limit` 为准。 |
| `--test_time_limit` | `-1.0` | 测试阶段 SCIP 时限覆盖值；大于 `0` 时覆盖配置文件中的测试时限。 |
| `--seed` | `1` | Python、NumPy、PyTorch 等主随机种子。 |
| `--scip_seed` | `1` | SCIP 求解器随机种子。 |
| `--generate_petri_instance` | `False` | 是否在训练/测试前自动调用 Petri MIP 生成器。 |
| `--petri_instance_dir` | `generated_instances/petri` | 自动生成实例时的输出目录。 |
| `--petri_instance_name` | `petri_batch10_fullflow_v7.lp` | 自动生成实例时的原始文件名，会追加日期。 |
| `--petri_batches` | `10` | 自动生成实例时传给生成器的 `num_batches`。 |
| `--petri_num_pm` | `2` | 自动生成实例时传给生成器的 `num_pm`。 |
| `--petri_num_steps` | `13` | 自动生成实例时传给生成器的 `num_steps`。 |
| `--petri_total_wafers` | `0` | 自动生成实例时的产品晶圆总数校验值。 |
| `--petri_process_mode` | `auto` | 自动生成实例时的工艺模式策略，取值同 `--process_mode`。 |
| `--petri_4x1_wafers` | `20` | 自动生成实例时的 4x1 产品晶圆数量。 |
| `--petri_2x2_wafers` | `20` | 自动生成实例时的 2x2 产品晶圆数量。 |
| `--petri_pec_pool_size` | `8` | 自动生成实例时的 PEC wafer 数量。 |
| `--petri_mode_sequence` | 空字符串 | 自动生成实例时的 wafer 级完整模式序列。 |
| `--petri_wafer_mode_map` / `--petri_wafer_modes` | 空字符串 | 自动生成实例时按晶圆编号覆盖模式。 |
| `--petri_default_wafer_mode` | 空字符串 | 自动生成实例时未覆盖晶圆的默认模式。 |
| `--petri_chamber_idle_penalty` | `1e-4` | 自动生成实例时透传给 `PetriMIPConfig.chamber_idle_penalty`，用于压缩 CH 可避免组间空闲。 |
| `--petri_chamber_nonprocess_wait_square_penalty` | `1e-2` | 自动生成实例时透传给 `PetriMIPConfig.chamber_nonprocess_wait_square_penalty`，用于高权重压缩 CH 非加工占腔等待。 |

### 11.4 `run_petri_a3c_beam.py` 参数

该脚本是“生成单个实例 + 写 runtime config + 调用测试 + 尝试画甘特图”的封装入口。

| 参数 | 默认值 | 含义 |
| --- | --- | --- |
| `--config_file` | `configs/petri_mip_test_config.json` | 基础配置文件；脚本会基于它写出临时 runtime config。 |
| `--test_model_path` | 必填 | 训练好的模型路径，通常是某个 run 目录下的 `params.pkl` 或 `itr_*.pkl`；也可传 `latest` 自动使用 `data` 下最新的 `params.pkl`。 |
| `--instance_dir` | `generated_instances/petri` | 新实例输出目录，同时也是测试实例目录。 |
| `--instance_name` | `petri_batch10_fullflow_v7.lp` | 新实例原始文件名，会自动追加日期。 |
| `--sel_cuts_percent` | `0.2` | 测试时 cut 保留比例基础值。 |
| `--policy_type` | `with_token` | 测试所用策略网络类型，应与训练模型保持一致。 |
| `--use_cutsel_percent_policy` | `True` | 是否使用高层 cut 数量策略，应与训练设置保持一致。 |
| `--test_decode_type` | `beam_search` | 测试解码方式；推荐 `beam_search`。 |
| `--time_limit` | `-1.0` | 覆盖测试 SCIP 时限；大于 `0` 时生效。 |
| `--seed` | `1` | 测试主随机种子。 |
| `--scip_seed` | `1` | SCIP 随机种子。 |
| `--instance_type` | `petri_transfer` | 结果目录命名标识。 |
| `--num_batches`、`--num_pm`、`--num_steps` | 同生成器 | 透传给 `petri_mip_generator.py` 的结构参数。 |
| `--total_wafers`、`--process_mode`、`--mode_4x1_wafers`、`--mode_2x2_wafers`、`--pec_pool_size` | 同生成器 | 透传给生成器的产品/工艺/PEC 参数。 |
| `--mode_sequence`、`--wafer_mode_map`、`--default_wafer_mode`、`--chamber_idle_penalty`、`--chamber_nonprocess_wait_square_penalty` | 同生成器 | 透传给生成器的 wafer 级模式配置、CH 组间空闲软惩罚和 CH 非加工占腔平方惩罚权重。 |

### 11.5 `run_ablation_experiments.py` 参数

消融脚本会比较 `solver_only`、`a3c_only`、`beam_only`、`a3c_beam` 四类方法。

| 参数 | 默认值 | 含义 |
| --- | --- | --- |
| `--config_file` | `configs/petri_mip_test_config.json` | 消融实验基础配置文件。 |
| `--test_model_path` | 空字符串 | A3C 模型路径；可传 `latest` 自动使用最新模型；为空时 A3C 相关方法会跳过，默认 SCIP 和启发式 Beam 仍可运行。 |
| `--instance_dir` | `generated_instances/petri` | 实例目录；生成实例和读取实例都使用它。 |
| `--instance_name` | `petri_batch10_fullflow_v7.lp` | 待生成或待读取的实例名；生成时会追加日期。 |
| `--generate_petri_instance` | `True` | 是否在消融前生成新实例；传 `False` 时读取已有实例。 |
| `--single_instance_file` | 空字符串 | 指定已有实例文件名或路径；为空时使用生成后的实例或 `instance_name`。 |
| `--output_dir` | `ablation_results` | 消融 JSON、CSV、Markdown、对比图和甘特图输出目录。 |
| `--instance_type` | `petri_transfer` | 结果文件名前缀中的实例类型标识。 |
| `--time_limit` | `-1.0` | 覆盖每种方法的 SCIP 求解时限；大于 `0` 时生效。 |
| `--seed` | `1` | 消融主随机种子。 |
| `--scip_seed` | `1` | SCIP 随机种子。 |
| `--sel_cuts_percent` | `0.2` | A3C/Beam 方法中的 cut 保留比例基础值。 |
| `--policy_type` | `with_token` | A3C 策略网络类型，应与训练模型一致。 |
| `--use_cutsel_percent_policy` | `True` | 是否使用高层 cut 数量策略。 |
| `--a3c_decode_type` | `greedy` | `a3c_only` 方法的解码方式。 |
| `--a3c_beam_decode_type` | `beam_search` | `a3c_beam` 方法的解码方式。 |
| `--heuristic_beam_size` | `3` | `beam_only` 启发式搜索的 beam 宽度；越大探索更多但更慢。 |
| `--heuristic_redundancy_weight` | `0.15` | 启发式重排中的冗余惩罚权重，用来降低相似 cut 重复选择。 |
| `--heuristic_max_candidates` | `256` | 启发式方法每轮最多考虑的候选 cut 数。 |
| `--heuristic_max_selected_cuts` | `256` | 启发式方法最多选择并交给求解器的 cut 数。 |
| `--num_batches`、`--num_pm`、`--num_steps` | 同生成器 | 生成消融实例时透传给 `petri_mip_generator.py`。 |
| `--total_wafers`、`--process_mode`、`--mode_4x1_wafers`、`--mode_2x2_wafers`、`--pec_pool_size` | 同生成器 | 生成消融实例时透传给生成器。注意该脚本 `--pec_pool_size` 默认是旧值 `40`，当前设备应显式传 `8` 或 `10`。 |
| `--mode_sequence`、`--wafer_mode_map`、`--default_wafer_mode`、`--chamber_idle_penalty`、`--chamber_nonprocess_wait_square_penalty` | 同生成器 | 生成消融实例时的 wafer 级模式配置、CH 组间空闲软惩罚和 CH 非加工占腔平方惩罚权重。 |

### 11.6 可视化和训练曲线脚本参数

| 脚本 | 参数 | 默认值 | 含义 |
| --- | --- | --- | --- |
| `petri_gantt.py` | `--solution_json` | 必填 | 求解结果 JSON 路径，可来自测试输出；也可传 `latest` 自动使用最新测试 solution JSON。 |
| `petri_gantt.py` | `--output_dir` | 空字符串 | 甘特图前端输出目录；为空时自动使用 `<solution_stem>_gantt`。 |
| `petri_gantt.py` | `--view` | `all` | 视图类型：`full` 全流程，`chambers` 只看 CH2/CH3，`resources` 按资源泳道，`all` 全部生成。 |
| `petri_gantt.py` | `--comparison_svg` | 空字符串 | 可选的消融对比图 SVG；传入后会嵌入同一个前端页面。 |
| `plot_progress_curves.py` | `--progress_csv` | 空字符串 | 要绘制的 `progress.csv`；若传目录，则使用该目录下的 `progress.csv`。 |
| `plot_progress_curves.py` | `--data_dir` | `data` | 未指定 `--progress_csv` 时，从该目录递归寻找最新训练曲线。 |
| `plot_progress_curves.py` | `--output` | 空字符串 | 输出 SVG 路径；为空时写到 `progress.csv` 所在目录。 |
| `plot_progress_curves.py` | `--window` | `3` | 移动平均窗口，用于平滑曲线。 |
| `plot_progress_curves.py` | `--width` | `1600` | 输出 SVG 宽度，单位像素。 |
| `plot_progress_curves.py` | `--columns` | `2` | 曲线面板列数。 |
| `plot_progress_curves.py` | `--title` | `Training Convergence Dashboard` | SVG 顶部主标题。 |
| `plot_progress_curves.py` | `--subtitle` | 空字符串 | 副标题；为空时默认显示源 `progress.csv` 路径。 |
| `plot_progress_curves.py` | `--hide_source_path` | `False` | 隐藏图表中的源文件路径。 |
| `stitch_progress_runs.py` | `--runs` | 必填 | 多个训练 run 目录或 `progress.csv` 路径，按拼接顺序传入。 |
| `stitch_progress_runs.py` | `--output` | 空字符串 | 拼接后的 CSV 输出路径；为空时写到第一个 run 目录。 |
| `stitch_progress_runs.py` | `--prefer` | `later` | 重复 epoch 的保留策略：`later` 保留后面的 run，`earlier` 保留前面的 run。 |

### 11.7 `configs/petri_mip_test_config.json` 常用配置项

| 配置路径 | 含义 |
| --- | --- |
| `experiment.base_log_dir` | 日志和 checkpoint 根目录。首次训练通常设为 `data`；续训时指向包含 `params.pkl` 的旧 run 目录。 |
| `experiment.exp_prefix` | 实验目录名前缀，训练时会和实例名、`instance_type` 组合成输出目录。 |
| `experiment.seed` | 配置文件中的实验随机种子。 |
| `start_epoch` | 起始 epoch。首次训练为 `0`，续训时设为下一轮起始 epoch。 |
| `env.instance_file_path` | 训练环境读取 MIP 实例的目录。 |
| `env.single_instance_file` | 配置文件中的默认实例名，会被命令行 `--single_instance_file` 覆盖。 |
| `env.scip_time_limit` | SCIP 单次求解时限，单位秒；训练耗时主要由它和采样次数共同决定。 |
| `env.presolving`、`env.separating`、`env.conflict`、`env.heuristics` | SCIP 预求解、cut 分离、冲突分析和内置启发式开关。 |
| `env.max_rounds_root` | root 节点最大 cut 分离轮数。 |
| `algorithm.num_epochs` | 总训练 epoch 数。 |
| `algorithm.train_steps_per_epoch` | 每个 epoch 内策略网络更新步数。 |
| `algorithm.batch_size` | 策略更新 batch 大小。 |
| `algorithm.actor_net_lr`、`algorithm.critic_net_lr` | actor 和 critic/value 网络学习率。 |
| `algorithm.reward_type`、`algorithm.baseline_type` | 配置文件中的奖励和 baseline 设置，可被命令行覆盖。 |
| `algorithm.evaluate_freq`、`algorithm.evaluate_samples` | 训练中评估频率和每次评估样本数。 |
| `trainer.samples_per_epoch` | 每个 epoch 采样多少次 SCIP 求解。 |
| `trainer.n_jobs` | 并行采样 worker 数；通常需整除 `samples_per_epoch`。 |
| `net_share.embedding_dim`、`net_share.hidden_dim` | cut 特征嵌入维度和策略网络隐藏维度。 |
| `policy.beam_size` | beam search 宽度。 |
| `cutsel_percent_policy.use_cutsel_percent_policy` | 是否启用高层 cut 数量策略。 |
| `cutsel_percent_policy.train_freq` | 高层策略训练频率。 |
| `devices.global_device`、`devices.multi_devices` | 主进程和 worker 设备设置；无 CUDA 时会回退 CPU。 |
| `test_kwargs.test_instance_path` | 测试实例目录。 |
| `test_kwargs.test_model_path` | 测试时加载的模型路径；快速配置中使用 `latest` 自动定位最新 `params.pkl`。 |
| `test_kwargs.n_jobs` | 测试并行 worker 数。 |

## 12. 故障排查

### 12.1 没有生成甘特图

常见原因：

- solution JSON 中所有记录 `solution` 为空
- SCIP 没有找到 incumbent
- JSON 不是测试或消融输出，而是 runtime config

仍可打开消融 `_gantt/index.html` 查看 comparison SVG。

### 12.2 `pec_pool_size` 报错

当前设备约束下使用：

```powershell
--pec_pool_size 8
```

或：

```powershell
--pec_pool_size 10
```

不要使用 `40`。

### 12.3 模型路径不存在

直接检查是否有训练输出：

```powershell
Get-ChildItem data -Recurse -Filter params.pkl
```

说明：如果没有任何输出，先运行第 2.2 节训练命令；如果有输出，`--test_model_path latest` 会自动使用最新的 `params.pkl`。

### 12.4 测试目录没有 LP

确认：

```powershell
Get-ChildItem generated_instances\petri -Filter "*.lp"
```

说明：如果为空，先运行第 2.1 节生成训练集命令或第 3.1 节封装求解命令；这些命令都会生成 `.lp` 实例。

### 12.5 页面打不开或看不到悬浮标签

直接打开前文固定输出目录：

```powershell
Start-Process "gantt_manual\index.html"
```

说明：如果 `gantt_manual\index.html` 不存在，先运行第 5.1 节甘特图命令。若浏览器安全策略阻止本地 SVG 脚本，可点击页面中的 `Open SVG` 单独打开当前 SVG，或把 `_gantt` 目录放到任意静态文件服务器中访问。

## 13. 文件索引

| 文件或目录 | 用途 |
| --- | --- |
| `petri_mip_generator.py` | 生成全流程 MIP |
| `parallel_reinforce_algorithm.py` | 训练和测试 cut selection 策略 |
| `run_petri_a3c_beam.py` | 单实例生成 + A3C+Beam 测试封装 |
| `run_ablation_experiments.py` | 四类方法消融实验 |
| `petri_gantt.py` | 甘特图 SVG 和交互式前端 |
| `plot_progress_curves.py` | 训练曲线可视化 |
| `stitch_progress_runs.py` | 多次训练曲线拼接 |
| `generated_instances/MIP*` | LP 实例和模型说明 |
| `data/` | 训练日志和模型 |
| `petri_transfer_use_hrl_*` | 测试结果 |
| `ablation_results/` | 消融结果 |

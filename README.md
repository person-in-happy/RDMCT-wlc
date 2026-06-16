# Dual-Source Mixed-Flow Semiconductor Scheduling

本仓库当前以 `petri_mip_generator.py` 为核心，面向“双源混流半导体组合设备”建立了一个**端到端全流程 MIP**：

- 产品晶圆路径：`LP -> ATR -> AL -> ATR -> LLupper -> VTR -> CH -> VTR -> LLlower -> ATR -> LP`
- PEC 晶圆路径：`PEC storage -> VTR -> CH -> VTR -> PEC storage`
- 两个共享旋转腔：`CH2`、`CH3`
- 两种工艺模式：`4x1`、`2x2`
- 目标：从第一片产品晶圆离开 `LP` 到最后一片产品晶圆回到 `LP` 的总时间最短

这一版不再只是 CH 批次级近似，而是显式加入了：

- `ATR` 搬运时序
- `AL` 单槽位占用
- `LLupper` / `LLlower` 双槽位容量
- `VTR` 上下料时序
- 产品 wafer 与 PEC wafer 的完整往返路径
- PEC 晶圆可循环复用的容量约束

目前代码已覆盖端到端 wafer 流转、机器人互斥、模块容量与 chamber 模式切换。设备说明中的“按加工次数触发 CH 清洁”还没有显式建成独立清洁作业，这是当前实现的边界。

## 1. 快速开始

下面的命令都默认在项目根目录执行。路径和参数直接写在命令里；每条命令下面给出说明。需要完整参数说明时再看 `Producedocs/docs/how_to_run_and_get_final_mip_solution.md`。

### 1.1 生成训练集

```powershell
python petri_mip_generator.py ^
  --output_dir generated_instances\petri ^
  --instance_name petri_batch10_fullflow_v7.lp ^
  --num_batches 10 ^
  --num_pm 2 ^
  --process_mode mixed ^
  --mode_4x1_wafers 10 ^
  --mode_2x2_wafers 10 ^
  --pec_pool_size 8 ^
  --chamber_idle_penalty 0.0001
```

说明：该命令会把训练实例生成到 `generated_instances\petri`，并自动给 `.lp` 文件名追加日期后缀；同时会生成对应的模型说明文档。记下终端输出的真实 `.lp` 文件名，下一步训练时填到 `--single_instance_file`。

### 1.2 训练模型

```powershell
python parallel_reinforce_algorithm.py ^
  --config_file configs\petri_mip_quick_config.json ^
  --train_type train ^
  --generate_petri_instance False ^
  --single_instance_file petri_batch10_fullflow_v7_<date>.lp ^
  --sel_cuts_percent 0.2 ^
  --reward_type solving_time ^
  --baseline_type simple ^
  --policy_type with_token ^
  --use_cutsel_percent_policy True ^
  --seed 1 ^
  --scip_seed 1 ^
  --time_limit 300 ^
  --instance_type petri_transfer
```

说明：该命令会读取 `configs\petri_mip_quick_config.json` 中的训练实例目录，默认是 `generated_instances\petri`；请把 `petri_batch10_fullflow_v7_<date>.lp` 替换成上一步真实生成的文件名。训练输出写入 `data`，快速配置默认 `num_epochs=5`、`samples_per_epoch=2`，适合先打通流程。

### 1.3 绘制训练曲线

```powershell
python plot_progress_curves.py ^
  --data_dir data ^
  --output data\latest_convergence_curves.svg ^
  --window 3 ^
  --title "Petri Cut Selection Training"
```

说明：该命令从 `data` 中递归寻找最新的 `progress.csv`，并把训练曲线输出到 `data\latest_convergence_curves.svg`。

### 1.4 运行 A3C + Beam 求解

```powershell
python run_petri_a3c_beam.py ^
  --config_file configs\petri_mip_quick_config.json ^
  --test_model_path latest ^
  --instance_dir generated_instances/petri ^
  --instance_name petri_batch10_fullflow_v7.lp ^
  --num_batches 10 ^
  --num_pm 2 ^
  --process_mode mixed ^
  --mode_4x1_wafers 10 ^
  --mode_2x2_wafers 10 ^
  --pec_pool_size 8 ^
  --chamber_idle_penalty 0.0001 ^
  --instance_type petri_transfer
```

说明：`--test_model_path latest` 会自动使用 `data` 目录下最新的 `params.pkl`。

### 1.5 运行消融实验

```powershell
python run_ablation_experiments.py ^
  --config_file configs\petri_mip_quick_config.json ^
  --test_model_path latest ^
  --instance_dir generated_instances/petri ^
  --instance_name petri_batch10_fullflow_v7.lp ^
  --generate_petri_instance True ^
  --num_batches 10 ^
  --num_pm 2 ^
  --process_mode mixed ^
  --mode_4x1_wafers 10 ^
  --mode_2x2_wafers 10 ^
  --pec_pool_size 8 ^
  --chamber_idle_penalty 0.0001 ^
  --time_limit 300 ^
  --instance_type petri_transfer
```

说明：消融结果写入 `ablation_results`；带模型时会比较 `solver_only`、`a3c_only`、`beam_only`、`a3c_beam`。

### 1.6 画甘特图

```powershell
python petri_gantt.py ^
  --solution_json latest ^
  --output_dir gantt_manual ^
  --view all

Start-Process "gantt_manual\index.html"
```

说明：`--solution_json latest` 会自动读取 `petri_transfer_use_hrl_Trueheuristics_cutsel` 下最新的 `*solutions*.json`；`Start-Process` 会用默认浏览器打开静态前端。

新版甘特图会展示：

- 产品 wafer 的 `ATR / AL / LL / VTR / PM / Return` 全路径阶段
- PEC wafer 的 `VTR / PM / Return` 阶段
- 每片产品 wafer 的最终回仓时间

### 1.7 常用命令参数说明

更完整的逐项说明见 `Producedocs/docs/how_to_run_and_get_final_mip_solution.md` 的“命令参数速查”章节。快速开始里最常用的参数含义如下：

| 参数 | 含义 |
| --- | --- |
| `--output_dir` / `--instance_dir` | 生成或读取 MIP 实例的目录。 |
| `--instance_name` | 实例原始文件名，生成器会自动追加日期后缀。 |
| `--num_batches` | 候选批次数上界兼容参数，当前会结合产品 PW 对数量自动收紧。 |
| `--num_pm` | 旋转腔数量，当前设备固定为 `2`，对应 `CH2` 和 `CH3`。 |
| `--mode_4x1_wafers` | 走 `4x1` 工艺的产品晶圆数量。 |
| `--mode_2x2_wafers` | 走 `2x2` 工艺的产品晶圆数量。 |
| `--pec_pool_size` | 可循环复用的 PEC wafer 数，当前常用 `8` 或 `10`。 |
| `--chamber_idle_penalty` / `--petri_chamber_idle_penalty` | CH 组间空闲软惩罚权重，默认 `0.0001`，用于压缩相邻 `4x1` 批次、`4x1 -> 2x2` 切换和 `2x2` 链内部的可避免等待。 |
| `--pm_rotation_time_180` | 旋转腔 180 度转动时间。 |
| `--pair_transfer_time` | VTR 搬运一个 PW 对的时间。 |
| `--atr_transfer_time` / `--atr_return_time` | ATR 送片和回片动作时间。 |
| `--aligner_time` | 产品晶圆占用 AL 校准器的最短时间。 |
| `--llupper_time` / `--lllower_time` | 产品晶圆在上下 load lock 中的最短停留时间。 |
| `--full_process_time` | `4x1` 满片加工时间。 |
| `--mix_boundary_process_time` / `--mix_internal_process_time` | `2x2` 边界 cycle 和内部 cycle 加工时间。 |
| `--config_file` | 训练、测试或消融实验使用的基础 JSON 配置文件。 |
| `--train_type` | `train` 表示训练，`test` 表示加载模型测试。 |
| `--single_instance_file` | 指定单个 `.lp` 实例；`all` 表示读取实例目录下全部实例。 |
| `--sel_cuts_percent` | cut 保留比例基础值，例如 `0.2` 表示约 20%。 |
| `--reward_type` | 强化学习奖励类型，当前 Petri 调度实验推荐 `solving_time`。 |
| `--baseline_type` | 强化学习 baseline 类型，常用 `simple`。 |
| `--policy_type` | 策略网络类型，当前推荐 `with_token`。 |
| `--use_cutsel_percent_policy` | 是否启用高层 cut 数量策略，当前推荐 `True`。 |
| `--test_model_path` | 训练完成后的模型文件路径；也可传 `latest` 自动使用 `data` 下最新的 `params.pkl`。 |
| `--time_limit` | 测试或消融中的 SCIP 求解时限覆盖值；训练时主要仍看配置文件中的 `env.scip_time_limit`。 |
| `--seed` / `--scip_seed` | 主程序和 SCIP 求解器的随机种子。 |
| `--instance_type` | 实例类型标识，用于日志和结果目录命名，当前推荐 `petri_transfer`。 |
| `--generate_petri_instance` | 消融或训练前是否自动生成新的 Petri/MIP 实例。 |
| `--solution_json` | 甘特图脚本读取的求解结果 JSON 文件；也可传 `latest` 自动读取最新测试 solution JSON。 |

## 2. 当前 MIP 的核心语义

### 2.1 输入层

- 输入给定的是 `4x1` 产品 wafer 数、`2x2` 产品 wafer 数和 PEC wafer 数
- 若使用 `mode_sequence`，则可以按 wafer 级指定每片产品 wafer 的工艺模式

### 2.2 PW 对形成

- 同模式产品 wafer 每两片组成一个 PW 对
- 若某种模式出现奇数尾片，则最后一个 PW 对自动变成 `1 product + 1 PEC`

### 2.3 `4x1` 规则

- 一个启用的 `4x1` 批次包含两组真实可达槽位
- 前侧槽位先装后卸，后侧槽位后装先卸
- 每组槽位恰好承载 1 个 PW 对；若某组没有产品 PW 对，则自动补入 `PEC + PEC`

### 2.4 `2x2` 规则

- 一个 chamber 上的 `2x2` 任务形成连续前缀链
- 链首需要 PEC 头边界
- 链尾需要 PEC 尾边界
- 产品 PW 对要经历 first-pass 与 second-pass 两次相关 chamber 占用

### 2.5 CH 组间连续性软惩罚

- 主目标仍是最小化 `c_max`，即最后一片产品 wafer 回到 `LP` 的时间
- `full_batch_idle_*` 衡量同一 CH 上相邻 `4x1` 批次之间的可避免空闲
- `full_to_mix_idle_*` 衡量尾部 `4x1` 批次到后续 `2x2` 链之间的切换空闲
- `mix_head_idle_*`、`mix_cycle_to_bridge_idle_*`、`mix_bridge_to_cycle_idle_*`、`mix_tail_idle_*` 衡量 `2x2` 链内部可避免等待
- `--chamber_idle_penalty` / `--petri_chamber_idle_penalty` 把这些 slack 加入二级目标；它鼓励加工更连续，但不会在上游资源未就绪或 cleaning 必须插入时强行要求零间隔

### 2.6 训练耗时为什么长

- 训练阶段的每个 sample 都会真正调用一次 SCIP 求解，不是轻量级仿真。
- 默认配置 `50` 个 epoch、每个 epoch `4` 个 sample、`scip_time_limit=300`，仅采样阶段的理论上界就接近 `200 x 300 = 60000s`，约 `16.7` 小时。
- 如果把 `--time_limit` 提到 `3000`，理论上界会放大到约 `166.7` 小时。
- 当前版本已经把 `4x1` 候选批次收紧为最小安全上界，并修正为前后槽位语义；以 `4x1=10, 2x2=10` 为例，模型规模已由 `15086 / 31871` 降到 `6326 / 14179`（变量 / 约束）。

### 2.7 显式资源约束

- `ATR`：按操作任务互斥
- `AL`：一次仅允许 1 片 wafer 占用
- `LLupper` / `LLlower`：各 2 个槽位
- `VTR`：所有 chamber 装卸桥接任务互斥
- `PEC token`：每个 PEC 作业必须占用一个可循环复用的 PEC wafer

## 3. 目录说明

### 3.1 主要目录

- `generated_instances/`：生成的 LP 模型、说明文件、解与可视化结果
- `configs/`：训练与测试配置
- `data/`：训练日志、模型参数、实验结果
- `ablation_results/`：消融实验输出
- `Producedocs/`：论文/专利/运行说明相关文档与 docx 导出脚本

### 3.2 核心脚本

- `petri_mip_generator.py`
  作用：生成当前端到端全流程 MIP，并输出对应的模型说明 Markdown
  使用：直接运行，或由 `run_petri_a3c_beam.py` / `run_ablation_experiments.py` 调用

- `petri_gantt.py`
  作用：将 SCIP 解结果渲染成产品 wafer 与 PEC wafer 的甘特图
  使用：输入求解结果 JSON

- `run_petri_a3c_beam.py`
  作用：一键生成实例并调用训练好的 A3C + Beam 策略进行测试
  使用：适合做单组实例评估与复现实验

- `run_ablation_experiments.py`
  作用：运行普通规则、普通启发式、A3C、A3C+Beam 等对比实验
  使用：适合批量实验与结果汇总

- `parallel_reinforce_algorithm.py`
  作用：learning-to-cut 的训练/测试主入口
  使用：适合训练或在更底层控制 SCIP + RL 流程

### 3.3 RL 与求解相关模块

- `algorithms.py`
  作用：强化学习算法逻辑

- `beam_search.py`
  作用：beam search 解码逻辑

- `cutsel_agent_parallel.py`
  作用：并行 cut selection agent

- `environments.py`
  作用：SCIP / RL 交互环境封装

- `pointer_net.py`、`pointer_net_end_token.py`
  作用：候选 cut 序列建模网络

- `value_net.py`
  作用：价值网络

### 3.4 支撑工具脚本

- `utils.py`
  作用：统计、变量族识别、实验辅助工具

- `path_utils.py`
  作用：路径解析、文件名日期后缀处理

- `scip_imports.py`
  作用：SCIP / PySCIPOpt 兼容导入

- `runtime_compat.py`
  作用：运行时兼容处理

- `global_const.py`
  作用：全局常量

- `logger.py`
  作用：日志工具

## 4. 文档说明

### 4.1 `Producedocs/docs/`

- `petri_per_wafer_path_mip.md`
  作用：说明当前全流程 MIP 如何覆盖产品 wafer、PEC wafer、AL、LL、机器人与 chamber

- `how_to_run_and_get_final_mip_solution.md`
  作用：运行说明，包含生成实例、训练、求解、画图、导出 docx 的命令

- `method_section_3.md`
  作用：论文方法部分第 3 节草稿

- `paper_innovation_points.md`
  作用：论文创新点整理

- `patent_disclosure_dual_source_rotary_a3c_beam_20260329.md`
  作用：当前专利交底书 Markdown 源文件

### 4.2 `Producedocs/` 导出脚本

- `generate_run_guide_docx.py`
  作用：把运行说明 Markdown 导出为 docx

- `generate_patent_disclosure_docx.py`
  作用：把专利交底书 Markdown 导出为 docx

- `docx_markdown_renderer.py`
  作用：Markdown 到 docx 的通用渲染器

## 5. 建议使用顺序

1. 先用 `petri_mip_generator.py` 生成一个小规模实例确认建模配置正确。
2. 再用 `parallel_reinforce_algorithm.py --train_type train` 训练 cut selection 模型，并记录输出目录中的 `params.pkl`。
3. 然后用 `run_petri_a3c_beam.py` 或 `run_ablation_experiments.py` 加载训练好的模型做求解与对比。
4. 求解完成后用 `petri_gantt.py` 检查全流程时序是否符合预期。
5. 若文档有变更，再运行 `Producedocs/generate_run_guide_docx.py` 与 `Producedocs/generate_patent_disclosure_docx.py` 导出正式材料。

## 6. 当前验证情况

本次修改后，`petri_mip_generator.py` 已完成：

- 语法编译检查
- 与 `run_petri_a3c_beam.py`、`run_ablation_experiments.py`、`parallel_reinforce_algorithm.py` 的接口兼容检查
- 小规模实例的建模与求解连通性检查

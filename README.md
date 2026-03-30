# Dual-Source Mixed-Flow Semiconductor Scheduling with MIP + A3C + Beam Search

本项目面向双源混流半导体组合设备调度问题，提供一条完整流程：

1. 生成可由 SCIP 直接读取的 `.lp` MIP 实例。
2. 在该类实例上训练/测试学习式 cut selection 策略。
3. 输出最终求解结果、甘特图以及消融实验结果。

## 当前 MIP 的建模语义

当前版本的 `petri_mip_generator.py` 已经按照“双源混流半导体组合设备调度问题”的要求改成 wafer 级输入：

- 输入直接给出两种模式的产品 wafer 数量：`4x1` 与 `2x2`
- MIP 先把产品 wafer 分配到 PW 对中
- 同一 PW 对中的产品 wafer 必须来自相同模式
- 若某一模式的产品 wafer 数量为奇数，则该模式最后一个 PW 对自动变成“1 片产品 wafer + 1 片 PEC wafer”
- `4x1` 槽位始终需要 2 个 PW 对；若只有 1 个产品承载 PW 对，则用 1 个纯 PEC PW 对补足
- `2x2` 路径中的产品承载 PW 对形成有序前缀，首尾分别使用纯 PEC PW 对作为边界
- 最终目标是最小化所有产品 wafer 的最大完工时间 `c_max`

也兼容旧的 `mode_sequence` 输入方式，但现在推荐优先使用显式模式数量：

- `--mode_4x1_wafers`
- `--mode_2x2_wafers`

## 目录说明

- `petri_mip_generator.py`：生成双源混流调度 MIP
- `parallel_reinforce_algorithm.py`：训练 / 测试主入口
- `run_petri_a3c_beam.py`：一键生成实例并执行 A3C + Beam 测试
- `run_ablation_experiments.py`：运行消融实验
- `petri_gantt.py`：从求解结果生成甘特图
- `generated_instances/petri/`：生成的 `.lp` 与实例说明
- `Producedocs/`：所有说明文档、专利材料、文档生成脚本和素材

## 快速开始

### 1. 生成 MIP 实例

```powershell
python petri_mip_generator.py ^
  --output_dir generated_instances/petri ^
  --instance_name petri_batch10_v3.lp ^
  --num_batches 10 ^
  --num_pm 2 ^
  --mode_4x1_wafers 24 ^
  --mode_2x2_wafers 15 ^
  --pec_pool_size 24
```

这会生成：

- `generated_instances/petri/petri_batch10_v3_<YYYYMMDD>.lp`
- `generated_instances/petri/petri_batch10_v3_<YYYYMMDD>_model.md`

### 2. 用训练好的模型执行测试

```powershell
python run_petri_a3c_beam.py ^
  --config_file configs/petri_mip_test_config.json ^
  --test_model_path data/petri_mip_rl_beam/YOUR_EXPERIMENT_DIR/params.pkl ^
  --instance_dir generated_instances/petri ^
  --instance_name petri_batch10_v3.lp ^
  --num_batches 10 ^
  --num_pm 2 ^
  --mode_4x1_wafers 24 ^
  --mode_2x2_wafers 15 ^
  --pec_pool_size 24 ^
  --sel_cuts_percent 0.2 ^
  --policy_type with_token ^
  --use_cutsel_percent_policy True ^
  --test_decode_type beam_search ^
  --seed 1 ^
  --scip_seed 1 ^
  --instance_type petri_transfer
```

### 3. 运行消融实验

```powershell
python run_ablation_experiments.py ^
  --config_file configs/petri_mip_test_config.json ^
  --test_model_path data/petri_mip_rl_beam/YOUR_EXPERIMENT_DIR/params.pkl ^
  --instance_dir generated_instances/petri ^
  --instance_name petri_batch10_v3.lp ^
  --generate_petri_instance True ^
  --num_batches 10 ^
  --num_pm 2 ^
  --mode_4x1_wafers 24 ^
  --mode_2x2_wafers 15 ^
  --pec_pool_size 24 ^
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

## 旧接口兼容说明

如果仍然使用旧的 `mode_sequence`：

- 可传 wafer 级序列，长度等于产品 wafer 总数
- 也兼容旧的 pair 级偶数序列，长度等于 `total_wafers / 2`
- 但新实验建议直接传 `mode_4x1_wafers` 与 `mode_2x2_wafers`

## 文档位置

所有说明文档、专利交底、论文方法草稿、专利素材和相关生成脚本已经集中移动到 `Producedocs/`，便于把项目核心功能和产出型文档分开维护。

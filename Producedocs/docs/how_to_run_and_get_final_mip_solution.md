# 双源混流半导体组合设备调度：运行说明

## 1. 当前实例生成方式

当前生成器推荐直接传入两种模式的产品 wafer 数量：

- `--mode_4x1_wafers`
- `--mode_2x2_wafers`
- `--pec_pool_size`

生成器会自动完成：

1. 同模式产品 wafer 到 PW 对的分配。
2. 奇数尾对的 `product + PEC` 补位。
3. `4x1` 槽位与 `2x2` 连续块上的调度建模。

`mode_sequence` 仍然可用，但只作为兼容旧流程的方式保留。

## 2. 生成 MIP 实例

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

输出文件：

- `generated_instances/petri/petri_batch10_v3_<YYYYMMDD>.lp`
- `generated_instances/petri/petri_batch10_v3_<YYYYMMDD>_model.md`

## 3. 训练 A3C 风格的 cut selection 策略

```powershell
python parallel_reinforce_algorithm.py ^
  --config_file configs/petri_mip_test_config.json ^
  --train_type train ^
  --generate_petri_instance True ^
  --petri_instance_dir generated_instances/petri ^
  --petri_instance_name petri_batch10_v3.lp ^
  --petri_batches 10 ^
  --petri_num_pm 2 ^
  --petri_num_steps 13 ^
  --petri_4x1_wafers 24 ^
  --petri_2x2_wafers 15 ^
  --petri_pec_pool_size 24 ^
  --single_instance_file petri_batch10_v3.lp ^
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

训练输出目录通常在 `data/` 下。

## 4. 使用 A3C + Beam Search 求最终解

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

典型输出：

- `*_solutions_<YYYYMMDD>.json`
- `*_solutions_<YYYYMMDD>_gantt/`

## 5. 手动生成甘特图

```powershell
python petri_gantt.py ^
  --solution_json petri_transfer_use_hrl_Trueheuristics_cutsel/seed_1_model_params.pkl_RL_max_cuts_root_0.2_solutions_<YYYYMMDD>.json
```

## 6. 运行消融实验

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

## 7. 旧参数兼容

如果仍需复现实验中的旧实例输入，可继续使用：

- `--total_wafers`
- `--mode_sequence`

其中：

- wafer 级 `mode_sequence` 长度应等于 `total_wafers`
- 旧的 pair 级 `mode_sequence` 仅在 `total_wafers` 为偶数时兼容

新实验建议统一改成显式传 `mode_4x1_wafers` 与 `mode_2x2_wafers`。

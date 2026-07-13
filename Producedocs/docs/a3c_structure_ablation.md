# A3C + 结构感知重排：训练与消融协议

本协议只在当前 `universal_mip_role23_v2` 特征和 `role_submodular_v1` 后处理器上训练和测试。旧 checkpoint 的特征或后处理转移语义不同，程序会主动拒绝加载，不能通过手工补写 schema 绕过检查。

## 1. 生成互斥的训练集和留出测试集

```powershell
python generate_structure_benchmark_suite.py `
  --output_root generated_instances\structure_benchmark `
  --warm_start_time_limit 120
```

生成 6 个训练实例和 6 个不参与训练的 holdout 实例。每个实例都生成与 LP 指纹绑定的 warm start，四种消融方法共享同一初始可行解。

## 2. 训练当前结构模型

```powershell
python -u parallel_reinforce_algorithm.py `
  --config_file configs\petri_structure_train_config.json `
  --train_type train `
  --single_instance_file all `
  --sel_cuts_percent 0.2 `
  --reward_type primaldualintegral `
  --baseline_type simple `
  --policy_type with_token `
  --use_cutsel_percent_policy True `
  --seed 1 `
  --scip_seed 1 `
  --instance_type petri_structure23
```

正式配置关闭逐轮在线测试，每 5 轮在独立验证集上评估一次，候选割上限为 128、选中割上限为 30。训练结束后正式消融使用 `best_validation_params.pkl`，不能默认使用最后一轮 `params.pkl`。等待时间已经位于 MIP 次目标中，不再重复叠加到 A3C 的 PDI 奖励。

## 3. 在 holdout 集上做公平消融

将 `<params.pkl>` 替换为训练输出的完整路径：

```powershell
python -u run_ablation_experiments.py `
  --config_file configs\petri_structure_train_config.json `
  --test_model_path <params.pkl> `
  --instance_dir generated_instances\structure_benchmark\holdout `
  --generate_petri_instance False `
  --all_instances True `
  --time_limit 120 `
  --evaluation_node_limit -1 `
  --evaluation_stall_node_limit -1 `
  --warm_start_time_limit 0 `
  --a3c_decode_type greedy `
  --a3c_beam_decode_type greedy `
  --a3c_max_candidates 128 `
  --a3c_max_selected_cuts 30 `
  --proposed_max_candidates 128 `
  --proposed_max_selected_cuts 30 `
  --heuristic_max_candidates 128 `
  --heuristic_max_selected_cuts 30 `
  --output_dir ablation_results `
  --instance_type petri_structure_holdout
```

四组分别为 SCIP Default、A3C Only、Structure Rerank Only、A3C + Structure Rerank。A3C Only 明确关闭后处理；最终方法固定保留 A3C 前缀锚点，再从受限扩展池中按单调子模目标完成剩余割集合。

## 4. 结论门槛

报告中的 `Clear advantage gate` 只有满足以下全部条件才会显示 `PASS`：

- 对每个基线至少有 3 个成对且时间可比的有效实例；
- 最终方法相对每个基线的平均 PDI 改善至少 5%；
- 最终方法相对每个基线的胜率至少为 2/3；
- 没有割选择回调突破统一求解时限。

若门槛未通过，应继续训练或调整结构重排，不应修改基线时限、删除失败实例或只展示有利指标。

## 快速链路检查

CPU 环境可先使用 `configs\petri_structure_smoke_config.json`。该配置仅验证训练、schema、warm start 和四路消融能运行，不用于性能结论。

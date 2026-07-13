# 2026-07-13 消融结果异常：原因、修复与复现

## 结论

`ablation_1.1_wafer17_41_20260713_132750` 不能用于判断本项目算法不如结构感知基线。原实验同时存在实例标签错误、实际选割预算与报告不一致、解码方式不同、停滞节点上限被误当成求解时间四个问题。

修复后，在原图实际对应的 17 片纯 2x2 模型上，以相同 45 秒时间上限、相同 128/30 割预算、关闭节点和停滞节点提前终止完成了四方法复跑：

| 方法 | 状态 | 最好 makespan | SCIP 时间/s | Wall time/s | 节点数 | Gap | PDI | Cut callback/s |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| SCIP Default | timelimit | 1166 | 45 | 44.636 | 15426 | 0.23517 | 1654.230 | 0 |
| A3C Only | timelimit | 1290 | 45 | 44.982 | 17756 | 0.36653 | 1842.724 | 0.1950 |
| Structure Rerank Only | optimal | 1018 | 37 | 37.809 | 9332 | 0 | 1403.332 | 1.2881 |
| A3C + Structure Rerank | optimal | 1018 | 39 | 38.213 | 4248 | 0 | 1821.610 | 0.1296 |

本项目方法相对结构基线保持相同最优解，节点数减少 54.5%，callback 时间减少约 90%，但本次 wall time 慢 0.404 秒，PDI 高 29.8%。另一次只运行这两个方法的诊断中，本项目 wall time 为 37.333 秒、结构基线为 38.752 秒，快慢次序相反，表明 1 至 2 秒的单次差异受运行顺序和系统负载影响，不能作为稳定结论。当前 checkpoint 不能宣称全面优于结构基线；它体现了更高的节点效率，但早期 primal/dual 轨迹仍需通过独立验证集选模和多样化重训改善。

原始修复后结果位于：

- `ablation_results/fair_fix_20260713/ablation_wafer17_22_fixed_time_diagnostic_20260713_140346.json`
- `ablation_results/fair_fix_20260713/ablation_wafer17_22_fixed_time_full_20260713_141918.json`
- `ablation_results/fair_fix_20260713/ablation_wafer17_41_fixed_fair_20260713_135158.json`

## 原实验为什么会误导

### 1. `wafer17_41` 实际生成成了纯 2x2

项目命名中的 `41` 表示 4x1，不是 41 片。旧文件 `wafer17_41_20260711.lp` 的模型说明却是：

- 4x1 晶圆：0
- 2x2 晶圆：17

它与 `wafer17_22_20262711.lp` 的 SHA-256 完全相同：

`b14acbbfcce9a9d11fc193bae6d56a43e45a371ddea9c2bd9b637f8fa766949f`

正确的 17 片纯 4x1 文件是 `wafer17_41_fixed_20260711.lp`，SHA-256 为：

`272659b0a5bf13ffb13973de1e4e48bc497d1f7bd68bdda003eb67bbe3c61377`

消融脚本现在会读取模型说明并核对 `_41`、`_22` 标签，同时写出文件大小和 SHA-256；标签不符或全实例实验中出现重复内容时直接终止。

### 2. 报告预算不是实际预算

旧报告显示结构基线使用 256/256、本项目使用 128/16，但环境又把这些值静默覆盖成配置中的 128/30。现在环境只会取“方法设置与环境安全上限的较小值”，结果文件同时记录申报预算和实际预算。

正式消融默认要求 A3C-only、结构基线、本项目三者使用相同候选割/选中割上限；不同预算会直接报错。

### 3. 旧命令使用了不同的神经解码方式

旧命令让 A3C-only 使用 greedy，让本项目使用 beam search，因此测到的时间差混合了结构重排贡献与神经 beam 的额外开销。正式消融现在要求两种学习方法的 decode type 相同，推荐都使用 greedy。

### 4. 33 秒和 37 秒是“到达停滞节点数”的时间

旧配置设置 `scip_stall_node_limit=8000`。不同方法每个节点的成本不同，所以谁先结束并不等于谁更快得到同质量解。正式消融默认关闭 node limit 和 stall-node limit，只保留统一 wall-time；同时报告 makespan、gap、PDI、节点数和 callback 时间。

## 可直接复跑的命令

先把 `<params.pkl>` 替换成当前模型或新训练得到的 `best_validation_params.pkl` 完整路径。

```powershell
python -u run_ablation_experiments.py `
  --config_file configs\petri_mip_test_config.json `
  --test_model_path <params.pkl> `
  --instance_dir generated_instances\test `
  --instance_name wafer17_22_20262711.lp `
  --single_instance_file wafer17_22_20262711.lp `
  --generate_petri_instance False `
  --time_limit 45 `
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
  --seed 1 `
  --scip_seed 1 `
  --instance_type wafer17_22_fixed_time `
  --output_dir ablation_results\formal_fixed_time
```

纯 4x1 功能验证必须使用 `wafer17_41_fixed_20260711.lp`，不能再使用标签错误的 `wafer17_41_20260711.lp`。该模型通常在根节点附近即求到最优，更适合检查实例和甘特图，不适合证明 cut-selection 优势。

## 下一轮训练必须怎样做

先生成互斥的训练集和验证集：

```powershell
python generate_structure_benchmark_suite.py `
  --output_root generated_instances\structure_benchmark `
  --warm_start_time_limit 120
```

再训练：

```powershell
python -u parallel_reinforce_algorithm.py `
  --config_file configs\petri_mip_formal_wafer18_config.json `
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

训练程序每 5 个已完成 epoch 在 `generated_instances/structure_benchmark/holdout` 上评估平均 PDI，并保存 `best_validation_params.pkl`。正式消融应使用该文件；`params.pkl` 只是最后一轮，不再默认代表最佳模型。

论文实验至少运行 3 个训练种子和多个互斥实例，报告均值、标准差、配对胜率和置信区间。若本项目在验证集或完整测试集上的 PDI 未稳定优于基线，应继续训练或改进奖励，而不是删除不利实例或更换统计口径。

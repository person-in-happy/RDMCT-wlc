# 消融实验诊断与改进建议

## 当前结果的核心判断

`ablation_results/ablation_petri_transfer_20260529_165929.*` 这组结果不能直接说明 A3C、Beam 或 A3C+Beam 没有优势。更准确的解释是：当前测试实例过大，所有方法都没有找到可行解，因此实验没有进入可比较的解质量阶段。

关键证据：

- 4 个方法的 `status` 都是 `timelimit`。
- 4 个方法的 `best_obj` 都是空值，`nonzero_solution_vars` 都是 0。
- 4 个方法的 `primal_dual_gap` 都是 `1e20`，这是无 incumbent solution 时的占位级结果，不应作为有效 gap 比较。
- `ntotal_nodes` 都是 1，说明求解基本停留在根节点，主要困难来自根 LP/预求解/可行解发现，而不是分支树上的 cut selection 策略差异。
- 仅测试 1 个实例，缺少跨实例、跨随机种子的统计支撑。

因此，“无明显优势”的主要原因不是算法已被充分证伪，而是实验设置没有给 cut selection 算法提供有效发挥和度量空间。

## 可能原因

1. 实例规模过大。当前 `mip_ablation_cleaning_20260529.lp` 约 152k 变量、359k 约束，根节点阶段已经足以消耗 3000 秒。
2. 没有可行初始解。cut selector 主要影响割选择和 LP bound 推进，不能替代构造型排程器提供 incumbent。
3. 训练分布与测试分布可能不一致。配置中模型来自 `mip_clean_20260508.lp` 相关训练，而本次测试实例是更大的 cleaning ablation 实例。
4. 指标口径此前偏乐观。脚本把“完成一次超时运行”计为 valid run，但没有区分是否找到可行解。
5. 启发式 `beam_only` 在大割池上存在额外开销。旧实现会对大量候选割做 beam 组合扩展和相似度计算，导致自身耗时可能掩盖求解贡献。

## 已做代码改进

- `run_ablation_experiments.py`
  - 新增 `n_solutions`、`has_solution`、`comparison_valid` 字段。
  - 汇总表区分 `Completed`、`With Incumbent`、`Solved`。
  - 解质量指标只统计有 incumbent 的运行，避免把 `1e20` gap 当作有效均值。
  - 报告中自动写入诊断提示，例如“无可行解”“仅根节点”“实例数量不足”。

- `cutsel_agent_parallel.py`
  - 为 `HeuristicBeamCutSelectAgent` 增加 `max_candidates` 和 `max_selected_cuts`。
  - 只在候选池内计算相似度矩阵，避免对全量 cuts 做二次开销。
  - 默认候选池和选择上限均为 256，降低大实例上 `beam_only` 的额外时间。

## 下一轮实验建议

1. 先做可解性分层实验：
   - small：`4x1=10, 2x2=10`
   - medium：`4x1=25, 2x2=15`
   - large：`4x1=51, 2x2=47`

2. 每个规模至少运行 5 到 10 个实例或随机种子，报告均值、标准差和胜率，而不是单实例结论。

3. 把可行解阶段和 cut selection 阶段分开：
   - 构造型启发式或 MIP start 先提供 incumbent。
   - A3C/Beam 再比较相同时间预算下的 bound、gap、primal-dual integral、最终 makespan。

4. 对 `sel_cuts_percent` 做扫参：
   - 推荐先试 `0.05, 0.10, 0.15, 0.20`。
   - 大实例上不建议一开始使用过高比例。

5. 对 Beam 开销单独报告：
   - 记录 cut selector 调用次数、平均候选割数量、策略推理时间。
   - 让论文中的比较区分“求解器时间”和“策略额外开销”。

## 推荐复跑命令

对当前大实例复跑时，先保留实例并限制启发式 beam 开销：

```powershell
python run_ablation_experiments.py ^
  --config_file configs/petri_mip_test_config.json ^
  --generate_petri_instance False ^
  --instance_dir generated_instances/MIP ^
  --instance_name mip_ablation_cleaning_20260529.lp ^
  --single_instance_file mip_ablation_cleaning_20260529.lp ^
  --time_limit 3000 ^
  --heuristic_max_candidates 128 ^
  --heuristic_max_selected_cuts 128 ^
  --instance_type petri_transfer
```

若要验证算法优势，优先用中小规模实例和已训练模型复跑，再逐步放大规模。

# AAAI-27 代码修改摘要

## 新增文件

- `aaai/run_aaai.ps1`
  - 为零基础用户提供 check、quick、generate-data、train、tune、benchmark、benchmark-all 和 paper 统一入口；
  - 所有默认输出均限制在 `aaai/`。

- `aaai/code/run_aaai27_benchmarks.py`
  - 统一运行 SCIP Default、Adaptive Cut Selection、HEM 和本文方法；
  - 支持多 seed、多 suite、跨规模、跨 MILP；
  - 输出 raw CSV、summary CSV、JSON 和 Markdown；
  - 统计 mean/std/median、shifted geometric mean、配对 speedup 和 bootstrap 95% CI。

- `aaai/code/tune_aaai27_acs.py`
  - 在 validation 集上调优四个 SCIP hybrid cut-selection 权重；
  - 输出完整网格、验证指标和最终权重。

- `aaai/code/combine_aaai27_runs.py`
  - 合并多个训练 seed 的 benchmark；
  - 去重与训练 seed 无关的 SCIP/ACS 基线；
  - 保留学习方法的 training seed 并重新生成 raw/summary/report。

- `aaai/code/generate_aaai27_petri_suites.py`
  - 生成 wafer 数量和配比互不泄漏的 Petri train/validation/test。

- `aaai/code/generate_aaai27_milp_families.py`
  - 生成 set cover、knapsack、facility location 和 independent set。

- `aaai/configs/aaai27_benchmark_suites.json`
  - 定义 Petri、多类 MILP 和 MIPLIB suite。

- `aaai/configs/aaai27_quick_suites.json`
  - 将流程演示数据和正式数据彻底隔离，避免 quick test 污染 train/validation/test。

- `aaai/configs/aaai27_hem_config.json`
  - HEM 测试网络结构，输入维数 13。

- `aaai/configs/aaai27_proposed_config.json`
  - 本文方法测试网络结构，输入维数 23。

- `aaai/configs/aaai27_hem_train.json`
  - HEM 训练配置。

- `aaai/configs/aaai27_proposed_train.json`
  - 本文方法训练配置；开启精简、限长、滚动文本日志。

- `aaai/docs/universal_mip_structure_features.md`
  - 面向非专业读者逐维解释新的通用 MIP 结构特征和 checkpoint 兼容性。

## 修改文件

- `utils.py`
  - 新增严格的 13 维 HEM 特征提取器；
  - 将原变量名前缀特征替换为读取 SCIP 元数据的通用 10 维角色与行几何特征。

- `logger.py`
  - 增加文本日志白名单、大小上限和滚动备份；`progress.csv` 保持完整。

- `algorithms.py`、`parallel_reinforce_algorithm.py`
  - checkpoint 写入并检查 `cut_feature_schema`，拒绝误用旧 23D 权重；
  - 精简子进程和训练批次的高频调试输出。

- `cutsel_agent_parallel.py`
  - 根据 checkpoint 输入维数切换 HEM/本文方法；
  - HEM 分支关闭 Petri 结构特征和结构 reranking；
  - 本文分支保留 23 维结构输入和 family-aware selection。

## 已完成验证

```powershell
python -m py_compile aaai\code\run_aaai27_benchmarks.py aaai\code\tune_aaai27_acs.py aaai\code\generate_aaai27_milp_families.py cutsel_agent_parallel.py utils.py
python aaai\code\run_aaai27_benchmarks.py --help
python aaai\code\generate_aaai27_milp_families.py --help
```

另已完成一次临时 smoke test：

- SCIP Default 与 ACS 参数化 baseline 均能读取 Petri LP 并返回结果；
- 旧 23 维 checkpoint 已明确标记为语义不兼容，必须用通用角色特征重新训练；
- runner 能生成 JSON、raw CSV、summary CSV 和 Markdown。

smoke test 的 3 秒/1 节点结果只验证软件链路，不可写入论文性能表。

## 仍需运行

- 重新训练 5 个 HEM 13 维 checkpoint；
- 重新训练 5 个本文 23 维 checkpoint；
- validation ACS tuning；
- Petri 10--20 SCIP seeds；
- 四类 MILP 5--10 seeds；
- MIPLIB2017 held-out 测试；
- Wilcoxon + Holm 统计检验；
- 独立 schedule-feasibility checker。
